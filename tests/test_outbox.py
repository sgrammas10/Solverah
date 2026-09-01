"""The transactional outbox, tested against the table rather than through eager mode.

That distinction is the whole point of this file, so it is worth stating plainly.

Under ``APP_ENV=testing`` Celery runs eagerly: ``.delay()`` executes the task
inline, in the calling process, at the moment it is called.  That makes every
other email test in the suite pass -- the monkeypatched send function is reached,
in order, with the right arguments -- and it is **no evidence whatsoever** about
durability.  An inline task cannot demonstrate what happens when the worker is a
different machine that starts three seconds later, because there is no worker and
no later.

So nothing here asserts on eager execution.  Every test drives
``solverah.services.outbox`` directly and reads the ``outbox`` table back through
its own connection, which is what a real worker would see.  The four properties
below are the ones the design rests on:

1. **Atomic with the business write.** The row is added to the caller's session
   and never committed by the outbox. A rolled-back business write leaves no row;
   a committed one leaves exactly one.
2. **A failed publish loses nothing.** ``published_at`` stays NULL, ``attempts``
   goes up, and the next sweep delivers it.
3. **A retry never double-sends.** Publishing an already-published row sends
   nothing and says so. This matters because ``task_acks_late`` means a worker
   killed after sending gets the message again.
4. **A permanently undeliverable row parks rather than spinning.** Past
   ``MAX_ATTEMPTS`` the sweep stops picking it up, visibly, with the row intact.

Test 1 is the one to break if you want to check this file is doing its job: make
``outbox.enqueue`` commit on its own and
``test_a_rolled_back_business_write_leaves_no_outbox_row`` fails immediately.
"""

import pytest

TOPIC = "email.verification"
EMAIL = "outbox-user@example.test"


@pytest.fixture()
def ctx(client):
    """An application context with the schema built, and a clean session after."""
    from app import app

    with app.app_context():
        yield app
        from model import db

        db.session.rollback()


@pytest.fixture()
def sent(monkeypatch):
    """Capture every verification email the publisher would send.

    Patches the same attribute every other email test in the suite patches --
    ``solverah.infra.email.send_confirmation_email`` -- because the outbox
    handler resolves the function off the module at call time precisely so that
    those patches keep working. If this fixture ever stops intercepting, the
    suite has started trying to send real mail.
    """
    delivered = []
    monkeypatch.setattr(
        "solverah.infra.email.send_confirmation_email",
        lambda to, code: delivered.append((to, code)),
    )
    return delivered


def _payload(code="123456"):
    return {"to": EMAIL, "code": code}


# ── 1. Atomicity with the business write ────────────────────────────────────


def test_enqueue_does_not_commit(ctx, sent):
    """The property everything else rests on.

    ``entry_state`` reads through ``db.engine.connect()`` -- a *different*
    connection -- so an uncommitted row is invisible to it. Seeing None here is
    what proves the row is still inside the caller's transaction rather than
    already durable.
    """
    from solverah.services import outbox

    entry_id = outbox.enqueue(TOPIC, _payload())

    assert outbox.entry_state(entry_id) is None


def test_a_rolled_back_business_write_leaves_no_outbox_row(ctx, sent):
    """Half of the invariant: neither, or both. Never just the email.

    **Break `outbox.enqueue` to commit on its own and this test fails.** That is
    the check on the check -- an atomicity test that still passes when atomicity
    is gone is worse than no test.
    """
    from model import User, db
    from solverah.services import outbox

    db.session.add(User(email=EMAIL, password_hash="not-a-real-hash"))
    entry_id = outbox.enqueue(TOPIC, _payload())

    db.session.rollback()

    assert outbox.entry_state(entry_id) is None
    assert User.query.filter_by(email=EMAIL).first() is None


def test_a_committed_business_write_leaves_exactly_one_outbox_row(ctx, sent):
    """The other half: the account and the email it is owed land together."""
    from model import User, db
    from solverah.services import outbox

    db.session.add(User(email=EMAIL, password_hash="not-a-real-hash"))
    entry_id = outbox.enqueue(TOPIC, _payload())
    db.session.commit()

    state = outbox.entry_state(entry_id)
    assert state is not None
    assert state["published_at"] is None
    assert state["attempts"] == 0
    assert User.query.filter_by(email=EMAIL).first() is not None
    assert outbox.unpublished_count() == 1
    # Committing owes the email; it does not send it. Delivery is the worker's.
    assert sent == []


def test_registration_commits_the_account_and_the_email_together(client, monkeypatch):
    """The invariant at the level a user would experience it.

    Registration used to create the account, commit, and *then* call Resend. This
    walks the real endpoint and asserts the row exists -- so the obligation is
    durable whether or not the provider was reachable.
    """
    from app import app
    from model import User
    from solverah.services import outbox

    # Not a no-op: a provider that is down is the case being defended against.
    def _boom(*_args, **_kwargs):
        raise RuntimeError("resend is down")

    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _boom)

    resp = client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": "Strongpass1!", "name": "Outbox User",
              "role": "job-seeker", "terms_accepted": True},
    )

    assert resp.status_code == 201

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        assert user is not None
        assert outbox.unpublished_count() == 1


# ── 2. A failed publish is a retry, never a loss ────────────────────────────


