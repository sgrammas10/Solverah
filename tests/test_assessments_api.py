"""``POST /assessments/{kind}/submissions`` and the rest of the unified route.

The collapse is the easy half. These tests are mostly about the three things
that could have been quietly lost in it:

* **The result shapes stay different.** Five instruments, five payloads. A test
  that only checked "200 and some JSON" would pass against a flattened envelope,
  so each kind is validated against its own model and `core`'s omissions are
  asserted explicitly.
* **The rate-limit buckets stay separate.** Five handlers at 5/min each became
  one handler, and one handler is one bucket unless something is done about it.
  Finishing Work Pulse must not spend FocusType's allowance.
* **Auth is still required where it was.** Four of five kinds need a JWT and the
  fifth deliberately does not, so `@jwt_required()` had to come off the route
  and move inside it. That is exactly the sort of change that drops CSRF
  protection without anything failing.
"""

import json
from unittest.mock import MagicMock

import pytest

from solverah.schemas.assessments import (
    AssessmentCatalogueResponse,
    RESULT_RESPONSES,
    SUBMISSION_RESPONSES,
)

PASSWORD = "Strongpass1!"

WP_ANSWERS = [
    {"question_id": "wp-q%d" % i, "option_id": "wp-q%d-b" % i} for i in range(1, 13)
]
MM_ANSWERS = [{"question_id": "mm-q%d" % i, "choice": "a"} for i in range(1, 16)]

FOCUS_TYPE_PAYLOAD = {
    "scene_1": ["big_project", "planning_doc", "urgent_client", "teammate_feedback",
                "emails", "admin_tasks"],
    "scene_2": {
        "now": ["email_client_important", "slack_mentioned"],
        "later": ["slack_teammate_question"],
        "ignore": ["email_newsletter", "calendar_meeting_invite", "task_new_ticket",
                   "task_planning_doc", "slack_team_channel", "email_system_report",
                   "calendar_team_lunch"],
    },
    "scene_3": {"deep_solo": 2.5, "planning": 0.5, "social": 0.5, "breaks": 0.25,
                "exploring": 0.25},
    "scene_4": {
        "now": ["deep_research"],
        "tomorrow": ["reply_teammate", "write_report_draft", "update_task_tracker",
                     "quick_call_unblock", "send_followup_email", "review_others_work",
                     "sketch_tomorrow_plan"],
        "avg_decision_time_ms": 500,
    },
    "scene_5": ["deep_work", "wind_down"],
}

WP_LLM_RESPONSE = {
    "narrative": "You bring deep focus to your work when conditions allow it.",
    "emerging_signals": [{"title": "Deep Focus Seeker", "description": "Needs quiet."}],
    "archetype": "Structured Deep Thinker",
    "archetype_description": "You build momentum through sustained effort.",
}

MM_LLM_RESPONSE = {
    "narrative": "You want a manager who explains the why.",
    "what_to_look_for": ["Clear written context"],
    "red_flags": ["Decisions with no stated reasoning"],
    "archetype_description": "You do your best work under an explainer.",
}


def _noop(*_args, **_kwargs):
    return None


def _mock_openai(monkeypatch, payload):
    mock_client = MagicMock()
    choice = MagicMock()
    choice.message.content = json.dumps(payload)
    response = MagicMock()
    response.choices = [choice]
    mock_client.chat.completions.create.return_value = response
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)
    return mock_client


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns its CSRF token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    email = "assess-api@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Assess User",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def _submit(client, kind, body, csrf=None):
    headers = {"X-CSRF-TOKEN": csrf} if csrf else {}
    return client.post(
        "/api/v1/assessments/%s/submissions" % kind, json=body, headers=headers
    )


# ── Catalogue ───────────────────────────────────────────────────────────────


def test_catalogue_lists_every_kind(client, auth):
    resp = client.get("/api/v1/assessments")

    assert resp.status_code == 200
    body = resp.get_json()
    AssessmentCatalogueResponse.model_validate(body)
    assert {entry["kind"] for entry in body["data"]} == {
        "core", "work_pulse", "wpll", "focus_type", "manager_match"
    }


def test_catalogue_reports_nothing_completed_for_a_fresh_account(client, auth):
    body = client.get("/api/v1/assessments").get_json()

    assert all(entry["completed"] is False for entry in body["data"])


def test_catalogue_reflects_a_completed_assessment(client, auth):
    _submit(client, "focus_type", FOCUS_TYPE_PAYLOAD, auth)

    body = client.get("/api/v1/assessments").get_json()
    completed = {e["kind"] for e in body["data"] if e["completed"]}

    assert completed == {"focus_type"}


# ── The five kinds submit, and keep their own result shapes ─────────────────


def test_focus_type_submits_and_matches_its_own_model(client, auth):
    resp = _submit(client, "focus_type", FOCUS_TYPE_PAYLOAD, auth)

    assert resp.status_code == 200
    SUBMISSION_RESPONSES["focus_type"].model_validate(resp.get_json())
    assert resp.get_json()["archetype"]


def test_work_pulse_submits_and_matches_its_own_model(client, auth, monkeypatch):
    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    resp = _submit(client, "work_pulse", {"answers": WP_ANSWERS}, auth)

    assert resp.status_code == 200
    body = resp.get_json()
    SUBMISSION_RESPONSES["work_pulse"].model_validate(body)
    assert body["narrative"] and body["archetype"]


def test_manager_match_submits_and_matches_its_own_model(client, auth, monkeypatch):
    _mock_openai(monkeypatch, MM_LLM_RESPONSE)

    resp = _submit(client, "manager_match", {"answers": MM_ANSWERS}, auth)

    assert resp.status_code == 200
    body = resp.get_json()
    SUBMISSION_RESPONSES["manager_match"].model_validate(body)
    assert body["what_to_look_for"]


