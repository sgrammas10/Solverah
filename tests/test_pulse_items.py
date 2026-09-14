"""Tests for work_pulse/pulse_items.py (BUILD_PLAN B-1): the item bank and the
round-robin selection. Pure functions, no Flask, no DB -- these tests import the
module directly and never touch `client`/`seed_user`.
"""

import pytest

from work_pulse.pulse_items import (
    DIMENSIONS,
    EXPECTED_DIMENSION_ITEM_COUNT,
    EXPERIENCED_ITEM,
    FORM_VERSION,
    ITEMS_PER_CHECKIN,
    PULSE_ITEMS,
    SCALE_MAX,
    SCALE_MIN,
    STEM_MAX_LENGTH,
    dimensions_for_checkin,
    is_valid_score,
    items_for_checkin,
    render_checkin,
)


# ---------------------------------------------------------------------------
# Item bank structure
# ---------------------------------------------------------------------------


def test_five_dimensions_are_covered_exactly_once_each():
    assert len(DIMENSIONS) == 5
    assert len(PULSE_ITEMS) == EXPECTED_DIMENSION_ITEM_COUNT == 5
    assert {item["dimension"] for item in PULSE_ITEMS} == set(DIMENSIONS)


def test_dimensions_match_insight_engine_question_dimensions():
    """B-1's read-first: `insight_engine.QUESTION_DIMENSIONS`'s five values are the
    dimensions this instrument is built on. A rename on either side that the other
    doesn't follow is exactly what this test exists to catch."""
    from work_pulse.insight_engine import QUESTION_DIMENSIONS

    assert set(DIMENSIONS) == set(QUESTION_DIMENSIONS.values())


def test_item_ids_are_unique():
    ids = [item["item_id"] for item in PULSE_ITEMS]
    assert len(ids) == len(set(ids))
    assert EXPERIENCED_ITEM["item_id"] not in ids


@pytest.mark.parametrize("item", PULSE_ITEMS, ids=[i["item_id"] for i in PULSE_ITEMS])
def test_every_dimension_item_has_both_anchors_and_a_short_stem(item):
    assert item["stem"].strip() == item["stem"]
    assert item["stem"].endswith("?")
    assert len(item["stem"]) <= STEM_MAX_LENGTH
    assert item["low_anchor"] and item["high_anchor"]
    assert item["low_anchor"] != item["high_anchor"]


def test_experienced_item_is_short_and_has_both_anchors():
    assert len(EXPERIENCED_ITEM["stem"]) <= STEM_MAX_LENGTH
    assert EXPERIENCED_ITEM["low_anchor"] != EXPERIENCED_ITEM["high_anchor"]
    assert EXPERIENCED_ITEM["stem"] == "This week, how well is work working for you?"


def test_form_version_is_exported_like_situation_items():
    assert isinstance(FORM_VERSION, str) and FORM_VERSION


# ---------------------------------------------------------------------------
# Scale validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [1, 2, 3, 4, 5])
def test_valid_scores_are_accepted(value):
    assert is_valid_score(value) is True


@pytest.mark.parametrize("value", [0, 6, -1, 3.0, "3", None, True, False])
def test_invalid_scores_are_rejected(value):
    assert is_valid_score(value) is False


def test_scale_bounds_are_one_to_five():
    assert (SCALE_MIN, SCALE_MAX) == (1, 5)


# ---------------------------------------------------------------------------
# Round-robin selection
# ---------------------------------------------------------------------------


def test_dimensions_for_checkin_serves_three_distinct_known_dimensions():
    dims = dimensions_for_checkin(user_id=1, sequence=0)
    assert len(dims) == ITEMS_PER_CHECKIN == 3
    assert len(set(dims)) == 3
    assert set(dims) <= set(DIMENSIONS)


def test_negative_sequence_is_rejected():
    with pytest.raises(ValueError, match="sequence"):
        dimensions_for_checkin(user_id=1, sequence=-1)


