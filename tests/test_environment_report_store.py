"""Tests for environment_report_store.py + the environment_reports / environment_dimension_score
tables (BUILD_PLAN A-2).

A-1 (the item-bank instrument) and A-3 (rules scoring) do not exist yet, so these tests
exercise storage on its own contract: a caller hands write_environment_report raw_answers
(opaque JSONB) and a complete dimension_scores dict, and storage persists it, unmodified,
append-only.
"""

import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from model import ENV_DIMENSIONS

FULL_SCORES = {k: 0.5 for k in ENV_DIMENSIONS}


def _write(db, user_id=1, **overrides):
    from environment_report_store import write_environment_report

    kwargs = dict(
        raw_answers={"env-q1": "a", "env-q2": "b"},
        dimension_scores=FULL_SCORES,
        stage_size=3,
        comp=3,
        experienced_outcome=4,
        career_status="employed",
        version="v1",
    )
    kwargs.update(overrides)
    return write_environment_report(db, user_id, **kwargs)


# ---------------------------------------------------------------------------
# Happy path + append-only semantics
# ---------------------------------------------------------------------------


def test_write_then_read_round_trips(client, seed_user):
    from app import app
    from environment_report_store import latest_environment_report
    from model import db

    seed_user(1)
    with app.app_context():
        report_id = _write(db, user_id=1, employer_name_normalized="acme corp")
        db.session.commit()

        result = latest_environment_report(1)
        assert result["id"] == report_id
        assert result["user_id"] == 1
        assert result["raw_answers"] == {"env-q1": "a", "env-q2": "b"}
        assert result["dimension_scores"] == FULL_SCORES
        assert result["stage_size"] == 3
        assert result["comp"] == 3
        assert result["experienced_outcome"] == 4
        assert result["career_status"] == "employed"
        assert result["employer_name_normalized"] == "acme corp"
        assert result["version"] == "v1"
        assert result["submitted_at"] is not None


def test_write_accepts_comp_none_for_not_sure(client, seed_user):
    """PRODUCT_DECISIONS.md §2, "Environment-instrument rulings" (2026-09-10):
    the environment instrument's "not sure" option answers `comp` with `None`
    rather than a guessed posture, and storage must not force one."""
    from app import app
    from environment_report_store import latest_environment_report
    from model import db

    seed_user(1)
    with app.app_context():
        report_id = _write(db, user_id=1, comp=None)
        db.session.commit()

        result = latest_environment_report(1)
        assert result["id"] == report_id
        assert result["comp"] is None


# ---------------------------------------------------------------------------
# industry (PRODUCT_DECISIONS.md §2, 2026-10-01)
# ---------------------------------------------------------------------------


def test_industry_round_trips_through_latest_and_history(client, seed_user):
    from app import app
    from environment_report_store import environment_report_history, latest_environment_report
    from model import db

    seed_user(1)
    with app.app_context():
        _write(db, user_id=1, industry="healthcare")
        db.session.commit()

        assert latest_environment_report(1)["industry"] == "healthcare"
        assert latest_environment_report(1, include_raw_answers=False)["industry"] == "healthcare"
        assert environment_report_history(1)[0]["industry"] == "healthcare"


def test_industry_defaults_to_null_and_serializes_as_none(client, seed_user):
    """An omitted industry (every caller written before 2026-10-01) is NULL,
    the instrument's "not sure / prefer not to say" -- and the key is still
    present on the read, never silently absent."""
    from app import app
    from environment_report_store import latest_environment_report
    from model import db

    seed_user(1)
    with app.app_context():
        _write(db, user_id=1)
        db.session.commit()

        result = latest_environment_report(1)
        assert "industry" in result
        assert result["industry"] is None


@pytest.mark.parametrize("bad_industry", ["crypto", "Tech", ""])
def test_industry_outside_the_level_vocabulary_is_rejected(client, seed_user, bad_industry):
    """ck_envreport_industry_vocab: the model indexes a per-level weight, so a key
    outside the config's levels would have no weight to use."""
    from app import app
    from model import EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            EnvironmentReport(
                user_id=1,
                raw_answers={},
                stage_size=3,
                comp=3,
                industry=bad_industry,
                experienced_outcome=3,
                career_status="employed",
                version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


@pytest.mark.parametrize("industry", [None, "tech", "finance", "healthcare", "retail", "other"])
def test_industry_check_accepts_every_level_and_null(client, seed_user, industry):
    """Sibling VALID-row test (S-40 lesson) for the CHECK above."""
    from app import app
    from model import EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            EnvironmentReport(
                user_id=1,
                raw_answers={},
                stage_size=3,
                comp=3,
                industry=industry,
                experienced_outcome=3,
                career_status="employed",
                version="v1",
            )
        )
        db.session.commit()
        assert EnvironmentReport.query.filter_by(user_id=1).one().industry == industry


