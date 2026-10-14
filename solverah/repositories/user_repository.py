"""Reads and writes for the ``users`` table.

Every query against ``User`` that used to sit inline in a handler lives here.
Collecting them is what made Phase 2c -- renaming the table to ``users``, adding
``public_id``/``status``/``version``, moving to a ``citext`` email column -- a
change to one file rather than a search across 4,000 lines.

Both things this file previously called out as wrong are fixed as of Phase 2c
(2026-08-27):

* The email column is ``CITEXT``, so a lookup is case-insensitive in the database
  rather than by every caller remembering to lower-case first.
  :func:`find_by_email` still normalises, and deliberately: registration stores a
  lower-cased address, and having the read agree with the write costs one
  ``.lower()`` and removes the question of which of the two is authoritative.
* The table is ``users``.  ``user`` is a reserved word and was quoted in every
  generated statement (P1-8's first bullet).
"""

from __future__ import annotations

from typing import Optional, Tuple

import sqlalchemy as sa

from model import User, db

__all__ = [
    "add",
    "email_exists",
    "find_by_email",
    "find_by_id",
]


def _live_email(email: str) -> Tuple[sa.ColumnElement, sa.ColumnElement]:
    """The WHERE clause of every lookup by address: ``uq_users_email``'s own.

    ``uq_users_email`` is partial on ``deleted_at IS NULL``, and Postgres uses a
    partial index only for a query whose WHERE implies the index's predicate.
    Filtering on the address alone therefore could not use the one index on it,
    and every lookup -- every signed-in request resolves its user here -- was a
    sequential scan of ``users``.

    The predicate is for the index, not a soft-delete: nothing sets
    ``deleted_at`` (tombstoning frees an address by rewriting it, see
    ``account_repository.tombstone_user``), so no account reads differently for
    it. It does say out loud the rule the index draws -- an address belongs to
    its live row -- which is the right answer on the day something does set it.
    """
    return User.email == email.strip().lower(), User.deleted_at.is_(None)


def find_by_email(email: Optional[str]) -> Optional[User]:
    """Return the live user with this email, or None.

    The email is stripped and lower-cased here rather than at each of the eight
    call sites that used to do it inline -- a caller that forgot produced a
    "no such account" for an address that exists, which reads as a data bug.
    The lookup is served by ``uq_users_email``; :func:`_live_email` says why it
    carries ``deleted_at IS NULL``.
    """
    if not email:
        return None
    return User.query.filter(*_live_email(email)).first()


def find_by_id(user_id: int) -> Optional[User]:
    """Return the user with this primary key, or None."""
    return db.session.get(User, user_id)


def email_exists(email: Optional[str]) -> bool:
    """Whether a live account already holds this email.

    An ``EXISTS`` on :func:`find_by_email`'s predicate: the same index answers
    it, and no row is loaded to learn a boolean.
    """
    if not email:
        return False
    return bool(
        db.session.execute(sa.select(sa.exists().where(*_live_email(email)))).scalar()
    )


def add(user: User) -> User:
    """Stage a new user for insertion.

    Does not commit: the service owns the transaction, so the user row and the
    audit row that describes its creation land together or not at all.
    """
    db.session.add(user)
    return user
