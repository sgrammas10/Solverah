"""FocusType scoring — pure functions, no Flask, no LLM.

Translates 5 scene payloads into a FocusType archetype and workplace
recommendations.  All scoring rules come directly from FOCUSTYPE_SPEC.md.
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

DIMENSIONS = [
    "deep_focus",
    "burst_energy",
    "reactivity",
    "structure_need",
    "urgency_drive",
    "social_fuel",
]

# ---------------------------------------------------------------------------
# Scene 1 — The Morning Stack
# Card placed in positions 0 or 1 → dimension contributions.
# Spec: if both top-2 slots contribute to the same dimension, cap at +2.
# ---------------------------------------------------------------------------

_S1_CARD_SCORES: dict[str, dict[str, int]] = {
    "big_project":        {"deep_focus": 2},
    "planning_doc":       {"structure_need": 2},
    "urgent_client":      {"urgency_drive": 2},
    "teammate_feedback":  {"social_fuel": 2},
    "emails":             {"structure_need": 1, "reactivity": 1},
    "admin_tasks":        {"structure_need": 1, "reactivity": 1},
}


def _score_scene_1(scene_1: list[str]) -> dict[str, int]:
    totals: dict[str, int] = {d: 0 for d in DIMENSIONS}
    for card in scene_1[:2]:
        for dim, pts in _S1_CARD_SCORES.get(card, {}).items():
            totals[dim] = min(totals[dim] + pts, 2)  # cap per-dimension at +2
    return totals


# ---------------------------------------------------------------------------
# Scene 2 — The Inbox Flood
# ---------------------------------------------------------------------------

_S2_TEAMMATE_CARDS = {"slack_teammate_question", "slack_mentioned", "slack_team_channel"}
_S2_PLANNING_CARDS = {"calendar_meeting_invite", "task_planning_doc", "calendar_team_lunch"}
_S2_CLIENT_CARDS   = {"email_client_important"}


def _score_scene_2(scene_2: dict[str, list[str]]) -> dict[str, int]:
    now    = scene_2.get("now", [])
    later  = scene_2.get("later", [])
    ignore = scene_2.get("ignore", [])

    scores: dict[str, int] = {d: 0 for d in DIMENSIONS}
    now_set = set(now)

    if len(now) >= 5:
        scores["reactivity"] += 2
    if len(now) <= 3:
        scores["deep_focus"] += 2

    if now_set & _S2_TEAMMATE_CARDS:
        scores["social_fuel"] += 1
    if now_set & _S2_PLANNING_CARDS:
        scores["structure_need"] += 1
    if now_set & _S2_CLIENT_CARDS:
        scores["urgency_drive"] += 1

    # "Most items in IGNORE" — ignore bucket larger than both now and later
    if len(ignore) > len(now) and len(ignore) > len(later):
        scores["deep_focus"] += 1

    return scores


# ---------------------------------------------------------------------------
# Scene 3 — The Free Day
# ---------------------------------------------------------------------------

_S3_DIM_MAP: dict[str, str] = {
    "deep_solo": "deep_focus",
    "planning":  "structure_need",
    "social":    "social_fuel",
    "breaks":    "burst_energy",
    "exploring": "reactivity",
}


def _score_scene_3(scene_3: dict[str, float]) -> dict[str, int]:
    scores: dict[str, int] = {d: 0 for d in DIMENSIONS}
    valid = {k: v for k, v in scene_3.items() if k in _S3_DIM_MAP}
    if not valid:
        return scores

    ranked = sorted(valid.items(), key=lambda x: x[1], reverse=True)
    scores[_S3_DIM_MAP[ranked[0][0]]] += 2
    if len(ranked) >= 2:
        scores[_S3_DIM_MAP[ranked[1][0]]] += 1

    return scores


# ---------------------------------------------------------------------------
# Scene 4 — The 2:30 Crash
# ---------------------------------------------------------------------------

_S4_SOCIAL_CARDS  = {"reply_teammate", "quick_call_unblock", "review_others_work"}
_S4_DEEP_CARDS    = {"write_report_draft", "deep_research"}
_S4_PLANNING_CARDS = {"update_task_tracker", "sketch_tomorrow_plan"}

_S4_TOTAL_CARDS = 8
_S4_ALMOST_ALL_TOMORROW_THRESHOLD = 6  # 6+ of 8 in TOMORROW


def _score_scene_4(scene_4: dict) -> dict[str, int]:
    now     = set(scene_4.get("now", []))
    tomorrow = set(scene_4.get("tomorrow", []))
    # Average over the cards the user actually clicked. Timed-out cards are not
    # decisions and the client leaves them out; when every card timed out it
    # sends null, and a missing or null value is no timing signal at all --
    # neither rule below fires. (It used to arrive as 0, which read as the
    # fastest decider possible and handed a user who never clicked +1
    # reactivity.)
    avg_ms  = scene_4.get("avg_decision_time_ms")

    scores: dict[str, int] = {d: 0 for d in DIMENSIONS}

    if now & _S4_SOCIAL_CARDS:
        scores["social_fuel"] += 2
    if now & _S4_DEEP_CARDS:
        scores["deep_focus"] += 1
        scores["urgency_drive"] += 1
    if now & _S4_PLANNING_CARDS:
        scores["structure_need"] += 2

    if len(tomorrow) >= _S4_ALMOST_ALL_TOMORROW_THRESHOLD:
        scores["burst_energy"] += 2

    if avg_ms is not None:
        if avg_ms < 1500:
            scores["reactivity"] += 1
        if avg_ms >= 3000:
            scores["deep_focus"] += 1

    return scores


# ---------------------------------------------------------------------------
# Scene 5 — The Evening Build
# ---------------------------------------------------------------------------

def _score_scene_5(scene_5: list[str]) -> dict[str, int]:
    scores: dict[str, int] = {d: 0 for d in DIMENSIONS}
    if not scene_5:
        return scores

    leads_with = scene_5[0]

    if leads_with == "deep_work":
        scores["deep_focus"] += 2

    # Two sprint blocks with a break between them (positional order)
    if "focused_sprint" in scene_5 and "second_sprint" in scene_5 and "break" in scene_5:
        sprint_idx        = scene_5.index("focused_sprint")
        second_sprint_idx = scene_5.index("second_sprint")
        break_idx         = scene_5.index("break")
        if sprint_idx < break_idx < second_sprint_idx:
            scores["burst_energy"] += 2

    if leads_with == "planning":
        scores["structure_need"] += 2

    if "teammate_checkin" in scene_5:
        scores["social_fuel"] += 2

    if "break" not in scene_5:
        scores["urgency_drive"] += 1
        scores["deep_focus"] += 1

    if leads_with == "focused_sprint":
        scores["burst_energy"] += 1

    return scores


# ---------------------------------------------------------------------------
# Archetype mapping
# ---------------------------------------------------------------------------

_DIMENSION_TO_ARCHETYPE: dict[str, str] = {
    "deep_focus":    "Deep Diver",
    "burst_energy":  "Sprint & Reset",
    "reactivity":    "Reactive Flow",
    "structure_need": "Structured Builder",
    "urgency_drive": "Pressure Igniter",
    "social_fuel":   "Collaborative Charger",
}

_TIEBREAKER_PAIRS: dict[frozenset, str] = {
    frozenset({"deep_focus", "structure_need"}): "Structured Builder",
    frozenset({"deep_focus", "burst_energy"}):   "Deep Diver",
    frozenset({"reactivity", "social_fuel"}):    "Collaborative Charger",
    frozenset({"urgency_drive", "reactivity"}):  "Pressure Igniter",
    frozenset({"burst_energy", "urgency_drive"}): "Sprint & Reset",
}


def _determine_archetype(scores: dict[str, int]) -> str:
    max_score = max(scores.values())
    winners = [d for d, s in scores.items() if s == max_score]

    if len(winners) == 1:
        return _DIMENSION_TO_ARCHETYPE[winners[0]]

    if len(winners) == 2:
        pair = frozenset(winners)
        if pair in _TIEBREAKER_PAIRS:
            return _TIEBREAKER_PAIRS[pair]

    # Alphabetical fallback for any other tie
    winners.sort()
    return _DIMENSION_TO_ARCHETYPE[winners[0]]


# ---------------------------------------------------------------------------
# Workplace recommendations
# ---------------------------------------------------------------------------

_RECOMMENDATIONS: dict[str, list[str]] = {
    "Deep Diver": [
        "Block 3–4 hour focus windows every morning before meetings",
        "Work in environments with zero notifications — phone on Do Not Disturb",
        "Batch all async communication into 2 dedicated windows per day",
        "Avoid open-plan offices or hot-desking — you need a consistent, quiet space",
        "Best tools: time-blocking calendar, noise-cancelling headphones, single-tab browser sessions",
    ],
    "Sprint & Reset": [
        "Work in 25–45 minute focused sprints with 10-minute hard breaks in between",
        "Track your sprint count — aim for 4–6 quality sprints per day, not hours",
        "Don't fight fatigue — recovery is part of your output cycle, not a failure",
        "Avoid back-to-back meetings with no buffer time",
        "Best tools: Pomodoro timer, standing desk, walking breaks as hard resets",
    ],
    "Reactive Flow": [
        "Embrace a varied schedule — monotony kills your output",
        "Dynamic, communicative environments suit you better than silent ones",
        "You handle urgent requests without losing the thread — lean into that",
        "Rigid focus-block scheduling works against your natural rhythm",
        "Best tools: kanban board, quick-capture note app, always-on Slack",
    ],
    "Structured Builder": [
        "Spend 15–20 minutes each morning writing your plan before touching any task",
        "Protect your routine — unplanned changes cost you more energy than most people",
        "You do your best work when scope is clearly defined before you begin",
        "Avoid jumping between projects — close one before opening another",
        "Best tools: detailed task manager (Linear, Notion), weekly planning ritual, meeting agendas sent in advance",
    ],
    "Pressure Igniter": [
        "Use artificial deadlines even when real ones don't exist",
        "Time-box everything — open-ended tasks will stall you",
        "Break long projects into milestones with hard dates, even self-imposed ones",
        "Avoid fully unstructured free time on complex work — you need a starting gun",
        "Best tools: visible countdown timers, commitment devices, accountability partner check-ins",
    ],
    "Collaborative Charger": [
        "Schedule co-working sessions for your hardest tasks — presence helps you focus",
        "Working alone for long stretches drains rather than protects your energy",
        "You think better when you can talk through problems, even briefly",
        "Avoid fully async-only roles — you need some live interaction to sustain momentum",
        "Best tools: pair working calls, voice memos for thinking out loud, shared live docs",
    ],
}


# ---------------------------------------------------------------------------
# Payload shape checks
# ---------------------------------------------------------------------------
#
# The request schema accepts any JSON object or list per scene, so a body such
# as ``scene_2.now: 5`` reaches the scorers above, which would fail with a
# TypeError (a 500). These checks run first and turn such a body into a
# FocusTypePayloadError, which the service answers with a 400. They check shape
# only; unknown card ids still score nothing, as before.


class FocusTypePayloadError(ValueError):
    """A scene payload whose shape the scorers cannot read."""


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _require_str_list(value: Any, where: str) -> None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise FocusTypePayloadError("%s must be a list of strings" % where)


def _require_dict(value: Any, where: str) -> None:
    if not isinstance(value, dict):
        raise FocusTypePayloadError("%s must be an object" % where)


def validate_scenes(
    scene_1: Any, scene_2: Any, scene_3: Any, scene_4: Any, scene_5: Any
) -> None:
    """Raise FocusTypePayloadError if any scene has a shape the scorers cannot read."""
    _require_str_list(scene_1, "scene_1")

    _require_dict(scene_2, "scene_2")
    for bucket in ("now", "later", "ignore"):
        if bucket in scene_2:
            _require_str_list(scene_2[bucket], "scene_2.%s" % bucket)

    _require_dict(scene_3, "scene_3")
    for key in _S3_DIM_MAP:
        if key in scene_3 and not _is_number(scene_3[key]):
            raise FocusTypePayloadError("scene_3.%s must be a number" % key)

    _require_dict(scene_4, "scene_4")
    for bucket in ("now", "tomorrow"):
        if bucket in scene_4:
            _require_str_list(scene_4[bucket], "scene_4.%s" % bucket)
    avg_ms = scene_4.get("avg_decision_time_ms")
    if avg_ms is not None and not (_is_number(avg_ms) and avg_ms >= 0):
        raise FocusTypePayloadError(
            "scene_4.avg_decision_time_ms must be a non-negative number or null"
        )

    _require_str_list(scene_5, "scene_5")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_focus_type(
    scene_1: list[str],
    scene_2: dict[str, list[str]],
    scene_3: dict[str, float],
    scene_4: dict,
    scene_5: list[str],
) -> dict:
    """Score all 5 FocusType scenes and return archetype + recommendations.

    Args:
        scene_1: Card IDs in priority order (position 0 = top priority).
        scene_2: {"now": [...], "later": [...], "ignore": [...]} triage buckets.
        scene_3: {"deep_solo": hrs, "planning": hrs, "social": hrs,
                  "breaks": hrs, "exploring": hrs} — must sum to ~4.
        scene_4: {"now": [...], "tomorrow": [...],
                  "avg_decision_time_ms": int | None} -- None (or absent)
                  when the user clicked no card, which scores no timing.
        scene_5: Block IDs in timeline order.

    Returns:
        {"archetype": str, "dimension_scores": {dim: int}, "recommendations": [str]}

    Raises:
        FocusTypePayloadError: a scene's shape cannot be scored.
    """
    validate_scenes(scene_1, scene_2, scene_3, scene_4, scene_5)

    totals: dict[str, int] = {d: 0 for d in DIMENSIONS}

    for scene_scores in (
        _score_scene_1(scene_1),
        _score_scene_2(scene_2),
        _score_scene_3(scene_3),
        _score_scene_4(scene_4),
        _score_scene_5(scene_5),
    ):
        for dim, pts in scene_scores.items():
            totals[dim] += pts

    archetype = _determine_archetype(totals)

    return {
        "archetype": archetype,
        "dimension_scores": totals,
        "recommendations": _RECOMMENDATIONS[archetype],
    }
