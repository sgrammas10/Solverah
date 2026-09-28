"""DB-ledger regression tests for package D1: the intake writes and retention.

Two of these pin correctness bugs rather than speed:

* ``insert_submission`` committed its row on a raw psycopg2 connection of its
  own, so ``finalize``'s "the row and the notification are one commit" was
  false: an outbox failure after the insert left a submission row that nobody
  was ever told about.
* ``link_account`` added its audit row after its only commit, so the row was
  rolled back at teardown and the event was never recorded.

The rest pin statement shapes: the user_intake upsert is one race-free
statement, the attach flows build their responses before committing instead
of reloading expired rows afterwards, the retention sweep's statement count
does not grow with the number of stale intakes, and the orphan sweep's guard
asks whether rows exist instead of counting them.

"Committed" is always checked from a second connection, never from the session
that did the work -- the session sees its own uncommitted writes.
"""

from __future__ import annotations

import datetime
import threading
import time
import uuid

import pytest
import sqlalchemy as sa

from tests.query_count import count_queries

PASSWORD = "Strongpass1!"
LINKER = "linker@example.com"


# ── Fakes and fixtures ──────────────────────────────────────────────────────


class _FakeBucket:
    """Stand-in for R2.

    Every HEAD matches what the tests declare (1024 bytes of PDF), a resume body
    cannot be fetched -- so the parser yields an empty profile, the documented
    degradation -- and deletes are recorded, or refused for keys containing a
    marker passed to :meth:`refuse`.
    """

    def __init__(self):
        self.objects = {}  # key -> last_modified
        self.deleted = []
        self._refused = ()

    def refuse(self, *markers):
        self._refused = markers

    def head_object(self, Bucket, Key):
        return {"ContentLength": 1024, "ContentType": "application/pdf"}

    def get_object(self, Bucket, Key):
        raise RuntimeError("no resume bodies in tests")

    def delete_object(self, Bucket, Key):
        if any(marker in Key for marker in self._refused):
            raise RuntimeError("delete refused")
        self.deleted.append(Key)
        self.objects.pop(Key, None)

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):
        yield {
            "Contents": [
                {"Key": key, "LastModified": modified}
                for key, modified in list(self.objects.items())
                if key.startswith(Prefix)
            ]
        }


