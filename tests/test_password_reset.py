import datetime
import pytest


def _noop(*_args, **_kwargs):
    return None


def _make_confirmed_user(client, monkeypatch):
    """Register and confirm a user, returning their email."""
    import app as app_module
    monkeypatch.setattr(app_module, "send_confirmation_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    email = "reset@example.com"
    client.post(
        "/api/register",
        json={"email": email, "password": "Strongpass1!", "name": "Reset User", "role": "job-seeker", "terms_accepted": True},
    )

    # Confirm email so the user can use password reset
    from app import app
    from model import db, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    return email


def test_request_reset_unknown_email_returns_404(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "send_password_reset_email", _noop)

    res = client.post("/api/request-password-reset", json={"email": "nobody@example.com"})
    assert res.status_code == 404
    assert "error" in res.get_json()


def test_request_reset_stores_token(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "send_password_reset_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    email = _make_confirmed_user(client, monkeypatch)
    res = client.post("/api/request-password-reset", json={"email": email})
    assert res.status_code == 200

    from app import app
    from model import User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        assert user.reset_token is not None
        assert len(user.reset_token) == 6
        assert user.reset_sent_at is not None


def test_verify_reset_wrong_code(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "send_password_reset_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    email = _make_confirmed_user(client, monkeypatch)
    client.post("/api/request-password-reset", json={"email": email})

    res = client.post("/api/verify-password-reset", json={"email": email, "code": "000000"})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_or_expired_code"


def test_verify_reset_expired_code(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "send_password_reset_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    email = _make_confirmed_user(client, monkeypatch)
    client.post("/api/request-password-reset", json={"email": email})

    from app import app
    from model import db, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        token = user.reset_token
        # Back-date the sent_at to 20 minutes ago to simulate expiry
        user.reset_sent_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=20)
        db.session.commit()

    res = client.post("/api/verify-password-reset", json={"email": email, "code": token})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_or_expired_code"


def test_verify_reset_success_logs_in(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "send_password_reset_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    email = _make_confirmed_user(client, monkeypatch)
    client.post("/api/request-password-reset", json={"email": email})

    from app import app
    from model import User
    with app.app_context():
        token = User.query.filter_by(email=email).first().reset_token

    res = client.post("/api/verify-password-reset", json={"email": email, "code": token})
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["message"] == "login successful"
    assert "csrfToken" in payload
    assert payload["user"]["email"] == email


def test_verify_reset_clears_token(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "send_password_reset_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    email = _make_confirmed_user(client, monkeypatch)
    client.post("/api/request-password-reset", json={"email": email})

    from app import app
    from model import User
    with app.app_context():
        token = User.query.filter_by(email=email).first().reset_token

    client.post("/api/verify-password-reset", json={"email": email, "code": token})

    from model import db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        assert user.reset_token is None
        assert user.reset_sent_at is None


def test_verify_reset_code_cannot_be_reused(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "send_password_reset_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    email = _make_confirmed_user(client, monkeypatch)
    client.post("/api/request-password-reset", json={"email": email})

    from app import app
    from model import User
    with app.app_context():
        token = User.query.filter_by(email=email).first().reset_token

    client.post("/api/verify-password-reset", json={"email": email, "code": token})

    # Try to use the same code again
    res = client.post("/api/verify-password-reset", json={"email": email, "code": token})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_or_expired_code"
