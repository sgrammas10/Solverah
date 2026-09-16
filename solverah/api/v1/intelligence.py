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

from security import (
    GUEST_INSIGHTS_GLOBAL_LIMIT,
    GUEST_INSIGHTS_PER_IP_LIMIT,
    global_rate_limit_key,
)
from solverah.errors import NotFoundError
from solverah.extensions import limiter
from solverah.infra import llm
from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import LegacyError
from solverah.schemas.intelligence import (
    AgentChatRequest,
    AgentMessagesRequest,
    PathPreferencesDocument,
    PathPreferencesPutRequest,
    PathPreferencesRequest,
    PathFitResponse,
    PathSuggestionJobAccepted,
    PathSuggestionJobStatus,
    RecommendationsPage,
    PathPreferencesResponse,
    PathSuggestionsResponse,
    QuizInsightsGuestResponse,
    QuizInsightsRequest,
    QuizInsightsResponse,
    RecommendationsResponse,
)
from solverah.services import (
    agent_service,
    insight_service,
    intelligence_service,
    scoring_jobs,
)

__all__ = ["intelligence_bp"]

intelligence_bp = Blueprint("intelligence", __name__)

_AUTHENTICATED = ["accessTokenCookie"]
_AUTHENTICATED_WRITE = ["accessTokenCookie", "csrfHeader"]

#: Shared rate-limit buckets, so a superseded path and its replacement count
#: into one budget while both are live. ``shared_limit``, not ``limit(scope=)``
#: -- the latter keys as ``"{endpoint}:{scope}"`` and would leave two.
_SCOPE_QUIZ_INSIGHTS = "intelligence:quiz-insights"
_SCOPE_RECOMMENDATIONS_REFRESH = "intelligence:recommendations-refresh"
_SCOPE_RECOMMENDATIONS_READ = "intelligence:recommendations-read"
_SCOPE_AGENT = "intelligence:agent"
_SCOPE_PATH_SUGGESTION_JOBS = "intelligence:path-suggestion-jobs"
_SCOPE_PATH_FIT = "intelligence:path-fit"

#: See ``solverah/api/v1/assessments.py`` for why a poll does not run on the
#: global defaults, and why the day cap is restated rather than dropped.
POLL_LIMIT = "60 per minute;2000 per day"
_SCOPE_GUEST_INSIGHTS = "intake:quiz-preview-insights"
_SCOPE_GUEST_INSIGHTS_GLOBAL = "intake:quiz-preview-insights:global"

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


