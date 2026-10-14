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
mutates rather than appending, and `close_ended_experiments` moves `active`
rows past their `ends_at` to `completed`.

STATUS IS A STORED FACT WITH THREE VALUES; PHASE IS DERIVED FROM IT
--------------------------------------------------------------------
`active` / `completed` / `abandoned` (`STATUSES`). `completed` was added on
2026-10-02: until then a naturally ended experiment kept `status = 'active'`
forever, so `ONE_ACTIVE_INDEX` (partial on `status = 'active'`) and the
service's 409 check both kept refusing every later start, and no UI could
clear it. A time predicate cannot live in a partial index (`now()` is not
immutable), so the only way the index can keep being the race backstop is for
an ended row to stop being `active` -- hence a stored `completed`, written
lazily by `close_ended_experiments` on the service's reads and writes rather
than by a cron: nothing reads an experiment except the service, and a row
nobody reads can stay `active` without harm.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional, Sequence

__all__ = [
    "EXPERIMENT_WINDOW",
    "ONE_ACTIVE_INDEX",
    "STATUSES",
    "active_experiment",
    "checkin_experienced_values",
    "abandon_experiment",
    "close_ended_experiments",
    "experienced_values_by_window",
    "experiment_for_user",
    "experiments_for_user",
    "start_experiment",
]

#: The partial unique index behind the one-active-experiment rule
#: (`model.Experiment`), named so a caller can tell that refusal apart from any
#: other IntegrityError.
ONE_ACTIVE_INDEX = "uq_experiments_one_active_per_user"

#: The stored `status` vocabulary (`ck_experiment_status_vocab`).
STATUSES: tuple[str, ...] = ("active", "completed", "abandoned")

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
    on `experiments` (`ONE_ACTIVE_INDEX`) is what makes a race between two such
    checks lose at the database rather than double-book -- the service answers
    that loss with the same 409.
    """
    from model import Experiment

    row = Experiment.query.filter_by(user_id=user_id, status="active").first()
    return _serialize(row) if row is not None else None


def close_ended_experiments(db, user_id: int, *, now: datetime.datetime) -> int:
    """Move this user's `active` rows whose `ends_at` has passed to `completed`.
    Returns how many moved -- usually 0, since at most one row is ever active.

    The lazy half of the status design (module docstring): the service calls
    this before every read or write of a user's experiments, so an ended row
    never stays `active` into a 409 check. `ends_at <= now` is the same
    boundary `work_pulse.experiments.derive_phase` draws, with the caller's
    *now* rather than the database clock so one request cannot disagree with
    itself about whether an experiment has ended.

    Does NOT commit -- same convention as `start_experiment`. Idempotent: a
    second call finds nothing to move.
    """
    from model import Experiment

    moved = (
        Experiment.query.filter(
            Experiment.user_id == user_id,
            Experiment.status == "active",
            Experiment.ends_at <= now,
        ).update({"status": "completed"}, synchronize_session="fetch")
    )
    db.session.flush()
    return moved


def start_experiment(
    db, user_id: int, *, dimension: str, direction: str, register: str = "change_in_place"
) -> dict[str, Any]:
    """Write one experiment, `started_at` now and `ends_at` now + 14 days.

    Does NOT commit -- the caller owns the transaction boundary, same as
    `environment_report_store.write_environment_report`. Does not check for an
    already-active experiment; that is the service layer's job (the 409), with
    `ONE_ACTIVE_INDEX` as the backstop a race would otherwise slip through: the
    flush here raises its IntegrityError.
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
    """Move one `active` experiment to `abandoned`, or return it unchanged if
    it already is -- the idempotence the route promises. None if it does not
    exist or is not this user's, so the caller can answer 404.

    A `completed` row is returned unchanged too: an experiment that ran its
    two weeks has a readout, and relabelling it "Abandoned" would hide that
    readout behind a word that is not true of it. The service closes ended
    rows before calling this, so a click that lands after `ends_at` is a
    no-op rather than a relabel.

    Does NOT commit -- same convention as `start_experiment`.
    """
    from model import Experiment

    row = Experiment.query.filter_by(id=experiment_id, user_id=user_id).first()
    if row is None:
        return None
    if row.status == "active":
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

    The two windows are disjoint by construction: a check-in landing exactly on
    `started_at` is excluded from the "before" list (`< started_at`, not `<=`)
    and left in the "after" one, matching the literal `[started_at, ends_at]`
    the readout is defined over. One read -- `experienced_values_by_window` for
    a single window.
    """
    return experienced_values_by_window(user_id, [(started_at, ends_at)])[0]


def experienced_values_by_window(
    user_id: int, windows: Sequence[tuple[datetime.datetime, datetime.datetime]]
) -> list[tuple[list[int], list[int]]]:
    """`checkin_experienced_values` for each `(started_at, ends_at)` in *windows*,
    in order, from ONE read of this user's check-ins.

    The read covers `[min(started_at) - 14 days, max(ends_at)]` -- every window's
    "before" and "after" at once, inclusive at both ends as
    `pulse_store.pulse_checkin_history` always is -- and selects only `taken_at`
    and `experienced`. Each window is then cut from it in Python with exactly the
    boundaries the per-window reads drew: `[started_at - 14 days, started_at)`
    before, `[started_at, ends_at]` after, newest first within each. Listing N
    experiments is therefore one query rather than 2N. Nothing is read for an
    empty *windows*.
    """
    import pulse_store

    if not windows:
        return []

    since = min(started_at for started_at, _ in windows) - EXPERIMENT_WINDOW
    until = max(ends_at for _, ends_at in windows)
    checkins = [
        (datetime.datetime.fromisoformat(checkin["taken_at"]), checkin["experienced"])
        for checkin in pulse_store.pulse_checkin_history(
            user_id, since=since, until=until, columns=("taken_at", "experienced")
        )
    ]

    return [
        (
            [
                experienced
                for taken_at, experienced in checkins
                if started_at - EXPERIMENT_WINDOW <= taken_at < started_at
            ],
            [
                experienced
                for taken_at, experienced in checkins
                if started_at <= taken_at <= ends_at
            ],
        )
        for started_at, ends_at in windows
    ]
