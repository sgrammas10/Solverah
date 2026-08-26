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

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "AssessmentFormResponse",
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