def test_selection_is_deterministic_for_the_same_user_and_sequence():
    first = dimensions_for_checkin(user_id=42, sequence=3)
    second = dimensions_for_checkin(user_id=42, sequence=3)
    assert first == second


def test_selection_takes_no_clock_so_a_missed_week_cannot_skip_a_dimension():
    """BUILD_PLAN B-1: "a missed week doesn't skip a dimension forever". The
    mechanism is structural, not behavioural: `dimensions_for_checkin` accepts only
    `user_id` and `sequence` -- no date, no "weeks since last check-in" -- so there is
    no calendar-time input a missed week could ever perturb. What decides the next
    `sequence` is `pulse_store.pulse_checkin_count` (a count of completed rows), which
    `tests/test_pulse_store.py::test_sequence_advances_by_completed_checkins_not_by_elapsed_time`
    proves does not move while a user is away."""
    import inspect

    params = list(inspect.signature(dimensions_for_checkin).parameters)
    assert params == ["user_id", "sequence"]


def test_every_dimension_served_equally_often_over_one_full_cycle():
    """The exact-fairness proof from the module docstring: over `len(DIMENSIONS)`
    consecutive sequences, every dimension is served exactly `ITEMS_PER_CHECKIN` times,
    because `ITEMS_PER_CHECKIN` and `len(DIMENSIONS)` are coprime."""
    from collections import Counter

    counts = Counter()
    for sequence in range(len(DIMENSIONS)):
        counts.update(dimensions_for_checkin(user_id=0, sequence=sequence))

    assert set(counts) == set(DIMENSIONS)
    assert all(count == ITEMS_PER_CHECKIN for count in counts.values())


@pytest.mark.parametrize("user_id", [0, 1, 2, 3, 4, 5, 99, 123456])
def test_fairness_holds_for_every_user_phase(user_id):
    """The per-user phase shift must not break the fairness guarantee for any user --
    it only changes WHICH cycle position a user starts on."""
    from collections import Counter

    counts = Counter()
    for sequence in range(len(DIMENSIONS)):
        counts.update(dimensions_for_checkin(user_id=user_id, sequence=sequence))

    assert set(counts) == set(DIMENSIONS)
    assert all(count == ITEMS_PER_CHECKIN for count in counts.values())


def test_different_users_can_get_different_starting_dimensions():
    """The phase shift's whole purpose: two users should not be locked in step on
    their very first check-in."""
    first_ever = {
        user_id: dimensions_for_checkin(user_id=user_id, sequence=0)
        for user_id in range(len(DIMENSIONS))
    }
    assert len(set(first_ever.values())) > 1


def test_items_for_checkin_matches_dimensions_for_checkin():
    dims = dimensions_for_checkin(user_id=5, sequence=2)
    items = items_for_checkin(user_id=5, sequence=2)
    assert tuple(item["dimension"] for item in items) == dims


def test_render_checkin_serves_three_items_plus_experienced_last():
    rendered = render_checkin(user_id=9, sequence=0)
    assert rendered["sequence"] == 0
    assert rendered["version"] == FORM_VERSION
    assert len(rendered["items"]) == ITEMS_PER_CHECKIN
    assert rendered["experienced_item"]["item_id"] == EXPERIENCED_ITEM["item_id"]
    # experienced_item is a distinct key, not appended into the items list --
    # it is always asked, never round-robin, so it must never look like a fourth
    # served dimension item.
    assert all("item_id" in item for item in rendered["items"])
    assert EXPERIENCED_ITEM["item_id"] not in {i["item_id"] for i in rendered["items"]}


def test_render_checkin_returns_plain_dicts_not_shared_mutable_state():
    """A caller mutating the returned dict must not corrupt the module's own item
    bank for the next caller."""
    rendered = render_checkin(user_id=1, sequence=0)
    rendered["items"][0]["stem"] = "mutated"
    fresh = render_checkin(user_id=1, sequence=0)
    assert fresh["items"][0]["stem"] != "mutated"
