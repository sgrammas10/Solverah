"""Work Pulse scoring, driven through the job pair it moved to in Phase 3c.

The synchronous ``POST /assessments/work_pulse/submissions`` is deleted: it
answers 410 with a pointer at ``POST /assessments/work_pulse/scoring-jobs``,
and ``test_the_synchronous_submit_is_a_410_tombstone`` is the test of that
deletion. Everything else here drives the enqueue and the poll. Under the
suite's eager execution the job runs inline, so the first poll after the 202
is already terminal -- and its ``result`` is byte-identical to what the old
route answered in its 200 body.
"""

import json
import pytest
from unittest.mock import MagicMock


WP_ANSWERS = [
    {"question_id": "wp-q1",  "option_id": "wp-q1-b"},
    {"question_id": "wp-q2",  "option_id": "wp-q2-a"},
    {"question_id": "wp-q3",  "option_id": "wp-q3-c"},
    {"question_id": "wp-q4",  "option_id": "wp-q4-b"},
    {"question_id": "wp-q5",  "option_id": "wp-q5-c"},
    {"question_id": "wp-q6",  "option_id": "wp-q6-a"},
    {"question_id": "wp-q7",  "option_id": "wp-q7-b"},
    {"question_id": "wp-q8",  "option_id": "wp-q8-c"},
    {"question_id": "wp-q9",  "option_id": "wp-q9-a"},
    {"question_id": "wp-q10", "option_id": "wp-q10-b"},
    {"question_id": "wp-q11", "option_id": "wp-q11-a"},
    {"question_id": "wp-q12", "option_id": "wp-q12-b"},
]

VALID_LLM_RESPONSE = {
    "narrative": (
        "You bring deep focus to your work when conditions allow it.\n\n"
        "Recovery is a real need for you, not a luxury.\n\n"
        "Your autonomy matters — being told exactly how to do something costs you."
    ),
    "emerging_signals": [
        {"title": "Deep Focus Seeker", "description": "You show strong signs of needing uninterrupted time to reach your best work."},
        {"title": "Autonomy Driven", "description": "You prefer to own the how, not just the what."},
    ],
    "archetype": "Structured Deep Thinker",
    "archetype_description": (
        "You build momentum through sustained, self-directed effort — your best work emerges "
        "when you control the pace and the process. Environments with clear expectations and "
        "minimal interruption tend to bring out your strongest output. Friction often surfaces "
        "when direction is imposed without explanation or when context-switching is constant."
    ),
}


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="wp@example.com", password="Strongpass1!"):
    import app as app_module
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "WP User", "role": "job-seeker", "terms_accepted": True},
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


def _mock_openai(monkeypatch, response_json=None, raise_exc=None):
    import app as app_module
    mock_client = MagicMock()
    if raise_exc is not None:
        mock_client.chat.completions.create.side_effect = raise_exc
    else:
        payload = response_json if response_json is not None else VALID_LLM_RESPONSE
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(payload)
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)
    return mock_client


def _queue(client, body, csrf=None):
    headers = {"X-CSRF-TOKEN": csrf} if csrf else {}
    return client.post(
        "/api/v1/assessments/work_pulse/scoring-jobs", json=body, headers=headers
    )


def _poll(client, job_id):
    return client.get("/api/v1/assessments/work_pulse/scoring-jobs/%s" % job_id)


def _score(client, csrf, answers):
    """Queue a scoring and poll it once.

    Eager execution has already run the job inline by the time the 202 comes
    back, so the first poll is terminal.
    """
    queued = _queue(client, {"answers": answers}, csrf)
    assert queued.status_code == 202
    return _poll(client, queued.get_json()["job_id"])


# ── Happy path ───────────────────────────────────────────────────────────────

