"""environment_report_store.py -- persistence for the Situation Report's environment side
(BUILD_PLAN A-2).

No Flask, no scoring logic. This module writes what it is given and reads it back; A-3
computes `dimension_scores` (rules today, the causal model's weights later -- same
interim-to-destination pattern as `culture_fit_score`) and A-5 is the only caller that will
exist once the API lands. Deliberately shaped like `assessment_store.py`: the write path does
not commit (the caller owns the transaction), and reads return plain dicts rather than ORM
rows so a consumer cannot navigate back into the session through the return value.

APPEND-ONLY (D-16 tradition), unlike the person-side dimension-score table. Every call to
`write_environment_report` inserts a new `environment_reports` row and a new set of
`environment_dimension_score` rows -- never an update to an existing one. A second
submission from the same user is a second, independent row; history is the point (it is
what Pulse trends and E-4's training data both read).

D-15 pinning (⚑5) is out of scope here on purpose. The Situation Report pins to a named
person-side snapshot, not to anything in this module -- see `model.py`'s "Environment side"
section docstring for why storing such a pin here would be the wrong place for it.
"""

from __future__ import annotations

from typing import Any, Optional

from model import ENV_DIMENSIONS

__all__ = [
    "write_environment_report",
    "latest_environment_report",
    "environment_report_history",
]


def _require_all_dimensions(dimension_scores: dict[str, float]) -> None:
    """Refuse a partial dimension set rather than storing a report with gaps.

    D-07: an incomplete `dimension_scores` dict silently stored as-is would leave three of
    six dimensions simply absent from every later read, indistinguishable from "not
    computed yet" versus "A-3 dropped one". A-3 owns producing all six; this is the last
    place that can catch the case where it did not, before it becomes a stored fact.
    """
    got = set(dimension_scores)
    want = set(ENV_DIMENSIONS)
    if got != want:
        missing = want - got
        extra = got - want
        raise ValueError(
            "dimension_scores must cover exactly %r. missing=%r extra=%r"
            % (ENV_DIMENSIONS, sorted(missing), sorted(extra))
        )
    for key, score in dimension_scores.items():
        if not (0.0 <= score <= 1.0):
            raise ValueError("dimension_scores[%r] = %r is outside [0, 1]" % (key, score))


def write_environment_report(
    db,
    user_id: int,
    *,
    raw_answers: dict[str, Any],
    dimension_scores: dict[str, float],
    stage_size: int,
    comp: Optional[int],
    experienced_outcome: int,
    career_status: str,
    version: str,
    employer_name_normalized: Optional[str] = None,
    industry: Optional[str] = None,
) -> int:
    """Write one submission: the header row plus its six dimension-score rows.

    Does NOT commit -- the caller owns the transaction boundary, same as
    `assessment_store.persist_submission`. Returns the new `environment_reports.id`.

    `raw_answers` is stored verbatim as JSONB; this function does not interpret its keys,
    because the item ids that populate it belong to A-1, which does not exist yet (see
    `model.py`'s "Environment side" section). `dimension_scores` must name exactly
    `model.ENV_DIMENSIONS`, each in [0, 1] -- A-3's contract, enforced here because a
    caller that got it wrong should fail loudly rather than write a report future readers
    would treat as complete.

    `comp` is `Optional`: the environment instrument's "not sure" option
    (PRODUCT_DECISIONS.md §2, "Environment-instrument rulings", 2026-09-10) answers with
    `None` rather than a guessed 1..5 posture, and `model.EnvironmentReport.comp` is
    nullable to hold it. `dimension_scores` still must cover all six dimensions -- comp
    is a confounder, not a dimension, and this function's completeness guarantee is about
    the dimensions only.

    `industry` is `Optional` on the same terms, and defaults to `None` as well
    (PRODUCT_DECISIONS.md §2, 2026-10-01). It holds a level key from
    `model.ENV_INDUSTRIES` or `None` for "not sure / prefer not to say", and the
    column's CHECK rejects anything else at flush.
    """
    from model import EnvironmentDimensionScore, EnvironmentReport

    _require_all_dimensions(dimension_scores)

    report = EnvironmentReport(
        user_id=user_id,
        raw_answers=raw_answers,
        stage_size=stage_size,
        comp=comp,
        industry=industry,
        experienced_outcome=experienced_outcome,
        career_status=career_status,
        employer_name_normalized=employer_name_normalized,
        version=version,
    )
    db.session.add(report)
    db.session.flush()  # need report.id for the child rows below

    for dimension_key, score in dimension_scores.items():
        db.session.add(
            EnvironmentDimensionScore(
                environment_report_id=report.id,
                user_id=user_id,
                dimension_key=dimension_key,
                score=score,
            )
        )

    return report.id


