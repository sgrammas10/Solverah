"""The Celery application, its queues, and the seam every enqueue goes through.

Phase 3, item 1.  Before this there was no job queue anywhere in the system
(P0-6): OpenAI, Groq, O*NET, Resend, and R2 calls all ran inline, and
``gunicorn.conf.py`` carries a 120-second timeout to accommodate them.  With sync
workers one slow provider occupies a whole worker for up to two minutes, so a
provider slowdown becomes a full outage.

**Five queues, and they are separate for isolation rather than for tidiness.**
An LLM call that takes 40 seconds and an email that takes 200ms do not belong in
one FIFO: a burst of the first starves the second, and the user waiting on a
verification code pays for somebody else's narrative generation.  Each queue can
be given its own worker count and its own concurrency.

    default      short work with no better home
    llm          provider-backed generation -- slow, bursty, retryable
    email        outbox publication; latency-sensitive, tiny payloads
    scoring      path scoring, match precomputation -- CPU-bound
    maintenance  sweeps and backfills; may be starved without anyone noticing

**Eager mode is not a test convenience, it is the no-broker degradation.**
``task_always_eager`` makes ``.delay()`` run the task inline in the calling
process.  Two environments have no broker and both need to keep working: CI,
which sets five environment variables and runs no Redis service container, and a
developer running the API with ``REDIS_URL`` unset.  Without eager, every
registration in both would raise on connect.  ``solverah/config.py`` derives it
and warns if it is ever true in production, where it would silently put the work
this phase moved off the request path straight back onto it.

What eager mode is *not* is evidence that the durable path works.  A task that
runs inline runs in the same process, in the same instant, with the same
exception behaviour -- so it proves ordering and arguments and nothing about
what happens when the worker is a different machine that starts three seconds
later.  ``tests/test_outbox.py`` tests the outbox against the table directly for
exactly that reason.

**Something must run the beat schedule.**  ``BEAT_SCHEDULE`` below drives the
sweeps that turn every best-effort enqueue in this system into an eventual
guarantee.  A deployment with workers and no beat process still delivers most
email -- and loses exactly the ones that failed the first time, which are the
ones the outbox exists for.

**Tasks get a Flask application context and their own database transaction.**
The context is pushed by :class:`FlaskTask` so a worker process can reach
``db.engine`` and the configuration.  The transaction is the task's own concern
and every task in ``solverah/tasks/`` opens one with ``db.engine.begin()``
rather than using ``db.session``.  That is load-bearing under eager mode:
``db.session`` is scoped to the thread, so a task committing it inside a request
would commit the *request's* pending work as well -- which would quietly undo
the "no writes on the read path" property this phase is here to establish.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from celery import Celery, Task
from flask import has_app_context
from kombu import Queue

from solverah.config import Settings

__all__ = [
    "QUEUES",
    "QUEUE_DEFAULT",
    "QUEUE_EMAIL",
    "QUEUE_LLM",
    "QUEUE_MAINTENANCE",
    "QUEUE_SCORING",
    "celery_app",
    "enqueue",
    "init_celery",
    "is_eager",
]

logger = logging.getLogger("solverah.queue")

QUEUE_DEFAULT = "default"
QUEUE_LLM = "llm"
QUEUE_EMAIL = "email"
QUEUE_SCORING = "scoring"
QUEUE_MAINTENANCE = "maintenance"

#: Declared as data so a worker command line, the compose file, and the routing
#: table below cannot drift from one another.
QUEUES = (QUEUE_DEFAULT, QUEUE_LLM, QUEUE_EMAIL, QUEUE_SCORING, QUEUE_MAINTENANCE)


#: Periodic work, and the reason each entry exists.
#:
#: **These are not optional.**  Three properties this phase claims are only true
#: if something runs them: "a failed publish leaves the row for retry" needs
#: ``outbox.drain``; "a lost enqueue costs latency, not the work" needs
#: ``resume.sweep_jobs``; and the outbox holding addresses and one-time codes is
#: bounded only by ``outbox.purge_published``.  A deployment with workers but no
#: beat has the tables and none of the guarantees.
#:
#: Intervals are chosen against what each one is recovering from.  The outbox
#: drain is frequent because its subject is a user waiting on a sign-in code and
#: the normal case is that it selects nothing.  The others recover from rarer
#: events and can afford to be quiet.
BEAT_SCHEDULE = {
    "outbox-drain": {
        "task": "solverah.outbox.drain",
        "schedule": timedelta(seconds=30),
    },
    "outbox-purge-published": {
        "task": "solverah.outbox.purge_published",
        "schedule": timedelta(hours=1),
    },
    "resume-jobs-sweep": {
        "task": "solverah.resume.sweep_jobs",
        "schedule": timedelta(minutes=5),
    },
}


class FlaskTask(Task):
    """Run every task body inside a Flask application context.

    A worker process has no request and no ambient app, but tasks reach
    ``db.engine`` and ``current_app.config`` through the services they call.
    Pushing the context here rather than in each task means a new task cannot
    forget to.

    Under eager execution a context is usually already pushed -- the caller is a
    request -- and pushing a second one would give the task a different
    ``db.session`` from the one the request is using.  So the existing context is
    reused when there is one.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        flask_app = self.app.conf.get("solverah_flask_app")
        if flask_app is None or has_app_context():
            return self.run(*args, **kwargs)
        with flask_app.app_context():
            return self.run(*args, **kwargs)


