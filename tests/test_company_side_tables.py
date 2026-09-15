"""Constraint-level tests for the S-07 tables (company side, match/funnel, model runs).

These tables have no application code path yet -- the match model is not productionized --
so what is testable today is the data contract itself: the vocabularies, ranges, and
uniqueness rules that schema.sql expressed as Postgres enums and constraints. Because the
enums were translated to String + CHECK, the SQLite test database enforces the same
vocabulary rules production Postgres will, and these tests exercise them for real rather
than trusting the translation.

That was only ever half true, and the missing half cost four tests here.  SQLite honours
the CHECK constraints but ships with *foreign keys* off, so every ``user_id=1`` below was
an orphan pointing at a `user` row that had never been created.  The vocabulary
assertions passed while the rows they asserted about could not exist in production.
Moving CI to Postgres (2026-08-27) surfaced all four at once; ``seed_user`` supplies the
parent row, and conftest now turns the SQLite pragma on so the two databases agree.

Every expected-failure test writes a sibling VALID row first (or after), so a test cannot
pass because the table is broken for all inserts -- the S-40 lesson: a check whose fixture
makes the failure invisible is not a check.
"""

import datetime

import pytest
from sqlalchemy.exc import IntegrityError


AS_OF = datetime.date(2026, 8, 19)


def _mk_company(db, name="Acme", slug="acme", domain=None):
    from model import Company

    company = Company(name=name, slug=slug, domain=domain, profile_json={})
    db.session.add(company)
    db.session.flush()
    return company


def _mk_score(db, company, dimension_key="autonomy", source="researched", as_of=AS_OF, **kw):
    from model import CompanyDimensionScore

    row = CompanyDimensionScore(
        company_id=company.id,
        dimension_key=dimension_key,
        score=kw.pop("score", 0.7),
        source=source,
        confidence=kw.pop("confidence", 0.3),
        as_of=as_of,
        **kw,
    )
    db.session.add(row)
    return row


def _mk_run(db):
    from model import ModelRun

    run = ModelRun(
        model_version="cbm-test", dimension_set_version="6d-v2", priors_version="p1"
    )
    db.session.add(run)
    db.session.flush()
    return run


def test_full_graph_inserts(client, seed_user):
    """Happy path: one row in every new table, linked the way the match pipeline will
    link them. If this fails, nothing else in this file means anything."""
    from app import app
    from model import (
        db,
        MatchRecommendation,
        OutcomeAppeal,
        OutcomeExperienced,
        RecAction,
        WeightPosterior,
    )

    seed_user(1)  # match_recommendation.user_id / outcome_experienced.user_id are FKs

    with app.app_context():
        company = _mk_company(db, domain="acme.example")
        _mk_score(db, company)

        from model import CompanyConfounderValue

        db.session.add(
            CompanyConfounderValue(
                company_id=company.id,
                confounder_key="stage_size",
                value_num=3.0,
                source="researched",
                as_of=AS_OF,
            )
        )

        run = _mk_run(db)
        db.session.add(
            WeightPosterior(model_run_id=run.id, weight_name="pace_mag", mean=0.4, sd=0.1)
        )

        rec = MatchRecommendation(
            user_id=1, company_id=company.id, model_run_id=run.id, p_fit=0.62, rank=1
        )
        db.session.add(rec)
        db.session.flush()

        db.session.add(RecAction(recommendation=rec, action="viewed"))
        db.session.add(
            OutcomeAppeal(recommendation=rec, fit_yes=True, channel="onsite")
        )
        db.session.add(
            OutcomeExperienced(
                user_id=1, company_id=company.id, recommendation=rec, working_scale=4
            )
        )
        db.session.commit()

        assert rec.is_exploration is False  # server/default, not accidentally NULL
        assert rec.channel == "onsite"


