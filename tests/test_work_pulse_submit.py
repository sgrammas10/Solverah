"""The original 12-question Work Pulse, retired on 2026-10-02.

Sebastian's ruling of that date retired the ``work_pulse`` kind. Nothing in the
client could start a sitting any more, yet ``POST
/assessments/work_pulse/scoring-jobs`` still accepted twelve answers and paid
for an OpenAI narrative. Every write door now answers ``410`` with error code
``kind_retired``, before auth and before the body is read, and no provider call
is reachable. The stored result stays readable, read-only, for users who
finished the old quiz.

Until this date this file tested the scorer itself, through the job pair it
moved to in Phase 3c. Those tests went with the scorer.
"""

import json
from unittest.mock import MagicMock

import pytest

WP_ANSWERS = [
    {"question_id": "wp-q%d" % i, "option_id": "wp-q%d-b" % i} for i in range(1, 13)
]

STORED_RESULT = {
    "narrative": "You bring deep focus to your work when conditions allow it.",
    "emerging_signals": [{"title": "Deep Focus Seeker", "description": "Needs quiet."}],
    "archetype": "Structured Deep Thinker",
    "archetype_description": "You build momentum through sustained effort.",
}

EMAIL = "wp-retired@example.com"
PASSWORD = "Strongpass1!"


def _noop(*_args, **_kwargs):
    return None


# `respondent_id_for_user` reads this at call time and has no default by design
# (D-05). Set per file, never in conftest.py: test_assessment_form.py deletes it
# to prove the no-default rule holds.
@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


@pytest.fixture()
def csrf(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns its CSRF token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)
    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "WP User",
              "role": "job-seeker", "terms_accepted": True},
    )

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


@pytest.fixture()
def provider(monkeypatch):
    """A provider double that would answer, so a call reaching it is visible."""
    mock_client = MagicMock()
    choice = MagicMock()
    choice.message.content = json.dumps(STORED_RESULT)
    response = MagicMock()
    response.choices = [choice]
    mock_client.chat.completions.create.return_value = response
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)
    return mock_client


def _store_legacy_sitting(*, result):
    """A sitting of the old quiz, as one stored before the retirement."""
    from app import app
    from model import User, db
    from solverah.domain import auth as auth_domain
    from solverah.repositories import assessment_repository
    from solverah.services import assessment_service

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        row = assessment_repository.open_current(
            user.id, "work_pulse", assessment_service.CLIENT_FORM_VERSION
        )
        row.answers = WP_ANSWERS
        row.completed_at = auth_domain.utcnow()
        row.status = "scored" if result else "complete"
        row.result = result
        row.narrative = result["narrative"] if result else None
        db.session.commit()
        return user.id


def _assert_retired(resp):
    assert resp.status_code == 410
    assert resp.mimetype == "application/problem+json"
    body = resp.get_json()
    assert body["type"] == "https://solverah.com/errors/gone"
    assert body["errors"] == [{"field": "kind", "code": "kind_retired"}]
    # Gone, not moved: there is no forwarding address for this operation.
    assert "replaced_by" not in body


# ── Every write door is a 410 ────────────────────────────────────────────────


def test_the_scoring_job_enqueue_is_retired(client, csrf, provider):
    resp = client.post(
        "/api/v1/assessments/work_pulse/scoring-jobs",
        json={"answers": WP_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )

    _assert_retired(resp)
    assert provider.chat.completions.create.call_count == 0


def test_the_enqueue_refuses_before_auth_and_before_the_body(client, provider):
    """No JWT and no body: still the 410, never a 401 or a 400/422."""
    _assert_retired(client.post("/api/v1/assessments/work_pulse/scoring-jobs"))
    assert provider.chat.completions.create.call_count == 0


def test_the_synchronous_submit_is_retired_rather_than_moved(client, provider):
    """It used to point at the job route; that route is gone too."""
    resp = client.post(
        "/api/v1/assessments/work_pulse/submissions", json={"answers": WP_ANSWERS}
    )

    _assert_retired(resp)
    assert provider.chat.completions.create.call_count == 0


def test_the_job_poll_is_retired(client, csrf):
    _assert_retired(
        client.get(
            "/api/v1/assessments/work_pulse/scoring-jobs/00000000000000000000000000000000"
        )
    )


def test_a_retired_enqueue_creates_no_job_and_no_submission(client, csrf, provider):
    from app import app
    from model import AssessmentSubmission, ScoringJob

    client.post(
        "/api/v1/assessments/work_pulse/scoring-jobs",
        json={"answers": WP_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )

    with app.app_context():
        assert ScoringJob.query.count() == 0
        assert AssessmentSubmission.query.filter_by(kind="work_pulse").count() == 0


def test_the_service_dispatch_refuses_the_retired_kind(client, csrf, provider):
    """The seam a worker reaches, refused independently of the routes."""
    import logging

    from app import app
    from model import User
    from solverah.services import assessment_service

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        outcome = assessment_service.submit(
            assessment_service.find_kind("work_pulse"),
            user,
            {"answers": WP_ANSWERS},
            logging.getLogger("test"),
        )

    assert outcome.status == 410
    assert outcome.body == {"error": assessment_service.RETIRED_WORK_PULSE_MESSAGE}
    assert provider.chat.completions.create.call_count == 0


def test_the_legacy_scorer_and_prompt_are_gone():
    """Deleted, not merely unrouted -- nothing left to reach by accident."""
    from solverah.services import assessment_prompts, assessment_service

    assert not hasattr(assessment_service, "submit_work_pulse")
    assert not hasattr(assessment_prompts, "build_wp_narrative_prompt")


# ── The read side stays ──────────────────────────────────────────────────────


def test_a_stored_narrative_stays_readable(client, csrf):
    _store_legacy_sitting(result=STORED_RESULT)

    resp = client.get("/api/v1/me/assessments/work_pulse/result")

    assert resp.status_code == 200
    assert resp.get_json() == STORED_RESULT


def test_a_sitting_without_a_narrative_is_a_404_not_a_resubmit_prompt(client, csrf):
    """Was a 422 telling the client to resubmit; there is nothing to resubmit to."""
    _store_legacy_sitting(result=None)

    resp = client.get("/api/v1/me/assessments/work_pulse/result")

    assert resp.status_code == 404


def test_no_sitting_is_a_404(client, csrf):
    assert client.get("/api/v1/me/assessments/work_pulse/result").status_code == 404


def test_a_legacy_completer_keeps_the_wpl_completed_flag(client, csrf):
    """The session flag the read-only results page gates on."""
    _store_legacy_sitting(result=STORED_RESULT)

    flags = client.get("/api/v1/auth/session").get_json()["flags"]

    assert flags["wpl_completed"] is True