def test_submit_returns_narrative_signals_and_archetype(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    poll = _score(client, csrf, WP_ANSWERS)

    assert poll.status_code == 200
    assert poll.get_json()["status"] == "succeeded"
    result = poll.get_json()["result"]
    assert isinstance(result["narrative"], str) and len(result["narrative"]) > 0
    assert isinstance(result["emerging_signals"], list) and len(result["emerging_signals"]) >= 1
    assert all("title" in s and "description" in s for s in result["emerging_signals"])
    assert isinstance(result["archetype"], str) and len(result["archetype"]) > 0


def test_submit_returns_archetype_description(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="desc@example.com")
    _mock_openai(monkeypatch)

    result = _score(client, csrf, WP_ANSWERS).get_json()["result"]

    assert "archetype_description" in result, "archetype_description must be present in the scored result"
    assert isinstance(result["archetype_description"], str) and len(result["archetype_description"]) > 0


def test_submit_persists_answers_and_narrative(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    _score(client, csrf, WP_ANSWERS)

    from app import app
    from model import AssessmentSubmission, User
    with app.app_context():
        user = User.query.filter_by(email="wp@example.com").first()
        # `assessment_submissions` since Phase 2d; `user_intake.wpl_*` before it.
        # Both commits landed, so the row is `scored` rather than `complete` --
        # the two-commit sequence's outcome is readable from the status now,
        # instead of having to be inferred from a null `wpl_result`.
        submission = AssessmentSubmission.query.filter_by(
            user_id=user.id, kind="work_pulse"
        ).first()
        assert submission is not None
        assert submission.answers == WP_ANSWERS
        assert submission.narrative == VALID_LLM_RESPONSE["narrative"]
        assert submission.result == VALID_LLM_RESPONSE
        assert submission.completed_at is not None
        assert submission.scored_at is not None
        assert submission.status == "scored"


# ── Validation errors ────────────────────────────────────────────────────────

def test_submit_rejects_fewer_than_12_answers(client, monkeypatch):
    """The precheck answers the 400 at the enqueue, not after a poll.

    Same status and same body the synchronous route used to answer: a
    malformed submission must stay an immediate, actionable refusal rather
    than becoming a handle and a failed job several seconds later.
    """
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    res = _queue(client, {"answers": WP_ANSWERS[:5]}, csrf)
    assert res.status_code == 400
    assert "12" in res.get_json()["error"]


def test_submit_rejects_more_than_12_answers(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    too_many = WP_ANSWERS + [{"question_id": "wp-q1", "option_id": "wp-q1-a"}]
    res = _queue(client, {"answers": too_many}, csrf)
    assert res.status_code == 400


def test_submit_rejects_missing_answers_key(client, monkeypatch):
    """422 since Phase 1b: `answers` is a required field of the declared schema.

    The precheck's own "answers must be a list of exactly 12 items" guard still
    runs and still answers 400 -- for a body that *has* `answers` and gets the
    count wrong. The two failures stay distinguishable on the job door exactly
    as they were on the synchronous one.
    """
    csrf = _register_and_login(client, monkeypatch)

    res = _queue(client, {}, csrf)
    assert res.status_code == 422
    assert "answers" in {error["field"] for error in res.get_json()["errors"]}


# ── Auth ─────────────────────────────────────────────────────────────────────

def test_submit_requires_auth(client):
    res = _queue(client, {"answers": WP_ANSWERS})
    assert res.status_code == 401


# ── LLM failure ──────────────────────────────────────────────────────────────

def test_a_provider_failure_fails_the_job_with_the_route_error(client, monkeypatch):
    """The 500 the synchronous route answered is now a failed job, same words.

    "Unable to generate Work Pulse results" is text the service authors; the
    job's `error` carries it through, which is what keeps a failed poll as
    actionable as the old 500 body was while keeping provider detail off the
    endpoint. Was `test_submit_returns_500_on_llm_exception` when the provider
    call sat on the request path.
    """
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch, raise_exc=RuntimeError("OpenAI down"))

    poll = _score(client, csrf, WP_ANSWERS)

    assert poll.status_code == 200
    body = poll.get_json()
    assert body["status"] == "failed"
    assert body["error"] == "Unable to generate Work Pulse results"
    assert body.get("result") is None


def test_submit_does_not_set_wpl_completed_at_on_llm_failure(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch, raise_exc=RuntimeError("OpenAI down"))

    _score(client, csrf, WP_ANSWERS)

    from app import app
    from model import UserIntake, User
    with app.app_context():
        user = User.query.filter_by(email="wp@example.com").first()
        intake = UserIntake.query.filter_by(user_id=user.id).first()
        # Intake row may or may not exist; if it does, wpl_completed_at must be None.
        if intake is not None:
            assert intake.wpl_completed_at is None


# ── Profile flag ─────────────────────────────────────────────────────────────

def test_profile_shows_wpl_completed_after_submit(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_openai(monkeypatch)

    before = client.get("/api/v1/auth/session").get_json()["flags"]
    assert before["wpl_completed"] is False

    _score(client, csrf, WP_ANSWERS)

    after = client.get("/api/v1/auth/session").get_json()["flags"]
    assert after["wpl_completed"] is True


def test_submit_creates_a_submission_when_none_exists(client, monkeypatch):
    """Scoring WP answers creates the row when save-to-account was never called.

    It used to create a ``user_intake`` row; since Phase 2d it creates a
    ``work_pulse`` submission -- and since 3c the worker creates it, through the
    same service the deleted route called. The second half of the test is worth
    more than it was: WPLL is now a row in the *same* table, so "scoring Work
    Pulse did not invent a WPLL sitting" is a row count rather than a check of
    two columns that happened to sit next to each other.
    """
    csrf = _register_and_login(client, monkeypatch, email="fresh@example.com")
    _mock_openai(monkeypatch)

    from app import app
    from model import AssessmentSubmission, User
    with app.app_context():
        user = User.query.filter_by(email="fresh@example.com").first()
        assert AssessmentSubmission.query.filter_by(user_id=user.id).count() == 0, \
            "Expected no submissions before submission"

    poll = _score(client, csrf, WP_ANSWERS)
    assert poll.get_json()["status"] == "succeeded"

    with app.app_context():
        user = User.query.filter_by(email="fresh@example.com").first()
        rows = AssessmentSubmission.query.filter_by(user_id=user.id).all()
        assert len(rows) == 1
        assert rows[0].kind == "work_pulse"
        assert rows[0].answers == WP_ANSWERS
        assert rows[0].completed_at is not None


# ── The deleted transport ────────────────────────────────────────────────────

def test_the_synchronous_submit_is_a_410_tombstone(client):
    """This is the test of the deletion.

    A 404 would lie -- the kind exists, and the operation existed until Phase
    3c deleted the synchronous half. A 200 would be worse: it would resurrect
    the blocking provider call Phase 3 removed. The refusal precedes auth and
    body validation, so it holds for any caller in any state -- this one posts
    with no JWT at all -- and the problem document carries the forwarding
    address.
    """
    res = client.post(
        "/api/v1/assessments/work_pulse/submissions", json={"answers": WP_ANSWERS}
    )

    assert res.status_code == 410
    assert res.mimetype == "application/problem+json"
    body = res.get_json()
    assert body["type"] == "https://solverah.com/errors/gone"
    assert body["title"] == "Gone"
    assert body["replaced_by"] == "/assessments/work_pulse/scoring-jobs"
    assert body["errors"][0]["code"] == "moved_to_scoring_jobs"
