"""Tests for the orphaned-object sweep (retention_cleanup rule 3), and for the
``flask retention cleanup`` cron entry point that runs all three rules.

Objects from presigned uploads that were never finalized have no database row,
so rules 1-2 -- which walk rows -- can never see them. Before rule 3 existed
they accumulated in R2 forever. These tests pin the two things that make a
sweep safe: it deletes what nothing references, and it never deletes anything
that is still referenced or still inside the upload grace window.

The CLI half pins what the cron needs: all three rules run, ``--dry-run``
changes nothing anywhere, and an unconfigured R2 is a non-zero exit rather than
a pass that quietly skipped the storage half of its work.
"""

import datetime
import json
import uuid

import pytest

from retention_cleanup import ORPHAN_GRACE_HOURS, _referenced_resume_keys, _sweep_orphans

NOW = datetime.datetime(2026, 8, 20, 12, 0, tzinfo=datetime.timezone.utc)
OLD = NOW - datetime.timedelta(hours=ORPHAN_GRACE_HOURS + 1)
RECENT = NOW - datetime.timedelta(hours=1)


class _FakeS3:
    """Stand-in for the R2 client: pages a fixed object list, records deletes."""

    def __init__(self, objects):
        self._objects = objects  # list of (key, last_modified)
        self.deleted = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):
        yield {
            "Contents": [
                {"Key": k, "LastModified": lm}
                for k, lm in self._objects
                if k.startswith(Prefix)
            ]
        }

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)


def _sweep(objects):
    """Run the sweep against *objects*, returning (summary, deleted_keys)."""
    from model import IntakeSubmission, ResumeParseCorrection, User, db

    fake = _FakeS3(objects)
    summary = _sweep_orphans(
        NOW, "test-bucket", lambda: fake, db,
        IntakeSubmission, ResumeParseCorrection, User,
    )
    return summary, fake.deleted


def _make_user(email="keep@example.com", profile=None):
    from model import User, db
    from solverah.repositories import profile_repository

    user = User(email=email, password_hash="x")
    db.session.add(user)
    # Flushed rather than committed so the profile write below has an id to
    # hang rows off; both land in the one commit at the end.
    db.session.flush()
    profile_repository.update_document(user.id, lambda _existing: profile or {})
    db.session.commit()
    return user


def _make_intake(resume_key):
    from model import IntakeSubmission, db

    db.session.add(IntakeSubmission(
        id=resume_key, first_name="A", last_name="B", email="i@example.com",
        state="NY", resume_key=resume_key, resume_mime="application/pdf",
        resume_size_bytes=10,
    ))
    db.session.commit()


def test_old_unreferenced_object_is_deleted(client):
    from app import app

    with app.app_context():
        _make_user()
        summary, deleted = _sweep([("intake/abandoned/resume.pdf", OLD)])

    assert deleted == ["intake/abandoned/resume.pdf"]
    assert summary["orphans_deleted"] == 1


def test_object_inside_grace_window_is_kept(client):
    """A 10-minute presign plus finalize must never race the sweep."""
    from app import app

    with app.app_context():
        _make_user()
        summary, deleted = _sweep([("intake/in-flight/resume.pdf", RECENT)])

    assert deleted == []
    assert summary["orphans_deleted"] == 0


def test_object_referenced_by_intake_row_is_kept(client):
    from app import app

    with app.app_context():
        _make_user()
        _make_intake("intake/live/resume.pdf")
        _, deleted = _sweep([("intake/live/resume.pdf", OLD)])

    assert deleted == []


@pytest.mark.parametrize("profile", [
    {"resumeKey": "profile/1/live/resume.pdf"},
    {"_parsedResumeSnapshot": {"resumeKey": "profile/1/live/resume.pdf"}},
])
def test_object_referenced_from_profile_json_is_kept(client, profile):
    """Both the active key and the parser snapshot key count as references."""
    from app import app

    with app.app_context():
        _make_user(profile=profile)
        _, deleted = _sweep([("profile/1/live/resume.pdf", OLD)])

    assert deleted == []


