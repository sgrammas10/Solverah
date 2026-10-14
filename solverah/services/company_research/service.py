"""The CompanyLens pipeline's front door: what C6's routes and the CLI call.

    request_research   -- name or id -> a run view (cached, in flight, or newly queued)
    run_research_job   -- the job body: research -> items -> scores -> records
    submit_job_posting -- a user's paste -> a posting view, its job dispatched
    run_job_posting_job-- the job body: extract -> items -> scores -> private records
    aggregate_company  -- re-aggregate from stored scores (no provider call)
    sweep_research_runs-- re-dispatch lost enqueues, fail dead runs

Every provider failure is recorded on the run row with the cost spent so far and a
fixed-vocabulary error string (never a raw exception: those carry request ids and
prompt fragments). ``LLMProviderUnavailable`` is raised OUT of ``request_research`` and
``submit_job_posting`` before anything is written or spent, for the route to map to a
503; inside a job it is a failed run.

The job bodies take an id and no ``db`` (``scoring_jobs.run`` has the same shape): a
Celery task or a thread calls them with nothing but the id, and they use the app's
session inside the context the caller pushed.

THE PUBLIC SWITCH (C5c, 2026-10-14). ``SOLVERAH_COMPANYLENS_RESEARCH_ENABLED``
(``research_enabled``, read at call time, default OFF) is what opens on-demand
research to signed-in users -- not the presence of ``ANTHROPIC_API_KEY``. Review-site
collection waits for attorney review before it is public (decided 2026-10-13), and a
key in Render must not be that decision. Off, ``request_research`` raises
``ResearchDisabled`` before writing anything, unless the caller passes
``allow_when_disabled=True`` (the CLI's ``--allow-when-disabled``, an internal batch
prefill). Reading existing research is never gated. Pasted postings never use the
research client and are not gated either.

OWNERSHIP OF A RUN (C5c). Production dispatches a run twice on purpose -- the web
pool at request time and the sweep cron for a row still ``queued`` after five minutes
-- so the job body CLAIMS the row first (``store.mark_research_run_running``, one
conditional UPDATE) and returns without a provider call when the claim fails. After
the research turn it checks it still owns the row before writing anything, and
finishes with a conditional UPDATE (``WHERE status = 'running'``): a row the sweep
reaped as ``timed_out`` keeps that verdict, the late result's items and records are
discarded, and the money is recorded under ``late_finish`` in the internal run card.
"""

from __future__ import annotations

import datetime
import logging
import os
from decimal import Decimal
from typing import Optional

import company_evidence_store as store
from company_evidence_store import JobPostingView, ResearchRunView
from solverah.infra import llm
from solverah.infra.llm import LLMProviderUnavailable
from solverah.infra.llm.research import (
    ResearchCallError,
    ResearchIncomplete,
    ResearchProviderError,
    ResearchRefused,
    estimate_research_cost_usd,
)
from solverah.repositories import company_repository
from solverah.services.company_research import aggregate as _aggregate
from solverah.services.company_research import jobs, job_posting, research, score_items
from solverah.services.company_research.constants import (
    RESEARCH_CACHE_DAYS,
    RESEARCH_JOB_HARD_LIMIT_SECONDS,
    STALE_QUEUED_MINUTES,
)
from solverah.services.company_research.prompts import RESEARCH_PROMPT_VERSION

__all__ = [
    "ERROR_INCOMPLETE",
    "ERROR_PIPELINE",
    "ERROR_PROVIDER",
    "ERROR_PROVIDER_UNAVAILABLE",
    "ERROR_REFUSED",
    "ERROR_SCORING",
    "ERROR_TIMED_OUT",
    "ERROR_UNPARSEABLE",
    "ERROR_UNVERIFIED",
    "PROVIDER",
    "RESEARCH_ENABLED_VAR",
    "ResearchDisabled",
    "aggregate_company",
    "existing_run",
    "find_company",
    "request_research",
    "research_enabled",
    "research_run_summary",
    "resolve_company",
    "run_job_posting_job",
    "run_research_job",
    "submit_job_posting",
    "sweep_research_runs",
]

