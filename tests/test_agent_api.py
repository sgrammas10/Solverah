import json
import pytest
from collections import OrderedDict
from unittest.mock import MagicMock


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="agent@example.com", password="Strongpass1!"):
    """Register a user, confirm email, log in, and return the CSRF token."""
    import app as app_module

    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Agent User", "role": "job-seeker", "terms_accepted": True},
    )

    # Confirm email so login succeeds
    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200
    csrf = resp.get_json()["csrfToken"]
    return csrf


def _mock_llm_streaming(monkeypatch, reply_text="I can help with that."):
    """Patch _get_agent_client to return a mock that streams reply_text word by word."""
    import app as app_module

    words = reply_text.split()
    chunks = []
    for i, word in enumerate(words):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = word + (" " if i < len(words) - 1 else "")
        chunks.append(chunk)

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter(chunks)
    monkeypatch.setattr("solverah.infra.llm.get_agent_client", lambda: mock_client)
    return mock_client


def _parse_sse(data: bytes) -> list[dict]:
    """Parse SSE response body into a list of event dicts."""
    events = []
    for line in data.decode().split("\n\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload:
                events.append(json.loads(payload))
    return events


def test_agent_chat_unauthenticated(client):
    resp = client.post("/api/v1/agent/messages", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 401


def test_agent_chat_missing_messages(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_llm_streaming(monkeypatch)

    resp = client.post(
        "/api/v1/agent/messages",
        json={},
        headers={"X-CSRF-TOKEN": csrf},
    )
    # 422, not the 400 the handler used to answer with. Phase 1b turned the
    # declared schema into an enforced one, so a missing required field is
    # rejected before the handler runs and reported as a problem document with
    # the offending field named -- which the hand-written 400 could not do.
    assert resp.status_code == 422
    assert "messages" in {e["field"] for e in resp.get_json()["errors"]}


def test_agent_chat_empty_messages(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_llm_streaming(monkeypatch)

    resp = client.post(
        "/api/v1/agent/messages",
        json={"messages": []},
        headers={"X-CSRF-TOKEN": csrf},
    )
    # An empty history is a schema violation now (`min_length=1`), not a
    # hand-rolled check inside the handler.
    assert resp.status_code == 422


def test_agent_chat_success(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    mock_client = _mock_llm_streaming(monkeypatch, reply_text="Here are some career tips.")

    resp = client.post(
        "/api/v1/agent/messages",
        json={"messages": [{"role": "user", "content": "What should I focus on?"}], "model": "test-model"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type

    events = _parse_sse(resp.data)
    done_event = next((e for e in events if e.get("done")), None)
    assert done_event is not None
    assert done_event["model"] == "test-model"

    full_reply = "".join(e.get("chunk", "") for e in events)
    assert "career tips" in full_reply

    # Ensure Groq was called with a system message prepended
    call_args = mock_client.chat.completions.create.call_args
    messages_sent = call_args.kwargs.get("messages") or call_args.kwargs["messages"]
    assert messages_sent[0]["role"] == "system"
    assert "Solverah AI" in messages_sent[0]["content"]


def test_agent_chat_without_model_uses_env_override(client, monkeypatch):
    """No client model -> SOLVERAH_AGENT_MODEL is what Groq is asked for."""
    csrf = _register_and_login(client, monkeypatch)
    mock_client = _mock_llm_streaming(monkeypatch)
    monkeypatch.setenv("SOLVERAH_AGENT_MODEL", "override/model")

    resp = client.post(
        "/api/v1/agent/messages",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "override/model"


def test_agent_chat_without_model_never_asks_for_the_retired_one(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    mock_client = _mock_llm_streaming(monkeypatch)
    monkeypatch.delenv("SOLVERAH_AGENT_MODEL", raising=False)

    resp = client.post(
        "/api/v1/agent/messages",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "openai/gpt-oss-20b"


def test_agent_chat_gpt_oss_asks_for_low_reasoning_effort(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    mock_client = _mock_llm_streaming(monkeypatch)
    monkeypatch.delenv("SOLVERAH_AGENT_MODEL", raising=False)

    resp = client.post(
        "/api/v1/agent/messages",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    assert mock_client.chat.completions.create.call_args.kwargs["reasoning_effort"] == "low"


def test_agent_chat_other_models_get_no_reasoning_effort(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    mock_client = _mock_llm_streaming(monkeypatch)

    resp = client.post(
        "/api/v1/agent/messages",
        json={"messages": [{"role": "user", "content": "hi"}], "model": "mistral"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    assert "reasoning_effort" not in mock_client.chat.completions.create.call_args.kwargs


def test_agent_chat_custom_model(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _mock_llm_streaming(monkeypatch)

    resp = client.post(
        "/api/v1/agent/messages",
        json={"messages": [{"role": "user", "content": "hi"}], "model": "mistral"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.data)
    done_event = next((e for e in events if e.get("done")), None)
    assert done_event is not None
    assert done_event["model"] == "mistral"


def test_agent_chat_groq_unavailable(client, monkeypatch):
    import app as app_module

    csrf = _register_and_login(client, monkeypatch)

    def _raise_connection(*_a, **_kw):
        raise ConnectionRefusedError("Connection refused")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _raise_connection
    monkeypatch.setattr("solverah.infra.llm.get_agent_client", lambda: mock_client)

    resp = client.post(
        "/api/v1/agent/messages",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 503


def test_fetch_resume_text_caches_s3_result(monkeypatch):
    from solverah.services import agent_service

    # Isolate cache state for this test. Must be an OrderedDict, not {}: the
    # cache is LRU since 2026-09-08 and the code calls move_to_end/popitem on
    # it, which a plain dict does not have. See tests/test_cache_bounds.py.
    monkeypatch.setattr("solverah.services.agent_service._resume_cache", OrderedDict())
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"resume bytes")}
    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: mock_s3)
    monkeypatch.setattr("solverah.services.resume_service.extract_resume_text",
                        lambda _path, _mime: "Extracted resume text")

    profile = {
        "resumeKey": "users/1/resume.pdf",
        "uploadedResume": {"type": "application/pdf"},
    }

    first = agent_service.fetch_resume_text(profile)
    second = agent_service.fetch_resume_text(profile)

    assert first == "Extracted resume text"
    assert second == "Extracted resume text"
    assert mock_s3.get_object.call_count == 1  # S3 hit only on first call


def test_agent_chat_includes_resume_in_context(client, monkeypatch):
    import app as app_module

    csrf = _register_and_login(client, monkeypatch)
    mock_client = _mock_llm_streaming(monkeypatch)
    monkeypatch.setattr("solverah.services.agent_service.fetch_resume_text",
                        lambda _: "Worked at Acme Corp as engineer.")

    client.post(
        "/api/v1/agent/messages",
        json={"messages": [{"role": "user", "content": "Review my resume"}]},
        headers={"X-CSRF-TOKEN": csrf},
    )

    call_args = mock_client.chat.completions.create.call_args
    system_msg = call_args.kwargs["messages"][0]["content"]
    assert "Acme Corp" in system_msg


# ---------------------------------------------------------------------------
# D-1 (docs/BUILD_PLAN.md): FocusType, ManagerMatch, and quiz-insight context
# ---------------------------------------------------------------------------
#
# These build the context directly (`agent_service.build_agent_context`)
# rather than through the chat SSE endpoint, so assertions can check for the
# presence/absence of specific instrument fields without parsing an event
# stream. Every instrument result is produced through its real submit path
# (or, for `manager_match` -- scored off the request path since Phase 3c --
# seeded the same way `test_manager_match_api.py::test_get_results_happy_path`
# seeds it), never hand-built to match what the code happens to read.

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


def _build_context(email):
    from app import app
    from model import User
    from solverah.services import agent_service

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        return agent_service.build_agent_context(user)


def test_agent_context_includes_focus_type_archetype_and_recommendations(client, monkeypatch):
    email = "agent_ft@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)

    resp = client.post(
        "/api/v1/assessments/focus_type/submissions",
        json=FOCUS_TYPE_PAYLOAD,
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    result = resp.get_json()

    context = _build_context(email)

    assert "## FocusType" in context
    assert result["archetype"] in context
    assert result["recommendations"][0] in context
    # Task D-1 scopes FocusType context to archetype + recommendations only --
    # the dimension scores it also returns must not leak into the prompt.
    assert "dimension_scores" not in context
    for dim, score in result["dimension_scores"].items():
        assert "%s: %s" % (dim, score) not in context


def test_agent_context_absent_when_focus_type_not_taken(client, monkeypatch):
    email = "agent_ft_absent@example.com"
    _register_and_login(client, monkeypatch, email=email)

    context = _build_context(email)

    assert "## FocusType" not in context


def test_agent_context_includes_manager_match_archetype_and_dimension_summary(client, monkeypatch):
    email = "agent_mm@example.com"
    _register_and_login(client, monkeypatch, email=email)

    from app import app
    from model import User, db
    from solverah.domain import auth as auth_domain
    from solverah.repositories import assessment_repository
    from solverah.services import assessment_service

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        submission = assessment_repository.open_current(
            user.id, "manager_match", assessment_service.CLIENT_FORM_VERSION
        )
        submission.result = {
            "archetype": "The Autonomist",
            "dimension_scores": {
                "autonomy": 0.8, "feedback_style": 0.3,
                "relationship": 0.5, "growth_focus": 0.6,
            },
            "narrative": "You want minimal check-ins and clear ownership of outcomes.",
            "what_to_look_for": ["Ask about decision rights"],
            "red_flags": ["Daily status reports"],
            "archetype_description": "You thrive with autonomy.",
        }
        submission.narrative = submission.result["narrative"]
        submission.status = "scored"
        submission.completed_at = submission.scored_at = auth_domain.utcnow()
        db.session.commit()

    context = _build_context(email)

    assert "## ManagerMatch" in context
    assert "The Autonomist" in context
    assert "autonomy: 0.80" in context
    # D-1 scopes ManagerMatch context to archetype + dimension summary only --
    # the LLM narrative is a separate, larger disclosure this section must not
    # carry.
    assert "minimal check-ins" not in context


def test_agent_context_absent_when_manager_match_not_taken(client, monkeypatch):
    email = "agent_mm_absent@example.com"
    _register_and_login(client, monkeypatch, email=email)

    context = _build_context(email)

    assert "## ManagerMatch" not in context


def test_agent_context_includes_quiz_insights(client, monkeypatch):
    email = "agent_qi@example.com"
    _register_and_login(client, monkeypatch, email=email)

    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile_repository.update_document(
            user.id,
            lambda existing: {
                **existing,
                "quizInsights": {
                    "careerQuizzes": {
                        "_generatedAt": "2026-09-08T00:00:00Z",
                        "_model": "gpt-4o-mini",
                        "earlyCareer": {
                            "title": "Early Career",
                            "summary": "Drawn to fast-moving, hands-on roles.",
                            "keyTakeaways": ["Values variety"],
                        },
                    },
                    "yourFutureYourWay": {
                        "title": "Your Future, Your Way",
                        "summary": "Leaning toward creative, people-facing work.",
                    },
                },
            },
        )
        db.session.commit()

    context = _build_context(email)

    assert "## Quiz Insights" in context
    assert "Drawn to fast-moving, hands-on roles." in context
    assert "Leaning toward creative, people-facing work." in context


def test_agent_context_absent_when_no_quiz_insights_generated(client, monkeypatch):
    email = "agent_qi_absent@example.com"
    _register_and_login(client, monkeypatch, email=email)

    context = _build_context(email)

    assert "## Quiz Insights" not in context


def test_agent_context_flat_quiz_summary_survives_a_dict_shaped_overall_insight(client, monkeypatch):
    """D-5 (docs/BUILD_PLAN.md): a flat single-group quiz's own ``summary`` must
    win over its ``overallInsight``, even though the latter is also a dict.

    ``insight_service._single_group_store`` stores the model's cross-quiz
    synthesis as ``overallInsight`` -- a dict with no leading underscore, on
    the same group document as the quiz's own flat ``summary``. The prior
    version of ``_quiz_insights_section`` treated "any dict-valued, non-
    underscore key" as a sub-entry list, so it read ``overallInsight`` as one
    and reported its synthesis text in place of the quiz's own summary.
    """
    email = "agent_qi_flat_overall@example.com"
    _register_and_login(client, monkeypatch, email=email)

    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile_repository.update_document(
            user.id,
            lambda existing: {
                **existing,
                "quizInsights": {
                    "yourFutureYourWay": {
                        "title": "Your Future, Your Way",
                        "summary": "You are drawn to creative, people-facing work.",
                        "overallInsight": {
                            "summary": "Cross-quiz synthesis text that must not leak here.",
                            "keyTakeaways": ["Growth-oriented"],
                        },
                        "generatedAt": "2026-09-10T00:00:00Z",
                        "model": "gpt-4o-mini",
                    },
                },
            },
        )
        db.session.commit()

    context = _build_context(email)

    assert "## Quiz Insights" in context
    assert "You are drawn to creative, people-facing work." in context
    assert "Cross-quiz synthesis text that must not leak here." not in context


def test_agent_context_includes_quiz_insights_nested_under_career_quizzes(client, monkeypatch):
    """The in-app authenticated submit flow for `yourFutureYourWay` and
    `careerJobSearch` posts `quizGroup: "careerQuizzes"`, which nests their
    insight as a sub-entry of the `careerQuizzes` group rather than under
    their own flat key -- deliberate, so `QuizInsights.tsx`'s combined
    `?group=careerQuizzes` view shows all six quizzes together. The generic
    sub-entry handling in `_quiz_insights_section` must still surface it.
    """
    email = "agent_qi_nested@example.com"
    _register_and_login(client, monkeypatch, email=email)

    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile_repository.update_document(
            user.id,
            lambda existing: {
                **existing,
                "quizInsights": {
                    "careerQuizzes": {
                        "_overallInsight": {"summary": "Career-wide synthesis."},
                        "_generatedAt": "2026-09-10T00:00:00Z",
                        "_model": "gpt-4o-mini",
                        "careerJobSearch": {
                            "title": "Career & Job Search",
                            "summary": "Actively exploring a lateral move.",
                        },
                    },
                },
            },
        )
        db.session.commit()

    context = _build_context(email)

    assert "## Quiz Insights" in context
    assert "Actively exploring a lateral move." in context
    assert "Career-wide synthesis." not in context


def test_agent_context_degrades_gracefully_with_no_instruments(client, monkeypatch):
    """No FocusType, no ManagerMatch, no quiz insights: absence, not a stub.

    The replaced TODO used to hard-code a "coming soon" placeholder
    regardless of what was true for the user; the replacement omits the
    section outright rather than asserting anything false.
    """
    email = "agent_none@example.com"
    _register_and_login(client, monkeypatch, email=email)

    context = _build_context(email)

    assert "## FocusType" not in context
    assert "## ManagerMatch" not in context
    assert "## Quiz Insights" not in context
    assert "coming soon" not in context.lower()
    assert "not yet available" not in context.lower()


def test_agent_context_system_prompt_has_a_no_recitation_guardrail(client, monkeypatch):
    email = "agent_guardrail@example.com"
    _register_and_login(client, monkeypatch, email=email)

    context = _build_context(email)

    assert "not to be recited" in context or "not to be recited back" in context


def test_agent_context_never_includes_core_person_side_scores(client, monkeypatch):
    """D-15 (docs/PRODUCT_DECISIONS.md / docs/BUILD_PLAN.md A-4): `core`'s six
    person-side dimension scores must never reach the agent's context, because
    the chat is a surface a retaker could otherwise use to interrogate them.

    Completes a real `core` sitting through the shuffled, token-based form --
    the same path a real respondent takes, via `assessment_form`/
    `assessment_store` -- rather than hand-building a result dict, so this
    proves the guarantee holds for the real submission path.
    `profile_repository.load_document` never assembles a `core` result into
    the document at all (only `focus_type_result` and `manager_match_result`
    are merged in from `assessment_submissions`), which is what makes the
    guarantee hold; this test is the regression check on that fact.
    """
    email = "agent_core@example.com"
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")
    csrf = _register_and_login(client, monkeypatch, email=email)

    form = client.get("/api/v1/assessments/core/form")
    assert form.status_code == 200
    responses = {
        item["token"]: item["options"][0]["key"]
        for block in form.get_json()["blocks"]
        for item in block["items"]
    }
    submit = client.post(
        "/api/v1/assessments/core/submissions",
        json={"responses": responses},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert submit.status_code == 200

    from app import app
    from model import User
    from solverah.repositories import profile_repository

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        document = profile_repository.load_document(user.id)
        # No key of any spelling carries a core/work_pulse result into the
        # document -- the guarantee this test exists to protect.
        assert "core_result" not in document
        assert "work_pulse_result" not in document

    context = _build_context(email)

    for dimension in ("autonomy", "pace", "collaboration", "feedback", "innovation", "decision"):
        assert dimension not in context.lower()
