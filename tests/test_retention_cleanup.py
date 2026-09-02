"""Tests for the orphaned-object sweep (retention_cleanup rule 3).

Objects from presigned uploads that were never finalized have no database row,
so rules 1-2 -- which walk rows -- can never see them. Before rule 3 existed
they accumulated in R2 forever. These tests pin the two things that make a
sweep safe: it deletes what nothing references, and it never deletes anything
that is still referenced or still inside the upload grace window.
"""

import datetime

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