logger = logging.getLogger("solverah.company_research")

PROVIDER = "anthropic"

#: The public switch. Read at call time; default OFF. See the module docstring.
RESEARCH_ENABLED_VAR = "SOLVERAH_COMPANYLENS_RESEARCH_ENABLED"
_TRUTHY = ("1", "true", "yes", "on")


def research_enabled() -> bool:
    """Whether on-demand company research may start a NEW run for a user."""
    return (os.environ.get(RESEARCH_ENABLED_VAR) or "").strip().lower() in _TRUTHY


class ResearchDisabled(RuntimeError):
    """``request_research`` would have started a new paid run, and the switch is off.
    Raised before anything is written; the route maps it to a 503 problem document
    with code ``research_disabled``."""

#: The fixed vocabulary `company_research_run.error` is written from.
ERROR_REFUSED = "research_refused"
ERROR_INCOMPLETE = "research_incomplete"
ERROR_PROVIDER = "research_provider_error"
ERROR_UNPARSEABLE = "research_unparseable"
#: The turn produced a record but nothing survived verification (candidates, zero
#: kept), or it carried no citation at all. A FAILED run, not six quiet unknowns
#: (review F2): the cost is recorded and the run card says what was dropped and why.
ERROR_UNVERIFIED = "research_unverified"
ERROR_PROVIDER_UNAVAILABLE = "provider_unavailable"
ERROR_SCORING = "scoring_failed"
ERROR_PIPELINE = "pipeline_error"
ERROR_TIMED_OUT = "timed_out"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

def resolve_company(db, *, company_name: Optional[str] = None, company_id: Optional[int] = None):
    """The ``Company`` row for a request: by id when given (must exist), else found or
    created by name (``company_repository.find_or_create_company``)."""
    from model import Company

    if company_id is not None:
        company = db.session.get(Company, company_id)
        if company is None:
            raise ValueError("company %r does not exist" % (company_id,))
        return company
    if not company_name or not company_name.strip():
        raise ValueError("request_research needs a company_name or a company_id")
    return company_repository.find_or_create_company(company_name)


def find_company(db, company_name: str):
    """The ``Company`` row a request for *company_name* would resolve to, or None --
    WITHOUT creating one. The route reads this first so a refused request (switch off,
    no provider, budget spent) writes nothing, not even the company row."""
    return company_repository.find_company(company_name)


# ---------------------------------------------------------------------------
# Research: request + job
# ---------------------------------------------------------------------------

def _cache_fresh(run: ResearchRunView, now: datetime.datetime) -> bool:
    if run.status != "done" or run.finished_at is None:
        return False
    finished = run.finished_at
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=datetime.timezone.utc)
    return (now - finished) <= datetime.timedelta(days=RESEARCH_CACHE_DAYS)


def existing_run(db, company_id: int, *, force: bool = False) -> Optional[ResearchRunView]:
    """The run `request_research` would return WITHOUT starting one: the in-flight run,
    or the latest `done` run while it is younger than the cache window (unless *force*).
    None means a request now would queue a NEW run -- what the route's per-user daily
    budget counts."""
    latest = store.latest_research_run(db, company_id)
    if latest is None:
        return None
    if latest.status in ("queued", "running"):
        return latest
    if not force and _cache_fresh(latest, _now()):
        return latest
    return None


