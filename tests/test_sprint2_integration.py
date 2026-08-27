"""Sprint 2 end-to-end integration smoke test.

Walks the full happy path in a single sequential test:
  1. Anonymous user completes Work Pulse Lite — POST /api/work-pulse/lite-lite/result
  2. User registers, confirms email, and logs in
  3. WPLL data saved to account — POST /api/intake/save-to-account
  4. User completes Work Pulse — POST /api/work-pulse/submit
  5. GET /api/profile returns both completion flags as True

All OpenAI calls are mocked. All DB operations run against the real (SQLite) test DB.
"""

import json
import pytest
from unittest.mock import MagicMock


WPLL_ANSWERS = [
    {"question_id": "wpll-q1", "option_id": "wpll-q1-c"},
    {"question_id": "wpll-q2", "option_id": "wpll-q2-d"},
    {"question_id": "wpll-q3", "option_id": "wpll-q3-a"},
    {"question_id": "wpll-q4", "option_id": "wpll-q4-b"},
    {"question_id": "wpll-q5", "option_id": "wpll-q5-a"},
]

WP_ANSWERS = [
    {"question_id": f"wp-q{i}", "option_id": f"wp-q{i}-a"}
    for i in range(1, 13)
]

_WPLL_LLM_PAYLOAD = {"insight_text": "Your work pattern shows clear fragmentation signals."}
_WP_LLM_PAYLOAD = {
    "narrative": (
        "You bring deliberate focus to complex problems.\n\n"
        "You need genuine recovery time after intense output."
    ),
    "emerging_signals": [
        {"title": "Focus-Driven", "description": "You work best in sustained, uninterrupted blocks."},
    ],
    "archetype": "Deep Work Specialist",
    "archetype_description": (
        "You build momentum through sustained, self-directed effort. "
        "Environments with clear expectations and minimal interruption bring out your strongest output."
    ),
}


def _patch_openai(monkeypatch, response_payload: dict):
    """Replace _get_openai_client with a mock that returns response_payload as JSON."""
    import app as app_module
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(response_payload)
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)


def _noop(*_args, **_kwargs):
    return None


def test_sprint2_full_happy_path(client, monkeypatch):
    """Full Sprint 2 flow: anonymous WPLL → register → save → WP submit → profile complete."""
    import app as app_module
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    # ── Step 1: anonymous WPLL result ────────────────────────────────────────
    _patch_openai(monkeypatch, _WPLL_LLM_PAYLOAD)

    wpll_res = client.post(
        "/api/v1/assessments/wpll/submissions",
        json={"answers": WPLL_ANSWERS},
    )
    assert wpll_res.status_code == 200
    wpll_body = wpll_res.get_json()
    assert isinstance(wpll_body["insight_text"], str) and len(wpll_body["insight_text"]) > 0
    assert len(wpll_body["locked_sections"]) == 3

    captured_insight = wpll_body["insight_text"]

    # ── Step 2: register, confirm, login ─────────────────────────────────────
    email, password = "sprint2@example.com", "Sprint2Pass1!"

    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Sprint Two", "terms_accepted": True},
    )
    assert reg_res.status_code == 201

    from app import app
    from model import User, db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        db.session.commit()

    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200
    csrf = login_res.get_json()["csrfToken"]

    # Both flags are False before any intake data is saved
    flags_initial = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags_initial["wpll_completed"] is False
    assert flags_initial["wpl_completed"] is False

    # ── Step 3: save WPLL data to account ───────────────────────────────────
    save_res = client.post(
        "/api/v1/intake/claims",
        json={
            "mode": "session",
            "selected_statement_ids": ["dir-1", "sus-2"],
            "wpll_answers": WPLL_ANSWERS,
            "wpll_insight_text": captured_insight,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert save_res.status_code == 200
    assert save_res.get_json()["wpll_completed"] is True

    flags_after_save = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags_after_save["wpll_completed"] is True
    assert flags_after_save["wpl_completed"] is False  # WP not done yet

    # ── Step 4: complete Work Pulse ──────────────────────────────────────────
    _patch_openai(monkeypatch, _WP_LLM_PAYLOAD)

    wp_res = client.post(
        "/api/v1/assessments/work_pulse/submissions",
        json={"answers": WP_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert wp_res.status_code == 200
    wp_body = wp_res.get_json()
    assert wp_body["archetype"] == "Deep Work Specialist"
    assert isinstance(wp_body["narrative"], str) and len(wp_body["narrative"]) > 0
    assert len(wp_body["emerging_signals"]) >= 1

    # ── Step 5: profile reflects both flags True ──────────────────────────────
    flags_final = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags_final["wpl_completed"] is True
    assert flags_final["wpll_completed"] is True

    # Confirm intake row holds full data for both phases
    from model import UserIntake
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        intake = UserIntake.query.filter_by(user_id=user.id).first()
        assert intake is not None
        assert intake.wpll_answers == WPLL_ANSWERS
        assert intake.wpl_answers == WP_ANSWERS
        assert intake.wpll_completed_at is not None
        assert intake.wpl_completed_at is not None
