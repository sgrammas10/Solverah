"""Reads and writes for ``intake_submissions`` and ``user_intake``.

One oddity is preserved here rather than cleaned up: :func:`insert_submission`
opens a raw psycopg2 connection instead of using the SQLAlchemy session.  That is
how both intake write paths have always worked.  It is worth being explicit about
what it costs, because it is not obvious from the call site:

* The INSERT is committed on **its own connection**, outside the request's
  SQLAlchemy transaction.  So the submission row can land while a later step in
  the same handler fails, and nothing rolls it back.
* It takes a second connection from the database for the duration, on top of the
  pooled one the request already holds -- so the effective connection ceiling is
  halved on these two endpoints.
* ``SQLALCHEMY_ENGINE_OPTIONS`` -- ``pool_pre_ping``, the sized pool, the
  statement timeout -- do not apply to it.

Changing it means changing transactional behaviour, so it is not this batch's to
change.  It is at least in one function now instead of being open-coded in two
handlers, which is what makes it a small change later.
"""

from __future__ import annotations

import datetime
import os
from typing import Any, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from model import IntakeSubmission, UserIntake, db

__all__ = [
    "find_submission",
    "find_user_intake",
    "get_db_conn",
    "insert_submission",
    "upsert_user_intake",
]


def get_db_conn():
    """Open a raw psycopg2 connection returning rows as dicts.

    Used by the intake insert path, which bypasses SQLAlchemy.  Callers are
    responsible for calling ``conn.close()``.
    """
    return psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)


def find_submission(submission_id: str) -> Optional[IntakeSubmission]:
    """Return the intake submission with this id, or None."""
    return IntakeSubmission.query.filter_by(id=submission_id).first()


def insert_submission(fields, email: str, status: str) -> None:
    """Insert one ``intake_submissions`` row.

    Args:
        fields: Normalised fields from :func:`solverah.domain.intake.parse_submission`.
        email: Address to record.  The anonymous path uses the submitted address;
            the authenticated path uses the JWT identity, so that a signed-in
            user cannot file a submission against someone else's email.
        status: ``"uploaded"`` for anonymous, ``"account_linked"`` when a
            signed-in user submitted it.
    """
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intake_submissions
                    (id, first_name, last_name, email, state, phone, linkedin_url, portfolio_url,
                    resume_key, resume_mime, resume_size_bytes, status)
                    VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s)
                    """,
                    (
                        fields.submission_id,
                        fields.first_name,
                        fields.last_name,
                        email,
                        fields.state,
                        fields.phone or None,
                        fields.linkedin_url or None,
                        fields.portfolio_url or None,
                        fields.object_key,
                        fields.mime,
                        fields.size,
                        status,
                    ),
                )
    finally:
        conn.close()


def find_user_intake(user_id: int) -> Optional[UserIntake]:
    """Return the ``user_intake`` row for this user, or None."""
    return UserIntake.query.filter_by(user_id=user_id).first()


def upsert_user_intake(
    user_id: int,
    selected_ids: List[Any],
    wpll_answers: List[Any],
    wpll_insight_text: str,
    now: datetime.datetime,
) -> UserIntake:
    """Create or update the anonymous-session data attached to an account.

    ``wpll_completed_at`` is set only on the first save carrying answers, so a
    re-save does not move the completion timestamp forward.

    The ``wpl_*`` columns are never touched here.  They belong to the Work Pulse
    submit endpoint, and writing them from this path would silently overwrite a
    completed assessment with nothing.

    Does not commit -- the caller owns the transaction.
    """
    intake = find_user_intake(user_id)

    if intake is None:
        intake = UserIntake(
            user_id=user_id,
            selected_statement_ids=selected_ids,
            wpll_answers=wpll_answers,
            wpll_insight_text=wpll_insight_text or None,
            wpll_completed_at=now if wpll_answers else None,
        )
        db.session.add(intake)
        return intake

    intake.selected_statement_ids = selected_ids
    intake.wpll_answers = wpll_answers
    intake.wpll_insight_text = wpll_insight_text or None
    # Only set wpll_completed_at on first save; preserve if already set.
    if wpll_answers and intake.wpll_completed_at is None:
        intake.wpll_completed_at = now
    return intake