def request_research(
    db,
    *,
    company_name: Optional[str] = None,
    company_id: Optional[int] = None,
    trigger: str,
    force: bool = False,
    dispatch: bool = True,
    allow_when_disabled: bool = False,
) -> ResearchRunView:
    """Research a company on demand, with the 90-day cache.

    Returns the latest ``done`` run when it is younger than ``RESEARCH_CACHE_DAYS``
    (unless *force*), the in-flight run as is when one is ``queued`` or ``running``,
    and otherwise a newly ``queued`` run whose job has been dispatched (unless
    *dispatch* is False: the CLI runs the job itself). The view returned for a new run
    is the row as queued, even when the job ran inline before this returns.

    Raises ``ResearchDisabled`` BEFORE writing anything when a new run is needed and
    the public switch is off (unless *allow_when_disabled*: the CLI's internal batch
    prefill), and ``LLMProviderUnavailable`` when either provider has no key: nothing
    is spent, and the route answers 503 either way. Cached and in-flight runs are
    returned under both conditions -- reading research is never gated. The caller may
    resolve the company first (``find_company``) to keep the company row unwritten.
    """
    company = resolve_company(db, company_name=company_name, company_id=company_id)
    now = _now()
    latest = store.latest_research_run(db, company.id)
    if latest is not None:
        if latest.status in ("queued", "running"):
            return latest
        if not force and _cache_fresh(latest, now):
            return latest

    if not allow_when_disabled and not research_enabled():
        raise ResearchDisabled(
            "company research is switched off (%s is not set)" % RESEARCH_ENABLED_VAR
        )
    # Both providers must be reachable before a run is queued: a run that would fail
    # at the first call for want of a key should be a 503 now, not a failed row later.
    llm.get_research_client()
    llm.get_scorer_client()

    run = store.start_research_run(
        db, company.id,
        trigger=trigger, provider=PROVIDER, model=llm.default_research_model(),
        prompt_version=RESEARCH_PROMPT_VERSION, status="queued",
    )
    if dispatch:
        from solverah.tasks.company_research_tasks import run_research_task

        jobs.dispatch(run_research_task, run_research_job, run.id)
    return run


def _research_error_label(exc: ResearchCallError) -> str:
    if isinstance(exc, ResearchRefused):
        return ERROR_REFUSED
    if isinstance(exc, ResearchIncomplete):
        return ERROR_INCOMPLETE
    if isinstance(exc, research.ResearchParseError):
        return ERROR_UNPARSEABLE
    if isinstance(exc, ResearchProviderError):
        return ERROR_PROVIDER
    return ERROR_PIPELINE


def _soft_time_limit_exception():
    try:
        from celery.exceptions import SoftTimeLimitExceeded
    except Exception:  # pragma: no cover - celery is a hard dependency
        return ()
    return (SoftTimeLimitExceeded,)


def _owned(db, run_id: int) -> bool:
    """Whether this thread still owns the run: the row is ``running``. Fresh from the
    database every time (the sweep writes from another process)."""
    from model import CompanyResearchRun

    db.session.expire_all()
    row = db.session.get(CompanyResearchRun, run_id)
    return row is not None and row.status == "running"


