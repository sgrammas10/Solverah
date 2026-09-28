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
  complete profile, the corpus or the embedding provider gave us nothing, and
  that is a transient upstream failure rather than a message the user can act
  on.  **A profile with no title and no skills is the one exception** (F-4): the
  scorer raises ``InsufficientProfile`` for it and this module answers
  ``400 profile_incomplete``, which the client can act on.
* **Missing OPENAI_API_KEY degrades rather than fails.**  ``score_paths`` takes
  ``None`` for the client and falls back to non-embedding scoring.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from model import User, db
from solverah.infra import llm
from solverah.repositories import (
    path_feedback_repository,
    path_fit_repository,
    profile_repository,
)
from solverah.services import path_cache

__all__ = [
    "IntelligenceResult",
    "PATH_PRIORITIES",
    "MOVE_INTENTS",
    "read_path_preferences",
    "SENIORITY_INTENTS",
    "build_user_context",
    "build_user_profile",
    "cached_path_suggestions",
    "clear_path_feedback",
    "derive_career_status",
    "path_fit",
    "path_suggestions",
    "record_path_feedback",
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

#: W-12.  How many cards BELOW the page the scoring job scores and narrates.
#:
#: It is the depth of the *scoring* reserve, not the size of the narrative store:
#: since W-14 `path_cache.store_reserve` holds all ``PAGE_SIZE + RESERVE_DEPTH``
#: narratives, page included, so a removed-and-restored card finds its prose too.
#:
#: Ten, measured rather than picked.  Replaying three taps the way `_rescore`
#: does, on three F-2 profiles, surfaced 12, 14 and 20 distinct occupations --
#: so a reserve of ten on top of the page of ten covers all three, and the worst
#: of them exactly.  Five would leave the third profile's first tap short on its
#: own (six un-narrated cards).  Twenty more would double the job's second
#: batch for the tail of a distribution nobody has walked.
#:
#: The cost is one extra narrator completion per job -- ~1,520 tokens, about
#: +$0.0007 -- and no wall time, because the two batches run on threads
#: (`path_narrative.generate_narratives_batched` has the measurements).
RESERVE_DEPTH: int = 10


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
    path_fit_repository.invalidate(user.id)  # F-5, with the Tier-1 cache below
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

def cached_path_suggestions(user: User) -> Optional[IntelligenceResult]:
    """The cached suggestions payload for *user*, or None on a miss.

    The whole of what ``GET /me/path-suggestions`` serves since Phase 3c. The
    fan-out to O*NET and OpenAI lives in :func:`path_suggestions`, which only a
    worker runs now -- a miss here is the route's cue to point the client at
    ``POST /me/path-suggestion-jobs`` rather than to compute inline.
    """
    cached = path_cache.get(user.id)
    if cached is None:
        return None
    return IntelligenceResult(status=200, body=cached)


def path_suggestions(user: User, logger) -> IntelligenceResult:
    """Score and narrate career-path suggestions, caching the result per user.

    Since Phase 3c this runs only off the request path -- `scoring_jobs` calls
    it from a worker, and the cache it stores into is what the GET serves. Kept
    whole rather than split from its cache write because the succeeded job and
    the warm cache must never disagree about what was computed.
    """
    from backend.services.onet_client import OnetClient
    from backend.services.path_narrative import (
        NarrativeGenerationError,
        generate_narratives_batched,
    )
    from backend.services.path_scoring import (
        PAGE_SIZE,
        CorpusUnavailable,
        InsufficientProfile,
        score_paths,
    )

    # Imported here, not at module scope: `path_wants_service` builds its panel
    # out of this module's `build_user_profile`, so the two import each other and
    # only one of them can win at import time. The deferral goes on this side
    # because it already defers every other heavy import in the function.
    from solverah.services import path_wants_service

    # W-14. A hit is only a hit if the thing cached was NARRATED.
    #
    # `_rescore` writes into this cache too, and on a cold worker it has no
    # reserve and no payload to carry prose from, so what it writes is ten
    # fallback sentences with no pills. Before this check the next job read that
    # back and served it -- and so did every reload after it, until an unrelated
    # profile write happened to invalidate the entry. In production that is
    # every user's first tap after a deploy or a worker recycle: the list they
    # came back to had lost its prose and could not get it back.
    #
    # Of the two shapes the brief offered, this is the one that keeps the other
    # three promises intact. Having `_rescore` skip the store instead would also
    # stop the poisoning, but it would take `GET /me/path-suggestions` back to a
    # miss straight after a tap and drop `feedback` off the payload a reload
    # polls -- W-13's finding, re-opened. Storing it and declining to *serve it
    # as narration* separates the two jobs the cache does: it is still the
    # record of what the user is looking at, and it is no longer an excuse to
    # skip the narrator.
    cached = path_cache.get(user.id)
    if cached is not None and path_cache.is_narrated(user.id):
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
        # F-6: the cold generation honours the user's stored judgements too.
        # Without this a reload after a deploy -- `path_cache` is per worker and
        # lost on one -- would silently rebuild the DEFAULT list while the rows
        # recording what the user asked for sat untouched in the database. The
        # judgements are user state, not a property of one re-rank, so every
        # generation reads them.
        judgements = path_feedback_repository.verdicts_for_user(user.id)
        # W-4: the cold generation honours the stored wants for the same reason
        # it honours the judgements -- `path_cache` is per worker and lost on a
        # deploy, so without this a reload would rebuild the ranking as though
        # the user had never answered the panel. Read by ALL THREE intents,
        # unlike the judgements: a want is the user's own statement about their
        # own day, not an opinion about a card the scorer chose (design doc §8.3).
        wants = path_wants_service.wants_for_scoring(
            user, user_profile, onet_client, openai_client
        )
        scored = score_paths(
            user_profile,
            onet_client,
            openai_client,
            feedback=judgements,
            wants=wants,
            # W-12. Ten more than the page, narrated below and kept off the wire,
            # so a tap that promotes one of them finds prose already written.
            reserve=RESERVE_DEPTH,
        )
    except InsufficientProfile:
        # The user has no job title and no skills, so there is nothing to score.
        # This is the ACC-4 / S16.11 defect: it used to arrive here as an empty
        # list and leave as `500 Unable to score career paths`, which told the
        # user to retry something no amount of retrying could fix. The SPA's
        # `stateForFailure()` has had a `profile_incomplete` branch the whole
        # time -- "Add a job title and a few skills to get started" -- and it was
        # dead only because the backend never sent the string.
        logger.info(
            "Insufficient profile for path scoring, user %s (title=%r, skills=%d)",
            user.id,
            user_profile.current_title,
            len(user_profile.skills),
        )
        return _error(400, "profile_incomplete")
    except CorpusUnavailable:
        # The corpus is a build artifact fetched from S3 and cached on disk;
        # unreachable is an outage, not a bad request, and retrying works. The
        # same branch `path_fit`, `record_path_feedback` and `_rescore` already
        # have -- this cold generation was the one caller that fell through to
        # the generic 500 below instead, and the job it runs under carried the
        # untyped string where the SPA's `stateForFailure()` already had a
        # `corpus_unavailable` branch waiting for it (F-8 follow-up).
        logger.warning("Corpus unavailable for path scoring, user %s", user.id)
        return _error(503, "corpus_unavailable")
    except Exception:  # noqa: BLE001 -- logged with a traceback
        logger.exception("Path scoring failed for user %s", user.id)
        return _error(500, "Unable to score career paths")

    if not scored:
        # The profile had signal but nothing came back: an unreachable corpus,
        # an embedding outage, a query the retrieval seam rejected. Genuinely
        # transient, so genuinely a 500 -- deliberately NOT the branch above.
        logger.warning(
            "Empty scored list for user %s (title=%r, skills=%d)",
            user.id,
            user_profile.current_title,
            len(user_profile.skills),
        )
        return _error(500, "Unable to score career paths")

    # W-12. The page is the first `PAGE_SIZE` of what came back; everything after
    # it is the reserve, which is narrated and cached but never served.
    page = scored[:PAGE_SIZE]
    page_codes = {path.onet_code for path in page}

    try:
        narrated = generate_narratives_batched(
            scored, build_user_context(profile, user.intake, career_status)
        )
    except NarrativeGenerationError:
        logger.exception("Path narrative generation failed for user %s", user.id)
        return _error(500, "Unable to generate path narratives")

    suggestions = [s for s in narrated if s.onet_code in page_codes]
    if page and not suggestions:
        # The batch carrying the page came back unusable. Fatal, exactly as it
        # was before W-12 -- the shortlist IS the product, and a job that
        # succeeded with no prose on any card would warm the cache with a
        # ten-card page of fallback sentences and no way to ask again.
        #
        # A RESERVE batch failing is not fatal and is not handled here:
        # `generate_narratives_batched` logs it and returns the batches that
        # worked, so those cards simply have no reserve entry and get the
        # `_overlap_sentence` fallback if a tap ever promotes them.
        logger.error(
            "Path narrative generation produced nothing for the page, user %s",
            user.id,
        )
        return _error(500, "Unable to generate path narratives")

    # W-14. **Every** narrative this job wrote, the page included -- not just the
    # ten below it, which is what W-12 stored.
    #
    # The page cards' prose is also on the payload, and `_describe` carries it
    # forward from there, so storing it twice looks redundant. It is redundant
    # right up to the moment a card LEAVES the page: a "Not for me" tap drops it
    # from the payload, "Start over" brings it back, and a reserve defined as the
    # complement of the page has no entry for it either. The card returned
    # reading "Uses your SQL." with no pills beside its narrated neighbours --
    # W-14's first bug, found driving the real stack after the fourth user test.
    #
    # The rule this restores is the simple one: a card that ever had prose in
    # this job gets that prose back, whichever half of the list it came from.
    reserve_narratives = {
        s.onet_code: {
            "why_text": s.why_text,
            "profile_dimensions": list(s.profile_dimensions),
        }
        for s in narrated
    }

    score_map = {path.onet_code: path.score for path in scored}
    # W-4, additive and keyed the same way `score_map` is: the narrator returns
    # its own objects, so the scorer's per-card fields are joined back on by
    # code rather than by position.
    reasons_map = {path.onet_code: path.reasons for path in scored}
    payload = {
        "suggestions": [
            {
                "onet_code": s.onet_code,
                "title": s.title,
                "why_text": s.why_text,
                "profile_dimensions": s.profile_dimensions,
                "match_score": score_map.get(s.onet_code, 0.0),
                "reasons": reasons_map.get(s.onet_code, []),
            }
            for s in suggestions
        ],
        "career_status": career_status,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        # F-6, additive. The list and the judgements that shaped it travel
        # together, so a client that reloads can light up the controls the user
        # already pressed and offer the reset. Without it a returning user would
        # be handed a list bent by invisible state with no way to straighten it.
        "feedback": judgements,
    }

    path_cache.store(user.id, payload)
    # Written unconditionally, empty included: this generation's reserve must
    # replace the last one rather than be merged with it, or a card dropped from
    # the shortlist would keep prose written against an older profile.
    path_cache.store_reserve(user.id, reserve_narratives)
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


# ---------------------------------------------------------------------------
# Tier 2 -- the deep fit for one occupation (BUILD_PLAN F-5)
# ---------------------------------------------------------------------------
#
# `path_suggestions` above is Tier 1: a cheap shortlist, no per-candidate O*NET
# traffic, run off the request path by a worker. This is Tier 2: the full
# analysis of the ONE occupation a user clicked, run *inside* the request,
# because four `_OCC_CACHE`-backed calls for one code are fast enough that a
# job/poll pair would cost the user more round trips than it saved (design doc
# §2.3). The two functions share `build_user_profile`, so the fit and the card
# it was opened from are computed from the same inputs by construction.

#: The reason on a `path_deep_fit.UnknownOccupation` -> the error string the SPA
#: branches on. Three codes rather than one, because the three want three
#: different things from the UI: a client bug, a card from a stale shortlist,
#: and a hand-built URL naming a SOC residual bucket.
_UNKNOWN_OCCUPATION_ERRORS = {
    "malformed": "invalid_onet_code",
    "unknown": "unknown_occupation",
    "residual": "unsupported_occupation",
}


def path_fit(user: User, onet_code: str, logger) -> IntelligenceResult:
    """Deep-fit one occupation for *user*, serving a stored result when fresh.

    Returns the same body either way, plus ``cached`` saying which it was --
    a client renders one shape and an operator can see the hit rate without a
    second endpoint.

    Error strings, all in the ``{"error": "..."}`` shape the rest of this module
    uses and `stateForFailure()` already branches on:

    ``400 career_status_not_set``  the scorer needs it and it cannot be derived
    ``400 profile_incomplete``     no job title and no skills (the F-4 branch)
    ``404 invalid_onet_code``      not an O*NET-SOC code
    ``404 unknown_occupation``     well-formed, not in the corpus
    ``404 unsupported_occupation`` a "..., All Other" residual bucket
    ``503 corpus_unavailable``     the corpus could not be loaded; retry
    ``500``                        anything else, logged with a traceback
    """
    from backend.services.onet_client import OnetClient
    from backend.services.path_deep_fit import (
        CorpusUnavailable,
        UnknownOccupation,
        deep_fit,
    )
    from backend.services.path_scoring import InsufficientProfile

    profile = profile_repository.load_document(user.id)
    career_status = profile.get("career_status") or derive_career_status(profile)
    if not career_status:
        return _error(400, "career_status_not_set")

    user_profile = build_user_profile(
        {**profile, "career_status": career_status}, user.intake, career_status
    )
    fingerprint = path_fit_repository.fingerprint(user_profile)

    stored = path_fit_repository.read(user.id, onet_code, fingerprint)
    if stored is not None:
        return IntelligenceResult(status=200, body={**stored, "cached": True})

    try:
        try:
            openai_client = llm.get_openai_client()
        except RuntimeError:
            # No API key: deep_fit degrades to the zone and title terms rather
            # than failing, the same promise score_paths makes.
            openai_client = None
        fit = deep_fit(user_profile, onet_code, OnetClient(), openai_client)
    except InsufficientProfile:
        logger.info(
            "Insufficient profile for deep fit, user %s (title=%r, skills=%d)",
            user.id,
            user_profile.current_title,
            len(user_profile.skills),
        )
        return _error(400, "profile_incomplete")
    except UnknownOccupation as exc:
        return _error(
            404, _UNKNOWN_OCCUPATION_ERRORS.get(exc.reason, "unknown_occupation")
        )
    except CorpusUnavailable:
        # The corpus is a build artifact fetched from S3 and cached on disk;
        # unreachable is an outage, not a bad request, and retrying works.
        logger.warning("Corpus unavailable for deep fit, user %s", user.id)
        return _error(503, "corpus_unavailable")
    except Exception:  # noqa: BLE001 -- logged with a traceback
        logger.exception("Deep fit failed for user %s (%s)", user.id, onet_code)
        return _error(500, "Unable to compute path fit")

    body = {
        **fit.to_dict(),
        "computed_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }
    # `computed_at` is stored with the payload so a later cache hit reports when
    # the analysis actually ran; `cached` is not, because it is a fact about the
    # response and not about the fit.
    path_fit_repository.store(user.id, onet_code, body, fingerprint)
    db.session.commit()
    return IntelligenceResult(status=200, body={**body, "cached": False})


# ---------------------------------------------------------------------------
# Tier 1 -- inline card feedback for `adjacent` (BUILD_PLAN F-6)
# ---------------------------------------------------------------------------
#
# `path_suggestions` above is the cold generation: a worker runs it, it costs an
# LLM completion for ten narratives, and the job/poll pair exists because of
# that. The two functions below are the WARM re-rank, and they are synchronous
# for the reason F-5's deep fit is -- the work is small enough that a job handle
# the client has to poll would cost more round trips than it deferred.
#
# WHAT A TAP COSTS, measured against the real corpus and the real APIs:
# `score_paths` is **3 ms** warm -- zero O*NET, the user's own texts already in
# `_EMBED_CACHE`, one 1,016 x 1,536 matrix product. The narrator was everything
# else, at 1.4-4 seconds depending on how many cards the re-rank surfaced, so it
# is **not on this path at all**. `_describe` has the measurements and the two
# sources a card's "why" comes from instead.
#
# THESE FUNCTIONS INVALIDATE NOTHING. `path_cache.invalidate` and
# `path_fit_repository.invalidate` are for writes that change a scoring *input
# derived from the profile*; a judgement is not that. It is an input the scorer
# takes directly, and the re-rank below stores its result INTO `path_cache`
# rather than dropping it. The Tier-2 fits are untouched on purpose: a deep fit
# is one occupation analysed against one profile, and the user's opinion about a
# different card does not change it.
#
# `tests/test_path_preferences_api.py`'s enumeration rule -- every
# `path_cache.invalidate` matched by a `path_fit_repository.invalidate` -- is
# therefore satisfied by adding neither, which is why it needed no carve-out.

#: O*NET-SOC, e.g. ``15-1252.00``.
#:
#: A second copy of `path_deep_fit._ONET_CODE_RE`, deliberately. That one is
#: private to a module F-6 does not own, and reaching into another module's
#: underscore name to save one line is the coupling that makes the next refactor
#: of `path_deep_fit` break this route instead. What genuinely has to be shared
#: -- the error *vocabulary* the SPA branches on -- is shared, through
#: `_UNKNOWN_OCCUPATION_ERRORS` above.
_ONET_CODE_PATTERN = re.compile(r"^\d{2}-\d{4}\.\d{2}$")


def record_path_feedback(
    user: User, data: Dict[str, Any], logger
) -> IntelligenceResult:
    """Store one judgement and return the re-ranked shortlist.

    Body: ``{"onet_code": ..., "verdict": "too_similar"|"interesting"|"not_for_me"}``.

    Errors, all in the ``{"error": "..."}`` shape `stateForFailure()` branches on:

    ``400 invalid_verdict``        the verdict is not one of the three
    ``400 career_status_not_set``  the scorer needs it and it cannot be derived
    ``400 profile_incomplete``     no job title and no skills
    ``404 invalid_onet_code``      not an O*NET-SOC code
    ``404 unknown_occupation``     well-formed, not in the corpus
    ``404 unsupported_occupation`` a "..., All Other" residual bucket
    ``503 corpus_unavailable``     the corpus could not be loaded; retry
    ``500``                        anything else, logged with a traceback

    The code is checked for SHAPE before the corpus is touched and for
    MEMBERSHIP after, which is F-5's ordering and F-5's reason: a malformed code
    is a permanent client bug, and answering it 503 through an S3 outage would
    send the caller retrying something that will never work.
    """
    verdict = (data or {}).get("verdict")
    onet_code = (data or {}).get("onet_code")
    if verdict not in path_feedback_repository.VERDICTS:
        return _error(400, "invalid_verdict")
    if not isinstance(onet_code, str) or not _ONET_CODE_PATTERN.match(onet_code):
        return _error(404, "invalid_onet_code")

    prepared = _prepare_rescore(user)
    if isinstance(prepared, IntelligenceResult):
        return prepared
    _, career_status, user_profile = prepared

    from backend.services.occupation_retrieval import (
        CorpusUnavailable,
        get_corpus,
        is_all_other_title,
    )

    try:
        corpus = get_corpus()
    except CorpusUnavailable:
        logger.warning("Corpus unavailable for path feedback, user %s", user.id)
        return _error(503, "corpus_unavailable")

    row = corpus.index_of(onet_code)
    if row is None:
        return _error(404, "unknown_occupation")
    if is_all_other_title(corpus.titles[row]):
        return _error(404, "unsupported_occupation")

    path_feedback_repository.record(user.id, onet_code, verdict)
    # Committed before the re-rank rather than after it. The judgement is what
    # the user asked for, and it is small and durable; the shortlist is a cache.
    # If the narrator times out on the next line the tap is still recorded and a
    # refresh shows its effect, instead of the tap being silently lost because
    # something downstream of it failed.
    db.session.commit()

    return _rescore(user, career_status, user_profile, logger)


def clear_path_feedback(user: User, logger) -> IntelligenceResult:
    """Drop every judgement for *user* and return the default shortlist.

    The "start over" button. Idempotent: clearing when there is nothing to clear
    is a 200 carrying the list a user who never tapped anything would get, not a
    404 -- the client is asking for a state, not deleting a row it named.

    Same error vocabulary as :func:`record_path_feedback`, minus the three that
    are about a code and a verdict it is not given.
    """
    prepared = _prepare_rescore(user)
    if isinstance(prepared, IntelligenceResult):
        return prepared
    _, career_status, user_profile = prepared

    path_feedback_repository.clear_for_user(user.id)
    db.session.commit()

    return _rescore(user, career_status, user_profile, logger)


def _prepare_rescore(user: User):
    """``(profile_document, career_status, UserProfile)``, or the error to return.

    The half of both handlers above that is about the *user* rather than about
    the judgement, lifted out because getting it subtly different between the two
    is how a POST and its matching DELETE end up disagreeing over whose profile
    is complete.
    """
    profile = profile_repository.load_document(user.id)
    career_status = profile.get("career_status") or derive_career_status(profile)
    if not career_status:
        return _error(400, "career_status_not_set")
    profile = {**profile, "career_status": career_status}
    return (
        profile,
        career_status,
        build_user_profile(profile, user.intake, career_status),
    )


def _rescore(
    user: User,
    career_status: str,
    user_profile,
    logger,
) -> IntelligenceResult:
    """Re-run Tier 1 with the user's stored judgements and cache the result.

    Writes into `path_cache` rather than invalidating it, so `GET
    /me/path-suggestions` serves exactly the list this returned and the two
    cannot disagree about what the user is looking at.
    """
    from backend.services.occupation_retrieval import CorpusUnavailable
    from backend.services.onet_client import OnetClient
    from backend.services.path_scoring import InsufficientProfile, score_paths

    # See `path_suggestions` for why this import is deferred.
    from solverah.services import path_wants_service

    judgements = path_feedback_repository.verdicts_for_user(user.id)

    try:
        try:
            openai_client = llm.get_openai_client()
        except RuntimeError:
            openai_client = None
        onet_client = OnetClient()
        # W-4, the second of the two sites that score for a signed-in user. A tap
        # must not quietly drop the wants: the re-rank writes its result into
        # `path_cache`, so a list built without them would become the list `GET
        # /me/path-suggestions` serves until the next profile write.
        wants = path_wants_service.wants_for_scoring(
            user, user_profile, onet_client, openai_client
        )
        scored = score_paths(
            user_profile,
            onet_client,
            openai_client,
            feedback=judgements,
            wants=wants,
        )
    except InsufficientProfile:
        logger.info("Insufficient profile for path feedback rescore, user %s", user.id)
        return _error(400, "profile_incomplete")
    except CorpusUnavailable:
        logger.warning(
            "Corpus unavailable during path feedback rescore, user %s", user.id
        )
        return _error(503, "corpus_unavailable")
    except Exception:  # noqa: BLE001 -- logged with a traceback
        logger.exception("Path feedback rescore failed for user %s", user.id)
        return _error(500, "Unable to score career paths")

    if not scored:
        # The transient-upstream case `path_suggestions` answers 500 for, plus
        # one way in that is specific to this route: a radius wide enough to
        # exclude everything. `path_scoring._RADIUS_MIN_SURVIVORS` is the guard
        # that makes that unreachable rather than merely unlikely, and this
        # branch is what it would look like if the guard ever stopped working.
        logger.warning(
            "Empty rescore for user %s (%d judgements)", user.id, len(judgements)
        )
        return _error(500, "Unable to score career paths")

    suggestions, narrated = _describe(user, scored)
    payload = {
        "suggestions": suggestions,
        "career_status": career_status,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        # W-13. **On the stored payload, not only on the response.** This used
        # to be `body={**payload, "feedback": judgements}` with `payload`
        # itself cached without the key -- so the tap's own 200 carried the
        # judgements and every later read of the cache did not.
        #
        # That is the whole of the third browser test's finding: tap "Not for
        # me" twice, reload, and the cards stay removed while "These paths are
        # shaped by what you've told us / Start over" is gone. A reload posts a
        # scoring job; `path_suggestions` answers it from this cache on a hit
        # and `scoring_jobs` stores that body as the job's `result`; the page
        # renders the bar from `result.feedback`. One missing key in the cached
        # copy and the user is looking at a list bent by state they can neither
        # see nor undo -- the exact failure F-6 put `feedback` on the wire to
        # prevent, reintroduced by the one path that wrote the cache by hand.
        #
        # `path_suggestions` has always cached the key; this is now the same
        # object in both places for the same reason that function keeps its
        # cache write inline: the succeeded job and the warm cache must never
        # disagree about what was computed.
        "feedback": judgements,
    }
    # W-14. Stored either way -- the GET and the job a reload polls both read
    # this, and the list the user is looking at is this one -- but flagged with
    # whether any of it was written by the narrator. A fallback-only page is a
    # true record of the screen and a false basis for skipping the next job's
    # narration, and `path_suggestions` is where those two part company.
    path_cache.store(user.id, payload, narrated=narrated)
    return IntelligenceResult(status=200, body=payload)


#: Copy for a card the re-rank surfaced that had no narrative yet.
#:
#: Julie owns the wording; these are best guesses. What is NOT a wording
#: question is the choice to have them at all -- see :func:`_describe`.
def _overlap_sentence(overlapping_skills: List[str]) -> str:
    names = [name for name in overlapping_skills if name][:3]
    if not names:
        return "A different direction. Open it to see how it lines up with your skills."
    if len(names) == 1:
        return "Uses your %s." % names[0]
    return "Uses your %s and %s." % (", ".join(names[:-1]), names[-1])


def _describe(user: User, scored) -> Tuple[List[Dict[str, Any]], bool]:
    """The re-ranked list with a "why" for every card and NO LLM call, and
    whether any of those "why"s came from the narrator (W-14).

    ── WHY THE NARRATOR IS NOT ON THIS PATH, MEASURED ─────────────────────────

    The re-rank itself is **3 ms** warm: zero O*NET, the user's own texts already
    in `_EMBED_CACHE`, one 1,016 x 1,536 matrix product. Everything else in a
    tap was the narrator, and the narrator is not close to affordable here
    (`gpt-4o-mini`, measured against the real API on the F-2 profiles):

        cards narrated    1        2        3        5        10
        latency        1.4-1.7s 1.9-2.1s 2.5-2.7s 3.1-3.7s 10.3-11.1s

    (The ten-card figure read 6.7 s from F-6 until W-12 re-measured it on three
    profiles: 10.35 / 11.09 / 10.35 s. Nothing in this repository changed; the
    provider got slower. It is corrected here rather than left to be read off
    as a current number.)

    A tap surfaces two to six new cards, so narrating them would put **1.5-4
    seconds** on a control the user is expected to press repeatedly, and roughly
    a second of that is fixed overhead no amount of carrying forward removes.
    An optimistic re-order hides latency; it does not make a list that settles
    four seconds later feel like an inline control. This is the one place F-6's
    brief turned out to be wrong about cost, and it is recorded in the landing
    note rather than absorbed quietly.

    ── WHAT A CARD SAYS INSTEAD ───────────────────────────────────────────────

    Three sources, in this order:

    1. **The reserve (W-12, widened by W-14).** The scoring job narrates twenty
       and shows ten; ALL TWENTY are in `path_cache.get_reserve`, written by the
       same narrator, from the same profile, in the same job. A card promoted out
       of the reserve therefore arrives reading like the cards beside it, which
       is what F-8 routed onward and what the first browser test asked for --
       and a card that was on the page, was removed by a tap, and came back on
       "Start over" finds its prose here too, which is what the fourth one
       asked for.

       **This is consulted BEFORE the carry-forward, and that order is the fix
       rather than a detail.** The carry-forward keeps any truthy `why_text`,
       *including a fallback sentence this function wrote on an earlier tap* --
       so without the reserve going first, a card that surfaced once as "Uses
       your SQL." would keep that sentence for the rest of the session even
       after prose for it existed. Reserve first means the upgrade lands on the
       next tap.

    2. **The narrative it already has.** Most of a re-rank is the same
       occupations reordered, and a `why_text` is a function of (occupation,
       profile) -- a tap moves neither. Those are carried across verbatim from
       the cached payload, so the prose the user has been reading does not
       change under them.
    3. **Its overlapping skills**, for a card beyond the reserve that was not on
       the list before. `score_paths` already computes these per card at no
       extra cost (one matrix product over skills the batch request already
       embedded), and they are the *same data* the narrator is handed to write
       from. "Uses your Lesson planning, Classroom management and Student
       assessment" is more concrete than most of what an LLM writes from the
       same input, and it arrives in microseconds.

    `profile_dimensions` is left empty for those cards rather than filled with
    invented tags: an empty list renders nothing, and a fabricated tag is worse
    than a missing one.

    ── THE SECOND RETURN VALUE (W-14) ─────────────────────────────────────────

    True when at least one card took its prose from source 1 or from a source-2
    payload that was itself narrated; False when every card fell through to
    source 3. That is the difference between a re-rank of a narrated list and a
    re-rank of nothing, and `path_suggestions` needs it to decide whether the
    cache entry `_rescore` is about to write is worth serving in place of a
    narrator run. It is computed here rather than sniffed off the finished list
    because a fallback sentence is indistinguishable from prose once written:
    only the site that chose the source knows which it used.
    """
    reserve = path_cache.get_reserve(user.id)
    cached = path_cache.get(user.id) or {}
    cached_narrated = path_cache.is_narrated(user.id)
    carried = {
        item.get("onet_code"): item
        for item in cached.get("suggestions") or []
        if item.get("onet_code") and item.get("why_text")
    }

    out: List[Dict[str, Any]] = []
    narrated = False
    for path in scored:
        prior = reserve.get(path.onet_code)
        if prior is not None:
            narrated = True
        else:
            prior = carried.get(path.onet_code)
            # A carried sentence is only narrator prose if the payload it came
            # off was. Tap twice on a cold worker and the second tap carries the
            # first tap's fallbacks forward -- truthy, and still not narration.
            if prior is not None and cached_narrated:
                narrated = True
        out.append(
            {
                "onet_code": path.onet_code,
                "title": path.title,
                "why_text": (
                    prior["why_text"]
                    if prior
                    else _overlap_sentence(path.overlapping_skills)
                ),
                "profile_dimensions": (
                    prior.get("profile_dimensions") or [] if prior else []
                ),
                "match_score": path.score,
                # W-4. NOT carried across from the cached card the way `why_text`
                # is, and the difference is what the two are about: a `why_text`
                # is a function of (occupation, profile) and a tap moves neither,
                # while a reason is a function of the PAGE -- the distinctiveness
                # rule counts a phrase across the cards actually shown, so a
                # re-rank that changed which ten they are has changed which
                # phrases are worth printing.
                "reasons": path.reasons,
            }
        )
    return out, narrated
