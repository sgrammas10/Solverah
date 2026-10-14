"""
company_evidence_store.py -- the only door to the company evidence pipeline's tables.

The six-trait build's company side (PRODUCT_DECISIONS.md §2, 2026-10-13): each company
trait is a RECORD, not a number. The production pipeline is

    research run  ->  evidence items  ->  per-item, per-dimension scores  ->  trait records
    (company_research_run) (company_evidence_item) (evidence_item_score)  (company_trait_record)

plus the user's own pasted job posting (job_posting_submission) as a role-scope source,
and the company's raw headcount from which the model's `stage_size` confounder is cut.
The research/scoring code (solverah/services/company_research/, C5) writes through the
functions here; the match service (C6) reads through them. Nothing else touches these
tables, for the same reason company_score_store.py is the only door to the S1-6 company
score table: one place to audit what a surface may see. (That table is not named here on
purpose: tests/test_company_confidence_unused.py reads prose, and this module's
`confidence` is the trait record's, not the score row's.)

THE ONE RULE THIS MODULE EXISTS TO HOLD
---------------------------------------
`company_evidence_item.excerpt_internal` -- the third-party text the scorer scored -- is
INTERNAL ONLY. No view here carries it, no read function returns it, and no route or page
may ever serialize it (GAP-14, Solverah_IP/compliance/AI_GOVERNANCE_AND_CLAIMS.md: verbatim
third-party quotes never render in the product). `paraphrase` is what a user may see.
`EXCERPT_IS_INTERNAL` states the rule once; tests/test_company_evidence_internal.py
enforces it as reachability, the way test_employer_visibility.py enforces D-01.

The column is also `deferred` on the model, so a serializer that walks a loaded row never
sees it unless it asks by name -- and the only code that asks by name is the write path
in this module and the scorer package.

WHAT THIS MODULE DELIBERATELY DOES NOT IMPORT
---------------------------------------------
No LLM client, nothing from `causal_graph`, nothing from the research package. It takes
plain inputs (the frozen dataclasses below) and returns plain views. The pipeline that
produces the inputs is the caller's concern.

PRIVATE vs SHARED RECORDS
-------------------------
A trait record aggregated from one user's pasted posting carries that `job_posting_id`
and is private to the posting's owner: `trait_records` (the shared company read) never
returns it, `posting_trait_records` does, and `delete_job_postings_for_user` destroys it
with the posting. The store refuses to link a posting's item scores into a shared record
or a research run's item scores into a posting record, so the two reads cannot leak into
each other. A posting can be pasted before its company exists (`company_id` NULL), but it
cannot be SCORED until it has one: evidence items need a company, and `write_items`
refuses a posting with no company rather than guessing.

CONVENTIONS
-----------
Every function takes the Flask-SQLAlchemy `db` first (the brief's signatures), reads and
writes through `db.session`, and every write function COMMITS before returning -- each
call is one atomic step of the pipeline, and a run that dies between steps leaves the
`company_research_run` row saying so. Vocabulary and shape rules are checked here as a
`ValueError` before the database would raise an `IntegrityError`, so a caller gets a
message that names the rule rather than a constraint name; the database holds the same
rules as CHECK constraints so nothing that bypasses this module can write a bad row.
"""

from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence

__all__ = [
    "DIAGNOSTICS_ARE_INTERNAL",
    "EXCERPT_IS_INTERNAL",
    "STAGE_SIZE_BANDS",
    "EvidenceItemInput",
    "EvidenceItemView",
    "ItemScoreInput",
    "JobPostingView",
    "ResearchRunView",
    "TraitRecordInput",
    "TraitRecordView",
    "create_job_posting",
    "delete_job_postings_for_user",
    "discard_research_run_output",
    "finish_research_run",
    "items_for_record",
    "job_postings_for_user",
    "latest_research_run",
    "mark_research_run_running",
    "posting_trait_records",
    "record_late_research_finish",
    "set_company_size",
    "set_job_posting_status",
    "stage_size_for_headcount",
    "start_research_run",
    "trait_records",
    "write_item_scores",
    "write_items",
    "write_trait_records",
    # C6 additions
    "CompanyLinkView",
    "companies_with_shared_records",
    "company_links_for_user",
    "confounder_values",
    "create_company_link",
    "delete_company_link",
    "delete_company_links_for_user",
    "end_company_link",
    "research_run",
    "shared_records_by_company",
]


#: The rule, stated once, quoted by the guard test so the two cannot drift.
EXCERPT_IS_INTERNAL = (
    "company_evidence_item.excerpt_internal is internal only: it is the third-party text "
    "the scorer scored and never reaches a route, a page, or a view (GAP-14). Users see "
    "paraphrase, source type, scope and dates."
)

#: The same rule for the research run card. It holds the research turn's raw text and
#: every citation's verbatim cited_text, so it is under GAP-14 exactly as the excerpt is.
DIAGNOSTICS_ARE_INTERNAL = (
    "company_research_run.diagnostics_internal is internal only: the pipeline's run card "
    "(counts, the raw research text, the citations) for the engineer reading a failed or "
    "thin run, never serialized by a route, a page, or a view (GAP-14)."
)


# ---------------------------------------------------------------------------
# Company size -> stage_size confounder
# ---------------------------------------------------------------------------

#: (band, exclusive upper bound on headcount). The bands are the Environment Report's own
#: `stage_size` item (work_pulse/situation_items.STAGE_SIZE_ITEM), in its words: 1 "a
#: handful of people", 2 "tens of people", 3 "hundreds", 4 "thousands", 5 "tens of
#: thousands". The confounder value a company gets must be on the same 1..5 scale the
#: user's own report puts THEIR employer on, or the model compares two different rulers.
STAGE_SIZE_BANDS: tuple[tuple[int, int], ...] = (
    (1, 10),
    (2, 100),
    (3, 1_000),
    (4, 10_000),
)
_STAGE_SIZE_TOP_BAND = 5


def stage_size_for_headcount(headcount: int) -> int:
    """The Environment Report's 1..5 size band for a raw headcount."""
    if not isinstance(headcount, int) or isinstance(headcount, bool) or headcount < 1:
        raise ValueError("headcount must be an integer >= 1; got %r" % (headcount,))
    for band, upper in STAGE_SIZE_BANDS:
        if headcount < upper:
            return band
    return _STAGE_SIZE_TOP_BAND