def test_company_domain_unique_but_nullable(client):
    """Two companies may both lack a domain (all existing rows will); two companies may
    never share one -- domain is the dedupe key."""
    from app import app
    from model import db

    with app.app_context():
        _mk_company(db, name="A", slug="a", domain=None)
        _mk_company(db, name="B", slug="b", domain=None)
        _mk_company(db, name="C", slug="c", domain="c.example")
        db.session.commit()

        with pytest.raises(IntegrityError):
            _mk_company(db, name="D", slug="d", domain="c.example")
            db.session.commit()
        db.session.rollback()


def test_company_score_grain_is_dim_source_asof(client):
    """One score per (company, dimension, source, as_of). A re-score on a new date inserts;
    the same cell twice is refused -- overwriting history is what the grain exists to stop."""
    from app import app
    from model import db

    with app.app_context():
        company = _mk_company(db)
        _mk_score(db, company)
        # Same dimension, later date: allowed (culture goes stale; re-scoring is an INSERT).
        _mk_score(db, company, as_of=datetime.date(2026, 9, 1))
        # Same dimension, same source, different SOURCE value: allowed (scraped vs declared).
        _mk_score(db, company, source="declared", confidence=1.0)
        db.session.commit()

        with pytest.raises(IntegrityError):
            _mk_score(db, company)  # identical cell
            db.session.commit()
        db.session.rollback()


def test_company_score_vocab_and_ranges_enforced(client):
    """The Postgres enums became CHECK constraints; prove the database (not just the
    loader) refuses a bad source, an out-of-range score, and an out-of-range confidence."""
    from app import app
    from model import db

    with app.app_context():
        company = _mk_company(db)
        _mk_score(db, company)  # sibling valid row: the table accepts good inserts
        db.session.commit()

        with pytest.raises(IntegrityError):
            _mk_score(db, company, dimension_key="pace", source="guessed")
            db.session.commit()
        db.session.rollback()

        with pytest.raises(IntegrityError):
            _mk_score(db, company, dimension_key="pace", score=1.2)
            db.session.commit()
        db.session.rollback()

        with pytest.raises(IntegrityError):
            _mk_score(db, company, dimension_key="pace", confidence=-0.1)
            db.session.commit()
        db.session.rollback()


def test_confounder_value_must_have_num_or_cat(client):
    """A confounder row with neither value is a row that says nothing; the CHECK refuses it."""
    from app import app
    from model import db, CompanyConfounderValue

    with app.app_context():
        company = _mk_company(db)
        db.session.add(
            CompanyConfounderValue(
                company_id=company.id,
                confounder_key="industry",
                value_cat="tech",
                source="researched",
                as_of=AS_OF,
            )
        )
        db.session.commit()

        with pytest.raises(IntegrityError):
            db.session.add(
                CompanyConfounderValue(
                    company_id=company.id,
                    confounder_key="comp",
                    value_num=None,
                    value_cat=None,
                    source="researched",
                    as_of=AS_OF,
                )
            )
            db.session.commit()
        db.session.rollback()


def test_weight_posterior_one_row_per_weight_per_run(client):
    from app import app
    from model import db, WeightPosterior

    with app.app_context():
        run = _mk_run(db)
        db.session.add(
            WeightPosterior(model_run_id=run.id, weight_name="intercept", mean=0.0, sd=1.0)
        )
        db.session.commit()

        with pytest.raises(IntegrityError):
            db.session.add(
                WeightPosterior(
                    model_run_id=run.id, weight_name="intercept", mean=0.1, sd=0.9
                )
            )
            db.session.commit()
        db.session.rollback()


def test_funnel_action_vocab_enforced(client, seed_user):
    from app import app
    from model import db, MatchRecommendation, RecAction

    seed_user(1)

    with app.app_context():
        company = _mk_company(db)
        rec = MatchRecommendation(user_id=1, company_id=company.id)
        db.session.add(rec)
        db.session.flush()
        db.session.add(RecAction(recommendation=rec, action="applied"))
        db.session.commit()

        with pytest.raises(IntegrityError):
            db.session.add(RecAction(recommendation=rec, action="ghosted"))
            db.session.commit()
        db.session.rollback()


