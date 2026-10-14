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

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import ConfigDict, Field, RootModel

from . import SolverahModel

__all__ = [
    "RESULT_RESPONSES",
    "SCORING_JOB_RESPONSES",
    "SUBMISSION_REQUESTS",
    "SUBMISSION_RESPONSES",
    "AssessmentScoringJobStatus",
    "ManagerMatchScoringJobStatus",
    "ScoringJobAccepted",
    "WpllScoringJobStatus",
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
    "TraitPreferenceEntry",
    "TraitPreferenceInput",
    "TraitPreferencesDocument",
    "TraitPreferencesPutRequest",
    "WorkPulseAnswer",
    "WorkPulseResult",
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


class WorkPulseResult(SolverahModel):
    """The retired original Work Pulse's narrative result.

    Persisted to ``assessment_submissions.result`` since Phase 2d --
    ``user_intake.wpl_result`` before it -- and returned verbatim by
    ``GET /me/assessments/work_pulse/result``. Read-only since the instrument
    was retired on 2026-10-02: nothing writes a new one, and its submit body
    and job-status models are deleted with the write doors.
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

    # WorkPulseResult stays a member although nothing submits one any more: this
    # union also documents `GET /me/assessments/{kind}/result`, which still
    # serves the retired instrument's stored narrative.
    root: Union[
        AssessmentSubmitResponse,
        WorkPulseResult,
        WpllResultResponse,
        FocusTypeResult,
        ManagerMatchResult,
    ]


#: ``{kind}`` -> the body that kind actually accepts. This is what is enforced.
#: The retired ``work_pulse`` has none: every door it had answers 410 before
#: the body is read.
SUBMISSION_REQUESTS: Dict[str, type] = {
    "core": AssessmentSubmitRequest,
    "wpll": WpllSubmitRequest,
    "focus_type": FocusTypeSubmitRequest,
    "manager_match": ManagerMatchSubmitRequest,
}

#: ``{kind}`` -> the body that kind returns. Referenced by tests and by the
#: operation description, so the mapping is stated once rather than in prose.
SUBMISSION_RESPONSES: Dict[str, type] = {
    "core": AssessmentSubmitResponse,
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


# ===========================================================================
# Phase 3b -- POST /assessments/{kind}/scoring-jobs and its poll
# ===========================================================================
#
# The three ``scored_by == "llm"`` instruments score off the request path.  The
# ``202`` body is genuinely uniform -- a handle, a state, and where to poll,
# none of which is instrument-specific -- so ``ScoringJobAccepted`` is one model
# and that is not an A12 violation.
#
# **The poll is where A12 applies, and it is answered the same way the submit
# route answers it.**  ``{kind}`` is in the path, so it selects the response
# model; the union below exists to document the operation and the per-kind map
# underneath is what tests assert against.  A single ``{status, result}`` with
# ``result: Any`` would be exactly the promise-nothing envelope A12 rejected --
# the asynchronous door into the same room.
#
# ``core`` and ``focus_type`` are absent from every map here, because they do not
# score off the request path at all.  For ``core`` that is doubly deliberate:
# it is the instrument whose dimension scores D-01 keeps off the wire, and it
# withholds them even from its own respondent (A12).  A job row would put them
# in ``scoring_jobs.result`` and a poll endpoint would serve them back.


class ScoringJobAccepted(SolverahModel):
    """``202`` from ``POST /assessments/{kind}/scoring-jobs``.

    Uniform across instruments because nothing in it is instrument-specific:
    the handle is a UUID, the status is always ``queued``, and the poll URL is
    derived from the two.  The *result* is where the instruments differ, and
    that is served by the poll under a per-kind model.
    """

    job_id: str = Field(
        description="Poll the status URL until status is 'succeeded' or 'failed'."
    )
    status: str = Field(description='Always "queued" here; the job has not started.')
    status_url: str = Field(description="Where to poll. Relative to the API root.")


class _ScoringJobStatusBase(SolverahModel):
    """Fields every poll response carries, whatever the instrument.

    Subclassed rather than parameterised so each instrument's ``result`` is a
    named, published type instead of a generic the document renders as ``any``.
    """

    model_config = ConfigDict(extra="allow")

    job_id: str
    status: str = Field(
        description="queued, running, succeeded or failed. The last two are terminal."
    )
    error: Optional[str] = Field(
        default=None,
        description=(
            "Present only on 'failed'. Either a validation message the scorer "
            "authored or a fixed generic string -- never provider text, which "
            "carries prompt fragments and therefore the user's own answers."
        ),
    )


class WpllScoringJobStatus(_ScoringJobStatusBase):
    """``GET /assessments/wpll/scoring-jobs/{job_id}``.

    The one poll that needs no JWT, because the instrument it belongs to needs
    none: ``wpll`` is the anonymous pre-launch teaser and has no account to
    scope a handle to.  The handle *is* the authorisation -- see
    ``scoring_jobs.find_anonymous`` for why that is acceptable here and nowhere
    else.
    """

    result: Optional[WpllResultResponse] = Field(
        default=None, description="Present only on 'succeeded'."
    )


class ManagerMatchScoringJobStatus(_ScoringJobStatusBase):
    """``GET /assessments/manager_match/scoring-jobs/{job_id}``."""

    result: Optional[ManagerMatchResult] = Field(
        default=None, description="Present only on 'succeeded'."
    )


class AssessmentScoringJobStatus(RootModel):
    """Documentation-only union of the two poll responses.

    Which member comes back is determined by ``{kind}`` in the path, not by
    anything in the body -- the same reason ``AssessmentSubmissionResponse``
    cannot be an OpenAPI discriminated union.  Do not validate against this;
    validate against :data:`SCORING_JOB_RESPONSES`.
    """

    root: Union[
        WpllScoringJobStatus,
        ManagerMatchScoringJobStatus,
    ]


#: ``{kind}`` -> the poll body that kind returns. This is what tests assert.
#:
#: Exactly the instruments in ``scoring_jobs.JOB_ELIGIBLE_KINDS``, and
#: ``tests/test_scoring_jobs.py`` asserts the two agree -- an instrument that
#: gained a job endpoint without a response model would be documented by the
#: union as "one of these" while returning another shape.
SCORING_JOB_RESPONSES: Dict[str, type] = {
    "wpll": WpllScoringJobStatus,
    "manager_match": ManagerMatchScoringJobStatus,
}


# ===========================================================================
# GET / PUT /me/trait-preferences -- per-trait tolerance and must-have
# ===========================================================================
#
# The six-trait match model (PRODUCT_DECISIONS.md §2, 2026-10-13). The request
# fields are plain `str` / `int` / `bool` rather than `Literal` or bounded ints, the
# same split `solverah/schemas/experiments.py` makes: an outright malformed body is
# the enforcement hook's 422, while the product's rules (all six traits once each,
# steps 0..2, at most two must-haves) are the service's 400 with a specific code.


class TraitPreferenceInput(SolverahModel):
    """One trait's answer."""

    model_config = ConfigDict(extra="ignore")

    dimension_key: str = Field(
        description=(
            "One of autonomy, pace, collaboration, feedback, innovation, decision."
        )
    )
    under_steps: int = Field(
        description=(
            "How much LESS of this trait than the user prefers a job may provide "
            "without cost, in steps of 0.25: 0, 1 or 2."
        )
    )
    over_steps: int = Field(
        description=(
            "How much MORE of this trait than the user prefers a job may provide "
            "without cost, in steps of 0.25: 0, 1 or 2."
        )
    )
    must_have: bool = Field(description="Non-negotiable. At most two per user.")


class TraitPreferencesPutRequest(SolverahModel):
    """All six traits, each exactly once. Appends a new sitting; earlier ones are kept."""

    model_config = ConfigDict(extra="ignore")

    traits: List[TraitPreferenceInput] = Field(
        description="Exactly six entries, one per trait."
    )


class TraitPreferenceEntry(SolverahModel):
    """One trait as stored. Unanswered: steps null, must_have false, answered false."""

    dimension_key: Literal[
        "autonomy", "pace", "collaboration", "feedback", "innovation", "decision"
    ]
    under_steps: Optional[int] = Field(
        description="0, 1 or 2; null when the user has not answered."
    )
    over_steps: Optional[int] = Field(
        description="0, 1 or 2; null when the user has not answered."
    )
    must_have: bool
    answered: bool


class TraitPreferencesDocument(SolverahModel):
    """The user's latest sitting, or all six traits unanswered.

    `answered: false` means the user never answered or skipped; matching and the
    Situation Report then behave exactly as before this step existed.
    """

    answered: bool
    max_must_haves: int = Field(description="The most must-haves a user may set (2).")
    traits: List[TraitPreferenceEntry] = Field(
        description="All six traits, in the product's fixed order."
    )