def run_research_job(run_id: int) -> ResearchRunView:
    """The research job body. Claims the row first and makes NO provider call unless
    the claim wins (see the module docstring, "ownership of a run"). Idempotent on a
    terminal row and a no-op on a row another worker owns: both return the row as is."""
    from model import CompanyResearchRun, db

    row = db.session.get(CompanyResearchRun, run_id)
    if row is None:
        raise ValueError("research run %r does not exist" % (run_id,))
    claimed = store.mark_research_run_running(db, run_id)
    if claimed is None:
        # Already running (another worker's), done, or failed: nothing to do here.
        db.session.expire_all()
        current = store.research_run(db, run_id)
        logger.info(
            "company_research_claim_lost",
            extra={"event": "company_research_claim_lost", "run_id": run_id,
                   "status": current.status},
        )
        return current
    row = db.session.get(CompanyResearchRun, run_id)
    company_id = row.company_id
    company = row.company

    cost: Optional[float] = None
    diagnostics: Optional[dict] = None
    try:
        outcome = research.run_research(company.name, domain=company.domain)
        cost = outcome.cost_usd
        diagnostics = dict(outcome.diagnostics)
        if outcome.unverified_run:
            raise _Unverified(
                "candidates=%d kept=%d citations=%d"
                % (outcome.candidates, len(outcome.items), outcome.citations)
            )
        # The turn took minutes; the sweep may have reaped the row meanwhile. Nothing
        # is written for a run this thread no longer owns.
        if not _owned(db, run_id):
            return _late(db, run_id, "done", cost)
        item_ids = store.write_items(db, company_id, outcome.items, research_run_id=run_id)
        if outcome.headcount is not None:
            store.set_company_size(
                db, company_id, outcome.headcount,
                as_of=outcome.headcount_as_of or datetime.date.today(),
                source="researched",
                provenance=outcome.headcount_source,
            )
        if outcome.domain and not company.domain:
            company_repository.claim_domain(company, outcome.domain)
        try:
            scoring = score_items.score_items(
                db, item_ids, packet_version=outcome.prompt_version,
                notes="research run %d" % run_id,
            )
        except LLMProviderUnavailable:
            raise
        except Exception as exc:
            raise _ScoringFailed(str(exc)) from exc
        diagnostics["scoring"] = {
            "scorer_run_id": scoring.scorer_run_id, "items": scoring.items,
            "scored": scoring.scored, "abstained": scoring.abstained, "calls": scoring.calls,
            "prompt_tokens": scoring.prompt_tokens,
            "completion_tokens": scoring.completion_tokens,
            "temperature_honored": scoring.temperature_honored, "model": scoring.model,
        }
        _ids, report = _aggregate.aggregate_company_report(
            db, company_id, research_run_id=run_id
        )
        diagnostics["aggregation"] = report
        finished = store.finish_research_run(
            db, run_id, status="done", cost_usd=cost, diagnostics=diagnostics
        )
        if finished is None:
            # Reaped between the ownership check and the finish: the items and the
            # record generation above were written for a run we no longer own.
            return _late(db, run_id, "done", cost, discard=True)
        logger.info(
            "company_research_done",
            extra={
                "event": "company_research_done", "run_id": run_id, "company_id": company_id,
                "items": len(item_ids), "candidates": outcome.candidates,
                "dropped_unverified": outcome.dropped_unverified,
                "dropped_paraphrase": outcome.dropped_paraphrase,
                "dropped_invalid": outcome.dropped_invalid,
                "scorer_run_id": scoring.scorer_run_id, "scorer_calls": scoring.calls,
                "scorer_prompt_tokens": scoring.prompt_tokens,
                "scorer_completion_tokens": scoring.completion_tokens,
                "cost_usd": cost,
            },
        )
        return finished
    except ResearchCallError as exc:
        db.session.rollback()
        return _fail(db, run_id, _research_error_label(exc),
                     estimate_research_cost_usd(exc.usage), exc,
                     getattr(exc, "diagnostics", None))
    except _Unverified as exc:
        db.session.rollback()
        return _fail(db, run_id, ERROR_UNVERIFIED, cost, exc, diagnostics)
    except LLMProviderUnavailable as exc:
        db.session.rollback()
        return _fail(db, run_id, ERROR_PROVIDER_UNAVAILABLE, cost, exc, diagnostics)
    except _ScoringFailed as exc:
        db.session.rollback()
        return _fail(db, run_id, ERROR_SCORING, cost, exc, diagnostics)
    except _soft_time_limit_exception() as exc:
        db.session.rollback()
        return _fail(db, run_id, ERROR_TIMED_OUT, cost, exc, diagnostics)
    except Exception as exc:  # noqa: BLE001 -- the run row is the error channel
        db.session.rollback()
        return _fail(db, run_id, ERROR_PIPELINE, cost, exc, diagnostics)


class _ScoringFailed(RuntimeError):
    pass


class _Unverified(RuntimeError):
    pass


