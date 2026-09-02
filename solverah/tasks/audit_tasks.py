"""Audit rows written off the request path.

The other half of P0-3: ``GET`` handlers record what was read without taking a
write lock on the request that is doing the reading.  See
``solverah/services/audit.py`` for which of the two recording paths a caller
should be on and why.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from solverah.infra.queue import QUEUE_MAINTENANCE, celery_app
from solverah.services import audit

__all__ = ["record_audit_event"]


@celery_app.task(name="solverah.audit.record_event", queue=QUEUE_MAINTENANCE)
def record_audit_event(
    action: str,
    actor_user_id: Optional[int],
    resource: str,
    metadata: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Insert one audit row.

    ``maintenance`` rather than ``default``: an audit row is the least
    latency-sensitive write in the system, and a burst of reads must not delay
    the queue an outbox publish or a resume parse is waiting in.
    """
    audit.write_event(
        action=action,
        actor_user_id=actor_user_id,
        resource=resource,
        metadata=metadata,
        ip=ip,
        user_agent=user_agent,
    )
