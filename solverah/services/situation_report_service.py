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
The pin exists so a report the user has already seen cannot silently shift under a
core retake. `situation_report_pin_store` holds only the EXPLICIT override an ⚑5
recalibrate call writes. With no override, the DEFAULT pin is the sitting that was
current when the report first came into being (`_default_pin`; Work Pulse retakes
became a product path in 6babb39):

* the latest completed core sitting at or before the user's FIRST current
  Environment Report (`environment_report_store.first_environment_report_submitted_at`);
* if every sitting is newer than that report (it was filed before core), the first
  sitting after it -- the report came into being when that sitting completed;
* with no Environment Report yet, the latest sitting -- what a report filed now
  would be built from (only `recalibrate` asks before one exists).

Every input is append-only -- core sittings and Environment Reports alike -- so the
anchor never moves once it exists: a retake after filing, or a re-filed report,
leaves the person side where it was until Recalibrate. A retake BEFORE the first
filing is a sitting the user built their (not yet existing) report on, so it is the
one used. A user with a single sitting resolves to it, exactly as before.

FALL-FORWARD. A defaulted sitting that cannot be scored any more (an item-bank
change since, `dimension_scores_for_submission` -> None) is skipped for the first
readable sitting after it. Nothing a user saw is being protected there: an
unreadable pin renders `needs_core` + `core_unreadable`, which shows no person side
at all, and its copy tells them to take Work Pulse again -- which only helps if the
retake is then read. Still deterministic: the first readable sitting after a fixed
anchor never changes on a later retake. An EXPLICIT pin never falls forward; the
user chose it, and Recalibrate is its exit.

`_pinned_sitting` is the one place that resolves all of this into what a read uses.
`causal_graph/v1_model/assemble_training_data.py` restates the rule in SQL, guarded
by a tripwire test that compares it with `_pinned_submission_id`.

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


def _default_pin(user_id: int) -> tuple[Optional[str], Optional[dict]]:
    """(submission_id, person_scores) for a user with no explicit override -- the
    rule in the module docstring. (None, None) when no core sitting row exists;
    (anchor_id, None) when neither the anchor nor any later sitting is readable.

    A single sitting needs no anchor: it is the only answer, so the Environment
    Report timestamp is read only once there is a choice to make."""
    import assessment_store
    import environment_report_store

    sittings = assessment_store.completed_core_sittings(user_id)
    if not sittings:
        return None, None

    start = len(sittings) - 1
    if len(sittings) > 1:
        anchor_at = environment_report_store.first_environment_report_submitted_at(user_id)
        if anchor_at is not None:
            at_or_before = [
                i for i, (_, completed_at) in enumerate(sittings) if completed_at <= anchor_at
            ]
            start = at_or_before[-1] if at_or_before else 0

    for submission_id, _completed_at in sittings[start:]:
        scores = assessment_store.dimension_scores_for_submission(submission_id)
        if scores is not None:
            return submission_id, scores
    return sittings[start][0], None


def _pinned_sitting(user_id: int) -> tuple[Optional[str], Optional[dict]]:
    """(submission_id, person_scores) the Situation Report reads: the explicit
    recalibrate override if one was ever written (never fallen forward from), else
    `_default_pin`. Scores are None when the resolved sitting cannot be read."""
    import assessment_store
    import situation_report_pin_store

    override = situation_report_pin_store.explicit_pin(user_id)
    if override is not None:
        submission_id = override["submission_id"]
        return submission_id, assessment_store.dimension_scores_for_submission(submission_id)
    return _default_pin(user_id)


def _pinned_submission_id(user_id: int) -> Optional[str]:
    """Just the submission_id half of `_pinned_sitting`. What `recalibrate` compares
    with the latest sitting, and what the model lane's tripwire test
    (`tests/test_assemble_environment_training_data.py`) checks its SQL against.

    An explicit pin is returned without scoring it -- it never falls forward, so its
    readability cannot change the answer. The default has to score its candidates:
    fall-forward is part of which id it names."""
    import situation_report_pin_store

    override = situation_report_pin_store.explicit_pin(user_id)
    if override is not None:
        return override["submission_id"]
    return _default_pin(user_id)[0]


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


def _needs_core_body(env: Optional[dict], manager: dict) -> Dict[str, Any]:
    """The `needs_core` body: the manager section and, when a current
    environment report exists, its bare dimension scores (nothing to diff)."""
    from work_pulse import situation

    body: Dict[str, Any] = {"state": NEEDS_CORE, "manager": manager}
    if env is None:
        body["environment"] = None
        return body
    body["environment"] = {
        "dimensions": [
            {"dimension": dim, "env_score": env["dimension_scores"][dim]}
            for dim in situation.DIMENSIONS
        ],
        "career_status": env["career_status"],
        "submitted_at": env["submitted_at"],
    }
    return body


def _career_status_changed(user_id: int, snapshot: str) -> bool:
    """Whether the caller's LIVE career status reads in a different tense from
    the one the report was filed under (audit 2026-10-02, F1).

    The report renders from the snapshot, so an `employed` user who has since
    left keeps a current-role report about a job they no longer hold (and the
    reverse). This flag only lets the page ask them to describe the job again;
    the report itself is not re-sliced. A live status that is unset or unknown
    is not evidence of a change, so it reads False.

    A live `first_job` also reads False. `first_job` is past-tense only as a
    rendering flag ("no current role"); it has no role to describe, so the
    environment form gates it and the submit refuses it with 409
    `first_job_no_role`. A flag would raise a banner whose only action is that
    dead end, and since only a new report clears it, it would never go away.
    """
    from work_pulse import situation_items

    live = _live_career_status(user_id)
    if live == "first_job" or live not in situation_items.TENSE_BY_CAREER_STATUS:
        return False
    return situation_items.is_past_tense(live) != situation_items.is_past_tense(snapshot)


def get_situation_report(user: User) -> SituationReportResult:
    """The three states, per BUILD_PLAN §3.5. D-15 (structural, every state): no
    person-side score, no numeric gap, no per-dimension magnitude, anywhere.

    Every state also carries `past_job_report_filed`. Nothing else here reads a
    past-job report: the latest-report read is current-only by construction.

    `complete` also carries `career_status_changed` (see `_career_status_changed`).
    `needs_core` carries `core_unreadable: true` when a current-instrument sitting
    exists but the pinned one has no readable scores -- a graceful state, never a 500.
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
        return SituationReportResult(status=200, body=_needs_core_body(env, manager))

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

    _submission_id, person_scores = _pinned_sitting(user.id)
    if person_scores is None:
        # `has_completed_assessment` said a current-instrument sitting exists, but
        # the pinned one has no readable scores: no core submission row behind the
        # person-side scores, an explicit pin naming a submission with no responses
        # or one the current item file cannot score, or a default pin with no
        # readable sitting from its anchor on. There is no person side to
        # diff against, which is `needs_core`'s situation -- flagged, so the page
        # can say "we couldn't read it" rather than "you haven't taken it".
        body = _needs_core_body(env, manager)
        body["core_unreadable"] = True
        return SituationReportResult(status=200, body=body)

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
            "career_status_changed": _career_status_changed(user.id, career_status_snapshot),
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
