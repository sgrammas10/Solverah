"""Schemas for the five assessment instruments.

Every result body below is open (``extra="allow"``).  That is not laziness: three
of these bodies are assembled partly from an LLM's JSON response, and the
handlers check only that a required set of keys is present -- extra keys the
model volunteers are passed through to the client today.  A closed model would
claim a guarantee the code does not make.

The required keys *are* declared, because those the handlers do enforce: a
Work Pulse response missing ``archetype`` is rejected with a 500 before it ever
reaches a client.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import ConfigDict, Field, RootModel

from . import SolverahModel

__all__ = [
    "RESULT_RESPONSES",
    "SUBMISSION_REQUESTS",
    "SUBMISSION_RESPONSES",
    "AssessmentCatalogueEntry",
    "AssessmentCatalogueResponse",
    "AssessmentFormResponse",
    "AssessmentSubmissionRequest",
    "AssessmentSubmissionResponse",
    "AssessmentSubmitRequest",
    "AssessmentSubmitResponse",
    "FocusTypeResult",
    "FocusTypeSubmitRequest",
    "ManagerMatchAnswer",
    "ManagerMatchResult",
    "ManagerMatchSubmitRequest",
    "WorkPulseAnswer",
    "WorkPulseResult",
    "WorkPulseSubmitRequest",
    "WpllResultResponse",
    "WpllSubmitRequest",
]


class WorkPulseAnswer(SolverahModel):
    model_config = ConfigDict(extra="allow")

    question_id: Optional[str] = None
    option_id: Optional[str] = None


class WpllSubmitRequest(SolverahModel):
    """Anonymous Work Pulse Lite-Lite teaser."""

    answers: List[WorkPulseAnswer] = Field(description="1-5 answers.")


class WpllResultResponse(SolverahModel):
    """The teaser insight plus the titles of the sections still locked.

    Two shapes can come back on a 200: the LLM-generated one below, and the
    deterministic rules-engine fallback when the provider call fails. Both carry
    ``insight_text`` and ``locked_sections``, which is why the fallback is
    invisible to the client -- and why it is safe here and nowhere else.
    """

    model_config = ConfigDict(extra="allow")

    insight_text: str
    locked_sections: List[str]


class WorkPulseSubmitRequest(SolverahModel):
    answers: List[WorkPulseAnswer] = Field(description="Exactly 12 answers.")


class WorkPulseResult(SolverahModel):
    """Work Pulse narrative result.

    Persisted to ``user_intake.wpl_result`` and returned verbatim by
    ``GET /work-pulse/results``.
    """

    model_config = ConfigDict(extra="allow")

    narrative: str
    emerging_signals: List[Any] = Field(default_factory=list)
    archetype: str
    archetype_description: Optional[str] = None


class FocusTypeSubmitRequest(SolverahModel):
    """Five scene payloads, scored deterministically -- no LLM on this path."""

    model_config = ConfigDict(extra="allow")

    scene_1: List[Any] = Field(description="Card IDs in priority order.")
    scene_2: Dict[str, Any] = Field(description='{"now": [], "later": [], "ignore": []}')
    scene_3: Dict[str, Any] = Field(
        description="Time split across deep_solo, planning, social, breaks, exploring."
    )
    scene_4: Dict[str, Any] = Field(
        description='{"now": [], "tomorrow": [], "avg_decision_time_ms": int}'
    )
    scene_5: List[Any] = Field(description="Block IDs in timeline order.")


class FocusTypeResult(SolverahModel):
    model_config = ConfigDict(extra="allow")

    archetype: Optional[str] = None
    dimension_scores: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[Any] = Field(default_factory=list)


class ManagerMatchAnswer(SolverahModel):
    model_config = ConfigDict(extra="allow")

    question_id: Optional[str] = None
    choice: Optional[str] = Field(default=None, description='"a" or "b".')


class ManagerMatchSubmitRequest(SolverahModel):
    answers: List[ManagerMatchAnswer] = Field(description="Exactly 15 forced-choice answers.")


class ManagerMatchResult(SolverahModel):
    """Deterministic scoring merged with the LLM-generated narrative."""

    model_config = ConfigDict(extra="allow")

    archetype: Optional[str] = None
    dimension_scores: Dict[str, Any] = Field(default_factory=dict)
    narrative: Optional[str] = None
    what_to_look_for: List[Any] = Field(default_factory=list)
    red_flags: List[Any] = Field(default_factory=list)
    archetype_description: Optional[str] = None


class AssessmentFormResponse(SolverahModel):
    """The person-side items, ordered for this respondent.

    The payload carries ``blocks``, not ``dimensions``. The client renders it
    verbatim: it must not sort, group, re-shuffle, or reorder options. Ordering
    is server-authoritative because two independent PRNGs in two languages
    diverging is silent, and a divergence corrupts a resumed session's ordering
    rather than raising (D-04).
    """

    model_config = ConfigDict(extra="allow")

    form_version: str
    respondent_id: str
    blocks: List[Any] = Field(default_factory=list)


class AssessmentSubmitRequest(SolverahModel):
    responses: Dict[str, str] = Field(
        description="Exactly 24 entries of {item_token: option_key}."
    )


class AssessmentSubmitResponse(SolverahModel):
    """Deliberately does not carry the six dimension scores.

    The documented threat to this instrument is aspirational answering by a user
    self-profiling for matching. Handing back the six numbers gives a retaking
    respondent a gradient to optimise against -- it teaches the
    item-to-dimension mapping that the shuffle and the interleave exist to hide.
    """

    submission_id: str
    scoring_key_version: str
    dimensions_scored: int


# ===========================================================================
# Phase 1b -- POST /assessments/{kind}/submissions
# ===========================================================================
#
# One route, five instruments, and **five request shapes and five response
# shapes**.  Collapsing the handlers was the goal; collapsing the payloads was
# never part of it, and would have been the expensive mistake.  A Work Pulse
# result is a narrative and an archetype, a FocusType result is six dimension
# scores and recommendations, a WPLL result is one sentence and a list of
# locked section titles, and a ``core`` submission deliberately returns no
# scores at all.  A lowest-common-denominator envelope over those five would
# have to be open enough to hold any of them, which makes it a document that
# promises nothing.
#
# So the union models below exist to *document* the route -- they emit
# ``anyOf`` over the five real schemas, each of which stays exactly what it was
# -- while the per-kind maps underneath are what the route actually enforces
# and what tests assert against.  ``solverah.openapi.document``'s ``request_for``
# is the hook that keeps those two facts consistent: the union is published, one
# member is enforced, and enforcing the union instead would let a Work Pulse
# body through on the FocusType path.


class AssessmentSubmissionRequest(RootModel):
    """Documentation-only union of the five submission bodies.

    Do not validate against this. Union members here are open models, so
    pydantic's smart matching will accept almost anything into the first one
    that fits -- which is precisely why the route enforces
    :data:`SUBMISSION_REQUESTS` per kind rather than this.
    """

    root: Union[
        AssessmentSubmitRequest,
        WorkPulseSubmitRequest,
        WpllSubmitRequest,
        FocusTypeSubmitRequest,
        ManagerMatchSubmitRequest,
    ]


class AssessmentSubmissionResponse(RootModel):
    """Documentation-only union of the five submission results.

    Which member comes back is determined by ``{kind}`` in the path, not by
    anything in the body, so this cannot be an OpenAPI discriminated union --
    3.1 keys a discriminator off a property of the payload, and the
    discriminator here is the URL. The union is the honest encoding of "one of
    these five, and the path tells you which".
    """

    root: Union[
        AssessmentSubmitResponse,
        WorkPulseResult,
        WpllResultResponse,
        FocusTypeResult,
        ManagerMatchResult,
    ]


#: ``{kind}`` -> the body that kind actually accepts. This is what is enforced.
SUBMISSION_REQUESTS: Dict[str, type] = {
    "core": AssessmentSubmitRequest,
    "work_pulse": WorkPulseSubmitRequest,
    "wpll": WpllSubmitRequest,
    "focus_type": FocusTypeSubmitRequest,
    "manager_match": ManagerMatchSubmitRequest,
}

#: ``{kind}`` -> the body that kind returns. Referenced by tests and by the
#: operation description, so the mapping is stated once rather than in prose.
SUBMISSION_RESPONSES: Dict[str, type] = {
    "core": AssessmentSubmitResponse,
    "work_pulse": WorkPulseResult,
    "wpll": WpllResultResponse,
    "focus_type": FocusTypeResult,
    "manager_match": ManagerMatchResult,
}

#: ``{kind}`` -> the body ``GET /me/assessments/{kind}/result`` returns.
#: ``core`` is absent by design: its dimension scores are withheld from the
#: submit response so a retaking respondent has no gradient to optimise
#: against, and a read endpoint would be the same disclosure through a
#: different door.
RESULT_RESPONSES: Dict[str, type] = {
    "work_pulse": WorkPulseResult,
    "focus_type": FocusTypeResult,
    "manager_match": ManagerMatchResult,
}


class AssessmentCatalogueEntry(SolverahModel):
    """One instrument, with the caller's completion state against it."""

    kind: str = Field(description="Path segment: core, work_pulse, wpll, focus_type, manager_match.")
    title: str
    requires_auth: bool = Field(description="False only for the anonymous wpll teaser.")
    scored_by: str = Field(
        description='"rules" or "llm". An llm-scored instrument is unavailable when the provider is.'
    )
    has_form: bool = Field(description="Whether GET /assessments/{kind}/form serves items.")
    has_result: bool = Field(
        description="Whether GET /me/assessments/{kind}/result can re-read a submission."
    )
    completed: bool


class AssessmentCatalogueResponse(SolverahModel):
    """``GET /assessments`` -- the five instruments and where the caller stands.

    Not paginated. The set is a fixed five that changes when code changes, not a
    list that grows with data, and a cursor over it would be ceremony.
    """

    data: List[AssessmentCatalogueEntry] = Field(default_factory=list)
