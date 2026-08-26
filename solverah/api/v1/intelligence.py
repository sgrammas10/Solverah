"""Path intelligence, job recommendations, the AI agent, and quiz insights.

Paths unchanged: ``/intelligence/path-preferences``,
``/intelligence/path-suggestions``, ``/recommendations`` (GET and POST),
``/agent/chat``, ``/quiz-insights``, ``/quiz-insights-guest``.

The agent handler stays fatter than the others on purpose: it maps provider
exceptions onto three different status codes and then returns a streaming
response, and both halves are HTTP concerns.  The context assembly it depends on
is in ``solverah/services/agent_service.py``.
"""

from __future__ import annotations

import json

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    stream_with_context,
)
from flask_jwt_extended import get_jwt_identity, jwt_required

from solverah.extensions import limiter
from solverah.infra import llm
from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import LegacyError
from solverah.schemas.intelligence import (
    AgentChatRequest,
    PathPreferencesRequest,
    PathPreferencesResponse,
    PathSuggestionsResponse,
    QuizInsightsGuestResponse,
    QuizInsightsRequest,
    QuizInsightsResponse,
    RecommendationsResponse,
)
from solverah.services import agent_service, insight_service, intelligence_service

__all__ = ["intelligence_bp"]

intelligence_bp = Blueprint("intelligence", __name__)

_AUTHENTICATED = ["accessTokenCookie"]
_AUTHENTICATED_WRITE = ["accessTokenCookie", "csrfHeader"]

#: Substrings that identify a provider connectivity failure rather than a bad
#: request. Matched against both the exception type name and its message,
#: because the SDK surfaces the same condition either way depending on version.
_CONNECTION_MARKERS = (
    "connection",
    "refused",
    "timeout",
    "unreachable",
    "apiconnection",
)


def _current_user():
    return user_repository.find_by_email(get_jwt_identity())


def _respond(result):
    return jsonify(result.body), result.status


