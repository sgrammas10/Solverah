"""The Celery application: its queues, its serializer, and its no-broker behaviour.

Cheap, fast checks over configuration that is easy to get wrong and impossible to
notice being wrong until production.

The one that matters most to this suite is
:func:`test_enqueue_never_raises_without_a_broker`. CI runs no Redis service
container, so every path that queues work reaches ``queue.enqueue`` with nothing
to connect to. If that raised, the failure would not look like a queue problem --
it would look like registration being broken.
"""

import pytest


@pytest.fixture()
def celery(client):
    """The configured application. Depends on ``client`` so ``create_app`` has run."""
    from solverah.infra.queue import celery_app

    return celery_app


def test_the_five_queues_are_declared(celery):
    """Named in docs/ARCHITECTURE.md Phase 3, and split for isolation.

    An LLM call that takes 40 seconds and an email that takes 200ms in one FIFO
    means a burst of the first starves the second, and the user waiting on a
    verification code pays for somebody else's narrative generation.
    """
    from solverah.infra.queue import QUEUES

    assert QUEUES == ("default", "llm", "email", "scoring", "maintenance")
    assert {q.name for q in celery.conf.task_queues} == set(QUEUES)
    assert celery.conf.task_default_queue == "default"


def test_every_task_is_routed_to_a_declared_queue(celery):
    """A task on an undeclared queue is a task no worker is subscribed to.

    It would be accepted by the broker and then sit there -- no error anywhere,
    just work that silently never happens.
    """
    from solverah.infra.queue import QUEUES

    ours = {
        name: task
        for name, task in celery.tasks.items()
        if name.startswith("solverah.")
    }

    assert ours, "no tasks registered; init_celery did not import solverah.tasks"
    for name, task in ours.items():
        assert task.queue in QUEUES, "%s is routed to %r" % (name, task.queue)


def test_the_email_and_maintenance_split_is_real(celery):
    """The two queues whose separation has a user-visible consequence.

    An outbox publish is what a user is waiting on; an audit row is not. Put them
    on one queue and a burst of profile reads delays somebody's sign-in code.
    """
    assert celery.tasks["solverah.outbox.publish_entry"].queue == "email"
    assert celery.tasks["solverah.audit.record_event"].queue == "maintenance"
    assert celery.tasks["solverah.resume.parse_job"].queue == "default"


def test_only_json_is_accepted(celery):
    """Celery's historical default was pickle.

    Anything that can reach the broker can then execute arbitrary code in a
    worker, which turns a Redis with a weak network boundary into remote code
    execution.
    """
    assert celery.conf.task_serializer == "json"
    assert celery.conf.accept_content == ["json"]


def test_tasks_are_acknowledged_late(celery):
    """A worker killed mid-task must redeliver rather than drop.

    This is what makes "the worker died" a retry, and it is why the outbox has to
    be safe against being published twice -- see tests/test_outbox.py.
    """
    assert celery.conf.task_acks_late is True


def test_testing_runs_eagerly_and_says_so(celery):
    """CI has no broker. Eager is how the suite reaches queued code at all.

    Asserted rather than assumed because the failure mode if it flipped is a
    connection timeout in every test that registers a user, reported as a
    registration bug.
    """
    assert celery.conf.task_always_eager is True


def test_an_eagerly_run_task_does_not_raise_into_its_caller(celery):
    """In production the caller is long gone by the time a task fails.

    A test that saw the exception would be asserting behaviour production does
    not have -- and a handler would be shaped around a 500 that can never occur.
    """
    assert celery.conf.task_eager_propagates is False


def test_every_scheduled_task_exists(celery):
    """A beat entry naming a task nobody registered fails only at fire time.

    And it fails in the beat process's log, hours after the deploy that broke it,
    which is not where anyone is looking. These three schedules are what turn
    every best-effort enqueue in the system into an eventual guarantee -- see
    solverah/infra/queue.py -- so a typo here silently removes a guarantee.
    """
    from solverah.infra.queue import BEAT_SCHEDULE

    for name, entry in BEAT_SCHEDULE.items():
        assert entry["task"] in celery.tasks, "%s schedules %r, which does not exist" % (
            name,
            entry["task"],
        )


def test_the_outbox_drain_is_scheduled(celery):
    """Named on its own because it is the one with a user waiting behind it.

    "A failed publish leaves the row for retry" is a claim about this schedule.
    Without it the row is left, and nothing retries.
    """
    from solverah.infra.queue import BEAT_SCHEDULE

    scheduled = {entry["task"] for entry in BEAT_SCHEDULE.values()}

    assert "solverah.outbox.drain" in scheduled
    assert "solverah.resume.sweep_jobs" in scheduled


def test_enqueue_never_raises_without_a_broker(client, monkeypatch):
    """The property CI depends on, checked against a *failing* enqueue.

    Eager mode means ``.delay()`` normally succeeds here, which would make this
    test pass without exercising anything. So the failure is forced.
    """
    from solverah.infra.queue import enqueue
    from solverah.tasks.outbox_tasks import publish_entry

    def _unreachable(*_args, **_kwargs):
        raise OSError("Error 111 connecting to localhost:6379. Connection refused.")

    monkeypatch.setattr(publish_entry, "delay", _unreachable)

    assert enqueue(publish_entry, 1) is None


def test_a_dropped_enqueue_leaves_the_row_for_the_sweep(client, monkeypatch):
    """Why swallowing it is allowed: the work is already durable.

    ``queue.enqueue`` may only be used for work whose record is committed before
    the enqueue. Here the outbox row survives a broker outage and ``drain``
    delivers it -- so a lost message costs latency, never the email.
    """
    from app import app
    from solverah.infra.queue import celery_app
    from solverah.services import outbox

    delivered = []
    monkeypatch.setattr(
        "solverah.infra.email.send_confirmation_email",
        lambda to, code: delivered.append((to, code)),
    )
    # Nothing reaches the broker at all, however the enqueue is attempted.
    monkeypatch.setitem(celery_app.conf, "task_always_eager", False)
    monkeypatch.setattr(
        "solverah.infra.queue.enqueue", lambda *_a, **_k: None, raising=True
    )

    with app.app_context():
        from model import db

        entry_id = outbox.enqueue(
            outbox.TOPIC_EMAIL_VERIFICATION, {"to": "x@example.test", "code": "1"}
        )
        db.session.commit()
        outbox.publish_soon(entry_id)

        assert delivered == [], "publish_soon reached the provider with no broker"
        assert outbox.unpublished_count() == 1

        outbox.drain()

    assert delivered == [("x@example.test", "1")]
