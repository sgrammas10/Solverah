"""POST /me/quiz-insights, POST /intake/quiz-preview/insights, and the
GuestQuiz -> account import path (docs/BUILD_PLAN.md D-5).

Neither endpoint had a dedicated test file before this chunk. Coverage here
goes through the real HTTP routes rather than calling `insight_service`
directly, so a route-level regression (auth, request validation, rate limit
wiring) would show up here too, not just a service-level one.

D-5's audit (chunk D-1) framed two things as broken that turn out not to be,
verified here rather than assumed:

* Raw quiz answers do NOT evaporate for an authenticated user. `quizResults`
  is on `validators.ALLOWED_PROFILE_FIELDS`, is not promoted by
  `profile_document.decompose`, and rides in `profiles.extra` like any other
  unpromoted key -- `test_stable_keys_round_trip_through_patch_and_get`
  below locks that in for all six quizzes.
* The GuestQuiz "import path" already exists: `Login.tsx`'s onSuccess
  handler replays `PATCH /me/profile` (raw answers) then
  `POST /me/quiz-insights` (the guest's own payload) against the two
  endpoints below. There is no dedicated backend import endpoint, and none
  is needed -- `test_guest_quiz_import_sequence_persists_results_and_insight`
  proves that exact replay lands both halves on a freshly registered account.
"""
import json
from unittest.mock import MagicMock


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="quiz@example.com", password="Strongpass1!"):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": email, "password": password, "name": "Quiz User",
            "role": "job-seeker", "terms_accepted": True,
        },
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


