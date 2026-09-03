"""Tests for /api/account/export and /api/account/delete (account_lifecycle.py).

Verifies the D-16 reconciliation decided 2026-08-20: deletion erases every
personal field but RETAINS assessment response rows de-identified via the
tombstoned user row. Each test is written to fail if its guarantee is removed
(operating-policy red rule 7).
"""

import pytest


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="lifecycle@example.com",
                        password="Strongpass1!"):

    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Lifecycle User",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        user_id = user.id

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"], user_id


def _seed_assessment_rows(user_id):
    """Plant a sitting so retention-after-deletion is actually testable.

    Written through assessment_store, not by constructing rows here. D-01 keeps the
    person-side tables off-limits outside that module (tests/test_employer_visibility.py),
    and a test that hand-builds the rows is also free to build ones the real write path
    cannot produce — which is how this file first missed the NOT NULL submission_id that
    persist_submission has always supplied.
    """
    from app import app
    from assessment_form import ScoredSubmission
    from assessment_store import persist_submission
    from model import db

    with app.app_context():
        persist_submission(db, user_id, ScoredSubmission(
            form_version="v2-2026-08-18",
            scoring_key_version="v2-2026-08-18+mean_pole",
            scores={"autonomy": 0.75},
            choices={"au1v2": "A"},
            confidences={"autonomy": 1.0},
        ))
        db.session.commit()


def _person_side(user_id):
    """What the person-side tables still hold, read through the sanctioned doorway."""
    from app import app
    from assessment_store import export_person_side

    with app.app_context():
        return export_person_side(user_id)


# ── Export ───────────────────────────────────────────────────────────────────

def test_export_returns_all_identified_data(client, monkeypatch):
    csrf, user_id = _register_and_login(client, monkeypatch)
    _seed_assessment_rows(user_id)

    res = client.get("/api/v1/me/export")
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["account"]["email"] == "lifecycle@example.com"
    assert payload["assessment_answers"][0]["item_id"] == "au1v2"
    assert payload["dimension_scores"][0]["dimension"] == "autonomy"


def test_export_requires_auth(client):
    res = client.get("/api/v1/me/export")
    assert res.status_code == 401


# ── Delete ───────────────────────────────────────────────────────────────────

