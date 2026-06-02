"""Tests for POST /api/work-pulse/submit."""

import json
import pytest
from unittest.mock import MagicMock


WP_ANSWERS = [
    {"question_id": "wp-q1",  "option_id": "wp-q1-b"},
    {"question_id": "wp-q2",  "option_id": "wp-q2-a"},
    {"question_id": "wp-q3",  "option_id": "wp-q3-c"},
    {"question_id": "wp-q4",  "option_id": "wp-q4-b"},
    {"question_id": "wp-q5",  "option_id": "wp-q5-c"},
    {"question_id": "wp-q6",  "option_id": "wp-q6-a"},
    {"question_id": "wp-q7",  "option_id": "wp-q7-b"},
    {"question_id": "wp-q8",  "option_id": "wp-q8-c"},
    {"question_id": "wp-q9",  "option_id": "wp-q9-a"},
    {"question_id": "wp-q10", "option_id": "wp-q10-b"},
    {"question_id": "wp-q11", "option_id": "wp-q11-a"},
    {"question_id": "wp-q12", "option_id": "wp-q12-b"},
]

VALID_LLM_RESPONSE = {
    "narrative": (
        "You bring deep focus to your work when conditions allow it.\n\n"
        "Recovery is a real need for you, not a luxury.\n\n"
        "Your autonomy matters — being told exactly how to do something costs you."
    ),
    "emerging_signals": [
        {"title": "Deep Focus Seeker", "description": "You show strong signs of needing uninterrupted time to reach your best work."},
        {"title": "Autonomy Driven", "description": "You prefer to own the how, not just the what."},
    ],
    "archetype": "Structured Deep Thinker",
}


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="wp@example.com", password="Strongpass1!"):
    import app as app_module
    monkeypatch.setattr(app_module, "send_confirmation_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    client.post(
        "/api/register",
        json={"email": email, "password": password, "name": "WP User", "role": "job-seeker"},
    )

    from app import app
    from model import User, db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def _mock_openai(monkeypatch, response_json=None, raise_exc=None):
    import app as app_module
    mock_client = MagicMock()
    if raise_exc is not None:
        mock_client.chat.completions.create.side_effect = raise_exc
    else:
        payload = response_json if response_json is not None else VALID_LLM_RESPONSE
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(payload)
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(app_module, "_get_openai_client", lambda: mock_client)
    return mock_client


# ── Happy path ───────────────────────────────────────────────────────────────

def test_submit_returns_narrative_signals_and_archetype(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    res = client.post(
        "/api/work-pulse/submit",
        json={"answers": WP_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert isinstance(body["narrative"], str) and len(body["narrative"]) > 0
    assert isinstance(body["emerging_signals"], list) and len(body["emerging_signals"]) >= 1
    assert all("title" in s and "description" in s for s in body["emerging_signals"])
    assert isinstance(body["archetype"], str) and len(body["archetype"]) > 0


def test_submit_persists_answers_and_narrative(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    client.post(
        "/api/work-pulse/submit",
        json={"answers": WP_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )

    from app import app
    from model import UserIntake, User
    with app.app_context():
        user = User.query.filter_by(email="wp@example.com").first()
        intake = UserIntake.query.filter_by(user_id=user.id).first()
        assert intake is not None
        assert intake.wpl_answers == WP_ANSWERS
        assert intake.wpl_narrative == VALID_LLM_RESPONSE["narrative"]
        assert intake.wpl_completed_at is not None


# ── Validation errors ────────────────────────────────────────────────────────

def test_submit_rejects_fewer_than_12_answers(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    res = client.post(
        "/api/work-pulse/submit",
        json={"answers": WP_ANSWERS[:5]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 400
    assert "12" in res.get_json()["error"]


def test_submit_rejects_more_than_12_answers(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    too_many = WP_ANSWERS + [{"question_id": "wp-q1", "option_id": "wp-q1-a"}]
    res = client.post(
        "/api/work-pulse/submit",
        json={"answers": too_many},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 400


def test_submit_rejects_missing_answers_key(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)

    res = client.post(
        "/api/work-pulse/submit",
        json={},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 400


# ── Auth ─────────────────────────────────────────────────────────────────────

def test_submit_requires_auth(client):
    res = client.post(
        "/api/work-pulse/submit",
        json={"answers": WP_ANSWERS},
    )
    assert res.status_code == 401


# ── LLM failure ──────────────────────────────────────────────────────────────

def test_submit_returns_500_on_llm_exception(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch, raise_exc=RuntimeError("OpenAI down"))

    res = client.post(
        "/api/work-pulse/submit",
        json={"answers": WP_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 500


def test_submit_does_not_set_wpl_completed_at_on_llm_failure(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch, raise_exc=RuntimeError("OpenAI down"))

    client.post(
        "/api/work-pulse/submit",
        json={"answers": WP_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )

    from app import app
    from model import UserIntake, User
    with app.app_context():
        user = User.query.filter_by(email="wp@example.com").first()
        intake = UserIntake.query.filter_by(user_id=user.id).first()
        # Intake row may or may not exist; if it does, wpl_completed_at must be None.
        if intake is not None:
            assert intake.wpl_completed_at is None


# ── Profile flag ─────────────────────────────────────────────────────────────

def test_profile_shows_wpl_completed_after_submit(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    before = client.get("/api/profile").get_json()
    assert before["wpl_completed"] is False

    client.post(
        "/api/work-pulse/submit",
        json={"answers": WP_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )

    after = client.get("/api/profile").get_json()
    assert after["wpl_completed"] is True


def test_submit_creates_intake_row_when_none_exists(client, monkeypatch):
    """Submitting WP answers should create a fresh UserIntake row when save-to-account
    was never called — no prior intake row should exist for this user."""
    csrf = _register_and_login(client, monkeypatch, email="fresh@example.com")
    _mock_openai(monkeypatch)

    from app import app
    from model import UserIntake, User
    with app.app_context():
        user = User.query.filter_by(email="fresh@example.com").first()
        assert UserIntake.query.filter_by(user_id=user.id).first() is None, \
            "Expected no intake row before submission"

    res = client.post(
        "/api/work-pulse/submit",
        json={"answers": WP_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email="fresh@example.com").first()
        intake = UserIntake.query.filter_by(user_id=user.id).first()
        assert intake is not None, "Intake row should have been created by submit"
        assert intake.wpl_answers == WP_ANSWERS
        assert intake.wpl_completed_at is not None
        # wpll fields must stay unset — save-to-account was never called
        assert intake.wpll_completed_at is None
        assert not intake.wpll_answers  # None or [] — never populated
