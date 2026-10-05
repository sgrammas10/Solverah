"""situation_report_pin_store.py -- the D-15 pin override for the Situation Report
(BUILD_PLAN A-5, ⚑5).

No Flask, no scoring logic. The DEFAULT pin -- the core sitting that was current when
the user's first Environment Report was filed (`situation_report_service._default_pin`)
-- needs no row here: it is a stable fact computed live from append-only rows (a later
sitting never changes which one was current then). This module owns only the EXPLICIT
override an "POST /me/situation-report/recalibrate" call writes; `solverah.services
.situation_report_service` is what decides whether the override or the default
applies on a given read.

Deliberately shaped like `manager_profile_store.py`: the write path does not commit
(the caller owns the transaction), and reads return plain dicts rather than ORM rows,
so a consumer cannot navigate back into the session through the return value.

MUTABLE, unlike `environment_report_store.py`/`manager_profile_store.py`'s
append-only rows -- there is exactly one active override per user, and
`set_pin` updates it in place. The history of when it moved lives in `AuditLog`
(`solverah.services.audit`), not in a second row here.
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "explicit_pin",
    "set_pin",
]


def _serialize(row) -> dict[str, Any]:
    return {
        "user_id": row.user_id,
        "submission_id": row.submission_id,
        "pinned_at": row.pinned_at.isoformat() if row.pinned_at else None,
    }


def explicit_pin(user_id: int) -> Optional[dict[str, Any]]:
    """This user's recalibrate override, or None if they have never recalibrated.

    THE sanctioned read for `solverah.services.situation_report_service`'s pin
    resolution: `None` here means "still on the default pin", not "unset" --
    there is no separate "no pin at all" state once a user has a completed core
    sitting.
    """
    from model import SituationReportPin

    row = SituationReportPin.query.filter_by(user_id=user_id).first()
    return _serialize(row) if row is not None else None


def set_pin(db, user_id: int, submission_id: str) -> dict[str, Any]:
    """Write or move this user's override to *submission_id*.

    Does NOT commit -- the caller owns the transaction boundary, same as
    `environment_report_store.write_environment_report` and
    `manager_profile_store.write_manager_profile`. Upserts in place rather than
    appending: unlike those two stores, there is exactly one live override per
    user, and `solverah.services.situation_report_service.recalibrate` is what
    decides whether this is worth calling at all (it skips the write, and the
    audit log entry, when the target is already where the effective pin sits --
    ⚑5's idempotence rule).

    One `INSERT ... ON CONFLICT (user_id) DO UPDATE` with no read first: two
    concurrent first recalibrates converge on one row instead of the second
    failing on the unique `user_id`. `pinned_at` is the column default on insert
    and `now()` on a move, as before. The row comes back through `RETURNING`,
    which also refreshes a copy `explicit_pin` already loaded into the session.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from model import SituationReportPin

    statement = pg_insert(SituationReportPin).values(
        user_id=user_id, submission_id=submission_id
    )
    statement = statement.on_conflict_do_update(
        index_elements=["user_id"],
        set_={
            "submission_id": statement.excluded.submission_id,
            "pinned_at": db.func.now(),
        },
    )
    row = db.session.scalars(
        statement.returning(SituationReportPin),
        execution_options={"populate_existing": True},
    ).one()
    return _serialize(row)