# ---------------------------------------------------------------------------
# Views (what readers get) and inputs (what writers give)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResearchRunView:
    id: int
    company_id: int
    trigger: str
    provider: str
    model: str
    prompt_version: str
    status: str
    started_at: Optional[datetime.datetime]
    finished_at: Optional[datetime.datetime]
    cost_usd: Optional[Decimal]
    error: Optional[str]
    created_at: datetime.datetime


@dataclass(frozen=True)
class EvidenceItemView:
    """One evidence item as a reader may see it. Carries the paraphrase, never the excerpt.

    `score` / `abstained` / `scorer_run_id` are set when the view comes from
    `items_for_record` (the read of one item under one record's dimension) and are
    None otherwise.
    """

    id: int
    company_id: int
    scope: str
    scope_label: Optional[str]
    source_type: str
    source_url: Optional[str]
    published_at: Optional[datetime.date]
    retrieved_at: datetime.datetime
    paraphrase: str
    research_run_id: Optional[int]
    job_posting_id: Optional[int]
    score: Optional[float] = None
    abstained: Optional[bool] = None
    scorer_run_id: Optional[int] = None


@dataclass(frozen=True)
class TraitRecordView:
    """One trait record. `job_posting_id` is None on the shared company read and set on a
    record private to the owner of that posting (only `posting_trait_records` returns
    those)."""

    id: int
    company_id: int
    job_posting_id: Optional[int]
    dimension_key: str
    scope: str
    scope_label: Optional[str]
    status: str
    estimate: Optional[float]
    low_end: Optional[float]
    high_end: Optional[float]
    confidence: Optional[float]
    evidence_count: int
    abstain_count: int
    first_dated: Optional[datetime.date]
    last_dated: Optional[datetime.date]
    split_explained_by: Optional[str]
    aggregation_version: str
    computed_at: datetime.datetime


@dataclass(frozen=True)
class JobPostingView:
    """The user's own paste. `posting_text` is theirs, so the view carries it -- it is
    what /me/export returns and what the paste panel shows back."""

    id: int
    user_id: int
    company_id: Optional[int]
    title: Optional[str]
    posting_text: str
    status: str
    created_at: datetime.datetime


@dataclass(frozen=True)
class EvidenceItemInput:
    """One item to write. `excerpt_internal` is the ONLY place outside the model and the
    scorer package that names the column, and it is the write path."""

    scope: str
    source_type: str
    excerpt_internal: str
    paraphrase: str
    scope_label: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[datetime.date] = None
    retrieved_at: Optional[datetime.datetime] = None
    #: Who is speaking, as the researcher recorded it ('employee review, Sales
    #: Associate', 'employer response', 'CEO, interview'). The scorer reads it (rubric
    #: gate 2) and the aggregation uses it to tell an employer's reply from a review.
    speaker: Optional[str] = None


@dataclass(frozen=True)
class ItemScoreInput:
    evidence_item_id: int
    dimension_key: str
    score: Optional[float] = None
    abstained: bool = False
    #: The scorer's own confidence band for this cell (rubric gate 5). STORED, never
    #: read by the aggregation (no weighting in v1; see constants.py).
    confidence: Optional[float] = None


@dataclass(frozen=True)
class TraitRecordInput:
    """One record to write. `score_ids` are the `evidence_item_score` rows it was computed
    from; `evidence_count`, `abstain_count` and (when not given) the dated range are
    DERIVED from them by the store rather than trusted from the caller."""

    dimension_key: str
    scope: str
    status: str
    scope_label: Optional[str] = None
    estimate: Optional[float] = None
    low_end: Optional[float] = None
    high_end: Optional[float] = None
    confidence: Optional[float] = None
    first_dated: Optional[datetime.date] = None
    last_dated: Optional[datetime.date] = None
    split_explained_by: Optional[str] = None
    score_ids: Sequence[int] = ()
    #: Set when aggregating one user's pasted posting (role scope only); the record is
    #: then private to that user and every `score_ids` entry must be on that posting's
    #: items. None for the shared record, whose scores must all be research-derived.
    job_posting_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_view(run) -> ResearchRunView:
    return ResearchRunView(
        id=run.id,
        company_id=run.company_id,
        trigger=run.trigger,
        provider=run.provider,
        model=run.model,
        prompt_version=run.prompt_version,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        cost_usd=run.cost_usd,
        error=run.error,
        created_at=run.created_at,
    )


def _item_view(item, *, score=None, abstained=None, scorer_run_id=None) -> EvidenceItemView:
    # Built field by field on purpose: never from the row's __dict__, which is how an
    # internal column ends up on the wire.
    return EvidenceItemView(
        id=item.id,
        company_id=item.company_id,
        scope=item.scope,
        scope_label=item.scope_label,
        source_type=item.source_type,
        source_url=item.source_url,
        published_at=item.published_at,
        retrieved_at=item.retrieved_at,
        paraphrase=item.paraphrase,
        research_run_id=item.research_run_id,
        job_posting_id=item.job_posting_id,
        score=score,
        abstained=abstained,
        scorer_run_id=scorer_run_id,
    )


def _record_view(row) -> TraitRecordView:
    return TraitRecordView(
        id=row.id,
        company_id=row.company_id,
        job_posting_id=row.job_posting_id,
        dimension_key=row.dimension_key,
        scope=row.scope,
        scope_label=row.scope_label,
        status=row.status,
        estimate=row.estimate,
        low_end=row.low_end,
        high_end=row.high_end,
        confidence=row.confidence,
        evidence_count=row.evidence_count,
        abstain_count=row.abstain_count,
        first_dated=row.first_dated,
        last_dated=row.last_dated,
        split_explained_by=row.split_explained_by,
        aggregation_version=row.aggregation_version,
        computed_at=row.computed_at,
    )


def _posting_view(row) -> JobPostingView:
    return JobPostingView(
        id=row.id,
        user_id=row.user_id,
        company_id=row.company_id,
        title=row.title,
        posting_text=row.posting_text,
        status=row.status,
        created_at=row.created_at,
    )


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _require_vocab(value: Any, vocab: Sequence[str], what: str) -> str:
    if value not in vocab:
        raise ValueError("%s must be one of %r; got %r" % (what, tuple(vocab), value))
    return value


