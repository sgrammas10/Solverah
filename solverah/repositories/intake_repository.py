"""Reads and writes for ``intake_submissions`` and ``user_intake``.

Since Phase 2d ``user_intake`` holds one live column: ``selected_statement_ids``.
The ``wpll_*`` and ``wpl_*`` families beside it moved to
``assessment_submissions`` and are read by nothing; they are dropped next
release.  That is why :func:`upsert_user_intake` takes two arguments where it
used to take five.

Nothing here commits: every statement runs on ``db.session``, inside the
caller's transaction.  :func:`insert_submission` was the exception until
2026-09-28.  It opened a raw psycopg2 connection and committed the row on it,
which meant:

* the row landed even when a later step of the same handler failed -- so
  ``finalize``'s "the row and its notification are one commit" was not true,
  and an outbox failure left a submission nobody was told about;
* a second, unpooled connection per submit, which ``SQLALCHEMY_ENGINE_OPTIONS``
  (``pool_pre_ping``, the statement timeout) never reached.

It is a Core INSERT on the session now: the caller's commit makes it durable and
the caller's rollback undoes it.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from sqlalchemy import func, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import load_only

from model import IntakeSubmission, UserIntake, db

__all__ = [
    "find_submission",
    "find_user_intake",
    "insert_submission",
    "upsert_user_intake",
]


def find_submission(submission_id: str) -> Optional[IntakeSubmission]:
    """Return the intake submission with this id, or None."""
    return IntakeSubmission.query.filter_by(id=submission_id).first()


def insert_submission(fields, email: str, status: str) -> IntakeSubmission:
    """Insert one ``intake_submissions`` row in the caller's transaction.

    The INSERT runs now, so a duplicate id or an over-long value still fails
    here, at the call -- but the row is durable only once the caller commits.
    Does not commit.

    Args:
        fields: Normalised fields from :func:`solverah.domain.intake.parse_submission`.
        email: Address to record.  The anonymous path uses the submitted address;
            the authenticated path uses the JWT identity, so that a signed-in
            user cannot file a submission against someone else's email.
        status: ``"uploaded"`` for anonymous, ``"account_linked"`` when a
            signed-in user submitted it.

    Returns:
        The inserted values as a *transient* ``IntakeSubmission``: never added
        to the session, so changing it writes nothing.  It saves a caller that
        needs the stored values from reading back the row it just wrote.
        ``created_at`` is the database's default and is not on it.
    """
    values = {
        "id": fields.submission_id,
        "first_name": fields.first_name,
        "last_name": fields.last_name,
        "email": email,
        "state": fields.state,
        "phone": fields.phone or None,
        "linkedin_url": fields.linkedin_url or None,
        "portfolio_url": fields.portfolio_url or None,
        "resume_key": fields.object_key,
        "resume_mime": fields.mime,
        "resume_size_bytes": fields.size,
        "status": status,
    }
    db.session.execute(insert(IntakeSubmission.__table__).values(**values))
    return IntakeSubmission(**values)


def find_user_intake(user_id: int, *, only: Sequence[str] = ()) -> Optional[UserIntake]:
    """Return the ``user_intake`` row for this user, or None.

    Args:
        user_id: The account.
        only: Attribute names to load.  The rest are deferred and load on first
            access.  Empty (the default) loads the whole row, dead ``wpll_*`` /
            ``wpl_*`` JSON included.
    """
    query = UserIntake.query.filter_by(user_id=user_id)
    if only:
        query = query.options(load_only(*(getattr(UserIntake, name) for name in only)))
    return query.first()


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

    One ``INSERT ... ON CONFLICT (user_id) DO UPDATE``.  It was a SELECT and
    then an INSERT or an UPDATE, so two claims for one account at once could
    both see no row, both INSERT, and the second died on the unique
    ``user_id`` at commit; now the second waits for the first and updates.
    The row comes back through ``RETURNING`` with ``populate_existing``, so a
    copy already in the session is refreshed rather than left stale.

    Does not commit -- the caller owns the transaction.
    """
    stmt = pg_insert(UserIntake).values(
        user_id=user_id, selected_statement_ids=selected_ids
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[UserIntake.user_id],
        set_={
            "selected_statement_ids": stmt.excluded.selected_statement_ids,
            # ON CONFLICT does not fire Column.onupdate; the ORM UPDATE this
            # replaced did.
            "updated_at": func.now(),
        },
    ).returning(UserIntake)
    return db.session.scalars(
        stmt, execution_options={"populate_existing": True}
    ).one()
