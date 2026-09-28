"""DB ledger, Package B: users, auth, sessions, the outbox and resume jobs.

Each regression test below pins one ledger finding and was run against the code
before its fix to watch it fail:

* ``find_by_email`` could not use ``uq_users_email``.  The index is partial on
  ``deleted_at IS NULL`` and the lookup carried no such predicate, so every
  signed-in request -- every route resolves its user through this function --
  scanned ``users``.  A ten-row test table picks a sequential scan whatever the
  indexes are, so the plan is read with ``enable_seqscan = off``: the question
  is whether the index *can* serve the query, not whether the planner prefers it
  at this size.
* Login committed when there was nothing to write.  A commit expires every
  loaded row, so the next read of ``user`` was a SELECT of the row just read.
* The failed-login counter was a read-modify-write in Python.  Two overlapping
  failures could not both land: ``users`` carries ``version_id_col``, so the
  second raised ``StaleDataError`` -- a 500 on the login path, and one lost
  count.
* ``refresh_tokens.issue`` and ``rotate`` re-read rows their own commit had just
  expired, and ``rotate`` set ``successor_id`` in a statement of its own.
* ``outbox.depth`` sent two counts, on two connections.
* ``resume_jobs.create`` reloaded the job it had just inserted.

Some tests are characterisation rather than regression, and pass on both sides
of the change by design: the lockout rules, the ``version`` contract a SQL-side
UPDATE must keep, and the way a tombstoned account looks up and signs in.
"""

import contextlib
import datetime
import re

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from tests.query_count import count_queries

EMAIL = "dbopt-auth@example.test"
PASSWORD = "Strongpass1!"
WRONG = "not-the-password-1!"


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def _no_outbound_email(monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.infra.email.send_password_reset_email", _noop)


@pytest.fixture()
def ctx(client):
    """An application context over the ``client`` fixture's schema.

    Left with no open transaction: ``client``'s teardown drops every table, and
    a transaction still open here would hold the locks that DROP waits on.
    """
    from app import app
    from model import db

    with app.app_context():
        yield app
        db.session.rollback()
        db.session.remove()


# -- helpers ------------------------------------------------------------------


def _register_confirmed(client, email=EMAIL):
    """An account that can sign in: registered through the API, confirmed directly."""
    from app import app
    from model import User, db

    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Ledger B",
              "terms_accepted": True},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    with app.app_context():
        user = User.query.filter_by(email=email).one()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        return user.id


def _login(client, password=PASSWORD, email=EMAIL):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _user_row(user_id):
    """The ``users`` row as the database holds it, read on a connection of its own."""
    from model import User, db

    users = User.__table__
    with db.engine.connect() as connection:
        return connection.execute(sa.select(users).where(users.c.id == user_id)).one()


def _reads_of(statements, table):
    """The SELECTs in *statements* whose FROM clause starts at *table*."""
    source = re.compile(r"\bFROM\s+%s\b" % re.escape(table), re.IGNORECASE)
    return [
        s for s in statements
        if s.lstrip().upper().startswith("SELECT") and source.search(s)
    ]


def _updates_of(statements, table):
    target = re.compile(r"\s*UPDATE\s+%s\b" % re.escape(table), re.IGNORECASE)
    return [s for s in statements if target.match(s)]


@contextlib.contextmanager
def _capture_sql():
    """Every ``(statement, parameters)`` pair sent inside the block."""
    from model import db

    sent = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        sent.append((statement, parameters))

    event.listen(db.engine, "before_cursor_execute", _record)
    try:
        yield sent
    finally:
        event.remove(db.engine, "before_cursor_execute", _record)


@contextlib.contextmanager
def _count_commits():
    """Every COMMIT a connection issues inside the block."""
    from model import db

    commits = []

    def _record(conn):
        commits.append(conn)

    event.listen(db.engine, "commit", _record)
    try:
        yield commits
    finally:
        event.remove(db.engine, "commit", _record)


