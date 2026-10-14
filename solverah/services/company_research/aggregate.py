"""Step 3 of the pipeline: item scores -> one ``CompanyTraitRecord`` per trait.

The rule (plan 2026-10-13, C5, REVISED to Julie's anchors ruling 5; agg-v2 after
research-ground-truth's review, C5b), with every number in ``constants.py`` under
``AGGREGATION_VERSION``:

* **unknown** -- fewer than ``MIN_SCORED_ITEMS`` non-abstaining items; or no
  INDEPENDENT non-abstaining item dated inside ``RECENCY_DAYS`` (review F8:
  company-authored items never count toward recency); or every item supporting the
  estimate is company-authored (review F4 / Julie ask 3: a company describing itself
  never makes a trait known on its own). ``Aggregate.unknown_reason`` says which.
* **mixed** -- only when BOTH sides of ``SPLIT_POINT`` have real support: at least
  ``MIXED_MIN_SIDE_COUNT`` items each and the smaller side at least
  ``MIXED_MIN_SIDE_FRACTION`` of the non-abstaining items. Before recording it, scope
  (grouping by scope TYPE -- company / division / location / role -- never by the
  free-text label, review F6) and then time (inside vs outside the recency window)
  are each tried as an explanation: if one partitions the items into groups of at least
  ``MIXED_MIN_SIDE_COUNT`` that are each single-sided and disagree,
  ``split_explained_by`` says which. Mixed is never averaged: ``low_end`` /
  ``high_end`` are the means of the two sides.
  A split explained by TIME whose recent side alone holds
  ``TIME_SPLIT_KNOWN_MIN_INDEPENDENT_RECENT`` independent items is reported KNOWN in
  the recent direction, keeping ``split_explained_by = 'time'`` as the "changed
  recently" note (Julie ask 4, provisional).
* **known** -- everything else. The estimate is the mean of the predominant side
  together with the 0.5 items (review F5), or of all items when there is no minority
  side (or the sides tie). The spread lowers the confidence instead of producing
  "mixed": five items at 0.9 and one at 0.1 come out known (high) with lower
  confidence.

Confidence = count factor x (1 - spread penalty) x size discount, all from the
constants module; a mixed record skips the spread penalty (its spread is the finding).
The scorer's per-item confidence is never read (no weighting in v1, Julie ask 2).
A record is written for ALL SIX traits every time, unknown ones included, so coverage
("4 of 6 known") is always computable from the latest generation.

``aggregate_dimension`` is pure (``ScoredEntry`` in, ``Aggregate`` out) so the table of
cases in ``tests/test_company_research_aggregate.py`` runs without a database;
``aggregate_company`` / ``aggregate_posting`` read the latest score per (item,
dimension) and write through the store. The shared read takes its items from ONE
research run -- the one given, else the latest ``done`` run -- so a re-run never
double-counts the previous run's items (review F7).

A pasted posting's private records are aggregated with ``independent_required=False``:
every item there is the posting's own words by construction, and the user pasted it to
read the role through them. The company-authored rules above are about the SHARED
record. (Flagged for Julie alongside ask 3.)
"""

from __future__ import annotations

import datetime
import math
import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from causal_graph.scorer_pipeline import DIMENSIONS
from company_evidence_store import (
    TraitRecordInput,
    stage_size_for_headcount,
    write_trait_records,
)
from solverah.services.company_research.constants import (
    AGGREGATION_VERSION,
    COUNT_CONFIDENCE_BASE,
    COUNT_CONFIDENCE_PER_ITEM,
    EMPLOYER_SPEAKER_PATTERN,
    INDEPENDENT_SOURCE_TYPES,
    MIN_SCORED_ITEMS,
    MIXED_MIN_SIDE_COUNT,
    MIXED_MIN_SIDE_FRACTION,
    RECENCY_DAYS,
    SIZE_DISCOUNT_BY_BAND,
    SIZE_DISCOUNT_UNKNOWN,
    SPLIT_POINT,
    SPREAD_FULL_STD,
    SPREAD_MAX_PENALTY,
    TIME_SPLIT_KNOWN_MIN_INDEPENDENT_RECENT,
)

__all__ = [
    "Aggregate",
    "ScoredEntry",
    "aggregate_company",
    "aggregate_company_report",
    "aggregate_dimension",
    "aggregate_posting",
    "is_independent",
    "size_discount",
]

