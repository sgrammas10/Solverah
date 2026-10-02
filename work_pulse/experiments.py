"""Condition experiments: phase derivation and the before/after readout
(BUILD_PLAN B-5).

Pure: no Flask, no DB, no clock of its own. `experiment_store.py` is where a row
comes from and where the raw Pulse check-in values that feed `compute_readout`
are read; this module only turns those into the three words a user is allowed
to see. `now` and the two value lists are always handed in, never fetched here
-- the same "pure functions, no Flask" rule `work_pulse.situation` states for
the gap engine.

THE ABOUT-THE-SAME THRESHOLD, AND WHY 0.5
------------------------------------------
`experienced` is an integer on a 1..5 scale, and a readout compares the mean of
whatever check-ins fall before an experiment's `started_at` against the mean of
whatever check-ins fall in `[started_at, ends_at]`. Both means are built from a
handful of check-ins at most -- this is a two-week window, not a longitudinal
study -- so the arithmetic has to stay honest about how little that buys.

A single check-in landing on the adjacent whole-number answer (a 3 instead of a
4, nothing about the person's situation having changed) moves a small sample's
mean by up to about half a point on its own. That is pure reporting noise in
the same sense `work_pulse.situation.ALIGNED_THRESHOLDS` treats one band's
worth of movement on one item as noise rather than signal: a difference at or
below half a point is not distinguishable from one check-in going the other
way, so it is called `about_the_same` rather than dressed up as a real move.
Above half a point takes at least a full point of real movement somewhere in
the sample, which is not explained by picking one adjacent integer differently
on a single answer. The boundary itself (`ABOUT_THE_SAME_THRESHOLD`, exactly
0.5) counts as `about_the_same` -- ties go to the conservative word, the one
that claims nothing moved, rather than to a direction.

This is a policy choice, not a fitted statistic -- the same status
`work_pulse.situation`'s own thresholds carry, and the same reason this module
states its reasoning here rather than asserting it silently.

WHAT THE VERDICT NEVER SAYS
----------------------------
`compute_readout` returns a verdict word plus the two check-in counts that
produced it, and nothing else -- never a delta, never the means themselves,
never a claim that the experiment caused anything. "Your numbers moved" is the
whole of what this module is willing to say; "this worked" is a claim about
causation a two-week, single-user, unblinded before/after comparison cannot
support, and PRODUCT_DECISIONS.md §2 is explicit that the aggregate, not this
per-user readout, is the model lane's evidence.
"""
from __future__ import annotations

import datetime
from typing import Sequence, TypedDict

__all__ = [
    "ABOUT_THE_SAME",
    "ABOUT_THE_SAME_THRESHOLD",
    "ABANDONED",
    "ENDED",
    "MOVED_DOWN",
    "MOVED_UP",
    "NOT_ENOUGH_DATA",
    "PHASES",
    "RUNNING",
    "VERDICTS",
    "ReadoutResult",
    "compute_readout",
    "derive_phase",
]

NOT_ENOUGH_DATA = "not_enough_data"
MOVED_UP = "moved_up"
MOVED_DOWN = "moved_down"
ABOUT_THE_SAME = "about_the_same"
VERDICTS: tuple[str, ...] = (NOT_ENOUGH_DATA, MOVED_UP, MOVED_DOWN, ABOUT_THE_SAME)

#: See the module docstring's "THE ABOUT-THE-SAME THRESHOLD" section. |delta| at
#: or below this, on the 1..5 `experienced` scale, reads as no clear move.
ABOUT_THE_SAME_THRESHOLD = 0.5


class ReadoutResult(TypedDict):
    verdict: str
    before_count: int
    after_count: int


def compute_readout(
    before_values: Sequence[int], after_values: Sequence[int]
) -> ReadoutResult:
    """The three words plus the two counts. Never a delta, never a mean --
    see the module docstring's "WHAT THE VERDICT NEVER SAYS".

    `not_enough_data` fires whenever EITHER side has zero check-ins: a readout
    with nothing on one side is not a comparison, and saying so plainly is the
    whole of BUILD_PLAN B-5's brief for that case.
    """
    before_count = len(before_values)
    after_count = len(after_values)

    if before_count == 0 or after_count == 0:
        verdict = NOT_ENOUGH_DATA
    else:
        delta = (sum(after_values) / after_count) - (sum(before_values) / before_count)
        if abs(delta) <= ABOUT_THE_SAME_THRESHOLD:
            verdict = ABOUT_THE_SAME
        elif delta > 0:
            verdict = MOVED_UP
        else:
            verdict = MOVED_DOWN

    return {"verdict": verdict, "before_count": before_count, "after_count": after_count}


RUNNING = "running"
ENDED = "ended"
ABANDONED = "abandoned"
PHASES: tuple[str, ...] = (RUNNING, ENDED, ABANDONED)


def derive_phase(
    status: str, ends_at: datetime.datetime, now: datetime.datetime
) -> str:
    """`running` / `ended` / `abandoned`, derived on every read.

    `abandoned` wins outright: an abandoned experiment stays abandoned
    regardless of where `ends_at` sits relative to `now`. `completed` -- the
    stored fact `experiment_store.close_ended_experiments` writes once
    `ends_at` has passed (2026-10-02 fix: an ended row left `active` kept the
    one-active index and the 409 check refusing every later start) -- reads as
    `ended`. An `active` row is still judged against the clock: the boundary is
    `now >= ends_at`, so the instant `ends_at` arrives the experiment reads as
    `ended` even before the row has been closed, matching `Experiment.ends_at`'s
    own docstring ("started_at + 14 days") rather than requiring one further
    tick or one further write.
    """
    if status == "abandoned":
        return ABANDONED
    if status == "completed" or now >= ends_at:
        return ENDED
    return RUNNING