@document(
    "Generate and persist AI career insights",
    tags=["intelligence"],
    request=QuizInsightsRequest,
    responses={200: QuizInsightsResponse, 400: LegacyError, 404: LegacyError, 500: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@intelligence_bp.route("/quiz-insights", methods=["POST"])
@limiter.limit("10 per minute")
@jwt_required()
def quiz_insights():
    """POST /quiz-insights - Generate and persist AI career insights.

    Validates and normalizes the quiz answers, calls OpenAI with a structured
    prompt, coerces the response to a canonical schema, and persists the
    insights into profile_data.quizInsights.
    """
    return _respond(
        insight_service.generate_for_user(
            _current_user(), request.get_json(silent=True) or {}, current_app.logger
        )
    )


@document(
    "Generate AI career insights for an unauthenticated preview",
    tags=["intelligence"],
    request=QuizInsightsRequest,
    responses={200: QuizInsightsGuestResponse, 400: LegacyError, 500: LegacyError},
    security=[],
)
@intelligence_bp.route("/quiz-insights-guest", methods=["POST"])
@limiter.limit("1 per day")
def quiz_insights_guest():
    """POST /quiz-insights-guest - Generate AI insights for unauthenticated preview.

    Same logic as /quiz-insights but requires no JWT. Hard-limited to 1 request
    per day per IP to reduce OpenAI spend. Insights are NOT persisted to any
    user profile.
    """
    return _respond(
        insight_service.generate_for_guest(
            request.get_json(silent=True) or {}, current_app.logger
        )
    )


@document(
    "List persisted job recommendations",
    tags=["intelligence"],
    responses={200: RecommendationsResponse},
    security=_AUTHENTICATED,
)
@intelligence_bp.route("/recommendations", methods=["GET"])
@limiter.limit("30 per minute")
@jwt_required()
def get_recommendations():
    """GET /recommendations - Return persisted job recommendations for the user.

    The ML pipeline that generated these has been replaced by the AI agent.
    Returns an empty list until a Groq-based recommendation flow is wired up.
    """
    return jsonify({"recommendations": []})


@document(
    "Trigger job recommendation generation",
    tags=["intelligence"],
    responses={200: RecommendationsResponse},
    security=_AUTHENTICATED_WRITE,
)
@intelligence_bp.route("/recommendations", methods=["POST"])
@limiter.limit("10 per minute")
@jwt_required()
def generate_recommendations():
    """POST /recommendations - Trigger job recommendation generation.

    Accepts a profilePipeline payload but is currently a no-op stub while the
    Groq-based recommendation flow is being built.
    """
    return jsonify({"recommendations": []})


@document(
    "Stream a chat turn from the AI agent",
    tags=["intelligence"],
    request=AgentChatRequest,
    responses={400: LegacyError, 422: LegacyError, 500: LegacyError, 503: LegacyError},
    security=_AUTHENTICATED_WRITE,
    description=(
        "Responds with `text/event-stream`, not JSON: one `data: {\"chunk\": ...}` "
        "frame per token, then `data: {\"done\": true, \"model\": ...}`. A failure "
        "that happens mid-stream is delivered as a `data: {\"error\": ...}` frame "
        "on a 200, because the status line has already been sent."
    ),
)
@intelligence_bp.route("/agent/chat", methods=["POST"])
@limiter.limit("30 per minute")
@jwt_required()
def agent_chat():
    """POST /agent/chat - Stream a chat turn from Groq with RAG context.

    Assembles a system prompt from the authenticated user's profile and company
    data, prepends it to the supplied message history, and streams the response
    as Server-Sent Events so the UI can render tokens as they arrive.
    """
    from flask import abort

    user = _current_user()
    if user is None:
        # first_or_404() in the original.
        abort(404)

    data = request.get_json(silent=True) or {}
    messages = data.get("messages")
    if not messages or not isinstance(messages, list) or len(messages) == 0:
        return jsonify({"error": "messages must be a non-empty list"}), 400

    model = (data.get("model") or llm.default_agent_model()).strip()
    resume_text = agent_service.fetch_resume_text(user.profile_data or {})
    system_prompt = agent_service.build_agent_context(user, resume_text=resume_text)
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    try:
        client = llm.get_agent_client()
        stream = client.chat.completions.create(
            model=model, messages=full_messages, stream=True
        )
    except Exception as exc:  # noqa: BLE001 -- mapped onto statuses below
        current_app.logger.error("agent_chat error: %s: %s", type(exc).__name__, exc)
        exc_type = type(exc).__name__.lower()
        exc_str = str(exc).lower()
        if "not found" in exc_str or "notfounderror" in exc_type:
            return jsonify({"error": "Model '%s' not found on Groq." % model}), 422
        if any(kw in exc_str or kw in exc_type for kw in _CONNECTION_MARKERS):
            return jsonify({"error": "AI service unavailable — Groq"}), 503
        return jsonify({"error": "Failed to generate response"}), 500

    def generate():
        try:
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield "data: %s\n\n" % json.dumps({"chunk": delta})
            yield "data: %s\n\n" % json.dumps({"done": True, "model": model})
        except Exception as exc:  # noqa: BLE001 -- the status line is already sent
            current_app.logger.error(
                "agent_chat stream error: %s: %s", type(exc).__name__, exc
            )
            yield "data: %s\n\n" % json.dumps({"error": "Stream interrupted"})

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        # X-Accel-Buffering tells nginx not to buffer the stream; without it the
        # proxy holds tokens back and the UI renders the whole reply at once,
        # which defeats the point of streaming.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@document(
    "Save the user's career search preferences",
    tags=["intelligence"],
    request=PathPreferencesRequest,
    responses={200: PathPreferencesResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@intelligence_bp.route("/intelligence/path-preferences", methods=["POST"])
@jwt_required()
def save_path_preferences():
    """POST /intelligence/path-preferences - Save career search preferences."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        intelligence_service.save_path_preferences(user, request.get_json() or {})
    )


@document(
    "Score and narrate career path suggestions",
    tags=["intelligence"],
    responses={200: PathSuggestionsResponse, 400: LegacyError, 404: LegacyError, 500: LegacyError},
    security=_AUTHENTICATED,
)
@intelligence_bp.route("/intelligence/path-suggestions", methods=["GET"])
@jwt_required()
def path_suggestions():
    """GET /intelligence/path-suggestions - Score and narrate career path suggestions.

    Orchestrates path_scoring.score_paths and path_narrative.generate_narratives,
    caching the result per user. The cache is invalidated when the user's
    WorkPulse results, experience entries, or ManagerMatch results are updated.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(intelligence_service.path_suggestions(user, current_app.logger))