def _serialize(
    report, scores_by_dim: dict[str, float], *, include_raw_answers: bool = True
) -> dict[str, Any]:
    serialized: dict[str, Any] = {
        "id": report.id,
        "user_id": report.user_id,
        "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None,
    }
    if include_raw_answers:
        # Only touched when wanted: on a row read with it deferred, this
        # attribute access would be a SELECT of its own.
        serialized["raw_answers"] = report.raw_answers
    serialized.update(
        {
            "dimension_scores": scores_by_dim,
            "stage_size": report.stage_size,
            "comp": report.comp,
            "industry": report.industry,
            "experienced_outcome": report.experienced_outcome,
            "career_status": report.career_status,
            "employer_name_normalized": report.employer_name_normalized,
            "version": report.version,
        }
    )
    return serialized


def latest_environment_report(
    user_id: int, *, include_raw_answers: bool = True
) -> Optional[dict[str, Any]]:
    """The user's most recent submission, or None if they have never submitted one.

    THE sanctioned read for A-5's `GET /api/v1/me/situation-report` "env report alone" /
    "both" states. Ordered by `submitted_at` (with `id` as the tiebreak two submissions in
    the same instant would otherwise leave ambiguous), matching
    `ix_environment_reports_user_submitted`'s column order, so the index hands back the
    newest row first rather than the rows being sorted. Not an index-only scan: the row
    itself still comes from the table.

    `include_raw_answers=False` leaves the `raw_answers` JSONB in the database and its
    key out of the result -- the Situation Report page reads the scores, the
    career_status snapshot and `submitted_at`, never the raw answers. Every other key
    is unchanged. The default, and `environment_report_history` (the export), still
    return them.
    """
    from sqlalchemy.orm import defer

    from model import EnvironmentDimensionScore, EnvironmentReport

    query = EnvironmentReport.query.filter_by(user_id=user_id)
    if not include_raw_answers:
        query = query.options(defer(EnvironmentReport.raw_answers))
    report = query.order_by(
        EnvironmentReport.submitted_at.desc(), EnvironmentReport.id.desc()
    ).first()
    if report is None:
        return None

    scores = EnvironmentDimensionScore.query.filter_by(environment_report_id=report.id).all()
    return _serialize(
        report,
        {s.dimension_key: s.score for s in scores},
        include_raw_answers=include_raw_answers,
    )


def environment_report_history(
    user_id: int, limit: Optional[int] = None
) -> list[dict[str, Any]]:
    """Every submission for this user, newest first. Feeds Pulse trends (B-4) and any
    future "how has your description of this job changed" view.

    `limit` is opt-in and unbounded by default: a history read is not the same question as
    "what applies right now" (`latest_environment_report`), and silently truncating it would
    be the same class of bug `assemble_training_data.py`'s module docstring warns against --
    an empty/short response read as absence rather than as a real, small answer.
    """
    from model import EnvironmentDimensionScore, EnvironmentReport

    query = EnvironmentReport.query.filter_by(user_id=user_id).order_by(
        EnvironmentReport.submitted_at.desc(), EnvironmentReport.id.desc()
    )
    if limit is not None:
        query = query.limit(limit)
    reports = query.all()
    if not reports:
        return []

    report_ids = [r.id for r in reports]
    scores = EnvironmentDimensionScore.query.filter(
        EnvironmentDimensionScore.environment_report_id.in_(report_ids)
    ).all()
    scores_by_report: dict[int, dict[str, float]] = {rid: {} for rid in report_ids}
    for s in scores:
        scores_by_report[s.environment_report_id][s.dimension_key] = s.score

    return [_serialize(r, scores_by_report[r.id]) for r in reports]
