"""The unversioned paths are gone, and the versioned ones do what they claimed.

This file was written for Phase 1a, where ``/api/v1/x`` and ``/api/x`` were two
URL rules bound to one endpoint.  It proved over the wire what
``tests/test_openapi.py`` proved about the url_map: that the alias was the same
handler and not a redirect, and -- the case the whole design turned on -- that an
authenticated POST, which a browser preflights because of the ``X-CSRF-TOKEN``
header, answered on the versioned path with no redirect in the way.

Phase 1b finished the cutover and deleted the aliases.  What is left to check is
the other half of that decision, and it is worth keeping rather than deleting
along with them:

* the unversioned paths really are gone -- an alias that survived would be an
  unversioned, undocumented, permanently-supported URL nobody meant to keep;
* the *superseded* versioned paths are gone too, which is the easier thing to
  forget, because they were never a migration affordance and nothing points at
  them;
* the versioned routes still enforce authentication, CSRF, and their own
  business rules, so removing the second path did not quietly remove a check
  along with it.
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
        "/api/v1/auth/register",
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

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


# ── The aliases are gone ────────────────────────────────────────────────────


#: One unversioned path per resource module. Not exhaustive by design -- the
#: url_map assertion below covers the whole set, and these are here so a failure
#: names a URL a human recognises instead of a count.
LEGACY_PATHS = [
    ("POST", "/api/login"),
    ("POST", "/api/register"),
    ("GET", "/api/profile"),
    ("GET", "/api/dashboard-data"),
    ("POST", "/api/intake/finalize"),
    ("GET", "/api/company-lens/matches"),
    ("GET", "/api/account/export"),
]


@pytest.mark.parametrize("method,path", LEGACY_PATHS)
def test_a_legacy_path_is_not_served(client, method, path):
    """404, not 401 and not a redirect.

    A 401 would mean the rule still exists and is merely refusing this caller,
    which is the failure mode that would keep an unversioned URL alive
    indefinitely without anyone noticing.
    """
    resp = client.open(path, method=method, json={})

    assert resp.status_code == 404


def test_no_unversioned_rule_survives_anywhere_in_the_url_map(client):
    """The exhaustive version of the check above.

    Health probes are deliberately exempt: `/healthz`, `/readyz` and `/metrics`
    are unversioned platform endpoints by design (Part 5.2), not leftovers.
    """
    from app import app
    from solverah.factory import LEGACY_PREFIX, V1_PREFIX

    unversioned = sorted(
        rule.rule
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith(LEGACY_PREFIX + "/")
        and not rule.rule.startswith(V1_PREFIX + "/")
    )

    assert unversioned == []


def test_the_superseded_versioned_paths_are_gone_too(client):
    """The easier half to forget.

    `/api/v1/login` was never a migration affordance -- it was the Phase 1a
    path, and Phase 1b renamed it to `/api/v1/auth/login`. Nothing points at the
    old one, which is exactly why it could sit there serving traffic forever.
    """
    for path in ("/api/v1/login", "/api/v1/profile", "/api/v1/dashboard-data",
                 "/api/v1/account/export", "/api/v1/company-lens/matches"):
        assert client.get(path).status_code == 404, path


# ── The versioned routes still check what they used to ──────────────────────


def test_export_answers_on_the_versioned_path(client, monkeypatch):
    _register_and_login(client, monkeypatch)

    resp = client.get("/api/v1/me/export")

    assert resp.status_code == 200
    assert resp.get_json()["account"]["email"] == "alias@example.com"


def test_export_response_matches_its_declared_schema(client, monkeypatch):
    """The OpenAPI document is only worth what this assertion is worth."""
    _register_and_login(client, monkeypatch)

    body = client.get("/api/v1/me/export").get_json()

    AccountExportResponse.model_validate(body)


def test_a_csrf_protected_write_works_on_the_versioned_path(client, monkeypatch):
    """The case the alias design existed for, still checked now that it is gone.

    The X-CSRF-TOKEN header makes this a non-simple cross-origin request, so a
    browser preflights it. If the versioned path answered with a redirect
    instead of the handler, this is the request that would break -- and it would
    break in the browser, not here.
    """
    csrf = _register_and_login(client, monkeypatch)

    resp = client.delete(
        "/api/v1/me",
        json={"confirm": "DELETE"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 200
    assert "Location" not in resp.headers
    AccountDeleteResponse.model_validate(resp.get_json())


def test_the_versioned_write_still_enforces_csrf(client, monkeypatch):
    _register_and_login(client, monkeypatch)

    resp = client.delete("/api/v1/me", json={"confirm": "DELETE"})

    assert resp.status_code == 401


def test_the_versioned_write_still_enforces_the_confirmation_string(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)

    resp = client.delete(
        "/api/v1/me",
        json={"confirm": "yes"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 400


def test_the_versioned_route_still_requires_authentication(client):
    resp = client.get("/api/v1/me/export")

    assert resp.status_code == 401
