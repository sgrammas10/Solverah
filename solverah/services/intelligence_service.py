"""Career-path preferences and O*NET-backed path suggestions.

``path_suggestions`` was the single largest handler in ``app.py`` -- roughly 190
lines that read eleven different keys out of the profile document, assembled two
dataclasses from them, called the scorer and the narrator, and shaped a payload.
Most of that length is the extraction, so that is what comes out first:
:func:`build_user_profile` and :func:`build_user_context` are pure functions of
the profile blob and the intake row, and the orchestration around them is now
short enough to read in one screen.

Two behaviours are preserved deliberately, and one is gone.

* **A GET that writes.**  When ``career_status`` was unset, the service derived
  it from an experience entry ending in "Present"/"Current" and *committed* the
  derivation mid-read -- the same class of problem as P0-3.  **Fixed in Phase 3.**
  The derivation still happens and still feeds the scorer; it is simply not
  persisted.  No backfill replaces it, unlike the culture-preferences write in
  ``matching_service``, and the difference is that this derivation is a pure
  function of the profile document already in hand -- there is nothing to save by
  storing it, and storing it wrote a *guess* into a field the user is the
  authority on.  ``PATCH /me/career-status`` remains the only thing that sets it.
* **Empty results are a 500, not a 200.**  If scoring returns nothing for a
  complete profile, O*NET gave us nothing, and that is a transient upstream
  failure rather than a message the user can act on.
* **Missing OPENAI_API_KEY degrades rather than fails.**  ``score_paths`` takes
  ``None`` for the client and falls back to non-embedding scoring.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from model import User, db
from solverah.infra import llm
from solverah.repositories import profile_repository
from solverah.services import path_cache

__all__ = [
    "IntelligenceResult",
    "PATH_PRIORITIES",
    "MOVE_INTENTS",
    "read_path_preferences",
    "SENIORITY_INTENTS",
    "build_user_context",
    "build_user_profile",
    "derive_career_status",
    "path_suggestions",
    "save_path_preferences",
]

MOVE_INTENTS = {"stay_in_field", "adjacent", "fresh_start"}
SENIORITY_INTENTS = {"move_up", "stay_lateral", "open"}
PATH_PRIORITIES = {
    "pay_title",
    "interesting_work",
    "work_life_balance",
    "learning_growth",
}

#: Values of ``endDate`` that mean the user still holds the role.
_CURRENT_ROLE_MARKERS = ("present", "current")


@dataclass
class IntelligenceResult:
    """A service outcome the API layer turns into a response."""

    status: int
    body: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status < 400


def _error(status: int, message: str) -> IntelligenceResult:
    return IntelligenceResult(status=status, body={"error": message})


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def save_path_preferences(user: User, data: Dict[str, Any]) -> IntelligenceResult:
    """Persist the three career-search preference fields.

    All three are required and validated against closed sets; an unknown value
    is a 400 rather than being stored, because the scorer branches on them and a
    typo would silently change ranking.
    """
    move_intent = data.get("move_intent")
    seniority_intent = data.get("seniority_intent")
    priority = data.get("priority")

    if move_intent not in MOVE_INTENTS:
        return _error(400, "Invalid move_intent")
    if seniority_intent not in SENIORITY_INTENTS:
        return _error(400, "Invalid seniority_intent")
    if priority not in PATH_PRIORITIES:
        return _error(400, "Invalid priority")

    preferences = {
        "move_intent": move_intent,
        "seniority_intent": seniority_intent,
        "priority": priority,
    }
    profile_repository.update_document(
        user.id, lambda existing: {**existing, "path_preferences": preferences}
    )
    db.session.commit()

    path_cache.invalidate(user.id)
    return IntelligenceResult(status=200, body={"message": "Preferences saved"})


# ---------------------------------------------------------------------------
# Profile extraction (pure)
# ---------------------------------------------------------------------------

def derive_career_status(profile: Dict[str, Any]) -> Optional[str]:
    """Infer ``career_status`` from experience, or None.

    If any entry has an ``endDate`` of "Present" or "Current" the user is
    employed. Anything else is unknowable from the profile alone, so the caller
    asks the user rather than guessing.
    """
    for entry in profile.get("experience") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("endDate", "")).strip().lower() in _CURRENT_ROLE_MARKERS:
            return "employed"
    return None


def _archetype_fields(intake) -> Tuple[str, str, List[str]]:
    """Work Pulse archetype, its description, and the emerging-signal sentences.

    The multi-sentence description and the signal *descriptions* are used rather
    than the short labels: they embed far more meaningfully against O*NET
    work-activity language than a title like "Independent Worker" does.
    """
    if not intake or not isinstance(intake.wpl_result, dict):
        return "", "", []

    result = intake.wpl_result
    signals = result.get("emerging_signals") or []
    tags = [
        signal.get("description") or signal.get("title", "")
        for signal in signals
        if isinstance(signal, dict) and (signal.get("description") or signal.get("title"))
    ]
    return (
        result.get("archetype", ""),
        result.get("archetype_description", ""),
        tags,
    )


def build_user_profile(profile: Dict[str, Any], intake, career_status: str):
    """Assemble the scorer's ``UserProfile`` from the profile blob.

    Pure apart from the imports: no database read, no network. That is the
    point -- path scoring is deterministic and this is the whole of its input,
    so a scoring regression can be reproduced from a saved blob.
    """
    from backend.services.path_scoring import UserProfile, UserSkill

    skills_raw = profile.get("skills") or []
    skill_levels = profile.get("skill_levels") or {}
    user_skills = [
        UserSkill(name=skill, level=skill_levels.get(skill, "beginner"))
        for skill in skills_raw
        if isinstance(skill, str)
    ]

    archetype, archetype_description, work_style_tags = _archetype_fields(intake)

    # FocusType scoring produces no rich description -- fall back to the label.
    focus_type = (profile.get("focus_type_result") or {}).get("archetype") or None

    # Prefer the LLM-generated description over the short archetype label.
    manager_match_result = profile.get("manager_match_result") or {}
    manager_match_desc = (
        manager_match_result.get("archetype_description")
        or manager_match_result.get("archetype")
        or None
    ) if manager_match_result else None

    current_title = None
    experience = profile.get("experience") or []
    if experience and career_status != "first_job":
        first_exp = experience[0] if isinstance(experience[0], dict) else {}
        current_title = first_exp.get("position") or first_exp.get("title") or None

    preferences = profile.get("path_preferences") or {}

    return UserProfile(
        current_title=current_title,
        career_status=career_status,
        skills=user_skills,
        archetype=archetype,
        archetype_description=archetype_description,
        move_intent=preferences.get("move_intent"),
        seniority_intent=preferences.get("seniority_intent"),
        priority=preferences.get("priority"),
        focus_type=focus_type,
        manager_match=manager_match_desc,
        work_style_tags=work_style_tags,
    )


def build_user_context(profile: Dict[str, Any], intake, career_status: str):
    """Assemble the narrator's ``UserContext`` from the profile blob."""
    from backend.services.path_narrative import UserContext

    archetype, _, _ = _archetype_fields(intake)
    skills_raw = profile.get("skills") or []
    preferences = profile.get("path_preferences") or {}

    return UserContext(
        archetype=archetype,
        management_preferences=profile.get("manager_match_result") or {},
        career_status=career_status,
        top_skills=[s for s in skills_raw[:5] if isinstance(s, str)],
        move_intent=preferences.get("move_intent"),
        seniority_intent=preferences.get("seniority_intent"),
        priority=preferences.get("priority"),
    )


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

