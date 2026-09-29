"""Assessment scoring and path suggestions, taken off the request path (3b).

Phase 3 item 3, continued.  3a moved resume parsing and all email; the two
handlers ``gunicorn.conf.py``'s 120-second timeout was actually raised for --
assessment scoring and path suggestions -- are what this moves.

**This is the mechanism 3a established, not a second one.**  Same four states,
same conditional-UPDATE claim, same reaper, same lost-enqueue sweep as
``resume_jobs``.  What differs is only what the work is::

    queued --> running --> succeeded
                       \\-> failed

**The only door since 3c.**  3b added these jobs alongside the synchronous
routes, because a client cannot move from awaiting a 200 to polling a job in
the same deploy that first gives it something to poll.  The frontend moved in
43a2024, and 3c closed the synchronous halves: ``POST
/assessments/{kind}/submissions`` answers the three moved kinds 410, and ``GET
/me/path-suggestions`` reads the cache a succeeded job warms and computes
nothing on a miss.

**Not every instrument moves, and the split is on what the scoring actually
does.**  ``assessment_service.AssessmentKind.scored_by`` already records it:

* ``work_pulse``, ``wpll``, ``manager_match`` are ``llm``.  Each makes a
  blocking OpenAI call of seconds-to-tens-of-seconds, and each is why the
  timeout is 120.  These move.
* ``core`` and ``focus_type`` are ``rules``.  They score in-process from
  deterministic tables -- no socket is opened -- and the contract capture
  measures them at 211 ms and 40 ms including the database writes and the HTTP
  round trip.  Handing a client a job to poll for work that finishes before the
  poll could be issued is strictly worse than answering it: two extra round
  trips, a row to reap, and a spinner for something that was already done.
  These stay synchronous, and ``JOB_ELIGIBLE_KINDS`` is where that decision
  lives rather than in prose.

There is a second reason ``core`` does not move, and it is the stronger one.
D-01 keeps person dimension scores off every wire an employer could reach, and
``core`` is the instrument that has them -- it deliberately returns none even to
the respondent (A12).  A job row stores its result in ``scoring_jobs.result``
and a poll endpoint serves it back; moving ``core`` would create a second place
those scores live and a second endpoint that emits them.  The instruments that
do move return narratives and archetypes.

**Rate limiting is the caller's job and it is not optional.**  A9's budgets
bound *provider spend*, and moving the provider call to a worker does not move
the spend -- it only changes who waits for it.  The enqueue endpoints therefore
carry the same per-instrument buckets as the synchronous submits, shared with
them, so a user cannot double their allowance by alternating paths.  Nothing in
this module enforces that; see ``solverah/api/v1/assessments.py``.

**The payload is nulled on a terminal state.**  It holds submitted answers,
which for the three persisting instruments are already in
``assessment_submissions.answers``.  Keeping a second copy past the scoring is
duplicate retention of assessment data with no reader.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import sqlalchemy as sa

from model import ScoringJob, User, db

__all__ = [
    "ASSESSMENT",
    "FAILED",
    "GENERIC_FAILURE",
    "JOB_ELIGIBLE_KINDS",
    "PATH_SUGGESTIONS",
    "PURGE_DAYS",
    "QUEUED",
    "RUNNING",
    "STALL_MINUTES",
    "SUCCEEDED",
    "create_assessment",
    "create_path_suggestions",
    "find_anonymous",
    "find_for_user",
    "is_job_eligible",
    "pending",
    "purge_terminal",
    "reap_stalled",
    "run",
    "status_for",
]

logger = logging.getLogger("solverah.scoring_jobs")

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"

ASSESSMENT = "assessment_scoring"
PATH_SUGGESTIONS = "path_suggestions"

#: The instruments that score off the request path.
#:
#: Exactly the ``scored_by == "llm"`` three.  Kept as a literal rather than
#: derived from ``ASSESSMENT_KINDS`` so that adding a sixth instrument is a
#: deliberate decision here about whether it blocks on a provider, not an
#: automatic consequence of a field somebody set for the catalogue's benefit.
#: ``tests/test_scoring_jobs.py`` asserts the two stay consistent.
JOB_ELIGIBLE_KINDS = ("work_pulse", "wpll", "manager_match")

#: How long a job may sit in a non-terminal state before the sweep fails it.
#:
#: The clock starts at enqueue rather than at pickup, so this has to absorb a
#: queue backed up behind a deploy as well as the scoring itself.  Same value as
#: ``resume_jobs`` for the same reason; an LLM call is slower than a parse but
#: both are minutes at the outside, and the number that matters is how long a
#: client is willing to hold a spinner.
STALL_MINUTES = 30

#: How long a terminal job's row survives.
#:
#: The row is a receipt, not a record: the three persisting instruments write
#: their real result to ``assessment_submissions`` and path suggestions writes
#: to the cache.  What is left here after a week is a result blob nobody will
#: poll for again, so the purge is what stops this table growing without bound.
#: ``wpll`` is the one whose result exists *only* here -- it is the anonymous
#: teaser and persists nothing -- and a week is far past the teaser's session.
PURGE_DAYS = 7

#: The only failure text a client is shown for an unhandled exception.
#:
#: Provider exceptions carry model names, request ids, and fragments of the
#: prompt -- which for these instruments contains the user's own answers and
#: resume-derived context.  A scoring failure must not become a disclosure on a
#: polling endpoint, so the exception goes to the logs with the job id and the
#: client gets this.
GENERIC_FAILURE = "Scoring failed. Please try again."

_table = ScoringJob.__table__


def is_job_eligible(kind_key: str) -> bool:
    """Whether *kind_key* scores off the request path. See the module docstring."""
    return kind_key in JOB_ELIGIBLE_KINDS


# ---------------------------------------------------------------------------
# Creating work
# ---------------------------------------------------------------------------


def _create(
    *,
    job_type: str,
    user_id: Optional[int],
    kind: Optional[str],
    payload: Dict[str, Any],
) -> ScoringJob:
    """Insert the row, commit it, then ask a worker for it.

    Committing before enqueuing is the ordering the outbox and ``resume_jobs``
    both use: a worker that receives the message before the row is visible finds
    nothing, and the answer to "what if the enqueue fails" has to be a row a
    sweep can find rather than a message that was never sent.
    """
    job = ScoringJob(
        user_id=user_id,
        job_type=job_type,
        kind=kind,
        payload=payload or {},
        status=QUEUED,
    )
    db.session.add(job)
    db.session.commit()

    from solverah.infra.queue import enqueue
    from solverah.tasks.scoring_tasks import run_scoring_job

    enqueue(run_scoring_job, job.id)
    return job


def create_assessment(
    kind_key: str, user: Optional[User], payload: Dict[str, Any]
) -> ScoringJob:
    """Queue one assessment scoring.

    *user* is None only for ``wpll``, the anonymous teaser.  The database check
    constraint ``ck_scoring_jobs_owner_required`` is what actually holds that
    line -- an ownerless row of any other kind is rejected by the schema rather
    than by this function remembering to.
    """
    return _create(
        job_type=ASSESSMENT,
        user_id=user.id if user is not None else None,
        kind=kind_key,
        payload=payload or {},
    )


def create_path_suggestions(user: User) -> ScoringJob:
    """Queue one path-suggestion scoring for *user*."""
    return _create(job_type=PATH_SUGGESTIONS, user_id=user.id, kind=None, payload={})


# ---------------------------------------------------------------------------
# Doing the work
# ---------------------------------------------------------------------------


def _claim(job_id: int) -> Optional[Dict[str, Any]]:
    """Move *job_id* from ``queued`` to ``running``, or return None.

    None means another worker holds it, or it has already finished.  Its own
    transaction, so the claim is durable before the provider call starts -- a
    claim that rolled back with the scoring would let a redelivery
    (``task_acks_late``) pay for the same completion twice, which on these three
    instruments is a real invoice rather than only wasted work.
    """
    with db.engine.begin() as connection:
        row = connection.execute(
            sa.update(_table)
            .where(_table.c.id == job_id, _table.c.status == QUEUED)
            .values(status=RUNNING, attempts=_table.c.attempts + 1)
            .returning(
                _table.c.user_id,
                _table.c.job_type,
                _table.c.kind,
                _table.c.payload,
            )
        ).first()

    if row is None:
        return None
    return {
        "user_id": row.user_id,
        "job_type": row.job_type,
        "kind": row.kind,
        "payload": row.payload or {},
    }


def _finish(
    job_id: int,
    status: str,
    *,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Write a terminal state and drop the payload, in one transaction.

    The payload is cleared here rather than by the purge sweep because the
    moment the scoring is done is the moment the answers stop having a reader;
    leaving it to a periodic job would mean the duplicate lives for however long
    that job is behind.
    """
    with db.engine.begin() as connection:
        connection.execute(
            sa.update(_table)
            .where(_table.c.id == job_id)
            .values(status=status, result=result, error=error, payload={})
        )


