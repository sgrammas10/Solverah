"""Schemas for company lookup, the six-trait CompanyLens read, research requests, pasted
job postings and "I took this job" links.

Six-trait build, C6 (2026-10-13; PRODUCT_DECISIONS.md §2). The rule every response
model here obeys: NO PROBABILITY ON THE WIRE. No `p_fit`, no z, no score, no estimate,
no confidence number, no percentage -- the ranking order and the per-trait labels
(status, direction, inside/outside tolerance, flag) ARE the output, with counts, dates
and paraphrased evidence. tests/test_company_lens_api.py walks every response for a
float or a score-shaped key and fails on one. The interim `fit_score` list this
replaced was deleted with its scorer (`culture_fit_score`).
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "CompanyDetailResponse",
    "CompanyLinkCreateRequest",
    "CompanyLinkEntry",
    "CompanyLinkListResponse",
    "CompanyLinkResponse",
    "CompanyListEntry",
    "CompanyListQuery",
    "CompanyListResponse",
    "CompanyReadQuery",
    "CompanyReadResponse",
    "CoverageCounts",
    "EvidenceItem",
    "EvidenceSummary",
    "FlagCounts",
    "JobPostingCreateRequest",
    "JobPostingResponse",
    "JobPostingStatus",
    "MatchEntry",
    "MatchesQuery",
    "MatchesResponse",
    "MixedRead",
    "NextStep",
    "PostingRead",
    "PostingTraitRead",
    "ResearchRequest",
    "ResearchRunResponse",
    "ResearchRunStatus",
    "TraitRead",
    "TraitReadSummary",
]


TraitKey = Literal["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
TraitStatus = Literal["known", "mixed", "unknown"]
Direction = Literal["more", "less", "even"]
TraitFlag = Literal["must_have_break", "risk", "investigate"]
NextStepCategory = Literal["decide", "investigate", "prepare", "explore", "act", "dont_act_yet"]
CompanyState = Literal["ranked", "not_enough_evidence"]
ResearchStatusValue = Literal["queued", "running", "done", "failed"]
PostingStatusValue = Literal["pending", "scored", "failed"]


class CompanyDetailResponse(SolverahModel):
    """One company's full stored research profile.

    ``id`` is the integer primary key and appears in the URL, so this endpoint
    enumerates: an authenticated caller can walk the ids and read the whole
    network. Part 4.2 replaces it with a UUID ``public_id``.

    ``profile`` is the serialised ``CompanyProfile`` from
    :mod:`packages.ml.culture` -- open here because its optional sections vary
    by how much research a company has had.
    """

    id: int
    name: Optional[str] = None
    slug: Optional[str] = None
    profile: Optional[Dict[str, Any]] = Field(
        default=None, description="Serialised CompanyProfile."
    )


# ===========================================================================
# Phase 1b -- cursor-paginated company list
# ===========================================================================


class CompanyListQuery(SolverahModel):
    """Query parameters for ``GET /companies``."""

    model_config = ConfigDict(extra="ignore")

    cursor: Optional[str] = Field(
        default=None,
        description="Opaque token from a previous next_cursor. Pass back unmodified.",
    )
    limit: Optional[int] = Field(default=None, description="Rows per page. Clamped to 1-100.")
    q: Optional[str] = Field(default=None, description="Case-insensitive substring of the name.")
    industry: Optional[str] = Field(
        default=None, description="Exact industry match, case-insensitive."
    )


class CompanyListEntry(SolverahModel):
    """One company in the list.

    Deliberately not the full profile: the list ships the fields a card renders
    and ``GET /companies/{id}`` ships the rest.
    """

    id: int
    name: Optional[str] = None
    slug: Optional[str] = None
    industry: Optional[str] = None


class CompanyListResponse(SolverahModel):
    """A page of companies. ``next_cursor`` is null on the last page."""

    data: List[CompanyListEntry] = Field(default_factory=list)
    next_cursor: Optional[str] = Field(
        default=None,
        description="Pass as ?cursor= for the next page. Null means this was the last.",
    )


# ===========================================================================
# The six-trait read
# ===========================================================================


class CoverageCounts(SolverahModel):
    """How many of the six traits the company could be read on. Always reported;
    fewer than 3 known is `not_enough_evidence`."""

    known: int
    mixed: int
    unknown: int
    total: int = Field(description="Always 6.")


class FlagCounts(SolverahModel):
    must_have_breaks: int = Field(
        description="Known traits outside the user's tolerance that are must-haves. "
                    "One or more sorts the company last; it is never hidden."
    )
    risks: int = Field(
        description="Mixed must-have traits whose worse end breaks the tolerance."
    )
    investigate: int = Field(description="Unknown must-have traits.")


class NextStep(SolverahModel):
    category: NextStepCategory
    reason: str


class TraitReadSummary(SolverahModel):
    """One trait as the list shows it: labels only, no numbers."""

    dimension: TraitKey
    label: str
    low_pole: str
    high_pole: str
    status: TraitStatus
    must_have: bool
    direction: Optional[Direction] = Field(
        default=None,
        description='Known traits only: the company offers "more" or "less" of the trait '
                    'than you prefer ("even" when the two agree exactly).',
    )
    within_tolerance: Optional[bool] = Field(
        default=None, description="Known traits only: inside your flat zone."
    )
    flag: Optional[TraitFlag] = None


class EvidenceItem(SolverahModel):
    """One paraphrased piece of evidence. Never a verbatim quote (GAP-14), never a score."""

    paraphrase: str
    source_type: str
    scope: str
    scope_label: Optional[str] = None
    published_at: Optional[str] = Field(default=None, description="ISO date, or null.")
    source_url: Optional[str] = None
    abstained: bool = False


class EvidenceSummary(SolverahModel):
    count: int
    abstained: int
    first_dated: Optional[str] = None
    last_dated: Optional[str] = None
    source_types: List[str] = Field(default_factory=list)


class MixedEnd(SolverahModel):
    direction: Direction
    within_tolerance: bool
    evidence: List[EvidenceItem] = Field(default_factory=list)


class MixedRead(SolverahModel):
    """A mixed trait, both ends read separately. Never averaged."""

    low_end: MixedEnd
    high_end: MixedEnd
    explanation: Optional[str] = Field(
        default=None, description="Whether scope or time explains the split, when it does."
    )


class TraitRead(TraitReadSummary):
    """One trait with its evidence, as `GET /companies/{id}/read` shows it."""

    evidence: Optional[EvidenceSummary] = None
    scope_note: Optional[str] = None
    mixed: Optional[MixedRead] = None
    paraphrases: List[EvidenceItem] = Field(
        default_factory=list, description="Known traits: the newest paraphrases."
    )
    explanation: Optional[str] = Field(
        default=None, description="Unknown and mixed traits: one plain line."
    )
    questions: List[str] = Field(
        default_factory=list,
        description="Must-have traits that are unknown or mixed: what to ask at interview.",
    )


class PostingTraitRead(TraitReadSummary):
    """The pasted posting's role-level read of one trait, beside the company's."""

    evidence: Optional[EvidenceSummary] = None
    paraphrases: List[EvidenceItem] = Field(default_factory=list)
    explanation: Optional[str] = None
    questions: List[str] = Field(default_factory=list)
    disagrees: bool = Field(
        description="Both the company and the posting are known on this trait and they "
                    "fall on different sides, or far apart."
    )


class ResearchRunStatus(SolverahModel):
    run_id: int
    company_id: int
    status: ResearchStatusValue
    error: Optional[str] = None
    created_at: Optional[str] = None
    finished_at: Optional[str] = None
    company: Optional[CompanyListEntry] = None


class CompanyRef(SolverahModel):
    id: int
    name: Optional[str] = None
    slug: Optional[str] = None
    size_band: Optional[int] = Field(
        default=None, description="1..5, the Environment Report's own size bands; null unknown."
    )
    size_note: Optional[str] = None


class JobPostingStatus(SolverahModel):
    id: int
    company_id: Optional[int] = None
    title: Optional[str] = None
    status: PostingStatusValue
    created_at: Optional[str] = None
    has_read: bool = Field(description="Whether role-level records exist for it yet.")


class PostingRead(JobPostingStatus):
    traits: List[PostingTraitRead] = Field(default_factory=list)
    disagreements: List[TraitKey] = Field(default_factory=list)


class MatchEntry(SolverahModel):
    """One company in the ranking. `rank` is null for `not_enough_evidence`."""

    id: int
    name: Optional[str] = None
    slug: Optional[str] = None
    state: CompanyState
    rank: Optional[int] = None
    coverage: CoverageCounts
    flags: FlagCounts
    next_step: NextStep
    must_have_reads: List[TraitReadSummary] = Field(default_factory=list)
    missing: List[TraitKey] = Field(
        default_factory=list, description="Traits with no read (unknown)."
    )
    size_note: Optional[str] = None
    research: Optional[ResearchRunStatus] = None


class MatchesQuery(SolverahModel):
    """Query parameters for ``GET /me/matches``."""

    model_config = ConfigDict(extra="ignore")

    cursor: Optional[str] = Field(default=None, description="Opaque token from next_cursor.")
    limit: Optional[int] = Field(default=None, description="Rows per page. Clamped to 1-100.")


class MatchesResponse(SolverahModel):
    """A page of the ranking, or one of the two empty states.

    `core_required`: the user has no current core sitting (not a 400 -- a state the
    page renders). `no_companies`: nothing has been researched yet. `ranked`: `data`
    holds ranked companies first (must-have breaks last among them) and
    `not_enough_evidence` companies after.
    """

    state: Literal["ranked", "core_required", "no_companies"]
    data: List[MatchEntry] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    total_companies: int
    preferences_answered: bool = Field(
        description="Whether the user has answered the tolerance step. If not, every "
                    "trait reads with the 0.15 floor zone and no must-haves."
    )


class CompanyReadQuery(SolverahModel):
    model_config = ConfigDict(extra="ignore")

    posting_id: Optional[int] = Field(
        default=None, description="One of the caller's own pasted postings for this company."
    )


class CompanyReadResponse(SolverahModel):
    """`GET /companies/{id}/read`. `traits` is present for `ranked` and
    `not_enough_evidence`; absent for `core_required` and `not_researched`."""

    state: Literal["ranked", "not_enough_evidence", "core_required", "not_researched"]
    company: CompanyRef
    research: Optional[ResearchRunStatus] = None
    preferences_answered: bool
    coverage: Optional[CoverageCounts] = None
    flags: Optional[FlagCounts] = None
    next_step: Optional[NextStep] = None
    missing: List[TraitKey] = Field(default_factory=list)
    traits: List[TraitRead] = Field(default_factory=list)
    posting: Optional[PostingRead] = None


# ===========================================================================
# Research requests
# ===========================================================================


class ResearchRequest(SolverahModel):
    name: str = Field(min_length=1, max_length=200, description="The company's name.")


class ResearchRunResponse(SolverahModel):
    """`202` from `POST /companies/research`. `cached` is true when a fresh run already
    existed and nothing new was started."""

    run: ResearchRunStatus
    cached: bool


# ===========================================================================
# Pasted job postings
# ===========================================================================


class JobPostingCreateRequest(SolverahModel):
    company_id: int
    text: str = Field(min_length=1, max_length=40000, description="The pasted posting.")
    title: Optional[str] = Field(default=None, max_length=300)


class JobPostingResponse(SolverahModel):
    posting: JobPostingStatus


# ===========================================================================
# "I took this job"
# ===========================================================================


class CompanyLinkCreateRequest(SolverahModel):
    company_id: int
    started_on: datetime.date


class CompanyLinkEndRequest(SolverahModel):
    ended_on: datetime.date


class CompanyLinkEntry(SolverahModel):
    id: int
    company_id: int
    started_on: str
    ended_on: Optional[str] = None
    created_at: Optional[str] = None
    company: Optional[CompanyListEntry] = None


class CompanyLinkResponse(SolverahModel):
    link: CompanyLinkEntry


class CompanyLinkListResponse(SolverahModel):
    data: List[CompanyLinkEntry] = Field(default_factory=list)