def _require_unit(value: Optional[float], what: str) -> Optional[float]:
    if value is None:
        return None
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError("%s must be in [0, 1]; got %r" % (what, value))
    return value


def _get_or_raise(db, model_cls, row_id: int, what: str):
    row = db.session.get(model_cls, row_id)
    if row is None:
        raise ValueError("%s %r does not exist" % (what, row_id))
    return row


# ---------------------------------------------------------------------------
# Research runs
# ---------------------------------------------------------------------------

def start_research_run(
    db,
    company_id: int,
    *,
    trigger: str,
    provider: str,
    model: str,
    prompt_version: str,
    status: str = "running",
) -> ResearchRunView:
    """Open a research run for *company_id*. Returns the row as a view.

    `status` is 'running' (the default: the caller is about to call the provider, and
    `started_at` is stamped now) or 'queued' (the row is a ticket for a worker; see
    `mark_research_run_running`). `model` is the exact pinned snapshot string -- an alias
    silently re-points when the vendor ships an update, which is the one thing this
    column exists to make visible.
    """
    from model import RESEARCH_TRIGGERS, CompanyResearchRun

    _require_vocab(trigger, RESEARCH_TRIGGERS, "trigger")
    _require_vocab(status, ("queued", "running"), "a new run's status")
    for name, value in (("provider", provider), ("model", model), ("prompt_version", prompt_version)):
        if not value or not str(value).strip():
            raise ValueError("research run needs a non-empty %s" % name)

    run = CompanyResearchRun(
        company_id=company_id,
        trigger=trigger,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        status=status,
        started_at=_now() if status == "running" else None,
    )
    db.session.add(run)
    db.session.commit()
    return _run_view(run)


def mark_research_run_running(db, run_id: int) -> Optional[ResearchRunView]:
    """A worker CLAIMS a queued run. Atomic: one conditional UPDATE
    (``WHERE status = 'queued'``), so two workers handed the same row id -- the web
    pool and the sweep cron both dispatch -- cannot both win. Returns the row as
    running for the winner and None for everyone else (the row is no longer queued:
    claimed, finished or reaped). ``ValueError`` only when the row does not exist.
    The read-check-write this replaced let both workers proceed and pay twice."""
    from model import CompanyResearchRun
    from sqlalchemy import update

    claimed = db.session.execute(
        update(CompanyResearchRun)
        .where(CompanyResearchRun.id == run_id, CompanyResearchRun.status == "queued")
        .values(status="running", started_at=_now())
        .returning(CompanyResearchRun.id)
    ).first()
    db.session.commit()
    if claimed is None:
        _get_or_raise(db, CompanyResearchRun, run_id, "research run")
        return None
    db.session.expire_all()
    return _run_view(db.session.get(CompanyResearchRun, run_id))


def finish_research_run(
    db,
    run_id: int,
    *,
    status: str,
    cost_usd: Optional[Decimal | float] = None,
    error: Optional[str] = None,
    diagnostics: Optional[dict] = None,
) -> Optional[ResearchRunView]:
    """Close a RUNNING run as 'done' or 'failed'. `error` is allowed -- and expected --
    only on 'failed', and should be a short fixed-vocabulary string or a trimmed
    message, never a raw provider exception. `diagnostics` is the pipeline's internal
    run card (counts, the raw research text and the citations); it is written to the
    INTERNAL column and no view ever carries it -- see `DIAGNOSTICS_ARE_INTERNAL`.

    Atomic and conditional (``WHERE status = 'running'``): a row the sweep already
    reaped as ``timed_out`` is NOT overwritten by the thread that finally finishes.
    Returns None when the row was not running -- the caller no longer owns the run and
    must discard its result (see `record_late_research_finish`). ``ValueError`` only
    when the row does not exist or the arguments disagree with the vocabulary."""
    from model import CompanyResearchRun
    from sqlalchemy import update

    _require_vocab(status, ("done", "failed"), "a finished run's status")
    if status == "done" and error is not None:
        raise ValueError("a run finished as 'done' carries no error")
    if status == "failed" and not (error and error.strip()):
        raise ValueError("a run finished as 'failed' must say why (error)")
    if cost_usd is not None and Decimal(str(cost_usd)) < 0:
        raise ValueError("cost_usd cannot be negative; got %r" % (cost_usd,))

    values: dict = {
        "status": status,
        "finished_at": _now(),
        "cost_usd": None if cost_usd is None else Decimal(str(cost_usd)),
        "error": error,
    }
    if diagnostics is not None:
        values["diagnostics_internal"] = diagnostics
    finished = db.session.execute(
        update(CompanyResearchRun)
        .where(CompanyResearchRun.id == run_id, CompanyResearchRun.status == "running")
        .values(**values)
        .returning(CompanyResearchRun.id)
    ).first()
    db.session.commit()
    if finished is None:
        _get_or_raise(db, CompanyResearchRun, run_id, "research run")
        return None
    db.session.expire_all()
    return _run_view(db.session.get(CompanyResearchRun, run_id))


def record_late_research_finish(
    db,
    run_id: int,
    *,
    attempted_status: str,
    cost_usd: Optional[Decimal | float],
    error: Optional[str] = None,
    items_discarded: int = 0,
) -> None:
    """A thread finished a run it no longer owned (the sweep reaped it first). The
    row's status, cost and error are left exactly as the reaper wrote them; the late
    result is noted under ``late_finish`` in the INTERNAL run card so the money spent
    is not invisible. Never raises on a terminal row; ``ValueError`` only when the row
    does not exist."""
    from model import CompanyResearchRun

    run = _get_or_raise(db, CompanyResearchRun, run_id, "research run")
    card = dict(run.diagnostics_internal or {})
    late = list(card.get("late_finish") or [])
    late.append({
        "at": _now().isoformat(),
        "attempted_status": attempted_status,
        "error": error,
        "cost_usd": None if cost_usd is None else float(cost_usd),
        "items_discarded": items_discarded,
        "row_status": run.status,
        "row_error": run.error,
    })
    card["late_finish"] = late
    run.diagnostics_internal = card
    db.session.commit()


