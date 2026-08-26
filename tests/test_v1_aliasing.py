"""Live tests that /api/v1/... and /api/... are the same handler, not a redirect.

tests/test_openapi.py proves the url_map is wired that way. These prove it over
the wire on a real, authenticated, CSRF-protected route -- including the case the
whole design turns on: an authenticated POST, which the browser preflights
because of the X-CSRF-TOKEN header, must answer on the versioned path without a
redirect in the way.

They also validate real handler output against the declared pydantic response
models, which is what keeps the generated OpenAPI document from drifting into
fiction while the schemas stay descriptive (see solverah/schemas/__init__.py).
"""

import pytest

from solverah.schemas.account import AccountDeleteResponse, AccountExportResponse


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="alias@example.com",
                        password="Strongpass1!"):

    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/register",
        json={"email": email, "password": password, "name": "Alias User",
              "role": "job-seeker", "terms_accepted": True},
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


# ── GET on both paths ───────────────────────────────────────────────────────


def test_export_answers_on_the_versioned_path(client, monkeypatch):
    _register_and_login(client, monkeypatch)

    resp = client.get("/api/v1/account/export")

    assert resp.status_code == 200
    assert resp.get_json()["account"]["email"] == "alias@example.com"


def test_versioned_and_legacy_paths_return_the_same_document(client, monkeypatch):
    """Same endpoint, same handler -- so the bodies must be indistinguishable."""
    _register_and_login(client, monkeypatch)

    versioned = client.get("/api/v1/account/export").get_json()
    legacy = client.get("/api/account/export").get_json()

    versioned.pop("exported_at")
    legacy.pop("exported_at")
    assert versioned == legacy


def test_legacy_path_does_not_redirect(client, monkeypatch):
    """A 3xx here would mean the frontend's calls take two round trips.

    Worse, on the preflighted writes below it would mean a POST whose redirect
    handling differs between browsers.
    """
    _register_and_login(client, monkeypatch)

    resp = client.get("/api/account/export")

    assert resp.status_code == 200
    assert "Location" not in resp.headers


def test_export_response_matches_its_declared_schema(client, monkeypatch):
    """The OpenAPI document is only worth what this assertion is worth."""
    _register_and_login(client, monkeypatch)

    body = client.get("/api/v1/account/export").get_json()

    AccountExportResponse.model_validate(body)


# ── Authenticated, CSRF-protected POST on the versioned path ────────────────


def test_csrf_protected_post_works_on_the_versioned_path(client, monkeypatch):
    """The case the alias design exists for.

    The X-CSRF-TOKEN header makes this a non-simple cross-origin request, so a
    browser preflights it. If /api/v1 answered with a redirect instead of the
    handler, this is the request that would break -- and it would break in the
    browser, not here.
    """
    csrf = _register_and_login(client, monkeypatch)

    resp = client.post(
        "/api/v1/account/delete",
        json={"confirm": "DELETE"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 200
    AccountDeleteResponse.model_validate(resp.get_json())


def test_versioned_post_still_enforces_csrf(client, monkeypatch):
    """The new path must not be a way around the protection the old one has."""
    _register_and_login(client, monkeypatch)

    resp = client.post("/api/v1/account/delete", json={"confirm": "DELETE"})

    assert resp.status_code == 401


def test_versioned_post_still_enforces_the_confirmation_string(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)

    resp = client.post(
        "/api/v1/account/delete",
        json={"confirm": "yes"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 400


def test_versioned_route_still_requires_authentication(client):
    resp = client.get("/api/v1/account/export")

    assert resp.status_code == 401