def test_outcome_appeal_is_one_per_recommendation(client, seed_user):
    """Appeal is a one-shot answer about a shown match; a second answer for the same
    recommendation must be refused, not averaged in later."""
    from app import app
    from model import db, MatchRecommendation, OutcomeAppeal

    seed_user(1)

    with app.app_context():
        company = _mk_company(db)
        rec = MatchRecommendation(user_id=1, company_id=company.id)
        db.session.add(rec)
        db.session.flush()
        db.session.add(
            OutcomeAppeal(recommendation=rec, fit_yes=False, channel="email")
        )
        db.session.commit()

        with pytest.raises(IntegrityError):
            db.session.add(
                OutcomeAppeal(recommendation=rec, fit_yes=True, channel="onsite")
            )
            db.session.commit()
        db.session.rollback()


def test_working_scale_is_ordinal_1_to_5(client, seed_user):
    """The experienced-fit label the model eventually trains on (OrderedLogistic -- S-06).
    0 and 6 are refused at the database, not just in whatever form collects it someday."""
    from app import app
    from model import db, OutcomeExperienced

    seed_user(1)

    with app.app_context():
        company = _mk_company(db)
        db.session.add(
            OutcomeExperienced(user_id=1, company_id=company.id, working_scale=1)
        )
        db.session.add(
            OutcomeExperienced(user_id=1, company_id=company.id, working_scale=5)
        )
        db.session.commit()

        for bad in (0, 6):
            with pytest.raises(IntegrityError):
                db.session.add(
                    OutcomeExperienced(user_id=1, company_id=company.id, working_scale=bad)
                )
                db.session.commit()
            db.session.rollback()


# ---------------------------------------------------------------------------
# scorer_run, the five-column key, and citations (S1-6)
# ---------------------------------------------------------------------------
# `uq_cscore_company_dim_source_asof` gained scorer_run_id so one company can be scored
# twice on one day under two rubrics. That column is NULLABLE, and a nullable column in a
# plain UNIQUE constraint would silently STOP de-duplicating the rows that have no scorer
# run -- Postgres treats NULLs as distinct. The constraint is therefore NULLS NOT DISTINCT,
# and the two halves are tested separately below because only one of them is obvious:
# everyone checks that two runs now coexist; nobody checks that two human rows still don't.
#
# The file's discipline applies as everywhere else here -- every expected-failure test
# writes a sibling VALID row, so none of these can pass because the table stopped accepting
# inserts altogether.


def _mk_scorer_run(db, rubric_version="v1-frozen-2026-08-15", **kw):
    from model import ScorerRun

    run = ScorerRun(
        model=kw.pop("model", "gpt-5.5-2026-04-23"),
        temperature=kw.pop("temperature", 1.0),
        temperature_honored=kw.pop("temperature_honored", True),
        reasoning_effort=kw.pop("reasoning_effort", "medium"),
        rubric_version=rubric_version,
        packet_version=kw.pop("packet_version", "v4.6"),
        **kw,
    )
    db.session.add(run)
    db.session.flush()
    return run


def test_two_rubrics_on_one_company_on_one_day_both_insert(client):
    """The whole point of the column. Before it, re-scoring a company under a reworded
    rubric on the same day failed outright, so the two scores could never be compared --
    which is what made anchor wording read as a blocker on everything downstream."""
    from app import app
    from model import db

    with app.app_context():
        company = _mk_company(db)
        v1 = _mk_scorer_run(db, rubric_version="v1-frozen-2026-08-15")
        v3 = _mk_scorer_run(db, rubric_version="v3-anchors-2026-09-01")

        _mk_score(db, company, source="scraped", scorer_run_id=v1.id, score=0.3)
        _mk_score(db, company, source="scraped", scorer_run_id=v3.id, score=0.7)
        db.session.commit()

        from model import CompanyDimensionScore

        rows = CompanyDimensionScore.query.filter_by(
            company_id=company.id, dimension_key="autonomy", source="scraped", as_of=AS_OF
        ).all()
        assert len(rows) == 2, "two scorer runs must coexist in one (company, dim, day) cell"
        assert {r.score for r in rows} == {0.3, 0.7}
        assert {r.scorer_run_id for r in rows} == {v1.id, v3.id}