def _fail(db, run_id: int, label: str, cost: Optional[float], exc: BaseException,
          diagnostics: Optional[dict] = None) -> ResearchRunView:
    logger.exception(
        "company_research_failed",
        extra={"event": "company_research_failed", "run_id": run_id, "error": label,
               "cost_usd": cost, "exc_type": type(exc).__name__},
    )
    finished = store.finish_research_run(
        db, run_id, status="failed", cost_usd=cost, error=label, diagnostics=diagnostics
    )
    if finished is None:
        return _late(db, run_id, "failed", cost, error=label, discard=True)
    return finished


def _late(db, run_id: int, attempted: str, cost: Optional[float], *,
          error: Optional[str] = None, discard: bool = False) -> ResearchRunView:
    """The thread finished a run it no longer owns (the sweep reaped it). The reaper's
    verdict stands; whatever this run wrote is removed (*discard*) and the shared read
    is rebuilt from the latest ``done`` run; the cost is noted in the internal card."""
    from model import CompanyResearchRun

    db.session.rollback()
    removed = 0
    if discard:
        removed = store.discard_research_run_output(db, run_id)
        row = db.session.get(CompanyResearchRun, run_id)
        if removed and _aggregate.latest_done_run_id(db, row.company_id) is not None:
            _aggregate.aggregate_company(db, row.company_id)
    store.record_late_research_finish(
        db, run_id, attempted_status=attempted, cost_usd=cost, error=error,
        items_discarded=removed,
    )
    current = store.research_run(db, run_id)
    logger.warning(
        "company_research_late_finish",
        extra={"event": "company_research_late_finish", "run_id": run_id,
               "attempted_status": attempted, "row_status": current.status,
               "cost_usd": cost, "items_discarded": removed},
    )
    return current


# ---------------------------------------------------------------------------
# Job postings: submit + job
# ---------------------------------------------------------------------------

def submit_job_posting(
    db,
    user_id: int,
    *,
    company_id: int,
    text: str,
    title: Optional[str] = None,
    dispatch: bool = True,
) -> JobPostingView:
    """Store a user's pasted posting under *company_id* and dispatch its scoring.

    A posting with no company cannot be scored (evidence items belong to a company),
    so *company_id* is required here and must exist: ``ValueError`` otherwise, before
    anything is written. Raises ``LLMProviderUnavailable`` before writing when the
    scorer has no key. The research client is never involved.
    """
    from model import Company

    if company_id is None:
        raise ValueError("a job posting needs a company before it can be scored")
    if db.session.get(Company, company_id) is None:
        raise ValueError("company %r does not exist" % (company_id,))
    if not text or not text.strip():
        raise ValueError("a job posting needs its text")
    llm.get_scorer_client()

    posting = store.create_job_posting(
        db, user_id, posting_text=text, company_id=company_id, title=title
    )
    if dispatch:
        from solverah.tasks.company_research_tasks import run_job_posting_task

        jobs.dispatch(run_job_posting_task, run_job_posting_job, posting.id)
    return posting


def run_job_posting_job(posting_id: int) -> JobPostingView:
    """The posting job body. Idempotent on a non-pending row."""
    from model import JobPostingSubmission, db

    row = db.session.get(JobPostingSubmission, posting_id)
    if row is None:
        raise ValueError("job posting %r does not exist" % (posting_id,))
    if row.status != "pending":
        return store._posting_view(row)
    if row.company_id is None:
        return store.set_job_posting_status(db, posting_id, "failed")

    try:
        extraction = job_posting.extract_posting_items(row.posting_text, title=row.title)
        item_ids = store.write_items(
            db, row.company_id, extraction.items, job_posting_id=posting_id
        )
        score_items.score_items(
            db, item_ids, packet_version=extraction.prompt_version,
            notes="job posting %d" % posting_id,
        )
        _aggregate.aggregate_posting(db, posting_id)
        logger.info(
            "job_posting_scored",
            extra={"event": "job_posting_scored", "posting_id": posting_id,
                   "items": len(item_ids), "candidates": extraction.candidates,
                   "dropped_unverified": extraction.dropped_unverified,
                   "dropped_paraphrase": extraction.dropped_paraphrase},
        )
        return store.set_job_posting_status(db, posting_id, "scored")
    except Exception as exc:  # noqa: BLE001 -- the posting row is the error channel
        db.session.rollback()
        logger.exception(
            "job_posting_failed",
            extra={"event": "job_posting_failed", "posting_id": posting_id,
                   "exc_type": type(exc).__name__},
        )
        return store.set_job_posting_status(db, posting_id, "failed")


