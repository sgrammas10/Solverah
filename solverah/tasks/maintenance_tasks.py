"""Sweeps and backfills. Nothing here is ever triggered by a request.

That is the defining property of this queue rather than a coincidence.  Work
here can be delayed indefinitely without a user noticing, which is exactly why
it must not share a queue with an outbox publish or a resume parse -- and why
:func:`backfill_culture_preferences` can exist at all.

The backfill is the replacement for a write that used to happen on
``GET /me/matches``.  ``resolve_culture_preferences`` derived a user's culture
vector from their Work Pulse answers when the profile did not have one, then
persisted it and **committed, inside a GET** -- the second half of P0-3.  The
derivation is cheap and deterministic, so the read now simply derives what it
needs and returns; the persistence it was doing on the side is this task,
running once over the accounts that predate ``culture_preferences`` being
written at submit time.
"""

from __future__ import annotations

import logging

from solverah.infra.queue import QUEUE_MAINTENANCE, celery_app
from solverah.services import matching_service

__all__ = ["backfill_culture_preferences"]

logger = logging.getLogger("solverah.tasks.maintenance")


@celery_app.task(name="solverah.maintenance.backfill_culture_preferences",
                 queue=QUEUE_MAINTENANCE)
def backfill_culture_preferences(limit: int = 500) -> dict:
    """Persist derived culture preferences for accounts that lack them.

    Bounded by *limit* and safe to run repeatedly: it selects only users who are
    still missing the key, so a second run over a finished backfill does nothing.
    """
    counts = matching_service.backfill_culture_preferences(limit=limit)
    if counts.get("written"):
        logger.info(
            "culture_preferences_backfilled",
            extra={"event": "culture_preferences_backfilled", **counts},
        )
    return counts