def _mock_openai_json(monkeypatch, payload):
    """Patch solverah.infra.llm.get_openai_client to return *payload* as JSON."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(payload)
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)
    return mock_client


ONE_QUIZ = [
    {
        "key": "yourFutureYourWay",
        "title": "Your Future, Your Way",
        "items": [{"question": "What matters most?", "selected": "Growth"}],
    }
]

CAREER_QUIZZES_ITEM = [
    {
        "key": "earlyCareer",
        "title": "Quiz 1: Early Career",
        "items": [{"question": "What motivates you?", "selected": "Recognition"}],
    }
]

# The model is prompted to always return a cross-quiz `overallInsight`, even
# for a single-quiz submission (insight_prompts.build_quiz_insight_prompt) --
# this response shape is what the flat single-group storage actually looks
# like, `overallInsight` included, not a simplified stand-in.
SINGLE_QUIZ_MODEL_RESPONSE = {
    "overallInsight": {
        "summary": "Across everything, growth is the throughline.",
        "keyTakeaways": ["Growth-oriented"],
        "nextSteps": ["Seek a growth-path role"],
    },
    "insights": [
        {
            "key": "yourFutureYourWay",
            "title": "Your Future, Your Way",
            "summary": "You are drawn to roles with visible growth trajectories.",
            "keyTakeaways": ["Values growth"],
            "combinedMeaning": "Growth over stability.",
            "nextSteps": ["Ask about promotion timelines"],
        }
    ],
}


# ---------------------------------------------------------------------------
# POST /me/quiz-insights -- authenticated, persists into quizInsights
# ---------------------------------------------------------------------------


def test_happy_path_persists_under_the_quiz_groups_own_flat_key(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="qi_happy@example.com")
    _mock_openai_json(monkeypatch, SINGLE_QUIZ_MODEL_RESPONSE)

    resp = client.post(
        "/api/v1/me/quiz-insights",
        json={"quizGroup": "yourFutureYourWay", "quizzes": ONE_QUIZ},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["overallInsight"]["summary"].startswith("Across everything")
    assert body["insights"][0]["summary"].startswith("You are drawn")

    profile = client.get("/api/v1/me/profile").get_json()["profile"]
    stored = profile["quizInsights"]["yourFutureYourWay"]
    assert stored["summary"].startswith("You are drawn")
    # The model's cross-quiz synthesis is stored too, but under its own key --
    # it must never be mistaken for the quiz's own summary (see
    # agent_service._quiz_insights_section and test_agent_api.py's D-5 case).
    assert stored["overallInsight"]["summary"].startswith("Across everything")


def test_unauthenticated_is_rejected(client):
    resp = client.post(
        "/api/v1/me/quiz-insights",
        json={"quizGroup": "yourFutureYourWay", "quizzes": ONE_QUIZ},
    )
    assert resp.status_code == 401


def test_missing_quiz_group_is_a_422(client, monkeypatch):
    """`quizGroup` is a required schema field; a missing one never reaches the
    service's own 400 for an empty-but-present one (see the next test)."""
    csrf = _register_and_login(client, monkeypatch, email="qi_missing@example.com")

    resp = client.post(
        "/api/v1/me/quiz-insights",
        json={"quizzes": ONE_QUIZ},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 422
    assert "quizGroup" in {e["field"] for e in resp.get_json()["errors"]}


def test_empty_quiz_group_is_a_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="qi_empty_group@example.com")

    resp = client.post(
        "/api/v1/me/quiz-insights",
        json={"quizGroup": "", "quizzes": ONE_QUIZ},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 400


def test_empty_quizzes_is_a_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="qi_empty_quizzes@example.com")

    resp = client.post(
        "/api/v1/me/quiz-insights",
        json={"quizGroup": "yourFutureYourWay", "quizzes": []},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 400


def test_openai_failure_is_a_500_and_persists_nothing(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="qi_failure@example.com")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("boom")
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)

    resp = client.post(
        "/api/v1/me/quiz-insights",
        json={"quizGroup": "yourFutureYourWay", "quizzes": ONE_QUIZ},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 500
    profile = client.get("/api/v1/me/profile").get_json()["profile"]
    assert "quizInsights" not in profile


def test_career_quizzes_group_persists_as_sub_entry_not_flat(client, monkeypatch):
    """`careerQuizzes` is the one group stored per-sub-quiz rather than as a
    single flat document (insight_service.CAREER_QUIZ_GROUP)."""
    csrf = _register_and_login(client, monkeypatch, email="qi_career@example.com")
    _mock_openai_json(monkeypatch, {
        "overallInsight": {"summary": "Career synthesis."},
        "insights": [{
            "key": "earlyCareer",
            "title": "Quiz 1: Early Career",
            "summary": "Drawn to fast-moving, hands-on roles.",
        }],
    })

    resp = client.post(
        "/api/v1/me/quiz-insights",
        json={"quizGroup": "careerQuizzes", "quizzes": CAREER_QUIZZES_ITEM},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200

    profile = client.get("/api/v1/me/profile").get_json()["profile"]
    career = profile["quizInsights"]["careerQuizzes"]
    assert career["earlyCareer"]["summary"].startswith("Drawn to")
    assert career["_overallInsight"]["summary"] == "Career synthesis."


def test_stable_keys_round_trip_through_patch_and_get(client, monkeypatch):
    """Raw answers for all six quizzes, under their stable `quizResults` keys,
    survive a PATCH /me/profile -> GET /me/profile round trip.

    Corrects chunk D-1's audit: raw quiz answers do not evaporate today for an
    authenticated user. `quizResults` is allowlisted in
    `validators.ALLOWED_PROFILE_FIELDS`, and `profile_document.decompose`
    leaves any key it does not explicitly promote sitting in `profiles.extra`
    verbatim -- which is where all six of these keys already land.
    """
    csrf = _register_and_login(client, monkeypatch, email="qi_stable_keys@example.com")

    quiz_results = {
        "careerQuizzes": {
            "earlyCareer": {"1": 0, "2": 1},
            "careerTransition": {"1": 2},
            "midCareer": {"1": 3},
            "teenFocused": {"1": 0},
        },
        "yourFutureYourWay": {"1": 1},
        "careerJobSearch": {"1": 2},
    }

    resp = client.patch(
        "/api/v1/me/profile",
        json={"profile": {"quizResults": quiz_results}},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200

    profile = client.get("/api/v1/me/profile").get_json()["profile"]
    assert profile["quizResults"] == quiz_results


# ---------------------------------------------------------------------------
# POST /intake/quiz-preview/insights -- anonymous, never persists
# ---------------------------------------------------------------------------


def test_guest_preview_happy_path_returns_insight_and_persists_nothing(client, monkeypatch):
    _mock_openai_json(monkeypatch, SINGLE_QUIZ_MODEL_RESPONSE)

    resp = client.post(
        "/api/v1/intake/quiz-preview/insights",
        json={"quizGroup": "yourFutureYourWay", "quizzes": ONE_QUIZ},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["overallSummary"].startswith("Across everything")
    assert body["insights"][0]["summary"].startswith("You are drawn")


def test_guest_preview_missing_body_is_a_422(client):
    resp = client.post("/api/v1/intake/quiz-preview/insights", json={})
    assert resp.status_code == 422


def test_guest_preview_empty_quiz_group_is_a_400(client):
    resp = client.post(
        "/api/v1/intake/quiz-preview/insights",
        json={"quizGroup": "", "quizzes": ONE_QUIZ},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# The GuestQuiz -> account import path (D-5).
#
# `Login.tsx`'s pending-quiz-save handler on a successful login is two plain
# calls against endpoints that already exist: `PATCH /me/profile` with the
# raw answers captured while anonymous, then `POST /me/quiz-insights` with
# the same payload the guest preview used. There is no dedicated backend
# "import" endpoint -- this replays that exact sequence against a freshly
# registered account and proves both halves land, and that the agent context
# picks up the result afterward.
# ---------------------------------------------------------------------------


def test_guest_quiz_import_sequence_persists_results_and_insight(client, monkeypatch):
    email = "qi_guest_import@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _mock_openai_json(monkeypatch, SINGLE_QUIZ_MODEL_RESPONSE)

    # What Login.tsx sends first: the raw answers, captured while anonymous.
    patch_resp = client.patch(
        "/api/v1/me/profile",
        json={"profile": {"quizResults": {"yourFutureYourWay": {"1": 0}}}},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert patch_resp.status_code == 200

    # What Login.tsx sends second: the guest's own quizPayload, replayed now
    # that there is a session to attach it to.
    insight_resp = client.post(
        "/api/v1/me/quiz-insights",
        json={"quizGroup": "yourFutureYourWay", "quizzes": ONE_QUIZ},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert insight_resp.status_code == 200

    profile = client.get("/api/v1/me/profile").get_json()["profile"]
    assert profile["quizResults"]["yourFutureYourWay"] == {"1": 0}
    assert profile["quizInsights"]["yourFutureYourWay"]["summary"].startswith("You are drawn")

    from app import app
    from model import User
    from solverah.services import agent_service

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        context = agent_service.build_agent_context(user)

    assert "## Quiz Insights" in context
    assert "You are drawn to roles with visible growth trajectories." in context
