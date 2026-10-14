"""CompanyLens research and posting jobs, as Celery tasks (six-trait build, C5).

On ``llm``: both make provider calls, and a research turn runs for minutes. Each task
carries its own time limits (``constants.py``): the soft limit raises inside the task
so ``service.run_research_job`` records the run as ``timed_out`` with the cost spent;
the hard limit is the backstop that kills a worker process that stopped listening.

The sweep is the guarantee behind ``enqueue`` for ``company_research_run`` (a lost
enqueue is re-sent; a dead run is failed). In production it is NOT scheduled through
Celery beat: it runs as the Render cron ``solverah-companies-sweep`` (``render.yaml``,
every 10 minutes), which calls ``flask companies sweep`` -> ``service.sweep_research_runs``
directly. The Celery task below exists for a deployment with a broker and a worker.

Production runs Celery eager with no worker, so in production these bodies run on the
service's own thread pool (``solverah/services/company_research/jobs.py``), not here;
a sweep-requeued run executes inside the cron process, which waits for it to finish.
"""

from __future__ import annotations

from solverah.infra.queue import QUEUE_LLM, QUEUE_MAINTENANCE, celery_app
from solverah.services.company_research import service
from solverah.services.company_research.constants import (
    POSTING_JOB_HARD_LIMIT_SECONDS,
    POSTING_JOB_SOFT_LIMIT_SECONDS,
    RESEARCH_JOB_HARD_LIMIT_SECONDS,
    RESEARCH_JOB_SOFT_LIMIT_SECONDS,
)

__all__ = ["run_job_posting_task", "run_research_task", "sweep_research_runs_task"]


@celery_app.task(
    name="solverah.company_research.run_research",
    queue=QUEUE_LLM,
    soft_time_limit=RESEARCH_JOB_SOFT_LIMIT_SECONDS,
    time_limit=RESEARCH_JOB_HARD_LIMIT_SECONDS,
)
def run_research_task(run_id: int) -> str:
    """Research, score and aggregate one company."""
    return service.run_research_job(run_id).status


@celery_app.task(
    name="solverah.company_research.run_job_posting",
    queue=QUEUE_LLM,
    soft_time_limit=POSTING_JOB_SOFT_LIMIT_SECONDS,
    time_limit=POSTING_JOB_HARD_LIMIT_SECONDS,
)
def run_job_posting_task(posting_id: int) -> str:
    """Extract, score and aggregate one pasted posting."""
    return service.run_job_posting_job(posting_id).status


@celery_app.task(name="solverah.company_research.sweep_runs", queue=QUEUE_MAINTENANCE)
def sweep_research_runs_task() -> dict:
    """Re-dispatch lost enqueues and fail dead runs."""
    from model import db

    return service.sweep_research_runs(db)