def discard_research_run_output(db, run_id: int) -> int:
    """Delete everything a research run wrote under its own id: its evidence items,
    their scores, and the trait records linked to those scores (with the links). For a
    run the thread no longer owns -- reaped between its writes and its finish -- the
    shared read must not be built from it. Returns the number of items removed. The
    scorer_run row is kept (it is a cost record)."""
    from model import (
        CompanyEvidenceItem,
        CompanyTraitRecord,
        CompanyTraitRecordEvidence,
        EvidenceItemScore,
    )

    item_ids = [
        i for (i,) in db.session.query(CompanyEvidenceItem.id)
        .filter(CompanyEvidenceItem.research_run_id == run_id)
    ]
    if not item_ids:
        return 0
    score_ids = [
        s for (s,) in db.session.query(EvidenceItemScore.id)
        .filter(EvidenceItemScore.evidence_item_id.in_(item_ids))
    ]
    if score_ids:
        record_ids = [
            r for (r,) in db.session.query(CompanyTraitRecordEvidence.trait_record_id)
            .filter(CompanyTraitRecordEvidence.evidence_item_score_id.in_(score_ids))
            .distinct()
        ]
        if record_ids:
            db.session.query(CompanyTraitRecordEvidence).filter(
                CompanyTraitRecordEvidence.trait_record_id.in_(record_ids)
            ).delete(synchronize_session=False)
            db.session.query(CompanyTraitRecord).filter(
                CompanyTraitRecord.id.in_(record_ids)
            ).delete(synchronize_session=False)
        db.session.query(EvidenceItemScore).filter(
            EvidenceItemScore.id.in_(score_ids)
        ).delete(synchronize_session=False)
    db.session.query(CompanyEvidenceItem).filter(
        CompanyEvidenceItem.id.in_(item_ids)
    ).delete(synchronize_session=False)
    db.session.commit()
    return len(item_ids)


def research_run(db, run_id: int) -> Optional[ResearchRunView]:
    """One run by id, or None. The poll read behind `GET /companies/research/<id>`."""
    from model import CompanyResearchRun

    run = db.session.get(CompanyResearchRun, run_id)
    return None if run is None else _run_view(run)


def latest_research_run(db, company_id: int) -> Optional[ResearchRunView]:
    """The most recently created run for *company_id*, whatever its status. This is the
    on-demand cache's status read: None means never researched."""
    from model import CompanyResearchRun

    run = (
        db.session.query(CompanyResearchRun)
        .filter(CompanyResearchRun.company_id == company_id)
        .order_by(CompanyResearchRun.created_at.desc(), CompanyResearchRun.id.desc())
        .first()
    )
    return None if run is None else _run_view(run)


# ---------------------------------------------------------------------------
# Evidence items
# ---------------------------------------------------------------------------

def write_items(
    db,
    company_id: int,
    items: Iterable[EvidenceItemInput],
    *,
    research_run_id: Optional[int] = None,
    job_posting_id: Optional[int] = None,
) -> list[int]:
    """Write evidence items under exactly one parent. Returns the new ids, in input order.

    Under a research run, every source type but 'user_pasted_posting' is allowed. Under a
    job posting, every item is 'user_pasted_posting' at 'role' scope -- a pasted posting
    is role-level evidence by decision, and the database holds the same rule.
    """
    from model import (
        EVIDENCE_SCOPES,
        EVIDENCE_SOURCE_TYPES,
        CompanyEvidenceItem,
        CompanyResearchRun,
        JobPostingSubmission,
    )

    if (research_run_id is None) == (job_posting_id is None):
        raise ValueError("write_items needs exactly one of research_run_id, job_posting_id")
    if research_run_id is not None:
        run = _get_or_raise(db, CompanyResearchRun, research_run_id, "research run")
        if run.company_id != company_id:
            raise ValueError(
                "research run %r belongs to company %r, not %r"
                % (research_run_id, run.company_id, company_id)
            )
    else:
        posting = _get_or_raise(db, JobPostingSubmission, job_posting_id, "job posting")
        if posting.company_id is None:
            raise ValueError(
                "job posting %r has no company yet; attach one before scoring it "
                "(evidence items belong to a company)" % (job_posting_id,)
            )
        if posting.company_id != company_id:
            raise ValueError(
                "job posting %r names company %r, not %r"
                % (job_posting_id, posting.company_id, company_id)
            )

    rows = []
    for item in items:
        _require_vocab(item.scope, EVIDENCE_SCOPES, "scope")
        _require_vocab(item.source_type, EVIDENCE_SOURCE_TYPES, "source_type")
        if job_posting_id is not None:
            if item.source_type != "user_pasted_posting":
                raise ValueError("an item under a job posting is source_type 'user_pasted_posting'")
            if item.scope != "role":
                raise ValueError("an item under a job posting is scope 'role'")
        elif item.source_type == "user_pasted_posting":
            raise ValueError("'user_pasted_posting' items are written under a job posting, not a run")
        if item.scope == "company" and item.scope_label is not None:
            raise ValueError("company-scope items carry no scope_label")
        if not item.excerpt_internal or not item.excerpt_internal.strip():
            raise ValueError("an evidence item needs the text that was scored (excerpt_internal)")
        if not item.paraphrase or not item.paraphrase.strip():
            raise ValueError("an evidence item needs a paraphrase; it is the only text a user sees")

        row = CompanyEvidenceItem(
            company_id=company_id,
            research_run_id=research_run_id,
            job_posting_id=job_posting_id,
            scope=item.scope,
            scope_label=item.scope_label,
            source_type=item.source_type,
            source_url=item.source_url,
            published_at=item.published_at,
            speaker=item.speaker,
            excerpt_internal=item.excerpt_internal,
            paraphrase=item.paraphrase,
        )
        if item.retrieved_at is not None:
            row.retrieved_at = item.retrieved_at
        db.session.add(row)
        rows.append(row)

    db.session.commit()
    return [row.id for row in rows]


# ---------------------------------------------------------------------------
# Item scores
# ---------------------------------------------------------------------------

