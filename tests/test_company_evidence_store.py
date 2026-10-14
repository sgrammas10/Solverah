"""The company evidence pipeline's storage (six-trait build, C3): the data contract and
the store that is its only door.

Three things are pinned here, all against the real Postgres test database:

1. The CHECK constraints, exercised directly through the ORM so the DATABASE is what
   refuses a bad row -- a 'known' record with no estimate, a 'mixed' record with no ends
   (or an averaged one with an estimate), an abstention that carries a score, an item
   with both parents or neither. Every expected-failure test writes a sibling VALID row
   so it cannot pass because the table is broken for all inserts (the S-40 lesson).
2. The store's behaviour: lifecycle of a research run, latest-record-wins, derived counts
   and dates, the posting cascade, the stage_size bands, and that no view ever carries
   `excerpt_internal`.
3. The migration, both directions, run for real: the schema the fixtures build
   (`db.create_all()`) is the post-upgrade one, so `downgrade()` is run against it, the
   tables are shown gone, `upgrade()` is run, and the constraint/index/column catalog is
   shown IDENTICAL to what the ORM built -- the ORM-vs-migration parity check for these
   six tables and the three company columns. Transactional DDL rolls it all back.
"""
from __future__ import annotations

import dataclasses
import datetime
import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

import company_evidence_store as store

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations" / "versions" / "20261013_company_evidence.py"
)
NEW_TABLES = (
    "company_research_run",
    "job_posting_submission",
    "company_evidence_item",
    "evidence_item_score",
    "company_trait_record",
    "company_trait_record_evidence",
)
COMPANY_COLUMNS = ("headcount", "headcount_as_of", "headcount_source")
UTC = datetime.timezone.utc
D = datetime.date


# ---------------------------------------------------------------------------
# Fixtures and builders
# ---------------------------------------------------------------------------

def _mk_company(db, name="Acme", slug="acme"):
    from model import Company

    company = Company(name=name, slug=slug, profile_json={})
    db.session.add(company)
    db.session.commit()
    return company


def _mk_scorer_run(db, rubric_version="v3.1"):
    from model import ScorerRun

    run = ScorerRun(
        model="gpt-5.5-2026-04-23", temperature=0, temperature_honored=True,
        rubric_version=rubric_version, packet_version="v4.11",
    )
    db.session.add(run)
    db.session.commit()
    return run


def _item(scope="company", source_type="employee_review", **kw):
    kw.setdefault("excerpt_internal", "Verbatim third-party text the scorer saw.")
    kw.setdefault("paraphrase", "Reviewers describe a fast pace.")
    return store.EvidenceItemInput(scope=scope, source_type=source_type, **kw)


def _research_run(db, company):
    return store.start_research_run(
        db, company.id, trigger="on_demand", provider="anthropic",
        model="claude-x-2026-09-01", prompt_version="r1",
    )


@pytest.fixture()
def world(client):
    """A company, an open research run, a scorer run, and the app context to use them in."""
    from app import app
    from model import db

    with app.app_context():
        company = _mk_company(db)
        run = _research_run(db, company)
        scorer = _mk_scorer_run(db)
        yield db, company, run, scorer


# ---------------------------------------------------------------------------
# Research runs
# ---------------------------------------------------------------------------

def test_research_run_lifecycle_and_latest(world):
    db, company, run, _ = world
    assert run.status == "running" and run.started_at is not None and run.finished_at is None
    assert store.latest_research_run(db, company.id).id == run.id

    done = store.finish_research_run(db, run.id, status="done", cost_usd=0.0421)
    assert done.status == "done"
    assert done.finished_at is not None
    assert done.cost_usd == Decimal("0.0421")
    assert done.error is None

    later = store.start_research_run(
        db, company.id, trigger="batch", provider="anthropic",
        model="claude-x-2026-09-01", prompt_version="r1", status="queued",
    )
    assert later.status == "queued" and later.started_at is None
    assert store.latest_research_run(db, company.id).id == later.id
    running = store.mark_research_run_running(db, later.id)
    assert running.status == "running" and running.started_at is not None
    failed = store.finish_research_run(db, later.id, status="failed", error="provider_timeout")
    assert failed.error == "provider_timeout"

    other = _mk_company(db, name="Other", slug="other")
    assert store.latest_research_run(db, other.id) is None


def test_finish_rules_are_checked_before_the_database(world):
    db, _, run, _ = world
    with pytest.raises(ValueError, match="no error"):
        store.finish_research_run(db, run.id, status="done", error="x")
    with pytest.raises(ValueError, match="must say why"):
        store.finish_research_run(db, run.id, status="failed")
    with pytest.raises(ValueError, match="one of"):
        store.finish_research_run(db, run.id, status="running")
    with pytest.raises(ValueError, match="one of"):
        store.start_research_run(
            db, run.company_id, trigger="cron", provider="p", model="m", prompt_version="v",
        )


