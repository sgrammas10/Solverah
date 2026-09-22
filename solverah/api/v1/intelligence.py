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
    PathFeedbackRequest,
    PathFeedbackResponse,
    PathFitResponse,
    PathSuggestionJobAccepted,
    PathSuggestionJobStatus,
    RecommendationsPage,
    PathPreferencesResponse,
    PathSuggestionsResponse,
    PathWantsPutRequest,
    PathWantsResponse,
    QuizInsightsGuestResponse,
    QuizInsightsRequest,
    QuizInsightsResponse,
    RecommendationsResponse,
)
from solverah.services import (
    agent_service,
    insight_service,
    intelligence_service,
    path_wants_service,
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
_SCOPE_PATH_FEEDBACK = "intelligence:path-feedback"
_SCOPE_PATH_WANTS = "intelligence:path-wants"

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
    for, `profile_incomplete` when the profile carries neither a job title nor
    any skills, and `corpus_unavailable` when the occupation corpus could not be
    loaded. The client handles the first two by prompting for the missing data
    and the third by offering the user a retry.
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
@limiter.shared_limit("30 per minute", scope=_SCOPE_PATH_FIT)
@jwt_required()
def post_my_path_fit(onet_code: str):
    """POST /me/path-fit/{onet_code} - the deep fit for one occupation.

    **30 per minute since W-9, and the number moved because what it protects
    did.** It was 10, matching `POST /me/path-suggestion-jobs` and `POST
    /me/recommendations/refresh`, because a click cost four live O*NET calls --
    ten clicks was 40 requests a minute at somebody else's threshold. W-9 put
    those four in a file beside the corpus (`occupation_fit`), so a click now
    costs one embeddings batch and one row, and the frontend warms the three
    cards on screen before they are clicked. Ten was then a limit that a page
    load plus three deliberate clicks could reach: Sebastian burned it inside a
    minute of testing.

    A stored fit is still served without spending anything, so what this bounds
    is 30 *distinct* occupations a minute -- three times the whole shortlist. It
    bounds a loop, not a reader.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        intelligence_service.path_fit(user, onet_code, current_app.logger)
    )


# ---------------------------------------------------------------------------
# F-6 -- inline card feedback, and the re-rank it triggers
# ---------------------------------------------------------------------------
#
# `POST /me/path-suggestion-jobs` above stays exactly where it is: it is the COLD
# generation, it costs an LLM completion for ten narratives, and the job/poll
# pair exists because of that cost. These two routes are the WARM re-rank and are
# synchronous, for F-5's reason and with F-5's shape -- the work is a matrix
# product plus, at most, one completion for the two to six cards that are new,
# and a job handle the client had to poll would cost the user more round trips
# than it deferred.
#
# Feedback deliberately does NOT go through the job pair. A tap has to change the
# list the user is looking at; routing it through an enqueue would mean the
# response to "I like this one" is a job id, and the list would change some time
# later, on a poll, with no way to tell the user's tap from a stale generation
# finishing.


@document(
    "Record a judgement about one suggested path and re-rank the shortlist",
    tags=["me"],
    request=PathFeedbackRequest,
    responses={
        200: PathFeedbackResponse,
        400: LegacyError,
        404: LegacyError,
        500: LegacyError,
        503: LegacyError,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Stores one verdict about one occupation and returns the re-ranked "
        "shortlist, which is also written into the per-user cache `GET "
        "/me/path-suggestions` serves.\n\n"
        "`verdict` is one of `too_similar`, `interesting`, `not_for_me`. They "
        "are three different signals, not three strengths of one: `too_similar` "
        "raises a cosine radius around the user's own occupation and excludes "
        "everything inside it, while the other two rotate the retrieval query "
        "toward and away from what they named. Only the `adjacent` move_intent "
        "reads them; they are stored for everyone, so switching to `adjacent` "
        "later does not start from nothing.\n\n"
        "Re-tapping the same card replaces that judgement. A card judged "
        "`too_similar` or `not_for_me` does not come back; one judged "
        "`interesting` does, ranked higher.\n\n"
        "`error` on a failure is one of `invalid_verdict`, "
        "`career_status_not_set`, `profile_incomplete` (400); "
        "`invalid_onet_code`, `unknown_occupation`, `unsupported_occupation` "
        "(404); or `corpus_unavailable` (503)."
    ),
)
@intelligence_bp.route("/me/path-feedback", methods=["POST"])
@limiter.shared_limit("20 per minute", scope=_SCOPE_PATH_FEEDBACK)
@jwt_required()
def post_my_path_feedback():
    """POST /me/path-feedback - store one judgement, return the new shortlist.

    **20 per minute, not the 10 every other spending route on this blueprint
    carries**, and the difference is the interaction rather than the spend. A
    shortlist is ten cards; a user working through them taps ten times in well
    under a minute, and answering their eighth tap with a 429 would be the rate
    limiter breaking the feature it is protecting. 20 is that plus headroom,
    while still bounding a loop.

    It is a real budget rather than a formality because a tap CAN reach a
    provider: the re-rank writes narratives for cards that were not on the list
    before, which is one `gpt-4o-mini` completion for two to six short strings.
    A tap that only reorders spends nothing (see
    `intelligence_service._renarrate`), so the limit bounds the worst case and
    the common case is free.

    Shares one bucket with the DELETE below, for the reason every `shared_limit`
    on this blueprint gives: clear-then-tap-then-clear is one user doing one
    thing, and two separate budgets would let it cost twice as much.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        intelligence_service.record_path_feedback(
            user, request.get_json(silent=True) or {}, current_app.logger
        )
    )


