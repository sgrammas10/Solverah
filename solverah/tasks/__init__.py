"""Celery task definitions -- thin wrappers, one per unit of queued work.

A task in here does three things and no more: name itself, choose a queue, and
call one service function.  Everything a task *does* lives in ``services/``,
which is what keeps queued work testable by calling the service directly and
what stops the queue becoming a second place business rules are written.

Importing this package registers every task on ``solverah.infra.queue.celery_app``.
``init_celery()`` performs that import at the end of ``create_app()`` rather than
at module scope, because these modules import services, services import
``solverah.infra.queue``, and registering at import time would close the cycle.

Task names are explicit strings rather than derived from the module path.  The
name is what travels on the wire: a message written by one deploy is executed by
the next, so a task whose name follows its module would break every in-flight
message the day somebody moves the file.
"""

from __future__ import annotations

from solverah.tasks import (  # noqa: F401  -- imported for registration
    audit_tasks,
    maintenance_tasks,
    outbox_tasks,
    resume_tasks,
    scoring_tasks,
)

__all__ = [
    "audit_tasks",
    "maintenance_tasks",
    "outbox_tasks",
    "resume_tasks",
    "scoring_tasks",
]