def _fill_users(count=2000):
    """Give ``users`` enough rows, and statistics, for index choice to be real.

    Seq scans are priced out below, but on a near-empty table that still leaves
    a tie: ``ix_users_status`` is partial on the same ``deleted_at IS NULL``, and
    a full scan of it costs what a lookup in ``uq_users_email`` costs when there
    is one page to read.  At a few thousand rows the lookup wins on its merits.
    """
    from model import User, db

    db.session.execute(
        sa.insert(User.__table__),
        [
            {"email": "filler-%d@example.test" % n, "password_hash": "not-a-real-hash"}
            for n in range(count)
        ],
    )
    db.session.commit()
    db.session.execute(sa.text("ANALYZE users"))
    db.session.commit()


def _plan_with_seqscan_off(statement, parameters):
    """``EXPLAIN`` the exact statement the code sent, with sequential scans priced out."""
    from model import db

    connection = db.session.connection()
    try:
        connection.exec_driver_sql("SET LOCAL enable_seqscan = off")
        rows = connection.exec_driver_sql("EXPLAIN " + statement, parameters).fetchall()
    finally:
        db.session.rollback()
    return "\n".join(row[0] for row in rows)


def _service_login(password, check_password=None):
    """``auth_service.login`` called directly, the way the route calls it."""
    from solverah.extensions import bcrypt
    from solverah.services import auth_service

    return auth_service.login(
        email=EMAIL,
        password=password,
        check_password=check_password or bcrypt.check_password_hash,
        wp_v2_completed=lambda _user_id: False,
    )


# -- find_by_email and the partial unique index --------------------------------


def test_find_by_email_is_served_by_the_partial_email_index(client, ctx):
    """Ledger ``user_repository``:43 and every ``missing-index`` route row."""
    from solverah.repositories import user_repository

    _register_confirmed(client)
    _fill_users()

    with _capture_sql() as sent:
        assert user_repository.find_by_email(EMAIL) is not None
    (statement, parameters), = sent

    plan = _plan_with_seqscan_off(statement, parameters)
    assert "uq_users_email" in plan, plan


def test_email_exists_is_an_exists_served_by_the_same_index(client, ctx):
    """Ledger ``user_repository``:53: an existence check, not a whole-row load."""
    from solverah.repositories import user_repository

    _register_confirmed(client)
    _fill_users()

    with _capture_sql() as sent:
        assert user_repository.email_exists(EMAIL) is True
    (statement, parameters), = sent

    assert "EXISTS" in statement.upper(), statement
    plan = _plan_with_seqscan_off(statement, parameters)
    assert "uq_users_email" in plan, plan


def test_a_soft_deleted_row_never_answers_for_its_address(client, ctx):
    """What the predicate means, pinned: an address belongs to its live row.

    ``uq_users_email`` is unique only among rows with ``deleted_at IS NULL``, so
    a soft-deleted row and a live row may hold the same address -- the index was
    drawn to allow exactly that.  Without the predicate, ``find_by_email`` took
    whichever of the two the scan met first.  Nothing sets ``deleted_at`` today
    (tombstoning rewrites the address instead, see the next test), so no real
    account can see the difference; this pins the rule for the day something
    does.
    """
    from model import User, db
    from solverah.repositories import user_repository

    gone = datetime.datetime.now(datetime.timezone.utc)
    shared = "shared-address@example.test"
    retired_only = "retired-only@example.test"
    db.session.add(User(email=shared, password_hash="not-a-real-hash", deleted_at=gone))
    db.session.add(User(email=retired_only, password_hash="not-a-real-hash", deleted_at=gone))
    db.session.commit()
    live = User(email=shared, password_hash="not-a-real-hash")
    db.session.add(live)
    db.session.commit()
    live_id = live.id

    assert user_repository.find_by_email(shared).id == live_id
    assert user_repository.email_exists(shared) is True
    assert user_repository.find_by_email(retired_only) is None
    assert user_repository.email_exists(retired_only) is False