_EMPLOYER_SPEAKER_RE = re.compile(EMPLOYER_SPEAKER_PATTERN, re.IGNORECASE)


def is_independent(source_type: str, speaker: Optional[str]) -> bool:
    """Whether an item is NOT the company describing itself: an employee's review or
    independent reporting, and not spoken by the employer (an employer's reply, an
    executive quoted in the piece)."""
    if source_type not in INDEPENDENT_SOURCE_TYPES:
        return False
    return not (speaker and _EMPLOYER_SPEAKER_RE.search(speaker))


@dataclass(frozen=True)
class ScoredEntry:
    """One item's score row on ONE dimension. ``score`` None means abstained."""

    score_id: int
    score: Optional[float]
    published_at: Optional[datetime.date]
    scope: str = "company"
    scope_label: Optional[str] = None
    source_type: str = "employee_review"
    speaker: Optional[str] = None

    @property
    def independent(self) -> bool:
        return is_independent(self.source_type, self.speaker)


@dataclass(frozen=True)
class Aggregate:
    status: str
    estimate: Optional[float]
    low_end: Optional[float]
    high_end: Optional[float]
    confidence: Optional[float]
    split_explained_by: Optional[str]
    score_ids: tuple
    """Every score row considered (scored AND abstained), for the record's links."""
    scored: int
    abstained: int
    recent: int
    """Non-abstaining items inside the window that count toward recency."""
    unknown_reason: Optional[str] = None
    """'too_few_items', 'no_recent_independent_item' or 'company_authored_only'."""


# ---------------------------------------------------------------------------
# The pure rule
# ---------------------------------------------------------------------------

def size_discount(headcount: Optional[int]) -> float:
    if headcount is None:
        return SIZE_DISCOUNT_UNKNOWN
    return SIZE_DISCOUNT_BY_BAND[stage_size_for_headcount(headcount)]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def _side(score: float) -> int:
    """-1 low, +1 high, 0 at the split point."""
    if score < SPLIT_POINT:
        return -1
    if score > SPLIT_POINT:
        return 1
    return 0


def _count_factor(n: int) -> float:
    return min(1.0, COUNT_CONFIDENCE_BASE + COUNT_CONFIDENCE_PER_ITEM * n)


def _spread_penalty(values: Sequence[float]) -> float:
    return min(1.0, _std(values) / SPREAD_FULL_STD) * SPREAD_MAX_PENALTY


def _single_sided(entries: Sequence[ScoredEntry]) -> Optional[int]:
    """The one side every non-neutral entry in *entries* is on, or None when they
    straddle the split (or none of them is off it)."""
    sides = {_side(e.score) for e in entries if _side(e.score) != 0}
    if len(sides) != 1:
        return None
    return sides.pop()


def _explained_by_partition(groups: Iterable[Sequence[ScoredEntry]]) -> bool:
    """A partition explains a split when every part holds at least
    MIXED_MIN_SIDE_COUNT items, every part is single-sided, and at least two parts
    disagree."""
    sides = []
    for group in groups:
        if not group:
            continue
        if len(group) < MIXED_MIN_SIDE_COUNT:
            return False
        side = _single_sided(group)
        if side is None:
            return False
        sides.append(side)
    return len(set(sides)) >= 2


def _is_recent(entry: ScoredEntry, today: datetime.date) -> bool:
    return entry.published_at is not None and (today - entry.published_at).days <= RECENCY_DAYS


def _split_explanation(scored: Sequence[ScoredEntry], today: datetime.date) -> Optional[str]:
    by_scope: dict = {}
    for e in scored:
        by_scope.setdefault(e.scope, []).append(e)
    if len(by_scope) >= 2 and _explained_by_partition(by_scope.values()):
        return "scope"
    recent = [e for e in scored if _is_recent(e, today)]
    older = [e for e in scored if not _is_recent(e, today)]
    if recent and older and _explained_by_partition([recent, older]):
        return "time"
    return None


