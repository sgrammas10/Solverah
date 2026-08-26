"""Tests for POST /api/intake/save-to-account and the updated GET /api/profile flags."""

import datetime
import pytest

WPLL_ANSWERS = [
    {"question_id": "wpll-q1", "option_id": "wpll-q1-c"},
    {"question_id": "wpll-q2", "option_id": "wpll-q2-d"},
    {"question_id": "wpll-q3", "option_id": "wpll-q3-a"},
    {"question_id": "wpll-q4", "option_id": "wpll-q4-b"},
    {"question_id": "wpll-q5", "option_id": "wpll-q5-a"},
]

STATEMENT_IDS = ["stmt-1", "stmt-2", "stmt-3"]


def _noop(*_args, **_kwargs):
    return None


def register_and_login(client, monkeypatch, email="test@example.com", password="Strongpass1!"):
    """Register a user via HTTP (with email send stubbed), confirm, log in, return csrf token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/register",
        json={"email": email, "password": password, "name": "Test", "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import db, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def test_save_to_account_creates_intake_row(client, monkeypatch):
    csrf = register_and_login(client, monkeypatch)
    res = client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": STATEMENT_IDS,
            "wpll_answers": WPLL_ANSWERS,
            "wpll_insight_text": "Some insight text.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["message"] == "Intake saved"
    assert body["wpll_completed"] is True


def test_save_to_account_upserts_on_second_call(client, monkeypatch):
    csrf = register_and_login(client, monkeypatch)

    client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": ["stmt-1"],
            "wpll_answers": WPLL_ANSWERS,
            "wpll_insight_text": "First insight.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    res = client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": ["stmt-2", "stmt-3"],
            "wpll_answers": WPLL_ANSWERS[:3],
            "wpll_insight_text": "Updated insight.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 200

    from model import UserIntake, User
    from app import app
    with app.app_context():
        user = User.query.filter_by(email="test@example.com").first()
        rows = UserIntake.query.filter_by(user_id=user.id).all()
        assert len(rows) == 1
        assert rows[0].selected_statement_ids == ["stmt-2", "stmt-3"]


def test_save_to_account_preserves_wpl_completed_at_on_upsert(client, monkeypatch):
    csrf = register_and_login(client, monkeypatch)

    client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": STATEMENT_IDS,
            "wpll_answers": WPLL_ANSWERS,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    sentinel = datetime.datetime(2025, 1, 1, 0, 0, 0)
    from model import UserIntake, User, db
    from app import app
    with app.app_context():
        user = User.query.filter_by(email="test@example.com").first()
        intake = UserIntake.query.filter_by(user_id=user.id).first()
        intake.wpl_completed_at = sentinel
        db.session.commit()

    client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": STATEMENT_IDS,
            "wpll_answers": WPLL_ANSWERS,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    with app.app_context():
        user = User.query.filter_by(email="test@example.com").first()
        intake = UserIntake.query.filter_by(user_id=user.id).first()
        assert intake.wpl_completed_at == sentinel


def test_save_to_account_requires_auth(client):
    res = client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": STATEMENT_IDS,
            "wpll_answers": WPLL_ANSWERS,
        },
    )
    assert res.status_code == 401


def test_save_to_account_rejects_too_many_answers(client, monkeypatch):
    csrf = register_and_login(client, monkeypatch)
    too_many = WPLL_ANSWERS + [{"question_id": "wpll-q1", "option_id": "wpll-q1-a"}]
    res = client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": STATEMENT_IDS,
            "wpll_answers": too_many,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 400


def test_save_to_account_accepts_empty_answers(client, monkeypatch):
    csrf = register_and_login(client, monkeypatch)
    res = client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": [],
            "wpll_answers": [],
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 200
    assert res.get_json()["wpll_completed"] is False


def test_profile_response_includes_wpl_flags(client, monkeypatch):
    csrf = register_and_login(client, monkeypatch)

    before = client.get("/api/profile").get_json()
    assert before["wpll_completed"] is False
    assert before["wpl_completed"] is False

    client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": STATEMENT_IDS,
            "wpll_answers": WPLL_ANSWERS,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    after = client.get("/api/profile").get_json()
    assert after["wpll_completed"] is True
    assert after["wpl_completed"] is False
