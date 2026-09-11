"""The Pulse check-in instrument: item bank + round-robin selection (BUILD_PLAN B-1).

Five dimensions, `insight_engine.QUESTION_DIMENSIONS`'s own keys and order (the teaser
this instrument grows out of), plus the model's outcome node, `experienced`. Unlike
`situation_items.py`'s twelve-item, two-per-dimension instrument -- built for one
unhurried sitting -- this one is built for a recurring, 60-SECOND HARD BUDGET check-in
(PRODUCT_DECISIONS.md §2, "The Pulse ships thin"): one short, single-clause stem per
dimension, a plain 1..5 anchored scale with only the two endpoints worded, and never
all five dimensions in one sitting -- `dimensions_for_checkin` serves three, round-robin,
so a user answers the whole bank over roughly two check-ins rather than one long one.

Every stem is worded so **higher always means better** (5 = the good end), the same
polarity as `experienced`'s own scale. `situation_items.py` alternates anchor order
within a dimension on purpose (a two-item, single-sitting instrument, where a
straight-line respondent is a bias risk worth defending against by construction); a
recurring one-item-per-dimension check-in has no second item to alternate against, so
holding one consistent polarity across all five items instead removes a rotate-the-scale
step from a flow that is trying to be fast, at the cost of no defense against a
straight-lining respondent -- an acceptable trade only because straight-lining a
36-second check-in loses far less than straight-lining a full assessment would (see
`PULSE_ITEMS_BIAS_REVIEW.md`).

Pure: no Flask, no DB, no clock, no randomness, no I/O of any kind. Importable by
anything. Storage lives in `pulse_store.py`; nothing here writes a row.
"""
from __future__ import annotations

from typing import TypedDict

#: `insight_engine.QUESTION_DIMENSIONS`'s five values, in that dict's own key order
#: (wpll-q1..q5). Kept identical rather than renamed so a future reconciliation between
#: the teaser and the real Pulse (if one is ever wanted) is a lookup, not a translation.
DIMENSIONS: tuple[str, ...] = (
    "fragmentation",
    "sustainability",
    "environmental_friction",
    "recognition_friction",
    "work_pace",
)

#: How many of the five dimensions one check-in serves. Three rather than five is the
#: 60-second budget's actual mechanism -- five single-clause items plus `experienced`
#: still reads as "one more thing" to a recurring visitor, three does not.
ITEMS_PER_CHECKIN = 3

#: `EnvironmentReport.version` / `AssessmentSubmission.form_version`'s role, under the
#: name this instrument's storage column uses (`pulse_checkins.version`).
FORM_VERSION = "pulse-v1-2026-09-11"

#: The answer scale every item in this module shares -- dimension items and
#: `EXPERIENCED_ITEM` alike. A plain int, not a JSONB pole map like
#: `situation_items.POLE_VALUES`: there is no derived scoring pass here, the answer a
#: user gives IS the stored score (`pulse_store.write_pulse_checkin` persists it
#: unmodified), so the module has nothing to map an answer token through.
SCALE_MIN = 1
SCALE_MAX = 5

#: A stem must fit on one line of a check-in that is trying to be answerable in 60
#: seconds. This is a proxy, not a real timing measurement (nothing in this module
#: can measure how long a person actually takes) -- see the bias review's "60-second
#: budget" note for the honest caveat that ships alongside it.
STEM_MAX_LENGTH = 70


class PulseItem(TypedDict):
    item_id: str
    dimension: str
    stem: str
    low_anchor: str
    high_anchor: str


class OutcomeItem(TypedDict):
    item_id: str
    stem: str
    low_anchor: str
    high_anchor: str


# ---------------------------------------------------------------------------
# The five dimension items -- one per dimension, single clause, both anchors named
# ---------------------------------------------------------------------------
# Wording discipline (PULSE_ITEMS_BIAS_REVIEW.md):
#   * No item implies that checking in more often, or reporting a problem, is virtuous
#     or expected -- the anti-nag decision (PRODUCT_DECISIONS.md §2, "The Pulse ships
#     thin") extends to wording, not just to cadence.
#   * `recognition_friction` is worded behaviourally ("got real notice") rather than
#     emotionally ("felt valued") to blunt some of the social-desirability pull a
#     feelings question about being appreciated invites -- see the bias review, which
#     is explicit that this reduces rather than removes it.
PULSE_ITEMS: list[PulseItem] = [
    {
        "item_id": "pulse-fragmentation-1",
        "dimension": "fragmentation",
        "stem": "How well could you focus without interruption this week?",
        "low_anchor": "Constantly pulled away",
        "high_anchor": "Stayed focused",
    },
    {
        "item_id": "pulse-sustainability-1",
        "dimension": "sustainability",
        "stem": "How sustainable did this week's workload feel?",
        "low_anchor": "Draining",
        "high_anchor": "Comfortable",
    },
    {
        "item_id": "pulse-environmental_friction-1",
        "dimension": "environmental_friction",
        "stem": "How much did your surroundings help you do good work?",
        "low_anchor": "Worked against you",
        "high_anchor": "Worked for you",
    },
    {
        "item_id": "pulse-recognition_friction-1",
        "dimension": "recognition_friction",
        "stem": "How much of your work got real notice this week?",
        "low_anchor": "Went unnoticed",
        "high_anchor": "Got noticed",
    },
    {
        "item_id": "pulse-work_pace-1",
        "dimension": "work_pace",
        "stem": "How well did this week's pace match what works for you?",
        "low_anchor": "Badly mismatched",
        "high_anchor": "Matched well",
    },
]

