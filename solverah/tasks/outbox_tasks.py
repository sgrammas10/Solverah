"""Publishing the transactional outbox.

Two tasks, and the difference between them is the whole reliability story.

:func:`publish_entry` is the fast path: the request that wrote the row asks for
it to go out now.  It is best-effort by construction -- the enqueue can fail, the
broker can be down, the worker can die between delivery and completion.

:func:`drain_outbox` is what makes that acceptable.  It sweeps everything still
owed, so every way the fast path can fail resolves into "published a bit later"
rather than "never published".  Run it on a schedule (Celery beat, or a cron
hitting the same service function); the queue it lives on is ``maintenance``
precisely so a backlog of sweeps cannot delay the emails a user is waiting on.
"""

from __future__ import annotations

import logging

from solverah.infra.queue import QUEUE_EMAIL, QUEUE_MAINTENANCE, celery_app
from solverah.services import outbox

__all__ = ["drain_outbox", "publish_entry", "purge_published_outbox"]

logger = logging.getLogger("solverah.tasks.outbox")


@celery_app.task(name="solverah.outbox.publish_entry", queue=QUEUE_EMAIL)
def publish_entry(entry_id: int) -> str:
    """Publish one outbox row.

    No ``autoretry_for``.  Retry policy lives in the table -- ``attempts``, and
    the sweep that reads it -- rather than in the broker, so a row is retried the
    same number of times whether the failure was the provider, the worker, or the
    broker losing the message entirely.  A second retry mechanism on top would
    make the effective count the product of the two.
    """
    return outbox.publish(entry_id)


@celery_app.task(name="solverah.outbox.drain", queue=QUEUE_MAINTENANCE)
def drain_outbox(limit: int = 100) -> dict:
    """Publish everything still owed. The safety net; see the module docstring."""
    counts = outbox.drain(limit=limit)
    if counts.get("selected"):
        logger.info("outbox_drained", extra={"event": "outbox_drained", **counts})
    return counts


@celery_app.task(name="solverah.outbox.purge_published", queue=QUEUE_MAINTENANCE)
def purge_published_outbox(older_than_hours: int = 24) -> int:
    """Delete delivered rows past their retention. See ``outbox.purge_published``."""
    deleted = outbox.purge_published(older_than_hours=older_than_hours)
    if deleted:
        logger.info(
            "outbox_purged", extra={"event": "outbox_purged", "deleted": deleted}
        )
    return deleted
