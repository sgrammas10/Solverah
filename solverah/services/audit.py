"""Audit event recording.

Formerly ``app.py:log_audit_event``.  It is the single seam for audit writes, so
a test substitutes ``solverah.services.audit.log_audit_event`` once regardless of
which service is doing the writing.

Two known problems are carried forward unchanged, because fixing either one here
would change behaviour in a batch whose contract is that behaviour does not
change:

* ``GET /api/profile`` writes one of these rows and commits on every read
  (P0-3).  Session restore fires it on every page load, so the highest-volume
  table in the system is written synchronously on the hottest endpoint, taking a
  write lock on a request that ought to be servable from a replica.  Phase 3
  moves it off the request path.
* ``AuditLog`` has a foreign key to ``user.id`` (P1-8), which couples the
  highest-volume table to the identity table and blocks relocating it to cheaper
  storage.  Phase 2 drops the constraint and partitions the table by month.

This module reads ``flask.request`` for the IP and user agent, which makes it the
one service that cannot be called from a worker as-is.  That is a deliberate
exception, recorded here rather than silently: the alternative is threading two
request-scoped strings through every call site in the application, and the
Phase 3 rewrite that moves audit writes to the outbox is where they become
explicit arguments.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from flask import request

from model import AuditLog, db

__all__ = ["log_audit_event"]


def log_audit_event(
    action: str,
    actor_user_id: Optional[int],
    resource: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Append an ``AuditLog`` row to the current SQLAlchemy session.

    Does NOT commit -- the caller must ``db.session.commit()`` to persist.
    This function is intentionally low-level; the caller owns the transaction
    so that audit rows are committed atomically with the surrounding changes.

    Args:
        action:        Short verb describing the operation (e.g. ``"read"``,
                       ``"update"``, ``"email_send_failed"``).
        actor_user_id: ``User.id`` of the acting user, or None for anonymous
                       events.
        resource:      Resource type affected (e.g. ``"profile"``, ``"email"``).
        metadata:      Optional dict of additional context (serialized to JSON).
    """
    audit = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource=resource,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
        event_metadata=metadata or {},
    )
    db.session.add(audit)
