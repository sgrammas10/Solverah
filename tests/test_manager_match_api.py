"""Tests for POST /api/manager-match/submit and GET /api/manager-match/results."""

import json
import pytest
from unittest.mock import MagicMock


MM_ANSWERS = [
    {"question_id": f"mm-q{i}", "choice": "a" if i % 2 == 0 else "b"}
    for i in range(1, 16)
]

VALID_LLM_RESPONSE = {
    "narrative": (
        "You need clear direction and regular touchpoints to do your best work.\n\n"
        "Your preference for structured feedback reveals a pattern of wanting confirmation "
        "at each stage rather than waiting for end-of-project reviews.\n\n"
        "When these conditions are met, you produce output with high consistency."
    ),
    "what_to_look_for": [
        "Ask how often the team holds 1:1s and what format they follow",
        "Ask whether the manager sets explicit success criteria before a project begins",
        "Probe for how feedback is typically delivered on the team",
        "Ask about onboarding — how long until new hires have full task ownership",
    ],
    "red_flags": [
        "A manager who equates autonomy with competence and leaves you without direction",
        "An org where check-ins are seen as micromanagement rather than support",
        "Roles with ambiguous scope where success is only defined retrospectively",
    ],
    "archetype_description": (
        "You operate at your peak when the expectations are clear and your manager "
        "is invested in your progress. Environments with frequent feedback loops and "
        "defined ownership allow you to build momentum without second-guessing direction."
    ),
}


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="mm@example.com", password="Strongpass1!"):
    import app as app_module
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "MM User", "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
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
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)
    return mock_client


# ── Happy path ────────────────────────────────────────────────────────────────

def test_submit_happy_path(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    res = client.post(
        "/api/v1/assessments/manager_match/submissions",
        json={"answers": MM_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 200
    body = res.get_json()

    assert "archetype" in body
    assert "dimension_scores" in body
    assert isinstance(body["narrative"], str) and len(body["narrative"]) > 0
    assert isinstance(body["what_to_look_for"], list) and len(body["what_to_look_for"]) >= 1
    assert isinstance(body["red_flags"], list) and len(body["red_flags"]) >= 1
    assert isinstance(body["archetype_description"], str) and len(body["archetype_description"]) > 0


def test_submit_persists_to_the_profile_document(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="mm_persist@example.com")
    _mock_openai(monkeypatch)

    client.post(
        "/api/v1/assessments/manager_match/submissions",
        json={"answers": MM_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )

    from app import app
    from model import User
    from solverah.repositories import profile_repository
    with app.app_context():
        user = User.query.filter_by(email="mm_persist@example.com").first()
        document = profile_repository.load_document(user.id)
        assert "manager_match_result" in document
        stored = document["manager_match_result"]
        assert stored["archetype"] is not None
        assert "narrative" in stored


# ── Validation errors ─────────────────────────────────────────────────────────

def test_submit_wrong_answer_count(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="mm_short@example.com")
    _mock_openai(monkeypatch)

    res = client.post(
        "/api/v1/assessments/manager_match/submissions",
        json={"answers": MM_ANSWERS[:14]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 400
    assert "15" in res.get_json()["error"]


def test_submit_invalid_choice_value(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="mm_bad@example.com")
    _mock_openai(monkeypatch)

    bad_answers = [dict(a) for a in MM_ANSWERS]
    bad_answers[2]["choice"] = "x"

    res = client.post(
        "/api/v1/assessments/manager_match/submissions",
        json={"answers": bad_answers},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 400


def test_submit_malformed_llm_response(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="mm_malformed@example.com")
    malformed = {k: v for k, v in VALID_LLM_RESPONSE.items() if k != "red_flags"}
    _mock_openai(monkeypatch, response_json=malformed)

    res = client.post(
        "/api/v1/assessments/manager_match/submissions",
        json={"answers": MM_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert res.status_code == 500


def test_submit_unauthenticated(client):
    res = client.post(
        "/api/v1/assessments/manager_match/submissions",
        json={"answers": MM_ANSWERS},
    )
    assert res.status_code == 401


# ── GET results ───────────────────────────────────────────────────────────────

def test_get_results_happy_path(client, monkeypatch):
    from solverah.domain import auth as auth_domain

    csrf = _register_and_login(client, monkeypatch, email="mm_get@example.com")

    from app import app
    from model import User, db
    from solverah.repositories import assessment_repository
    from solverah.services import assessment_service
    with app.app_context():
        user = User.query.filter_by(email="mm_get@example.com").first()
        # Seeded as a submission since Phase 2d; it was a key in the profile
        # document before. Written through the repository rather than by
        # constructing the row here: `open_current` is the write doorway, so a
        # test cannot seed a row the application could not produce -- and the
        # form-version registration the foreign key needs happens on the way in.
        submission = assessment_repository.open_current(
            user.id, "manager_match", assessment_service.CLIENT_FORM_VERSION
        )
        submission.result = {"archetype": "The Autonomist", "narrative": "test"}
        submission.narrative = "test"
        submission.status = "scored"
        submission.completed_at = submission.scored_at = auth_domain.utcnow()
        db.session.commit()

    res = client.get("/api/v1/me/assessments/manager_match/result")
    assert res.status_code == 200
    body = res.get_json()
    assert body["archetype"] == "The Autonomist"
    assert body["narrative"] == "test"


def test_get_results_no_result(client, monkeypatch):
    _register_and_login(client, monkeypatch, email="mm_empty@example.com")

    res = client.get("/api/v1/me/assessments/manager_match/result")
    assert res.status_code == 404
    assert "No ManagerMatch result found" in res.get_json()["error"]