def _score_assessment(
    claimed: Dict[str, Any]
) -> Tuple[str, Optional[Dict], Optional[str]]:
    """Run one assessment scoring through the same service the submit route uses.

    Deliberately calls ``assessment_service.submit`` rather than reimplementing
    the dispatch: the synchronous route and this must produce the same result for
    the same answers, and the only way to guarantee that is for there to be one
    scorer.  ``tests/test_scoring_jobs.py`` asserts the equivalence on both the
    success and the validation-failure paths.
    """
    from solverah.repositories import user_repository
    from solverah.services import assessment_service

    kind = assessment_service.find_kind(claimed["kind"])
    if kind is None:
        return FAILED, None, GENERIC_FAILURE

    user = None
    if claimed["user_id"] is not None:
        user = user_repository.find_by_id(claimed["user_id"])
        if user is None:
            # The account went away between enqueue and pickup. Nothing to score
            # and nobody to serve it to; the row goes terminal so the reaper does
            # not spend the stall window on it.
            return FAILED, None, GENERIC_FAILURE

    outcome = assessment_service.submit(kind, user, claimed["payload"], logger)
    if outcome.status == 200:
        return SUCCEEDED, outcome.body, None

    # `assessment_service` writes its own error strings and they are fixed text
    # -- "answers must be a list of exactly 12 items", "Unable to generate Work
    # Pulse results". Passing those through is what makes a failed job
    # actionable. Anything that is not a string the service authored is replaced.
    message = outcome.body.get("error") if isinstance(outcome.body, dict) else None
    return FAILED, None, message if isinstance(message, str) else GENERIC_FAILURE


