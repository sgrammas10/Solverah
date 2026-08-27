"""``GET /auth/session`` -- the cheap session probe, and the P0-3 fix.

The SPA restored its session by calling `GET /profile`, which returns the entire
`profile_data` blob and commits an `AuditLog` row on the way out. Session restore
fires on every page load, so the highest-volume table in the system was written
synchronously on the hottest endpoint, for data the app shell does not render.

These tests hold both halves of the replacement down: it answers the question
the shell actually asks, and it does not write. The second is the one that needs
a test, because nothing else in the suite would notice the write coming back.
"""

import pytest

from solverah.schemas.auth import SessionResponse

EMAIL = "session-api@example.com"
PASSWORD = "Strongpass1!"


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def registered(client, monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Session User",
              "role": "job-seeker", "terms_accepted": True},
    )


@pytest.fixture()
def auth(client, registered):
    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def _audit_count():
    from app import app
    from model import AuditLog

    with app.app_context():
        return AuditLog.query.count()


def test_session_returns_identity_flags_and_a_csrf_token(client, auth):
    resp = client.get("/api/v1/auth/session")

    assert resp.status_code == 200
    body = resp.get_json()
    SessionResponse.model_validate(body)
    assert body["user"]["email"] == EMAIL
    assert body["csrf_token"]
    assert body["flags"]["email_confirmed"] is True


def test_session_does_not_ship_the_profile_blob(client, auth):
    """The whole reason it exists. Shipping it here would put P0-3 back."""
    body = client.get("/api/v1/auth/session").get_json()

    assert "profileData" not in body
    assert "profileData" not in body["user"]


def test_session_writes_nothing(client, auth):
    """P0-3, asserted as an absence.

    A refactor that reintroduced the audit write on this path would pass every
    other test in the suite.
    """
    before = _audit_count()

    for _ in range(3):
        assert client.get("/api/v1/auth/session").status_code == 200

    assert _audit_count() == before


def test_session_reports_assessment_completion_flags(client, auth):
    flags = client.get("/api/v1/auth/session").get_json()["flags"]

    assert flags["wpl_completed"] is False
    assert flags["wpll_completed"] is False
    assert flags["wp_v2_completed"] is False


def test_session_is_401_without_a_jwt(client):
    """The probe must not answer for an anonymous caller."""
    assert client.get("/api/v1/auth/session").status_code == 401


def test_session_reports_an_unconfirmed_account_as_unconfirmed(client, registered):
    """The flag the shell needs to decide whether to show the verify prompt."""
    from app import app
    from model import User, db

    # Registration leaves email_confirmed False, so log in via the reset path
    # rather than /auth/login, which refuses an unconfirmed account by design.
    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        assert user.email_confirmed is False
        user.email_confirmed = True
        db.session.commit()

    client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        user.email_confirmed = False
        db.session.commit()

    assert client.get("/api/v1/auth/session").get_json()["flags"]["email_confirmed"] is False