def test_wpll_submits_without_a_jwt(client):
    """The one anonymous instrument. It runs the pre-launch teaser."""
    resp = _submit(client, "wpll", {"answers": [{"question_id": "q1", "option_id": "a"}]})

    assert resp.status_code == 200
    SUBMISSION_RESPONSES["wpll"].model_validate(resp.get_json())


def test_the_five_result_shapes_are_not_interchangeable(client, auth, monkeypatch):
    """The hazard the collapse creates: one route inviting one payload.

    A Work Pulse result carries a narrative and an archetype; a FocusType result
    carries dimension scores and recommendations. If a future refactor
    harmonised them into a shared envelope this is the test that notices.
    """
    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    work_pulse = _submit(client, "work_pulse", {"answers": WP_ANSWERS}, auth).get_json()
    focus_type = _submit(client, "focus_type", FOCUS_TYPE_PAYLOAD, auth).get_json()

    assert "narrative" in work_pulse and "narrative" not in focus_type
    assert "dimension_scores" in focus_type and "dimension_scores" not in work_pulse


# ── `core` withholds its scores, through every door ─────────────────────────


def test_core_submission_never_returns_dimension_scores(client, auth, monkeypatch):
    """D-04's threat model, restated as an assertion.

    Handing back the six numbers gives a retaking respondent a gradient to
    optimise against, which teaches the item-to-dimension mapping the shuffle
    and interleave exist to hide.
    """
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")

    form = client.get("/api/v1/assessments/core/form")
    assert form.status_code == 200

    responses = {}
    for block in form.get_json()["blocks"]:
        for item in block["items"]:
            responses[item["token"]] = item["options"][0]["key"]

    resp = _submit(client, "core", {"responses": responses}, auth)

    assert resp.status_code == 200
    body = resp.get_json()
    SUBMISSION_RESPONSES["core"].model_validate(body)
    assert "scores" not in body
    assert "dimension_scores" not in body


def test_core_has_no_result_endpoint(client, auth):
    """Absent by design, not pending: it would be the same disclosure elsewhere."""
    assert "core" not in RESULT_RESPONSES
    assert client.get("/api/v1/me/assessments/core/result").status_code == 404


# ── Reading a stored result ─────────────────────────────────────────────────


def test_result_round_trips_for_focus_type(client, auth):
    _submit(client, "focus_type", FOCUS_TYPE_PAYLOAD, auth)

    resp = client.get("/api/v1/me/assessments/focus_type/result")

    assert resp.status_code == 200
    RESULT_RESPONSES["focus_type"].model_validate(resp.get_json())


def test_result_is_404_before_anything_is_submitted(client, auth):
    assert client.get("/api/v1/me/assessments/manager_match/result").status_code == 404


# ── The discriminator ───────────────────────────────────────────────────────


def test_an_unknown_kind_is_a_404_problem_document(client, auth):
    resp = _submit(client, "astrology", {"answers": []}, auth)

    assert resp.status_code == 404
    assert resp.mimetype == "application/problem+json"
    assert resp.get_json()["errors"][0]["code"] == "unknown_kind"


def test_the_body_is_enforced_against_the_kind_not_the_union(client, auth):
    """The reason `request_for` exists.

    Enforcing the documented union would accept a Work Pulse body on the
    FocusType path, because open union members match nearly anything -- which
    would leave the route documented as strict and behaving as loose.
    """
    resp = _submit(client, "focus_type", {"answers": WP_ANSWERS}, auth)

    assert resp.status_code == 422
    fields = {error["field"] for error in resp.get_json()["errors"]}
    assert "scene_1" in fields


def test_a_form_is_404_for_a_kind_that_has_none(client, auth):
    """Truthful rather than an empty payload implying one might arrive."""
    assert client.get("/api/v1/assessments/work_pulse/form").status_code == 404


# ── Auth, which had to move off the decorator ───────────────────────────────


def test_an_authenticated_kind_refuses_an_anonymous_submission(client):
    resp = _submit(client, "focus_type", FOCUS_TYPE_PAYLOAD)

    assert resp.status_code == 401


def test_an_authenticated_kind_still_enforces_csrf(client, auth):
    """`verify_jwt_in_request()` does the CSRF check the decorator used to.

    Hand-rolling "is there a cookie" here instead would have dropped CSRF
    protection from four instruments without failing anything else.
    """
    resp = _submit(client, "focus_type", FOCUS_TYPE_PAYLOAD)

    assert resp.status_code == 401


def test_the_catalogue_requires_authentication(client):
    assert client.get("/api/v1/assessments").status_code == 401


# ── Rate limiting: one route, still five budgets ────────────────────────────


@pytest.fixture()
def enforcing(client):
    """A client with the TESTING rate-limit exemption switched off."""
    from app import app
    from solverah.extensions import limiter

    limiter.reset()
    app.config["TESTING"] = False
    try:
        yield client
    finally:
        app.config["TESTING"] = True
        limiter.reset()


def test_each_kind_gets_its_own_rate_limit_bucket(enforcing, auth):
    """The decision collapsing the five handlers forced.

    One endpoint is one Flask-Limiter bucket by default, so a user who finished
    Work Pulse and started FocusType would have been spending a single 5-per-
    minute allowance across two unrelated instruments. Scoping the bucket by
    kind preserves what the five separate handlers had.
    """
    for _ in range(6):
        spent = _submit(enforcing, "focus_type", FOCUS_TYPE_PAYLOAD, auth)
    assert spent.status_code == 429

    other = _submit(enforcing, "manager_match", {"answers": MM_ANSWERS}, auth)

    assert other.status_code != 429