def _score_path_suggestions(
    claimed: Dict[str, Any]
) -> Tuple[str, Optional[Dict], Optional[str], Optional[Callable[[], Dict]]]:
    """Run one path-suggestion scoring; the service call warms the cache.

    ``intelligence_service.path_suggestions`` populates ``path_cache`` as it
    returns, and since 3c that cache is the *only* thing ``GET
    /me/path-suggestions`` serves -- this job is what stands between a miss
    there and an empty screen.

    The fourth value (W-16) is the narration phase still to run, or None when
    every sentence was already stored. :func:`run` starts it after the scored
    result is written.
    """
    from solverah.repositories import user_repository
    from solverah.services import intelligence_service

    user = user_repository.find_by_id(claimed["user_id"])
    if user is None:
        return FAILED, None, GENERIC_FAILURE, None

    outcome = intelligence_service.path_suggestions(user, logger)
    if outcome.status == 200:
        return SUCCEEDED, outcome.body, None, outcome.narration

    message = outcome.body.get("error") if isinstance(outcome.body, dict) else None
    return FAILED, None, message if isinstance(message, str) else GENERIC_FAILURE, None


def _record_narration(job_id: int, result: Dict[str, Any]) -> None:
    """Replace a succeeded job's scored result with its narrated one (W-16).

    Since W-17 also with each PARTIAL result -- the page's first three filled in
    as they land, `narration_pending` still true -- so the poll shows them
    before the rest are written.

    Conditional on the row still being ``succeeded``: a job the purge deleted,
    or a row that is somehow no longer the success it was a second ago, is left
    alone rather than resurrected. Its own transaction, like :func:`_finish` --
    it runs on the narration thread, not inside anybody's request.
    """
    with db.engine.begin() as connection:
        connection.execute(
            sa.update(_table)
            .where(_table.c.id == job_id, _table.c.status == SUCCEEDED)
            .values(result=result)
        )


