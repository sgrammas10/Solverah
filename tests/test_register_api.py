import pytest


def _noop(*_args, **_kwargs):
    return None


def test_register_success(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "send_confirmation_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    response = client.post(
        "/api/register",
        json={
            "email": "valid@example.com",
            "password": "Strongpass1!",
            "name": "Valid User",
            "role": "job-seeker",
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["message"] == "registered"
    assert payload["user"]["email"] == "valid@example.com"


def test_register_duplicate_email(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "send_confirmation_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    first = client.post(
        "/api/register",
        json={
            "email": "dup@example.com",
            "password": "Strongpass1!",
            "name": "Dup User",
            "role": "job-seeker",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/register",
        json={
            "email": "dup@example.com",
            "password": "Strongpass1!",
            "name": "Dup User",
            "role": "job-seeker",
        },
    )
    assert second.status_code == 400
    assert second.get_json() == {"error": "User already exists"}
