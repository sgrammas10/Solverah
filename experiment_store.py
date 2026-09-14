"""experiment_store.py -- persistence for condition experiments (BUILD_PLAN B-5).

No Flask, no scoring logic, no validation of whether `(dimension, direction)`
names a real `change_in_place` cell -- that lives in
`solverah.services.experiment_service`, the same split `environment_report_store`
draws with A-3's scoring. Deliberately shaped like `environment_report_store.py`
and `situation_report_pin_store.py`: write paths do not commit (the caller owns
the transaction), and reads return plain dicts rather than ORM rows, so a consumer
cannot navigate back into the session through the return value.

MUTABLE, unlike `environment_report_store.py`'s append-only rows -- `abandon`
moves one row's `status` in place, the same shape `situation_report_pin_store.set_pin`
mutates rather than appending.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

__all__ = [
    "EXPERIMENT_WINDOW",
    "active_experiment",
    "checkin_experienced_values",
    "abandon_experiment",
    "experiment_for_user",
    "experiments_for_user",
    "start_experiment",
]

#: The fixed two-week window (BUILD_PLAN B-5). Stored into `ends_at` at write
#: time -- see `model.Experiment`'s docstring for why that is not computed on
#: read.
EXPERIMENT_WINDOW = datetime.timedelta(days=14)


def _serialize(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "dimension": row.dimension,
        "direction": row.direction,
        "register": row.register,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ends_at": row.ends_at.isoformat() if row.ends_at else None,
        "status": row.status,
        "abandoned_at": row.abandoned_at.isoformat() if row.abandoned_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def active_experiment(user_id: int) -> Optional[dict[str, Any]]:
    """This user's currently active experiment, or None.

    THE sanctioned read for the 409 check: `solverah.services.experiment_service
    .start_experiment` calls this before writing, and the partial unique index
    on `experiments` (`uq_experiments_one_active_per_user`) is what makes a race
    between two such checks lose at the database rather than double-book.
    """
    from model import Experiment

    row = Experiment.query.filter_by(user_id=user_id, status="active").first()
    return _serialize(row) if row is not None else None


def start_experiment(
    db, user_id: int, *, dimension: str, direction: str, register: str = "change_in_place"
) -> dict[str, Any]:
    """Write one experiment, `started_at` now and `ends_at` now + 14 days.

    Does NOT commit -- the caller owns the transaction boundary, same as
    `environment_report_store.write_environment_report`. Does not check for an
    already-active experiment; that is the service layer's job (the 409), with
    this call's own `uq_experiments_one_active_per_user` as the backstop a race
    would otherwise slip through.
    """
    from model import Experiment

    now = datetime.datetime.now(datetime.timezone.utc)
    row = Experiment(
        user_id=user_id,
        dimension=dimension,
        direction=direction,
        register=register,
        started_at=now,
        ends_at=now + EXPERIMENT_WINDOW,
        status="active",
    )
    db.session.add(row)
    db.session.flush()
    return _serialize(row)


def experiment_for_user(user_id: int, experiment_id: int) -> Optional[dict[str, Any]]:
    """One experiment, but only if it belongs to *user_id* -- the abandon
    route's 404-vs-someone-else's-row check (D-01's "indistinguishable from
    not existing" precedent, `solverah.errors.NotFoundError`)."""
    from model import Experiment

    row = Experiment.query.filter_by(id=experiment_id, user_id=user_id).first()
    return _serialize(row) if row is not None else None


def experiments_for_user(user_id: int) -> list[dict[str, Any]]:
    """Every experiment this user has ever started, newest first. Feeds both
    `GET /me/experiments` and account export -- unbounded, same reasoning
    `pulse_store.pulse_checkin_history`'s own docstring gives: a history read is
    a different question from "what applies right now", and truncating it
    silently would read a real, short history as if it were missing data."""
    from model import Experiment

    rows = (
        Experiment.query.filter_by(user_id=user_id)
        .order_by(Experiment.created_at.desc(), Experiment.id.desc())
        .all()
    )
    return [_serialize(row) for row in rows]


def abandon_experiment(db, user_id: int, experiment_id: int) -> Optional[dict[str, Any]]:
    """Move one experiment to `abandoned`, or return it unchanged if it already
    is -- the idempotence the route promises. None if it does not exist or is
    not this user's, so the caller can answer 404.

    Does NOT commit -- same convention as `start_experiment`.
    """
    from model import Experiment

    row = Experiment.query.filter_by(id=experiment_id, user_id=user_id).first()
    if row is None:
        return None
    if row.status != "abandoned":
        row.status = "abandoned"
        row.abandoned_at = datetime.datetime.now(datetime.timezone.utc)
        db.session.flush()
    return _serialize(row)


def checkin_experienced_values(
    user_id: int, *, started_at: datetime.datetime, ends_at: datetime.datetime
) -> tuple[list[int], list[int]]:
    """The two windows `work_pulse.experiments.compute_readout` compares:
    `experienced` values from check-ins in the 14 days strictly before
    `started_at`, and from check-ins in `[started_at, ends_at]`.

    The two windows are disjoint by construction: `pulse_store.pulse_checkin_history`'s
    bounds are inclusive, so a check-in landing exactly on `started_at` would
    otherwise count on both sides. It is excluded from the "before" list here
    (`< started_at`, not `<=`) and left in the "after" one, matching the
    literal `[started_at, ends_at]` the readout is defined over.
    """
    import pulse_store

    before = pulse_store.pulse_checkin_history(
        user_id, since=started_at - EXPERIMENT_WINDOW, until=started_at
    )
    after = pulse_store.pulse_checkin_history(user_id, since=started_at, until=ends_at)

    before_values = [
        checkin["experienced"]
        for checkin in before
        if checkin["taken_at"] is not None
        and datetime.datetime.fromisoformat(checkin["taken_at"]) < started_at
    ]
    after_values = [checkin["experienced"] for checkin in after]
    return before_values, after_values
