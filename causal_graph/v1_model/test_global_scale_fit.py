"""PyMC-side tests for the optional global-scale reparameterization (2026-09-29).

Lives here rather than in tests/ because it imports pymc, which the main suite's
interpreter does not have and CI does not install. Run it on system Python, BY PATH:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 py -3.10 -m pytest \\
        causal_graph/v1_model/test_global_scale_fit.py -q

Budget ~5-9 minutes (pure-Python pytensor; 8.5 min measured under load). The numpy helpers are tested in the
main suite, tests/test_global_scale.py.

WHAT THIS PINS
1. Switch OFF is the model that existed before the switch: the same free RVs, the
   same log density at the initial point, and the same posterior from a short
   seeded fit. The constants below were captured on the pre-change code
   (2026-09-29, pymc 5.25.1, default PYTENSOR_FLAGS=cxx=). A compiled pytensor
   mode may differ in the last digits; the fit comparison is therefore at 1e-9,
   not bit-for-bit, and the free-RV list and logp are the sharp checks.
2. Switch ON still exports exactly the twenty flat weight names, and the notes
   block carries s.
3. Recovery: a planted s = 0.4 (her ordering kept, deltas zero) pulls s's
   posterior from its prior median 1 toward 0.4, and the 94% HDI covers it.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from causal_graph.v1_model.devfit import run_fit, seed_synthetic  # noqa: E402

import build_model as bm       # noqa: E402  -- sets PYTENSOR_FLAGS before pytensor
import pymc as pm              # noqa: E402,F401  -- must follow build_model
import global_scale as gs      # noqa: E402
from match_core import flatten_weights, load, weights_from_priors  # noqa: E402

DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]

# --- captured on the pre-change code, see the module docstring -------------------
BASELINE_FREE_RVS = [
    "intercept", "autonomy_mag", "autonomy_dir", "pace_mag", "pace_dir",
    "collaboration_mag", "collaboration_dir", "feedback_mag", "feedback_dir",
    "innovation_mag", "innovation_dir", "decision_mag", "decision_dir",
    "w_stage_size", "w_comp", "w_industry", "cut_spacing",
]
BASELINE_DETERMINISTICS = ["p_fit", "p_rating"]
BASELINE_LOGP = -60.335691364359235
BASELINE_OUTCOME = [5, 3, 5, 3, 3, 5, 2, 5, 3, 2, 1, 4, 2, 4, 3, 2, 5, 2, 1, 4,
                    2, 5, 2, 4, 1, 4, 2, 4, 5, 2, 2, 4, 4, 4, 3, 3, 5, 4, 2, 2]
BASELINE_FIT_MEANS = {          # chains=1, tune=30, draws=30, random_seed=7
    "intercept": 1.4733194379482863,
    "pace_mag": -2.6016487465004388,
    "autonomy_mag": -0.9343908196190938,
    "feedback_dir": 1.040259709840572,
}


def _rows(cfg, pri, n, seed, planted_scale=None):
    """n drawn rows, masked as the real source masks them."""
    cohort = seed_synthetic.SyntheticCohort(cfg=cfg, pri=pri, planted_scale=planted_scale)
    rng = np.random.default_rng(seed)
    rows = [cohort.draw(rng) for _ in range(n)]
    person = {d: np.array([r["person_scores"][d] for r in rows]) for d in DIMS}
    env = {d: np.array([r["env_scores"][d] for r in rows]) for d in DIMS}
    conf = {
        "stage_size": np.array([float(r["stage_size"]) for r in rows]),
        "comp": np.array([np.nan if r["comp"] is None else float(r["comp"]) for r in rows]),
        "industry": np.array([None] * n, dtype=object),
    }
    conf_missing = {
        "stage_size": np.zeros(n, dtype=bool),
        "comp": np.array([r["comp"] is None for r in rows]),
        "industry": np.ones(n, dtype=bool),
    }
    outcome = np.array([r["rating"] for r in rows], dtype=int)
    return person, env, conf, conf_missing, outcome


@pytest.fixture(scope="module")
def cfg_pri():
    return load()


@pytest.fixture(scope="module")
def baseline_rows(cfg_pri):
    cfg, pri = cfg_pri
    return _rows(cfg, pri, 40, 0)


# ---------------------------------------------------------------------------
# 1. Switch OFF: the pre-change model
# ---------------------------------------------------------------------------

def test_the_regression_cohort_is_the_one_the_constants_were_captured_on(baseline_rows):
    """If the generator changes, the constants below stop meaning anything."""
    assert baseline_rows[4].tolist() == BASELINE_OUTCOME


@pytest.mark.parametrize("pass_none", [False, True])
def test_switch_off_builds_the_pre_change_graph(cfg_pri, baseline_rows, pass_none):
    cfg, pri = cfg_pri
    person, env, conf, conf_missing, outcome = baseline_rows
    extra = {"global_scale": None} if pass_none else {}

    model = bm.build_model(person, env, conf, cfg, pri, outcome=outcome,
                           head="experienced", conf_missing=conf_missing, **extra)

    assert [v.name for v in model.free_RVs] == BASELINE_FREE_RVS
    assert [v.name for v in model.deterministics] == BASELINE_DETERMINISTICS
    assert float(model.compile_logp()(model.initial_point())) == BASELINE_LOGP


def test_switch_off_short_seeded_fit_matches_the_pre_change_posterior(cfg_pri, baseline_rows):
    cfg, pri = cfg_pri
    person, env, conf, conf_missing, outcome = baseline_rows
    idata = bm.fit_posterior(person, env, conf, outcome, cfg, pri, head="experienced",
                             conf_missing=conf_missing, global_scale=None,
                             draws=30, tune=30, chains=1, cores=1, random_seed=7,
                             progressbar=False, compute_convergence_checks=False)
    for name, expected in BASELINE_FIT_MEANS.items():
        assert float(idata.posterior[name].values.mean()) == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# 2. Switch ON: the graph, the export, the notes
# ---------------------------------------------------------------------------

def test_switch_on_replaces_the_twelve_dimension_rvs_with_one_scale_and_deltas(
        cfg_pri, baseline_rows):
    cfg, pri = cfg_pri
    person, env, conf, conf_missing, outcome = baseline_rows
    model = bm.build_model(person, env, conf, cfg, pri, outcome=outcome,
                           head="experienced", conf_missing=conf_missing,
                           global_scale=gs.global_scale_settings())

    free = [v.name for v in model.free_RVs]
    dim_names = ["%s_%s" % (d, f) for d in DIMS for f in ("mag", "dir")]
    assert gs.SCALE_NAME in free
    assert [n for n in free if n.endswith(gs.DELTA_SUFFIX)] == [
        n + gs.DELTA_SUFFIX for n in dim_names
    ]
    assert not set(dim_names) & set(free)
    # the effective weights keep their ordinary names, as deterministics
    dets = {v.name for v in model.deterministics}
    assert set(dim_names) <= dets
    # intercept, confounders and cutpoints are exactly as before
    for name in ("intercept", "w_stage_size", "w_comp", "w_industry", "cut_spacing"):
        assert name in free


def test_switch_on_effective_weight_is_s_times_her_mean_plus_delta(cfg_pri, baseline_rows):
    cfg, pri = cfg_pri
    person, env, conf, conf_missing, outcome = baseline_rows
    model = bm.build_model(person, env, conf, cfg, pri, outcome=outcome,
                           head="experienced", conf_missing=conf_missing,
                           global_scale=gs.global_scale_settings())
    from pytensor import clone_replace
    import pytensor.tensor as pt

    effective = clone_replace(model["pace_mag"], {
        model["global_scale"]: pt.constant(0.4),
        model["pace_mag_delta"]: pt.constant(0.05),
    })
    expected = 0.4 * pri["dimensions"]["pace"]["mag"]["mean"] + 0.05
    assert float(effective.eval()) == pytest.approx(expected)


def test_switch_on_prior_sigmas_are_the_settings(cfg_pri, baseline_rows):
    cfg, pri = cfg_pri
    person, env, conf, conf_missing, outcome = baseline_rows
    model = bm.build_model(person, env, conf, cfg, pri, outcome=outcome,
                           head="experienced", conf_missing=conf_missing,
                           global_scale=gs.global_scale_settings(0.7, 0.05))
    s_rv = model["global_scale"]
    d_rv = model["feedback_dir_delta"]
    assert float(s_rv.owner.inputs[-1].eval()) == pytest.approx(0.7)
    assert float(d_rv.owner.inputs[-1].eval()) == pytest.approx(0.05)


@pytest.fixture(scope="module")
def scaled_idata(cfg_pri, baseline_rows):
    cfg, pri = cfg_pri
    person, env, conf, conf_missing, outcome = baseline_rows
    return bm.fit_posterior(person, env, conf, outcome, cfg, pri, head="experienced",
                            conf_missing=conf_missing,
                            global_scale=gs.global_scale_settings(),
                            draws=100, tune=100, chains=2, cores=1, random_seed=0,
                            progressbar=False, compute_convergence_checks=False)


def test_switch_on_exports_exactly_the_twenty_priors_names(cfg_pri, scaled_idata):
    cfg, pri = cfg_pri
    expected = [n for n, _, _ in flatten_weights(cfg, weights_from_priors(cfg, pri))]
    produced = [n for n, _, _ in flatten_weights(cfg, run_fit.posterior_weights(scaled_idata, cfg))]
    assert produced == expected
    assert len(produced) == 20


def test_the_exported_weight_is_the_effective_one(cfg_pri, scaled_idata):
    cfg, pri = cfg_pri
    post = scaled_idata.posterior
    s = np.asarray(post["global_scale"].values).reshape(-1)
    delta = np.asarray(post["pace_mag_delta"].values).reshape(-1)
    effective = s * pri["dimensions"]["pace"]["mag"]["mean"] + delta
    weights = run_fit.posterior_weights(scaled_idata, cfg)
    assert weights["dimensions"]["pace"]["mag"]["mean"] == pytest.approx(effective.mean())
    assert weights["dimensions"]["pace"]["mag"]["sd"] == pytest.approx(effective.std(ddof=1))


def test_the_notes_block_carries_s_and_is_json(cfg_pri, scaled_idata):
    cfg, _pri = cfg_pri
    notes = run_fit.global_scale_notes(scaled_idata, gs.global_scale_settings(), cfg)
    assert notes["prior"] == {"dist": "LogNormal", "mu_log": 0.0, "sigma_log": 0.5}
    assert notes["delta_sd"] == 0.10
    post = notes["posterior"]
    assert set(post) == {"mean", "sd", "hdi_low", "hdi_high", "hdi_prob"}
    assert 0 < post["hdi_low"] < post["mean"] < post["hdi_high"]
    assert notes["max_abs_delta_mean"]["name"].endswith(gs.DELTA_SUFFIX)
    assert json.loads(json.dumps(notes, sort_keys=True)) == notes


# ---------------------------------------------------------------------------
# 3. Recovery
# ---------------------------------------------------------------------------

PLANTED_S = 0.4


@pytest.fixture(scope="module")
def recovery_idata(cfg_pri):
    """200 rows drawn under s = 0.4 (deltas 0). ~3 minutes on pure-Python pytensor."""
    cfg, pri = cfg_pri
    person, env, conf, conf_missing, outcome = _rows(cfg, pri, 200, 0, planted_scale=PLANTED_S)
    return bm.fit_posterior(person, env, conf, outcome, cfg, pri, head="experienced",
                            conf_missing=conf_missing,
                            global_scale=gs.global_scale_settings(),
                            draws=150, tune=150, chains=2, cores=1, random_seed=0,
                            progressbar=False, compute_convergence_checks=False)


def test_a_planted_scale_is_recovered(recovery_idata):
    summary = gs.summarize_scale(recovery_idata.posterior["global_scale"].values)
    # moved from the prior median 1 most of the way toward the truth ...
    assert summary["mean"] < 0.75, summary
    assert abs(summary["mean"] - PLANTED_S) < abs(1.0 - PLANTED_S) / 2, summary
    # ... and the interval covers it
    assert summary["hdi_low"] <= PLANTED_S <= summary["hdi_high"], summary


def test_the_recovery_fit_is_healthy(recovery_idata):
    diag = run_fit.diagnostics(recovery_idata)
    assert diag["divergences"] == 0, diag
    assert diag["max_rhat"] < 1.1, diag
