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

PAST-JOB REPORTS (PRODUCT_DECISIONS.md §2, Sebastian, 2026-10-01)
-----------------------------------------------------------------
`POST /me/environment-report` with `subject: "past"` files a report about the one
job before the user's current or most recent one. At most `PAST_REPORT_LIMIT` per
user, only after a current report exists, never for `first_job`. Such a report is
stored and exported but never read by `get_situation_report`: the store's latest
read filters on the current subject, and the only trace a past report leaves on
that response is `past_job_report_filed`.
"""

from __future__ import annotations

import datetime
import functools
import os
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

SUBJECT_CURRENT = "current"
SUBJECT_PAST = "past"

#: How many past-job reports one user may file (Sebastian, 2026-10-01: one).
PAST_REPORT_LIMIT = 1


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
    """``{"has_profile": bool}`` -- one EXISTS probe, not the newest sitting."""
    import manager_profile_store

    return {"has_profile": manager_profile_store.has_manager_profile(user_id)}


def _live_career_status(user_id: int) -> Optional[str]:
    """The caller's CURRENT career_status, deriving it the same way
    `intelligence_service.path_suggestions` does -- reading through
    `profile_repository` rather than the ORM directly, and falling back to a
    derivation from experience when the field was never explicitly set.

    `include_assessments=False`: neither the field nor the derivation reads the
    two assessment-result keys, so their query is skipped."""
    from solverah.repositories import profile_repository
    from solverah.services.intelligence_service import derive_career_status

    profile = profile_repository.load_document(user_id, include_assessments=False)
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


def _check_past_report_allowed(user_id: int) -> None:
    """Raise the 409 that applies when this user may not file a past report now.

    Takes a row lock on the user first, so two past submits racing each other
    (a double click) serialize here and the second one sees the first one's row
    and refuses, rather than both reading a count of zero."""
    import environment_report_store
    from sqlalchemy import select

    db.session.execute(select(User.id).where(User.id == user_id).with_for_update())
    if environment_report_store.count_environment_reports(user_id, SUBJECT_CURRENT) == 0:
        raise ConflictError(
            detail=(
                "Describe your current or most recent job first -- a past-job report "
                "is accepted only after that one."
            ),
            errors=[{"field": "subject", "code": "current_report_required"}],
        )
    if environment_report_store.count_environment_reports(user_id, SUBJECT_PAST) >= PAST_REPORT_LIMIT:
        raise ConflictError(
            detail="You have already described a past job.",
            errors=[{"field": "subject", "code": "past_report_limit"}],
        )


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

    `subject` (default `"current"`): `"past"` files the user's one past-job report
    -- see the module docstring. Its refusals are 409s with distinguishable codes:
    `first_job_no_role` (as for a current report), `current_report_required`, and
    `past_report_limit`. `career_status` is still the live status, stored as "the
    filer's status that day", not as a description of the past job.
    """
    from work_pulse import situation, situation_items

    if not isinstance(payload, dict):
        return _error(400, "body must be an object")

    subject = payload.get("subject", SUBJECT_CURRENT)
    if subject not in (SUBJECT_CURRENT, SUBJECT_PAST):
        return _error(400, "subject must be 'current' or 'past'")

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

    if subject == SUBJECT_PAST:
        _check_past_report_allowed(user.id)

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
        # Optional (PRODUCT_DECISIONS.md §2, 2026-10-01): an absent key and an
        # explicit null both mean "not sure / prefer not to say".
        industry = situation_items.context_level("industry", payload.get("industry"))
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
        industry=industry,
        experienced_outcome=experienced,
        career_status=career_status,
        version=situation_items.FORM_VERSION,
        employer_name_normalized=employer_name_normalized,
        subject=subject,
    )
    db.session.commit()

    return SituationReportResult(
        status=200,
        body={
            "dimension_scores": dimension_scores,
            "stage_size": stage_size,
            "comp": comp,
            "industry": industry,
            "experienced": experienced,
            "career_status": career_status,
            "version": situation_items.FORM_VERSION,
            "subject": subject,
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
    holds for this payload the same as every other field in it -- so the note is
    not even selected, and "strictly newer" is the query's own `at > submitted_at`.
    """
    import pulse_store

    if not submitted_at:
        return []
    events = pulse_store.pulse_events_in_range(
        user_id,
        after=datetime.datetime.fromisoformat(submitted_at),
        columns=("event_type", "at"),
    )
    return [{"type": event["event_type"], "date": event["at"]} for event in events]


#: Which source `_dimension_weights` reads from -- see its docstring. Read with
#: `os.environ.get` at call time (the same plain style `solverah/cli.py` uses for
#: `DEFAULT_APP_BASE_URL`), never at import time, so tests can monkeypatch it
#: per test and a running process picks up a changed setting without a restart.
_WEIGHTS_SOURCE_VAR = "SOLVERAH_MODEL_WEIGHTS_SOURCE"


@functools.lru_cache(maxsize=1)
def _priors_dimension_weights() -> Dict[str, Dict[str, float]]:
    """E-5's elicited per-dimension weights, read from
    `causal_graph/v1_model/priors.yaml` through `match_scoring`. Means only; the
    `sd` describes the expert's confidence and has no bearing on which of two
    mismatches is listed first.

    No fallback to flat weights if this fails. D-07 forbids degrading to a
    default, the file is in the repo, and the image copies the whole tree -- so a
    missing file is a deploy defect and must surface as one. Cached because the
    file is read once per worker and never changes under a running process --
    unlike the `run` source below, nothing can invalidate it short of a restart.
    """
    import match_scoring

    cfg, pri = match_scoring.load()
    weights = match_scoring.weights_from_priors(cfg, pri)
    return {
        dim: {"mag": float(w["mag"]["mean"]), "dir": float(w["dir"]["mean"])}
        for dim, w in weights["dimensions"].items()
    }


#: The `run`-source cache: `{"run_id": ..., "weights": ...}`. Unlike the priors
#: path, `lru_cache` on no arguments would never notice a newer `model_run`
#: appearing -- a developer fits one and the server keeps ranking on the old
#: weights until restart. Instead this re-checks the CURRENT run's id on every
#: call (one cheap query) and only re-parses the weight rows when that id
#: changes, so a new run reaches the next request with no cache to clear by hand.
_run_weights_cache: Dict[str, Any] = {"run_id": None, "weights": None}


def _run_dimension_weights() -> Dict[str, Dict[str, float]]:
    """The latest `model_run`'s per-dimension weights, via
    `match_scoring.load_run_weights`. NO FALLBACK (D-07): a database with no run,
    or a run whose weight rows do not match the active config, raises
    `MatchModelError` and this lets it propagate -- a dev box asked to serve a
    fitted run that is not there must say so, not quietly serve the priors.
    """
    import match_scoring

    run = match_scoring.current_run(db)
    # id AND trained_at: a recreated dev database restarts ids at 1, so the id
    # alone would let a brand-new run 1 be served from the old run 1's cache.
    run_key = (run.id, run.trained_at)
    if _run_weights_cache["run_id"] != run_key:
        _, weights = match_scoring.load_run_weights(db, run=run)
        _run_weights_cache["run_id"] = run_key
        _run_weights_cache["weights"] = {
            dim: {"mag": float(w["mag"]["mean"]), "dir": float(w["dir"]["mean"])}
            for dim, w in weights["dimensions"].items()
        }
    return _run_weights_cache["weights"]


def _dimension_weights() -> Dict[str, Dict[str, float]]:
    """E-5's per-dimension weights for `work_pulse.situation`'s ranking, from
    whichever source `SOLVERAH_MODEL_WEIGHTS_SOURCE` names (PRODUCT_DECISIONS,
    2026-09-21):

    - unset or `"priors"` (the default): today's behavior, unchanged --
      `causal_graph/v1_model/priors.yaml`'s expert-elicited means, through
      `match_scoring`. Production stays on this; it is the only source with no
      new deploy dependency.
    - `"run"`: the latest `model_run` row, via `match_scoring.load_run_weights`.
      No fallback to priors if a run does not exist or is malformed (D-07).
    - anything else: `ValueError`, naming the variable and the two valid values
      -- a typo must not silently read as `"priors"`.

    Either branch returns plain `{dim: {"mag": float, "dir": float}}`, means
    only, regardless of source.
    """
    source = os.environ.get(_WEIGHTS_SOURCE_VAR) or "priors"
    if source == "priors":
        return _priors_dimension_weights()
    if source == "run":
        return _run_dimension_weights()
    raise ValueError(
        f"{_WEIGHTS_SOURCE_VAR}={source!r} is not valid -- must be 'priors' or 'run'"
    )


def get_situation_report(user: User) -> SituationReportResult:
    """The three states, per BUILD_PLAN §3.5. D-15 (structural, every state): no
    person-side score, no numeric gap, no per-dimension magnitude, anywhere.

    Every state also carries `past_job_report_filed`. Nothing else here reads a
    past-job report: the latest-report read is current-only by construction.
    """
    import environment_report_store

    result = _situation_report(user)
    result.body["past_job_report_filed"] = (
        environment_report_store.count_environment_reports(user.id, SUBJECT_PAST) > 0
    )
    return result


def _situation_report(user: User) -> SituationReportResult:
    """`get_situation_report` minus the past-report flag."""
    import assessment_store
    import environment_report_store
    from work_pulse import situation, situation_content, situation_items

    # No state of this page shows the raw answers, so their JSONB stays in the database.
    env = environment_report_store.latest_environment_report(user.id, include_raw_answers=False)
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
    report_rows = situation.build_situation_report(
        env_scores, person_scores, weights=_dimension_weights()
    )
    # `build_situation_report` is order-stable by contract and returns fixed
    # DIMENSIONS order; `rank` is the ranking. Both frontends render the list in
    # the order they receive it and neither sorts -- D-15 leaves them no
    # magnitude to sort on -- so the ranking only reaches a reader if the
    # payload is ordered here.
    report_rows = sorted(report_rows, key=lambda row: row["rank"])

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
    completed core sitting: no write, no audit row, `recalibrated: false`.

    The pin row is read once, by `_pinned_submission_id`; a move is one upsert
    (`situation_report_pin_store.set_pin`), which reads nothing first."""
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