def test_database_refuses_a_terminal_run_without_finished_at(world):
    """The CHECKs behind the store: done needs finished_at, error only on failed."""
    from model import CompanyResearchRun

    db, company, _, _ = world
    now = datetime.datetime.now(UTC)

    def _run(**kw):
        row = CompanyResearchRun(
            company_id=company.id, trigger="batch", provider="p", model="m",
            prompt_version="v", **kw,
        )
        db.session.add(row)
        db.session.commit()

    _run(status="done", started_at=now, finished_at=now)  # the valid sibling
    for bad in (
        dict(status="done", started_at=now),                       # terminal, no finished_at
        dict(status="running", started_at=now, finished_at=now),   # not terminal, finished
        dict(status="running"),                                    # running, never started
        dict(status="done", started_at=now, finished_at=now, error="x"),  # error on done
    ):
        with pytest.raises(IntegrityError):
            _run(**bad)
        db.session.rollback()


# ---------------------------------------------------------------------------
# Evidence items: exactly one parent, scopes, the pasted-posting rules
# ---------------------------------------------------------------------------

def test_item_needs_exactly_one_parent_in_the_database(world):
    from model import CompanyEvidenceItem

    db, company, run, _ = world
    posting = store.create_job_posting(db, _user(db), posting_text="We move fast.")

    def _row(**kw):
        base = dict(company_id=company.id, scope="role", source_type="job_posting",
                    excerpt_internal="x", paraphrase="p")
        base.update(kw)
        db.session.add(CompanyEvidenceItem(**base))
        db.session.commit()

    _row(research_run_id=run.id)  # valid sibling
    with pytest.raises(IntegrityError):  # both
        _row(research_run_id=run.id, job_posting_id=posting.id, source_type="user_pasted_posting")
    db.session.rollback()
    with pytest.raises(IntegrityError):  # neither
        _row()
    db.session.rollback()
    with pytest.raises(IntegrityError):  # posting parent but not the posting source type
        _row(job_posting_id=posting.id)
    db.session.rollback()
    with pytest.raises(IntegrityError):  # posting at company scope
        _row(job_posting_id=posting.id, source_type="user_pasted_posting", scope="company")
    db.session.rollback()
    with pytest.raises(IntegrityError):  # a label at company scope
        _row(research_run_id=run.id, scope="company", scope_label="HQ")
    db.session.rollback()


def test_write_items_checks_the_same_rules_first(world):
    db, company, run, _ = world
    with pytest.raises(ValueError, match="exactly one"):
        store.write_items(db, company.id, [_item()])
    with pytest.raises(ValueError, match="exactly one"):
        store.write_items(db, company.id, [_item()], research_run_id=run.id, job_posting_id=1)
    with pytest.raises(ValueError, match="scope_label"):
        store.write_items(db, company.id, [_item(scope_label="HQ")], research_run_id=run.id)
    with pytest.raises(ValueError, match="under a job posting"):
        store.write_items(
            db, company.id, [_item(scope="role", source_type="user_pasted_posting")],
            research_run_id=run.id,
        )
    with pytest.raises(ValueError, match="paraphrase"):
        store.write_items(db, company.id, [_item(paraphrase="  ")], research_run_id=run.id)
    other = _mk_company(db, name="Other", slug="other")
    with pytest.raises(ValueError, match="belongs to company"):
        store.write_items(db, other.id, [_item()], research_run_id=run.id)

    ids = store.write_items(
        db, company.id,
        [_item(speaker="employee review, Cashier"),
         _item(scope="location", scope_label="Austin office", published_at=D(2026, 3, 1))],
        research_run_id=run.id,
    )
    assert len(ids) == 2 and ids[0] < ids[1]
    from model import CompanyEvidenceItem

    assert db.session.get(CompanyEvidenceItem, ids[0]).speaker == "employee review, Cashier"
    assert db.session.get(CompanyEvidenceItem, ids[1]).speaker is None


def test_pasted_posting_items_are_role_scope_only(world):
    db, company, _, _ = world
    unattached = store.create_job_posting(db, _user(db), posting_text="No company yet.")
    with pytest.raises(ValueError, match="has no company yet"):
        store.write_items(
            db, company.id,
            [_item(scope="role", source_type="user_pasted_posting")],
            job_posting_id=unattached.id,
        )
    posting = store.create_job_posting(db, _user(db), posting_text="We move fast.", company_id=company.id)
    with pytest.raises(ValueError, match="scope 'role'"):
        store.write_items(
            db, company.id, [_item(scope="company", source_type="user_pasted_posting")],
            job_posting_id=posting.id,
        )
    with pytest.raises(ValueError, match="'user_pasted_posting'"):
        store.write_items(
            db, company.id, [_item(scope="role", source_type="job_posting")],
            job_posting_id=posting.id,
        )
    ids = store.write_items(
        db, company.id,
        [_item(scope="role", scope_label="Staff Engineer", source_type="user_pasted_posting")],
        job_posting_id=posting.id,
    )
    assert len(ids) == 1