def write_item_scores(db, scores: Iterable[ItemScoreInput], *, scorer_run_id: int) -> int:
    """Write per-item, per-dimension scores under one scorer run. Returns rows written.

    Idempotent on (item, dimension, scorer run): re-presenting a score updates the row in
    place; a NEW scorer run inserts beside the old rows. An abstention is a row with
    `abstained=True` and no score -- "looked, found nothing on this dimension" -- and is
    distinct from no row at all.
    """
    from model import EvidenceItemScore, ScorerRun

    _get_or_raise(db, ScorerRun, scorer_run_id, "scorer run")

    written = 0
    for entry in scores:
        if not entry.dimension_key or not entry.dimension_key.strip():
            raise ValueError("an item score needs a dimension_key")
        if entry.abstained and entry.score is not None:
            raise ValueError(
                "item %r / %s: abstained scores carry no value (got %r)"
                % (entry.evidence_item_id, entry.dimension_key, entry.score)
            )
        if not entry.abstained and entry.score is None:
            raise ValueError(
                "item %r / %s: a non-abstaining score needs a value"
                % (entry.evidence_item_id, entry.dimension_key)
            )
        score = _require_unit(entry.score, "score")
        confidence = _require_unit(entry.confidence, "confidence")
        if entry.abstained and confidence is not None:
            raise ValueError(
                "item %r / %s: abstained scores carry no confidence (got %r)"
                % (entry.evidence_item_id, entry.dimension_key, confidence)
            )

        row = (
            db.session.query(EvidenceItemScore)
            .filter_by(
                evidence_item_id=entry.evidence_item_id,
                dimension_key=entry.dimension_key,
                scorer_run_id=scorer_run_id,
            )
            .first()
        )
        if row is None:
            row = EvidenceItemScore(
                evidence_item_id=entry.evidence_item_id,
                dimension_key=entry.dimension_key,
                scorer_run_id=scorer_run_id,
            )
            db.session.add(row)
        row.score = score
        row.abstained = bool(entry.abstained)
        row.confidence = confidence
        written += 1

    db.session.commit()
    return written


# ---------------------------------------------------------------------------
# Trait records
# ---------------------------------------------------------------------------

def _validate_record_shape(rec: TraitRecordInput) -> None:
    from model import EVIDENCE_SCOPES, SPLIT_EXPLANATIONS, TRAIT_RECORD_STATUSES

    _require_vocab(rec.scope, EVIDENCE_SCOPES, "scope")
    _require_vocab(rec.status, TRAIT_RECORD_STATUSES, "status")
    if not rec.dimension_key or not rec.dimension_key.strip():
        raise ValueError("a trait record needs a dimension_key")
    if rec.scope == "company" and rec.scope_label is not None:
        raise ValueError("company-scope records carry no scope_label")
    if rec.job_posting_id is not None and rec.scope != "role":
        raise ValueError("a record built from a pasted posting is scope 'role'")

    has_estimate = rec.estimate is not None
    has_ends = rec.low_end is not None and rec.high_end is not None
    if (rec.low_end is None) != (rec.high_end is None):
        raise ValueError("low_end and high_end are given together or not at all")
    if rec.status == "known" and not has_estimate:
        raise ValueError("a 'known' record needs an estimate")
    if rec.status != "known" and has_estimate:
        raise ValueError(
            "only a 'known' record carries an estimate; a 'mixed' record is never averaged"
        )
    if rec.status == "mixed" and not has_ends:
        raise ValueError("a 'mixed' record needs low_end and high_end")
    if rec.status != "mixed" and has_ends:
        raise ValueError("only a 'mixed' record carries low_end/high_end")
    if has_ends and rec.low_end > rec.high_end:
        raise ValueError("low_end must be <= high_end")
    if rec.split_explained_by is not None:
        _require_vocab(rec.split_explained_by, SPLIT_EXPLANATIONS, "split_explained_by")
        if rec.status == "unknown":
            raise ValueError(
                "split_explained_by is only meaningful on a 'mixed' record, or on a "
                "'known' one that reports the recent side of a time-explained split"
            )
    for name in ("estimate", "low_end", "high_end", "confidence"):
        _require_unit(getattr(rec, name), name)
    if (rec.first_dated is None) != (rec.last_dated is None):
        raise ValueError("first_dated and last_dated are given together or not at all")
    if rec.first_dated is not None and rec.first_dated > rec.last_dated:
        raise ValueError("first_dated must be <= last_dated")


def write_trait_records(
    db,
    company_id: int,
    records: Iterable[TraitRecordInput],
    *,
    aggregation_version: str,
    computed_at: Optional[datetime.datetime] = None,
) -> list[int]:
    """Insert one generation of trait records for *company_id*. Returns the new ids.

    Always inserts; history is kept and `trait_records` / `posting_trait_records` read the
    latest per key. Every `score_ids` entry must be an `evidence_item_score` row on this
    company and on the record's own dimension, AND on the record's side of the private /
    shared line: a record with `job_posting_id` links only that posting's items, a shared
    record links only research-run items. The store links them and DERIVES
    `evidence_count` (the non-abstaining ones), `abstain_count`, and -- unless the input
    gives them -- the dated range from the linked items' `published_at`.
    """
    from model import (
        CompanyEvidenceItem,
        CompanyTraitRecord,
        CompanyTraitRecordEvidence,
        EvidenceItemScore,
        JobPostingSubmission,
    )

    if not aggregation_version or not aggregation_version.strip():
        raise ValueError("write_trait_records needs an aggregation_version")

    rows = []
    links: list[tuple[Any, list[int]]] = []
    for rec in records:
        _validate_record_shape(rec)
        if rec.job_posting_id is not None:
            posting = _get_or_raise(db, JobPostingSubmission, rec.job_posting_id, "job posting")
            if posting.company_id != company_id:
                raise ValueError(
                    "job posting %r names company %r, not %r"
                    % (rec.job_posting_id, posting.company_id, company_id)
                )

        score_ids = list(dict.fromkeys(int(s) for s in rec.score_ids))
        scored = []
        if score_ids:
            scored = (
                db.session.query(EvidenceItemScore, CompanyEvidenceItem)
                .join(CompanyEvidenceItem, EvidenceItemScore.evidence_item_id == CompanyEvidenceItem.id)
                .filter(EvidenceItemScore.id.in_(score_ids))
                .all()
            )
            found = {s.id for s, _ in scored}
            missing = [s for s in score_ids if s not in found]
            if missing:
                raise ValueError("evidence_item_score rows do not exist: %r" % (missing,))
            for s, item in scored:
                if item.company_id != company_id:
                    raise ValueError(
                        "score %r is on company %r, not %r" % (s.id, item.company_id, company_id)
                    )
                if s.dimension_key != rec.dimension_key:
                    raise ValueError(
                        "score %r is on dimension %r, not %r"
                        % (s.id, s.dimension_key, rec.dimension_key)
                    )
                if item.job_posting_id != rec.job_posting_id:
                    raise ValueError(
                        "score %r is on an item from job posting %r; a record for job "
                        "posting %r cannot link it (a user's paste is private to that "
                        "user, and the shared record is research-derived only)"
                        % (s.id, item.job_posting_id, rec.job_posting_id)
                    )

        evidence_count = sum(1 for s, _ in scored if not s.abstained)
        abstain_count = sum(1 for s, _ in scored if s.abstained)
        first_dated, last_dated = rec.first_dated, rec.last_dated
        if first_dated is None:
            dates = [i.published_at for s, i in scored if not s.abstained and i.published_at]
            if dates:
                first_dated, last_dated = min(dates), max(dates)

        row = CompanyTraitRecord(
            company_id=company_id,
            job_posting_id=rec.job_posting_id,
            dimension_key=rec.dimension_key,
            scope=rec.scope,
            scope_label=rec.scope_label,
            status=rec.status,
            estimate=rec.estimate,
            low_end=rec.low_end,
            high_end=rec.high_end,
            confidence=rec.confidence,
            evidence_count=evidence_count,
            abstain_count=abstain_count,
            first_dated=first_dated,
            last_dated=last_dated,
            split_explained_by=rec.split_explained_by,
            aggregation_version=aggregation_version,
        )
        if computed_at is not None:
            row.computed_at = computed_at
        db.session.add(row)
        rows.append(row)
        links.append((row, score_ids))

    db.session.flush()
    for row, score_ids in links:
        for score_id in score_ids:
            db.session.add(
                CompanyTraitRecordEvidence(trait_record_id=row.id, evidence_item_score_id=score_id)
            )
    db.session.commit()
    return [row.id for row in rows]


