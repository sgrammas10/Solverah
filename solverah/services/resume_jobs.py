"""Resume parsing as a job, rather than as something a request waits for.

Phase 3, item 3, and P0-6's most visible instance.  ``POST /me/resumes/{id}/complete``
downloads the object from R2, writes it to a temp file, runs pdfminer or
python-docx over it, and merges the result into the profile -- all inside the
request.  A large PDF holds a gunicorn worker for the duration, which is part of
why ``gunicorn.conf.py`` carries a 120-second timeout.

**This is an addition, not a replacement.**  The synchronous endpoint is
untouched and still works.  A frontend cannot switch from "await a 200" to
"poll a job" in the same deploy that gives it something to poll, so both exist
until it has; Part 5.2's ``202`` is the destination and this is the half of it
the backend can land alone.  The exit criterion for the whole of Phase 3 --
dropping the gunicorn timeout to 30s -- is deliberately *not* claimed here,
because assessment scoring and path suggestions are still synchronous.

**The state machine, and the two states that are not terminal.**

    queued ──► running ──► succeeded
                      └──► failed

``queued`` and ``running`` are where a job sits if the worker never picks it up
or dies mid-parse.  :func:`reap_stalled` is what stops those becoming jobs that
poll forever: past a deadline they are failed with a reason, because a client
holding a spinner needs an answer more than it needs an optimistic status.

**Claiming is a conditional UPDATE, not a read-then-write.**  ``UPDATE ... WHERE
status = 'queued'`` returning zero rows means somebody else already has it, which
is how a redelivered message (``task_acks_late``) results in one parse rather
than two.  The parse itself is not transactional -- it fetches bytes over the
network -- so the claim is what stands in for that.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional

import sqlalchemy as sa

from model import ResumeParseJob, User, db
from solverah.repositories import profile_repository
from solverah.services import resume_service

__all__ = [
    "FAILED",
    "PURGE_DAYS",
    "QUEUED",
    "RUNNING",
    "STALL_MINUTES",
    "SUCCEEDED",
    "create",
    "purge_terminal",
    "reap_stalled",
    "run",
    "status_for",
]

logger = logging.getLogger("solverah.resume_jobs")

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"

#: How long a job may sit in a non-terminal state before the sweep fails it.
#:
#: Generous relative to a parse (seconds) because the clock starts at enqueue,
#: not at pickup: a queue backed up behind a deploy is a slow job, not a stalled
#: one, and failing those would turn a rolling restart into a wave of bogus
#: errors.
STALL_MINUTES = 30

#: How long a terminal job's row survives before :func:`purge_terminal` deletes it.
#:
#: Longer than ``scoring_jobs``' seven days because these rows are the support
#: record for "my resume didn't parse" -- ``attempts``, the object key, and the
#: failure reason -- and that conversation can start a while after the upload.
#: Thirty days is a support window; keeping name-bearing filenames past it is
#: retention with no reader (SECURITY_AUDIT_2026-09 #7).
PURGE_DAYS = 30

#: The only failure text a client is ever shown.
#:
#: Parse failures come from pdfminer, python-docx, and botocore, and their
#: messages carry bucket names, object keys, and file paths.  Mapping to a fixed
#: string means a 500 from storage cannot become an information leak on a polling
#: endpoint; the real exception goes to the logs with the job id.
GENERIC_FAILURE = "Could not parse the uploaded resume."

_table = ResumeParseJob.__table__


def create(
    user: User, *, object_key: str, mime: str, size: int, name: str
) -> ResumeParseJob:
    """Record the request to parse, commit it, and ask a worker to do the work.

    Committing before enqueuing is the same ordering the outbox uses and for the
    same reason: a worker that receives the message before the row is visible
    finds nothing, and the answer to "what if the enqueue fails" has to be a row
    a sweep can find rather than a message that was never sent.

    Returns the job *detached*, holding its columns as written.  ``id`` and
    ``public_id`` are server-generated and come back on the INSERT's
    ``RETURNING``; detaching before the commit keeps them readable afterwards.
    Left attached, the commit would expire them, and the first read after it --
    the enqueue below, or the route's ``public_id`` -- would reload a row this
    function had just written.  The ``status`` it reports is therefore always
    ``queued``, the state it was written in, which is what the ``202`` means.
    """
    job = ResumeParseJob(
        user_id=user.id,
        object_key=object_key,
        mime=mime,
        size_bytes=size,
        resume_name=name or None,
        status=QUEUED,
    )
    db.session.add(job)
    db.session.flush()
    db.session.expunge(job)
    db.session.commit()

    from solverah.infra.queue import enqueue
    from solverah.tasks.resume_tasks import parse_resume_job

    enqueue(parse_resume_job, job.id)
    return job


def _claim(job_id: int) -> Optional[Dict[str, Any]]:
    """Move *job_id* from ``queued`` to ``running``, or return None.

    None means another worker holds it, or it has already finished.  Its own
    transaction, so the claim is durable before the parse starts -- a claim that
    rolled back with the parse would let a redelivery run the work twice.
    """
    with db.engine.begin() as connection:
        row = connection.execute(
            sa.update(_table)
            .where(_table.c.id == job_id, _table.c.status == QUEUED)
            .values(status=RUNNING, attempts=_table.c.attempts + 1)
            .returning(
                _table.c.user_id,
                _table.c.object_key,
                _table.c.mime,
                _table.c.size_bytes,
                _table.c.resume_name,
            )
        ).first()

    if row is None:
        return None
    return {
        "user_id": row.user_id,
        "object_key": row.object_key,
        "mime": row.mime,
        "size_bytes": row.size_bytes,
        "resume_name": row.resume_name,
    }


def _finish(job_id: int, status: str, error: Optional[str] = None) -> None:
    """Write a terminal state, in its own transaction."""
    with db.engine.begin() as connection:
        connection.execute(
            sa.update(_table)
            .where(_table.c.id == job_id)
            .values(status=status, error=error)
        )


def run(job_id: int) -> str:
    """Do one job's parse and record the outcome. Returns the terminal status.

    Runs the same merge ``profile_service.finish_resume_upload`` does, through
    ``profile_repository.update_document`` -- so the optimistic-lock retry that
    protects a concurrent profile save protects this too, and a parse landing
    while the user is editing their profile cannot clobber the edit.

    Uses ``db.session`` for the merge, unlike the claim and the finish either
    side of it.  That is deliberate rather than inconsistent: the merge is the
    compare-and-swap in ``update_document``, which is ORM code, and reimplementing
    it against a Core connection would be a second copy of the one write path
    Phase 2a exists to have only once.  It is safe here because every caller
    reaches this with a clean session -- a worker has nothing else open, and
    :func:`create` commits before it enqueues.
    """
    claimed = _claim(job_id)
    if claimed is None:
        logger.info(
            "resume_job_not_claimable",
            extra={"event": "resume_job_not_claimable", "job_id": job_id},
        )
        return "skipped"

    try:
        profile_updates = resume_service.build_profile_from_resume_key(
            resume_key=claimed["object_key"],
            resume_mime=claimed["mime"],
            resume_size_bytes=claimed["size_bytes"],
            resume_name=claimed["resume_name"],
        )
        snapshot = resume_service.snapshot_of(claimed["object_key"], profile_updates)

        def merge(existing: Dict[str, Any]) -> Dict[str, Any]:
            return {**existing, **profile_updates, "_parsedResumeSnapshot": snapshot}

        profile_repository.update_document(claimed["user_id"], merge)
        db.session.commit()
    except Exception as exc:  # noqa: BLE001 -- the job row is the error channel
        db.session.rollback()
        logger.exception(
            "resume_job_failed",
            extra={"event": "resume_job_failed", "job_id": job_id, "error": str(exc)},
        )
        _finish(job_id, FAILED, GENERIC_FAILURE)
        return FAILED

    _finish(job_id, SUCCEEDED)
    logger.info("resume_job_succeeded",
                extra={"event": "resume_job_succeeded", "job_id": job_id})
    return SUCCEEDED


def find_for_user(user_id: int, public_id: str) -> Optional[ResumeParseJob]:
    """One of *user_id*'s jobs by its public handle, or None.

    Scoped by ``user_id`` in the query rather than checked afterwards: a job
    handle belonging to somebody else must be indistinguishable from one that
    does not exist, and a filter cannot be forgotten the way a follow-up ``if``
    can.
    """
    try:
        parsed = uuid.UUID(public_id)
    except (ValueError, AttributeError, TypeError):
        return None

    return ResumeParseJob.query.filter_by(user_id=user_id, public_id=parsed).first()


def status_for(job: ResumeParseJob) -> Dict[str, Any]:
    """The status payload for one job.

    ``profile`` is present only on success, and it is the current document rather
    than a snapshot taken when the job finished: the client is about to render
    it, and a document from thirty seconds ago could already be behind a profile
    save the same user made in another tab.
    """
    body: Dict[str, Any] = {
        "job_id": job.public_id.hex,
        "status": job.status,
        "error": job.error,
    }
    if job.status == SUCCEEDED:
        body["profile"] = profile_repository.load_document(job.user_id)
    return body


def reap_stalled(older_than_minutes: int = STALL_MINUTES) -> int:
    """Fail jobs stuck in a non-terminal state past the deadline.

    A worker killed mid-parse leaves a row in ``running`` that nothing will ever
    move, and a client polling it waits forever.  Failing it is the honest
    answer: the parse did not happen, and the user can upload again.
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
            .values(status=FAILED, error=GENERIC_FAILURE)
        )
    reaped = result.rowcount or 0
    if reaped:
        logger.warning(
            "resume_jobs_reaped", extra={"event": "resume_jobs_reaped", "count": reaped}
        )
    return reaped


def pending_ids(limit: int = 100) -> List[int]:
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

    SECURITY_AUDIT_2026-09 finding #7: these rows carry ``resume_name`` (often a
    person's own name in the filename) and ``object_key``, ``user_id`` cascades
    on a hard DELETE that account *tombstoning* never issues, and no purge
    existed -- so they survived forever.  The parse result itself lives in the
    profile tables; after :data:`PURGE_DAYS` the row is a stale receipt.

    Only ``succeeded``/``failed`` rows are deleted.  A ``queued`` or ``running``
    row -- however old -- is :func:`reap_stalled`'s to fail first; deleting it
    would turn a pollable job into a 404.
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
            "resume_jobs_purged",
            extra={"event": "resume_jobs_purged", "count": purged},
        )
    return purged