# ---------------------------------------------------------------------------
# Item scores: abstained <=> score IS NULL, idempotent per scorer run
# ---------------------------------------------------------------------------

def test_abstention_is_exclusive_with_a_score_in_the_database(world):
    from model import EvidenceItemScore

    db, company, run, scorer = world
    (item_id,) = store.write_items(db, company.id, [_item()], research_run_id=run.id)

    def _row(dim, **kw):
        row = EvidenceItemScore(
            evidence_item_id=item_id, dimension_key=dim, scorer_run_id=scorer.id, **kw
        )
        db.session.add(row)
        db.session.commit()

    _row("pace", score=0.8, abstained=False, confidence=0.6)   # valid siblings, both shapes
    _row("autonomy", score=None, abstained=True)
    with pytest.raises(IntegrityError):
        _row("feedback", score=0.5, abstained=True)
    db.session.rollback()
    with pytest.raises(IntegrityError):  # the scorer's confidence is a unit value
        _row("feedback", score=0.5, abstained=False, confidence=1.5)
    db.session.rollback()
    with pytest.raises(IntegrityError):
        _row("feedback", score=None, abstained=False)
    db.session.rollback()
    with pytest.raises(IntegrityError):  # same (item, dim, run) twice
        _row("pace", score=0.2, abstained=False)
    db.session.rollback()


def test_write_item_scores_is_idempotent_per_scorer_run(world):
    from model import EvidenceItemScore

    db, company, run, scorer = world
    (item_id,) = store.write_items(db, company.id, [_item()], research_run_id=run.id)

    with pytest.raises(ValueError, match="abstained scores carry no value"):
        store.write_item_scores(
            db, [store.ItemScoreInput(item_id, "pace", score=0.5, abstained=True)],
            scorer_run_id=scorer.id,
        )
    with pytest.raises(ValueError, match="needs a value"):
        store.write_item_scores(
            db, [store.ItemScoreInput(item_id, "pace")], scorer_run_id=scorer.id
        )
    with pytest.raises(ValueError, match="\\[0, 1\\]"):
        store.write_item_scores(
            db, [store.ItemScoreInput(item_id, "pace", score=1.5)], scorer_run_id=scorer.id
        )
    with pytest.raises(ValueError, match="carry no confidence"):
        store.write_item_scores(
            db, [store.ItemScoreInput(item_id, "pace", abstained=True, confidence=0.3)],
            scorer_run_id=scorer.id,
        )

    scores = [
        store.ItemScoreInput(item_id, "pace", score=0.8, confidence=0.9),
        store.ItemScoreInput(item_id, "autonomy", abstained=True),
    ]
    assert store.write_item_scores(db, scores, scorer_run_id=scorer.id) == 2
    # Re-presenting the same run updates in place: still two rows.
    scores[0] = store.ItemScoreInput(item_id, "pace", score=0.6, confidence=0.3)
    assert store.write_item_scores(db, scores, scorer_run_id=scorer.id) == 2
    rows = {r.dimension_key: r for r in EvidenceItemScore.query.filter_by(evidence_item_id=item_id)}
    assert len(rows) == 2 and rows["pace"].score == 0.6 and rows["autonomy"].abstained
    assert rows["pace"].confidence == 0.3 and rows["autonomy"].confidence is None

    # A new scorer run inserts beside, never over.
    rerun = _mk_scorer_run(db, rubric_version="v3.2")
    store.write_item_scores(db, scores[:1], scorer_run_id=rerun.id)
    assert EvidenceItemScore.query.filter_by(evidence_item_id=item_id).count() == 3


# ---------------------------------------------------------------------------
# Trait records: the shape rules, latest-wins, derived counts, evidence read
# ---------------------------------------------------------------------------

def test_record_shape_rules_hold_in_the_database(world):
    from model import CompanyTraitRecord

    db, company, _, _ = world

    def _row(**kw):
        base = dict(company_id=company.id, dimension_key="pace", scope="company",
                    aggregation_version="agg-test")
        base.update(kw)
        db.session.add(CompanyTraitRecord(**base))
        db.session.commit()

    # Valid siblings: one of each status, and the known-with-a-time-note shape.
    _row(status="known", estimate=0.7)
    _row(status="known", estimate=0.7, split_explained_by="time")  # "changed recently"
    _row(status="mixed", low_end=0.2, high_end=0.9, split_explained_by="scope")
    _row(status="unknown")
    for bad in (
        dict(status="known"),                                   # known without estimate
        dict(status="mixed"),                                   # mixed without ends
        dict(status="mixed", low_end=0.2, high_end=0.9, estimate=0.55),  # averaged mixed
        dict(status="mixed", low_end=0.9, high_end=0.2),        # ends reversed
        dict(status="mixed", low_end=0.2),                      # one end only
        dict(status="unknown", estimate=0.5),                   # unknown with a number
        dict(status="unknown", split_explained_by="time"),      # split on unknown
        dict(status="known", estimate=1.2),                     # out of range
        dict(status="known", estimate=0.5, scope_label="HQ"),   # label at company scope
        dict(status="unknown", first_dated=D(2026, 1, 1)),      # one date only
        dict(status="unknown", first_dated=D(2026, 2, 1), last_dated=D(2026, 1, 1)),
        dict(status="unknown", evidence_count=-1),
        dict(status="guess"),
    ):
        with pytest.raises(IntegrityError):
            _row(**bad)
        db.session.rollback()

    # A posting-derived record is role scope, by CHECK; the valid sibling first.
    posting = store.create_job_posting(db, _user(db), posting_text="x", company_id=company.id)
    _row(status="unknown", scope="role", scope_label="SWE", job_posting_id=posting.id)
    with pytest.raises(IntegrityError):
        _row(status="unknown", scope="division", scope_label="Eng", job_posting_id=posting.id)
    db.session.rollback()


