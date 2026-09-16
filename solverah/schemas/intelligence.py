"""Schemas for path intelligence, recommendations, the agent, and quiz insights."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "AgentChatMessage",
    "AgentChatRequest",
    "AgentMessagesRequest",
    "PathPreferencesDocument",
    "PathPreferencesPutRequest",
    "RecommendationsPage",
    "PathPreferencesRequest",
    "PathPreferencesResponse",
    "PathSuggestion",
    "PathSuggestionJobAccepted",
    "PathSuggestionJobStatus",
    "PathSuggestionsResponse",
    "QuizInsight",
    "QuizInsightsGuestResponse",
    "QuizInsightsRequest",
    "QuizInsightsResponse",
    "QuizItem",
    "QuizPayload",
    "RecommendationsResponse",
]


class PathPreferencesRequest(SolverahModel):
    """The three career-search preferences.

    All three are required and validated against closed sets: the path scorer
    branches on them, so an unrecognised value would silently change ranking
    rather than fail.
    """

    move_intent: str = Field(description='"stay_in_field", "adjacent", or "fresh_start".')
    seniority_intent: str = Field(description='"move_up", "stay_lateral", or "open".')
    priority: str = Field(
        description='"pay_title", "interesting_work", "work_life_balance", or "learning_growth".'
    )


class PathPreferencesResponse(SolverahModel):
    message: str


class PathSuggestion(SolverahModel):
    """One suggested O*NET occupation with its narrative."""

    model_config = ConfigDict(extra="allow")

    onet_code: Optional[str] = None
    title: Optional[str] = None
    why_text: Optional[str] = Field(
        default=None, description="LLM-generated rationale for this path."
    )
    profile_dimensions: Any = Field(
        default=None, description="Which parts of the profile drove the match."
    )
    match_score: Optional[float] = None


class PathSuggestionsResponse(SolverahModel):
    """Scored and narrated career paths, cached per user.

    A 400 with ``career_status_not_set`` means the profile is missing a field
    the scorer requires, and the client should prompt for it. A 400 with
    ``profile_incomplete`` means the profile has neither a job title nor any
    skills, so there is nothing to retrieve on -- prompt for those rather than
    retrying. A 500 means the occupation corpus or the narrator failed, and the
    client should retry.
    """

    suggestions: List[PathSuggestion] = Field(default_factory=list)
    career_status: str
    generated_at: str = Field(description="ISO 8601 UTC, second precision.")


class RecommendationsResponse(SolverahModel):
    """Job recommendations.

    Currently always empty: the ML pipeline that produced these was replaced by
    the AI agent and the Groq-backed replacement is not wired up. Both the GET
    and the POST are stubs that return this shape, which is why the frontend
    renders an empty state rather than an error.
    """

    recommendations: List[Any] = Field(default_factory=list)


class AgentChatMessage(SolverahModel):
    model_config = ConfigDict(extra="allow")

    role: str = Field(description='"user" or "assistant".')
    content: str


class AgentChatRequest(SolverahModel):
    """A chat turn. The response is Server-Sent Events, not JSON.

    The server prepends its own system message carrying RAG context assembled
    from the profile, the company network, and the user's resume text -- so the
    client must not send a system message of its own expecting it to be honoured.
    """

    messages: List[AgentChatMessage] = Field(
        description="Full conversation history; must be non-empty."
    )
    model: Optional[str] = Field(
        default=None, description='Groq model. Defaults to "llama-3.1-8b-instant".'
    )


class QuizItem(SolverahModel):
    question: str
    selected: str


class QuizPayload(SolverahModel):
    key: str = Field(description="Echoed verbatim in the matching insight.")
    title: str
    items: List[QuizItem]


class QuizInsightsRequest(SolverahModel):
    """Quizzes to generate insights for.

    A quiz with no key, no title, or no answered items is discarded before the
    model is called; if that leaves nothing, the request is a 400.
    """

    quizGroup: str
    quizzes: List[QuizPayload]


class QuizInsight(SolverahModel):
    model_config = ConfigDict(extra="allow")

    key: Optional[str] = Field(default=None, description="Matches the quiz's key.")
    title: Optional[str] = None
    summary: Optional[str] = None
    keyTakeaways: Any = None
    combinedMeaning: Any = None
    nextSteps: Any = None


class QuizInsightsResponse(SolverahModel):
    """Authenticated generation. Also written to the profile's ``quizInsights``."""

    quizGroup: str
    overallInsight: Any = Field(
        default=None, description="Cross-quiz synthesis, when the model returns one."
    )
    insights: List[QuizInsight] = Field(default_factory=list)


class QuizInsightsGuestResponse(SolverahModel):
    """Anonymous preview. Nothing is persisted.

    Note the key: this returns ``overallSummary`` where the authenticated
    endpoint returns ``overallInsight``. Both are read by the frontend, so the
    inconsistency is preserved rather than fixed here.
    """

    quizGroup: str
    overallSummary: Any = None
    insights: List[QuizInsight] = Field(default_factory=list)


