"""Queries against the profile-adjacent tables.

``profile_data`` itself is a column on ``user``, so "the profile" is written
through the user row -- see :func:`save_profile_data` for why that is a single
function rather than an attribute assignment scattered across handlers.

``ResumeParseCorrection`` is the parser's training corpus: one row per field the
user edited after an upload, holding both what the parser produced and what they
changed it to.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from model import IntakeSubmission, JobRecommendation, ResumeParseCorrection, User, db

__all__ = [
    "count_job_recommendations",
    "find_correction",
    "has_intake_submission",
    "record_resume_corrections",
    "save_profile_data",
]


def save_profile_data(user: User, profile_data: Dict[str, Any]) -> None:
    """Replace the user's ``profile_data`` blob.

    Assignment rather than mutation is required, not stylistic: the column is a
    plain JSON type with no mutation tracking, so mutating the dict in place
    leaves SQLAlchemy unaware anything changed and the write is silently lost.

    Does not commit -- the caller owns the transaction, so the profile change and
    the audit row that records it land together.
    """
    user.profile_data = profile_data


def find_correction(
    user_id: int, resume_key: str, field: str
) -> Optional[ResumeParseCorrection]:
    """Return the existing correction row for this (user, resume, field)."""
    return ResumeParseCorrection.query.filter_by(
        user_id=user_id,
        resume_key=resume_key,
        field=field,
    ).first()


def record_resume_corrections(
    user_id: int,
    resume_key: str,
    corrections: List[tuple],
) -> int:
    """Upsert one ``ResumeParseCorrection`` per changed field.

    Args:
        corrections: ``(field, parsed_value, corrected_value)`` triples, as
            produced by :func:`solverah.domain.profile.resume_field_corrections`.

    Returns:
        How many rows were written or updated.

    Note:
        ``parsed_value`` is only set on insert.  On a second edit of the same
        field the original parser output is preserved and only the corrected
        value moves -- otherwise the row would end up comparing the user's first
        edit to their second, and the parser signal would be lost.
    """
    written = 0
    for field, parsed_value, corrected_value in corrections:
        existing = find_correction(user_id, resume_key, field)
        if existing:
            existing.corrected_value = corrected_value
            existing.updated_at = datetime.datetime.utcnow()
        else:
            db.session.add(
                ResumeParseCorrection(
                    user_id=user_id,
                    resume_key=resume_key,
                    field=field,
                    parsed_value=parsed_value,
                    corrected_value=corrected_value,
                )
            )
        written += 1
    return written


def count_job_recommendations(user_id: int) -> int:
    """How many recommendation rows exist for this user."""
    return JobRecommendation.query.filter_by(user_id=user_id).count()


def has_intake_submission(email: str) -> bool:
    """Whether a pre-launch intake submission exists for this address.

    Case-sensitive, matching the original query.  ``IntakeSubmission.email`` is
    stored as submitted, so an address that differs only in case reads as absent
    -- a real bug, fixed by Phase 2's ``citext`` columns rather than by changing
    the comparison here, since changing it would alter which dashboards show the
    intake banner.
    """
    return IntakeSubmission.query.filter_by(email=email).first() is not None