@pytest.mark.parametrize(
    "rec, message",
    [
        (store.TraitRecordInput("pace", "company", "known"), "needs an estimate"),
        (store.TraitRecordInput("pace", "company", "mixed"), "needs low_end and high_end"),
        (store.TraitRecordInput("pace", "company", "mixed", low_end=0.1, high_end=0.9, estimate=0.5),
         "never averaged"),
        (store.TraitRecordInput("pace", "company", "unknown", estimate=0.5), "never averaged"),
        (store.TraitRecordInput("pace", "company", "known", estimate=0.5, low_end=0.1, high_end=0.9),
         "only a 'mixed'"),
        (store.TraitRecordInput("pace", "company", "mixed", low_end=0.9, high_end=0.1), "<="),
        (store.TraitRecordInput("pace", "company", "unknown", split_explained_by="time"),
         "only meaningful on a 'mixed'"),
        (store.TraitRecordInput("pace", "company", "known", estimate=0.5, scope_label="HQ"),
         "no scope_label"),
        (store.TraitRecordInput("pace", "company", "known", estimate=0.5, confidence=2.0), "\\[0, 1\\]"),
        (store.TraitRecordInput("pace", "team", "known", estimate=0.5), "one of"),
        (store.TraitRecordInput("pace", "company", "unknown", job_posting_id=1), "scope 'role'"),
    ],
)
def test_write_trait_records_refuses_the_shape_before_the_database(world, rec, message):
    db, company, _, _ = world
    with pytest.raises(ValueError, match=message):
        store.write_trait_records(db, company.id, [rec], aggregation_version="agg-test")


def test_latest_record_wins_per_dimension_scope_and_label(world):
    db, company, _, _ = world
    t0 = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    t1 = datetime.datetime(2026, 10, 1, tzinfo=UTC)

    # Generation 1: pace known at company scope, pace unknown in Austin.
    store.write_trait_records(
        db, company.id,
        [
            store.TraitRecordInput("pace", "company", "known", estimate=0.4),
            store.TraitRecordInput("pace", "location", "unknown", scope_label="Austin office"),
            store.TraitRecordInput("autonomy", "company", "unknown"),
        ],
        aggregation_version="agg-1", computed_at=t0,
    )
    # Generation 2: pace at company scope becomes mixed; Austin untouched; autonomy known.
    store.write_trait_records(
        db, company.id,
        [
            store.TraitRecordInput("pace", "company", "mixed", low_end=0.2, high_end=0.9,
                                   split_explained_by="scope"),
            store.TraitRecordInput("autonomy", "company", "known", estimate=0.6),
        ],
        aggregation_version="agg-2", computed_at=t1,
    )

    current = store.trait_records(db, company.id)
    assert [(r.dimension_key, r.scope, r.scope_label, r.status, r.aggregation_version)
            for r in current] == [
        ("autonomy", "company", None, "known", "agg-2"),
        ("pace", "company", None, "mixed", "agg-2"),
        ("pace", "location", "Austin office", "unknown", "agg-1"),
    ]
    mixed = current[1]
    assert mixed.estimate is None and (mixed.low_end, mixed.high_end) == (0.2, 0.9)
    assert mixed.split_explained_by == "scope"
    assert all(isinstance(r, store.TraitRecordView) for r in current)

    only_company = store.trait_records(db, company.id, scope="company")
    assert [r.dimension_key for r in only_company] == ["autonomy", "pace"]
    with pytest.raises(ValueError, match="one of"):
        store.trait_records(db, company.id, scope="team")

    # History is kept: five rows exist, three are current.
    from model import CompanyTraitRecord

    assert CompanyTraitRecord.query.filter_by(company_id=company.id).count() == 5

    other = _mk_company(db, name="Other", slug="other")
    assert store.trait_records(db, other.id) == []