def test_same_scorer_run_twice_in_one_cell_is_refused(client):
    """Adding scorer_run_id must not turn the cell into a free-for-all: one run may still
    write a given (company, dimension, day) only once. Overwriting history is what the
    grain exists to stop, and a re-run of the SAME run is a duplicate, not new evidence."""
    from app import app
    from model import db

    with app.app_context():
        company = _mk_company(db)
        run = _mk_scorer_run(db)
        _mk_score(db, company, source="scraped", scorer_run_id=run.id)
        # Sibling valid row: a DIFFERENT dimension under the same run still inserts, so a
        # pass below cannot come from the table having stopped accepting scraped rows.
        _mk_score(db, company, dimension_key="pace", source="scraped", scorer_run_id=run.id)
        db.session.commit()

        with pytest.raises(IntegrityError):
            _mk_score(db, company, source="scraped", scorer_run_id=run.id, score=0.9)
            db.session.commit()
        db.session.rollback()


def test_null_scorer_run_rows_still_deduplicate(client):
    """The NULLS NOT DISTINCT half, and the one most likely to be quietly wrong.

    'researched' (human) and 'declared' rows carry no scorer_run_id. Under a PLAIN unique
    constraint over the same five columns this test would FAIL -- Postgres treats NULLs as
    distinct, so both rows would insert and a guarantee that exists today would have been
    removed in passing by a migration whose stated purpose was to ADD one. The constraint
    is declared NULLS NOT DISTINCT precisely so this still raises.
    """
    from app import app
    from model import db

    with app.app_context():
        company = _mk_company(db)
        # Sibling valid rows: NULL-scorer_run rows do still insert, and still separate on
        # `source`. Only the exact duplicate below may be refused.
        _mk_score(db, company, source="researched")
        _mk_score(db, company, source="declared", confidence=1.0)
        db.session.commit()

        with pytest.raises(IntegrityError):
            _mk_score(db, company, source="researched", score=0.9)
            db.session.commit()
        db.session.rollback()

        from model import CompanyDimensionScore

        # The two sibling rows survived; only the duplicate was refused.
        assert CompanyDimensionScore.query.filter_by(company_id=company.id).count() == 2


def test_unmatched_citation_is_kept_without_provenance(client):
    """A quote the verifier could not find in the packet is STORED, with no excerpt id and
    no source tag. It is not an error and it is not discarded: an unverifiable quote is
    exactly the failure this table exists to make visible, and dropping it would leave the
    score looking better evidenced than it is. Having no provenance to report is why both
    provenance columns are null rather than guessed."""
    from app import app
    from model import db, DimensionScoreCitation

    with app.app_context():
        company = _mk_company(db)
        run = _mk_scorer_run(db)
        score = _mk_score(db, company, source="scraped", scorer_run_id=run.id)
        db.session.flush()

        db.session.add(
            DimensionScoreCitation(
                company_dimension_score_id=score.id,
                quote_text="a phrase the model produced that is nowhere in the packet",
                matched=False,
            )
        )
        # Sibling valid row: a MATCHED citation with full provenance.
        db.session.add(
            DimensionScoreCitation(
                company_dimension_score_id=score.id,
                quote_text="Heavy micromanagement.",
                matched=True,
                matched_excerpt_id="B13",
                source_tag="noncompany",
            )
        )
        db.session.commit()

        rows = DimensionScoreCitation.query.filter_by(
            company_dimension_score_id=score.id
        ).order_by(DimensionScoreCitation.matched).all()
        assert len(rows) == 2, "the unmatched quote must be retained, not rejected"
        unmatched = rows[0]
        assert unmatched.matched is False
        assert unmatched.matched_excerpt_id is None
        assert unmatched.source_tag is None