@pytest.fixture()
def bucket(monkeypatch):
    """A configured bucket behind every storage entry point these flows use."""
    fake = _FakeBucket()
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: fake)
    monkeypatch.setattr("solverah.services.resume_service.get_s3_client", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _no_mail(monkeypatch):
    """No step here may depend on a mail provider being reachable."""
    from solverah.infra import email as email_infra

    for name in dir(email_infra):
        if name.startswith("send_"):
            monkeypatch.setattr(email_infra, name, lambda *_a, **_k: None)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _committed(sql, **params):
    """Rows as a second connection sees them -- that is, what was committed."""
    from app import app
    from model import db

    with app.app_context():
        with db.engine.connect() as conn:
            return [dict(row) for row in conn.execute(sa.text(sql), params).mappings()]


def _committed_submission(submission_id):
    rows = _committed(
        "SELECT id, email, status, first_name, last_name, resume_key "
        "FROM intake_submissions WHERE id = :id",
        id=submission_id,
    )
    return rows[0] if rows else None


def _audit_events(action):
    return _committed(
        "SELECT actor_user_id, metadata FROM audit_log WHERE action = :action",
        action=action,
    )


def _submission_body(email="ada@example.com"):
    """A finalize body whose upload the fake bucket will confirm."""
    submission_id = str(uuid.uuid4())
    return {
        "submission_id": submission_id,
        "object_key": "intake/%s/resume.pdf" % submission_id,
        "mime": "application/pdf",
        "size": 1024,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": email,
        "state": "NY",
        "privacy_consent": True,
    }


def _make_user(email, name="Existing User"):
    """A confirmed account that can sign in with PASSWORD. Returns its id."""
    from app import app
    from model import User, db
    from solverah.extensions import bcrypt

    with app.app_context():
        user = User(
            email=email,
            password_hash=bcrypt.generate_password_hash(PASSWORD).decode("utf-8"),
            name=name,
            email_confirmed=True,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, email):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["csrfToken"]


def _claim(client, body, csrf=None):
    headers = {"X-CSRF-TOKEN": csrf} if csrf else {}
    return client.post("/api/v1/intake/claims", json=body, headers=headers)


def _seed_submission(email, age_days=0, key_marker="resume"):
    """An intake row sitting in the funnel. Returns (id, resume_key)."""
    from app import app
    from model import IntakeSubmission, db

    submission_id = str(uuid.uuid4())
    resume_key = "intake/%s/%s.pdf" % (submission_id, key_marker)
    # Naive UTC: the column is `timestamp without time zone`.
    created = datetime.datetime.now(datetime.timezone.utc).replace(
        tzinfo=None
    ) - datetime.timedelta(days=age_days)
    with app.app_context():
        db.session.add(IntakeSubmission(
            id=submission_id, first_name="Claim", last_name="Tester", email=email,
            state="NY", resume_key=resume_key, resume_mime="application/pdf",
            resume_size_bytes=1024, created_at=created,
        ))
        db.session.commit()
    return submission_id, resume_key


def _reloads(statements, table):
    """Primary-key SELECTs of *table*: the refresh an expired instance issues."""
    return [
        s for s in statements
        if s.lstrip().upper().startswith("SELECT")
        and ("FROM %s" % table) in s
        and "%(pk_1)s" in s
    ]


# ── finalize: the row and its notification are one commit ──────────────────


def test_finalize_leaves_no_row_when_the_outbox_write_fails(client, bucket, monkeypatch):
    """Review focus 4: the S3 check passes, the outbox insert fails, no orphan row.

    Until the insert joined the session it committed on a connection of its
    own, so the row survived the failure -- a submission nobody was told about.
    """
    def _outbox_down(*_args, **_kwargs):
        raise RuntimeError("outbox insert failed")

    monkeypatch.setattr("solverah.services.outbox.enqueue", _outbox_down)
    body = _submission_body()

    resp = client.post("/api/v1/intake/submissions", json=body)

    assert resp.status_code == 500
    assert _committed_submission(body["submission_id"]) is None


def test_finalize_commits_the_row_with_its_notification(client, bucket):
    from solverah.services import outbox

    body = _submission_body(email="Ada@Example.com")

    resp = client.post("/api/v1/intake/submissions", json=body)

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    row = _committed_submission(body["submission_id"])
    assert row["email"] == "ada@example.com"
    assert row["status"] == "uploaded"
    assert row["resume_key"] == body["object_key"]
    notices = _committed(
        "SELECT payload FROM outbox WHERE topic = :topic",
        topic=outbox.TOPIC_EMAIL_INTAKE_NOTIFICATION,
    )
    assert len(notices) == 1
    assert notices[0]["payload"]["object_key"] == body["object_key"]


# ── link: one commit carries the row, the profile, the name and the audit ────


def test_link_records_its_audit_event(client, bucket):
    """The audit row was added after the only commit, and rolled back with the session."""
    user_id = _make_user(LINKER)
    csrf = _login(client, LINKER)
    body = dict(_submission_body(email="someone-else@example.com"), mode="link")

    resp = _claim(client, body, csrf)

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    events = _audit_events("intake_link_account")
    assert len(events) == 1
    assert events[0]["actor_user_id"] == user_id
    assert events[0]["metadata"] == {
        "submission_id": body["submission_id"], "email": LINKER,
    }


def test_link_writes_the_row_in_the_request_transaction_and_never_rereads_it(
    client, bucket
):
    """The INSERT runs on the app's engine, and ``fields`` already held the row.

    It used to go out on a raw psycopg2 connection -- invisible to the
    statement counter, and outside the transaction -- and then be read straight
    back through the session to build the profile from values already in hand.
    """
    from app import app

    _make_user(LINKER)
    csrf = _login(client, LINKER)
    body = dict(_submission_body(email="someone-else@example.com"), mode="link")

    # count_queries reads db.engine, which needs an app context. The request
    # reuses this one instead of pushing its own; nothing asserted here depends
    # on the request's session teardown, and "committed" is read afterwards
    # through a second connection.
    with app.app_context(), count_queries() as statements:
        resp = _claim(client, body, csrf)

    assert resp.status_code == 200
    inserts = [s for s in statements if "INSERT INTO intake_submissions" in s]
    rereads = [s for s in statements if "FROM intake_submissions" in s]
    assert {"inserts": len(inserts), "rereads": len(rereads)} == {
        "inserts": 1, "rereads": 0,
    }
    row = _committed_submission(body["submission_id"])
    assert row["email"] == LINKER  # the JWT identity, never the body's address
    assert row["status"] == "account_linked"


def test_link_takes_the_name_and_profile_from_the_submission(client, bucket):
    from app import app
    from model import User
    from solverah.repositories import profile_repository

    user_id = _make_user(LINKER, name="Old Name")
    csrf = _login(client, LINKER)
    body = dict(_submission_body(), mode="link", first_name="Grace", last_name="Hopper")
    body["phone"] = "555-010-0199"

    assert _claim(client, body, csrf).status_code == 200

    with app.app_context():
        assert User.query.filter_by(id=user_id).one().name == "Grace Hopper"
        document = profile_repository.load_document(user_id)
    assert document["firstName"] == "Grace"
    assert document["lastName"] == "Hopper"
    assert document["phone"] == "555-010-0199"
    assert document["resumeKey"] == body["object_key"]


def _refuse_upload(monkeypatch, fake):
    def _missing(**_kwargs):
        raise RuntimeError("NoSuchKey")

    monkeypatch.setattr(fake, "head_object", _missing)


def _profile_merge_fails(monkeypatch, _fake):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("profile write failed")

    monkeypatch.setattr(
        "solverah.repositories.profile_repository.update_document", _boom
    )


@pytest.mark.parametrize(
    "break_it, status",
    [(_refuse_upload, 400), (_profile_merge_fails, 500)],
    ids=["before-the-insert", "after-the-insert"],
)
def test_link_that_fails_leaves_neither_row_nor_audit_event(
    client, bucket, monkeypatch, break_it, status
):
    """Every path either commits the submission with its audit event, or neither.

    The after-the-insert case left a committed row behind while the request
    500'd, and a retry with the same submission id then hit the primary key.
    """
    _make_user(LINKER)
    csrf = _login(client, LINKER)
    body = dict(_submission_body(), mode="link")
    break_it(monkeypatch, bucket)

    resp = _claim(client, body, csrf)

    assert resp.status_code == status
    assert _committed_submission(body["submission_id"]) is None
    assert _audit_events("intake_link_account") == []


# ── The attach flows answer before they commit ──────────────────────────────


def test_register_builds_its_response_before_the_commit(client, bucket):
    """The commit expires the new user; reading it afterwards was a refresh SELECT."""
    from app import app
    from solverah.extensions import bcrypt
    from solverah.services import intake_service
    from validators import validate_password

    submission_id, _ = _seed_submission("new-account@example.com")

    with app.test_request_context():
        with count_queries() as statements:
            result = intake_service.create_account(
                {"submission_id": submission_id, "password": PASSWORD},
                hash_password=bcrypt.generate_password_hash,
                validate_password=validate_password,
            )

    assert result.status == 201
    assert result.body["message"] == "registered"
    assert result.body["user"]["email"] == "new-account@example.com"
    assert result.body["user"]["name"] == "Claim Tester"
    assert result.body["user"]["role"] == "job-seeker"
    assert isinstance(result.body["user"]["id"], int)
    assert _reloads(statements, "users") == []


def test_sign_in_builds_its_response_before_the_commit(client, bucket):
    from app import app
    from solverah.extensions import bcrypt
    from solverah.services import intake_service

    user_id = _make_user("signer@example.com")
    submission_id, _ = _seed_submission("signer@example.com")

    with app.test_request_context():
        with count_queries() as statements:
            result = intake_service.sign_in(
                {"submission_id": submission_id, "email": "signer@example.com",
                 "password": PASSWORD},
                check_password=bcrypt.check_password_hash,
            )

    assert result.status == 200
    assert result.issue_token is True
    assert result.body == {
        "message": "signed in",
        "user": {"id": user_id, "email": "signer@example.com",
                 "name": "Claim Tester", "role": "job-seeker"},
    }
    assert _reloads(statements, "users") == []


SESSION_BODY = {
    "selected_statement_ids": ["dir-1", "sus-2"],
    "wpll_answers": [
        {"question_id": "wpll-q%d" % i, "option_id": "wpll-q%d-c" % i}
        for i in range(1, 6)
    ],
    "wpll_insight_text": "Test insight text.",
}


def test_save_to_account_answers_before_the_commit(client):
    from app import app
    from model import User, db
    from solverah.services import intake_service

    user_id = _make_user("saver@example.com")

    with app.test_request_context():
        user = db.session.get(User, user_id)
        with count_queries() as statements:
            result = intake_service.save_to_account(user, SESSION_BODY)

    assert result.status == 200
    assert result.body == {"message": "Intake saved", "wpll_completed": True}
    assert _reloads(statements, "assessment_submissions") == []


# ── user_intake: one upsert statement, race-free ────────────────────────────


def _user_intake_rows(user_id):
    return _committed(
        "SELECT selected_statement_ids, wpll_answers FROM user_intake "
        "WHERE user_id = :uid",
        uid=user_id,
    )


def test_upsert_user_intake_is_one_statement(client):
    from app import app
    from model import db
    from solverah.repositories import intake_repository

    user_id = _make_user("one-statement@example.com")

    with app.app_context():
        with count_queries() as statements:
            intake_repository.upsert_user_intake(user_id, ["dir-1"])
        db.session.commit()

    assert len(statements) == 1, statements
    assert "ON CONFLICT (user_id) DO UPDATE" in statements[0]


def test_two_upserts_leave_one_row_holding_the_second_selection(client):
    from app import app
    from model import UserIntake, db
    from solverah.repositories import intake_repository

    user_id = _make_user("twice@example.com")

    with app.app_context():
        first = intake_repository.upsert_user_intake(user_id, ["dir-1"])
        assert isinstance(first, UserIntake)
        assert first.selected_statement_ids == ["dir-1"]
        db.session.commit()

    with app.app_context():
        loaded = intake_repository.find_user_intake(user_id)
        second = intake_repository.upsert_user_intake(user_id, ["sus-2", "dir-3"])
        # The session's copy is the stored row, not the one read before the write.
        assert second is loaded
        assert loaded.selected_statement_ids == ["sus-2", "dir-3"]
        db.session.commit()

    rows = _user_intake_rows(user_id)
    assert len(rows) == 1
    assert rows[0]["selected_statement_ids"] == ["sus-2", "dir-3"]
    assert rows[0]["wpll_answers"] == []  # the insert's column default still applies


def _wait_for_lock_wait_or_exit(conn, worker, timeout=15.0):
    """Return once *worker* is blocked on a row lock, or has finished.

    *conn* is opened by the caller before the worker starts, so no connection is
    being established while the worker opens its own. Each poll ends its
    transaction: ``pg_stat_activity`` is snapshotted once per transaction.
    """
    deadline = time.monotonic() + timeout
    while worker.is_alive() and time.monotonic() < deadline:
        waiting = conn.execute(sa.text(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND wait_event_type = 'Lock'"
        )).scalar()
        conn.rollback()
        if waiting:
            return
        time.sleep(0.05)


def test_racing_upserts_for_one_user_both_commit_into_one_row(client):
    """Two claims for one account at once: both succeed, one row survives.

    Select-then-insert let both see "no row" and both INSERT; the loser died
    with an IntegrityError at commit. The upsert makes the second writer wait
    for the first and then update.
    """
    from app import app
    from model import db
    from solverah.repositories import intake_repository

    user_id = _make_user("race@example.com")
    outcome = {}

    def _second_writer():
        with app.app_context():
            try:
                intake_repository.upsert_user_intake(user_id, ["second"])
                db.session.commit()
                outcome["second"] = "committed"
            except Exception as exc:  # noqa: BLE001 -- reported by the assert
                db.session.rollback()
                outcome["second"] = repr(exc)

    worker = threading.Thread(target=_second_writer)
    ctx = app.app_context()
    ctx.push()
    try:
        with db.engine.connect() as observer:
            # The first writer runs its upsert but does not commit yet.
            intake_repository.upsert_user_intake(user_id, ["first"])
            worker.start()
            _wait_for_lock_wait_or_exit(observer, worker)
            db.session.commit()
    finally:
        db.session.rollback()
        ctx.pop()
        if worker.ident is not None:
            worker.join(timeout=30)

    assert outcome == {"second": "committed"}
    rows = _user_intake_rows(user_id)
    assert len(rows) == 1
    assert rows[0]["selected_statement_ids"] == ["second"]


def test_find_user_intake_loads_only_the_named_columns(client):
    from app import app
    from model import db
    from solverah.repositories import intake_repository

    user_id = _make_user("narrow@example.com")
    with app.app_context():
        intake_repository.upsert_user_intake(user_id, ["dir-1"])
        db.session.commit()

    with app.app_context():
        with count_queries() as narrow:
            intake = intake_repository.find_user_intake(
                user_id, only=["selected_statement_ids"]
            )
        assert intake.selected_statement_ids == ["dir-1"]
    with app.app_context():
        with count_queries() as full:
            assert intake_repository.find_user_intake(user_id).wpl_result is None

    assert len(narrow) == 1
    assert "user_intake.selected_statement_ids" in narrow[0]
    assert "user_intake.wpl_result" not in narrow[0]
    assert "user_intake.wpl_result" in full[0]


# ── retention_cleanup ───────────────────────────────────────────────────────


def _intake_ids():
    return {row["id"] for row in _committed("SELECT id FROM intake_submissions")}


def test_rule_one_deletes_exactly_the_abandoned_intakes(client, bucket):
    """Stale and accountless goes, with its object first; everything else stays."""
    from retention_cleanup import run_cleanup

    _make_user("kept@example.com")
    gone, gone_key = _seed_submission("gone@example.com", age_days=100)
    kept_by_account, _ = _seed_submission("KEPT@example.com", age_days=100)
    recent, _ = _seed_submission("gone-later@example.com", age_days=1)
    stuck, _ = _seed_submission("stuck@example.com", age_days=100, key_marker="refused")
    bucket.refuse("refused")

    summary = run_cleanup(dry_run_sweep=True)

    assert summary["abandoned_intakes_deleted"] == 1
    assert summary["r2_objects_deleted"] == 1
    assert summary["r2_delete_failures"] == 1  # its row stays for the next run
    assert bucket.deleted == [gone_key]
    assert gone not in _intake_ids()
    assert _intake_ids() == {kept_by_account, recent, stuck}


def test_rule_one_without_a_bucket_deletes_rows_only(client, monkeypatch):
    from retention_cleanup import run_cleanup

    monkeypatch.delenv("S3_BUCKET_NAME", raising=False)

    def _no_storage():
        raise AssertionError("no bucket is configured; storage must not be touched")

    monkeypatch.setattr("solverah.infra.storage.get_s3_client", _no_storage)
    gone, _ = _seed_submission("gone@example.com", age_days=100)

    summary = run_cleanup(dry_run_sweep=True)

    assert summary["abandoned_intakes_deleted"] == 1
    assert summary["r2_objects_deleted"] == 0
    assert _intake_ids() == set()


def test_rule_one_statement_count_is_flat_in_the_number_of_stale_intakes(
    client, bucket
):
    """One users lookup and one DELETE per stale intake was the N+1."""
    from app import app
    from retention_cleanup import run_cleanup

    _make_user("kept@example.com")
    _seed_submission("kept@example.com", age_days=100)

    def _statements_for(stale):
        for i in range(stale):
            _seed_submission("gone-%d-%d@example.com" % (stale, i), age_days=100)
        with app.app_context(), count_queries() as statements:
            summary = run_cleanup(dry_run_sweep=True)
        assert summary["abandoned_intakes_deleted"] == stale
        return statements

    few = _statements_for(2)
    many = _statements_for(6)

    assert len(many) == len(few), many


def test_a_full_run_sweeps_what_rule_one_left_behind(client, bucket):
    """All three rules end to end, through the storage client the script imports."""
    from retention_cleanup import ORPHAN_GRACE_HOURS, run_cleanup

    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=ORPHAN_GRACE_HOURS + 1
    )
    _make_user("kept@example.com")
    _, gone_key = _seed_submission("gone@example.com", age_days=100)
    _, live_key = _seed_submission("kept@example.com", age_days=100)
    bucket.objects.update({gone_key: old, live_key: old, "intake/orphan/resume.pdf": old})

    summary = run_cleanup()

    assert summary["abandoned_intakes_deleted"] == 1
    assert summary["orphans_deleted"] == 1
    assert sorted(bucket.deleted) == sorted([gone_key, "intake/orphan/resume.pdf"])
    assert set(bucket.objects) == {live_key}