def test_object_referenced_by_parse_correction_is_kept(client):
    from app import app
    from model import ResumeParseCorrection, db

    with app.app_context():
        user = _make_user()
        db.session.add(ResumeParseCorrection(
            user_id=user.id, resume_key="profile/1/corrected/resume.pdf",
            field="skills",
        ))
        db.session.commit()
        _, deleted = _sweep([("profile/1/corrected/resume.pdf", OLD)])

    assert deleted == []


def test_empty_database_aborts_the_sweep(client):
    """An empty DB makes every object look orphaned -- assume wrong DB, not garbage."""
    from app import app

    with app.app_context():
        summary, deleted = _sweep([("intake/anything/resume.pdf", OLD)])

    assert deleted == []
    assert summary["orphan_sweep_skipped"] == "empty database"


def test_referenced_keys_collects_all_three_sources(client):
    from app import app
    from model import IntakeSubmission, ResumeParseCorrection, User, db

    with app.app_context():
        user = _make_user(profile={
            "resumeKey": "profile/a.pdf",
            "_parsedResumeSnapshot": {"resumeKey": "profile/b.pdf"},
        })
        _make_intake("intake/c.pdf")
        db.session.add(ResumeParseCorrection(
            user_id=user.id, resume_key="profile/d.pdf", field="experience",
        ))
        db.session.commit()

        keys = _referenced_resume_keys(
            db, IntakeSubmission, ResumeParseCorrection, User
        )

    assert keys == {"profile/a.pdf", "profile/b.pdf", "intake/c.pdf", "profile/d.pdf"}


@pytest.mark.parametrize("status,kept", [
    ("queued", True),
    ("running", True),
    ("succeeded", False),
    ("failed", False),
])
def test_object_named_by_an_unfinished_parse_job_is_kept(client, status, kept):
    """A parse job names its key before any profile row does.

    The parse-jobs route rebuilds the key from the caller's id and queues the
    job; only the job's run writes it into the ``resumes`` row. Until then the
    job row is the one place the key lives, so a queued or running job's object
    must survive the sweep. A finished job's key is either on the profile by
    now (succeeded) or garbage (failed), so the job no longer protects it.
    """
    from app import app
    from model import ResumeParseJob, db

    key = "profile/1/%s/resume.pdf" % status
    with app.app_context():
        user = _make_user()
        db.session.add(ResumeParseJob(
            user_id=user.id, object_key=key, mime="application/pdf", status=status,
        ))
        db.session.commit()
        _, deleted = _sweep([(key, OLD)])

    assert (deleted == []) is kept, deleted


# -- flask retention cleanup ---------------------------------------------------

_S3_ENV = ("S3_BUCKET_NAME", "S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID",
           "S3_SECRET_ACCESS_KEY", "S3_REGION")


class _RecordingS3:
    """A mutable stand-in for R2 that records every call it receives."""

    def __init__(self, objects):
        self.objects = dict(objects)  # key -> last_modified
        self.calls = []  # (operation, key_or_prefix)

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):
        self.calls.append(("list", Prefix))
        yield {"Contents": [
            {"Key": k, "LastModified": lm}
            for k, lm in sorted(self.objects.items()) if k.startswith(Prefix)
        ]}

    def delete_object(self, Bucket, Key):
        self.calls.append(("delete", Key))
        self.objects.pop(Key, None)

    def put_object(self, Bucket, Key, **_kwargs):
        self.calls.append(("put", Key))


def _ago(**kwargs):
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**kwargs)


def _naive_ago(**kwargs):
    """``_ago`` for the columns that are ``timestamp without time zone``."""
    return _ago(**kwargs).replace(tzinfo=None)