def test_record_counts_and_dates_are_derived_from_the_linked_scores(world):
    db, company, run, scorer = world
    ids = store.write_items(
        db, company.id,
        [
            _item(published_at=D(2026, 1, 15), paraphrase="One"),
            _item(published_at=D(2025, 6, 1), paraphrase="Two", source_type="news"),
            _item(published_at=D(2026, 5, 1), paraphrase="Three (says nothing on pace)"),
            _item(paraphrase="Four, undated"),
        ],
        research_run_id=run.id,
    )
    store.write_item_scores(
        db,
        [
            store.ItemScoreInput(ids[0], "pace", score=0.8),
            store.ItemScoreInput(ids[1], "pace", score=0.7),
            store.ItemScoreInput(ids[2], "pace", abstained=True),
            store.ItemScoreInput(ids[3], "pace", score=0.9),
            store.ItemScoreInput(ids[0], "autonomy", score=0.1),
        ],
        scorer_run_id=scorer.id,
    )
    from model import EvidenceItemScore

    pace_ids = [s.id for s in EvidenceItemScore.query.filter_by(dimension_key="pace")]
    autonomy_id = EvidenceItemScore.query.filter_by(dimension_key="autonomy").one().id

    with pytest.raises(ValueError, match="on dimension 'autonomy'"):
        store.write_trait_records(
            db, company.id,
            [store.TraitRecordInput("pace", "company", "known", estimate=0.8, score_ids=[autonomy_id])],
            aggregation_version="agg-test",
        )
    with pytest.raises(ValueError, match="do not exist"):
        store.write_trait_records(
            db, company.id,
            [store.TraitRecordInput("pace", "company", "known", estimate=0.8, score_ids=[10_000])],
            aggregation_version="agg-test",
        )

    (record_id,) = store.write_trait_records(
        db, company.id,
        [store.TraitRecordInput("pace", "company", "known", estimate=0.8, confidence=0.5,
                                score_ids=pace_ids)],
        aggregation_version="agg-test",
    )
    (record,) = store.trait_records(db, company.id)
    assert record.id == record_id
    assert (record.evidence_count, record.abstain_count) == (3, 1)
    # The dated range is over the NON-abstaining, dated items only.
    assert (record.first_dated, record.last_dated) == (D(2025, 6, 1), D(2026, 1, 15))

    # Newest first, undated last; abstentions are included, not hidden.
    evidence = store.items_for_record(db, record_id)
    assert [e.paraphrase for e in evidence] == [
        "Three (says nothing on pace)", "One", "Two", "Four, undated",
    ]
    assert [e.score for e in evidence] == [None, 0.8, 0.7, 0.9]
    assert [e.abstained for e in evidence] == [True, False, False, False]
    assert {e.scorer_run_id for e in evidence} == {scorer.id}
    assert all(isinstance(e, store.EvidenceItemView) for e in evidence)

    # An explicit range is honoured as given.
    (explicit_id,) = store.write_trait_records(
        db, company.id,
        [store.TraitRecordInput("pace", "company", "known", estimate=0.8, score_ids=pace_ids,
                                first_dated=D(2024, 1, 1), last_dated=D(2026, 6, 1))],
        aggregation_version="agg-test",
    )
    (record,) = store.trait_records(db, company.id)
    assert record.id == explicit_id and record.first_dated == D(2024, 1, 1)

    with pytest.raises(ValueError, match="does not exist"):
        store.items_for_record(db, 10_000)


def test_views_never_carry_the_internal_excerpt(world):
    """The read side of GAP-14. The guard test pins reachability; this pins the shape."""
    db, company, run, scorer = world
    (item_id,) = store.write_items(
        db, company.id, [_item(excerpt_internal="SECRET VERBATIM")], research_run_id=run.id
    )
    store.write_item_scores(
        db, [store.ItemScoreInput(item_id, "pace", score=0.5)], scorer_run_id=scorer.id
    )
    from model import EvidenceItemScore

    score_id = EvidenceItemScore.query.one().id
    (record_id,) = store.write_trait_records(
        db, company.id,
        [store.TraitRecordInput("pace", "company", "known", estimate=0.5, score_ids=[score_id])],
        aggregation_version="agg-test",
    )
    (view,) = store.items_for_record(db, record_id)
    names = {f.name for f in dataclasses.fields(view)}
    assert "excerpt_internal" not in names
    assert "SECRET VERBATIM" not in repr(view)
    assert "SECRET VERBATIM" not in repr(store.trait_records(db, company.id))