#: The application.  Constructed unbound at import, for the same reason the Flask
#: extensions in ``solverah/extensions.py`` are: a task module has to be able to
#: decorate with ``@celery_app.task`` at import time, before any configuration
#: exists.  ``init_celery()`` decides what broker it talks to.
celery_app = Celery("solverah", task_cls=FlaskTask)

# Broker-independent defaults.  Everything here is true whether or not a broker
# was ever configured, so it is set at import rather than in init_celery().
celery_app.conf.update(
    task_default_queue=QUEUE_DEFAULT,
    task_queues=tuple(Queue(name) for name in QUEUES),
    # JSON only.  Celery's historical default was pickle, which makes any client
    # able to reach the broker able to execute arbitrary code in a worker.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Acknowledge after the task returns, not when it is delivered.  A worker
    # killed mid-task therefore returns the message to the queue instead of
    # dropping it -- which is what makes "the worker died" a redelivery rather
    # than a lost email.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # An eagerly-run task that raises must not raise into its caller: in
    # production the caller is long gone, and a test that saw the exception would
    # be asserting behaviour production does not have.
    task_eager_propagates=False,
    broker_connection_retry_on_startup=True,
    beat_schedule=BEAT_SCHEDULE,
)


def init_celery(app, settings: Optional[Settings] = None) -> Celery:
    """Point :data:`celery_app` at this deployment's broker and Flask app.

    Args:
        app: The Flask application tasks should run inside.
        settings: Validated settings.  When None -- the configuration failed
            validation -- the queue degrades to eager rather than blocking boot,
            which is the same call ``create_app`` makes for everything else.

    Returns:
        The configured :data:`celery_app`, for a worker entrypoint to hand to
        the ``celery`` command line.
    """
    broker = settings.celery_broker_url if settings else None
    eager = settings.celery_task_always_eager if settings else True

    celery_app.conf.update(
        broker_url=broker,
        result_backend=settings.celery_result_backend if settings else None,
        task_always_eager=eager,
        solverah_flask_app=app,
    )

    _quieten_celery_codegen()

    # Importing the task modules is what registers them.  Deferred to here rather
    # than done at module scope because they import services, which import this
    # module -- registering at import time would be a cycle.
    from solverah import tasks  # noqa: F401  -- imported for its side effect

    app.extensions["celery"] = celery_app
    logger.info(
        "celery_configured",
        extra={
            "event": "celery_configured",
            "broker": "redis" if broker else "none",
            "eager": eager,
            "queues": list(QUEUES),
        },
    )
    return celery_app


def _quieten_celery_codegen() -> None:
    """Stop Celery logging the source of every function it generates.

    ``celery.utils.functional.head_from_fun`` builds a signature-matching wrapper
    for each task and logs the generated source at DEBUG.  ``LOG_LEVEL`` defaults
    to DEBUG outside production, so without this a developer's console gets forty
    stanzas of generated Python at every boot and the request log is unreadable.
    Scoped to that one logger rather than to ``celery``, so a worker's own DEBUG
    output -- which is the output somebody would actually be asking for -- is
    untouched.
    """
    logging.getLogger("celery.utils.functional").setLevel(logging.INFO)


def is_eager() -> bool:
    """Whether tasks currently run inline in the calling process."""
    return bool(celery_app.conf.get("task_always_eager"))


def enqueue(task: Task, *args: Any, **kwargs: Any) -> Optional[str]:
    """Hand *task* to the broker, and never fail the caller if that does not work.

    Every caller of this is a request that has already committed its business
    write.  Raising here would turn a successful registration into a 500 over a
    queue that is momentarily unreachable -- the precise failure mode the outbox
    exists to end, reintroduced one layer up.

    A dropped enqueue is therefore a *delay*, not a loss, and only because the
    row is already in the database: ``outbox.drain`` sweeps anything unpublished
    and the resume-job sweep does the same for parse jobs.  Nothing may be
    enqueued through here that has no such sweep behind it.

    Returns:
        The task id, or None if the broker could not be reached.
    """
    try:
        return task.delay(*args, **kwargs).id
    except Exception as exc:  # noqa: BLE001 -- see docstring; a sweep covers it
        logger.error(
            "task_enqueue_failed",
            extra={
                "event": "task_enqueue_failed",
                "task": task.name,
                "error": str(exc),
            },
        )
        return None
