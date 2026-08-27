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

        db.session.add(RecAction(recommendation_id=rec.id, action="viewed"))
        db.session.add(
            OutcomeAppeal(recommendation_id=rec.id, fit_yes=True, channel="onsite")
        )
        db.session.add(
            OutcomeExperienced(
                user_id=1, company_id=company.id, recommendation_id=rec.id, working_scale=4
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
        db.session.add(RecAction(recommendation_id=rec.id, action="applied"))
        db.session.commit()

        with pytest.raises(IntegrityError):
            db.session.add(RecAction(recommendation_id=rec.id, action="ghosted"))
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
            OutcomeAppeal(recommendation_id=rec.id, fit_yes=False, channel="email")
        )
        db.session.commit()

        with pytest.raises(IntegrityError):
            db.session.add(
                OutcomeAppeal(recommendation_id=rec.id, fit_yes=True, channel="onsite")
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
