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
    "PathFeedbackRequest",
    "PathFeedbackResponse",
    "PathFitGap",
    "PathFitResponse",
    "PathFitZone",
    "PathPreferencesRequest",
    "PathPreferencesResponse",
    "PathSuggestion",
    "PathSuggestionJobAccepted",
    "PathSuggestionJobStatus",
    "PathSuggestionsResponse",
    "PathWantAnswer",
    "PathWantAnchor",
    "PathWantCondition",
    "PathWantTask",
    "PathWantsPutRequest",
    "PathWantsResponse",
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
        default=None,
        description=(
            "LLM-generated rationale for this path. Empty while the response's "
            "`narration_pending` is true and this card's sentence has not landed."
        ),
    )
    profile_dimensions: Any = Field(
        default=None, description="Which parts of the profile drove the match."
    )
    match_score: Optional[float] = None
    reasons: List[str] = Field(
        default_factory=list,
        description=(
            "W-4, additive. At most two plain-words phrases saying what is "
            "DISTINCTIVE about this card against the user's own job -- the line "
            "that replaces the percentage W-1 removed. Built from the measured "
            "work-conditions sidecar and nothing else: no LLM, no extra "
            "embedding. Empty is normal and carries no error: a phrase that "
            "would read the same on most of the page says nothing about any "
            "card and is dropped from all of them (design doc 8.2), and a user "
            "who has stated no wants gets no reason line at all."
        ),
    )
    overlapping_skills: List[str] = Field(
        default_factory=list,
        description=(
            "W-16, additive. The user's own skills this occupation uses, as the "
            "scorer found them -- the same list the narrator is handed and the "
            "fallback sentence is built from. Carried on the card because the "
            "fallback can now be written after the card (when a narration fails "
            "or never lands). Not rendered by the SPA."
        ),
    )


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
    feedback: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "F-6, additive. Every inline judgement standing for this user, as "
            "onet_code -> verdict, and the same map `POST /me/path-feedback` "
            "returns. It travels with the list because it SHAPED the list: a "
            "client that got the ranking without it would show a user a "
            "shortlist bent by state they cannot see and cannot reset. Empty "
            "for a user who has judged nothing, which is also the state in which "
            "the ranking is the plain default."
        ),
    )
    narration_pending: bool = Field(
        default=False,
        description=(
            "W-16, additive. True while at least one card's `why_text` is still "
            "being written: the list is scored and shown first, and the "
            "narrator's sentences land a few seconds later. A card waiting on "
            "one has `why_text` \"\" and `profile_dimensions` []; the client "
            "shows a placeholder line for it and keeps polling. It becomes "
            "false when the narration lands (sentences filled in place, order "
            "unchanged), when it fails (the fallback sentence instead), or -- if "
            "the worker running it died -- on the first read more than 60 s "
            "after `generated_at`, which serves the fallback sentences. False on "
            "every payload written before W-16."
        ),
    )


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
        default=None, description='Groq model. Defaults to "openai/gpt-oss-20b" (or SOLVERAH_AGENT_MODEL).'
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
        default=None, description='Groq model. Defaults to "openai/gpt-oss-20b" (or SOLVERAH_AGENT_MODEL).'
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
        description=(
            "queued, running, succeeded or failed. The last two are terminal for "
            "the job. W-16: `succeeded` now arrives as soon as the list is "
            "scored; while `result.narration_pending` is true the result is "
            "still being updated in place with the cards' sentences, so a client "
            "keeps polling until it is false."
        )
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


# ===========================================================================
# F-5 -- POST /me/path-fit/{onet_code}, the Tier-2 deep fit
# ===========================================================================
#
# Tier 1 (`PathSuggestionsResponse` above) is a cheap shortlist. This is the
# full analysis of the one occupation a user clicked: four `_OCC_CACHE`-backed
# O*NET calls and one batched embedding request, run synchronously, stored per
# (user, occupation) and invalidated on profile write.
#
# Every field is a number or a list the card can render directly. Nothing here
# is LLM-written -- see `backend/services/path_deep_fit.py` on why the narrative
# is deliberately deferred rather than missing.


class PathFitZone(SolverahModel):
    """Job Zone feasibility of this occupation for this user.

    The live scale is 2-5: O*NET v2 merged zones 1 and 2. `occupation_zone` and
    `delta` are null for the 93 corpus rows with no zone, and a missing zone is
    NEUTRAL -- `score` is then what a role at the user's own level would get,
    not a penalty.
    """

    user_zone: int = Field(description="The user's own Job Zone, 2-5.")
    user_zone_resolved: bool = Field(
        description="False when user_zone is the fallback guess rather than a real value."
    )
    occupation_zone: Optional[int] = Field(
        default=None, description="This occupation's Job Zone, or null if it has none."
    )
    delta: Optional[int] = Field(
        default=None, description="occupation_zone - user_zone, or null."
    )
    score: float = Field(description="The feasibility term, -0.3 to 1.0.")


