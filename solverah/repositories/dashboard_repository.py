"""The one read behind the dashboard's Recent Activity card.

Five tables each hold a dated event the job-seeker made happen: an instrument
sitting in ``assessment_submissions``, an environment report, a manager profile,
a pulse check-in, and the resume on file. The dashboard wants the newest of each,
so this is one ``UNION ALL`` of per-source ``max()`` aggregates -- one round trip
however many sources there are, and every branch is served by an index that
already leads with ``user_id``.

Only the latest event per source (per instrument, for assessments) comes back.
That is deliberate: four weekly check-ins listed as four rows would crowd out
everything else on a five-row card, and "you checked in on your pulse, 2 days
ago" says what the four rows would.

The core instrument's *submission row* is read here and nothing past it: the row
carries a kind and timestamps, never answers or scores, which is what keeps this
module outside the D-01 allowlist (see ``assessment_repository``'s docstring).
"""

from __future__ import annotations

import datetime
from typing import List, NamedTuple, Optional

import sqlalchemy as sa

from model import (
    AssessmentSubmission,
    EnvironmentReport,
    ManagerProfile,
    PulseCheckin,
    Resume,
    db,
)

__all__ = [
    "ActivityRow",
    "SOURCE_ASSESSMENT",
    "SOURCE_ENVIRONMENT_REPORT",
    "SOURCE_MANAGER_PROFILE",
    "SOURCE_PULSE_CHECKIN",
    "SOURCE_RESUME",
    "latest_activity",
]

SOURCE_ASSESSMENT = "assessment"
SOURCE_ENVIRONMENT_REPORT = "environment_report"
SOURCE_MANAGER_PROFILE = "manager_profile"
SOURCE_PULSE_CHECKIN = "pulse_checkin"
SOURCE_RESUME = "resume"

#: ``wpll`` is the anonymous pre-signup session claimed onto the account, not
#: something the user did from their account, so it is not activity.
_EXCLUDED_KINDS = ("wpll",)


class ActivityRow(NamedTuple):
    """The newest event of one source. ``kind`` is set for assessments only."""

    source: str
    kind: Optional[str]
    at: datetime.datetime


def _single_source(source: str, model, column) -> sa.Select:
    """``(source, NULL, max(column))`` for one user-scoped table."""
    return sa.select(
        sa.literal(source).label("source"),
        sa.cast(sa.null(), sa.Text).label("kind"),
        sa.func.max(column).label("at"),
    ).where(model.user_id == sa.bindparam("user_id"))


def _assessments() -> sa.Select:
    """The newest completed sitting of each instrument, one row per kind."""
    return (
        sa.select(
            sa.literal(SOURCE_ASSESSMENT).label("source"),
            AssessmentSubmission.kind.label("kind"),
            sa.func.max(AssessmentSubmission.completed_at).label("at"),
        )
        .where(
            AssessmentSubmission.user_id == sa.bindparam("user_id"),
            AssessmentSubmission.completed_at.isnot(None),
            AssessmentSubmission.kind.notin_(_EXCLUDED_KINDS),
        )
        .group_by(AssessmentSubmission.kind)
    )


def _environment_reports() -> sa.Select:
    """The newest report about the user's CURRENT job. A past-job report
    (PRODUCT_DECISIONS.md §2, 2026-10-01) is not activity here: the card says
    "You described your current job", and the dashboard's recommendations read
    this source as "has a Situation Report", which a past report never gives."""
    return _single_source(
        SOURCE_ENVIRONMENT_REPORT, EnvironmentReport, EnvironmentReport.submitted_at
    ).where(EnvironmentReport.subject == "current")


def latest_activity(user_id: int) -> List[ActivityRow]:
    """The newest event per source for *user_id*, newest first. One query.

    A source the user has never touched is absent rather than a row with a null
    timestamp.
    """
    union = sa.union_all(
        _assessments(),
        _environment_reports(),
        _single_source(SOURCE_MANAGER_PROFILE, ManagerProfile, ManagerProfile.created_at),
        _single_source(SOURCE_PULSE_CHECKIN, PulseCheckin, PulseCheckin.taken_at),
        _single_source(SOURCE_RESUME, Resume, Resume.created_at),
    ).subquery()
    stmt = (
        sa.select(union.c.source, union.c.kind, union.c.at)
        .where(union.c.at.isnot(None))
        .order_by(union.c.at.desc())
    )
    rows = db.session.execute(stmt, {"user_id": user_id}).all()
    return [ActivityRow(source=row.source, kind=row.kind, at=row.at) for row in rows]