def path_suggestions(user: User, logger) -> IntelligenceResult:
    """Score and narrate career-path suggestions, caching the result per user."""
    from backend.services.onet_client import OnetClient
    from backend.services.path_narrative import NarrativeGenerationError, generate_narratives
    from backend.services.path_scoring import score_paths

    cached = path_cache.get(user.id)
    if cached is not None:
        return IntelligenceResult(status=200, body=cached)

    profile = profile_repository.load_document(user.id)
    career_status = profile.get("career_status")
    if not career_status:
        # Derive from experience before giving up. This used to persist and
        # commit the derivation -- the write on a GET named in the module
        # docstring -- and now applies it to the in-memory document only. The
        # scorer sees exactly what it saw before; the database does not.
        career_status = derive_career_status(profile)
        if not career_status:
            return _error(400, "career_status_not_set")
        profile = {**profile, "career_status": career_status}

    user_profile = build_user_profile(profile, user.intake, career_status)

    try:
        onet_client = OnetClient()
        try:
            openai_client = llm.get_openai_client()
        except RuntimeError:
            # No API key: score_paths falls back to non-embedding scoring rather
            # than failing the request.
            openai_client = None
        scored = score_paths(user_profile, onet_client, openai_client)
    except Exception:  # noqa: BLE001 -- logged with a traceback
        logger.exception("Path scoring failed for user %s", user.id)
        return _error(500, "Unable to score career paths")

    if not scored:
        # Profile is complete but O*NET returned nothing -- treat as a
        # transient service issue rather than a profile problem.
        logger.warning(
            "Empty scored list for user %s (title=%r, skills=%d)",
            user.id,
            user_profile.current_title,
            len(user_profile.skills),
        )
        return _error(500, "Unable to score career paths")

    try:
        suggestions = generate_narratives(
            scored, build_user_context(profile, user.intake, career_status)
        )
    except NarrativeGenerationError:
        logger.exception("Path narrative generation failed for user %s", user.id)
        return _error(500, "Unable to generate path narratives")

    score_map = {path.onet_code: path.score for path in scored}
    payload = {
        "suggestions": [
            {
                "onet_code": s.onet_code,
                "title": s.title,
                "why_text": s.why_text,
                "profile_dimensions": s.profile_dimensions,
                "match_score": score_map.get(s.onet_code, 0.0),
            }
            for s in suggestions
        ],
        "career_status": career_status,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }

    path_cache.store(user.id, payload)
    return IntelligenceResult(status=200, body=payload)


def read_path_preferences(user: User) -> IntelligenceResult:
    """The three saved preferences, or nulls when the user has not set them.

    New in Phase 1b. The endpoint this pairs with was write-only, so a client
    that wanted to show the user their own answers had to either keep a copy or
    read them out of the profile blob -- which is exactly the coupling to
    the profile document's shape that putting schemas at the API boundary exists
    to stop.
    """
    saved = profile_repository.load_document(user.id).get("path_preferences") or {}
    return IntelligenceResult(
        status=200,
        body={
            "move_intent": saved.get("move_intent"),
            "seniority_intent": saved.get("seniority_intent"),
            "priority": saved.get("priority"),
        },
    )
