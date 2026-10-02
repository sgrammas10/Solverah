"""Tests for assessment_store.has_completed_assessment -- the completion gate behind
`wp_v2_completed` in the user payload.

Deliberately written WITHOUT naming the person-side tables: seeding goes through
persist_submission (the single write path) and reading goes through has_completed_assessment,
so this file stays off the tests/test_employer_visibility.py allowlist by construction rather
than by exemption.
"""

import pytest


def _fake_submission(scoring_key_version: str):
    """A minimally valid ScoredSubmission. Choices/scores are shaped, not scored -- this file
    tests persistence and gating, not the scorer (test_assessment_form.py owns that)."""
    from assessment_form import ScoredSubmission

    dims = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
    choices = {}
    for d in dims:
        for rung in range(1, 5):
            choices[f"{d[:2]}{rung}v2"] = "A"
    return ScoredSubmission(
        form_version="v2-2026-08-18",
        scoring_key_version=scoring_key_version,
        scores={d: 0.5 for d in dims},
        choices=choices,
        # Shaped like the real thing: five graded dimensions, feedback None (D-17(a)).
        confidences={d: (None if d == "feedback" else 1.0) for d in dims},
    )


def test_no_submission_means_not_completed(client):
    from app import app
    from assessment_store import has_completed_assessment

    with app.app_context():
        assert has_completed_assessment(424242) is False


def test_current_key_submission_counts_as_completed(client, seed_user):
    from app import app
    from model import db
    from assessment_form import scoring_key_version
    from assessment_store import has_completed_assessment, persist_submission

    # assessment_response.user_id is a real foreign key. User 2 is deliberately NOT
    # seeded -- the per-user assertion below is about a user with no submission, and
    # has_completed_assessment reads rows rather than checking the user exists.
    seed_user(1)

    with app.app_context():
        persist_submission(db, 1, _fake_submission(scoring_key_version()))
        db.session.commit()
        assert has_completed_assessment(1) is True
        # And it is per-user, not global.
        assert has_completed_assessment(2) is False


def test_stale_key_submission_does_not_count(client, seed_user):
    """The load-bearing assertion: completion is a fact about an INSTRUMENT.

    A sitting stored under a superseded scoring key must not satisfy the current instrument's
    completion gate -- this is what makes 'the item file changed' automatically re-prompt
    everyone (decided 2026-08-19), instead of silently treating v-old profiles as current.
    """
    from app import app
    from model import db
    from assessment_store import has_completed_assessment, persist_submission

    seed_user(3)

    with app.app_context():
        persist_submission(db, 3, _fake_submission("v1-superseded+mean_pole"))
        db.session.commit()
        assert has_completed_assessment(3) is False


def test_a_sitting_the_current_item_file_cannot_score_reads_as_absent(client, seed_user):
    """Situation-report F2 hand-off (2026-10-02).

    The default pin (first_completed_core_submission_id) is not keyed to the scoring-key
    version, so after an item-bank change it can name a sitting whose item ids the current
    file no longer holds. Re-scoring that sitting used to raise AssessmentError, which the
    Situation Report surfaced as a 500. It must read as an absence instead.

    _fake_submission's item ids are shaped, not real, so the current file cannot score them --
    which is exactly the post-change case.
    """
    from app import app
    from model import db
    from assessment_store import dimension_scores_for_submission, persist_submission

    seed_user(4)

    with app.app_context():
        submission_id = persist_submission(db, 4, _fake_submission("v1-superseded+mean_pole"))
        db.session.commit()
        assert dimension_scores_for_submission(submission_id) is None


def test_an_unknown_sitting_reads_as_absent(client):
    from app import app
    from assessment_store import dimension_scores_for_submission

    with app.app_context():
        assert dimension_scores_for_submission("0" * 32) is None