# ---------------------------------------------------------------------------
# Aggregation and reporting
# ---------------------------------------------------------------------------

def aggregate_company(db, company_id: int) -> list[int]:
    """Re-aggregate the shared records from the stored scores. No provider call."""
    return _aggregate.aggregate_company(db, company_id)


def research_run_summary(db, run_id: int) -> dict:
    """What the CLI prints per company: run status, cost, counts, the records. The
    counts come from the run card; its text never does (GAP-14 -- the card is
    internal, and this summary goes to stdout)."""
    from model import Company, CompanyEvidenceItem, CompanyResearchRun

    row = db.session.get(CompanyResearchRun, run_id)
    if row is None:
        raise ValueError("research run %r does not exist" % (run_id,))
    company = db.session.get(Company, row.company_id)
    items = (
        db.session.query(CompanyEvidenceItem)
        .filter(CompanyEvidenceItem.research_run_id == run_id)
        .count()
    )
    records = store.trait_records(db, row.company_id, scope="company")
    card = row.diagnostics_internal or {}
    return {
        "company": company.name,
        "company_id": company.id,
        "run_id": row.id,
        "status": row.status,
        "error": row.error,
        "model": row.model,
        "served_model": card.get("served_model"),
        "cost_usd": None if row.cost_usd is None else float(row.cost_usd),
        "candidates": card.get("candidates"),
        "citations": (card.get("citations") or {}).get("total"),
        "dropped": {k: v for k, v in (card.get("dropped") or {}).items() if k != "by_reason"},
        "items": items,
        "headcount": company.headcount,
        "records": {r.dimension_key: r.status for r in records},
        "known": sum(1 for r in records if r.status == "known"),
    }


def sweep_research_runs(db, *, now: Optional[datetime.datetime] = None) -> dict:
    """Re-dispatch ``queued`` runs older than ``STALE_QUEUED_MINUTES`` (a lost enqueue)
    and fail ``running`` runs older than the research hard limit (a dead worker or
    thread). The sweep behind ``enqueue``, as ``scoring_jobs.sweep`` is for its table."""
    from model import CompanyResearchRun

    now = now or _now()
    stale_queued = now - datetime.timedelta(minutes=STALE_QUEUED_MINUTES)
    dead_running = now - datetime.timedelta(seconds=RESEARCH_JOB_HARD_LIMIT_SECONDS)

    requeued = 0
    for (run_id,) in db.session.query(CompanyResearchRun.id).filter(
        CompanyResearchRun.status == "queued", CompanyResearchRun.created_at < stale_queued
    ):
        from solverah.tasks.company_research_tasks import run_research_task

        jobs.dispatch(run_research_task, run_research_job, run_id)
        requeued += 1

    reaped = 0
    for (run_id,) in db.session.query(CompanyResearchRun.id).filter(
        CompanyResearchRun.status == "running", CompanyResearchRun.started_at < dead_running
    ).all():
        # Conditional: a thread that finished between the query and this update keeps
        # its result, and the reap counts only when it was the one that closed the row.
        if store.finish_research_run(db, run_id, status="failed", error=ERROR_TIMED_OUT):
            reaped += 1
    return {"requeued": requeued, "reaped": reaped}


def total_cost_usd(db, run_ids) -> Optional[Decimal]:
    from model import CompanyResearchRun

    total = Decimal("0")
    for (cost,) in db.session.query(CompanyResearchRun.cost_usd).filter(
        CompanyResearchRun.id.in_(list(run_ids))
    ):
        if cost is not None:
            total += Decimal(cost)
    return total