def aggregate_dimension(
    entries: Sequence[ScoredEntry],
    *,
    today: datetime.date,
    headcount: Optional[int] = None,
    independent_required: bool = True,
) -> Aggregate:
    """Apply the rule to one dimension's entries. See the module docstring.

    *independent_required* False (a pasted posting's private records) lets
    company-authored items count toward recency and support a known estimate.
    """
    all_ids = tuple(e.score_id for e in entries)
    scored = [e for e in entries if e.score is not None]
    abstained = len(entries) - len(scored)

    def counts(e: ScoredEntry) -> bool:
        return e.independent or not independent_required

    recent = sum(1 for e in scored if counts(e) and _is_recent(e, today))

    def unknown(reason: str) -> Aggregate:
        return Aggregate("unknown", None, None, None, None, None, all_ids,
                         len(scored), abstained, recent, reason)

    if len(scored) < MIN_SCORED_ITEMS:
        return unknown("too_few_items")
    if recent == 0:
        return unknown("no_recent_independent_item")

    values = [e.score for e in scored]
    low = [e for e in scored if _side(e.score) < 0]
    high = [e for e in scored if _side(e.score) > 0]
    neutral = [e for e in scored if _side(e.score) == 0]
    smaller, larger = (low, high) if len(low) <= len(high) else (high, low)
    n = len(scored)
    discount = size_discount(headcount)

    is_mixed = (
        len(smaller) >= MIXED_MIN_SIDE_COUNT
        and len(smaller) / n >= MIXED_MIN_SIDE_FRACTION
    )
    if is_mixed:
        explanation = _split_explanation(scored, today)
        if explanation == "time":
            recent_entries = [e for e in scored if _is_recent(e, today)]
            if sum(1 for e in recent_entries if counts(e)) >= TIME_SPLIT_KNOWN_MIN_INDEPENDENT_RECENT:
                recent_values = [e.score for e in recent_entries]
                confidence = (
                    _count_factor(len(recent_entries))
                    * (1.0 - _spread_penalty(recent_values)) * discount
                )
                return Aggregate("known", _mean(recent_values), None, None, confidence,
                                 "time", all_ids, n, abstained, recent)
        return Aggregate(
            "mixed", None,
            _mean([e.score for e in low]), _mean([e.score for e in high]),
            _count_factor(n) * discount,
            explanation,
            all_ids, n, abstained, recent,
        )

    if smaller and len(smaller) < len(larger):
        supporting = larger + neutral
    else:
        # no minority side, or a tie too small to be mixed: every item counts
        supporting = scored
    if not any(counts(e) for e in supporting):
        return unknown("company_authored_only")
    estimate = _mean([e.score for e in supporting])
    confidence = _count_factor(n) * (1.0 - _spread_penalty(values)) * discount
    return Aggregate("known", estimate, None, None, confidence,
                     None, all_ids, n, abstained, recent)


def _record_input(dim: str, agg: Aggregate, *, scope: str, scope_label: Optional[str],
                  job_posting_id: Optional[int]) -> TraitRecordInput:
    return TraitRecordInput(
        dimension_key=dim,
        scope=scope,
        status=agg.status,
        scope_label=scope_label,
        estimate=agg.estimate,
        low_end=agg.low_end,
        high_end=agg.high_end,
        confidence=agg.confidence,
        split_explained_by=agg.split_explained_by,
        score_ids=agg.score_ids,
        job_posting_id=job_posting_id,
    )


def _report(agg: Aggregate) -> dict:
    return {
        "status": agg.status,
        "unknown_reason": agg.unknown_reason,
        "split_explained_by": agg.split_explained_by,
        "scored": agg.scored,
        "abstained": agg.abstained,
        "recent": agg.recent,
    }


# ---------------------------------------------------------------------------
# Reading the latest scores and writing the records
# ---------------------------------------------------------------------------

def latest_done_run_id(db, company_id: int) -> Optional[int]:
    """The company's most recently finished ``done`` research run, or None."""
    from model import CompanyResearchRun

    row = (
        db.session.query(CompanyResearchRun.id)
        .filter(CompanyResearchRun.company_id == company_id,
                CompanyResearchRun.status == "done")
        .order_by(CompanyResearchRun.finished_at.desc(), CompanyResearchRun.id.desc())
        .first()
    )
    return None if row is None else row[0]


