"""PyMC-side tests for the devfit harness: the posterior -> weight-rows boundary.

Lives here rather than in tests/ because it imports pymc, which the main suite's
interpreter does not have and CI does not install. Run it explicitly, on system
Python, BY PATH:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \\
        causal_graph/v1_model/devfit/test_devfit_fit.py -q

Do NOT run `pytest causal_graph` wholesale -- that tree has a known-red baseline
from missing optional packages, and its conftest deliberately poisons
OPENAI_API_KEY.

WHAT THIS PINS

`run_fit.posterior_weights` is the seam where PyMC stops. Everything downstream --
`match_scoring.record_fitted_run`, `flatten_weights`, the 20 `weight_posterior`
rows, every later `load_run_weights` in the app -- is pure numpy, and that is a
deliberate boundary: PyMC must never become a server dependency. So the thing
worth testing here is that a real posterior crosses that boundary with EXACTLY
the names the priors path produces. A missing or extra name would not fail here;
it would fail later, in the app, on every load, because `unflatten_weights` is
strict in both directions (D-07).

Deliberately small: N=40 rows, one chain, 40 tune / 40 draws. This is a shape and
naming test, not a recovery test -- recovery is what the acceptance run in
devfit/README.md measures, on 1200 rows.

No database. The rows are drawn by `seed_synthetic.SyntheticCohort`, which is the
same generator the real seeder uses but needs no connection of its own.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

# The package's own sys.path setup (causal_graph/v1_model + the repo root), so the
# bare `import match_core` / `import build_model` below resolve the same way they
# do for the scripts.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from causal_graph.v1_model.devfit import run_fit, seed_synthetic  # noqa: E402

import build_model as bm      # noqa: E402  -- sets PYTENSOR_FLAGS before pytensor
import pymc as pm             # noqa: E402,F401  -- must follow build_model
from match_core import active, flatten_weights, load, weights_from_priors  # noqa: E402

N = 40
DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]


@pytest.fixture(scope="module")
def cfg_pri():
    return load()


@pytest.fixture(scope="module")
def cohort_rows(cfg_pri):
    """N drawn rows in the arrays build_model wants, masked exactly as the real
    source masks them: `industry` absent on every row, `comp` absent on some."""
    cfg, pri = cfg_pri
    cohort = seed_synthetic.SyntheticCohort(cfg=cfg, pri=pri)
    rng = np.random.default_rng(0)
    rows = [cohort.draw(rng) for _ in range(N)]

    person = {d: np.array([r["person_scores"][d] for r in rows]) for d in DIMS}
    env = {d: np.array([r["env_scores"][d] for r in rows]) for d in DIMS}
    conf = {
        "stage_size": np.array([float(r["stage_size"]) for r in rows]),
        "comp": np.array(
            [np.nan if r["comp"] is None else float(r["comp"]) for r in rows]
        ),
        "industry": np.array([None] * N, dtype=object),
    }
    conf_missing = {
        "stage_size": np.zeros(N, dtype=bool),
        "comp": np.array([r["comp"] is None for r in rows]),
        "industry": np.ones(N, dtype=bool),
    }
    outcome = np.array([r["rating"] for r in rows], dtype=int)
    return person, env, conf, conf_missing, outcome


@pytest.fixture(scope="module")
def idata(cfg_pri, cohort_rows):
    cfg, pri = cfg_pri
    person, env, conf, conf_missing, outcome = cohort_rows
    # TWO chains, deliberately: r_hat is a between-chain statistic and does not
    # exist with one, which is the case `diagnostics` reports as unavailable and
    # `is_healthy` refuses. A one-chain fixture could not test the happy path.
    return bm.fit_posterior(
        person, env, conf, outcome, cfg, pri,
        head="experienced", conf_missing=conf_missing,
        draws=150, tune=150, chains=2, cores=1, random_seed=0,
        progressbar=False, compute_convergence_checks=False,
    )


# ---------------------------------------------------------------------------
# 1. The boundary: a real posterior -> 20 flat rows, names unchanged
# ---------------------------------------------------------------------------

def test_posterior_weights_flatten_to_exactly_the_priors_names(cfg_pri, idata):
    """The names are a database interface. `unflatten_weights` refuses a missing
    name AND an unexpected one, so a drifted set breaks every load in the app --
    not this fit."""
    cfg, pri = cfg_pri

    expected = [name for name, _, _ in flatten_weights(cfg, weights_from_priors(cfg, pri))]
    produced = [name for name, _, _ in flatten_weights(cfg, run_fit.posterior_weights(idata, cfg))]

    assert produced == expected
    assert len(produced) == 20


def test_the_flat_rows_round_trip_back_through_unflatten(cfg_pri, idata):
    """What record_fitted_run writes, every later load reads. Proven against the
    strict reader rather than against a re-derivation of its rules."""
    from match_core import unflatten_weights

    cfg, _pri = cfg_pri
    weights = run_fit.posterior_weights(idata, cfg)
    rows = {name: (mean, sd) for name, mean, sd in flatten_weights(cfg, weights)}

    back = unflatten_weights(cfg, rows)
    assert back["intercept"]["mean"] == pytest.approx(weights["intercept"]["mean"])
    for dim in DIMS:
        for feat in ("mag", "dir"):
            assert back["dimensions"][dim][feat]["mean"] == pytest.approx(
                weights["dimensions"][dim][feat]["mean"]
            )
    np.testing.assert_allclose(
        back["confounders"]["industry"]["mean"],
        weights["confounders"]["industry"]["mean"],
    )


def test_posterior_weights_are_plain_floats_and_arrays(cfg_pri, idata):
    """match_scoring never imports pymc, and the ORM cannot bind an xarray scalar.
    The conversion to plain Python happens HERE, which is why this is the test
    that guards it."""
    cfg, _pri = cfg_pri
    weights = run_fit.posterior_weights(idata, cfg)

    assert type(weights["intercept"]["mean"]) is float
    assert type(weights["intercept"]["sd"]) is float
    for feats in weights["dimensions"].values():
        for leaf in feats.values():
            assert type(leaf["mean"]) is float and type(leaf["sd"]) is float
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue
        leaf = weights["confounders"][c["key"]]
        if c.get("kind") == "categorical":
            assert isinstance(leaf["mean"], np.ndarray)
            assert leaf["mean"].shape == (len(c["levels"]),)
            assert leaf["sd"].shape == (len(c["levels"]),)
        else:
            assert type(leaf["mean"]) is float


def test_a_fully_masked_confounder_is_exported_and_is_still_its_prior(cfg_pri, idata):
    """`industry` is masked on every row this source produces, so the data says
    nothing about its five level weights. They must be exported UNCHANGED rather
    than dropped -- the 20-row set is a database interface, and `notes` is where
    a reader learns the term was masked.

    The assertion here is on the SD, not the mean. A weight the likelihood never
    touches keeps its prior's spread exactly, and 300 draws estimate a spread
    well. The MEAN of a Normal(0, 1) over 300 autocorrelated draws has a Monte
    Carlo error of order 0.1-0.2, so a tight bound on it would be testing the
    RNG, not the masking -- this file's fit is small on purpose. The sharp
    version of that claim is measured where it can be: the 1200-row acceptance
    run in README.md, and the 200-row fit in
    causal_graph/v1_model/test_ordinal_head.py which pins the mean inside 0.15.
    """
    cfg, pri = cfg_pri
    weights = run_fit.posterior_weights(idata, cfg)

    means = np.asarray(weights["confounders"]["industry"]["mean"])
    sds = np.asarray(weights["confounders"]["industry"]["sd"])
    prior_sd = float(pri["confounders"]["industry"]["sd"])

    assert means.shape == (5,) and sds.shape == (5,)
    assert np.isfinite(means).all() and np.isfinite(sds).all()
    # Unshrunk: data that never entered z cannot have narrowed this.
    assert np.abs(sds - prior_sd).max() < 0.25, sds.tolist()
    # And still centred on the prior, to within sampling noise at this size.
    assert np.abs(means).max() < 0.6, means.tolist()


# ---------------------------------------------------------------------------
# 2. The diagnostics and the cutpoint spacings
# ---------------------------------------------------------------------------

def test_cutpoint_spacings_are_three_and_are_not_weight_rows(cfg_pri, idata):
    cfg, _pri = cfg_pri

    spacings = run_fit.cutpoint_spacings(idata)
    assert len(spacings) == 3
    assert all(s["mean"] > 0 for s in spacings), "spacings are positive by construction"

    names = [name for name, _, _ in flatten_weights(cfg, run_fit.posterior_weights(idata, cfg))]
    assert not any("cut" in name or "spacing" in name for name in names)


def test_diagnostics_reports_a_real_rhat_from_two_chains(idata):
    diag = run_fit.diagnostics(idata)
    assert set(diag) == {"max_rhat", "max_rhat_on", "divergences"}
    assert np.isfinite(diag["max_rhat"])
    assert diag["max_rhat"] > 0.9          # r_hat is ~1 for anything that mixed
    assert isinstance(diag["divergences"], int)
    assert diag["max_rhat_on"]


def test_a_single_chain_reports_rhat_unavailable_rather_than_zero(cfg_pri, cohort_rows):
    """r_hat is a BETWEEN-chain statistic; with one chain arviz returns NaN for
    every variable. `np.nanmax` over all-NaN is where this went wrong first: it
    yields 0.0, and 0.0 < 1.05, so the gate silently passed a run nothing had
    checked. Reported as unavailable, and refused."""
    cfg, pri = cfg_pri
    person, env, conf, conf_missing, outcome = cohort_rows

    one_chain = bm.fit_posterior(
        person, env, conf, outcome, cfg, pri,
        head="experienced", conf_missing=conf_missing,
        draws=40, tune=40, chains=1, cores=1, random_seed=1,
        progressbar=False, compute_convergence_checks=False,
    )

    diag = run_fit.diagnostics(one_chain)
    assert not np.isfinite(diag["max_rhat"])
    assert "2 chains" in diag["max_rhat_on"]
    assert run_fit.is_healthy(diag) is False


# ---------------------------------------------------------------------------
# 3. --prior-sd-scale touches the dimensions and nothing else
# ---------------------------------------------------------------------------

def test_prior_sd_scale_widens_only_the_dimension_weights(cfg_pri):
    cfg, pri = cfg_pri
    scaled = run_fit.scaled_priors(pri, 3.0)

    for dim in DIMS:
        for feat in ("mag", "dir"):
            assert scaled["dimensions"][dim][feat]["sd"] == pytest.approx(
                pri["dimensions"][dim][feat]["sd"] * 3.0
            )
            # the MEAN is untouched: widening is about confidence, not position
            assert scaled["dimensions"][dim][feat]["mean"] == pytest.approx(
                pri["dimensions"][dim][feat]["mean"]
            )

    assert scaled["intercept"] == pri["intercept"]
    assert scaled["confounders"] == pri["confounders"]
    assert scaled["cutpoints"] == pri["cutpoints"]


def test_prior_sd_scale_never_mutates_the_loaded_priors(cfg_pri):
    """priors.yaml holds elicited numbers. A widened run is a dev convenience and
    must not leak into anything else in the process."""
    cfg, pri = cfg_pri
    before = float(pri["dimensions"]["pace"]["mag"]["sd"])
    run_fit.scaled_priors(pri, 5.0)
    assert float(pri["dimensions"]["pace"]["mag"]["sd"]) == before


def test_scale_of_one_is_an_unchanged_copy(cfg_pri):
    cfg, pri = cfg_pri
    assert run_fit.scaled_priors(pri, 1.0) == pri


def test_a_widened_prior_actually_reaches_the_model(cfg_pri, cohort_rows):
    """The flag is only meaningful if pm.Normal gets the wider sigma. Checked on
    the built model rather than on the dict."""
    cfg, pri = cfg_pri
    person, env, conf, conf_missing, outcome = cohort_rows

    def pace_mag_sigma(priors):
        model = bm.build_model(person, env, conf, cfg, priors, outcome=outcome,
                               head="experienced", conf_missing=conf_missing)
        rv = next(v for v in model.free_RVs if v.name == "pace_mag")
        return float(rv.owner.inputs[-1].eval())

    narrow = pace_mag_sigma(pri)
    wide = pace_mag_sigma(run_fit.scaled_priors(pri, 3.0))
    assert wide == pytest.approx(narrow * 3.0)