def _latest_records(db, *filters) -> list[TraitRecordView]:
    """The CURRENT record per (company, dimension, scope, scope_label, job_posting_id)
    among the rows matching *filters*: the latest `computed_at` wins, older generations
    are history. Postgres `DISTINCT ON`, which the whole app already requires. Ordered by
    dimension, scope, label."""
    from model import CompanyTraitRecord

    key = (
        CompanyTraitRecord.company_id,
        CompanyTraitRecord.dimension_key,
        CompanyTraitRecord.scope,
        CompanyTraitRecord.scope_label,
        CompanyTraitRecord.job_posting_id,
    )
    rows = (
        db.session.query(CompanyTraitRecord)
        .filter(*filters)
        .distinct(*key)
        .order_by(*key, CompanyTraitRecord.computed_at.desc(), CompanyTraitRecord.id.desc())
        .all()
    )
    rows.sort(key=lambda r: (r.dimension_key, r.scope, r.scope_label or ""))
    return [_record_view(r) for r in rows]


def trait_records(db, company_id: int, scope: Optional[str] = None) -> list[TraitRecordView]:
    """The SHARED company read: the current record per (dimension, scope, scope_label)
    for *company_id*, research-derived rows only. A record built from a user's pasted
    posting is never returned here, whoever asks -- see `posting_trait_records`. `scope`
    narrows to one scope."""
    from model import EVIDENCE_SCOPES, CompanyTraitRecord

    filters = [
        CompanyTraitRecord.company_id == company_id,
        CompanyTraitRecord.job_posting_id.is_(None),
    ]
    if scope is not None:
        _require_vocab(scope, EVIDENCE_SCOPES, "scope")
        filters.append(CompanyTraitRecord.scope == scope)
    return _latest_records(db, *filters)


def posting_trait_records(db, job_posting_id: int) -> list[TraitRecordView]:
    """The PRIVATE read: the current record per (dimension, scope_label) built from one
    pasted posting. The caller (C6) checks that the requesting user owns the posting;
    this function does not know who is asking."""
    from model import CompanyTraitRecord, JobPostingSubmission

    _get_or_raise(db, JobPostingSubmission, job_posting_id, "job posting")
    return _latest_records(db, CompanyTraitRecord.job_posting_id == job_posting_id)


def items_for_record(db, record_id: int) -> list[EvidenceItemView]:
    """The evidence behind one trait record: each linked item with its score (or its
    abstention) on the record's dimension. Paraphrase, source type, scope, dates, url --
    NEVER the excerpt. Abstentions are included: a record that says "4 items, 2 said
    nothing" is more honest than one that hides the two."""
    from model import (
        CompanyEvidenceItem,
        CompanyTraitRecord,
        CompanyTraitRecordEvidence,
        EvidenceItemScore,
    )

    _get_or_raise(db, CompanyTraitRecord, record_id, "trait record")
    rows = (
        db.session.query(EvidenceItemScore, CompanyEvidenceItem)
        .join(
            CompanyTraitRecordEvidence,
            CompanyTraitRecordEvidence.evidence_item_score_id == EvidenceItemScore.id,
        )
        .join(CompanyEvidenceItem, EvidenceItemScore.evidence_item_id == CompanyEvidenceItem.id)
        .filter(CompanyTraitRecordEvidence.trait_record_id == record_id)
        .order_by(
            CompanyEvidenceItem.published_at.desc().nulls_last(), CompanyEvidenceItem.id
        )
        .all()
    )
    return [
        _item_view(item, score=s.score, abstained=s.abstained, scorer_run_id=s.scorer_run_id)
        for s, item in rows
    ]


# ---------------------------------------------------------------------------
# Job postings (user-keyed)
# ---------------------------------------------------------------------------

def create_job_posting(
    db,
    user_id: int,
    *,
    posting_text: str,
    company_id: Optional[int] = None,
    title: Optional[str] = None,
) -> JobPostingView:
    """Store a posting the user pasted. Never fetched: the text is what they gave us."""
    from model import JobPostingSubmission

    if not posting_text or not posting_text.strip():
        raise ValueError("a job posting needs its text")
    row = JobPostingSubmission(
        user_id=user_id,
        company_id=company_id,
        title=(title.strip() or None) if title else None,
        posting_text=posting_text,
        status="pending",
    )
    db.session.add(row)
    db.session.commit()
    return _posting_view(row)


