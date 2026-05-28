"""Tests for POST /api/intake/save-to-account and the updated GET /api/profile flags."""

import json
import pytest

WPLL_ANSWERS = [
    {"question_id": "wpll-q1", "option_id": "wpll-q1-c"},
    {"question_id": "wpll-q2", "option_id": "wpll-q2-d"},
    {"question_id": "wpll-q3", "option_id": "wpll-q3-a"},
    {"question_id": "wpll-q4", "option_id": "wpll-q4-b"},
    {"question_id": "wpll-q5", "option_id": "wpll-q5-a"},
]

STATEMENT_IDS = ["stmt-1", "stmt-2", "stmt-3"]


def register_and_login(client, email="test@example.com", password="TestPass1!@"):
    client.post(
        "/api/register",
        json={"email": email, "password": password, "name": "Test", "role": "job-seeker"},
    )
    from model import db, User
    from app import app
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        db.session.commit()
    return client.post("/api/login", json={"email": email, "password": password})


def test_save_to_account_creates_intake_row(client):
    register_and_login(client)
    res = client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": STATEMENT_IDS,
            "wpll_answers": WPLL_ANSWERS,
            "wpll_insight_text": "Some insight text.",
        },
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["message"] == "Intake saved"
    assert body["wpll_completed"] is True


def test_save_to_account_upserts_on_second_call(client):
    register_and_login(client)
    client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": ["stmt-1"],
            "wpll_answers": WPLL_ANSWERS,
            "wpll_insight_text": "First insight.",
        },
    )
    res = client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": ["stmt-2", "stmt-3"],
            "wpll_answers": WPLL_ANSWERS[:3],
            "wpll_insight_text": "Updated insight.",
        },
    )
    assert res.status_code == 200

    from model import UserIntake, User, db
    from app import app
    with app.app_context():
        user = User.query.filter_by(email="test@example.com").first()
        rows = UserIntake.query.filter_by(user_id=user.id).all()
        assert len(rows) == 1
        assert rows[0].selected_statement_ids == ["stmt-2", "stmt-3"]


def test_save_to_account_preserves_wpl_completed_at_on_upsert(client):
    import datetime
    register_and_login(client)
    client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": STATEMENT_IDS,
            "wpll_answers": WPLL_ANSWERS,
        },
    )

    from model import UserIntake, User, db
    from app import app
    sentinel = datetime.datetime(2025, 1, 1, 0, 0, 0)
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


def test_save_to_account_rejects_too_many_answers(client):
    register_and_login(client)
    too_many = WPLL_ANSWERS + [{"question_id": "wpll-q1", "option_id": "wpll-q1-a"}]
    res = client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": STATEMENT_IDS,
            "wpll_answers": too_many,
        },
    )
    assert res.status_code == 400


def test_save_to_account_accepts_empty_answers(client):
    register_and_login(client)
    res = client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": [],
            "wpll_answers": [],
        },
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["wpll_completed"] is False


def test_profile_response_includes_wpl_flags(client):
    register_and_login(client)

    profile_before = client.get("/api/profile")
    assert profile_before.status_code == 200
    before = profile_before.get_json()
    assert before["wpll_completed"] is False
    assert before["wpl_completed"] is False

    client.post(
        "/api/intake/save-to-account",
        json={
            "selected_statement_ids": STATEMENT_IDS,
            "wpll_answers": WPLL_ANSWERS,
        },
    )

    profile_after = client.get("/api/profile")
    assert profile_after.status_code == 200
    after = profile_after.get_json()
    assert after["wpll_completed"] is True
    assert after["wpl_completed"] is False
