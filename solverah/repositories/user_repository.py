"""Reads and writes for the ``user`` table.

Every query against ``User`` that used to sit inline in a handler lives here.
Collecting them is what makes the Phase 2 changes to this table -- renaming it to
``users``, adding ``public_id``/``status``/``version``, moving to a ``citext``
email column -- a change to one file rather than a search across 4,000 lines.

Two things the current shape gets wrong, carried forward unchanged because
Phase 1a does not alter behaviour:

* Lookups are ``filter_by(email=...)`` against a case-sensitive column, so every
  caller has to remember to lower-case first.  Phase 2's ``citext`` column and
  its partial unique index remove that footgun; until then
  :func:`find_by_email` does the normalising in one place so no caller can
  forget.
* The table is literally named ``user``, a reserved word in Postgres, so it is
  quoted in every generated statement.
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
