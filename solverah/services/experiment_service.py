"""Condition experiments: the API-facing orchestration (BUILD_PLAN B-5).

Wires `experiment_store.py`'s persistence to `work_pulse.experiments`'s pure
phase/readout logic and to `work_pulse.situation_content`'s guidance cells,
which is where an experiment's own `experiment_name` and the "is this pair a
real cell" check both come from. Raises `solverah.errors` types, per
`solverah/services/__init__.py`'s convention -- new code with no legacy
`{"error": ...}` history to match, the same reasoning `pulse_service.py` gives
for doing the same.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List

from sqlalchemy.exc import IntegrityError

from model import User, db
from solverah.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "abandon_experiment",
    "list_experiments",
    "start_experiment",
]


def _direction_to_content(direction: Any) -> "str | None":
    """`work_pulse.situation`'s short direction vocabulary (the one a
    `StrainDimensionEntry` already carries) -> `work_pulse.situation_content`'s
    longer one (the one `GUIDANCE_CELLS` is keyed on). `None` for anything
    else, which fails the cell-pair check below by simply not being a key
    `GUIDANCE_CELLS` recognizes."""
    from work_pulse import situation_content

    if not isinstance(direction, str):
        return None
    return {"under": situation_content.UNDER_SUPPLIED, "over": situation_content.OVER_SUPPLIED}.get(
        direction
    )


def _require_dict(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError(detail="body must be an object")
    return payload


def _require_change_in_place_cell(dimension: Any, direction: Any) -> None:
    """422 unless `(dimension, direction)` names one of the twelve real
    `change_in_place` cells -- a business question
    (`work_pulse.situation_content.GUIDANCE_CELLS`), not merely a type check.
    """
    from work_pulse import situation_content

    # `dimension` must be hashable before it can even be tried as a dict key --
    # a non-string payload value (a list, say) would otherwise raise TypeError
    # here instead of the 422 this function exists to give.
    key = (dimension, _direction_to_content(direction), situation_content.CHANGE_IN_PLACE)
    if not isinstance(dimension, str) or key not in situation_content.GUIDANCE_CELLS:
        raise ValidationError(
            detail=(
                "dimension/direction must name one of the twelve change-in-place "
                "cells the Situation Report can diagnose."
            ),
            errors=[{"field": "dimension", "code": "not_a_change_in_place_cell"}],
        )


def _experiment_name(dimension: str, direction: str) -> str:
    from work_pulse import situation_content

    content_direction = _direction_to_content(direction)
    cell = situation_content.GUIDANCE_CELLS[(dimension, content_direction, situation_content.CHANGE_IN_PLACE)]
    return cell["experiment_name"]


def _enrich_all(user_id: int, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add the three things `experiment_store`'s row never carries: the
    derived `phase`, the before/after `readout`, and the cell's own
    `experiment_name` -- for every row of one user's experiments, reading that
    user's check-ins once for all of them
    (`experiment_store.experienced_values_by_window`) rather than twice per row."""
    import experiment_store
    from work_pulse import experiments as experiment_engine

    windows = [
        (
            datetime.datetime.fromisoformat(row["started_at"]),
            datetime.datetime.fromisoformat(row["ends_at"]),
        )
        for row in rows
    ]
    values = experiment_store.experienced_values_by_window(user_id, windows)

    enriched = []
    for row, (_started_at, ends_at), (before_values, after_values) in zip(rows, windows, values):
        now = datetime.datetime.now(datetime.timezone.utc)
        readout = experiment_engine.compute_readout(before_values, after_values)
        phase = experiment_engine.derive_phase(row["status"], ends_at, now)

        # `user_id` is always the caller's own (the route resolves it from the JWT),
        # `created_at` is bookkeeping the wire has no use for, and `register` is
        # always `"change_in_place"` today (`model.Experiment`'s docstring) with no
        # UI that renders any other value -- all three dropped, the same reasoning
        # `pulse_service._drop_user_id` gives for its own field.
        enriched.append(
            {
                **{k: v for k, v in row.items() if k not in ("user_id", "created_at", "register")},
                "phase": phase,
                "readout": readout,
                "experiment_name": _experiment_name(row["dimension"], row["direction"]),
            }
        )
    return enriched


def _enrich(row: Dict[str, Any]) -> Dict[str, Any]:
    """`_enrich_all` for one row."""
    return _enrich_all(row["user_id"], [row])[0]


def _already_active() -> ConflictError:
    return ConflictError(
        detail="An experiment is already running -- finish or abandon it first.",
        errors=[{"field": "experiment", "code": "experiment_already_active"}],
    )


def _lost_the_one_active_race(exc: IntegrityError) -> bool:
    """Whether *exc* is `experiment_store.ONE_ACTIVE_INDEX` refusing a second
    active experiment -- and not some other constraint, which stays a 500."""
    import experiment_store

    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == experiment_store.ONE_ACTIVE_INDEX


def start_experiment(user: User, payload: Any) -> Dict[str, Any]:
    """``POST /me/experiments``. 422 for a bad cell, 409
    (``errors[0].code == "experiment_already_active"``) if one is already
    running -- the methodological one-at-a-time rule
    (``model.Experiment``'s docstring).

    The same 409 when this start loses a race: another start for this user
    commits between the check below and this INSERT, and the one-active index
    refuses the second row. Nothing else has been written in this transaction
    by then (the check is a read), so rolling it back loses nothing.
    """
    import experiment_store

    payload = _require_dict(payload)
    dimension = payload.get("dimension")
    direction = payload.get("direction")
    _require_change_in_place_cell(dimension, direction)

    if experiment_store.active_experiment(user.id) is not None:
        raise _already_active()

    try:
        row = experiment_store.start_experiment(
            db, user.id, dimension=dimension, direction=direction
        )
        db.session.commit()
    except IntegrityError as exc:
        if not _lost_the_one_active_race(exc):
            raise
        db.session.rollback()
        raise _already_active() from exc
    return _enrich(row)


def list_experiments(user: User) -> Dict[str, Any]:
    """``GET /me/experiments``. Newest first, each enriched with phase,
    readout, and the cell's own name -- at most two queries (the experiments,
    then their check-ins) however many experiments there are."""
    import experiment_store

    rows = experiment_store.experiments_for_user(user.id)
    return {"experiments": _enrich_all(user.id, rows)}


def abandon_experiment(user: User, experiment_id: int) -> Dict[str, Any]:
    """``POST /me/experiments/{id}/abandon``. Idempotent: abandoning an
    already-abandoned experiment is a 200 with the row unchanged, not an
    error. 404 (never a bare failure) if the id does not exist or belongs to
    someone else -- indistinguishable on purpose (`solverah.errors.NotFoundError`)."""
    import experiment_store

    row = experiment_store.abandon_experiment(db, user.id, experiment_id)
    if row is None:
        raise NotFoundError(detail="No experiment with that id.")
    db.session.commit()
    return _enrich(row)
