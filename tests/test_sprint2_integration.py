"""Sprint 2 end-to-end integration smoke test.

Walks the full happy path in a single sequential test. Since Phase 3c the
WPLL submit runs through the scoring-job pair -- enqueue a job, poll its
status -- rather than a synchronous POST:
  1. Anonymous user completes Work Pulse Lite — enqueue + poll the wpll scoring job
  2. User registers, confirms email, and logs in
  3. WPLL data saved to account — POST /api/v1/intake/claims
  4. User completes Work Pulse — the 24-item core instrument /work-pulse serves
     (the original 12-question kind this step used to submit was retired on
     2026-10-02)
  5. GET /api/v1/auth/session returns both completion flags as True

Under eager test execution the job runs inline, so each poll is immediately
terminal and the body the old synchronous 200 returned is the poll's ``result``.

All OpenAI calls are mocked. All DB operations run against the real test DB.
"""

import json
import pytest
from unittest.mock import MagicMock


WPLL_ANSWERS = [
    {"question_id": "wpll-q1", "option_id": "wpll-q1-c"},
    {"question_id": "wpll-q2", "option_id": "wpll-q2-d"},
    {"question_id": "wpll-q3", "option_id": "wpll-q3-a"},
    {"question_id": "wpll-q4", "option_id": "wpll-q4-b"},
    {"question_id": "wpll-q5", "option_id": "wpll-q5-a"},
]

_WPLL_LLM_PAYLOAD = {"insight_text": "Your work pattern shows clear fragmentation signals."}


def _patch_openai(monkeypatch, response_payload: dict):
    """Replace _get_openai_client with a mock that returns response_payload as JSON."""
    import app as app_module
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(response_payload)
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)


def _noop(*_args, **_kwargs):
    return None


# `respondent_id_for_user` reads this at call time and has no default by design
# (D-05). Set per file, never in conftest.py: test_assessment_form.py deletes it
# to prove the no-default rule holds.
@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


def test_sprint2_full_happy_path(client, monkeypatch):
    """Full Sprint 2 flow, through the Phase 3c job pair: anonymous WPLL
    enqueue + poll → register → save → Work Pulse (core) → profile complete."""
    import app as app_module
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    # ── Step 1: anonymous WPLL result, through the scoring-job pair ──────────
    _patch_openai(monkeypatch, _WPLL_LLM_PAYLOAD)

    wpll_accepted = client.post(
        "/api/v1/assessments/wpll/scoring-jobs",
        json={"answers": WPLL_ANSWERS},
    )
    assert wpll_accepted.status_code == 202
    wpll_job_id = wpll_accepted.get_json()["job_id"]

    wpll_poll = client.get("/api/v1/assessments/wpll/scoring-jobs/%s" % wpll_job_id)
    assert wpll_poll.status_code == 200
    assert wpll_poll.get_json()["status"] == "succeeded"
    wpll_body = wpll_poll.get_json()["result"]
    assert isinstance(wpll_body["insight_text"], str) and len(wpll_body["insight_text"]) > 0
    assert len(wpll_body["locked_sections"]) == 3

    captured_insight = wpll_body["insight_text"]

    # ── Step 2: register, confirm, login ─────────────────────────────────────
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

    # Both flags are False before any intake data is saved
    flags_initial = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags_initial["wpll_completed"] is False
    assert flags_initial["wpl_completed"] is False

    # ── Step 3: save WPLL data to account ───────────────────────────────────
    save_res = client.post(
        "/api/v1/intake/claims",
        json={
            "mode": "session",
            "selected_statement_ids": ["dir-1", "sus-2"],
            "wpll_answers": WPLL_ANSWERS,
            "wpll_insight_text": captured_insight,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert save_res.status_code == 200
    assert save_res.get_json()["wpll_completed"] is True

    flags_after_save = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags_after_save["wpll_completed"] is True
    assert flags_after_save["wpl_completed"] is False  # WP not done yet

    # ── Step 4: complete Work Pulse, the core instrument /work-pulse serves ──
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

    # ── Step 5: profile reflects both flags True ──────────────────────────────
    flags_final = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags_final["wp_v2_completed"] is True
    assert flags_final["wpll_completed"] is True
    assert flags_final["wpl_completed"] is False  # the retired kind, never taken

    # Confirm both phases are on record. Two rows in one table since Phase 2d;
    # two column families on `user_intake` before it. This is the assertion the
    # unification is for -- the same query answers it for either instrument.
    from model import AssessmentSubmission
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        rows = {
            row.kind: row
            for row in AssessmentSubmission.query.filter_by(user_id=user.id).all()
        }
        assert set(rows) == {"wpll", "core"}
        assert rows["wpll"].answers == WPLL_ANSWERS
        assert rows["wpll"].completed_at is not None
        assert rows["core"].completed_at is not None