def test_industry_levels_agree_across_instrument_orm_wire_and_model_config():
    """Four restatements of one vocabulary: the model config (the authority),
    the instrument, the ORM CHECK and the request/response schema's Literal."""
    from pathlib import Path
    from typing import get_args

    import yaml

    from model import ENV_INDUSTRIES
    from solverah.schemas.situation_report import Industry
    from work_pulse.situation_items import INDUSTRY_LEVELS

    config = Path(__file__).resolve().parents[1] / "causal_graph" / "v1_model" / "solverah_model_config.yaml"
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    levels = tuple(next(c for c in cfg["confounders"] if c["key"] == "industry")["levels"])

    assert INDUSTRY_LEVELS == levels
    assert ENV_INDUSTRIES == levels
    assert get_args(Industry) == levels


def test_second_submission_is_a_second_row_not_an_update(client, seed_user):
    """The append-only precedent (D-16): a resubmission never overwrites the first."""
    from app import app
    from environment_report_store import environment_report_history
    from model import EnvironmentDimensionScore, EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        first_id = _write(db, user_id=1, stage_size=2)
        db.session.commit()

        second_scores = {k: 0.9 for k in ENV_DIMENSIONS}
        second_id = _write(db, user_id=1, stage_size=5, dimension_scores=second_scores)
        db.session.commit()

        assert first_id != second_id
        assert EnvironmentReport.query.filter_by(user_id=1).count() == 2
        assert (
            EnvironmentDimensionScore.query.filter_by(user_id=1).count()
            == 2 * len(ENV_DIMENSIONS)
        )

        # The first row's own stage_size and scores are untouched by the second write.
        first_row = db.session.get(EnvironmentReport, first_id)
        assert first_row.stage_size == 2

        history = environment_report_history(1)
        assert [h["id"] for h in history] == [second_id, first_id]  # newest first
        assert history[0]["dimension_scores"] == second_scores


def test_latest_environment_report_is_none_when_user_has_no_reports(client, seed_user):
    from app import app
    from environment_report_store import latest_environment_report

    seed_user(1)
    with app.app_context():
        assert latest_environment_report(1) is None


def test_environment_report_history_is_empty_list_not_none(client, seed_user):
    from app import app
    from environment_report_store import environment_report_history

    seed_user(1)
    with app.app_context():
        assert environment_report_history(1) == []


def test_environment_report_history_limit(client, seed_user):
    from app import app
    from environment_report_store import environment_report_history
    from model import db

    seed_user(1)
    with app.app_context():
        for i in range(3):
            _write(db, user_id=1, version="v%d" % i)
            db.session.commit()

        assert len(environment_report_history(1)) == 3
        limited = environment_report_history(1, limit=1)
        assert len(limited) == 1
        assert limited[0]["version"] == "v2"  # newest


def test_history_and_latest_are_scoped_per_user(client, seed_user):
    from app import app
    from environment_report_store import environment_report_history, latest_environment_report
    from model import db

    seed_user(1, 2)
    with app.app_context():
        _write(db, user_id=1)
        db.session.commit()

        assert latest_environment_report(2) is None
        assert environment_report_history(2) == []
        assert len(environment_report_history(1)) == 1


# ---------------------------------------------------------------------------
# write_environment_report's own validation (A-3's contract)
# ---------------------------------------------------------------------------


def test_write_rejects_a_partial_dimension_set(client, seed_user):
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        incomplete = {k: 0.5 for k in ENV_DIMENSIONS if k != "pace"}
        with pytest.raises(ValueError, match="missing"):
            _write(db, user_id=1, dimension_scores=incomplete)


def test_write_rejects_an_unknown_dimension_key(client, seed_user):
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        extra = dict(FULL_SCORES, made_up_dim=0.5)
        with pytest.raises(ValueError, match="extra"):
            _write(db, user_id=1, dimension_scores=extra)


def test_write_rejects_a_score_outside_zero_one(client, seed_user):
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        bad = dict(FULL_SCORES, pace=1.5)
        with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
            _write(db, user_id=1, dimension_scores=bad)


