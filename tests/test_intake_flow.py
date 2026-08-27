"""Integration tests: full intake flow from registration through flags reflection."""

import datetime


def _noop(*_args, **_kwargs):
    return None


def _register_and_confirm(client, monkeypatch, email="flow@example.com", password="FlowPass1!@#"):
    """Register a user and bypass email confirmation for testing."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Flow User", "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import db, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        db.session.commit()
    return email, password


def _login(client, email, password):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


# `mode` is the discriminator on POST /api/v1/intake/claims, which Phase 1b
# collapsed the four account-attachment endpoints onto. "session" is the one
# with no submission behind it: an anonymous Work Pulse Lite-Lite session held
# in sessionStorage, adopted onto the account that just signed in.
SAMPLE_INTAKE = {
    "mode": "session",
    "selected_statement_ids": ["dir-1", "sus-2"],
    "wpll_answers": [
        {"question_id": "wpll-q1", "option_id": "wpll-q1-c"},
        {"question_id": "wpll-q2", "option_id": "wpll-q2-d"},
        {"question_id": "wpll-q3", "option_id": "wpll-q3-b"},
        {"question_id": "wpll-q4", "option_id": "wpll-q4-c"},
        {"question_id": "wpll-q5", "option_id": "wpll-q5-c"},
    ],
    "wpll_insight_text": "Test insight text.",
}


def test_full_intake_flow_creates_user_intake_row(client, monkeypatch):
    email, pw = _register_and_confirm(client, monkeypatch)
    csrf = _login(client, email, pw)
    resp = client.post(
        "/api/v1/intake/claims",
        json=SAMPLE_INTAKE,
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200

    from app import app
    from model import User, UserIntake
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        assert user.intake is not None
        assert user.intake.selected_statement_ids == ["dir-1", "sus-2"]
        assert len(user.intake.wpll_answers) == 5
        assert user.intake.wpll_completed_at is not None


def test_profile_reflects_wpll_completed_after_save(client, monkeypatch):
    email, pw = _register_and_confirm(client, monkeypatch)
    csrf = _login(client, email, pw)

    # Before save
    flags_before = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags_before["wpll_completed"] is False

    # Save
    client.post(
        "/api/v1/intake/claims",
        json=SAMPLE_INTAKE,
        headers={"X-CSRF-TOKEN": csrf},
    )

    # After save
    flags_after = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags_after["wpll_completed"] is True
    assert flags_after["wpl_completed"] is False


def test_second_save_upserts_not_duplicates(client, monkeypatch):
    email, pw = _register_and_confirm(client, monkeypatch)
    csrf = _login(client, email, pw)

    client.post(
        "/api/v1/intake/claims",
        json=SAMPLE_INTAKE,
        headers={"X-CSRF-TOKEN": csrf},
    )
    updated = {**SAMPLE_INTAKE, "selected_statement_ids": ["ldr-1"]}
    client.post(
        "/api/v1/intake/claims",
        json=updated,
        headers={"X-CSRF-TOKEN": csrf},
    )

    from app import app
    from model import User, UserIntake
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        rows = UserIntake.query.filter_by(user_id=user.id).all()
        assert len(rows) == 1
        assert rows[0].selected_statement_ids == ["ldr-1"]


def test_second_save_preserves_wpll_completed_at(client, monkeypatch):
    email, pw = _register_and_confirm(client, monkeypatch)
    csrf = _login(client, email, pw)

    client.post(
        "/api/v1/intake/claims",
        json=SAMPLE_INTAKE,
        headers={"X-CSRF-TOKEN": csrf},
    )

    from app import app
    from model import User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        original_ts = user.intake.wpll_completed_at

    # Second save
    client.post(
        "/api/v1/intake/claims",
        json=SAMPLE_INTAKE,
        headers={"X-CSRF-TOKEN": csrf},
    )

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        assert user.intake.wpll_completed_at == original_ts


def test_wpl_completed_remains_false_until_sprint2_endpoint(client, monkeypatch):
    email, pw = _register_and_confirm(client, monkeypatch)
    csrf = _login(client, email, pw)

    client.post(
        "/api/v1/intake/claims",
        json=SAMPLE_INTAKE,
        headers={"X-CSRF-TOKEN": csrf},
    )

    flags = client.get("/api/v1/auth/session").get_json()["flags"]
    # wpl_completed_at is only set by Sprint 2's /work-pulse/lite/submit
    assert flags["wpl_completed"] is False
