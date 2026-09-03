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


# ── Backoff: retries respect the row's age ──────────────────────────────────


def test_a_retried_row_waits_out_its_backoff_window(ctx, sent):
    """A row with failed attempts behind it is not retried by every sweep.

    ``RETRY_MIN_AGE`` was added for the cron cadence: under the old flat design
    8 attempts burned in ~4 minutes of provider outage. Here a row with two
    attempts must be at least 15 minutes old before try 3 -- a fresh one is
    skipped, and the same row backdated past the threshold is picked up.
    """
    import sqlalchemy as sa

    from model import Outbox, db
    from solverah.services import outbox

    entry_id = outbox.enqueue(TOPIC, _payload("515151"))
    db.session.commit()

    with db.engine.begin() as connection:
        connection.execute(
            sa.update(Outbox.__table__)
            .where(Outbox.__table__.c.id == entry_id)
            .values(attempts=2)
        )

    assert outbox.drain() == {"selected": 0}
    assert sent == []

    # Age the row past the attempts=2 threshold (15 minutes) and sweep again.
    with db.engine.begin() as connection:
        connection.execute(
            sa.update(Outbox.__table__)
            .where(Outbox.__table__.c.id == entry_id)
            .values(created_at=sa.text("now() - interval '16 minutes'"))
        )

    assert outbox.drain() == {"selected": 1, outbox.PUBLISHED: 1}
    assert sent == [(EMAIL, "515151")]


def test_a_first_failure_is_retried_by_the_very_next_sweep(ctx, monkeypatch, sent):
    """The Scenario A case that started all this: one failed inline send.

    ``attempts == 1`` must be eligible immediately -- the user is waiting on a
    sign-in code, and the next cron pass (minutes away) is the retry. Only the
    later attempts back off.
    """
    from model import db
    from solverah.services import outbox

    entry_id = outbox.enqueue(TOPIC, _payload("616161"))
    db.session.commit()

    monkeypatch.setattr(
        "solverah.infra.email.send_confirmation_email",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("provider blip")),
    )
    assert outbox.publish(entry_id) == outbox.FAILED

    monkeypatch.setattr(
        "solverah.infra.email.send_confirmation_email",
        lambda to, code: sent.append((to, code)),
    )
    assert outbox.drain() == {"selected": 1, outbox.PUBLISHED: 1}
    assert sent == [(EMAIL, "616161")]


def test_the_backoff_schedule_matches_max_attempts():
    """One entry per allowed try, or the CASE in ``drain`` silently misroutes."""
    from solverah.services import outbox

    assert len(outbox.RETRY_MIN_AGE) == outbox.MAX_ATTEMPTS


# ── Concurrency: two sweeps, one row, one email ─────────────────────────────


def test_two_concurrent_sweeps_cannot_both_claim_one_row(ctx, monkeypatch):
    """The double-send trap, exercised with a real second connection.

    Sweep A claims the row and is held *inside the provider call* -- where
    ``publish`` holds the row's ``FOR UPDATE`` lock. Sweep B runs a full drain
    while A is in flight: its ``SKIP LOCKED`` select must skip the row, select
    nothing, and send nothing. Exactly one email leaves.

    (The other interleaving -- both sweeps collecting the id before either
    publishes -- is serialised by the same row lock inside ``publish`` and is
    covered by ``test_publishing_an_already_published_row_sends_nothing``.)
    """
    import threading

    from app import app
    from model import db
    from solverah.services import outbox

    entry_id = outbox.enqueue(TOPIC, _payload("717171"))
    db.session.commit()

    in_send = threading.Event()
    release = threading.Event()
    sends = []

    def held_send(to, code):
        sends.append((to, code))
        in_send.set()
        if not release.wait(timeout=15):
            raise RuntimeError("test never released the provider call")

    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", held_send)

    results = {}

    def sweep_a():
        with app.app_context():
            results["a"] = outbox.drain()

    thread = threading.Thread(target=sweep_a, daemon=True)
    thread.start()
    assert in_send.wait(timeout=15), "sweep A never reached the provider call"

    # A holds the row lock across its send; B's whole pass runs meanwhile.
    results["b"] = outbox.drain()

    release.set()
    thread.join(timeout=15)
    assert not thread.is_alive(), "sweep A never finished"

    assert results["b"] == {"selected": 0}, "sweep B claimed a row sweep A held"
    assert results["a"] == {"selected": 1, outbox.PUBLISHED: 1}
    assert sends == [(EMAIL, "717171")], "one row produced more than one send"
    assert outbox.entry_state(entry_id)["published_at"] is not None


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


def test_purge_spares_pending_parked_and_recently_delivered_rows(ctx, sent):
    """Every class of row the purge must NOT delete, in one pass.

    Deletion requires BOTH delivered AND past the window. A pending row (owed),
    a parked row (owed, exhausted -- an operator's to-do, and old enough that
    age alone would qualify it), and a freshly delivered row (inside the window)
    must all survive a purge, whatever their age.
    """
    import sqlalchemy as sa

    from model import Outbox, db
    from solverah.services import outbox

    pending_id = outbox.enqueue(TOPIC, _payload("111111"))
    parked_id = outbox.enqueue(TOPIC, _payload("222222"))
    fresh_id = outbox.enqueue(TOPIC, _payload("333333"))
    db.session.commit()
    outbox.publish(fresh_id)  # delivered just now: inside any sane window

    with db.engine.begin() as connection:
        # Parked, and old enough that only the published_at IS NOT NULL guard
        # (never age) can be what protects it.
        connection.execute(
            sa.update(Outbox.__table__)
            .where(Outbox.__table__.c.id == parked_id)
            .values(
                attempts=outbox.MAX_ATTEMPTS,
                created_at=sa.text("now() - interval '30 days'"),
            )
        )
        connection.execute(
            sa.update(Outbox.__table__)
            .where(Outbox.__table__.c.id == pending_id)
            .values(created_at=sa.text("now() - interval '30 days'"))
        )

    assert outbox.purge_published(older_than_hours=24) == 0
    assert outbox.entry_state(pending_id) is not None
    assert outbox.entry_state(parked_id) is not None
    assert outbox.entry_state(fresh_id) is not None


# ── Readiness reporting ─────────────────────────────────────────────────────


def test_readyz_stays_200_with_parked_rows_and_reports_the_depth(client, ctx, sent):
    """Depth is information, never readiness.

    A parked row is somebody's email permanently undelivered -- worth surfacing
    -- but the process can still serve traffic, and a /readyz that 503'd on it
    would pull every instance out of the load balancer at once over a backlog.
    So: the counts must appear in the payload, and the status code must stay on
    the database check alone.
    """
    import sqlalchemy as sa

    from model import Outbox, db
    from solverah.services import outbox

    outbox.enqueue(TOPIC, _payload("111111"))                # pending
    parked_id = outbox.enqueue(TOPIC, _payload("222222"))    # parked below
    delivered_id = outbox.enqueue(TOPIC, _payload("333333")) # published: not counted
    db.session.commit()
    outbox.publish(delivered_id)

    with db.engine.begin() as connection:
        connection.execute(
            sa.update(Outbox.__table__)
            .where(Outbox.__table__.c.id == parked_id)
            .values(attempts=outbox.MAX_ATTEMPTS)
        )

    res = client.get("/readyz")
    body = res.get_json()

    assert res.status_code == 200
    assert body["status"] == "ready"
    assert body["outbox"] == {"pending": 1, "parked": 1}