def set_job_posting_status(db, posting_id: int, status: str) -> JobPostingView:
    from model import JOB_POSTING_STATUSES, JobPostingSubmission

    _require_vocab(status, JOB_POSTING_STATUSES, "status")
    row = _get_or_raise(db, JobPostingSubmission, posting_id, "job posting")
    row.status = status
    db.session.commit()
    return _posting_view(row)


def job_postings_for_user(db, user_id: int) -> list[JobPostingView]:
    """Every posting the user pasted, newest first. The /me/export read."""
    from model import JobPostingSubmission

    rows = (
        db.session.query(JobPostingSubmission)
        .filter(JobPostingSubmission.user_id == user_id)
        .order_by(JobPostingSubmission.created_at.desc(), JobPostingSubmission.id.desc())
        .all()
    )
    return [_posting_view(r) for r in rows]


def delete_job_postings_for_user(db, user_id: int, *, commit: bool = True) -> int:
    """Destroy the user's postings and everything derived from them -- the account-
    deletion read. Returns the number of postings removed.

    A pasted posting is free text about a person's job search, and free text is never
    retained de-identified (D-7b). Everything derived from it goes with it: the evidence
    items under it, their scores, the trait records carrying its `job_posting_id`, and
    every link row on either side. Shared (research-derived) records are untouched --
    the store never let a posting's scores into one, so there is nothing of the user's
    in them.

    `commit=False` leaves the commit to the caller: account deletion runs this inside
    its own transaction (the postings go with the tombstone or not at all), so it is
    the one caller for which this module's commit-per-call convention is wrong. The
    deletes are still issued on `db.session` in order; only the commit is withheld.
    """
    from model import (
        CompanyEvidenceItem,
        CompanyTraitRecord,
        CompanyTraitRecordEvidence,
        EvidenceItemScore,
        JobPostingSubmission,
    )

    posting_ids = [
        pid
        for (pid,) in db.session.query(JobPostingSubmission.id).filter(
            JobPostingSubmission.user_id == user_id
        )
    ]
    if not posting_ids:
        return 0
    record_ids = [
        rid
        for (rid,) in db.session.query(CompanyTraitRecord.id).filter(
            CompanyTraitRecord.job_posting_id.in_(posting_ids)
        )
    ]
    if record_ids:
        db.session.query(CompanyTraitRecordEvidence).filter(
            CompanyTraitRecordEvidence.trait_record_id.in_(record_ids)
        ).delete(synchronize_session=False)
        db.session.query(CompanyTraitRecord).filter(
            CompanyTraitRecord.id.in_(record_ids)
        ).delete(synchronize_session=False)
    item_ids = [
        iid
        for (iid,) in db.session.query(CompanyEvidenceItem.id).filter(
            CompanyEvidenceItem.job_posting_id.in_(posting_ids)
        )
    ]
    if item_ids:
        score_ids = [
            sid
            for (sid,) in db.session.query(EvidenceItemScore.id).filter(
                EvidenceItemScore.evidence_item_id.in_(item_ids)
            )
        ]
        if score_ids:
            db.session.query(CompanyTraitRecordEvidence).filter(
                CompanyTraitRecordEvidence.evidence_item_score_id.in_(score_ids)
            ).delete(synchronize_session=False)
            db.session.query(EvidenceItemScore).filter(
                EvidenceItemScore.id.in_(score_ids)
            ).delete(synchronize_session=False)
        db.session.query(CompanyEvidenceItem).filter(
            CompanyEvidenceItem.id.in_(item_ids)
        ).delete(synchronize_session=False)
    removed = (
        db.session.query(JobPostingSubmission)
        .filter(JobPostingSubmission.id.in_(posting_ids))
        .delete(synchronize_session=False)
    )
    if commit:
        db.session.commit()
    return removed


# ---------------------------------------------------------------------------
# Company size
# ---------------------------------------------------------------------------

def set_company_size(
    db,
    company_id: int,
    headcount: int,
    *,
    as_of: datetime.date,
    source: str,
    provenance: Optional[str] = None,
) -> int:
    """Record a company's raw headcount and write the derived `stage_size` confounder.

    `source` is company_confounder_value's vocabulary ('scraped' | 'researched' |
    'declared'); `provenance` is the free-text note kept on the company row ('careers
    page', 'LinkedIn, 2026-09') and defaults to the vocabulary word. The confounder row
    is upserted on its existing key (company, 'stage_size', source, as_of), so re-stating
    a size for the same date updates rather than duplicates. Returns the band written.
    """
    from model import SCORE_SOURCES, Company, CompanyConfounderValue

    _require_vocab(source, SCORE_SOURCES, "source")
    band = stage_size_for_headcount(headcount)
    company = _get_or_raise(db, Company, company_id, "company")

    company.headcount = headcount
    company.headcount_as_of = as_of
    company.headcount_source = provenance or source

    row = (
        db.session.query(CompanyConfounderValue)
        .filter_by(company_id=company_id, confounder_key="stage_size", source=source, as_of=as_of)
        .first()
    )
    if row is None:
        row = CompanyConfounderValue(
            company_id=company_id,
            confounder_key="stage_size",
            source=source,
            as_of=as_of,
        )
        db.session.add(row)
    row.value_num = float(band)
    row.value_cat = None
    db.session.commit()
    return band


# ---------------------------------------------------------------------------
# Bulk reads for the match service (C6)
# ---------------------------------------------------------------------------

def companies_with_shared_records(db) -> list[int]:
    """Ids of every company that has at least one SHARED (research-derived) trait
    record, in id order. What `/me/matches` ranks: a company nobody has researched has
    nothing to read."""
    from model import CompanyTraitRecord

    rows = (
        db.session.query(CompanyTraitRecord.company_id)
        .filter(CompanyTraitRecord.job_posting_id.is_(None))
        .distinct()
        .order_by(CompanyTraitRecord.company_id)
        .all()
    )
    return [company_id for (company_id,) in rows]


