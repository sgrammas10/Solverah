"""Schemas for the Pulse surface (BUILD_PLAN B-2).

`PulseCheckinRecord`/`PulseEventRecord` mirror `pulse_store.py`'s own
`_serialize_checkin`/`_serialize_event` shape rather than the write responses
below by coincidence -- `GET /me/pulse/history` returns exactly what those
serializers produce, so the schema is the serializer's contract made explicit.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "PulseCadenceResponse",
    "PulseCadenceUpdateRequest",
    "PulseCheckinItem",
    "PulseCheckinRecord",
    "PulseCheckinRequest",
    "PulseCheckinResponse",
    "PulseEventRecord",
    "PulseEventRequest",
    "PulseEventResponse",
    "PulseHistoryQuery",
    "PulseHistoryResponse",
    "PulseNextCheckinResponse",
    "PulseOutcomeItem",
]


class PulseCheckinRequest(SolverahModel):
    item_scores: Dict[str, int] = Field(
        description=(
            "Exactly the dimensions work_pulse.pulse_items.dimensions_for_checkin "
            "served for this user's next sequence, each answered 1..5. The server "
            "derives which dimensions that is -- posting a different set, or a score "
            "outside 1..5, is refused (422)."
        )
    )
    experienced: int = Field(
        ge=1,
        le=5,
        description="pulse-experienced: 'This week, how well is work working for you?'",
    )


class PulseCheckinResponse(SolverahModel):
    """``POST /me/pulse/checkins`` -- an echo of what was recorded, like
    `EnvironmentReportSubmitResponse`: a Pulse answer already IS its own score,
    so there is nothing derived to add."""

    id: int
    sequence: int
    taken_at: Optional[str] = None
    item_scores: Dict[str, int]
    experienced: int
    version: str


class PulseCheckinRecord(SolverahModel):
    """One check-in as ``GET /me/pulse/history`` lists it."""

    id: int
    taken_at: Optional[str] = None
    sequence: int
    item_scores: Dict[str, int]
    experienced: int
    version: str


class PulseEventRequest(SolverahModel):
    event_type: Literal["new_manager", "reorg", "remote_change", "role_change", "other"]
    note: Optional[str] = Field(
        default=None,
        max_length=280,
        description=(
            "Optional short context, mainly for 'other'. "
            "model.PULSE_EVENT_NOTE_MAX_LENGTH caps it at 280 characters."
        ),
    )


class PulseEventResponse(SolverahModel):
    id: int
    at: Optional[str] = None
    event_type: str
    note: Optional[str] = None


class PulseEventRecord(SolverahModel):
    """One event as ``GET /me/pulse/history`` lists it -- the same shape as
    `PulseEventResponse`, named separately because the two responses document
    different endpoints."""

    id: int
    at: Optional[str] = None
    event_type: str
    note: Optional[str] = None


class PulseHistoryQuery(SolverahModel):
    """Query parameters for ``GET /me/pulse/history``."""

    model_config = ConfigDict(extra="ignore")

    since: Optional[str] = Field(
        default=None, description="ISO-8601 datetime, inclusive lower bound on taken_at/at."
    )
    until: Optional[str] = Field(
        default=None, description="ISO-8601 datetime, inclusive upper bound on taken_at/at."
    )
    limit: Optional[int] = Field(
        default=None,
        description="Max check-ins returned, clamped 1..100. Unbounded when absent. "
        "Events are never limited.",
    )


class PulseHistoryResponse(SolverahModel):
    checkins: List[PulseCheckinRecord]
    events: List[PulseEventRecord]


class PulseCheckinItem(SolverahModel):
    item_id: str
    dimension: str
    stem: str
    low_anchor: str
    high_anchor: str


class PulseOutcomeItem(SolverahModel):
    item_id: str
    stem: str
    low_anchor: str
    high_anchor: str


class PulseNextCheckinResponse(SolverahModel):
    """``GET /me/pulse/next-checkin`` -- `work_pulse.pulse_items.render_checkin`'s
    shape verbatim: server-derived and FORM_VERSION-stamped, so a client always
    knows which three dimensions (plus the outcome item) to render next without
    computing the round-robin itself."""

    sequence: int
    version: str
    items: List[PulseCheckinItem]
    experienced_item: PulseOutcomeItem


class PulseCadenceResponse(SolverahModel):
    """``GET``/``PATCH /me/pulse/settings`` -- one shape for both, because the
    client caches the PATCH echo as the GET value."""

    cadence: Literal["weekly", "biweekly", "monthly", "off"] = Field(
        description="The four cadences, all of them user-settable."
    )
    auto_slowed: bool = Field(
        description=(
            "True only when the anti-nag auto-drop moved this user to 'monthly' on its "
            "own. A user who chose 'monthly' is False. Gates the 'we've slowed these "
            "down' note, which belongs only to the state the server chose."
        )
    )


class PulseCadenceUpdateRequest(SolverahModel):
    cadence: Literal["weekly", "biweekly", "monthly", "off"] = Field(
        description="The four cadences a user can choose. 'off' is always this one call."
    )
