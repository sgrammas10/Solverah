"""Schemas for condition experiments (BUILD_PLAN B-5).

`dimension`/`direction` are plain `str` on the request, not `Literal` over the
known vocabularies -- the same choice `EnvironmentReportSubmitRequest.answers`
makes for its item ids. Whether a pair names one of the twelve real
`change_in_place` cells is a business question
(`work_pulse.situation_content.GUIDANCE_CELLS`), not a wire-shape one, and
`solverah/services/experiment_service.py` is what answers it -- a distinct 422
from the schema-level one `enforce=True` already gives an outright malformed
body, the same split B-2's `pulse-checkin-malformed` capture pins for Pulse.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from . import SolverahModel

__all__ = [
    "ExperimentAbandonResponse",
    "ExperimentListResponse",
    "ExperimentReadout",
    "ExperimentRecord",
    "ExperimentStartRequest",
    "ExperimentStartResponse",
]


class ExperimentStartRequest(SolverahModel):
    dimension: str = Field(
        description="One of work_pulse.situation.DIMENSIONS ('autonomy', 'pace', …)."
    )
    direction: str = Field(
        description="'under' or 'over' -- work_pulse.situation's short vocabulary, "
        "the same one a StrainDimensionEntry's own `direction` field already carries."
    )


class ExperimentReadout(SolverahModel):
    """`work_pulse.experiments.compute_readout`'s output, unchanged. Never a
    delta or a mean -- see that module's docstring for why."""

    verdict: str = Field(
        description="One of 'not_enough_data', 'moved_up', 'moved_down', 'about_the_same'."
    )
    before_count: int = Field(description="Check-ins in the 14 days before started_at.")
    after_count: int = Field(description="Check-ins in [started_at, ends_at].")


class ExperimentRecord(SolverahModel):
    """One experiment, as `POST /me/experiments`, `GET /me/experiments`, and
    `POST /me/experiments/{id}/abandon` all return it."""

    id: int
    dimension: str
    direction: str
    started_at: str
    ends_at: str
    status: str = Field(
        description="'active', 'completed' or 'abandoned' -- the stored fact. "
        "'completed' is written once ends_at has passed, so an ended experiment "
        "never blocks the next start."
    )
    abandoned_at: Optional[str] = None
    phase: str = Field(
        description="'running' / 'ended' / 'abandoned' -- derived on read from "
        "status and ends_at, never stored."
    )
    experiment_name: str = Field(
        description="The cell's own name, resolved from work_pulse.situation_content."
    )
    readout: ExperimentReadout


class ExperimentStartResponse(ExperimentRecord):
    """``POST /me/experiments`` -- 201 with the new row."""


class ExperimentListResponse(SolverahModel):
    """``GET /me/experiments`` -- newest first."""

    experiments: list[ExperimentRecord]


class ExperimentAbandonResponse(ExperimentRecord):
    """``POST /me/experiments/{id}/abandon`` -- 200, idempotent."""