def test_citation_provenance_is_all_or_nothing(client):
    """`matched` and the two provenance columns move together. A source_tag on a quote that
    was never found would be a provenance claim about nothing -- the model's self-report
    smuggled back in after the verifier was built specifically to replace it."""
    from app import app
    from model import db, DimensionScoreCitation

    with app.app_context():
        company = _mk_company(db)
        run = _mk_scorer_run(db)
        score = _mk_score(db, company, source="scraped", scorer_run_id=run.id)
        db.session.flush()
        db.session.add(
            DimensionScoreCitation(
                company_dimension_score_id=score.id, quote_text="verified quote",
                matched=True, matched_excerpt_id="A1", source_tag="company",
            )
        )
        db.session.commit()

        # unmatched but carrying provenance
        with pytest.raises(IntegrityError):
            db.session.add(
                DimensionScoreCitation(
                    company_dimension_score_id=score.id, quote_text="q",
                    matched=False, matched_excerpt_id="A2", source_tag="company",
                )
            )
            db.session.commit()
        db.session.rollback()

        # matched but missing it
        with pytest.raises(IntegrityError):
            db.session.add(
                DimensionScoreCitation(
                    company_dimension_score_id=score.id, quote_text="q2", matched=True
                )
            )
            db.session.commit()
        db.session.rollback()


# ---------------------------------------------------------------------------
# company_score_store -- the doorway
# ---------------------------------------------------------------------------

#: One packet's worth of extractor output, in the plain-dict shape the store takes.
_INGEST_DIMENSIONS = [
    {
        "dimension_key": "autonomy",
        "score": 0.3,
        "confidence": 0.6,
        "citations": [
            {
                "quote_text": "Heavy micromanagement.",
                "matched": True,
                "matched_excerpt_id": "B13",
                "source_tag": "noncompany",
            },
            {"quote_text": "invented phrase", "matched": False},
        ],
    },
    {
        "dimension_key": "pace",
        "score": 0.7,
        "confidence": 0.9,
        "citations": [
            {
                "quote_text": "We had to move fast",
                "matched": True,
                "matched_excerpt_id": "D2",
                "source_tag": "disputed",
            }
        ],
    },
]

_INGEST_RUN = {
    "model": "gpt-5.5-2026-04-23",
    "temperature": 1.0,
    "temperature_honored": True,
    "reasoning_effort": "medium",
    "rubric_version": "v1-frozen-2026-08-15",
    "packet_version": "v4.6",
    "run_at": datetime.datetime(2026, 9, 1, 12, 0, tzinfo=datetime.timezone.utc),
    "notes": "test ingest",
}


def _counts(db):
    from model import CompanyDimensionScore, DimensionScoreCitation, ScorerRun

    return (
        ScorerRun.query.count(),
        CompanyDimensionScore.query.count(),
        DimensionScoreCitation.query.count(),
    )


def test_ingest_writes_run_scores_and_citations_together(client):
    from app import app
    from model import db
    import company_score_store

    with app.app_context():
        company = _mk_company(db)
        db.session.commit()

        summary = company_score_store.ingest_extractor_result(
            company_id=company.id,
            as_of=datetime.date(2026, 9, 1),
            run=_INGEST_RUN,
            dimensions=_INGEST_DIMENSIONS,
            is_ground_truth=True,
        )
        assert summary["scorer_run_created"] is True
        assert summary["scores_created"] == 2
        assert _counts(db) == (1, 2, 3)

        scores = company_score_store.get_company_scores(
            company.id, "v1-frozen-2026-08-15"
        )
        assert {s["dimension_key"] for s in scores} == {"autonomy", "pace"}
        assert all(s["is_ground_truth"] for s in scores)

        citations = company_score_store.get_score_citations(s["id"] for s in scores)
        autonomy = next(s for s in scores if s["dimension_key"] == "autonomy")
        assert len(citations[autonomy["id"]]) == 2, "the unmatched quote is returned too"

        # The PROPOSED DDL's closing measurement, over stored rows.
        support = company_score_store.noncompany_support(company.id)
        assert support[autonomy["id"]] is True   # B13 is noncompany and matched
        pace = next(s for s in scores if s["dimension_key"] == "pace")
        assert support[pace["id"]] is False      # 'disputed' is not non-company support