def _seed_one_of_each():
    """One row or object for each rule to act on, plus one each must leave alone."""
    from app import app
    from model import AuditLog, IntakeSubmission, db

    with app.app_context():
        _make_user(profile={"resumeKey": "profile/1/live/resume.pdf"})
        for intake_id, email, age in (("ret-gone", "gone@example.com", 100),
                                      ("ret-fresh", "fresh@example.com", 1)):
            db.session.add(IntakeSubmission(
                id=intake_id, first_name="A", last_name="B", email=email,
                state="NY", resume_key="intake/%s/resume.pdf" % intake_id,
                resume_mime="application/pdf", resume_size_bytes=10,
                created_at=_naive_ago(days=age),
            ))
        for age in (400, 10):
            db.session.add(AuditLog(
                action="login", resource="user", ip_address="203.0.113.7",
                user_agent="pytest-agent", created_at=_naive_ago(days=age),
            ))
        db.session.commit()

    old = _ago(hours=ORPHAN_GRACE_HOURS + 1)
    return _RecordingS3({
        "intake/ret-gone/resume.pdf": old,    # rule 1's object
        "intake/ret-fresh/resume.pdf": old,   # referenced by a recent intake
        "profile/1/live/resume.pdf": old,     # referenced by the profile
        "intake/orphan/resume.pdf": old,      # rule 3's object
    })


def _db_state():
    """(intake ids, audit rows still holding an IP), as committed."""
    from app import app
    from model import AuditLog, IntakeSubmission, db

    with app.app_context():
        intakes = sorted(i for (i,) in db.session.query(IntakeSubmission.id))
        audit_with_ip = db.session.query(AuditLog).filter(
            AuditLog.ip_address.isnot(None)).count()
        db.session.rollback()
    return intakes, audit_with_ip


@pytest.fixture()
def r2(monkeypatch):
    """A configured bucket: S3_BUCKET_NAME set, the client factory faked."""
    holder = {}
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: holder["fake"])
    return holder


@pytest.fixture()
def no_r2(monkeypatch):
    for name in _S3_ENV:
        monkeypatch.delenv(name, raising=False)


def _cleanup(*args):
    """Run ``flask retention cleanup``; return (exit_code, parsed JSON line or None)."""
    from app import app

    result = app.test_cli_runner().invoke(args=["retention", "cleanup", *args])
    payload = None
    for line in reversed(result.output.strip().splitlines()):
        try:
            payload = json.loads(line)
            break
        except ValueError:
            continue
    return result.exit_code, payload


def _make_user_in_context():
    from app import app

    with app.app_context():
        _make_user()


def test_cli_cleanup_runs_all_three_rules(client, r2):
    r2["fake"] = fake = _seed_one_of_each()

    code, payload = _cleanup()

    assert code == 0, payload
    assert payload["event"] == "retention_cleanup"
    assert payload["abandoned_intakes_deleted"] == 1
    assert payload["r2_objects_deleted"] == 1
    assert payload["audit_rows_minimized"] == 1
    assert payload["orphans_deleted"] == 1
    assert sorted(fake.objects) == [
        "intake/ret-fresh/resume.pdf", "profile/1/live/resume.pdf",
    ]
    assert _db_state() == (["ret-fresh"], 1)


def test_cli_dry_run_changes_nothing_and_reports_what_each_rule_would_do(client, r2):
    r2["fake"] = fake = _seed_one_of_each()
    before_objects = dict(fake.objects)
    before_db = _db_state()

    code, payload = _cleanup("--dry-run")

    assert code == 0, payload
    assert payload["dry_run"] is True
    # Reading the bucket is the only storage call a dry run may make.
    assert {op for op, _ in fake.calls} == {"list"}, fake.calls
    assert fake.objects == before_objects
    assert _db_state() == before_db

    would = payload["would"]
    assert would["abandoned_intakes"] == {"count": 1, "sample_ids": ["ret-gone"]}
    assert would["intake_objects"] == {
        "count": 1, "sample_keys": ["intake/ret-gone/resume.pdf"],
    }
    assert would["audit_rows_minimized"]["count"] == 1
    assert len(would["audit_rows_minimized"]["sample_ids"]) == 1
    # Rule 1's object is rule 1's to delete: its row still names it here.
    assert would["orphans"] == {
        "count": 1, "sample_keys": ["intake/orphan/resume.pdf"], "listed": 4,
    }
    for name in ("abandoned_intakes_deleted", "r2_objects_deleted",
                 "audit_rows_minimized", "orphans_deleted"):
        assert payload[name] == 0, name