def test_delete_requires_explicit_confirmation(client, monkeypatch):
    csrf, user_id = _register_and_login(client, monkeypatch)

    res = client.delete("/api/v1/me", json={},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 400

    from app import app
    from model import User, db

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.email == "lifecycle@example.com"  # untouched


def test_delete_tombstones_user_and_purges_pii(client, monkeypatch):
    csrf, user_id = _register_and_login(client, monkeypatch)
    _seed_assessment_rows(user_id)

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        user = db.session.get(User, user_id)
        # Personal fields gone
        assert user.email == f"deleted-{user_id}@tombstone.invalid"
        assert user.name is None
        # The profile document is the tombstone and nothing else, which also
        # means no experience, education, skill or resume rows survive -- the
        # write path rebuilds those from the document it is handed.
        assert set(profile_repository.load_document(user_id).keys()) == {"deleted_at"}
        assert user.confirmation_token is None
        assert user.reset_token is None
        # The old password can never verify again (not a bcrypt hash at all)
        assert user.password_hash.startswith("!deleted!")

    # THE decided reconciliation: research rows survive, de-identified
    surviving = _person_side(user_id)
    assert len(surviving["answers"]) == 1
    assert len(surviving["dimension_scores"]) == 1


def test_delete_removes_dependent_personal_rows(client, monkeypatch):
    csrf, user_id = _register_and_login(client, monkeypatch)

    from app import app
    from model import JobRecommendation, UserIntake, db

    with app.app_context():
        db.session.add(JobRecommendation(user_id=user_id, job_id=1, score=0.9))
        db.session.add(UserIntake(user_id=user_id, selected_statement_ids=[],
                                  wpll_answers=[]))
        db.session.commit()

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    with app.app_context():
        assert JobRecommendation.query.filter_by(user_id=user_id).count() == 0
        assert UserIntake.query.filter_by(user_id=user_id).count() == 0


def test_deleted_account_cannot_login(client, monkeypatch):
    csrf, user_id = _register_and_login(client, monkeypatch)

    client.delete("/api/v1/me", json={"confirm": "DELETE"},
                headers={"X-CSRF-TOKEN": csrf})

    res = client.post("/api/v1/auth/login", json={
        "email": "lifecycle@example.com", "password": "Strongpass1!"})
    assert res.status_code in (400, 401, 404)


# ── The legacy blob (SECURITY_AUDIT_2026-09 4.1) ─────────────────────────────
#
# `users.profile_data` is the pre-Phase-2a copy of the profile document. Nothing
# reads or writes it any more, which is precisely how it went unscrubbed: the
# deletion path was rewritten around the tables that replaced it, and the column
# it was decomposed *from* was left holding everything. Every account created
# before Phase 2a still has one, so this is not a hypothetical row.
#
# These are destructive-path tests, so they assert the blast radius in both
# directions: the deleting user's blob is gone, and nobody else's is touched.

#: A stand-in for what a pre-decomposition account actually holds. Written
#: straight to the column because no code path writes it any more -- which is
#: the point.
_LEGACY_BLOB = {
    "firstName": "Legacy",
    "lastName": "User",
    "phone": "+1-555-0100",
    "linkedinUrl": "https://linkedin.com/in/legacy-user",
    "resumeText": "Legacy User -- Senior Widget Engineer at Acme, 2019-2024",
    "experience": [{"id": 1, "company": "Acme", "position": "Engineer"}],
}


def _seed_legacy_blob(user_id, blob=None):
    from app import app
    from model import User, db

    with app.app_context():
        user = db.session.get(User, user_id)
        user.profile_data = dict(blob if blob is not None else _LEGACY_BLOB)
        db.session.commit()


def _legacy_blob(user_id):
    from app import app
    from model import User, db

    with app.app_context():
        return db.session.get(User, user_id).profile_data


def test_delete_scrubs_the_legacy_profile_data_blob(client, monkeypatch):
    """Deletion empties `users.profile_data`, not just the tables that replaced it.

    Before this, a tombstoned pre-Phase-2a account kept its phone number,
    LinkedIn URL, parsed resume text and employment history verbatim in the row
    the response calls scrubbed.
    """
    csrf, user_id = _register_and_login(client, monkeypatch)
    _seed_legacy_blob(user_id)
    assert _legacy_blob(user_id)["phone"] == "+1-555-0100"  # the fixture took

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                        headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    assert _legacy_blob(user_id) == {}


def test_delete_scrubs_only_the_deleting_users_blob(client, monkeypatch):
    """The scrub is one row wide.

    A column-level UPDATE with a missing or wrong predicate would empty the
    legacy profile of every account in the table, and there is no undo for that
    -- so the bystander is asserted, not assumed.
    """
    _, bystander_id = _register_and_login(
        client, monkeypatch, email="bystander@example.com"
    )
    _seed_legacy_blob(bystander_id, {"firstName": "Bystander", "phone": "+1-555-0199"})

    # Logging in as the second account replaces the session cookie, so the
    # delete below is unambiguously the second user's.
    csrf, user_id = _register_and_login(client, monkeypatch)
    _seed_legacy_blob(user_id)

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                        headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    assert _legacy_blob(user_id) == {}
    assert _legacy_blob(bystander_id) == {
        "firstName": "Bystander",
        "phone": "+1-555-0199",
    }

    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        bystander = db.session.get(User, bystander_id)
        assert bystander.email == "bystander@example.com"
        assert bystander.status != "deleted"
        # The bystander's new-format profile is intact too: the scrub reaches
        # one column on one row and nothing downstream of it.
        assert "deleted_at" not in profile_repository.load_document(bystander_id)


def test_the_new_format_profile_tables_keep_their_existing_deletion_path(
    client, monkeypatch
):
    """Scrubbing the legacy column changed nothing about how Phase 2a rows die.

    They are still erased by rewriting the profile document -- one write path,
    so a field added to the profile later is erased without anyone remembering
    to come back. This asserts the child rows themselves, which the document
    assertion in `test_delete_tombstones_user_and_purges_pii` reaches only
    through `load_document`.
    """
    csrf, user_id = _register_and_login(client, monkeypatch)
    _seed_legacy_blob(user_id)

    from app import app
    from model import ProfileEducation, ProfileExperience, ProfileSkill, db
    from solverah.repositories import profile_repository

    with app.app_context():
        profile_repository.update_document(
            user_id,
            lambda existing: {
                **existing,
                "experience": [
                    {"id": 1, "company": "Acme", "position": "Engineer",
                     "startDate": "", "endDate": "2024", "description": ""}
                ],
                "education": [
                    {"id": 1, "institution": "State U", "degree": "BSc",
                     "startDate": "", "endDate": "", "gpa": "", "description": ""}
                ],
                "skills": ["widgets", "sprockets"],
            },
        )
        db.session.commit()

        assert ProfileExperience.query.filter_by(user_id=user_id).count() == 1
        assert ProfileEducation.query.filter_by(user_id=user_id).count() == 1
        assert ProfileSkill.query.filter_by(user_id=user_id).count() == 2

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                        headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    with app.app_context():
        assert ProfileExperience.query.filter_by(user_id=user_id).count() == 0
        assert ProfileEducation.query.filter_by(user_id=user_id).count() == 0
        assert ProfileSkill.query.filter_by(user_id=user_id).count() == 0
        assert set(profile_repository.load_document(user_id).keys()) == {"deleted_at"}


def test_the_blob_scrub_is_part_of_the_tombstone_not_a_later_write(
    client, monkeypatch
):
    """One unit of work, so there is no window in which the row is half-deleted.

    `tombstone_user` does not commit -- its caller owns the transaction -- and
    the scrub has to live inside that same boundary. A scrub committed
    separately is a scrub that a crash in between turns into a deleted account
    still holding a complete profile, which nothing would ever look at again to
    notice. Rolling back is what demonstrates it: if the two were in one
    transaction, undoing it undoes both.
    """
    _, user_id = _register_and_login(client, monkeypatch)
    _seed_legacy_blob(user_id)

    from app import app
    from model import User, db
    from solverah.repositories import account_repository

    with app.app_context():
        user = db.session.get(User, user_id)
        account_repository.tombstone_user(
            user,
            tombstone_domain="tombstone.invalid",
            now_iso="2026-09-03T00:00:00",
            dead_password="!deleted!",
        )

        # Uncommitted, and already both.
        assert user.profile_data == {}
        assert user.status == "deleted"

        db.session.rollback()

        restored = db.session.get(User, user_id)
        assert restored.status != "deleted"
        assert restored.profile_data["phone"] == "+1-555-0100"