def test_posting_records_are_private_to_the_posting_and_never_shared(world):
    """Orchestrator review 2026-10-13: user A's paste must not become part of what user B
    reads. The shared read excludes posting records; the private read returns only the
    posting's own; the store refuses to link scores across the line in either direction."""
    from model import EvidenceItemScore

    db, company, run, scorer = world
    user_a = _user(db, 1)
    posting = store.create_job_posting(db, user_a, posting_text="We move fast.", company_id=company.id)

    # Shared, research-derived evidence and record.
    (shared_item,) = store.write_items(db, company.id, [_item(paraphrase="Public")], research_run_id=run.id)
    # A's private evidence and record.
    (private_item,) = store.write_items(
        db, company.id,
        [_item(scope="role", scope_label="SWE", source_type="user_pasted_posting", paraphrase="A's paste")],
        job_posting_id=posting.id,
    )
    store.write_item_scores(
        db,
        [store.ItemScoreInput(shared_item, "pace", score=0.4),
         store.ItemScoreInput(private_item, "pace", score=0.9)],
        scorer_run_id=scorer.id,
    )
    shared_score = EvidenceItemScore.query.filter_by(evidence_item_id=shared_item).one().id
    private_score = EvidenceItemScore.query.filter_by(evidence_item_id=private_item).one().id

    # Neither side may link the other's scores.
    with pytest.raises(ValueError, match="private to that user"):
        store.write_trait_records(
            db, company.id,
            [store.TraitRecordInput("pace", "role", "known", estimate=0.9, scope_label="SWE",
                                    score_ids=[private_score])],
            aggregation_version="agg-test",
        )
    with pytest.raises(ValueError, match="cannot link it"):
        store.write_trait_records(
            db, company.id,
            [store.TraitRecordInput("pace", "role", "known", estimate=0.4, scope_label="SWE",
                                    score_ids=[shared_score], job_posting_id=posting.id)],
            aggregation_version="agg-test",
        )
    other_company = _mk_company(db, name="Other", slug="other")
    with pytest.raises(ValueError, match="names company"):
        store.write_trait_records(
            db, other_company.id,
            [store.TraitRecordInput("pace", "role", "unknown", job_posting_id=posting.id)],
            aggregation_version="agg-test",
        )

    (shared_id,) = store.write_trait_records(
        db, company.id,
        [store.TraitRecordInput("pace", "company", "known", estimate=0.4, score_ids=[shared_score])],
        aggregation_version="agg-test",
    )
    (private_v1,) = store.write_trait_records(
        db, company.id,
        [store.TraitRecordInput("pace", "role", "unknown", scope_label="SWE",
                                score_ids=[private_score], job_posting_id=posting.id)],
        aggregation_version="agg-test",
        computed_at=datetime.datetime(2026, 9, 1, tzinfo=UTC),
    )
    (private_v2,) = store.write_trait_records(
        db, company.id,
        [store.TraitRecordInput("pace", "role", "known", estimate=0.9, scope_label="SWE",
                                score_ids=[private_score], job_posting_id=posting.id)],
        aggregation_version="agg-test",
        computed_at=datetime.datetime(2026, 10, 1, tzinfo=UTC),
    )

    # The shared read -- what user B gets -- carries no posting record, at any scope.
    shared = store.trait_records(db, company.id)
    assert [(r.id, r.job_posting_id) for r in shared] == [(shared_id, None)]
    assert store.trait_records(db, company.id, scope="role") == []

    # The private read is the owner's own, latest generation only.
    private = store.posting_trait_records(db, posting.id)
    assert [(r.id, r.job_posting_id, r.status) for r in private] == [(private_v2, posting.id, "known")]
    assert [e.paraphrase for e in store.items_for_record(db, private_v2)] == ["A's paste"]
    assert private_v1 != private_v2
    with pytest.raises(ValueError, match="does not exist"):
        store.posting_trait_records(db, 10_000)

    # Deletion removes every trace of A's paste; the shared record is untouched.
    from model import CompanyTraitRecord, CompanyTraitRecordEvidence

    assert store.delete_job_postings_for_user(db, user_a) == 1
    assert CompanyTraitRecord.query.filter(CompanyTraitRecord.job_posting_id.isnot(None)).count() == 0
    assert db.session.get(CompanyTraitRecord, private_v1) is None
    assert CompanyTraitRecordEvidence.query.filter_by(evidence_item_score_id=private_score).count() == 0
    assert [(r.id, r.evidence_count) for r in store.trait_records(db, company.id)] == [(shared_id, 1)]
    assert [e.paraphrase for e in store.items_for_record(db, shared_id)] == ["Public"]


# ---------------------------------------------------------------------------
# Job postings (user-keyed)
# ---------------------------------------------------------------------------

def _user(db, user_id=1):
    from model import User

    if db.session.get(User, user_id) is None:
        db.session.add(User(id=user_id, email="u%d@example.test" % user_id, password_hash="x"))
        db.session.commit()
    return user_id


