"""Tests for GET /api/companies/<company_id>."""

import pytest


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="detail@example.com", password="Strongpass1!"):
    import app as app_module
    monkeypatch.setattr(app_module, "send_confirmation_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    client.post("/api/register", json={"email": email, "password": password, "name": "Detail User"})

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


def _seed_company():
    from app import app
    from model import Company, db
    with app.app_context():
        company = Company(
            name="Stripe",
            slug="stripe",
            profile_json={
                "overview": {"name": "Stripe", "industry": "Fintech", "size": "enterprise"},
                "culture": {
                    "pace": "fast",
                    "empathy": 0.7,
                    "creative_drive": 0.8,
                    "adaptability": 0.9,
                    "futuristic": 0.85,
                    "harmony": 0.6,
                    "data_orientation": 0.75,
                },
            },
            work_environment="collaborative",
            pace="fast",
            empathy=0.7,
            creative_drive=0.8,
            adaptability=0.9,
            futuristic=0.85,
            harmony=0.6,
            data_orientation=0.75,
        )
        db.session.add(company)
        db.session.commit()
        return company.id


def test_happy_path_returns_200_with_profile(client, monkeypatch):
    _register_and_login(client, monkeypatch)
    company_id = _seed_company()

    resp = client.get(f"/api/companies/{company_id}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == company_id
    assert body["name"] == "Stripe"
    assert body["slug"] == "stripe"
    assert "profile" in body
    assert body["profile"]["overview"]["industry"] == "Fintech"


def test_unknown_id_returns_404(client, monkeypatch):
    _register_and_login(client, monkeypatch, email="notfound@example.com")

    resp = client.get("/api/companies/99999")
    assert resp.status_code == 404


def test_unauthenticated_returns_401(client):
    resp = client.get("/api/companies/1")
    assert resp.status_code == 401