def _do_agent_stream():
    """The agent handler body, shared by both routes.

    Not called as ``agent_chat()`` from the Part 5.2 view: that name is bound to
    the ``@limiter.shared_limit`` wrapper, so calling it would charge the shared
    30-per-minute bucket twice for one request and quietly halve the allowance
    on whichever path delegated. See ``solverah/api/v1/auth.py`` for the same
    trap and the test that caught it.
    """
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
    resume_text = agent_service.resume_text_for(user)
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
    "Read the user's career search preferences",
    tags=["me"],
    responses={200: PathPreferencesDocument, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@intelligence_bp.route("/me/path-preferences", methods=["GET"])
@jwt_required()
def get_path_preferences():
    """GET /me/path-preferences - the three saved preferences, or nulls.

    New in Phase 1b: the endpoint this pairs with was write-only, so a client
    wanting to show the user their own answers had to keep a copy or read them
    out of the profile blob.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(intelligence_service.read_path_preferences(user))


@document(
    "Replace the user's career search preferences",
    tags=["me"],
    request=PathPreferencesPutRequest,
    responses={200: PathPreferencesDocument, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
)
@intelligence_bp.route("/me/path-preferences", methods=["PUT"])
@jwt_required()
def put_path_preferences():
    """PUT /me/path-preferences - write all three preferences.

    PUT rather than the POST this replaces, because the write replaces the whole
    set rather than merging into it. Returns the saved document instead of
    `{"message": "Preferences saved"}`, so a client does not have to make a
    second call to see what it stored.

    Each value is checked against a closed set: the path scorer branches on all
    three, so an unrecognised one would silently change ranking rather than fail.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    saved = intelligence_service.save_path_preferences(
        user, request.get_json(silent=True) or {}
    )
    if not saved.ok:
        return _respond(saved)
    return _respond(intelligence_service.read_path_preferences(user))


@document(
    "Read the cached career path suggestions",
    tags=["me"],
    responses={200: PathSuggestionsResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "Serves the per-user cache that a succeeded path-suggestion job "
        "populates; the cache is invalidated when Work Pulse results, "
        "experience entries, or ManagerMatch results change.\n\n"
        "A miss is `404` and computes nothing: the problem document's "
        "`start_job_url` names `POST /me/path-suggestion-jobs`, which queues "
        "the O*NET and OpenAI fan-out this route performed inline before "
        "Phase 3c and whose poll returns the same payload this serves."
    ),
)
@intelligence_bp.route("/me/path-suggestions", methods=["GET"])
@jwt_required()
def get_path_suggestions():
    """GET /me/path-suggestions - the cached suggestions, and only the cache.

    Until Phase 3c a miss here ran the whole O*NET and OpenAI fan-out inside
    the request -- the handler `gunicorn.conf.py`'s 120-second timeout was
    raised for. The SPA moved to the job pair in 43a2024, so a miss now answers
    404 with a pointer at the enqueue instead of computing. Deliberately not a
    202: nothing was queued on the client's behalf, and a job the client did
    not start is a job it does not know to poll.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    cached = intelligence_service.cached_path_suggestions(user)
    if cached is None:
        raise NotFoundError(
            detail=(
                "No cached path suggestions. Queue a scoring at "
                "POST /me/path-suggestion-jobs and poll the job; its result "
                "is the payload this route serves."
            ),
            errors=[{"field": "cache", "code": "not_generated"}],
            extra={"start_job_url": "/me/path-suggestion-jobs"},
        )
    return _respond(cached)


@document(
    "Generate and persist AI career insights",
    tags=["me"],
    request=QuizInsightsRequest,
    responses={200: QuizInsightsResponse, 400: LegacyError, 404: LegacyError, 500: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
)
@intelligence_bp.route("/me/quiz-insights", methods=["POST"])
@limiter.shared_limit("10 per minute", scope=_SCOPE_QUIZ_INSIGHTS)
@jwt_required()
def post_my_quiz_insights():
    """POST /me/quiz-insights - generate and persist AI career insights.

    Validates and normalizes the quiz answers, calls OpenAI with a structured
    prompt, coerces the response to a canonical schema, and persists the result
    into profile_data.quizInsights.
    """
    return _respond(
        insight_service.generate_for_user(
            _current_user(), request.get_json(silent=True) or {}, current_app.logger
        )
    )


@document(
    "List persisted job recommendations",
    tags=["me"],
    responses={200: RecommendationsPage},
    security=_AUTHENTICATED,
    enforce=True,
)
@intelligence_bp.route("/me/recommendations", methods=["GET"])
@limiter.shared_limit("30 per minute", scope=_SCOPE_RECOMMENDATIONS_READ)
@jwt_required()
def get_my_recommendations():
    """GET /me/recommendations - a page of job recommendations.

    Always empty today: the ML pipeline that produced these was replaced by the
    AI agent and the Groq-backed replacement is not wired up.

    Paginated anyway, and that is deliberate. The envelope is the contract, so
    the day this starts returning rows is not the day every client changes.
    """
    return jsonify({"data": [], "next_cursor": None})


@document(
    "Trigger job recommendation generation",
    tags=["me"],
    responses={200: RecommendationsPage},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
)
@intelligence_bp.route("/me/recommendations/refresh", methods=["POST"])
@limiter.shared_limit("10 per minute", scope=_SCOPE_RECOMMENDATIONS_REFRESH)
@jwt_required()
def refresh_my_recommendations():
    """POST /me/recommendations/refresh - trigger recommendation generation.

    A no-op stub while the Groq-based flow is being built. Part 5.2 has this
    answering 202 with a job handle; that arrives with Phase 3's queue, at which
    point there is real work for the handle to refer to.
    """
    return jsonify({"data": [], "next_cursor": None})


@document(
    "Stream a chat turn from the AI agent",
    tags=["agent"],
    request=AgentMessagesRequest,
    responses={400: LegacyError, 422: LegacyError, 500: LegacyError, 503: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Responds with `text/event-stream`, not JSON: one `data: {\"chunk\": ...}` "
        "frame per token, then `data: {\"done\": true, \"model\": ...}`. A failure "
        "that happens mid-stream is delivered as a `data: {\"error\": ...}` frame "
        "on a 200, because the status line has already been sent."
    ),
)
@intelligence_bp.route("/agent/messages", methods=["POST"])
@limiter.shared_limit("30 per minute", scope=_SCOPE_AGENT)
@jwt_required()
def agent_messages():
    """POST /agent/messages - stream a chat turn from Groq with RAG context.

    Assembles a system prompt from the authenticated user's profile and company
    data, prepends it to the supplied message history, and streams the response
    as Server-Sent Events so the UI can render tokens as they arrive.

    The `messages must be a non-empty list` branch the handler this replaces
    carried is gone: `enforce=True` and `min_length=1` on the model reject an
    empty history before the handler runs, in the Problem Details shape rather
    than a bespoke 400 body.
    """
    return _do_agent_stream()


# ---------------------------------------------------------------------------
# Phase 3b/3c -- path suggestions off the request path
# ---------------------------------------------------------------------------
#
# `GET /me/path-suggestions` used to fan out to O*NET and OpenAI inside the
# request. It and assessment scoring were the two handlers `gunicorn.conf.py`'s
# 120-second timeout was raised for. 3b added this job pair alongside the GET;
# 3c cut the GET down to a cache read once the frontend had moved (43a2024), so
# the fan-out below is the only way the scoring runs.


@document(
    "Queue a path-suggestion scoring and return a job handle",
    tags=["me"],
    responses={202: PathSuggestionJobAccepted, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    request_required=False,
    description=(
        "The only way path suggestions are computed since Phase 3c. Queues the "
        "O*NET and OpenAI fan-out and answers `202` with a job handle; poll "
        "`GET /me/path-suggestion-jobs/{job_id}` until `status` is `succeeded` "
        "or `failed`.\n\n"
        "A succeeded job warms the per-user cache `GET /me/path-suggestions` "
        "serves, so the payload can be re-read there without paying for the "
        "scoring twice.\n\n"
        "Rate limited, and the cache-reading `GET` is not: an enqueue returns "
        "immediately and can be issued in a loop, so the budget that bounds "
        "provider spend has to live here (A9)."
    ),
)
@intelligence_bp.route("/me/path-suggestion-jobs", methods=["POST"])
@limiter.shared_limit("10 per minute", scope=_SCOPE_PATH_SUGGESTION_JOBS)
@jwt_required()
def post_my_path_suggestion_job():
    """POST /me/path-suggestion-jobs - queue the scoring, return 202.

    **This route carries a limit the GET it feeds does not, and that is
    deliberate rather than an oversight in one of them.** Since 3c the GET is a
    cache read that reaches no provider, so there is nothing there for a budget
    to bound. An enqueue returns in milliseconds, so a loop issues hundreds;
    and each one that a worker picks up before the first has populated the
    cache is a full O*NET and OpenAI fan-out at full cost. A9's principle is
    that the budget bounds provider spend -- this is the only door to the
    spend, so this is where the budget lives.

    10 per minute, matching `POST /me/recommendations/refresh`: the other
    authenticated operation whose whole purpose is to ask the server to
    regenerate something expensive.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    job = scoring_jobs.create_path_suggestions(user)
    job_id = job.public_id.hex
    return (
        jsonify(
            {
                "job_id": job_id,
                "status": job.status,
                "status_url": "/me/path-suggestion-jobs/%s" % job_id,
            }
        ),
        202,
    )


@document(
    "Report the state of a queued path-suggestion scoring",
    tags=["me"],
    responses={200: PathSuggestionJobStatus, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@intelligence_bp.route("/me/path-suggestion-jobs/<job_id>", methods=["GET"])
@limiter.limit(POLL_LIMIT)
@jwt_required()
def get_my_path_suggestion_job(job_id: str):
    """GET /me/path-suggestion-jobs/{job_id} - poll a queued scoring.

    404 covers no such job, a malformed handle, and somebody else's job alike.
    Distinguishing them would confirm that a handle exists, which is the only
    thing protecting one.

    `error` on a failed job carries the scorer's own message -- notably
    `career_status_not_set`, the same condition the synchronous GET answers 400
    for, and `profile_incomplete` when the profile carries neither a job title
    nor any skills. The client handles both by prompting for the missing data
    rather than by retrying.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    job = scoring_jobs.find_for_user(
        user.id, job_id, job_type=scoring_jobs.PATH_SUGGESTIONS
    )
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(scoring_jobs.status_for(job)), 200


# ---------------------------------------------------------------------------
# F-5 -- the Tier-2 deep fit, on click
# ---------------------------------------------------------------------------
#
# `POST /me/path-suggestion-jobs` above queues the Tier-1 shortlist because that
# fan-out is slow. This one is synchronous and there is no job pair, which is
# the design (`docs/PATH_INTELLIGENCE_REDESIGN.md` §2.3), not an omission: four
# `_OCC_CACHE`-backed O*NET calls for one code and one batched embedding request
# finish inside a request, and a job handle the client has to poll would cost
# the user more round trips than the work it deferred.
#
# POST rather than GET, for the same reason the job enqueue is a POST: it is a
# per-click provider spend with a stored side effect. A GET-with-cache would put
# the spend behind a method browsers, proxies and prefetchers are entitled to
# issue on their own, and would sit outside the CSRF guard that every other
# write on this blueprint is behind.


@document(
    "Deep-fit one occupation for the signed-in user",
    tags=["me"],
    responses={
        200: PathFitResponse,
        400: LegacyError,
        404: LegacyError,
        500: LegacyError,
        503: LegacyError,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    request_required=False,
    description=(
        "The Tier-2 analysis of one O*NET occupation: which of the user's "
        "skills it uses, what it rates highly that they have not named, "
        "coverage and work-style fit, Job Zone feasibility, its tasks and its "
        "hot technologies.\n\n"
        "Synchronous. Costs four `_OCC_CACHE`-backed O*NET requests and one "
        "batched embedding request; the result is stored per (user, "
        "occupation) and returned from storage until the profile changes, so "
        "clicking the same card twice is free. `cached` says which happened.\n\n"
        "Rate limited for the same reason `POST /me/path-suggestion-jobs` is "
        "(A9): this is the door to a provider spend.\n\n"
        "`error` on a failure is one of `career_status_not_set`, "
        "`profile_incomplete` (400); `invalid_onet_code`, `unknown_occupation`, "
        "`unsupported_occupation` (404); or `corpus_unavailable` (503). The "
        "first two are answered by prompting for the missing data, the next "
        "three by dropping the card, the last by retrying."
    ),
)
@intelligence_bp.route("/me/path-fit/<onet_code>", methods=["POST"])
@limiter.shared_limit("10 per minute", scope=_SCOPE_PATH_FIT)
@jwt_required()
def post_my_path_fit(onet_code: str):
    """POST /me/path-fit/{onet_code} - the deep fit for one occupation.

    10 per minute, matching `POST /me/path-suggestion-jobs` and `POST
    /me/recommendations/refresh`: the budget that bounds provider spend lives on
    the route that reaches the provider. A shortlist is ten cards, so ten clicks
    a minute is every card on the page and then some, and a stored fit is served
    without spending anything -- the limit bounds a loop, not a reader.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        intelligence_service.path_fit(user, onet_code, current_app.logger)
    )