def test_a_tombstoned_account_looks_up_and_signs_in_exactly_as_before(client, ctx):
    """Review focus 5: deletion must behave as it did before the predicate.

    Deletion tombstones -- the address is rewritten to ``deleted-{id}@...`` and
    ``deleted_at`` stays NULL -- so the tombstone is still a live row to the
    index and to ``find_by_email``, under its new address, and the old address
    is free.  If deletion ever starts setting ``deleted_at``, the first
    assertion fails, and that is the moment to re-read ``find_by_email``.
    """
    from solverah.repositories import user_repository

    user_id = _register_confirmed(client)
    csrf = _login(client).get_json()["csrfToken"]
    resp = client.delete(
        "/api/v1/me", json={"confirm": "DELETE"}, headers={"X-CSRF-TOKEN": csrf}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    row = _user_row(user_id)
    assert row.deleted_at is None
    assert row.email.startswith("deleted-%d@" % user_id)

    assert user_repository.find_by_email(EMAIL) is None
    assert user_repository.email_exists(EMAIL) is False
    assert user_repository.find_by_email(row.email).id == user_id
    assert user_repository.email_exists(row.email) is True
    assert _login(client).status_code == 401


# -- login ---------------------------------------------------------------------


def test_login_reads_the_user_row_at_most_twice_and_never_rereads_its_session(client, ctx):
    """Ledger ``auth_service``:233/236 and ``refresh_tokens``:244.

    Before the fix a successful login SELECTed the same ``users`` row three
    times -- the lookup, a reload after a commit with nothing to write, a reload
    after ``issue`` committed -- and SELECTed back the ``user_sessions`` row
    ``issue`` had just inserted.  What remains is the lookup, and one reload
    when ``auth.start_session`` reads ``user.email`` after ``issue`` has
    committed; that read is in the route, outside this package.
    """
    _register_confirmed(client)

    with count_queries() as statements:
        resp = _login(client)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert len(_reads_of(statements, "users")) <= 2, statements
    assert _reads_of(statements, "user_sessions") == [], statements


def test_a_login_with_nothing_to_reset_does_not_commit(client, ctx):
    """Ledger ``auth_service``:233: no write, so no commit.

    The session row that ``issue`` inserts next is the request's only commit.
    """
    _register_confirmed(client)

    with _count_commits() as commits:
        result = _service_login(PASSWORD)

    assert result.status == 200
    assert result.body["user"]["email"] == EMAIL
    assert commits == []


def test_a_login_after_failures_clears_the_counter_in_one_versioned_write(client, ctx):
    """Characterisation: the reset still happens, and it moves ``version``."""
    user_id = _register_confirmed(client)
    assert _login(client, WRONG).status_code == 401
    assert _login(client, WRONG).status_code == 401
    before = _user_row(user_id)
    assert before.failed_login_count == 2

    resp = _login(client)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    after = _user_row(user_id)
    assert after.failed_login_count == 0
    assert after.locked_until is None
    assert after.version == before.version + 1


def test_the_threshold_failure_locks_the_account_and_restarts_the_count(client, ctx):
    """Characterisation of the lockout rules the SQL-side counter must keep."""
    from solverah.services import auth_service

    user_id = _register_confirmed(client)
    for _attempt in range(auth_service.MAX_LOGIN_ATTEMPTS - 1):
        assert _login(client, WRONG).status_code == 401
    assert _user_row(user_id).failed_login_count == auth_service.MAX_LOGIN_ATTEMPTS - 1
    assert _user_row(user_id).locked_until is None

    assert _login(client, WRONG).status_code == 401

    row = _user_row(user_id)
    earliest = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=auth_service.LOGIN_LOCKOUT_MINUTES - 1
    )
    assert row.failed_login_count == 0
    assert row.locked_until is not None and row.locked_until > earliest
    # Locked: even the right password is refused, before it is checked.
    assert _login(client).status_code == 423


def test_two_failed_logins_through_two_sessions_are_both_counted(client, ctx):
    """Ledger ``auth_service``:227, the lost update.

    The second attempt runs start to finish while the first is inside its
    password check -- the bcrypt window, which is where two real requests
    overlap.  Both read the row at the same ``version``.  Counted in Python, the
    first to write won and the second raised ``StaleDataError``; counted in
    SQL, each increment lands on the row as it stands.
    """
    from app import app

    user_id = _register_confirmed(client)
    before = _user_row(user_id)
    inner = []

    def check_password_while_another_attempt_runs(_hash, _password):
        with app.app_context():
            inner.append(_service_login(WRONG, check_password=lambda *_args: False))
        return False

    outer = _service_login(WRONG, check_password=check_password_while_another_attempt_runs)

    assert [r.status for r in inner] == [401]
    assert outer.status == 401
    after = _user_row(user_id)
    assert after.failed_login_count == before.failed_login_count + 2
    assert after.version == before.version + 2