def test_ingest_is_idempotent(client):
    """Re-ingesting one run must leave row counts untouched. Without this a re-run of a
    backfill silently doubles the evidence behind every score, and the noncompany-support
    measurement above starts reading a duplicated citation as corroboration."""
    from app import app
    from model import db
    import company_score_store

    with app.app_context():
        company = _mk_company(db)
        db.session.commit()
        kwargs = dict(
            company_id=company.id,
            as_of=datetime.date(2026, 9, 1),
            run=_INGEST_RUN,
            dimensions=_INGEST_DIMENSIONS,
        )

        company_score_store.ingest_extractor_result(**kwargs)
        first = _counts(db)

        second_summary = company_score_store.ingest_extractor_result(**kwargs)
        assert _counts(db) == first, "re-ingesting the same run duplicated rows"
        assert second_summary["scorer_run_created"] is False
        assert second_summary["scores_created"] == 0
        assert second_summary["scores_updated"] == 2
        # Citations already matched, so nothing was rewritten and their ids are stable.
        assert second_summary["citations_written"] == 0


def test_ingest_under_two_rubrics_keeps_both(client):
    """The deliverable, at the doorway rather than at the constraint: one company, one
    dimension, one day, two rubric versions, both readable."""
    from app import app
    from model import db
    import company_score_store

    with app.app_context():
        company = _mk_company(db)
        db.session.commit()
        as_of = datetime.date(2026, 9, 1)

        company_score_store.ingest_extractor_result(
            company_id=company.id, as_of=as_of, run=_INGEST_RUN,
            dimensions=_INGEST_DIMENSIONS,
        )
        v3_run = dict(_INGEST_RUN, rubric_version="v3-anchors-2026-09-01", notes="v3")
        v3_dims = [dict(d, score=0.9) for d in _INGEST_DIMENSIONS]
        company_score_store.ingest_extractor_result(
            company_id=company.id, as_of=as_of, run=v3_run, dimensions=v3_dims,
        )

        v1_scores = company_score_store.get_company_scores(company.id, "v1-frozen-2026-08-15")
        v3_scores = company_score_store.get_company_scores(company.id, "v3-anchors-2026-09-01")
        assert len(v1_scores) == 2 and len(v3_scores) == 2
        v1_autonomy = next(s for s in v1_scores if s["dimension_key"] == "autonomy")
        v3_autonomy = next(s for s in v3_scores if s["dimension_key"] == "autonomy")
        assert v1_autonomy["score"] == 0.3 and v3_autonomy["score"] == 0.9
        assert v1_autonomy["as_of"] == v3_autonomy["as_of"] == as_of


def test_ingest_refuses_a_run_without_a_rubric_version(client):
    """rubric_version is never inferred or defaulted. A mislabelled rubric poisons the one
    comparison these rows exist to support, and a silently-defaulted one is mislabelled."""
    from app import app
    from model import db
    import company_score_store

    with app.app_context():
        company = _mk_company(db)
        db.session.commit()
        bad = {k: v for k, v in _INGEST_RUN.items() if k != "rubric_version"}

        with pytest.raises(ValueError, match="rubric_version"):
            company_score_store.ingest_extractor_result(
                company_id=company.id, as_of=datetime.date(2026, 9, 1),
                run=bad, dimensions=_INGEST_DIMENSIONS,
            )
        # Sibling valid call: the same payload WITH a rubric_version goes in fine, so the
        # refusal above is about the missing field and not about the store being broken.
        company_score_store.ingest_extractor_result(
            company_id=company.id, as_of=datetime.date(2026, 9, 1),
            run=_INGEST_RUN, dimensions=_INGEST_DIMENSIONS,
        )
        assert _counts(db) == (1, 2, 3)
