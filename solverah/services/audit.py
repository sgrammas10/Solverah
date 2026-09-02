"""Audit event recording, on and off the request path.

Formerly ``app.py:log_audit_event``.  It is the single seam for audit writes, so
a test substitutes ``solverah.services.audit.log_audit_event`` once regardless of
which service is doing the writing.

There are now two ways in, and picking the wrong one is the mistake this
docstring exists to prevent.

**:func:`log_audit_event` -- for a request that is already writing.**  Appends the
row to the caller's session and does not commit.  The audit row and the change it
describes land in one transaction, which is the property that makes the trail
worth having: there is no state in which the profile was updated but the record
of who updated it was lost.  Every ``POST``/``PATCH``/``PUT`` path uses this and
none of them changed in Phase 3.

**:func:`record_read_event` -- for a request that must not write.**  Hands the
event to a worker and returns.  The read issues no INSERT, takes no write lock,
and commits nothing.

That second one is P0-3, the half of it that lives on the server.
``GET /api/profile`` wrote an ``AuditLog`` row and called ``db.session.commit()``
on every read; session restore fired it on every page load, so the
highest-volume table in the system was written synchronously on the hottest
endpoint, on a request that ought to be servable from a replica.  Phase 1b took
session restore off that endpoint; Phase 3 takes the write off the read.

**Why a task rather than a Redis stream.**  Part 4.7 offers either.  A stream is
the right answer at the volume the endpoint had *before* Phase 1b moved session
restore onto ``GET /auth/session``, which writes nothing; what remains is a
deliberate read of a personal-data document, at a rate measured in reads per
user per session.  One message each is not a volume problem, and it avoids a
second delivery mechanism -- with its own drain loop, its own failure modes, and
its own way of losing events -- for a table that already has one.

**Why the IP and user agent are now arguments.**  They are request-scoped, and a
worker has no request.  Reading ``flask.request`` inside the write is what made
this module the one documented exception to "services must be callable from a
worker" (``tests/test_layering.py``).  :func:`log_audit_event` still reads them
from the ambient request when they are not supplied, so its thirteen call sites
are untouched; the read path captures them in the request and passes them
explicitly, which is what lets the row be written somewhere else entirely.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import sqlalchemy as sa
from flask import has_request_context, request

from model import AuditLog, db

__all__ = [
    "log_audit_event",
    "record_read_event",
    "request_fingerprint",
    "write_event",
]

logger = logging.getLogger("solverah.audit")

#: Column widths from ``model.AuditLog``.  Truncating here rather than letting
#: Postgres raise means a hostile 8KB User-Agent header degrades the audit row
#: instead of failing the request that carries it.
_IP_MAX = 64
_USER_AGENT_MAX = 300


def request_fingerprint() -> Dict[str, Optional[str]]:
    """The two request-scoped strings an audit row records.

    Returns them as data so they can be captured in a handler and handed to a
    worker.  Empty outside a request context, which is the worker's own case:
    a task that re-derived them would be recording its own address.
    """
    if not has_request_context():
        return {"ip": None, "user_agent": None}
    return {
        "ip": (request.remote_addr or "")[:_IP_MAX] or None,
        "user_agent": (request.headers.get("User-Agent", "") or "")[:_USER_AGENT_MAX],
    }


def log_audit_event(
    action: str,
    actor_user_id: Optional[int],
    resource: str,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Append an ``AuditLog`` row to the current SQLAlchemy session.

    Does NOT commit -- the caller must ``db.session.commit()`` to persist.
    This function is intentionally low-level; the caller owns the transaction
    so that audit rows are committed atomically with the surrounding changes.

    **Do not call this from a ``GET`` handler.**  Use :func:`record_read_event`.
    A read that appends here either commits (P0-3, the defect) or leaves the row
    to be rolled back with the session (worse -- the write looks recorded and is
    not).

    Args:
        action:        Short verb describing the operation (e.g. ``"read"``,
                       ``"update"``, ``"email_send_failed"``).
        actor_user_id: ``User.id`` of the acting user, or None for anonymous
                       events.
        resource:      Resource type affected (e.g. ``"profile"``, ``"email"``).
        metadata:      Optional dict of additional context (serialized to JSON).
        ip:            Client address.  Read from the ambient request when
                       omitted, which is what keeps the existing call sites
                       unchanged.
        user_agent:    Client user agent, same rule.
    """
    if ip is None and user_agent is None:
        fingerprint = request_fingerprint()
        ip = fingerprint["ip"]
        user_agent = fingerprint["user_agent"]

    audit = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource=resource,
        ip_address=ip,
        user_agent=user_agent,
        event_metadata=metadata or {},
    )
    db.session.add(audit)


def write_event(
    action: str,
    actor_user_id: Optional[int],
    resource: str,
    metadata: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Insert one audit row in a transaction of its own. The worker's entry point.

    Core INSERT on its own connection rather than ``db.session``, and that is not
    a style preference.  Under eager execution the "worker" is the request
    thread and ``db.session`` is scoped to it, so committing that session here
    would also commit whatever the request had pending -- turning a read that is
    supposed to write nothing into a read that commits, which is the exact defect
    being removed.  ``db.engine.begin()`` is the same code in both modes.

    Requires a Flask application context for ``db.engine``; the task base class
    supplies one.
    """
    with db.engine.begin() as connection:
        connection.execute(
            sa.insert(AuditLog.__table__).values(
                actor_user_id=actor_user_id,
                action=action,
                resource=resource,
                ip_address=ip,
                user_agent=user_agent,
                metadata=metadata or {},
            )
        )


def record_read_event(
    action: str,
    actor_user_id: Optional[int],
    resource: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Record an audit event without writing anything in this request.

    Call from a ``GET`` handler's service.  Captures the request fingerprint
    here -- the only place it exists -- and hands the rest to a worker.

    Never raises.  An audit trail is worth having and is not worth failing a read
    over: if the queue cannot be reached the event is logged at ERROR and
    dropped, which is a gap in the trail that shows up in the logs rather than a
    500 the user sees.  That is a deliberately different trade from the outbox,
    where the row is durable before anything is enqueued and a lost enqueue costs
    only latency.
    """
    fingerprint = request_fingerprint()
    try:
        from solverah.infra.queue import enqueue
        from solverah.tasks.audit_tasks import record_audit_event

        enqueue(
            record_audit_event,
            action=action,
            actor_user_id=actor_user_id,
            resource=resource,
            metadata=metadata or {},
            ip=fingerprint["ip"],
            user_agent=fingerprint["user_agent"],
        )
    except Exception as exc:  # noqa: BLE001 -- see docstring
        logger.error(
            "audit_read_event_dropped",
            extra={
                "event": "audit_read_event_dropped",
                "action": action,
                "resource": resource,
                "error": str(exc),
            },
        )