def test_a_failed_login_moves_version_so_a_stale_writer_still_loses(client, ctx):
    """The ``version_id_col`` contract, kept by the SQL-side counter.

    A session that read the row before the failed login must still fail its
    own write afterwards, exactly as it would had the counter gone through the
    ORM.  An UPDATE that skipped ``version`` would let it overwrite silently.
    """
    from model import User, db

    user_id = _register_confirmed(client)
    stale = Session(db.engine)
    try:
        holder = stale.get(User, user_id)
        read_at = holder.version

        assert _service_login(WRONG).status == 401
        assert _user_row(user_id).version == read_at + 1

        holder.name = "written from a stale read"
        with pytest.raises(StaleDataError):
            stale.commit()
    finally:
        stale.close()


# -- register and OTP sign-in ----------------------------------------------------


def test_register_answers_from_values_read_before_its_commit(client, ctx):
    """Ledger ``auth_service``:126 and :171.

    Before: a whole-row SELECT to learn whether the address was taken, and a
    reload of the new row after the commit to build the body.  Now: one EXISTS.
    """
    with count_queries() as statements:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "name": "Ledger B",
                  "terms_accepted": True},
        )

    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["message"] == "registered"
    assert set(body["user"]) == {"id", "email", "name", "role"}
    assert body["user"]["email"] == EMAIL
    assert body["user"]["name"] == "Ledger B"
    assert body["user"]["role"] == "job-seeker"
    assert body["user"]["id"] == _user_row(body["user"]["id"]).id
    users_reads = _reads_of(statements, "users")
    assert len(users_reads) == 1, statements
    assert "EXISTS" in users_reads[0].upper()


def test_otp_sign_in_reloads_the_user_row_at_most_once(client, ctx, monkeypatch):
    """Ledger ``auth_service``:427 and ``refresh_tokens``:244, on the OTP path.

    ``verify_password_reset`` must commit (the code is single-use), and that
    commit expires the row.  Before: a reload for the body, another after
    ``issue`` committed, and a SELECT of the new session row.  Now the body is
    read before the commit and ``issue`` takes the id from the identity map, so
    the only reload left is the route's ``user.email``.
    """
    codes = []
    monkeypatch.setattr(
        "solverah.infra.email.send_password_reset_email",
        lambda to, code: codes.append(code),
    )
    user_id = _register_confirmed(client)
    assert client.post("/api/v1/auth/password/forgot", json={"email": EMAIL}).status_code == 200
    assert len(codes) == 1

    with count_queries() as statements:
        resp = client.post(
            "/api/v1/auth/password/reset", json={"email": EMAIL, "code": codes[0]}
        )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["user"] == {
        "id": user_id, "email": EMAIL, "name": "Ledger B", "role": "job-seeker",
    }
    assert len(_reads_of(statements, "users")) <= 2, statements
    assert _reads_of(statements, "user_sessions") == [], statements


def test_an_intake_sign_in_reloads_the_user_row_at_most_once(client, ctx, monkeypatch):
    """``refresh_tokens.issue`` on the intake path, where the caller commits first.

    ``intake_service.sign_in`` commits the merge and hands ``start_session`` the
    expired ``user``.  Before: ``issue`` reloaded it to read ``user.id``,
    reloaded it again after its own commit for the log line, and SELECTed the
    session row back for ``family_id``.  Now the one reload left is the route's
    read of ``user.email`` after ``issue`` commits (``auth.start_session``).
    """
    import uuid

    from model import IntakeSubmission, db

    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)
    _register_confirmed(client)
    submission_id = str(uuid.uuid4())
    db.session.add(IntakeSubmission(
        id=submission_id, first_name="Ledger", last_name="Bee", email=EMAIL,
        state="NY", resume_key="intake/%s/resume.pdf" % submission_id,
        resume_mime="application/pdf", resume_size_bytes=1024,
    ))
    db.session.commit()

    with count_queries() as statements:
        resp = client.post("/api/v1/intake/claims", json={
            "mode": "sign_in", "submission_id": submission_id,
            "email": EMAIL, "password": PASSWORD,
        })

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert len(_reads_of(statements, "users")) <= 2, statements
    assert _reads_of(statements, "user_sessions") == [], statements


