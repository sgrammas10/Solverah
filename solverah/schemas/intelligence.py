"""Schemas for path intelligence, recommendations, the agent, and quiz insights."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "AgentChatRequest",
    "PathPreferencesRequest",
    "PathPreferencesResponse",
    "PathSuggestion",
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
    the scorer requires, and the client should prompt for it. A 500 means O*NET
    or the narrator failed, and the client should retry.
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
    """Authenticated generation. Also written to ``profile_data.quizInsights``."""

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