def run(job_id: int) -> str:
    """Do one job and record the outcome. Returns the terminal status.

    ``skipped`` -- not a stored state -- means the claim found nothing to do,
    which is the correct and expected outcome of a redelivered message for a job
    that already ran.
    """
    claimed = _claim(job_id)
    if claimed is None:
        logger.info(
            "scoring_job_not_claimable",
            extra={"event": "scoring_job_not_claimable", "job_id": job_id},
        )
        return "skipped"

    narration = None
    try:
        if claimed["job_type"] == ASSESSMENT:
            status, result, error = _score_assessment(claimed)
        else:
            status, result, error, narration = _score_path_suggestions(claimed)
    except Exception as exc:  # noqa: BLE001 -- the job row is the error channel
        db.session.rollback()
        logger.exception(
            "scoring_job_failed",
            extra={
                "event": "scoring_job_failed",
                "job_id": job_id,
                "job_type": claimed["job_type"],
                "error": str(exc),
            },
        )
        _finish(job_id, FAILED, error=GENERIC_FAILURE)
        return FAILED

    _finish(job_id, status, result=result, error=error)
    logger.info(
        "scoring_job_finished",
        extra={
            "event": "scoring_job_finished",
            "job_id": job_id,
            "job_type": claimed["job_type"],
            "kind": claimed["kind"],
            "status": status,
        },
    )

    # W-16. Cards first, sentences after. The scored result is committed above,
    # so the poll can render the cards from this moment; the narration runs
    # after, off this thread, and replaces the result with the narrated one when
    # it lands. In that order and no other: started before `_finish`, a fast
    # narration could write its result first and then be overwritten by the
    # scored one, leaving a job that says "pending" about sentences that exist.
    #
    # If this process dies mid-narration the row is still `succeeded` -- the
    # reaper never sees it, because it only fails `queued`/`running` rows -- and
    # `intelligence_service.resolve_stale_narration` is what ends the wait: every
    # read past NARRATION_DEADLINE serves the fallback sentences instead.
    if narration is not None and status == SUCCEEDED:
        from solverah.services import intelligence_service

        try:
            # W-17: the same write for a partial result as for the final one.
            # Both run on the narration thread, partials first, so the final
            # payload is always the last thing written.
            intelligence_service.start_narration(
                narration,
                lambda final: _record_narration(job_id, final),
                on_partial=lambda partial: _record_narration(job_id, partial),
            )
        except Exception:  # noqa: BLE001 -- the deadline read covers the job
            logger.exception(
                "path_narration_not_started",
                extra={"event": "path_narration_not_started", "job_id": job_id},
            )
    return status


# ---------------------------------------------------------------------------
# Reading a job back
# ---------------------------------------------------------------------------