# ===========================================================================
# Phase 1b
# ===========================================================================


class PathPreferencesDocument(SolverahModel):
    """``GET|PUT /me/path-preferences`` -- the three career-search preferences.

    The endpoint this replaces was write-only and answered ``{"message": ...}``,
    so a client had no way to read back what it had saved and had to keep its
    own copy or dig the values out of the profile blob. A resource that can be
    read is most of what the redesign is for.

    Null on every field means the user has not set them. The fields are optional
    on the *response* and required on :class:`PathPreferencesPutRequest`,
    because "not yet answered" is a real state and "answered with nothing" is
    not -- the scorer branches on all three.
    """

    move_intent: Optional[str] = Field(
        default=None, description='"stay_in_field", "adjacent", or "fresh_start".'
    )
    seniority_intent: Optional[str] = Field(
        default=None, description='"move_up", "stay_lateral", or "open".'
    )
    priority: Optional[str] = Field(
        default=None,
        description='"pay_title", "interesting_work", "work_life_balance", or "learning_growth".',
    )


class PathPreferencesPutRequest(SolverahModel):
    """``PUT /me/path-preferences``.

    PUT rather than POST: all three fields are written together and the write
    replaces whatever was there, so the verb matches what happens. Each is
    validated against a closed set server-side -- the path scorer branches on
    them, and an unrecognised value would silently change ranking rather than
    fail.
    """

    model_config = ConfigDict(extra="ignore")

    move_intent: str = Field(description='"stay_in_field", "adjacent", or "fresh_start".')
    seniority_intent: str = Field(description='"move_up", "stay_lateral", or "open".')
    priority: str = Field(
        description='"pay_title", "interesting_work", "work_life_balance", or "learning_growth".'
    )


class RecommendationsPage(SolverahModel):
    """``GET /me/recommendations`` -- a page of job recommendations.

    Currently always empty with a null cursor: the ML pipeline that produced
    these was replaced by the AI agent and the Groq-backed replacement is not
    wired up. It is paginated anyway, and that is the point of doing it now --
    the envelope is the contract, so the day it returns rows is not the day
    every client changes.
    """

    data: List[Any] = Field(default_factory=list)
    next_cursor: Optional[str] = Field(default=None)


class AgentMessagesRequest(SolverahModel):
    """``POST /agent/messages``. The response is Server-Sent Events, not JSON.

    The server prepends its own system message carrying RAG context assembled
    from the profile, the company network, and the user's resume text -- so a
    client must not send a system message of its own expecting it to be
    honoured.
    """

    model_config = ConfigDict(extra="ignore")

    messages: List[AgentChatMessage] = Field(
        min_length=1, description="Full conversation history; must be non-empty."
    )
    model: Optional[str] = Field(
        default=None, description='Groq model. Defaults to "llama-3.1-8b-instant".'
    )


# ===========================================================================
# Phase 3b -- POST /me/path-suggestion-jobs and its poll
# ===========================================================================
#
# `GET /me/path-suggestions` fans out to O*NET and OpenAI; it and assessment
# scoring are the two handlers `gunicorn.conf.py`'s 120-second timeout was
# raised for. These two operations are the asynchronous counterpart, added
# alongside the GET rather than replacing it -- the GET is unchanged and is
# still what the frontend calls.
#
# `result` is `PathSuggestionsResponse`, not a loose object: there is one
# discriminator here, so the per-discriminator rule A12 states for the five
# instruments is satisfied by naming the one shape this job can produce.


class PathSuggestionJobAccepted(SolverahModel):
    """``202`` from ``POST /me/path-suggestion-jobs``."""

    job_id: str = Field(
        description="Poll the status URL until status is 'succeeded' or 'failed'."
    )
    status: str = Field(description='Always "queued" here; the job has not started.')
    status_url: str = Field(description="Where to poll. Relative to the API root.")


class PathSuggestionJobStatus(SolverahModel):
    """``GET /me/path-suggestion-jobs/{job_id}``.

    On ``succeeded``, ``result`` is byte-for-byte what ``GET
    /me/path-suggestions`` would have returned -- the job runs the same service
    function -- so a client's rendering logic does not fork between the two
    paths.

    The job also warms ``path_cache`` on the way through, which means the
    synchronous GET is a cache hit immediately after a job succeeds. A client
    mid-migration can therefore poll the job and then read the old endpoint,
    and neither call pays for the scoring twice.
    """

    model_config = ConfigDict(extra="allow")

    job_id: str
    status: str = Field(
        description="queued, running, succeeded or failed. The last two are terminal."
    )
    error: Optional[str] = Field(
        default=None,
        description=(
            "Present only on 'failed'. `career_status_not_set` means the profile "
            "is missing a field the scorer requires -- the same condition the "
            "synchronous GET answers 400 for. `profile_incomplete` means it has "
            "neither a job title nor any skills, so there is nothing to score; "
            "both are answered by prompting for the missing data, not by "
            "retrying."
        ),
    )
    result: Optional[PathSuggestionsResponse] = Field(
        default=None, description="Present only on 'succeeded'."
    )
