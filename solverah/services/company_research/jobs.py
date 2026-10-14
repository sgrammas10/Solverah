"""How a research or posting job gets off the request thread.

Three paths, chosen at dispatch time, in this order:

1. **A broker is configured** (``solverah.infra.queue`` is not eager): hand the Celery
   task to the broker through ``enqueue`` -- the pattern ``scoring_jobs`` uses. The
   task carries its own time limits (``solverah/tasks/company_research_tasks.py``).
2. **Eager and inline** (``COMPANY_RESEARCH_INLINE``, default on under ``TESTING``):
   the same ``enqueue`` call, which under eager Celery runs the task body inline in
   this process. Deterministic, which is what the tests need.
3. **Eager and not inline** -- which is PRODUCTION (one Render web service, no Redis,
   no worker; ``intelligence_service.start_narration`` documents the same fact for
   W-16): a bounded thread pool with the Flask app context pushed, so the job gets
   its own database session and the request returns at once. A research turn runs
   for minutes; inline in a request it would be killed at gunicorn's 30 s timeout.

Path 3 has no time limit of its own: the research client's 600 s stream-silence
timeout and ``MAX_CONTINUATIONS`` bound a turn, and ``service.sweep_research_runs``
fails a ``running`` row older than the research hard limit so a dead thread does not
leave a run spinning forever. The pool's threads are NOT daemon threads: Python joins
``ThreadPoolExecutor`` workers at interpreter exit, so a process that dispatched a run
(the web process, or the ``flask companies sweep`` cron re-dispatching a stale
``queued`` row) waits for the run to finish before it exits. A process KILLED mid-run
(a deploy, an OOM) leaves the row ``running`` for the sweep to reap.

Because the sweep re-dispatches a row the web pool may still be about to run, a row
can be handed to two workers. The job body claims the row atomically first
(``store.mark_research_run_running``) and the loser returns without a provider call;
see ``service.run_research_job``.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from solverah.services.company_research.constants import RESEARCH_THREAD_WORKERS

__all__ = ["INLINE_CONFIG_KEY", "dispatch"]

logger = logging.getLogger("solverah.company_research.jobs")

INLINE_CONFIG_KEY = "COMPANY_RESEARCH_INLINE"

_pool: Optional[ThreadPoolExecutor] = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(
                max_workers=RESEARCH_THREAD_WORKERS, thread_name_prefix="company-research"
            )
        return _pool


def dispatch(task, run_inline: Callable[[int], object], row_id: int) -> str:
    """Start the job for *row_id*. Returns which path was taken: ``"queued"``,
    ``"inline"`` or ``"threaded"``. Never raises into the caller: a broker that
    cannot be reached is logged by ``enqueue`` and the sweep re-dispatches."""
    from solverah.infra.queue import active_flask_app, enqueue, is_eager

    if not is_eager():
        enqueue(task, row_id)
        return "queued"

    # The app the caller runs under, not merely the last one `create_app()` built
    # (see `active_flask_app`).
    app = active_flask_app()
    inline = app is None or app.config.get(INLINE_CONFIG_KEY, app.testing)
    if inline:
        enqueue(task, row_id)  # eager: runs the task body now, in this process
        return "inline"

    def run_in_context() -> None:
        with app.app_context():
            try:
                run_inline(row_id)
            except Exception:  # noqa: BLE001 -- the run row is the error channel
                logger.exception(
                    "company_research_thread_crashed",
                    extra={"event": "company_research_thread_crashed", "row_id": row_id},
                )

    future: Future = _get_pool().submit(run_in_context)
    del future  # fire and forget; the run row is what anyone polls
    return "threaded"
