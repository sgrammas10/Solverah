"""Schemas for the Situation Report surface (BUILD_PLAN A-5).

`SituationReportResponse` is open (``extra="allow"``) for the same reason
`ManagerPlaybook` is: the payload's shape genuinely varies by `state` (`needs_core`
carries `environment`, `needs_environment_report` carries
`can_submit_environment_report`, `complete` carries `dimensions`,
`guidance_notice`, `events_since_report` -- BUILD_PLAN B-4's Pulse-event
resubmission prompt, `{'type', 'date'}` per event, never a `note` --
`career_status_changed`, the live-vs-snapshot tense flag, and `tolerance_applied`,
with `must_have` and `within_tolerance` on each dimension; `needs_core` may carry
`core_unreadable`), and a closed
model over the union would either flatten every field to `Any` or lie about
which state guarantees which key. `state`, `manager` and `past_job_report_filed`
are the three keys every state carries, so they are the three this module declares.
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

#: `model.ENV_REPORT_SUBJECTS` (PRODUCT_DECISIONS.md §2, 2026-10-01).
Subject = Literal["current", "past"]


def _outcome_field(question: str):
    """One optional exploratory outcome (PRODUCT_DECISIONS.md §2, 2026-10-13):
    `work_pulse.situation_items.OUTCOME_ITEMS`, asked after `experienced`."""
    return Field(
        default=None,
        ge=1,
        le=5,
        description=(
            "Optional exploratory outcome, 1..5, stored raw: '%s' Null or absent means "
            "skipped." % question
        ),
    )


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
    satisfaction: Optional[int] = _outcome_field("All things considered, how satisfied are you with this job?")
    performance: Optional[int] = _outcome_field("How well do you think you are performing in this role?")
    engagement: Optional[int] = _outcome_field("How energised are you by the work itself?")
    sustainability: Optional[int] = _outcome_field("Could you keep working the way you do now for another year?")
    retention_intention: Optional[int] = _outcome_field(
        "How likely is it that you will still be in this role a year from now?"
    )
    employer_name: Optional[str] = Field(
        default=None,
        description="Optional, displayed nowhere at launch (⚑6) -- stored for a future aggregation lane.",
    )
    subject: Subject = Field(
        default="current",
        description=(
            "Which job this report describes: 'current' (the default -- the current or "
            "most recent job) or 'past' (the one job before that). A past report is "
            "accepted once per user, only after a current report exists, and never for "
            "first_job; it never changes the Situation Report."
        ),
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
    subject: Subject
    satisfaction: Optional[int] = None
    performance: Optional[int] = None
    engagement: Optional[int] = None
    sustainability: Optional[int] = None
    retention_intention: Optional[int] = None


class SituationReportResponse(SolverahModel):
    """``GET /me/situation-report``. See the module docstring for why this is open."""

    model_config = ConfigDict(extra="allow")

    state: str = Field(
        description="One of 'needs_core', 'needs_environment_report', 'complete'."
    )
    manager: Dict[str, Any] = Field(
        description="{'has_profile': bool} -- link-or-prompt to the Manager Decoder."
    )
    past_job_report_filed: bool = Field(
        description=(
            "Whether the user has filed their one past-job environment report "
            "(subject 'past'). Present in every state; a past report never changes "
            "anything else in this response."
        )
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
