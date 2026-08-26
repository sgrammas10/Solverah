import pytest


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch):

    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/register",
        json={"email": "recs@example.com", "password": "Strongpass1!", "name": "Recs User", "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email="recs@example.com").first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post(
        "/api/login",
        json={"email": "recs@example.com", "password": "Strongpass1!"},
    )
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def test_get_recommendations_unauthenticated(client):
    resp = client.get("/api/recommendations")
    assert resp.status_code == 401


def test_get_recommendations_returns_empty_list(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    resp = client.get("/api/recommendations", headers={"X-CSRF-TOKEN": csrf})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "recommendations" in data
    assert data["recommendations"] == []


def test_post_recommendations_unauthenticated(client):
    resp = client.post("/api/recommendations", json={"profilePipeline": "[]"})
    assert resp.status_code == 401


def test_post_recommendations_returns_empty_list(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    resp = client.post(
        "/api/recommendations",
        json={"profilePipeline": "[]"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "recommendations" in data
    assert data["recommendations"] == []
