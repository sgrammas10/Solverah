"""Tests for POST /api/intelligence/path-preferences."""
import pytest


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_path_suggestions_api.py)
# ---------------------------------------------------------------------------

def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="prefs@example.com", password="Strongpass1!"):
    import app as app_module
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/register",
        json={"email": email, "password": password, "name": "Prefs User", "role": "job-seeker", "terms_accepted": True},
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


VALID_PREFS = {
    "move_intent": "adjacent",
    "seniority_intent": "move_up",
    "priority": "learning_growth",
}


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
    resp = client.post("/api/intelligence/path-preferences", json=VALID_PREFS)
    assert resp.status_code == 401


def test_happy_path_returns_200(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    resp = client.post(
        "/api/intelligence/path-preferences",
        json=VALID_PREFS,
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "Preferences saved"


def test_preferences_persisted_in_profile_data(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    client.post(
        "/api/intelligence/path-preferences",
        json=VALID_PREFS,
        headers={"X-CSRF-TOKEN": csrf},
    )

    from app import app
    from model import User
    from solverah.services import path_cache
    with app.app_context():
        user = User.query.filter_by(email="prefs@example.com").first()
        prefs = (user.profile_data or {}).get("path_preferences")
    assert prefs == VALID_PREFS


def test_invalid_move_intent_returns_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    resp = client.post(
        "/api/intelligence/path-preferences",
        json={**VALID_PREFS, "move_intent": "sideways"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400
    assert "move_intent" in resp.get_json()["error"]


def test_invalid_seniority_intent_returns_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    resp = client.post(
        "/api/intelligence/path-preferences",
        json={**VALID_PREFS, "seniority_intent": "unknown"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400
    assert "seniority_intent" in resp.get_json()["error"]


def test_invalid_priority_returns_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    resp = client.post(
        "/api/intelligence/path-preferences",
        json={**VALID_PREFS, "priority": "vibes"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400
    assert "priority" in resp.get_json()["error"]


def test_missing_field_returns_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    # move_intent missing (None is not in valid set)
    resp = client.post(
        "/api/intelligence/path-preferences",
        json={"seniority_intent": "move_up", "priority": "pay_title"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400


def test_save_preferences_invalidates_path_cache(client, monkeypatch):
    import app as app_module

    csrf = _register_and_login(client, monkeypatch)

    # Seed a fake cache entry for this user
    from app import app
    from model import User
    from solverah.services import path_cache
    with app.app_context():
        user = User.query.filter_by(email="prefs@example.com").first()
        path_cache.store(user.id, {"suggestions": [], "career_status": "employed", "generated_at": "2026-01-01T00:00:00Z"})
        user_id = user.id

    assert user_id in path_cache.snapshot()

    client.post(
        "/api/intelligence/path-preferences",
        json=VALID_PREFS,
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert user_id not in path_cache.snapshot()
