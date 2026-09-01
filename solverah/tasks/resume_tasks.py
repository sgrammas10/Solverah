"""Resume parsing, off the request path.

On ``default`` rather than ``llm``: the parser is pdfminer and python-docx, which
is CPU and disk, not a provider call.  It shares the queue with anything else
short and unclassified, and it is bounded by the 10MB upload cap.
"""

from __future__ import annotations

from solverah.infra.queue import QUEUE_DEFAULT, QUEUE_MAINTENANCE, celery_app
from solverah.services import resume_jobs

__all__ = ["parse_resume_job", "sweep_resume_jobs"]


@celery_app.task(name="solverah.resume.parse_job", queue=QUEUE_DEFAULT)
def parse_resume_job(job_id: int) -> str:
    """Parse one uploaded resume into its owner's profile."""
    return resume_jobs.run(job_id)


@celery_app.task(name="solverah.resume.sweep_jobs", queue=QUEUE_MAINTENANCE)
def sweep_resume_jobs(limit: int = 100) -> dict:
    """Pick up jobs the broker never delivered, and fail the ones that stalled.

    The two halves cover the two ways :func:`parse_resume_job` can fail to
    happen. A lost enqueue leaves a row in ``queued`` that no message exists for,
    so it is re-run here. A worker killed mid-parse leaves one in ``running``
    that nothing will move, so past the deadline it is failed -- a client
    polling it needs an answer rather than an indefinite spinner.
    """
    reaped = resume_jobs.reap_stalled()
    requeued = 0
    for job_id in resume_jobs.pending_ids(limit=limit):
        parse_resume_job.apply_async(args=(job_id,))
        requeued += 1
    return {"reaped": reaped, "requeued": requeued}