def test_job_posting_create_list_and_delete_cascade(world):
    from model import (
        CompanyEvidenceItem,
        CompanyTraitRecord,
        CompanyTraitRecordEvidence,
        EvidenceItemScore,
    )

    db, company, _, scorer = world
    uid = _user(db)
    with pytest.raises(ValueError, match="needs its text"):
        store.create_job_posting(db, uid, posting_text="   ")

    first = store.create_job_posting(db, uid, posting_text="We move fast.", title="  SWE ")
    second = store.create_job_posting(db, uid, posting_text="Calm pace.", company_id=company.id)
    assert first.status == "pending" and first.title == "SWE" and first.company_id is None
    assert isinstance(first, store.JobPostingView)
    assert [p.id for p in store.job_postings_for_user(db, uid)] == [second.id, first.id]
    assert store.set_job_posting_status(db, second.id, "scored").status == "scored"
    with pytest.raises(ValueError, match="one of"):
        store.set_job_posting_status(db, second.id, "done")

    (item_id,) = store.write_items(
        db, company.id,
        [_item(scope="role", scope_label="SWE", source_type="user_pasted_posting")],
        job_posting_id=second.id,
    )
    store.write_item_scores(
        db, [store.ItemScoreInput(item_id, "pace", score=0.3)], scorer_run_id=scorer.id
    )
    score_id = EvidenceItemScore.query.one().id
    (record_id,) = store.write_trait_records(
        db, company.id,
        [store.TraitRecordInput("pace", "role", "unknown", scope_label="SWE",
                                score_ids=[score_id], job_posting_id=second.id)],
        aggregation_version="agg-test",
    )
    (shared_id,) = store.write_trait_records(
        db, company.id, [store.TraitRecordInput("pace", "company", "unknown")],
        aggregation_version="agg-test",
    )

    other = _user(db, 2)
    kept = store.create_job_posting(db, other, posting_text="Someone else's paste.")

    assert store.delete_job_postings_for_user(db, uid) == 2
    assert store.job_postings_for_user(db, uid) == []
    assert CompanyEvidenceItem.query.count() == 0
    assert EvidenceItemScore.query.count() == 0
    assert CompanyTraitRecordEvidence.query.count() == 0
    # Nothing derived from the paste survives: the posting's record is gone with it. The
    # shared record and the other user's paste are untouched.
    assert [r.id for r in store.trait_records(db, company.id)] == [shared_id]
    assert db.session.get(CompanyTraitRecord, record_id) is None
    assert [p.id for p in store.job_postings_for_user(db, other)] == [kept.id]
    assert store.delete_job_postings_for_user(db, uid) == 0


# ---------------------------------------------------------------------------
# Company size -> stage_size
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "headcount, band",
    [(1, 1), (9, 1), (10, 2), (99, 2), (100, 3), (999, 3), (1_000, 4), (9_999, 4),
     (10_000, 5), (250_000, 5)],
)
def test_stage_size_bands_match_the_environment_report(headcount, band):
    assert store.stage_size_for_headcount(headcount) == band


@pytest.mark.parametrize("bad", [0, -5, 2.5, True, "100"])
def test_stage_size_rejects_non_headcounts(bad):
    with pytest.raises(ValueError):
        store.stage_size_for_headcount(bad)


def test_set_company_size_writes_the_confounder_and_upserts(world):
    from model import Company, CompanyConfounderValue

    db, company, _, _ = world
    band = store.set_company_size(
        db, company.id, 450, as_of=D(2026, 10, 1), source="researched", provenance="careers page",
    )
    assert band == 3
    row = db.session.get(Company, company.id)
    assert (row.headcount, row.headcount_as_of, row.headcount_source) == (450, D(2026, 10, 1), "careers page")
    conf = CompanyConfounderValue.query.filter_by(company_id=company.id).one()
    assert (conf.confounder_key, conf.value_num, conf.source, conf.as_of) == ("stage_size", 3.0, "researched", D(2026, 10, 1))

    # Same key: updated in place, not duplicated.
    assert store.set_company_size(db, company.id, 12_000, as_of=D(2026, 10, 1), source="researched") == 5
    conf = CompanyConfounderValue.query.filter_by(company_id=company.id).one()
    assert conf.value_num == 5.0
    assert db.session.get(Company, company.id).headcount_source == "researched"

    # A different date is a new row (the existing table's grain).
    store.set_company_size(db, company.id, 30, as_of=D(2025, 1, 1), source="researched")
    assert CompanyConfounderValue.query.filter_by(company_id=company.id).count() == 2

    with pytest.raises(ValueError, match="one of"):
        store.set_company_size(db, company.id, 30, as_of=D(2025, 1, 1), source="linkedin")
    with pytest.raises(ValueError, match=">= 1"):
        store.set_company_size(db, company.id, 0, as_of=D(2025, 1, 1), source="declared")
    with pytest.raises(ValueError, match="does not exist"):
        store.set_company_size(db, 10_000, 30, as_of=D(2025, 1, 1), source="declared")

    with pytest.raises(IntegrityError):  # the CHECK, bypassing the store
        row = db.session.get(Company, company.id)
        row.headcount = 0
        db.session.commit()
    db.session.rollback()


# ---------------------------------------------------------------------------
# The migration, both directions, against the real database
# ---------------------------------------------------------------------------

def _load_migration(connection):
    spec = importlib.util.spec_from_file_location("_h_company_evidence", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(connection))
    return module


