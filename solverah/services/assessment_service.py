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
    "AssessmentResult",
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