# ---------------------------------------------------------------------------
# Model-level constraints (CHECK constraints hold even if a future caller bypasses
# environment_report_store and writes the ORM rows directly)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_stage_size", [0, 6, -1])
def test_stage_size_out_of_range_is_rejected(client, seed_user, bad_stage_size):
    from app import app
    from model import EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            EnvironmentReport(
                user_id=1,
                raw_answers={},
                stage_size=bad_stage_size,
                comp=3,
                experienced_outcome=3,
                career_status="employed",
                version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


@pytest.mark.parametrize("bad_comp", [0, 6])
def test_comp_out_of_range_is_rejected(client, seed_user, bad_comp):
    from app import app
    from model import EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            EnvironmentReport(
                user_id=1,
                raw_answers={},
                stage_size=3,
                comp=bad_comp,
                experienced_outcome=3,
                career_status="employed",
                version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_comp_null_is_accepted_by_the_check_constraint(client, seed_user):
    """Sibling VALID-row test (S-40 lesson) for the nullable `comp` CHECK:
    NULL must pass alongside the in-range values `test_comp_out_of_range_is_rejected`
    already guards, not just skip the constraint by accident."""
    from app import app
    from model import EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            EnvironmentReport(
                user_id=1,
                raw_answers={},
                stage_size=3,
                comp=None,
                experienced_outcome=3,
                career_status="employed",
                version="v1",
            )
        )
        db.session.commit()
        assert EnvironmentReport.query.filter_by(user_id=1).one().comp is None


@pytest.mark.parametrize("bad_outcome", [0, 6])
def test_experienced_outcome_out_of_range_is_rejected(client, seed_user, bad_outcome):
    from app import app
    from model import EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            EnvironmentReport(
                user_id=1,
                raw_answers={},
                stage_size=3,
                comp=3,
                experienced_outcome=bad_outcome,
                career_status="employed",
                version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_career_status_outside_the_vocabulary_is_rejected(client, seed_user):
    from app import app
    from model import EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            EnvironmentReport(
                user_id=1,
                raw_answers={},
                stage_size=3,
                comp=3,
                experienced_outcome=3,
                career_status="retired",
                version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_a_valid_row_of_every_career_status_is_accepted(client, seed_user):
    """Sibling VALID-row test (S-40 lesson): proves the vocabulary CHECK isn't rejecting
    every insert, only the ones outside it."""
    from app import app
    from model import CAREER_STATUSES, EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        for status in CAREER_STATUSES:
            db.session.add(
                EnvironmentReport(
                    user_id=1,
                    raw_answers={},
                    stage_size=3,
                    comp=3,
                    experienced_outcome=3,
                    career_status=status,
                    version="v1",
                )
            )
        db.session.commit()
        assert EnvironmentReport.query.filter_by(user_id=1).count() == len(CAREER_STATUSES)


def test_dimension_score_out_of_range_is_rejected(client, seed_user):
    from app import app
    from model import EnvironmentDimensionScore, EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        report = EnvironmentReport(
            user_id=1,
            raw_answers={},
            stage_size=3,
            comp=3,
            experienced_outcome=3,
            career_status="employed",
            version="v1",
        )
        db.session.add(report)
        db.session.flush()

        db.session.add(
            EnvironmentDimensionScore(
                environment_report_id=report.id,
                user_id=1,
                dimension_key="pace",
                score=1.1,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_duplicate_dimension_on_one_report_is_rejected(client, seed_user):
    """uq_edscore_report_dim: one submission cannot write 'pace' twice."""
    from app import app
    from model import EnvironmentDimensionScore, EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        report = EnvironmentReport(
            user_id=1,
            raw_answers={},
            stage_size=3,
            comp=3,
            experienced_outcome=3,
            career_status="employed",
            version="v1",
        )
        db.session.add(report)
        db.session.flush()

        db.session.add(
            EnvironmentDimensionScore(
                environment_report_id=report.id, user_id=1, dimension_key="pace", score=0.5
            )
        )
        db.session.commit()

        db.session.add(
            EnvironmentDimensionScore(
                environment_report_id=report.id, user_id=1, dimension_key="pace", score=0.7
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_the_same_dimension_key_across_two_reports_is_allowed(client, seed_user):
    """Unlike the person-side dimension-score table, there is no (user, dimension) uniqueness here --
    that is what makes append-only history possible at all."""
    from app import app
    from model import EnvironmentDimensionScore, db

    seed_user(1)
    with app.app_context():
        first_id = _write(db, user_id=1)
        db.session.commit()
        second_id = _write(db, user_id=1)
        db.session.commit()

        assert first_id != second_id
        assert (
            EnvironmentDimensionScore.query.filter_by(
                user_id=1, dimension_key="pace"
            ).count()
            == 2
        )


def test_environment_report_requires_a_real_user(client):
    """fk_envreport_user: an orphan user_id is rejected, same discipline
    test_company_side_tables.py's incident note describes for the company-side tables."""
    from app import app
    from model import EnvironmentReport, db

    with app.app_context():
        db.session.add(
            EnvironmentReport(
                user_id=999999,
                raw_answers={},
                stage_size=3,
                comp=3,
                experienced_outcome=3,
                career_status="employed",
                version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


# ---------------------------------------------------------------------------
# subject: current vs past (PRODUCT_DECISIONS.md §2, 2026-10-01)
# ---------------------------------------------------------------------------


def test_subject_defaults_to_current_and_is_serialized(client, seed_user):
    from app import app
    from environment_report_store import environment_report_history, latest_environment_report
    from model import db

    seed_user(1)
    with app.app_context():
        _write(db, user_id=1)
        db.session.commit()

        assert latest_environment_report(1)["subject"] == "current"
        assert environment_report_history(1)[0]["subject"] == "current"


def test_a_past_report_never_becomes_the_latest_report(client, seed_user):
    """The Situation Report reads `latest_environment_report`; a past report filed
    AFTER the current one must not take its place."""
    from app import app
    from environment_report_store import latest_environment_report
    from model import db

    seed_user(1)
    with app.app_context():
        current_id = _write(db, user_id=1, stage_size=2)
        db.session.commit()
        _write(db, user_id=1, stage_size=5, subject="past")
        db.session.commit()

        latest = latest_environment_report(1)
        assert latest["id"] == current_id
        assert latest["subject"] == "current"
        narrowed = latest_environment_report(1, include_raw_answers=False)
        assert narrowed["id"] == current_id


def test_a_past_only_user_has_no_latest_report(client, seed_user):
    from app import app
    from environment_report_store import latest_environment_report
    from model import db

    seed_user(1)
    with app.app_context():
        _write(db, user_id=1, subject="past")
        db.session.commit()

        assert latest_environment_report(1) is None


def test_history_includes_past_reports_with_their_subject(client, seed_user):
    from app import app
    from environment_report_store import environment_report_history
    from model import db

    seed_user(1)
    with app.app_context():
        current_id = _write(db, user_id=1)
        db.session.commit()
        past_id = _write(db, user_id=1, subject="past")
        db.session.commit()

        history = environment_report_history(1)
        assert [(h["id"], h["subject"]) for h in history] == [
            (past_id, "past"),
            (current_id, "current"),
        ]


def test_count_environment_reports_counts_per_subject_and_per_user(client, seed_user):
    from app import app
    from environment_report_store import count_environment_reports
    from model import db

    seed_user(1)
    seed_user(2)
    with app.app_context():
        assert count_environment_reports(1, "current") == 0
        assert count_environment_reports(1, "past") == 0
        _write(db, user_id=1)
        _write(db, user_id=1)
        _write(db, user_id=1, subject="past")
        _write(db, user_id=2, subject="past")
        db.session.commit()

        assert count_environment_reports(1, "current") == 2
        assert count_environment_reports(1, "past") == 1
        assert count_environment_reports(2, "current") == 0
        with pytest.raises(ValueError):
            count_environment_reports(1, "former")


def test_write_rejects_an_unknown_subject_before_touching_the_session(client, seed_user):
    from app import app
    from model import EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        with pytest.raises(ValueError):
            _write(db, user_id=1, subject="previous")
        assert EnvironmentReport.query.filter_by(user_id=1).count() == 0


def _raw_row(**overrides):
    from model import EnvironmentReport

    kwargs = dict(
        user_id=1,
        raw_answers={},
        stage_size=3,
        comp=3,
        experienced_outcome=3,
        career_status="employed",
        version="v1",
    )
    kwargs.update(overrides)
    return EnvironmentReport(**kwargs)


@pytest.mark.parametrize("bad_subject", ["previous", "Past", ""])
def test_subject_outside_the_vocabulary_is_rejected(client, seed_user, bad_subject):
    """ck_envreport_subject_vocab, at the database (the ORM path skips the store's check)."""
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        db.session.add(_raw_row(subject=bad_subject))
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_a_past_first_job_row_is_rejected(client, seed_user):
    """ck_envreport_past_not_first_job: a never-employed user has no past job."""
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        db.session.add(_raw_row(subject="past", career_status="first_job"))
        with pytest.raises(IntegrityError):
            db.session.commit()


@pytest.mark.parametrize(
    "subject, career_status",
    [("current", "employed"), ("current", "between_jobs"), ("current", "first_job"),
     ("past", "employed"), ("past", "between_jobs")],
)
def test_every_allowed_subject_and_status_pair_is_accepted(client, seed_user, subject, career_status):
    """Sibling VALID-row test (S-40 lesson) for the two subject CHECKs."""
    from app import app
    from model import EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        db.session.add(_raw_row(subject=subject, career_status=career_status))
        db.session.commit()
        assert EnvironmentReport.query.filter_by(user_id=1).one().subject == subject


def test_subject_vocabulary_agrees_across_orm_instrument_and_wire():
    from typing import get_args

    from model import ENV_REPORT_SUBJECTS
    from solverah.schemas.situation_report import Subject
    from work_pulse.situation_items import SUBJECTS

    assert ENV_REPORT_SUBJECTS == SUBJECTS == get_args(Subject) == ("current", "past")


# ---------------------------------------------------------------------------
# The five optional exploratory outcomes (PRODUCT_DECISIONS.md §2, 2026-10-13)
# ---------------------------------------------------------------------------

OUTCOMES = {
    "outcome_satisfaction": 4,
    "outcome_performance": 5,
    "outcome_engagement": 2,
    "outcome_sustainability": 1,
    "outcome_retention_intention": 3,
}


def test_outcome_columns_agree_with_the_instrument_and_are_nullable():
    from model import ENV_OUTCOME_COLUMNS, EnvironmentReport
    from work_pulse.situation_items import OUTCOME_COLUMNS, OUTCOME_ITEMS

    assert list(OUTCOME_COLUMNS) == [i["item_id"] for i in OUTCOME_ITEMS]
    assert tuple(OUTCOME_COLUMNS.values()) == ENV_OUTCOME_COLUMNS
    for column in ENV_OUTCOME_COLUMNS:
        assert EnvironmentReport.__table__.c[column].nullable is True


def test_outcomes_round_trip_raw_through_latest_and_history(client, seed_user):
    """Stored RAW (1..5), not mapped to 0..1 -- the mapping is the analysis's."""
    from app import app
    from environment_report_store import environment_report_history, latest_environment_report
    from model import db

    seed_user(1)
    with app.app_context():
        _write(db, user_id=1, outcomes=OUTCOMES)
        db.session.commit()

        for result in (
            latest_environment_report(1),
            latest_environment_report(1, include_raw_answers=False),
            environment_report_history(1)[0],
        ):
            for column, value in OUTCOMES.items():
                assert result[column] == value, column


def test_outcomes_left_out_or_none_are_null_and_still_serialized(client, seed_user):
    """Skipped: an omitted outcome (and every caller written before 2026-10-13)
    stores NULL, and the key is present on the read, never silently absent."""
    from app import app
    from environment_report_store import latest_environment_report
    from model import ENV_OUTCOME_COLUMNS, db

    seed_user(1)
    with app.app_context():
        _write(db, user_id=1, outcomes={"outcome_engagement": None, "outcome_performance": 3})
        db.session.commit()

        result = latest_environment_report(1)
        for column in ENV_OUTCOME_COLUMNS:
            assert column in result
        assert result["outcome_performance"] == 3
        assert result["outcome_engagement"] is None
        assert result["outcome_satisfaction"] is None

        _write(db, user_id=1)
        db.session.commit()
        assert all(latest_environment_report(1)[c] is None for c in ENV_OUTCOME_COLUMNS)


def test_an_unknown_outcome_key_is_refused_before_anything_is_written(client, seed_user):
    from app import app
    from model import EnvironmentReport, db

    seed_user(1)
    with app.app_context():
        with pytest.raises(ValueError, match="outcomes"):
            _write(db, user_id=1, outcomes={"satisfaction": 4})
        db.session.rollback()
        assert EnvironmentReport.query.filter_by(user_id=1).count() == 0


@pytest.mark.parametrize("column", [
    "outcome_satisfaction", "outcome_performance", "outcome_engagement",
    "outcome_sustainability", "outcome_retention_intention",
])
@pytest.mark.parametrize("bad", [0, 6])
def test_outcome_outside_one_to_five_is_rejected_by_the_check(client, seed_user, column, bad):
    """ck_envreport_<column>_range, at the database, behind the service's guard.
    The store flushes the header row for its id, so the CHECK fires inside the write."""
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        with pytest.raises(IntegrityError):
            _write(db, user_id=1, outcomes={column: bad})
        db.session.rollback()


@pytest.mark.parametrize("value", [None, 1, 5])
def test_outcome_check_accepts_the_ends_of_the_scale_and_null(client, seed_user, value):
    """Sibling VALID-row test (S-40 lesson) for the CHECK above."""
    from app import app
    from environment_report_store import latest_environment_report
    from model import db

    seed_user(1)
    with app.app_context():
        _write(db, user_id=1, outcomes={"outcome_sustainability": value})
        db.session.commit()
        assert latest_environment_report(1)["outcome_sustainability"] == value