def _catalog(db) -> dict:
    """Everything the migration is responsible for, as the database reports it."""
    tables = sa.text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = ANY(:names)"
    )
    columns = sa.text(
        "SELECT table_name, column_name, data_type, is_nullable, column_default, "
        "character_maximum_length, numeric_precision, numeric_scale "
        "FROM information_schema.columns WHERE table_schema = 'public' "
        "AND (table_name = ANY(:names) OR (table_name = 'company' AND column_name = ANY(:cols))) "
        "ORDER BY table_name, column_name"
    )
    constraints = sa.text(
        "SELECT c.relname, con.conname, con.contype, pg_get_constraintdef(con.oid) "
        "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
        "WHERE c.relname = ANY(:names) OR con.conname = 'ck_company_headcount_positive' "
        "ORDER BY 1, 2"
    )
    indexes = sa.text(
        "SELECT tablename, indexname, indexdef FROM pg_indexes "
        "WHERE tablename = ANY(:names) ORDER BY 1, 2"
    )
    params = {"names": list(NEW_TABLES), "cols": list(COMPANY_COLUMNS)}
    run = lambda stmt: [tuple(r) for r in db.session.execute(stmt, params).fetchall()]  # noqa: E731
    return {
        "tables": sorted(r[0] for r in run(tables)),
        "columns": run(columns),
        "constraints": run(constraints),
        "indexes": run(indexes),
    }


def test_migration_round_trips_and_matches_the_orm(client):
    """downgrade() removes everything; upgrade() rebuilds it IDENTICALLY to create_all().

    The catalog comparison is the ORM-vs-migration parity check: every column type and
    nullability, every CHECK's expression as Postgres normalises it, every unique key,
    foreign key and index. A migration that drifted from model.py by one constraint
    would show up as a differing tuple with the constraint named.
    """
    from app import app
    from model import db

    with app.app_context():
        before = _catalog(db)
        assert before["tables"] == sorted(NEW_TABLES)
        assert {c[1] for c in before["columns"] if c[0] == "company"} == set(COMPANY_COLUMNS)
        assert any(c[1] == "ck_company_headcount_positive" for c in before["constraints"])

        module = _load_migration(db.session.connection())
        module.downgrade()
        after_down = _catalog(db)
        assert after_down["tables"] == []
        assert after_down["columns"] == []
        assert after_down["constraints"] == []
        assert after_down["indexes"] == []

        module.upgrade()
        after_up = _catalog(db)
        assert after_up == before

        # Transactional DDL: the fixture's schema is exactly as it was.
        db.session.rollback()
        assert _catalog(db) == before


def test_migration_is_the_next_link_after_the_trait_prefs_stub():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20261013_company_evidence"' in source
    assert 'down_revision = "20261013_trait_prefs"' in source


# ---------------------------------------------------------------------------
# One current job per user (links)
# ---------------------------------------------------------------------------

def test_second_link_closes_the_first(world):
    db, company, _, _ = world
    uid = _user(db)
    first = store.create_company_link(
        db, uid, company_id=company.id, started_on=datetime.date(2026, 1, 5))
    second = store.create_company_link(
        db, uid, company_id=company.id, started_on=datetime.date(2026, 6, 1))
    by_id = {l.id: l for l in store.company_links_for_user(db, uid)}
    assert by_id[first.id].ended_on == datetime.date(2026, 6, 1)
    assert by_id[second.id].ended_on is None


def test_backdated_second_link_does_not_violate_the_check(world):
    db, company, _, _ = world
    uid = _user(db)
    first = store.create_company_link(
        db, uid, company_id=company.id, started_on=datetime.date(2026, 6, 1))
    store.create_company_link(
        db, uid, company_id=company.id, started_on=datetime.date(2026, 1, 1))
    by_id = {l.id: l for l in store.company_links_for_user(db, uid)}
    # closed on its own start: a zero-length stint, never ended before it began
    assert by_id[first.id].ended_on == datetime.date(2026, 6, 1)


def test_db_refuses_two_open_links_for_one_user(world):
    import sqlalchemy.exc
    from model import UserCompanyLink

    db, company, _, _ = world
    uid = _user(db)
    for day in (1, 2):
        db.session.add(UserCompanyLink(
            user_id=uid, company_id=company.id, started_on=datetime.date(2026, 1, day)))
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_end_company_link_owner_only_and_date_rule(world):
    db, company, _, _ = world
    uid = _user(db)
    other = _user(db, 2)
    link = store.create_company_link(
        db, uid, company_id=company.id, started_on=datetime.date(2026, 3, 1))
    assert store.end_company_link(db, other, link.id, ended_on=datetime.date(2026, 4, 1)) is None
    with pytest.raises(ValueError):
        store.end_company_link(db, uid, link.id, ended_on=datetime.date(2026, 2, 1))
    done = store.end_company_link(db, uid, link.id, ended_on=datetime.date(2026, 4, 1))
    assert done.ended_on == datetime.date(2026, 4, 1)