def test_issue_does_not_reload_the_user_it_is_handed(client, ctx):
    """Ledger ``refresh_tokens``:244, at the unit.

    A caller that has just committed hands ``issue`` an expired instance.  The
    id is in the identity map and ``family_id`` comes back on the INSERT, so
    the INSERT is the only statement.  Before: a reload of the user for its id,
    another after the commit for the log line, and a SELECT of the session row.
    """
    from model import User, UserSession, db
    from solverah.services import refresh_tokens

    user_id = _register_confirmed(client)
    user = db.session.get(User, user_id)
    db.session.commit()  # expires `user`, as the OTP path's commit does

    with count_queries() as statements:
        issued = refresh_tokens.issue(user)

    assert len(statements) == 1, statements
    assert statements[0].lstrip().upper().startswith("INSERT INTO USER_SESSIONS")
    stored = UserSession.query.filter_by(user_id=user_id).one()
    assert str(stored.family_id) == issued.family_id


# -- refresh rotation -------------------------------------------------------------


def test_rotation_reads_the_user_once_and_links_the_successor_in_the_claim(client, ctx):
    """Ledger ``refresh_tokens``:295/349/356.

    Before: SELECT the session, SELECT the user, UPDATE (claim), INSERT the
    successor, UPDATE ``successor_id``, then SELECT the user again because the
    commit had expired it -- six.  Now the account's existence rides on the
    session SELECT, the claim sets ``successor_id`` itself, and the user is
    read once, after the commit, so the route's ``user.email`` is already
    loaded -- four.
    """
    _register_confirmed(client)
    assert _login(client).status_code == 200

    with count_queries() as statements:
        resp = client.post("/api/v1/auth/refresh", json={})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert len(statements) <= 4, statements
    assert len(_reads_of(statements, "users")) == 1, statements
    assert len(_updates_of(statements, "user_sessions")) == 1, statements


# -- the outbox and resume jobs ----------------------------------------------------


def test_depth_sends_one_statement(client, ctx):
    """Ledger ``outbox``:386/405 and ``cli.py``:134."""
    from model import Outbox, db
    from solverah.services import outbox

    payload = {"to": "depth@example.test", "code": "123456"}
    outbox.enqueue(outbox.TOPIC_EMAIL_VERIFICATION, payload)                # pending
    parked = outbox.enqueue(outbox.TOPIC_EMAIL_VERIFICATION, payload)       # parked
    delivered = outbox.enqueue(outbox.TOPIC_EMAIL_VERIFICATION, payload)    # not owed
    db.session.commit()
    assert outbox.publish(delivered) == outbox.PUBLISHED
    table = Outbox.__table__
    with db.engine.begin() as connection:
        connection.execute(
            sa.update(table).where(table.c.id == parked).values(attempts=outbox.MAX_ATTEMPTS)
        )

    with count_queries() as statements:
        depth = outbox.depth()

    assert depth == {"pending": 1, "parked": 1}
    assert len(statements) == 1, statements


def test_create_hands_back_a_job_readable_without_a_reload(client, ctx, monkeypatch):
    """Ledger ``resume_jobs``:114/120.

    The route reads ``public_id`` and ``status`` off the job ``create`` returns.
    The commit used to expire it, so that read was a SELECT of the row just
    inserted.  Now the INSERT is the only statement, and the worker is handed
    the committed row's id.
    """
    from model import ResumeParseJob, User, db
    from solverah.services import resume_jobs

    user_id = _register_confirmed(client)
    user = db.session.get(User, user_id)
    # Patched after registering, whose verification email is enqueued too.
    queued = []
    monkeypatch.setattr(
        "solverah.infra.queue.enqueue", lambda _task, *args, **_kw: queued.append(args)
    )

    with count_queries() as statements:
        job = resume_jobs.create(
            user,
            object_key="profile/%d/abc/resume.pdf" % user_id,
            mime="application/pdf",
            size=2048,
            name="cv.pdf",
        )
        handle, status, job_id = job.public_id.hex, job.status, job.id

    assert len(statements) == 1, statements
    assert statements[0].lstrip().upper().startswith("INSERT INTO RESUME_PARSE_JOBS")
    assert status == resume_jobs.QUEUED
    assert queued == [(job_id,)]
    stored = db.session.get(ResumeParseJob, job_id)
    assert stored.public_id.hex == handle
    assert stored.status == resume_jobs.QUEUED
