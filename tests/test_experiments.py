"""Tests for the condition-experiments pure logic: readout words and phase
derivation (BUILD_PLAN B-5)."""
from __future__ import annotations

import datetime

from work_pulse.experiments import (
    ABANDONED,
    ABOUT_THE_SAME,
    ABOUT_THE_SAME_THRESHOLD,
    ENDED,
    MOVED_DOWN,
    MOVED_UP,
    NOT_ENOUGH_DATA,
    RUNNING,
    compute_readout,
    derive_phase,
)

# ---------------------------------------------------------------------------
# compute_readout
# ---------------------------------------------------------------------------


def test_not_enough_data_when_before_is_empty():
    result = compute_readout([], [4, 4, 5])
    assert result == {"verdict": NOT_ENOUGH_DATA, "before_count": 0, "after_count": 3}


def test_not_enough_data_when_after_is_empty():
    result = compute_readout([3, 3], [])
    assert result == {"verdict": NOT_ENOUGH_DATA, "before_count": 2, "after_count": 0}


def test_not_enough_data_on_both_empty_sides():
    result = compute_readout([], [])
    assert result == {"verdict": NOT_ENOUGH_DATA, "before_count": 0, "after_count": 0}


def test_moved_up_when_the_mean_rises_past_the_threshold():
    # before mean 2.0, after mean 4.0 -- delta +2.0, well past the threshold.
    result = compute_readout([2, 2], [4, 4])
    assert result["verdict"] == MOVED_UP
    assert result["before_count"] == 2
    assert result["after_count"] == 2


def test_moved_down_when_the_mean_falls_past_the_threshold():
    result = compute_readout([4, 4], [2, 2])
    assert result["verdict"] == MOVED_DOWN


def test_about_the_same_when_the_mean_barely_moves():
    # before mean 3.0, after mean 3.2 -- delta well under the threshold.
    result = compute_readout([3, 3, 3], [3, 3, 4])
    assert result["verdict"] == ABOUT_THE_SAME


def test_about_the_same_on_identical_means():
    result = compute_readout([3, 4, 5], [3, 4, 5])
    assert result["verdict"] == ABOUT_THE_SAME


def test_threshold_boundary_is_inclusive_to_about_the_same():
    """Exactly ABOUT_THE_SAME_THRESHOLD (0.5) counts as no clear move -- ties
    go to the conservative word, per the module docstring."""
    # before mean 3.0, after mean 3.5 -- delta exactly 0.5.
    result = compute_readout([3, 3], [3, 4])
    assert result["verdict"] == ABOUT_THE_SAME

    # Just past the boundary is a real move.
    just_over_delta = ABOUT_THE_SAME_THRESHOLD + 0.01
    result_up = compute_readout([3], [3 + just_over_delta])
    assert result_up["verdict"] == MOVED_UP


def test_readout_never_carries_a_delta_or_mean_field():
    """The module docstring's rule, checked structurally: the only keys are
    verdict and the two counts."""
    result = compute_readout([1, 2], [4, 5])
    assert set(result) == {"verdict", "before_count", "after_count"}


# ---------------------------------------------------------------------------
# derive_phase
# ---------------------------------------------------------------------------

STARTED = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
ENDS = datetime.datetime(2026, 9, 15, tzinfo=datetime.timezone.utc)


def test_running_before_ends_at():
    now = ENDS - datetime.timedelta(seconds=1)
    assert derive_phase("active", ENDS, now) == RUNNING


def test_ended_exactly_at_the_ends_at_boundary():
    """`now == ends_at` reads as ended, not running -- the boundary belongs to
    `ended`, matching `Experiment.ends_at`'s "started_at + 14 days" contract."""
    assert derive_phase("active", ENDS, ENDS) == ENDED


def test_ended_after_ends_at():
    now = ENDS + datetime.timedelta(days=1)
    assert derive_phase("active", ENDS, now) == ENDED


def test_abandoned_wins_even_before_ends_at():
    now = ENDS - datetime.timedelta(days=5)
    assert derive_phase("abandoned", ENDS, now) == ABANDONED


def test_abandoned_wins_even_after_ends_at():
    now = ENDS + datetime.timedelta(days=5)
    assert derive_phase("abandoned", ENDS, now) == ABANDONED


def test_completed_reads_as_ended():
    """The stored `completed` status (2026-10-02) is the closed form of an
    ended experiment: the phase word is the same `ended` the clock gives an
    `active` row past its `ends_at`, so the wire never changes words when the
    lazy close lands."""
    now = ENDS + datetime.timedelta(days=5)
    assert derive_phase("completed", ENDS, now) == ENDED
    # Defensive: a completed row is never running again, whatever the clock says.
    assert derive_phase("completed", ENDS, ENDS - datetime.timedelta(days=1)) == ENDED