@document(
    "Clear every path judgement and return the default shortlist",
    tags=["me"],
    responses={
        200: PathFeedbackResponse,
        400: LegacyError,
        404: LegacyError,
        500: LegacyError,
        503: LegacyError,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    request_required=False,
    description=(
        "The reset. Deletes every stored judgement for the signed-in user and "
        "returns the shortlist they would have seen having tapped nothing -- "
        "which is byte-for-byte the list `POST /me/path-suggestion-jobs` "
        "produces, because zero judgements is the identity case in the "
        "scorer.\n\n"
        "Idempotent: clearing nothing is a `200` with that same list, not a "
        "`404`. The client is asking for a state, not deleting a row it named."
    ),
)
@intelligence_bp.route("/me/path-feedback", methods=["DELETE"])
@limiter.shared_limit("20 per minute", scope=_SCOPE_PATH_FEEDBACK)
@jwt_required()
def delete_my_path_feedback():
    """DELETE /me/path-feedback - clear the judgements, return the default list.

    A DELETE that returns a body, and a large one. The alternative is `204` plus
    a second round trip to fetch what the user is now looking at, which is a
    worse experience for a button whose whole purpose is "put it back how it
    was" -- and it would let the two responses disagree if a write landed
    between them.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        intelligence_service.clear_path_feedback(user, current_app.logger)
    )


# ---------------------------------------------------------------------------
# W-4 -- "what should change" about the user's own job
# ---------------------------------------------------------------------------
#
# `POST /me/path-feedback` above is a judgement about a card the scorer chose.
# These two are the other direction and a different kind of statement: the user's
# own answer about the job they already hold. That is why all three move intents
# read them while only `adjacent` and `fresh_start` read the judgements -- design
# doc §8.3, and `score_paths`' `wants` argument says the same thing one layer
# down.
#
# NEITHER ROUTE RE-RANKS, and that is the ⚑7 lesson the panel exists under. A tap
# has to change the list the user is looking at, so `POST /me/path-feedback`
# returns the new shortlist; the panel must NEVER stand between the user and a
# result, so the page loads ranked as it is today and the client re-ranks by
# queueing the ordinary suggestion job after it writes. A PUT that returned a
# shortlist would be a panel the first result waits for.
#
# The write therefore invalidates instead: the cached list was computed without
# this answer, so it is wrong the moment the answer lands. See
# `path_wants_service`'s module docstring for why the stored deep fits go with
# it.


@document(
    "Read the \"what should change\" panel for the user's own job",
    tags=["me"],
    responses={200: PathWantsResponse, 404: LegacyError, 503: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "The panel is built from the user's OWN occupation: about eight of its "
        "O*NET tasks in plain words, plus four measured work conditions, each "
        "carrying whatever the user has already answered.\n\n"
        "`status` is `ok`, `no_anchor` (no current job, or a title that resolves "
        "to nothing usable -- show no panel and let card taps steer the page), or "
        "`unavailable` (the task sidecar could not be loaded, so the task half is "
        "empty and only the conditions can be answered).\n\n"
        "Costs no O*NET request and no LLM call. The anchor is resolved out of "
        "the corpus, on the one profile-document embedding `score_paths` caches "
        "anyway.\n\n"
        "`error` on a failure is `corpus_unavailable` (503), which is retried."
    ),
)
@intelligence_bp.route("/me/path-wants", methods=["GET"])
@limiter.shared_limit("20 per minute", scope=_SCOPE_PATH_WANTS)
@jwt_required()
def get_my_path_wants():
    """GET /me/path-wants - the panel, and the user's answers on it.

    Rate limited although it is a read, which `GET /me/path-suggestions` is not,
    and the difference is what the two do. That one is a dict lookup in a
    per-worker cache. This one resolves the anchor, which on a cold
    `_EMBED_CACHE` is an embedding request -- a provider spend, so A9's principle
    puts a budget on it.

    Shares one bucket with the PUT below, for the reason every `shared_limit` on
    this blueprint gives: read-answer-read is one user doing one thing, and two
    separate budgets would let it cost twice as much.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(path_wants_service.read_path_wants(user, current_app.logger))


@document(
    "Record what should change about the user's own job",
    tags=["me"],
    request=PathWantsPutRequest,
    responses={
        200: PathWantsResponse,
        404: LegacyError,
        422: LegacyError,
        503: LegacyError,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Stores the answers named in the body and returns the whole panel, in "
        "`GET /me/path-wants`' shape -- so a client renders one component and "
        "reads the state of its own controls off the response it just wrote.\n\n"
        "PARTIAL IS VALID and is the expected case: the body names the rows it "
        "is changing and leaves the rest alone, because the panel is skippable "
        "and must be valid half-finished. `verdict: null` clears a row, and "
        "clearing something already clear is a `200`, not a `404`.\n\n"
        "Idempotent: sending the same body twice writes the same state.\n\n"
        "Every key is checked against what a `GET` would offer for the user's "
        "CURRENT occupation. A key from a different one -- which is what a "
        "client holding a panel across a job change sends -- is a `422` and "
        "NOTHING is written, not even the acceptable half of the body.\n\n"
        "A write drops the cached shortlist, so the next `POST "
        "/me/path-suggestion-jobs` re-ranks with the new answers. This route "
        "deliberately does not re-rank itself: the panel must never stand "
        "between the user and a result."
    ),
)
@intelligence_bp.route("/me/path-wants", methods=["PUT"])
@limiter.shared_limit("20 per minute", scope=_SCOPE_PATH_WANTS)
@jwt_required()
def put_my_path_wants():
    """PUT /me/path-wants - store the named answers, return the panel.

    20 per minute, matching `POST /me/path-feedback` rather than the 10 the
    spending routes carry, and for that route's reason: the panel is twelve
    controls and a user working down it answers a dozen times in well under a
    minute. A client that batches its answers sends one request; one that writes
    per control sends twelve, and refusing the ninth would be the rate limiter
    breaking the feature it is protecting.

    PUT rather than POST because the body replaces the answers it names rather
    than appending to them, which is `PUT /me/path-preferences`' reasoning.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        path_wants_service.save_path_wants(
            user, request.get_json(silent=True) or {}, current_app.logger
        )
    )
