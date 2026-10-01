"""Pure-numpy helpers for the optional global-scale reparameterization.

causal_graph/v1_model/global_scale.py. The PyMC side (the model graph, recovery)
is tested next to the model on system Python -- see
causal_graph/v1_model/test_global_scale_fit.py. Nothing here imports pymc.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

import match_scoring  # noqa: F401  -- puts causal_graph/v1_model on sys.path

import global_scale as gs  # noqa: E402
from match_core import load, point_weights, weights_from_priors  # noqa: E402

DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]


@pytest.fixture(scope="module")
def cfg_pri():
    return load()


@pytest.fixture()
def prior_point(cfg_pri):
    cfg, pri = cfg_pri
    return point_weights(weights_from_priors(cfg, pri))


def test_the_main_suite_never_imports_pymc():
    assert "pymc" not in sys.modules


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

def test_default_settings_are_the_documented_ones():
    assert gs.global_scale_settings() == {"sigma_log": 0.5, "delta_sd": 0.10}


@pytest.mark.parametrize("bad", [0.0, -0.1, float("nan"), float("inf")])
def test_non_positive_or_non_finite_settings_are_refused(bad):
    with pytest.raises(ValueError):
        gs.global_scale_settings(sigma_log=bad)
    with pytest.raises(ValueError):
        gs.global_scale_settings(delta_sd=bad)


def test_the_delta_sd_is_tighter_than_the_experts_own_sd(cfg_pri):
    """The whole design: at low N the shared s moves, the deltas mostly do not."""
    _cfg, pri = cfg_pri
    her_sd = min(float(f["sd"]) for feats in pri["dimensions"].values() for f in feats.values())
    assert gs.DEFAULT_DELTA_SD < her_sd / 2


# ---------------------------------------------------------------------------
# scale_dimension_weights
# ---------------------------------------------------------------------------

def test_scaling_multiplies_every_dimension_weight_and_nothing_else(cfg_pri, prior_point):
    cfg, _pri = cfg_pri
    scaled = gs.scale_dimension_weights(prior_point, cfg, 0.4)

    for dim in DIMS:
        for feat in ("mag", "dir"):
            assert scaled["dimensions"][dim][feat] == pytest.approx(
                0.4 * prior_point["dimensions"][dim][feat]
            )
    assert scaled["intercept"] == prior_point["intercept"]
    assert scaled["confounders"]["comp"] == prior_point["confounders"]["comp"]
    assert scaled["confounders"]["stage_size"] == prior_point["confounders"]["stage_size"]
    np.testing.assert_array_equal(scaled["confounders"]["industry"],
                                  prior_point["confounders"]["industry"])


def test_scaling_never_mutates_its_input(cfg_pri, prior_point):
    cfg, _pri = cfg_pri
    before = prior_point["dimensions"]["pace"]["mag"]
    gs.scale_dimension_weights(prior_point, cfg, 0.1)
    assert prior_point["dimensions"]["pace"]["mag"] == before


def test_a_scale_of_one_changes_nothing(cfg_pri, prior_point):
    cfg, _pri = cfg_pri
    same = gs.scale_dimension_weights(prior_point, cfg, 1.0)
    assert same["dimensions"] == prior_point["dimensions"]


def test_scaling_keeps_her_relative_ordering(cfg_pri, prior_point):
    cfg, _pri = cfg_pri
    order = lambda w: sorted(DIMS, key=lambda d: w["dimensions"][d]["mag"])  # noqa: E731
    assert order(gs.scale_dimension_weights(prior_point, cfg, 0.4)) == order(prior_point)


# ---------------------------------------------------------------------------
# hdi / summarize_scale
# ---------------------------------------------------------------------------

def test_hdi_of_a_uniform_grid_is_a_contiguous_block_of_the_right_width():
    draws = np.arange(100, dtype=float)
    low, high = gs.hdi(draws, 0.9)
    assert high - low == pytest.approx(90.0)


def test_hdi_finds_the_short_side_of_a_skewed_sample():
    """A lognormal's shortest interval sits left of the equal-tailed one."""
    rng = np.random.default_rng(0)
    draws = rng.lognormal(0.0, 0.5, size=20000)
    low, high = gs.hdi(draws, 0.94)
    eq_low, eq_high = np.quantile(draws, [0.03, 0.97])
    assert high - low < eq_high - eq_low
    assert low < eq_low
    assert np.mean((draws >= low) & (draws <= high)) == pytest.approx(0.94, abs=0.002)


@pytest.mark.parametrize("bad_prob", [0.0, 1.0, 1.5])
def test_hdi_refuses_a_meaningless_probability(bad_prob):
    with pytest.raises(ValueError):
        gs.hdi(np.arange(10.0), bad_prob)


def test_hdi_needs_two_draws():
    with pytest.raises(ValueError):
        gs.hdi([1.0], 0.9)


def test_summarize_scale_is_plain_floats_accepting_chain_by_draw_arrays():
    draws = np.random.default_rng(1).normal(0.4, 0.1, size=(2, 500))
    out = gs.summarize_scale(draws)
    assert set(out) == {"mean", "sd", "hdi_low", "hdi_high", "hdi_prob"}
    assert all(type(v) is float for v in out.values())
    assert out["mean"] == pytest.approx(0.4, abs=0.02)
    assert out["sd"] == pytest.approx(0.1, abs=0.01)
    assert out["hdi_low"] < 0.4 < out["hdi_high"]


# ---------------------------------------------------------------------------
# the additivity illustration
# ---------------------------------------------------------------------------

def test_a_minus_point_two_gap_on_all_six_is_the_quoted_three_in_ten(cfg_pri, prior_point):
    """The harshness this change exists to test: her weights, a small gap
    (person wants 0.2 less than the role offers) on every dimension."""
    cfg, _pri = cfg_pri
    assert gs.uniform_gap_p_fit(cfg, prior_point, -0.2) == pytest.approx(0.333, abs=0.005)


def test_a_zero_scale_leaves_only_the_intercept(cfg_pri, prior_point):
    """s -> 0 is 'the gap does not predict the rating': P(doing well) is her
    well-matched baseline, 8 in 10, whatever the gap."""
    cfg, _pri = cfg_pri
    assert gs.uniform_gap_p_fit(cfg, prior_point, -0.2, scale=0.0) == pytest.approx(0.8, abs=1e-6)


def test_a_smaller_scale_is_monotonically_gentler(cfg_pri, prior_point):
    cfg, _pri = cfg_pri
    values = [gs.uniform_gap_p_fit(cfg, prior_point, -0.2, scale=s) for s in (1.0, 0.7, 0.4, 0.1)]
    assert values == sorted(values)
