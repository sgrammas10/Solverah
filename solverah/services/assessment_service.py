"""The five assessment instruments: Work Pulse, WPLL, FocusType, ManagerMatch,
and the current 24-item person-side culture assessment.

Part 5.2 collapses the five near-identical submit handlers into one
``POST /assessments/{kind}/submissions`` with the differences living in
``assessment_forms.definition`` and a scoring strategy per kind.  That is Phase
1b.  What this module does now is put the five side by side in one file, which
is what makes the shape of that collapse visible: three of them are
score-then-narrate-then-store-in-a-blob and differ only in which scorer, which
prompt, and which key.

Deliberately unchanged:

* The **two-commit** sequence in :func:`submit_work_pulse`.  Answers and the
  completion timestamp are committed first, then the narrative blob separately,
  so that a failure writing ``wpl_result`` -- a column that has been missing on a
  deployment mid-migration -- still leaves the user marked complete rather than
  losing a 12-question submission.
* Scoring the person-side assessment returns the submission id and the key
  version but **not the six dimension scores**.  Handing them back gives a
  retaking respondent a gradient to optimise against, which teaches the
  item-to-dimension mapping the shuffle and interleave exist to hide.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from model import User, db
from solverah.domain import auth as auth_domain
from solverah.infra import llm
from solverah.repositories import assessment_repository
from solverah.services import assessment_prompts, path_cache

__all__ = [
    "ASSESSMENT_KINDS",
    "AssessmentKind",
    "AssessmentResult",
    "KINDS_BY_KEY",
    "catalogue",
    "find_kind",
    "form",
    "result",
    "submit",
    "MANAGER_MATCH_ANSWER_COUNT",
    "WORK_PULSE_ANSWER_COUNT",
    "WPLL_MAX_ANSWERS",
    "get_manager_match_result",
    "get_work_pulse_result",
    "submit_focus_type",
    "submit_manager_match",
    "submit_work_pulse",
    "wpll_insight",
]

WORK_PULSE_ANSWER_COUNT = 12
MANAGER_MATCH_ANSWER_COUNT = 15
WPLL_MAX_ANSWERS = 5

#: Result keys inside the ``profile_data`` blob.
FOCUS_TYPE_KEY = "focus_type_result"
MANAGER_MATCH_KEY = "manager_match_result"


@dataclass
class AssessmentResult:
    """A service outcome the API layer turns into a response."""

    status: int
    body: Any = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status < 400


def _error(status: int, message: str) -> AssessmentResult:
    return AssessmentResult(status=status, body={"error": message})


def _chat_json(messages: List[Dict[str, Any]], model_env: str, default_model: str) -> dict:
    """One JSON-mode chat completion, parsed.

    Raises whatever the SDK raises -- callers decide what a provider failure
    means for their endpoint, and they do not all agree (WPLL falls back to the
    rules engine, Work Pulse returns 500).
    """
    client = llm.get_openai_client()
    response = client.chat.completions.create(
        model=os.environ.get(model_env, default_model),
        messages=messages,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content or "{}")


# ---------------------------------------------------------------------------
# Work Pulse Lite-Lite (anonymous teaser)
# ---------------------------------------------------------------------------

def wpll_insight(answers: Any) -> AssessmentResult:
    """Generate the anonymous WPLL teaser insight.

    Falls back silently to the deterministic rules engine when the LLM call
    fails or returns something unusable. That fallback is the right call here
    and only here: this is an unauthenticated teaser with no persistence, so a
    slightly less personal sentence beats an error page. The authenticated
    instruments return 500 instead, because a narrative they cannot generate is
    a result they cannot store.
    """
    from work_pulse.insight_engine import LOCKED_SECTION_TITLES, generate_result

    if not isinstance(answers, list):
        return _error(400, "answers must be a list")
    if len(answers) == 0:
        return _error(400, "answers is required")
    if len(answers) > WPLL_MAX_ANSWERS:
        return _error(400, "Too many answers")

    insight_text = None
    try:
        system_msg, user_msg = assessment_prompts.build_wpll_insight_prompt(answers)
        parsed = _chat_json(
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "OPENAI_WPLL_MODEL",
            "gpt-4o-mini",
        )
        candidate = parsed.get("insight_text")
        if isinstance(candidate, str) and candidate.strip():
            insight_text = candidate
    except Exception:  # noqa: BLE001 -- see docstring; fall back, do not fail
        pass

    if insight_text is None:
        return AssessmentResult(status=200, body=generate_result(answers))

    return AssessmentResult(
        status=200,
        body={"insight_text": insight_text, "locked_sections": LOCKED_SECTION_TITLES},
    )


# ---------------------------------------------------------------------------
# Work Pulse (authenticated, 12 items)
# ---------------------------------------------------------------------------

def submit_work_pulse(user: User, answers: Any, logger) -> AssessmentResult:
    """Score, narrate, and persist a Work Pulse submission."""
    from work_pulse.derive_preferences import derive_culture_preferences

    if not isinstance(answers, list) or len(answers) != WORK_PULSE_ANSWER_COUNT:
        return _error(400, "answers must be a list of exactly 12 items")

    # Load or create the intake row before the LLM call, so a concurrent
    # duplicate collides cheaply rather than after a paid round trip.
    intake = assessment_repository.get_or_create_user_intake(user.id)

    try:
        result = _chat_json(
            assessment_prompts.build_wp_narrative_prompt(
                answers,
                wpll_answers=intake.wpll_answers or None,
                selected_statement_ids=intake.selected_statement_ids or None,
            ),
            "OPENAI_WP_MODEL",
            "gpt-4o-mini",
        )
    except Exception:  # noqa: BLE001 -- logged with a traceback below
        logger.exception("Work Pulse narrative generation failed")
        return _error(500, "Unable to generate Work Pulse results")

    required = ("narrative", "emerging_signals", "archetype", "archetype_description")
    if not all(key in result for key in required):
        return _error(500, "Malformed response from model")

    # Commit 1: persist answers and mark the user as WP-complete.
    # This must succeed before we attempt to store the narrative so that
    # wpl_completed_at is always written even if the wpl_result column is
    # missing (e.g. a pending migration) or the second commit fails for any
    # other reason.
    intake.wpl_answers = answers
    intake.wpl_completed_at = auth_domain.utcnow()

    profile = dict(user.profile_data or {})
    profile["culture_preferences"] = derive_culture_preferences(answers)
    user.profile_data = profile

    db.session.commit()

    # Commit 2: store the full narrative/result blob (best-effort).
    # If this fails (e.g. wpl_result column not yet migrated) the user is
    # still marked complete; they will see an error on the results page and
    # can retry narrative generation after running flask db upgrade.
    try:
        intake.wpl_narrative = result["narrative"]
        intake.wpl_result = result
        db.session.commit()
        path_cache.invalidate(user.id)
    except Exception:  # noqa: BLE001 -- see the comment above
        db.session.rollback()
        logger.exception("Work Pulse: failed to persist narrative/result blob")

    return AssessmentResult(status=200, body=result)


def get_work_pulse_result(user: User) -> AssessmentResult:
    """Return the stored Work Pulse narrative, for rehydrating a fresh session."""
    intake = assessment_repository.find_user_intake(user.id)
    if not intake or not intake.wpl_completed_at:
        return _error(404, "No Work Pulse results found")
    if not intake.wpl_result:
        # Answers saved but narrative blob missing (e.g. wpl_result column not
        # yet migrated). Tell the client to resubmit so narrative can be
        # regenerated -- 422 rather than 404, because the distinction is
        # actionable: one means "take the assessment", the other "try again".
        return _error(422, "Work Pulse results pending — please resubmit")

    return AssessmentResult(status=200, body=intake.wpl_result)


# ---------------------------------------------------------------------------
# FocusType (authenticated, 5 scenes, deterministic)
# ---------------------------------------------------------------------------

def submit_focus_type(user: User, data: Dict[str, Any]) -> AssessmentResult:
    """Score and persist a FocusType result.

    Entirely deterministic -- no LLM, so no failure mode beyond a bad payload.
    """
    from focus_type.score import score_focus_type

    missing = ["scene_%d" % i for i in range(1, 6) if "scene_%d" % i not in data]
    if missing:
        return _error(400, "Missing scene payloads: %s" % ", ".join(missing))

    result = score_focus_type(
        data["scene_1"],
        data["scene_2"],
        data["scene_3"],
        data["scene_4"],
        data["scene_5"],
    )

    assessment_repository.save_profile_result(user, FOCUS_TYPE_KEY, result)
    db.session.commit()
    path_cache.invalidate(user.id)

    return AssessmentResult(status=200, body=result)


# ---------------------------------------------------------------------------
# ManagerMatch (authenticated, 15 forced-choice items)
# ---------------------------------------------------------------------------

def submit_manager_match(user: User, answers: Any, logger) -> AssessmentResult:
    """Score deterministically, narrate with the LLM, then persist both."""
    from manager_match.score import score_manager_match

    if not isinstance(answers, list) or len(answers) != MANAGER_MATCH_ANSWER_COUNT:
        return _error(400, "answers must be a list of exactly 15 items")

    try:
        scoring = score_manager_match(answers)
    except ValueError as exc:
        return _error(400, str(exc))

    try:
        llm_result = _chat_json(
            assessment_prompts.build_mm_narrative_prompt(
                answers, scoring["archetype"], scoring["dimension_scores"]
            ),
            "OPENAI_WP_MODEL",
            "gpt-4o-mini",
        )
    except Exception:  # noqa: BLE001 -- logged with a traceback below
        logger.exception("ManagerMatch narrative generation failed")
        return _error(500, "Unable to generate ManagerMatch results")

    required = ("narrative", "what_to_look_for", "red_flags", "archetype_description")
    if not all(key in llm_result for key in required):
        return _error(500, "Malformed response from model")

    result = {**scoring, **llm_result}

    assessment_repository.save_profile_result(user, MANAGER_MATCH_KEY, result)
    db.session.commit()
    path_cache.invalidate(user.id)

    return AssessmentResult(status=200, body=result)


def get_manager_match_result(user: User) -> AssessmentResult:
    """Return the stored ManagerMatch result."""
    result = assessment_repository.get_profile_result(user, MANAGER_MATCH_KEY)
    if result is None:
        return _error(404, "No ManagerMatch result found")
    return AssessmentResult(status=200, body=result)


def submit_person_side(user: User, responses: Any) -> AssessmentResult:
    """Score and persist a completed person-side assessment.

    Everything correctness-critical -- the server-authoritative shuffle (D-04),
    the cross-dimension interleave, the opaque item tokens, the per-dimension
    arity check (D-02) -- lives in ``assessment_form``, and persistence goes
    through ``assessment_store``, the single sanctioned doorway to the
    person-side tables (D-01).  This function orchestrates the two and owns the
    transaction; it must not reach past either.

    The six dimension scores are deliberately absent from the result -- see the
    module docstring.
    """
    from assessment_form import AssessmentError, submit_form
    from assessment_store import persist_submission, respondent_id_for_user

    try:
        result = submit_form(respondent_id_for_user(user.id), responses)
    except AssessmentError as exc:
        return _error(400, str(exc))

    try:
        submission_id = persist_submission(db, user.id, result)
        db.session.commit()
    except Exception:
        # Re-raised, not swallowed: a failure to persist a completed assessment
        # is a 500 the operator must see. Rolling back first keeps the session
        # usable for the error handler.
        db.session.rollback()
        raise

    return AssessmentResult(
        status=200,
        body={
            "submission_id": submission_id,
            "scoring_key_version": result.scoring_key_version,
            "dimensions_scored": len(result.scores),
        },
    )


def person_side_form(user: User, logger) -> AssessmentResult:
    """The person-side items, ordered for this respondent.

    Ordering is server-authoritative: two independent PRNGs in two languages
    diverging is silent, and a divergence corrupts a resumed session's ordering
    rather than raising.
    """
    from assessment_form import PresentationContractError, get_form
    from assessment_store import respondent_id_for_user

    try:
        return AssessmentResult(status=200, body=get_form(respondent_id_for_user(user.id)))
    except PresentationContractError as exc:
        # Do not degrade to an unshuffled form. A form that silently renders in
        # difficulty order produces data that looks fine and is not (D-07).
        logger.error("assessment form unservable: %s", exc)
        return _error(500, "Assessment is temporarily unavailable")


# ===========================================================================
# Phase 1b -- one route, five instruments
# ===========================================================================
#
# Part 5.2 collapses five near-identical submit handlers into
# ``POST /assessments/{kind}/submissions``.  The registry below is what the
# ``{kind}`` discriminator resolves against, and the shape of it is the point:
# the five differ in a scorer, a prompt, a storage key, and whether they need a
# JWT, and nothing else.  Adding assessment #6 is an entry here.
#
# What is emphatically **not** unified is the result.  The five produce
# genuinely different payloads -- a narrative and an archetype, six dimension
# scores, a teaser sentence with locked section titles, a submission id with no
# scores at all -- and flattening them into a lowest-common-denominator envelope
# would throw away the part each instrument exists to produce.  Each kind keeps
# its own response model; the route is what is shared, not the shape.
#
# ``core``'s response is the sharpest example of why. It deliberately withholds
# the six dimension scores, because handing them back gives a retaking
# respondent a gradient to optimise against and teaches the item-to-dimension
# mapping the shuffle and interleave exist to hide. A "uniform" result envelope
# with a ``scores`` field would have quietly undone that.

#: Result keys the two blob-stored instruments write to.
_RESULT_KEYS = {
    "focus_type": FOCUS_TYPE_KEY,
    "manager_match": MANAGER_MATCH_KEY,
}


@dataclass(frozen=True)
class AssessmentKind:
    """One instrument, and everything the unified route needs to know about it.

    Attributes:
        key: The ``{kind}`` path segment.
        title: Human-readable name, for the catalogue.
        requires_auth: Whether a JWT is required. ``wpll`` is the only one that
            does not: it is the anonymous teaser on the pre-launch funnel and
            has no account to attach to yet.
        scored_by: ``"rules"`` or ``"llm"``. Carried because it is what decides
            whether a provider outage makes the instrument unavailable, and the
            catalogue is the honest place to say so.
        has_form: Whether the server serves the items. Only ``core`` does; the
            other four are rendered from definitions the client already holds.
        has_result: Whether a completed submission can be re-read later.
    """

    key: str
    title: str
    requires_auth: bool
    scored_by: str
    has_form: bool
    has_result: bool


ASSESSMENT_KINDS = (
    AssessmentKind("core", "Culture Assessment", True, "rules", True, False),
    AssessmentKind("work_pulse", "Work Pulse", True, "llm", False, True),
    AssessmentKind("wpll", "Work Pulse Lite-Lite", False, "llm", False, False),
    AssessmentKind("focus_type", "FocusType", True, "rules", False, True),
    AssessmentKind("manager_match", "ManagerMatch", True, "llm", False, True),
)

KINDS_BY_KEY = {kind.key: kind for kind in ASSESSMENT_KINDS}


def find_kind(key: str) -> Optional[AssessmentKind]:
    """The instrument named *key*, or None when nothing is."""
    return KINDS_BY_KEY.get(key)


def submit(kind: AssessmentKind, user: Optional[User], data: Dict[str, Any], logger) -> AssessmentResult:
    """Route a submission to the instrument that scores it.

    Dispatch is explicit rather than a callable stashed on the registry entry,
    because the five signatures genuinely differ -- three take a bare answers
    list, one takes the whole payload, one takes no user -- and a uniform
    adapter would be five wrappers pretending to be one.
    """
    if kind.key == "core":
        return submit_person_side(user, data.get("responses"))
    if kind.key == "work_pulse":
        return submit_work_pulse(user, data.get("answers"), logger)
    if kind.key == "wpll":
        return wpll_insight(data.get("answers", []))
    if kind.key == "focus_type":
        return submit_focus_type(user, data)
    if kind.key == "manager_match":
        return submit_manager_match(user, data.get("answers"), logger)
    return _error(404, "Unknown assessment")


def form(kind: AssessmentKind, user: User, logger) -> AssessmentResult:
    """The server-ordered items for *kind*.

    Only ``core`` has them. The other four are rendered from question
    definitions that ship with the client, and a 404 is the truthful answer for
    a form that does not exist rather than an empty one that implies it might.
    """
    if kind.key == "core":
        return person_side_form(user, logger)
    return _error(404, "%s has no server-served form" % kind.key)


def result(kind: AssessmentKind, user: User) -> AssessmentResult:
    """The stored result for *kind*, or a 404.

    ``core`` is absent on purpose, not pending. Its scores are withheld from the
    submit response for a documented reason -- an aspirational respondent
    optimising against a visible gradient -- and a read endpoint that handed
    them back would be the same disclosure through a different door.
    """
    if kind.key == "work_pulse":
        return get_work_pulse_result(user)
    if kind.key == "manager_match":
        return get_manager_match_result(user)
    if kind.key == "focus_type":
        stored = assessment_repository.get_profile_result(user, FOCUS_TYPE_KEY)
        if stored is None:
            return _error(404, "No FocusType result found")
        return AssessmentResult(status=200, body=stored)
    return _error(404, "%s does not store a retrievable result" % kind.key)


def catalogue(user: User) -> AssessmentResult:
    """Every instrument, with this user's completion state against each.

    New in Phase 1b, and the thing that makes ``{kind}`` discoverable: without
    it a client has to hard-code the five keys and work out completion from
    three unrelated places -- ``user_intake`` timestamps, two blob keys, and the
    person-side tables.
    """
    return AssessmentResult(
        status=200,
        body={
            "data": [
                {
                    "kind": kind.key,
                    "title": kind.title,
                    "requires_auth": kind.requires_auth,
                    "scored_by": kind.scored_by,
                    "has_form": kind.has_form,
                    "has_result": kind.has_result,
                    "completed": _is_completed(kind, user),
                }
                for kind in ASSESSMENT_KINDS
            ]
        },
    )


def _is_completed(kind: AssessmentKind, user: User) -> bool:
    """Whether *user* has finished *kind*.

    Four storage locations for five instruments, which is the schema problem
    Part 4.4's ``assessment_*`` unification exists to end. Reading them in one
    place is as far as Phase 1b goes.
    """
    if kind.key == "core":
        from assessment_store import has_completed_assessment

        try:
            return bool(has_completed_assessment(user.id))
        except Exception:  # noqa: BLE001 -- a catalogue must not fail a page load
            return False

    if kind.key in _RESULT_KEYS:
        return assessment_repository.get_profile_result(user, _RESULT_KEYS[kind.key]) is not None

    intake = assessment_repository.find_user_intake(user.id)
    if intake is None:
        return False
    if kind.key == "work_pulse":
        return intake.wpl_completed_at is not None
    return intake.wpll_completed_at is not None
