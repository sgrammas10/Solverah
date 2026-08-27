"""Queries for assessment state held on ``user_intake`` and the profile document.

Two storage locations, for historical reasons that Phase 2 unifies:

* **Work Pulse** (and the anonymous Lite-Lite session before it) live in
  columns on ``user_intake``: ``wpl_answers``, ``wpl_narrative``,
  ``wpl_result``, ``wpl_completed_at``.
* **FocusType** and **ManagerMatch** results live as keys inside the profile
  document -- ``profiles.extra`` since Phase 2a, and the ``profile_data`` blob
  before it. Neither is a table of their own, which is what Part 5.2 fixes.
* The current 24-item person-side assessment lives in its own tables, which
  this module deliberately does not name, import, or query. They are reachable
  only through ``assessment_store`` -- D-01 keeps that doorway closed and
  ``tests/test_employer_visibility.py`` enforces it by scanning source for
  references, prose included.

Part 5.2 unifies all five instruments onto one form/submission pair with a
scoring strategy per kind, which is what makes adding a sixth a data change.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from model import User, UserIntake, db
from solverah.repositories import profile_repository

__all__ = [
    "find_user_intake",
    "get_profile_result",
    "get_or_create_user_intake",
    "save_profile_result",
]


def find_user_intake(user_id: int) -> Optional[UserIntake]:
    """Return the ``user_intake`` row for this user, or None."""
    return UserIntake.query.filter_by(user_id=user_id).first()


def get_or_create_user_intake(user_id: int) -> UserIntake:
    """Return the user's intake row, creating it if absent.

    Flushes immediately after the INSERT so a concurrent duplicate request
    raises ``IntegrityError`` here -- cheap, before the expensive LLM call --
    rather than at commit, after it. On that collision the other request's row
    is re-read and used.
    """
    from sqlalchemy.exc import IntegrityError

    intake = find_user_intake(user_id)
    if intake is not None:
        return intake

    intake = UserIntake(user_id=user_id)
    db.session.add(intake)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        intake = find_user_intake(user_id)
    return intake


def get_profile_result(user: User, key: str) -> Optional[Any]:
    """Read one assessment result out of the profile document."""
    return profile_repository.load_document(user.id).get(key)


def save_profile_result(user: User, key: str, result: Dict[str, Any]) -> None:
    """Write one assessment result into the profile document.

    Goes through :func:`profile_repository.update_document`, so a submission
    landing at the same moment as a profile save no longer discards it -- the
    pair of writes was one of the two concrete examples P0-1 was written up
    with, and it is the reason this is a function call rather than an
    assignment.

    Does not commit -- the caller owns the transaction.
    """
    profile_repository.update_document(
        user.id, lambda existing: {**existing, key: result}
    )
