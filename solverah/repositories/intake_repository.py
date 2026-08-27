"""Reads and writes for ``intake_submissions`` and ``user_intake``.

Since Phase 2d ``user_intake`` holds one live column: ``selected_statement_ids``.
The ``wpll_*`` and ``wpl_*`` families beside it moved to
``assessment_submissions`` and are read by nothing; they are dropped next
release.  That is why :func:`upsert_user_intake` takes two arguments where it
used to take five.

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


def upsert_user_intake(user_id: int, selected_ids: List[Any]) -> UserIntake:
    """Create or update the statement selections attached to an account.

    Statement selections are intake data: they are what the visitor picked on
    screen 1 of ``/start``, they are not scored, and no instrument produces them.
    So they stay here.

    **The WPLL answers used to be written here too, and are not any more.** Phase
    2d moved them to ``assessment_submissions`` with the other four instruments'
    data -- see ``intake_service.save_to_account``, which now writes both halves.
    The ``wpll_*`` and ``wpl_*`` columns still exist on this table, are read by
    nothing, and are dropped in the next release; the same one-release stay
    ``users.profile_data`` is serving.

    Does not commit -- the caller owns the transaction.
    """
    intake = find_user_intake(user_id)

    if intake is None:
        intake = UserIntake(user_id=user_id, selected_statement_ids=selected_ids)
        db.session.add(intake)
        return intake

    intake.selected_statement_ids = selected_ids
    return intake
