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

from typing import Optional

from model import User, db

__all__ = [
    "add",
    "email_exists",
    "find_by_email",
    "find_by_id",
]


def find_by_email(email: Optional[str]) -> Optional[User]:
    """Return the user with this email, or None.

    The email is stripped and lower-cased here rather than at each of the eight
    call sites that used to do it inline -- a caller that forgot produced a
    "no such account" for an address that exists, which reads as a data bug.
    """
    if not email:
        return None
    return User.query.filter_by(email=email.strip().lower()).first()


def find_by_id(user_id: int) -> Optional[User]:
    """Return the user with this primary key, or None."""
    return db.session.get(User, user_id)


def email_exists(email: Optional[str]) -> bool:
    """Whether an account already exists for this email."""
    return find_by_email(email) is not None


def add(user: User) -> User:
    """Stage a new user for insertion.

    Does not commit: the service owns the transaction, so the user row and the
    audit row that describes its creation land together or not at all.
    """
    db.session.add(user)
    return user
