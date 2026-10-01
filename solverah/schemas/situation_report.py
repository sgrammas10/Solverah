"""Schemas for the Situation Report surface (BUILD_PLAN A-5).

`SituationReportResponse` is open (``extra="allow"``) for the same reason
`ManagerPlaybook` is: the payload's shape genuinely varies by `state` (`needs_core`
carries `environment`, `needs_environment_report` carries
`can_submit_environment_report`, `complete` carries `dimensions`,
`guidance_notice` and `events_since_report` -- BUILD_PLAN B-4's Pulse-event
resubmission prompt, `{'type', 'date'}` per event, never a `note`), and a closed
model over the union would either flatten every field to `Any` or lie about
which state guarantees which key. `state` and `manager` are the two keys every
state carries, so they are the two this module declares.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "EnvironmentReportSubmitRequest",
    "EnvironmentReportSubmitResponse",
    "SituationReportRecalibrateResponse",
    "SituationReportResponse",
]

#: `work_pulse.situation_items.INDUSTRY_LEVELS`, spelled out so the OpenAPI document
#: carries an enum (a computed Literal is invisible to type checkers). A tripwire test
#: asserts the two agree.
Industry = Literal["tech", "finance", "healthcare", "retail", "other"]


class EnvironmentReportSubmitRequest(SolverahModel):
    answers: Dict[str, str] = Field(
        description=(
            "The twelve environment-dimension item ids -> chosen option key "
            "('a'..'e'), exactly (work_pulse.situation_items.ENVIRONMENT_ITEMS)."
        )
    )
    stage_size: int = Field(ge=1, le=5, description="1 (seed) .. 5 (enterprise).")
    comp: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="1..5 market-relative pay posture, or null for 'not sure'.",
    )
    industry: Optional[Industry] = Field(
        default=None,
        description=(
            "The organization's industry, one of the causal model's `industry` levels, "
            "or null (or absent) for 'not sure / prefer not to say'."
        ),
    )
    experienced: int = Field(
        ge=1, le=5, description="Overall, how well is this role working for you?"
    )
    employer_name: Optional[str] = Field(
        default=None,
        description="Optional, displayed nowhere at launch (⚑6) -- stored for a future aggregation lane.",
    )


class EnvironmentReportSubmitResponse(SolverahModel):
    """``POST /me/environment-report`` -- an echo of the user's own description of
    their job. Never a person-side score, per D-15: this is the environment side
    alone, with nothing yet to diff it against."""

    dimension_scores: Dict[str, float]
    stage_size: int
    comp: Optional[int] = None
    industry: Optional[Industry] = None
    experienced: int
    career_status: str
    version: str


class SituationReportResponse(SolverahModel):
    """``GET /me/situation-report``. See the module docstring for why this is open."""

    model_config = ConfigDict(extra="allow")

    state: str = Field(
        description="One of 'needs_core', 'needs_environment_report', 'complete'."
    )
    manager: Dict[str, Any] = Field(
        description="{'has_profile': bool} -- link-or-prompt to the Manager Decoder."
    )


class SituationReportRecalibrateResponse(SolverahModel):
    """``POST /me/situation-report/recalibrate``."""

    recalibrated: bool = Field(
        description=(
            "Whether the pin actually moved. False when already pinned to the "
            "latest completed core sitting -- the ⚑5 idempotence rule -- and "
            "nothing was written."
        )
    )