def shared_records_by_company(
    db, company_ids: Iterable[int], scope: Optional[str] = "company"
) -> dict[int, list[TraitRecordView]]:
    """`trait_records` for many companies in one statement: `{company_id: [records]}`,
    current record per (dimension, scope, scope_label), shared rows only. A company with
    no record is absent from the dict. `scope` narrows to one scope (default: the
    company-wide read the research step writes); None returns every scope."""
    from model import EVIDENCE_SCOPES, CompanyTraitRecord

    ids = list(company_ids)
    if not ids:
        return {}
    filters = [
        CompanyTraitRecord.company_id.in_(ids),
        CompanyTraitRecord.job_posting_id.is_(None),
    ]
    if scope is not None:
        _require_vocab(scope, EVIDENCE_SCOPES, "scope")
        filters.append(CompanyTraitRecord.scope == scope)
    out: dict[int, list[TraitRecordView]] = {}
    for record in _latest_records(db, *filters):
        out.setdefault(record.company_id, []).append(record)
    return out


def confounder_values(db, company_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """`{company_id: {confounder_key: value}}` from company_confounder_value, the latest
    `as_of` per (company, key) winning. The value is `value_num` when present, else
    `value_cat`. A company with no rows is absent; a key with no row is absent -- the
    caller masks it (match_core's `conf_missing`), never defaults it (D-07)."""
    from model import CompanyConfounderValue as Row

    ids = list(company_ids)
    if not ids:
        return {}
    rows = (
        db.session.query(Row.company_id, Row.confounder_key, Row.value_num, Row.value_cat)
        .filter(Row.company_id.in_(ids))
        .order_by(Row.company_id, Row.confounder_key, Row.as_of.asc(), Row.id.asc())
        .all()
    )
    out: dict[int, dict[str, Any]] = {}
    for company_id, key, value_num, value_cat in rows:
        # ascending as_of: the last write per key is the latest, and overwrites.
        out.setdefault(company_id, {})[key] = value_num if value_num is not None else value_cat
    return out


# ---------------------------------------------------------------------------
# "I took this job" links (user-keyed)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompanyLinkView:
    id: int
    user_id: int
    company_id: int
    started_on: datetime.date
    ended_on: Optional[datetime.date]
    created_at: datetime.datetime


def _link_view(row) -> CompanyLinkView:
    return CompanyLinkView(
        id=row.id,
        user_id=row.user_id,
        company_id=row.company_id,
        started_on=row.started_on,
        ended_on=row.ended_on,
        created_at=row.created_at,
    )


def create_company_link(
    db, user_id: int, *, company_id: int, started_on: datetime.date
) -> CompanyLinkView:
    """Record that the user took a job at *company_id* on *started_on*. The company must
    exist (`ValueError` otherwise, before anything is written).

    ONE CURRENT JOB PER USER (orchestrator ruling, 2026-10-13): if the user already has
    an open link (`ended_on IS NULL`), it is closed in this same transaction before the
    new one is inserted. The closed link's `ended_on` is the new link's `started_on` --
    or, when the new job is backdated earlier than the open link's own `started_on`,
    that open link's `started_on`, so `ck_ucl_ended_after_started` never trips. This
    plus `ix_ucl_one_open_per_user` (a partial unique index on `user_id` where
    `ended_on IS NULL`) is what keeps `pulse_store`'s active-link lookup unambiguous.
    """
    from model import Company, UserCompanyLink

    if not isinstance(started_on, datetime.date) or isinstance(started_on, datetime.datetime):
        raise ValueError("started_on must be a date")
    _get_or_raise(db, Company, company_id, "company")
    open_link = (
        db.session.query(UserCompanyLink)
        .filter(UserCompanyLink.user_id == user_id, UserCompanyLink.ended_on.is_(None))
        .first()
    )
    if open_link is not None:
        open_link.ended_on = max(started_on, open_link.started_on)
    row = UserCompanyLink(user_id=user_id, company_id=company_id, started_on=started_on)
    db.session.add(row)
    db.session.commit()
    return _link_view(row)


def company_links_for_user(db, user_id: int) -> list[CompanyLinkView]:
    """Every link the user made, newest start first. The /me/company-links and
    /me/export read."""
    from model import UserCompanyLink

    rows = (
        db.session.query(UserCompanyLink)
        .filter(UserCompanyLink.user_id == user_id)
        .order_by(UserCompanyLink.started_on.desc(), UserCompanyLink.id.desc())
        .all()
    )
    return [_link_view(r) for r in rows]


def end_company_link(
    db, user_id: int, link_id: int, *, ended_on: datetime.date
) -> Optional[CompanyLinkView]:
    """"I left": owner-only close of one of the user's own links. Returns None when no
    such link belongs to this user (the route answers 404 either way, so a link id
    cannot be probed). Raises `ValueError` when *ended_on* is before the link's
    `started_on` -- the same rule `ck_ucl_ended_after_started` enforces in the DB."""
    from model import UserCompanyLink

    if not isinstance(ended_on, datetime.date) or isinstance(ended_on, datetime.datetime):
        raise ValueError("ended_on must be a date")
    row = (
        db.session.query(UserCompanyLink)
        .filter(UserCompanyLink.id == link_id, UserCompanyLink.user_id == user_id)
        .first()
    )
    if row is None:
        return None
    if ended_on < row.started_on:
        raise ValueError("ended_on must be on or after started_on")
    row.ended_on = ended_on
    db.session.commit()
    return _link_view(row)


def delete_company_link(db, user_id: int, link_id: int) -> bool:
    """Remove one of the user's own links. False when no such link belongs to this
    user -- the route answers 404 either way, so a link id cannot be probed."""
    from model import UserCompanyLink

    row = (
        db.session.query(UserCompanyLink)
        .filter(UserCompanyLink.id == link_id, UserCompanyLink.user_id == user_id)
        .first()
    )
    if row is None:
        return False
    db.session.delete(row)
    db.session.commit()
    return True


def delete_company_links_for_user(db, user_id: int, *, commit: bool = True) -> int:
    """Destroy every link the user made. NOT called by account deletion (auth-accounts'
    ruling: account deletion RETAINS the user's company links, house precedent
    `employer_name_normalized`); kept for the user's own `DELETE /me/company-links/<id>`
    path and tests, same `commit=False` convention as `delete_job_postings_for_user`.
    C8's `pulse_checkins.company_link_id` is `ON DELETE SET NULL`, so nothing has to run
    before this -- deleting a link here, or one at a time, never blocks on it."""
    from model import UserCompanyLink

    removed = (
        db.session.query(UserCompanyLink)
        .filter(UserCompanyLink.user_id == user_id)
        .delete(synchronize_session=False)
    )
    if commit:
        db.session.commit()
    return removed
