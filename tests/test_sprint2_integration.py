"""Sprint 2 end-to-end integration smoke test.

Walks the happy path that survives in a single sequential test:
  1. User registers, confirms email, and logs in
  2. User completes Work Pulse -- the 24-item core instrument /work-pulse serves
     (the original 12-question kind this step used to submit was retired on
     2026-10-02)
  3. GET /api/v1/auth/session reports Work Pulse complete

Until 2026-11-23 this began with the anonymous pre-signup teaser: a ``wpll``
scoring job enqueued with no session, then claimed onto the new account through
``POST /intake/claims`` mode ``session``. ``/start`` was deleted that day, and
with it the anonymous ``wpll`` job (ruling C; the kind is retired, see
``test_wpll_result.py``) and the session claim (public-funnel). Neither step has
a door any more, so the flow starts at registration.

All DB operations run against the real test DB.
"""

import pytest


def _noop(*_args, **_kwargs):
    return None


# `respondent_id_for_user` reads this at call time and has no default by design
# (D-05). Set per file, never in conftest.py: test_assessment_form.py deletes it
# to prove the no-default rule holds.
@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


def test_sprint2_full_happy_path(client, monkeypatch):
    """register -> Work Pulse (core) -> the session flag says so."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    # ── Step 1: register, confirm, login ─────────────────────────────────────
    email, password = "sprint2@example.com", "Sprint2Pass1!"

    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Sprint Two", "terms_accepted": True},
    )
    assert reg_res.status_code == 201

    from app import app
    from model import User, db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        db.session.commit()

    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200
    csrf = login_res.get_json()["csrfToken"]

    flags_initial = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags_initial["wp_v2_completed"] is False
    assert flags_initial["wpll_completed"] is False
    assert flags_initial["wpl_completed"] is False

    # ── Step 2: complete Work Pulse, the core instrument /work-pulse serves ──
    form = client.get("/api/v1/assessments/core/form")
    assert form.status_code == 200
    responses = {
        item["token"]: item["options"][0]["key"]
        for block in form.get_json()["blocks"]
        for item in block["items"]
    }
    core = client.post(
        "/api/v1/assessments/core/submissions",
        json={"responses": responses},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert core.status_code == 200
    assert "dimension_scores" not in core.get_json()  # D-15: no gradient handed back

    # ── Step 3: the session reflects it ──────────────────────────────────────
    flags_final = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags_final["wp_v2_completed"] is True
    assert flags_final["wpll_completed"] is False  # the retired teaser, never claimed
    assert flags_final["wpl_completed"] is False  # the retired kind, never taken

    from model import AssessmentSubmission
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        rows = {
            row.kind: row
            for row in AssessmentSubmission.query.filter_by(user_id=user.id).all()
        }
        assert set(rows) == {"core"}
        assert rows["core"].completed_at is not None
