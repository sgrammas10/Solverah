"""Assessment scoring and path suggestions, off the request path.

On ``llm`` rather than ``default``, unlike resume parsing: every job this module
runs makes a provider call.  That is the whole reason the ``llm`` queue exists
separately -- a burst of forty-second scorings must not sit in front of a
verification email, and the queue is what gives the two independent worker
counts.

One task for both job types, dispatched on ``job_type`` inside
:func:`solverah.services.scoring_jobs.run`.  Two tasks would be two names on the
wire for one state machine, and the sweep would have to know which name to
re-send for each row -- a lookup that exists only to undo a split that bought
nothing.
"""

from __future__ import annotations

from solverah.infra.queue import QUEUE_LLM, QUEUE_MAINTENANCE, celery_app
from solverah.services import scoring_jobs

__all__ = ["run_scoring_job", "sweep_scoring_jobs", "purge_scoring_jobs"]


@celery_app.task(name="solverah.scoring.run_job", queue=QUEUE_LLM)
def run_scoring_job(job_id: int) -> str:
    """Score one submission, or one user's career paths."""
    return scoring_jobs.run(job_id)


@celery_app.task(name="solverah.scoring.sweep_jobs", queue=QUEUE_MAINTENANCE)
def sweep_scoring_jobs(limit: int = 100) -> dict:
    """Pick up jobs the broker never delivered, and fail the ones that stalled.

    The two halves cover the two ways :func:`run_scoring_job` can fail to happen,
    exactly as ``resume_tasks.sweep_resume_jobs`` does.  A lost enqueue leaves a
    row in ``queued`` that no message exists for, so it is re-sent here.  A worker
    killed mid-scoring leaves one in ``running`` that nothing will move, so past
    the deadline it is failed -- a client polling it needs an answer rather than
    an indefinite spinner.
    """
    reaped = scoring_jobs.reap_stalled()
    requeued = 0
    for job_id in scoring_jobs.pending(limit=limit):
        run_scoring_job.apply_async(args=(job_id,))
        requeued += 1
    return {"reaped": reaped, "requeued": requeued}


@celery_app.task(name="solverah.scoring.purge_jobs", queue=QUEUE_MAINTENANCE)
def purge_scoring_jobs() -> int:
    """Delete terminal job rows past their retention window.

    ``resume_parse_jobs`` has no equivalent because its rows are bounded by the
    account they cascade from.  These are not: a ``wpll`` job is anonymous, so no
    account deletion will ever reach it and nothing else would bound the table.
    """
    return scoring_jobs.purge_terminal()