def test_a_failed_publish_leaves_the_row_for_retry(ctx, monkeypatch):
    from solverah.services import outbox

    monkeypatch.setattr(
        "solverah.infra.email.send_confirmation_email",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("provider down")),
    )

    entry_id = outbox.enqueue(TOPIC, _payload())
    from model import db

    db.session.commit()

    assert outbox.publish(entry_id) == outbox.FAILED

    state = outbox.entry_state(entry_id)
    assert state["published_at"] is None, "a failed send must not mark it delivered"
    assert state["attempts"] == 1
    assert outbox.unpublished_count() == 1


def test_the_sweep_delivers_what_a_failed_publish_left(ctx, monkeypatch, sent):
    """End to end for the outage case: down, then up, and the email still lands."""
    from model import db
    from solverah.services import outbox

    monkeypatch.setattr(
        "solverah.infra.email.send_confirmation_email",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("provider down")),
    )
    entry_id = outbox.enqueue(TOPIC, _payload("424242"))
    db.session.commit()
    outbox.publish(entry_id)

    monkeypatch.setattr(
        "solverah.infra.email.send_confirmation_email",
        lambda to, code: sent.append((to, code)),
    )
    counts = outbox.drain()

    assert counts == {"selected": 1, outbox.PUBLISHED: 1}
    assert sent == [(EMAIL, "424242")]
    assert outbox.entry_state(entry_id)["published_at"] is not None


# ── 3. A retry never double-sends ───────────────────────────────────────────


def test_publishing_an_already_published_row_sends_nothing(ctx, sent):
    """``task_acks_late`` means a worker killed after sending gets the message
    again. The row's ``published_at`` is what stops that being a second email."""
    from model import db
    from solverah.services import outbox

    entry_id = outbox.enqueue(TOPIC, _payload())
    db.session.commit()

    assert outbox.publish(entry_id) == outbox.PUBLISHED
    assert len(sent) == 1

    assert outbox.publish(entry_id) == outbox.ALREADY_PUBLISHED
    assert len(sent) == 1, "a retry re-sent a delivered email"


def test_a_drain_after_a_successful_publish_finds_nothing(ctx, sent):
    from model import db
    from solverah.services import outbox

    entry_id = outbox.enqueue(TOPIC, _payload())
    db.session.commit()
    outbox.publish(entry_id)

    assert outbox.drain() == {"selected": 0}
    assert len(sent) == 1


# ── 4. An undeliverable row parks ───────────────────────────────────────────


def test_a_row_past_max_attempts_is_no_longer_swept(ctx, monkeypatch, sent):
    """A payload that can never be delivered must not consume every sweep.

    It is parked, not deleted and not marked published: ``published_at`` is still
    NULL and the row is still countable, so an operator can see it.
    """
    import sqlalchemy as sa

    from model import Outbox, db
    from solverah.services import outbox

    entry_id = outbox.enqueue(TOPIC, _payload())
    db.session.commit()

    with db.engine.begin() as connection:
        connection.execute(
            sa.update(Outbox.__table__)
            .where(Outbox.__table__.c.id == entry_id)
            .values(attempts=outbox.MAX_ATTEMPTS)
        )

    assert outbox.drain() == {"selected": 0}
    assert sent == []
    assert outbox.entry_state(entry_id)["published_at"] is None
    assert outbox.unpublished_count(include_parked=True) == 1
    assert outbox.unpublished_count(include_parked=False) == 0


# ── Topics ──────────────────────────────────────────────────────────────────


def test_an_unknown_topic_is_refused_at_the_write(ctx):
    """Fails where the mistake is, not three hours later in a worker.

    A row with a topic no publisher handles can never be delivered; refusing it
    here means a typo is a traceback in the request that made it rather than a
    parked row somebody finds in a sweep's logs.
    """
    from solverah.services import outbox

    with pytest.raises(ValueError):
        outbox.enqueue("email.does_not_exist", {})


def test_every_topic_constant_has_a_handler():
    """The registry and the constants cannot drift apart."""
    from solverah.services import outbox

    constants = {
        value
        for name, value in vars(outbox).items()
        if name.startswith("TOPIC_") and isinstance(value, str)
    }

    assert constants == set(outbox.TOPICS)


# ── Retention ───────────────────────────────────────────────────────────────


def test_purge_removes_delivered_rows_and_keeps_owed_ones(ctx, monkeypatch, sent):
    """The table holds addresses and one-time codes, so delivered rows expire.

    An *undelivered* row is never purged, including a parked one: that is
    somebody's email still owed, and deleting it would be the loss the whole
    design exists to prevent.
    """
    import sqlalchemy as sa

    from model import Outbox, db
    from solverah.services import outbox

    delivered_id = outbox.enqueue(TOPIC, _payload("111111"))
    owed_id = outbox.enqueue(TOPIC, _payload("222222"))
    db.session.commit()
    outbox.publish(delivered_id)

    # Backdate the delivered row past the retention window.
    with db.engine.begin() as connection:
        connection.execute(
            sa.update(Outbox.__table__)
            .where(Outbox.__table__.c.id == delivered_id)
            .values(published_at=sa.text("now() - interval '48 hours'"))
        )

    assert outbox.purge_published(older_than_hours=24) == 1
    assert outbox.entry_state(delivered_id) is None
    assert outbox.entry_state(owed_id) is not None
