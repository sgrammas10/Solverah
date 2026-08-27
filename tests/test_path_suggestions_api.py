"""Tests for GET /api/intelligence/path-suggestions."""
import os
import pytest
from unittest.mock import MagicMock

import backend.services.path_scoring as path_scoring_mod
import backend.services.path_narrative as path_narrative_mod
from backend.services.path_scoring import ScoredPath
from backend.services.path_narrative import PathSuggestion

# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------

SCORED_PATHS = [
    ScoredPath(
        onet_code="11-2021.00",
        title="Marketing Managers",
        score=0.82,
        overlapping_skills=["Communication"],
    ),
    ScoredPath(
        onet_code="11-3021.00",
        title="IT Managers",
        score=0.65,
        overlapping_skills=[],
    ),
]

PATH_SUGGESTIONS = [
    PathSuggestion(
        onet_code="11-2021.00",
        title="Marketing Managers",
        why_text="Your skills align well with marketing leadership.",
        profile_dimensions=["Matches your Creative Drive archetype", "Builds on Communication skills"],
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="paths@example.com", password="Strongpass1!"):
    import app as app_module
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Path User", "role": "job-seeker", "terms_accepted": True},
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


def _set_profile(email: str, extra: dict):
    from app import app
    from model import User, db
    from solverah.repositories import profile_repository
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile_repository.update_document(
            user.id, lambda existing: {**existing, **extra}
        )
        db.session.commit()


def _mock_scoring(monkeypatch):
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    mock_score = MagicMock(return_value=SCORED_PATHS)
    mock_narrative = MagicMock(return_value=PATH_SUGGESTIONS)
    monkeypatch.setattr(path_scoring_mod, "score_paths", mock_score)
    monkeypatch.setattr(path_narrative_mod, "generate_narratives", mock_narrative)
    return mock_score, mock_narrative


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_path_cache():
    from solverah.services import path_cache
    path_cache.clear()
    yield
    path_cache.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_unauthenticated_returns_401(client):
    resp = client.get("/api/v1/me/path-suggestions")
    assert resp.status_code == 401


def test_missing_career_status_returns_400(client, monkeypatch):
    _register_and_login(client, monkeypatch)
    resp = client.get("/api/v1/me/path-suggestions")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "career_status_not_set"


def test_happy_path_returns_correct_shape(client, monkeypatch):
    _register_and_login(client, monkeypatch)
    _set_profile("paths@example.com", {
        "career_status": "employed",
        "skills": ["Communication", "Python"],
        "skill_levels": {"Communication": "advanced", "Python": "intermediate"},
        "experience": [{"position": "Software Engineer", "company": "Acme"}],
        "manager_match_result": {"archetype": "The Autonomist", "dimension_scores": {}},
    })
    mock_score, mock_narrative = _mock_scoring(monkeypatch)

    resp = client.get("/api/v1/me/path-suggestions")
    assert resp.status_code == 200
    body = resp.get_json()

    assert "suggestions" in body
    assert "career_status" in body
    assert "generated_at" in body
    assert body["career_status"] == "employed"
    assert body["generated_at"].endswith("Z")

    assert len(body["suggestions"]) == 1
    s = body["suggestions"][0]
    assert s["onet_code"] == "11-2021.00"
    assert s["title"] == "Marketing Managers"
    assert isinstance(s["why_text"], str) and len(s["why_text"]) > 0
    assert isinstance(s["profile_dimensions"], list) and len(s["profile_dimensions"]) >= 1
    assert s["match_score"] == pytest.approx(0.82)

    mock_score.assert_called_once()
    mock_narrative.assert_called_once()


def test_second_call_returns_cached_response(client, monkeypatch):
    _register_and_login(client, monkeypatch, email="paths_cache@example.com")
    _set_profile("paths_cache@example.com", {"career_status": "between_jobs"})
    mock_score, _ = _mock_scoring(monkeypatch)

    resp1 = client.get("/api/v1/me/path-suggestions")
    assert resp1.status_code == 200

    resp2 = client.get("/api/v1/me/path-suggestions")
    assert resp2.status_code == 200

    assert mock_score.call_count == 1
    assert resp1.get_json() == resp2.get_json()