def test_cli_dry_run_samples_are_capped(client, r2):
    from app import app
    from model import IntakeSubmission, User, db
    from retention_cleanup import SAMPLE_SIZE

    with app.app_context():
        db.session.add(User(email="anyone@example.com", password_hash="x"))
        for _ in range(SAMPLE_SIZE + 5):
            intake_id = str(uuid.uuid4())
            db.session.add(IntakeSubmission(
                id=intake_id, first_name="A", last_name="B", email="g@example.com",
                state="NY", resume_key="intake/%s/resume.pdf" % intake_id,
                resume_mime="application/pdf", resume_size_bytes=10,
                created_at=_naive_ago(days=100),
            ))
        db.session.commit()
    r2["fake"] = _RecordingS3({})

    code, payload = _cleanup("--dry-run")

    assert code == 0, payload
    intakes = payload["would"]["abandoned_intakes"]
    assert intakes["count"] == SAMPLE_SIZE + 5
    assert len(intakes["sample_ids"]) == SAMPLE_SIZE


@pytest.mark.parametrize("dry_run", [False, True])
def test_cli_exits_nonzero_when_no_bucket_and_rule_one_has_objects(client, no_r2, dry_run):
    """With no bucket, rule 1 keeps every row whose object it cannot delete.

    An unconfigured cron must be a failure that changes nothing in rule 1, not
    a pass that deletes rows and strands their resumes in the bucket.
    """
    _seed_one_of_each()

    code, payload = _cleanup(*(["--dry-run"] if dry_run else []))

    assert code != 0, payload
    assert "S3_BUCKET_NAME" in payload["r2_unconfigured"]
    assert _db_state()[0] == ["ret-fresh", "ret-gone"]
    if dry_run:
        assert payload["would"]["intake_objects"]["count"] == 1
    else:
        assert payload["abandoned_intakes_deleted"] == 0
        assert payload["r2_objects_left_unconfigured"] == 1


def test_cli_exits_nonzero_when_no_bucket_even_with_rule_one_idle(client, no_r2):
    """Rule 3's work is only knowable by listing the bucket, so it always has some."""
    _make_user_in_context()

    code, payload = _cleanup()

    assert code != 0, payload
    assert payload["abandoned_intakes_deleted"] == 0
    assert "not configured" in payload["orphan_sweep_skipped"]


def test_cli_exits_nonzero_without_crashing_when_credentials_are_missing(
    client, no_r2, monkeypatch
):
    """A bucket name with no credentials: rows kept, JSON still printed, exit 1."""
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    _seed_one_of_each()

    code, payload = _cleanup()

    assert code != 0
    assert payload is not None, "the pass crashed instead of reporting"
    assert "S3_ENDPOINT_URL" in payload["r2_unconfigured"]
    assert payload["r2_delete_failures"] == 1
    assert "not configured" in payload["orphan_sweep_skipped"]
    # The stale row stays until its object can be deleted with it.
    assert _db_state()[0] == ["ret-fresh", "ret-gone"]


class _UnreachableS3(_RecordingS3):
    """R2 that answers deletes but whose listing fails like a dead endpoint."""

    def paginate(self, Bucket, Prefix):
        from botocore.exceptions import EndpointConnectionError

        raise EndpointConnectionError(endpoint_url="https://r2.invalid")


def test_cli_storage_error_in_the_sweep_still_reports_and_exits_nonzero(client, r2):
    """Rules 1-2 have committed by the time rule 3 lists; their summary must survive."""
    seeded = _seed_one_of_each()
    r2["fake"] = _UnreachableS3(seeded.objects)

    code, payload = _cleanup()

    assert code != 0
    assert payload is not None, "the pass crashed instead of reporting"
    assert payload["orphan_sweep_skipped"] == "storage error: EndpointConnectionError"
    assert payload["abandoned_intakes_deleted"] == 1
    assert payload["audit_rows_minimized"] == 1


def test_cli_empty_database_is_not_a_clean_pass(client, r2):
    """A cron pointed at an empty database is pointed at the wrong one."""
    r2["fake"] = _RecordingS3({})

    code, payload = _cleanup()

    assert code != 0, payload
    assert payload["orphan_sweep_skipped"] == "empty database"
