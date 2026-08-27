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