class PathFitGap(SolverahModel):
    """One thing this role rates highly that the user's skills do not cover."""

    name: str
    importance: float = Field(description="O*NET importance, 0-100.")


class PathFitResponse(SolverahModel):
    """``200`` from ``POST /me/path-fit/{onet_code}``.

    Identical whether the fit was just computed or served from storage;
    ``cached`` is the only thing that differs, and it describes the response
    rather than the fit.
    """

    model_config = ConfigDict(extra="allow")

    onet_code: str
    title: str
    fit_score: float = Field(
        description=(
            "0.0-1.0. NOT the Tier-1 card score and it will not equal it: "
            "coverage here is measured against the occupation's own rated "
            "skills and hot technologies, not against its role document."
        )
    )
    retrieval_cosine: float = Field(
        description="Raw cosine of the user's retrieval query against this role document."
    )
    centroid_score: float
    coverage_score: float
    skills_score: float
    work_style_score: float
    zone: PathFitZone
    matched_skills: List[str] = Field(
        default_factory=list, description="The user's own skills this role uses."
    )
    gap_skills: List[PathFitGap] = Field(
        default_factory=list, description="Most important first, at most 8."
    )
    tasks: List[str] = Field(
        default_factory=list, description="O*NET task statements, most important first."
    )
    tech_stack: List[str] = Field(
        default_factory=list, description="Hot technologies, most in-demand first."
    )
    weights: Dict[str, float] = Field(
        default_factory=dict, description="The role/coverage/zone/style split used."
    )
    onet_calls: int = Field(
        description="O*NET requests this fit cost. Four unless a call failed."
    )
    narrative: Optional[str] = Field(
        default=None,
        description=(
            "Reserved. Always null in F-5 -- adding an LLM call per click is a "
            "latency and spend decision that has not been made."
        ),
    )
    computed_at: str = Field(description="When the analysis ran, UTC.")
    cached: bool = Field(
        description="True when this came from storage rather than being computed now."
    )


# ===========================================================================
# F-6 -- POST/DELETE /me/path-feedback, the inline card feedback loop
# ===========================================================================
#
# `PathSuggestionsResponse` above is the shortlist. These two routes change what
# it contains and hand back the new one in the same shape, plus the judgements
# that produced it -- so a client renders one list component and reads the state
# of its own buttons off the same response, rather than making a second call to
# find out what it just wrote.
#
# Only the `adjacent` move_intent reads the judgements. They are stored for every
# user regardless, because a user who switches to `adjacent` later should not
# have lost what they already said.


class PathFeedbackRequest(SolverahModel):
    """The body of ``POST /me/path-feedback``: one judgement about one card."""

    onet_code: str = Field(
        description='O*NET-SOC, e.g. "15-1252.00", from a card in the shortlist.'
    )
    verdict: str = Field(
        description=(
            '"too_similar", "interesting", or "not_for_me". The three are not '
            "interchangeable: the first raises a cosine radius around the user's "
            "own occupation and the other two rotate the retrieval query toward "
            "and away from what they named."
        )
    )


class PathFeedbackResponse(SolverahModel):
    """``200`` from ``POST`` and ``DELETE /me/path-feedback``.

    `suggestions`, `career_status` and `generated_at` are
    `PathSuggestionsResponse`'s fields with `PathSuggestionsResponse`'s meaning --
    this re-ranked list is written into the same per-user cache `GET
    /me/path-suggestions` serves, so the two are the same list and not two views
    of one.
    """

    model_config = ConfigDict(extra="allow")

    suggestions: List[PathSuggestion] = Field(default_factory=list)
    career_status: str
    generated_at: str = Field(description="ISO 8601 UTC, second precision.")
    feedback: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Every judgement standing for this user, as onet_code -> verdict. "
            "Empty after a DELETE."
        ),
    )
    narration_pending: bool = Field(
        default=False,
        description=(
            "W-16, additive. True while at least one card's `why_text` is still "
            "being written: the list is scored and shown first, and the "
            "narrator's sentences land a few seconds later. A card waiting on "
            "one has `why_text` \"\" and `profile_dimensions` []; the client "
            "shows a placeholder line for it and keeps polling. It becomes "
            "false when the narration lands (sentences filled in place, order "
            "unchanged), when it fails (the fallback sentence instead), or -- if "
            "the worker running it died -- on the first read more than 60 s "
            "after `generated_at`, which serves the fallback sentences. False on "
            "every payload written before W-16."
        ),
    )