def _sweep_with(bucket_fake):
    from model import IntakeSubmission, ResumeParseCorrection, User, db
    from retention_cleanup import _sweep_orphans

    now = datetime.datetime.now(datetime.timezone.utc)
    return _sweep_orphans(
        now, "test-bucket", lambda: bucket_fake, db,
        IntakeSubmission, ResumeParseCorrection, User,
    )


def test_orphan_guard_asks_whether_rows_exist_not_how_many(client, bucket):
    from app import app

    with app.app_context():
        with count_queries() as statements:
            summary = _sweep_with(bucket)

    assert summary["orphan_sweep_skipped"] == "empty database"
    assert len(statements) == 1, statements
    assert "EXISTS" in statements[0].upper()
    assert "COUNT(" not in statements[0].upper()


@pytest.mark.parametrize("seed", ["user", "intake"])
def test_orphan_guard_lets_either_table_through(client, bucket, seed):
    """Users alone, or intakes alone, are enough to trust the database."""
    from app import app

    if seed == "user":
        _make_user("anyone@example.com")
    else:
        _seed_submission("visitor@example.com")

    with app.app_context():
        summary = _sweep_with(bucket)

    assert "orphan_sweep_skipped" not in summary


def test_correction_keys_are_read_once_each(client):
    from app import app
    from model import IntakeSubmission, ResumeParseCorrection, User, db
    from retention_cleanup import _referenced_resume_keys

    user_id = _make_user("corrector@example.com")
    with app.app_context():
        for field in ("experience", "education", "skills"):
            db.session.add(ResumeParseCorrection(
                user_id=user_id, resume_key="profile/x/resume.pdf", field=field,
            ))
        db.session.commit()

        with count_queries() as statements:
            keys = _referenced_resume_keys(db, IntakeSubmission, ResumeParseCorrection, User)

    assert "profile/x/resume.pdf" in keys
    reads = [s for s in statements if "FROM resume_parse_correction" in s]
    assert len(reads) == 1
    assert "DISTINCT" in reads[0].upper()