def _parse_handle(public_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(public_id)
    except (ValueError, AttributeError, TypeError):
        return None


def find_for_user(
    user_id: int, public_id: str, *, job_type: str, kind: Optional[str] = None
) -> Optional[ScoringJob]:
    """One of *user_id*'s jobs by its handle, or None.

    Scoped by ``user_id`` **and** by ``job_type``/``kind`` in the query rather
    than checked afterwards.  The ownership filter is the same rule
    ``resume_jobs`` follows -- somebody else's handle must be indistinguishable
    from one that does not exist.  The type filter is what stops a Work Pulse job
    being polled at the ManagerMatch path and served under ManagerMatch's
    response model, which is A12's per-discriminator promise broken from the read
    side.
    """
    parsed = _parse_handle(public_id)
    if parsed is None:
        return None

    query = ScoringJob.query.filter_by(
        user_id=user_id, public_id=parsed, job_type=job_type
    )
    if kind is not None:
        query = query.filter_by(kind=kind)
    return query.first()


def find_anonymous(public_id: str, *, kind: str) -> Optional[ScoringJob]:
    """An ownerless job by its handle -- ``wpll`` only.

    ``wpll`` has no account, so the handle is the capability: holding it is the
    whole of the authorisation, which is why ``user_id IS NULL`` is part of the
    filter rather than assumed.  Without it this would serve any user's job of
    that kind to an unauthenticated caller who guessed a handle.

    Safe only because the instrument is the anonymous teaser and its result is a
    single generated sentence with no account behind it.  The check constraint
    ``ck_scoring_jobs_owner_required`` is what stops any other kind reaching this
    function with a row to find.
    """
    parsed = _parse_handle(public_id)
    if parsed is None:
        return None

    return ScoringJob.query.filter(
        ScoringJob.public_id == parsed,
        ScoringJob.user_id.is_(None),
        ScoringJob.job_type == ASSESSMENT,
        ScoringJob.kind == kind,
    ).first()


def status_for(job: ScoringJob) -> Dict[str, Any]:
    """The status payload for one job.

    ``result`` is present only on success and is whatever that discriminator's
    scorer produced -- the same body the synchronous route returns for the same
    submission.  The *shape* of it is the route's promise, not this function's:
    each poll endpoint publishes and validates the per-kind model, which is what
    keeps A12's "a response model per discriminator" true on the job path too.
    """
    body: Dict[str, Any] = {
        "job_id": job.public_id.hex,
        "status": job.status,
        "error": job.error,
    }
    if job.status == SUCCEEDED and job.result is not None:
        result = job.result
        if job.job_type == PATH_SUGGESTIONS:
            # W-16. A result still saying `narration_pending` past the deadline
            # belongs to a narration whose worker died; read it with the
            # fallback sentences filled in so the page stops waiting.
            from solverah.services import intelligence_service

            result = intelligence_service.resolve_stale_narration(result)
        body["result"] = result
    return body


# ---------------------------------------------------------------------------
# The sweeps
# ---------------------------------------------------------------------------


def reap_stalled(older_than_minutes: int = STALL_MINUTES) -> int:
    """Fail jobs stuck in a non-terminal state past the deadline.

    A worker killed mid-scoring leaves a row in ``running`` that nothing will
    move, and a client polling it waits forever.  Failing it is the honest
    answer: the scoring did not happen and the user can submit again.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=older_than_minutes
    )
    with db.engine.begin() as connection:
        result = connection.execute(
            sa.update(_table)
            .where(
                _table.c.status.in_((QUEUED, RUNNING)),
                _table.c.created_at < cutoff,
            )
            .values(status=FAILED, error=GENERIC_FAILURE, payload={})
        )
    reaped = result.rowcount or 0
    if reaped:
        logger.warning(
            "scoring_jobs_reaped",
            extra={"event": "scoring_jobs_reaped", "count": reaped},
        )
    return reaped


def pending(limit: int = 100) -> List[int]:
    """Ids of jobs still queued. The sweep's half of a lost enqueue."""
    with db.engine.connect() as connection:
        return [
            row.id
            for row in connection.execute(
                sa.select(_table.c.id)
                .where(_table.c.status == QUEUED)
                .order_by(_table.c.created_at)
                .limit(limit)
            )
        ]


def purge_terminal(older_than_days: int = PURGE_DAYS) -> int:
    """Delete terminal rows past their retention window.

    Without this the table grows with every scoring forever, holding result blobs
    nobody will poll for again -- and for ``wpll`` those rows have no account
    behind them, so no account deletion ever removes them.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=older_than_days
    )
    with db.engine.begin() as connection:
        result = connection.execute(
            sa.delete(_table).where(
                _table.c.status.in_((SUCCEEDED, FAILED)),
                _table.c.created_at < cutoff,
            )
        )
    purged = result.rowcount or 0
    if purged:
        logger.info(
            "scoring_jobs_purged",
            extra={"event": "scoring_jobs_purged", "count": purged},
        )
    return purged