# ===========================================================================
# W-4 -- GET/PUT /me/path-wants, "what should change" about the user's own job
# ===========================================================================
#
# `PathFeedbackRequest` above is a judgement about a card the scorer chose. This
# is the other direction and a different kind of statement: the user's own
# answer about the job they already hold, which every move_intent reads because
# it is not an opinion about a suggestion (design doc 8.3).
#
# The panel is built server-side rather than being a static form, and that is the
# design: the questions ARE the user's own occupation's O*NET task statements, so
# only the server -- which resolves the anchor and holds the sidecar -- knows what
# they are. A client renders what it is given.
#
# `item_text` never reaches the wire. The original statement is what gets
# embedded and the label is what gets read (design doc 8.7, F-7's measured
# metaphor hazard); a client has no use for the first and shipping it would
# invite one to send it back as the key.


class PathWantAnchor(SolverahModel):
    """The occupation the panel is asking about."""

    onet_code: str = Field(description='O*NET-SOC, e.g. "15-1252.00".')
    title: str = Field(description="The occupation's O*NET title, not the user's own.")


class PathWantTask(SolverahModel):
    """One task row of the panel."""

    key: str = Field(
        description=(
            "Opaque, stable, and what a PUT sends back. Derived from the "
            "original O*NET statement, so an answer survives a quarterly "
            "sidecar rebuild and a relabel -- not a position and not the label."
        )
    )
    label: str = Field(description="Plain words, written offline. What the user reads.")
    verdict: Optional[str] = Field(
        default=None,
        description='"more", "less", or null. Null is "fine", and is stored as no row.',
    )


class PathWantCondition(SolverahModel):
    """One measured work-condition row of the panel."""

    axis: str = Field(
        description='One of "people", "public", "leading", "desk". Also the PUT key.'
    )
    label: str = Field(description="Plain words. What the user reads.")
    verdict: Optional[str] = Field(
        default=None, description='"more", "less", or null.'
    )


class PathWantsResponse(SolverahModel):
    """``200`` from ``GET`` and ``PUT /me/path-wants`` -- the same shape from both.

    One shape rather than two, for the reason `PathFeedbackResponse` gives: a
    client renders one panel component and reads the state of its own controls
    off the response it just wrote, instead of making a second call to find out
    what it stored.
    """

    status: str = Field(
        description=(
            '"ok" when the panel can be shown; "no_anchor" when the user has no '
            "current job, or it resolves to nothing usable, in which case there "
            "is no panel and taps alone steer the page; \"unavailable\" when the "
            "task sidecar could not be loaded, which leaves the conditions half "
            "answerable and the task half empty."
        )
    )
    anchor: Optional[PathWantAnchor] = Field(
        default=None, description="Null exactly when status is \"no_anchor\"."
    )
    tasks: List[PathWantTask] = Field(
        default_factory=list,
        description=(
            "The offered task rows, in sidecar order, at most eight. Empty for "
            "an occupation O*NET publishes no statements for, and empty when "
            "status is \"no_anchor\" or \"unavailable\"."
        ),
    )
    conditions: List[PathWantCondition] = Field(
        default_factory=list,
        description=(
            "The four condition rows, in a fixed order. Offered whenever there "
            "is an anchor: the axes are names in code, so nothing on this half "
            "depends on a sidecar being present."
        ),
    )


class PathWantAnswer(SolverahModel):
    """One answer in a ``PUT /me/path-wants`` body."""

    kind: str = Field(description='"task" or "condition".')
    key: str = Field(
        description=(
            "The `key` of a task row or the `axis` of a condition row, from a "
            "GET for the user's CURRENT anchor. A key this anchor does not offer "
            "is a 422 and nothing is written."
        )
    )
    verdict: Optional[str] = Field(
        default=None,
        description='"more", "less", or null. Null clears the answer.',
    )


class PathWantsPutRequest(SolverahModel):
    """The body of ``PUT /me/path-wants``.

    PARTIAL IS VALID AND IS THE EXPECTED CASE. The panel is skippable and must be
    valid half-finished (design doc 8.3), so a body naming three of twelve rows
    changes those three and leaves the rest exactly as they were. This is a PUT
    over *the answers it names*, not over the panel: a client that wanted to
    clear a row sends it with a null verdict rather than omitting it.
    """

    answers: List[PathWantAnswer] = Field(
        default_factory=list,
        description="May be empty: writing nothing is a valid, idempotent no-op.",
    )