#: The model's outcome node, asked every check-in (never round-robin) -- BUILD_PLAN
#: B-1's exact wording. Last in the served set, same reasoning as
#: `situation_items.EXPERIENCED_ITEM`: the one evaluative item comes after the
#: descriptive ones so its verdict cannot prime them.
EXPERIENCED_ITEM: OutcomeItem = {
    "item_id": "pulse-experienced",
    "stem": "This week, how well is work working for you?",
    "low_anchor": "Not working",
    "high_anchor": "Working very well",
}

EXPECTED_DIMENSION_ITEM_COUNT = len(PULSE_ITEMS)

_ITEMS_BY_DIMENSION: dict[str, PulseItem] = {item["dimension"]: item for item in PULSE_ITEMS}
_ITEMS_BY_ID: dict[str, PulseItem] = {item["item_id"]: item for item in PULSE_ITEMS}


# ---------------------------------------------------------------------------
# Round-robin selection
# ---------------------------------------------------------------------------


def dimensions_for_checkin(user_id: int, sequence: int) -> tuple[str, ...]:
    """The `ITEMS_PER_CHECKIN` dimensions this user's `sequence`-th check-in serves.

    `sequence` counts this user's own COMPLETED check-ins (0 for their first,
    1 for their second, ...) -- never a calendar week number. That is what makes a
    missed week harmless: nothing here reads a clock, so a gap in calendar time does
    not advance `sequence` and does not skip any dimension. `pulse_store.py`'s
    `pulse_checkin_count` is the sanctioned way a caller turns "how many check-ins has
    this user completed" into the next `sequence` to serve.

    **Coverage, proven exactly rather than approximately.** `ITEMS_PER_CHECKIN` (3) and
    `len(DIMENSIONS)` (5) are coprime, so walking `DIMENSIONS` in fixed order with a
    start index that advances by `ITEMS_PER_CHECKIN` each `sequence` visits every
    starting position exactly once before repeating, with period `len(DIMENSIONS)`.
    Over any `len(DIMENSIONS)`-long run of consecutive sequences that starts on a
    period boundary, every dimension is therefore served exactly
    `ITEMS_PER_CHECKIN` times -- not approximately fair, exactly fair
    (`test_every_dimension_served_equally_often_over_one_full_cycle` proves the count).

    `user_id` sets a per-user PHASE (`user_id % len(DIMENSIONS)`) on top of the same
    cycle, not a different cycle -- every user still gets the exact-fairness guarantee
    above, but two users do not see the same three dimensions on their Nth check-in,
    which would otherwise clump the whole population's early answers onto the same
    dimensions at the same lifecycle point.
    """
    if sequence < 0:
        raise ValueError(f"sequence must be >= 0, got {sequence!r}")

    n = len(DIMENSIONS)
    phase = user_id % n
    start = (ITEMS_PER_CHECKIN * (sequence + phase)) % n
    return tuple(DIMENSIONS[(start + i) % n] for i in range(ITEMS_PER_CHECKIN))


def items_for_checkin(user_id: int, sequence: int) -> list[PulseItem]:
    """The `PulseItem` entries `dimensions_for_checkin` selected, in that order."""
    return [_ITEMS_BY_DIMENSION[dim] for dim in dimensions_for_checkin(user_id, sequence)]


def render_checkin(user_id: int, sequence: int) -> dict:
    """The check-in a form renderer (B-3) wants: the three served items plus the
    outcome item, in serve order, with `experienced` always last (see
    `EXPERIENCED_ITEM`'s docstring)."""
    items = items_for_checkin(user_id, sequence)
    return {
        "sequence": sequence,
        "version": FORM_VERSION,
        "items": [dict(item) for item in items],
        "experienced_item": dict(EXPERIENCED_ITEM),
    }


def is_valid_score(value: object) -> bool:
    """Whether `value` is a legal answer to any item in this bank -- an int in
    `[SCALE_MIN, SCALE_MAX]`. A `bool` is rejected even though Python's `bool` is an
    `int` subtype: `True`/`False` are never a legal 1..5 answer, and silently accepting
    one would store a 0 or a 1 that looks like a real low score.
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, int) and SCALE_MIN <= value <= SCALE_MAX
