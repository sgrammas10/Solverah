"""Situation Report orchestration (BUILD_PLAN A-5).

Wires together A-1's item bank (`work_pulse.situation_items`), A-2's environment
storage (`environment_report_store`), A-3's gap engine (`work_pulse.situation`),
A-6's guidance content (`work_pulse.situation_content`), ⚑4's shared manager-profile
store (`manager_profile_store`) and ⚑5's D-15 pin (`situation_report_pin_store`,
`assessment_store`) into the two writes and the one read this surface serves.

Person-side reads go through `assessment_store` exclusively (D-01): this module
never imports either of the two gated person-side tables itself, and
`tests/test_employer_visibility.py` is the control that would catch it if it did.

THE D-15 PIN, RESOLVED HERE
----------------------------
"The first completed core sitting" needs no stored row at all -- it is
`assessment_store.first_completed_core_submission_id`, stable by construction because
`core` sittings are append-only (a later retake can never change which one was
first). `situation_report_pin_store` holds only the EXPLICIT override an ⚑5
recalibrate call writes. `_pinned_submission_id` below is the one place that
resolves "override, or the first sitting" into what a read actually uses -- which is
also what makes a plain core retake, with no recalibrate, leave `get_situation_report`
byte-identical: nothing this function reads changes when a new sitting merely exists.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from model import User, db
from solverah.errors import ConflictError

__all__ = [
    "SituationReportResult",
    "get_situation_report",
    "recalibrate",
    "submit_environment_report",
]

NEEDS_CORE = "needs_core"
NEEDS_ENVIRONMENT_REPORT = "needs_environment_report"
COMPLETE = "complete"


@dataclass
class SituationReportResult:
    """A service outcome the API layer turns into a response."""

    status: int
    body: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status < 400


def _error(status: int, message: str) -> SituationReportResult:
    return SituationReportResult(status=status, body={"error": message})


def _manager_section(user_id: int) -> dict:
    import manager_profile_store

    return {"has_profile": manager_profile_store.latest_manager_profile(user_id) is not None}


def _live_career_status(user_id: int) -> Optional[str]:
    """The caller's CURRENT career_status, deriving it the same way
    `intelligence_service.path_suggestions` does -- reading through
    `profile_repository` rather than the ORM directly, and falling back to a
    derivation from experience when the field was never explicitly set."""
    from solverah.repositories import profile_repository
    from solverah.services.intelligence_service import derive_career_status

    profile = profile_repository.load_document(user_id)
    status = profile.get("career_status")
    if not status:
        status = derive_career_status(profile)
    return status


def _pinned_submission_id(user_id: int) -> Optional[str]:
    """The submission_id the Situation Report reads person-side scores through:
    the explicit recalibrate override if one was ever written, else the first
    completed core sitting (⚑5's default pin -- see the module docstring)."""
    import assessment_store
    import situation_report_pin_store

    override = situation_report_pin_store.explicit_pin(user_id)
    if override is not None:
        return override["submission_id"]
    return assessment_store.first_completed_core_submission_id(user_id)


# ---------------------------------------------------------------------------
# POST /me/environment-report
# ---------------------------------------------------------------------------


def submit_environment_report(user: User, payload: Any) -> SituationReportResult:
    """Score and store one environment-report submission (A-1/A-2/A-3, sync).

    `career_status` is snapshotted from the caller's LIVE profile at submit time
    (never from the request body -- a user cannot describe someone else's tense).
    `first_job` refuses with a distinguishable 409: PRODUCT_DECISIONS.md §2's
    "Environment-instrument rulings" -- a never-employed user has no role to
    describe, and forcing the form would record a decline as a real answer.
    """
    from work_pulse import situation, situation_items

    if not isinstance(payload, dict):
        return _error(400, "body must be an object")

    career_status = _live_career_status(user.id)
    if not career_status:
        return _error(400, "career_status_not_set")
    if career_status not in situation_items.TENSE_BY_CAREER_STATUS:
        return _error(400, "unknown career_status %r" % career_status)

    if career_status == "first_job":
        raise ConflictError(
            detail=(
                "first_job has no role to describe -- the environment form is "
                "skipped entirely for a never-employed user."
            ),
            errors=[{"field": "career_status", "code": "first_job_no_role"}],
        )

    answers = payload.get("answers")
    expected_ids = {item["item_id"] for item in situation_items.item_list_in_form_order()}
    if not isinstance(answers, dict) or set(answers) != expected_ids:
        return _error(
            400,
            "answers must name exactly the twelve environment items: %s"
            % ", ".join(sorted(expected_ids)),
        )

    try:
        for item_id, choice in answers.items():
            situation_items.option_score(item_id, choice)  # validates; raises on bad input
        dimension_scores = situation.score_environment(
            answers, situation_items.item_spec(career_status)
        )
        stage_size = situation_items.context_value("stage_size", payload.get("stage_size"))
        comp = situation_items.context_value("comp", payload.get("comp"))
        experienced = situation_items.context_value("experienced", payload.get("experienced"))
    except ValueError as exc:
        return _error(400, str(exc))

    employer_name = payload.get("employer_name")
    employer_name_normalized = (
        employer_name.strip().lower()
        if isinstance(employer_name, str) and employer_name.strip()
        else None
    )

    import environment_report_store

    environment_report_store.write_environment_report(
        db,
        user.id,
        raw_answers=answers,
        dimension_scores=dimension_scores,
        stage_size=stage_size,
        comp=comp,
        experienced_outcome=experienced,
        career_status=career_status,
        version=situation_items.FORM_VERSION,
        employer_name_normalized=employer_name_normalized,
    )
    db.session.commit()

    return SituationReportResult(
        status=200,
        body={
            "dimension_scores": dimension_scores,
            "stage_size": stage_size,
            "comp": comp,
            "experienced": experienced,
            "career_status": career_status,
            "version": situation_items.FORM_VERSION,
        },
    )


# ---------------------------------------------------------------------------
# GET /me/situation-report
# ---------------------------------------------------------------------------


def _needs_forward_slice(assembled: dict) -> dict:
    """The needs-forward register rules (BUILD_PLAN A-5, per A-6's content):
    the diagnosis renders its `needs_forward` sentence only, `negotiate` is
    suppressed entirely, `change_in_place` is reduced to its `signal` (the rest
    of the cell describes a job the reader no longer holds), and no Decoder
    cross-reference is shown (that paragraph is written for a role in progress).
    `rarely_moves` carries over unchanged -- the rule names the other two only.
    """
    diagnosis = assembled["diagnosis"]
    registers = assembled["registers"]
    sliced: dict = {}
    if "change_in_place" in registers:
        sliced["change_in_place"] = {"signal": registers["change_in_place"]["signal"]}
    if "rarely_moves" in registers:
        sliced["rarely_moves"] = dict(registers["rarely_moves"])
    return {
        "diagnosis": {"headline": diagnosis["headline"], "text": diagnosis["needs_forward"]},
        "registers": sliced,
        "defers_to_decoder": assembled["defers_to_decoder"],
        "decoder_crossref": None,
    }


def _current_role_slice(assembled: dict) -> dict:
    diagnosis = assembled["diagnosis"]
    return {
        "diagnosis": {"headline": diagnosis["headline"], "text": diagnosis["current_role"]},
        "registers": assembled["registers"],
        "defers_to_decoder": assembled["defers_to_decoder"],
        "decoder_crossref": assembled["decoder_crossref"],
    }


def _events_since_report(user_id: int, submitted_at: Optional[str]) -> List[Dict[str, str]]:
    """Pulse events strictly newer than the environment report's `submitted_at`
    (BUILD_PLAN B-4) -- what the frontend's resubmission banner reads to ask
    "does your Situation Report still describe this job?". `type` and `date`
    only, never `note`: `pulse_events.note` is free text a user typed, and D-15
    holds for this payload the same as every other field in it.
    """
    import pulse_store

    if not submitted_at:
        return []
    since = datetime.datetime.fromisoformat(submitted_at)
    events = pulse_store.pulse_events_in_range(user_id, since=since)
    return [
        {"type": event["event_type"], "date": event["at"]}
        for event in events
        if event["at"] is not None and datetime.datetime.fromisoformat(event["at"]) > since
    ]


def get_situation_report(user: User) -> SituationReportResult:
    """The three states, per BUILD_PLAN §3.5. D-15 (structural, every state): no
    person-side score, no numeric gap, no per-dimension magnitude, anywhere.
    """
    import assessment_store
    import environment_report_store
    from work_pulse import situation, situation_content, situation_items

    env = environment_report_store.latest_environment_report(user.id)
    has_core = assessment_store.has_completed_assessment(user.id)
    manager = _manager_section(user.id)

    if not has_core:
        body: Dict[str, Any] = {"state": NEEDS_CORE, "manager": manager}
        if env is not None:
            body["environment"] = {
                "dimensions": [
                    {"dimension": dim, "env_score": env["dimension_scores"][dim]}
                    for dim in situation.DIMENSIONS
                ],
                "career_status": env["career_status"],
                "submitted_at": env["submitted_at"],
            }
        else:
            body["environment"] = None
        return SituationReportResult(status=200, body=body)

    if env is None:
        live_status = _live_career_status(user.id)
        return SituationReportResult(
            status=200,
            body={
                "state": NEEDS_ENVIRONMENT_REPORT,
                "can_submit_environment_report": live_status != "first_job",
                "manager": manager,
            },
        )

    submission_id = _pinned_submission_id(user.id)
    person_scores = assessment_store.dimension_scores_for_submission(submission_id)

    env_scores = env["dimension_scores"]
    report_rows = situation.build_situation_report(env_scores, person_scores)

    career_status_snapshot = env["career_status"]
    past_tense = situation_items.is_past_tense(career_status_snapshot)

    dimensions = []
    for row in report_rows:
        dim = row["dimension"]
        bucket = row["bucket"]

        if bucket == situation.ALIGNED:
            if past_tense:
                # A-6b: an alignment does not survive the move to needs-forward --
                # see work_pulse.situation_content.aligned_note_for's docstring.
                continue
            dimensions.append(
                {
                    "dimension": dim,
                    "env_score": row["env_score"],
                    "bucket": bucket,
                    "direction": None,
                    "rank": row["rank"],
                    "aligned_note": situation_content.aligned_note_for(dim, row["env_score"]),
                }
            )
            continue

        direction_word = situation_content.direction_for_bucket(bucket, row["direction"])
        assembled = situation_content.guidance_for(dim, direction_word)
        sliced = _needs_forward_slice(assembled) if past_tense else _current_role_slice(assembled)
        dimensions.append(
            {
                "dimension": dim,
                "env_score": row["env_score"],
                "bucket": bucket,
                "direction": row["direction"],
                "rank": row["rank"],
                **sliced,
            }
        )

    return SituationReportResult(
        status=200,
        body={
            "state": COMPLETE,
            "career_status": career_status_snapshot,
            "needs_forward": past_tense,
            "dimensions": dimensions,
            "guidance_notice": situation_content.GUIDANCE_NOTICE,
            "manager": manager,
            "events_since_report": _events_since_report(user.id, env["submitted_at"]),
        },
    )


# ---------------------------------------------------------------------------
# POST /me/situation-report/recalibrate
# ---------------------------------------------------------------------------


def recalibrate(user: User) -> SituationReportResult:
    """⚑5's explicit re-pin. Idempotent when already pinned to the latest
    completed core sitting: no write, no audit row, `recalibrated: false`."""
    import assessment_store
    import situation_report_pin_store
    from solverah.services.audit import log_audit_event

    if not assessment_store.has_completed_assessment(user.id):
        raise ConflictError(
            detail="Take the core assessment first -- there is no sitting to pin to yet.",
            errors=[{"field": "core", "code": "no_core_sitting"}],
        )

    latest = assessment_store.latest_completed_core_submission_id(user.id)
    current = _pinned_submission_id(user.id)
    moved = current != latest

    if moved:
        situation_report_pin_store.set_pin(db, user.id, latest)
        log_audit_event(
            "situation_report_recalibrate",
            user.id,
            "situation_report",
            metadata={"moved": True},
        )
        db.session.commit()

    return SituationReportResult(status=200, body={"recalibrated": moved})