def _latest_entries(db, company_id: int, *, research_run_id: Optional[int],
                    job_posting_id: Optional[int]) -> dict:
    """Per dimension, one ``ScoredEntry`` per item: the row from the item's LATEST
    scorer run (a re-score under a new run supersedes the old rows, which stay as
    history). The shared read takes the items of ONE research run; the posting read
    takes that posting's items."""
    from model import CompanyEvidenceItem, EvidenceItemScore

    query = (
        db.session.query(EvidenceItemScore, CompanyEvidenceItem)
        .join(CompanyEvidenceItem, EvidenceItemScore.evidence_item_id == CompanyEvidenceItem.id)
        .filter(CompanyEvidenceItem.company_id == company_id)
    )
    if job_posting_id is None:
        if research_run_id is None:
            return {dim: [] for dim in DIMENSIONS}
        query = query.filter(CompanyEvidenceItem.research_run_id == research_run_id)
    else:
        query = query.filter(CompanyEvidenceItem.job_posting_id == job_posting_id)

    latest: dict = {}
    for score, item in query.all():
        key = (item.id, score.dimension_key)
        held = latest.get(key)
        if held is None or score.scorer_run_id > held[0].scorer_run_id:
            latest[key] = (score, item)

    entries: dict = {dim: [] for dim in DIMENSIONS}
    for (item_id, dim), (score, item) in latest.items():
        entries.setdefault(dim, []).append(ScoredEntry(
            score_id=score.id,
            score=None if score.abstained else score.score,
            published_at=item.published_at,
            scope=item.scope,
            scope_label=item.scope_label,
            source_type=item.source_type,
            speaker=item.speaker,
        ))
    return entries


def aggregate_company_report(
    db, company_id: int, *, today: Optional[datetime.date] = None,
    research_run_id: Optional[int] = None,
) -> tuple[list[int], dict]:
    """Write one generation of SHARED, company-scope records (all six traits) from the
    item scores of ONE research run -- *research_run_id* when given (the run in
    progress), else the company's latest ``done`` run. Returns the new record ids and
    a per-dimension report (status, unknown reason, counts) for the run card."""
    from model import Company

    company = db.session.get(Company, company_id)
    if company is None:
        raise ValueError("company %r does not exist" % (company_id,))
    today = today or datetime.date.today()
    run_id = research_run_id if research_run_id is not None else latest_done_run_id(db, company_id)
    entries = _latest_entries(db, company_id, research_run_id=run_id, job_posting_id=None)
    aggregates = {
        dim: aggregate_dimension(entries.get(dim, []), today=today, headcount=company.headcount)
        for dim in DIMENSIONS
    }
    records = [
        _record_input(dim, aggregates[dim], scope="company", scope_label=None, job_posting_id=None)
        for dim in DIMENSIONS
    ]
    ids = write_trait_records(db, company_id, records, aggregation_version=AGGREGATION_VERSION)
    report = {
        "research_run_id": run_id,
        "aggregation_version": AGGREGATION_VERSION,
        "dimensions": {dim: _report(aggregates[dim]) for dim in DIMENSIONS},
    }
    return ids, report


def aggregate_company(db, company_id: int, *, today: Optional[datetime.date] = None,
                      research_run_id: Optional[int] = None) -> list[int]:
    """``aggregate_company_report`` for callers that only need the record ids."""
    ids, _report_ = aggregate_company_report(
        db, company_id, today=today, research_run_id=research_run_id
    )
    return ids


def aggregate_posting(db, job_posting_id: int, *, today: Optional[datetime.date] = None) -> list[int]:
    """Write one generation of PRIVATE, role-scope records for one pasted posting.
    ``scope_label`` is the posting's title when the user gave one."""
    from model import Company, JobPostingSubmission

    posting = db.session.get(JobPostingSubmission, job_posting_id)
    if posting is None:
        raise ValueError("job posting %r does not exist" % (job_posting_id,))
    if posting.company_id is None:
        raise ValueError("job posting %r has no company; it cannot be aggregated" % (job_posting_id,))
    company = db.session.get(Company, posting.company_id)
    today = today or datetime.date.today()
    entries = _latest_entries(
        db, posting.company_id, research_run_id=None, job_posting_id=job_posting_id
    )
    records = [
        _record_input(
            dim,
            aggregate_dimension(entries.get(dim, []), today=today, headcount=company.headcount,
                                independent_required=False),
            scope="role", scope_label=posting.title, job_posting_id=job_posting_id,
        )
        for dim in DIMENSIONS
    ]
    return write_trait_records(
        db, posting.company_id, records, aggregation_version=AGGREGATION_VERSION
    )
