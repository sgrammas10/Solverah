"""manager_profile_store.py -- persistence for the Manager Decoder's observed-manager
instrument (BUILD_PLAN C-3).

No Flask, no scoring logic. A caller hands `write_manager_profile` the raw answers
(authored option identity -- see `model.ManagerProfile`'s docstring) and the dimension
scores `score_manager_profile` already computed, and storage persists both, unmodified.
Deliberately shaped like `environment_report_store.py`: the write path does not commit
(the caller owns the transaction), and reads return plain dicts rather than ORM rows, so a
consumer cannot navigate back into the session through the return value.

APPEND-ONLY (D-16 tradition), same reasoning as `environment_reports`: this is ⚑4's shared
store -- the Decoder (C-2) reads it now, the Situation Report's manager section
(workstream A) reads it later -- and a store two features read cannot silently rewrite the
row one of them is currently looking at. Every call to `write_manager_profile` inserts a
new `manager_profiles` row; `latest_manager_profile` is what "current" means.
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "write_manager_profile",
    "has_manager_profile",
    "latest_manager_profile",
    "manager_profile_history",
]


def write_manager_profile(
    db,
    user_id: int,
    *,
    answers: list[dict],
    dimension_scores: dict[str, float],
    scoring_key: str,
    version: str,
) -> int:
    """Write one sitting. Does NOT commit -- the caller owns the transaction boundary,
    same as `assessment_store.persist_submission` and `write_environment_report`.

    Returns the new `manager_profiles.id`.
    """
    from model import ManagerProfile

    row = ManagerProfile(
        user_id=user_id,
        answers=answers,
        dimension_scores=dimension_scores,
        scoring_key=scoring_key,
        version=version,
    )
    db.session.add(row)
    db.session.flush()  # populates row.id for a caller that needs it before commit
    return row.id


def _serialize(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "answers": row.answers,
        "dimension_scores": row.dimension_scores,
        "scoring_key": row.scoring_key,
        "version": row.version,
    }


def has_manager_profile(user_id: int) -> bool:
    """Whether this user has submitted at least one sitting.

    The Situation Report's manager section (⚑4) asks only this, so it gets one
    `SELECT EXISTS` on `user_id` -- the leading column of
    `ix_manager_profiles_user_created` -- instead of `latest_manager_profile`'s whole
    newest row: neither JSONB column leaves the database to be thrown away.
    """
    import sqlalchemy as sa

    from model import ManagerProfile, db

    return db.session.execute(
        sa.select(sa.exists().where(ManagerProfile.user_id == user_id))
    ).scalar_one()


def latest_manager_profile(user_id: int) -> Optional[dict[str, Any]]:
    """This user's most recent sitting, or None if they have never submitted one.

    THE sanctioned read for the Decoder's `GET /me/manager-playbook`; the Situation
    Report's manager section (⚑4) needs only `has_manager_profile`. Ordered by
    `created_at` (with `id` as the tiebreak two sittings in the same instant would
    otherwise leave ambiguous), matching `ix_manager_profiles_user_created`'s column
    order, so the index hands back the newest row first rather than the rows being
    sorted. Not an index-only scan: the whole row, both JSONB columns included, comes
    from the table.
    """
    from model import ManagerProfile

    row = (
        ManagerProfile.query.filter_by(user_id=user_id)
        .order_by(ManagerProfile.created_at.desc(), ManagerProfile.id.desc())
        .first()
    )
    return _serialize(row) if row is not None else None


def manager_profile_history(user_id: int) -> list[dict[str, Any]]:
    """Every sitting for this user, newest first. Unbounded, unlike
    `latest_manager_profile`: a subject-access export (BUILD_PLAN D-7) asks "what do you
    HOLD about me", not "what applies right now", and this table is append-only (D-16) --
    every retake is a real, separate sitting, not a superseded draft. Same ordering as
    `latest_manager_profile`, matching `ix_manager_profiles_user_created`.
    """
    from model import ManagerProfile

    rows = (
        ManagerProfile.query.filter_by(user_id=user_id)
        .order_by(ManagerProfile.created_at.desc(), ManagerProfile.id.desc())
        .all()
    )
    return [_serialize(row) for row in rows]
