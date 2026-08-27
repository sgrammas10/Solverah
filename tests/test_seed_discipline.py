"""Tests for the seeds rule mechanism (S-04 / D-21).

The load-bearing assertions, in order of how easy the corresponding bug would be to miss:

1. PAIRING IS REAL, NOT ASSERTED. mean(a - b) == mean(a) - mean(b) ALWAYS, so a
   "simplification" of paired_contrast into a difference of arm means would leave every
   headline number identical and change only the dispersion. The discriminating fixture is
   two arms that move together (b = a + c): paired SD is 0, mean-based SD is not. Testing the
   value here would catch nothing -- the S-40 lesson applied before the bug exists.

2. THE PILOT RENDER CONTAINS NO NUMBER. The rule's clause is "labelled as a pilot with no
   number quoted", and the console output is what a session copies from. Asserted by checking
   the formatted value is absent from the string, not by eyeballing a prefix.

3. METADATA CANNOT BE FALSIFIED. n_draws and dispersion are derived from the array; the
   paired constructor refuses unequal lengths rather than truncating.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "causal_graph" / "v1_model"))

from seed_discipline import MIN_DRAWS, Finding, NotQuotable  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Pairing is structural
# ---------------------------------------------------------------------------

def test_paired_contrast_uses_per_draw_differences_not_arm_means():
    """Two arms that move together seed-for-seed: the paired difference is constant, so its
    SD is 0. A version that differenced the arm MEANS would report the same value with a
    non-zero spread and would look perfectly reasonable."""
    arm_a = [1.0, 5.0, 9.0, 13.0, 17.0]          # large seed-to-seed spread
    arm_b = [v - 0.2 for v in arm_a]             # ...identical in every seed

    f = Finding.paired_contrast("aligned arms", arm_a, arm_b)
    assert f.value == pytest.approx(0.2)
    assert f.dispersion == pytest.approx(0.0)    # the whole point of pairing
    assert f.quotable

    # The same arms, order scrambled in one of them: same means, no longer aligned. The
    # value is unchanged (mean of differences == difference of means) but the spread is not.
    scrambled = Finding.paired_contrast("misaligned arms", arm_a, list(reversed(arm_b)))
    assert scrambled.value == pytest.approx(0.2)
    assert scrambled.dispersion > 1.0


def test_paired_contrast_refuses_unequal_lengths():
    with pytest.raises(ValueError):
        Finding.paired_contrast("ragged", [1.0, 2.0, 3.0], [1.0, 2.0])


def test_unpaired_contrast_is_never_quotable_even_with_many_draws():
    f = Finding.unpaired_contrast("independent arms", [1.0] * 8, [2.0] * 8)
    assert f.paired is False
    assert not f.quotable
    assert "unpaired arms" in "; ".join(f.disqualifiers)


# ---------------------------------------------------------------------------
# 2. The pilot render quotes no number
# ---------------------------------------------------------------------------

def test_pilot_render_omits_the_value_entirely():
    f = Finding.paired_contrast("single seed run", [2.5], [0.0])
    assert not f.quotable
    rendered = f.render()
    assert "PILOT" in rendered
    assert f"{f.value:.3f}" not in rendered   # 2.500 must not appear anywhere
    assert "2.5" not in rendered
    # The number is still reachable for further computation -- deliberately, and visibly.
    assert f.value == pytest.approx(2.5)


def test_quotable_render_carries_its_provenance():
    f = Finding.paired_contrast("proper run", [1.0, 2.0, 3.0, 4.0], [0.5, 1.0, 2.5, 3.0])
    rendered = f.render()
    assert "PILOT" not in rendered
    assert f"{f.value:.3f}" in rendered
    assert "4 paired seeds" in rendered
    assert "SD" in rendered


def test_quote_raises_rather_than_degrading():
    f = Finding.estimate("one draw", [0.42])
    with pytest.raises(NotQuotable):
        f.quote()
    ok = Finding.estimate("three draws", [0.40, 0.42, 0.44])
    assert ok.quote() == "0.420"


# ---------------------------------------------------------------------------
# 3. Metadata is derived, and the threshold is the written rule
# ---------------------------------------------------------------------------

def test_n_draws_and_dispersion_come_from_the_data():
    f = Finding.estimate("five draws", [1.0, 2.0, 3.0, 4.0, 5.0])
    assert f.n_draws == 5
    assert f.value == pytest.approx(3.0)
    assert f.dispersion == pytest.approx(1.5811388, rel=1e-6)  # sample SD, ddof=1
    assert f.paired is None                                    # pairing N/A for one arm
    assert f.quotable


def test_threshold_is_min_draws():
    below = Finding.estimate("below", [1.0] * (MIN_DRAWS - 1))
    at = Finding.estimate("at", [1.0, 1.1, 1.2][:MIN_DRAWS])
    assert not below.quotable
    assert at.quotable
    assert f">= {MIN_DRAWS}" in "; ".join(below.disqualifiers)


def test_single_draw_has_no_dispersion_and_says_so():
    f = Finding.estimate("one", [0.7])
    assert f.dispersion is None
    reasons = "; ".join(f.disqualifiers)
    assert "no dispersion" in reasons


def test_bootstrap_is_a_first_class_draw_kind():
    """The S-17/S-18 generalization: real-data statistics have no seed, so a seeds-only rule
    could never be complied with. Bootstrap resamples are draws."""
    f = Finding.estimate(
        "fraction arriving via {1,1,0,0}", [0.31, 0.29, 0.33, 0.30], draw_kind="bootstrap"
    )
    assert f.quotable
    assert "bootstrap" in f.render()


def test_unknown_draw_kind_refuses():
    with pytest.raises(ValueError):
        Finding.estimate("mystery", [1.0, 2.0, 3.0], draw_kind="vibes")


def test_empty_and_non_finite_input_refuse():
    with pytest.raises(ValueError):
        Finding.estimate("empty", [])
    with pytest.raises(ValueError):
        Finding.estimate("nan", [1.0, float("nan"), 3.0])
