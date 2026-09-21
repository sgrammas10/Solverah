"""PyMC-side tests for the ordered-outcome head.

Lives here rather than in tests/ because it imports pymc, which the main suite's
interpreter does not have and CI does not install. Run it explicitly, on system Python:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \\
        causal_graph/v1_model/test_ordinal_head.py -q

Do NOT run `pytest causal_graph` wholesale -- that tree has a known-red baseline from
missing optional packages, and its conftest deliberately poisons OPENAI_API_KEY.

Deliberately fast: prior predictive with a handful of draws, no NUTS. Sampling belongs
in ordinal_recovery.py, which is a script and not a test.

The numpy half of this head (match_core.ordinal_probs, preprocess_conf's NULL handling)
is tested in tests/test_ordinal_head.py, in the suite that actually runs in CI.
"""

import numpy as np
import pytest

import build_model as bm      # sets PYTENSOR_FLAGS before pytensor is configured
import pymc as pm                # noqa: E402  -- must follow build_model, see above
from match_core import load, ordinal_probs

DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
N = 12


@pytest.fixture(scope="module")
def cfg_pri():
    return load()


def _inputs(n=N, seed=0):
    rng = np.random.default_rng(seed)
    person = {d: rng.choice(bm.PERSON_LATTICE, n) for d in DIMS}
    env = {d: bm.closest_achievable(rng.random(n)) for d in DIMS}
    conf = {
        "stage_size": rng.normal(3.0, 1.5, n),
        "comp": rng.normal(3.0, 1.0, n),
        "industry": rng.choice(["tech", "finance", "healthcare", "retail", "other"], n),
    }
    return person, env, conf


# ---------------------------------------------------------------------------
# 1. The ordinal head builds and samples
# ---------------------------------------------------------------------------

def test_ordinal_model_builds_with_an_observed_rating(cfg_pri):
    cfg, pri = cfg_pri
    person, env, conf = _inputs()
    outcome = np.array([1, 2, 3, 4, 5] + [3] * (N - 5))

    model = bm.build_model(person, env, conf, cfg, pri, outcome=outcome,
                           head="experienced")

    names = {v.name for v in model.observed_RVs}
    assert names == {"working_scale"}
    assert "cut_spacing" in {v.name for v in model.free_RVs}
    assert {"p_fit", "p_rating"} <= {v.name for v in model.deterministics}


def test_prior_predictive_runs_on_the_ordinal_head(cfg_pri):
    cfg, pri = cfg_pri
    person, env, conf = _inputs()

    model = bm.build_model(person, env, conf, cfg, pri, head="experienced")
    with model:
        idata = pm.sample_prior_predictive(draws=40, random_seed=0)

    p_rating = idata.prior["p_rating"].values
    assert p_rating.shape[-2:] == (N, 5)
    np.testing.assert_allclose(p_rating.sum(axis=-1), 1.0, atol=1e-9)


# ---------------------------------------------------------------------------
# 2. THE MAPPING, through PyMC's own likelihood
# ---------------------------------------------------------------------------

def test_top_two_ratings_carry_exactly_p_fit(cfg_pri):
    """The invariant the pin exists for, checked on PyMC's OrderedLogistic rather than
    on the numpy twin: across prior draws, P(rating >= 4) IS sigmoid(z). If the pin ever
    becomes a free cutpoint this is what catches it -- nothing else would fail."""
    cfg, pri = cfg_pri
    person, env, conf = _inputs()

    model = bm.build_model(person, env, conf, cfg, pri, head="experienced")
    with model:
        idata = pm.sample_prior_predictive(draws=200, random_seed=1)

    p_rating = idata.prior["p_rating"].values        # (chain, draw, N, 5)
    p_fit = idata.prior["p_fit"].values              # (chain, draw, N)
    np.testing.assert_allclose(p_rating[..., 3:].sum(axis=-1), p_fit, atol=1e-9, rtol=0)


def test_numpy_twin_matches_pymcs_probabilities(cfg_pri):
    """match_core.ordinal_probs is what serving will read; PyMC's compute_p is what the
    likelihood scores. Two implementations of one formula is how they drift, so they are
    pinned against each other here."""
    cfg, pri = cfg_pri

    z = np.linspace(-4.0, 4.0, 17)
    cutpoints = np.array([-3.0, -1.5, 0.0, 1.5])
    theirs = pm.OrderedLogistic.compute_p(z, cutpoints).eval()
    np.testing.assert_allclose(ordinal_probs(z, cutpoints), theirs, atol=1e-12, rtol=0)


def test_cutpoints_are_ascending_with_the_pin_at_zero(cfg_pri):
    """Built from positive spacings, so ordering holds by construction and the pinned
    element stays exactly 0 -- no `ordered` transform to fight it."""
    cfg, pri = cfg_pri
    head_cfg = bm.head_config(cfg, "experienced")

    with pm.Model():
        cutpoints = bm.ordinal_cutpoints(head_cfg, pri)
        drawn = pm.draw(cutpoints, draws=50, random_seed=2)

    assert drawn.shape == (50, 4)
    assert (drawn[:, 2] == 0.0).all()
    assert (np.diff(drawn, axis=-1) > 0).all()


# ---------------------------------------------------------------------------
# 3. doing_well_at drives the pin (it is derived, not hardcoded)
# ---------------------------------------------------------------------------

def test_pin_index_is_derived_from_doing_well_at():
    assert bm.pinned_cutpoint_index({"levels": 5, "doing_well_at": 4}) == 2
    assert bm.pinned_cutpoint_index({"levels": 5, "doing_well_at": 3}) == 1
    assert bm.pinned_cutpoint_index({"levels": 5, "doing_well_at": 2}) == 0
    assert bm.pinned_cutpoint_index({"levels": 5, "doing_well_at": 5}) == 3

    with pytest.raises(ValueError):
        bm.pinned_cutpoint_index({"levels": 5, "doing_well_at": 1})   # nothing below it
    with pytest.raises(ValueError):
        bm.pinned_cutpoint_index({"levels": 5, "doing_well_at": 6})
    with pytest.raises(ValueError):
        bm.pinned_cutpoint_index({"levels": 2, "doing_well_at": 2})   # that is Bernoulli


def test_a_config_with_doing_well_at_3_moves_the_pin(cfg_pri):
    """The threshold is config, not a constant baked into the code: move it and
    sigmoid(z) must become P(rating >= 3) with no other change."""
    cfg, pri = cfg_pri
    head_cfg = dict(bm.head_config(cfg, "experienced"), doing_well_at=3)

    with pm.Model():
        drawn = pm.draw(bm.ordinal_cutpoints(head_cfg, pri), draws=20, random_seed=3)

    assert (drawn[:, 1] == 0.0).all()                       # pin moved down one
    assert (np.diff(drawn, axis=-1) > 0).all()

    z = np.linspace(-3.0, 3.0, 13)
    for cuts in drawn[:5]:
        p = ordinal_probs(z, cuts)
        expected = 1.0 / (1.0 + np.exp(-z))
        np.testing.assert_allclose(p[..., 2:].sum(axis=-1), expected, atol=1e-12, rtol=0)


# ---------------------------------------------------------------------------
# 4. Bad outcomes refuse, loudly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [0, 6, 3.5, -1, np.nan])
def test_out_of_range_or_fractional_outcomes_raise(cfg_pri, bad):
    """Never clipped, never rounded: a coerced rating is a wrong likelihood that
    nothing downstream would show."""
    cfg, pri = cfg_pri
    person, env, conf = _inputs()
    outcome = np.array([3.0] * N)
    outcome[4] = bad

    with pytest.raises(ValueError) as exc:
        bm.build_model(person, env, conf, cfg, pri, outcome=outcome, head="experienced")
    assert "1..5" in str(exc.value)


def test_valid_ratings_map_to_zero_based_categories():
    assert bm.ordinal_observed([1, 2, 3, 4, 5], 5).tolist() == [0, 1, 2, 3, 4]
    assert bm.ordinal_observed(np.array([4.0, 2.0]), 5).tolist() == [3, 1]


def test_unknown_head_refuses(cfg_pri):
    cfg, pri = cfg_pri
    person, env, conf = _inputs()
    with pytest.raises(ValueError):
        bm.build_model(person, env, conf, cfg, pri, head="nonesuch")


# ---------------------------------------------------------------------------
# 5. The appeal head did not move
# ---------------------------------------------------------------------------

EXPECTED_APPEAL_RVS = {
    "intercept",
    "autonomy_mag", "autonomy_dir",
    "pace_mag", "pace_dir",
    "collaboration_mag", "collaboration_dir",
    "feedback_mag", "feedback_dir",
    "innovation_mag", "innovation_dir",
    "decision_mag", "decision_dir",
    "w_stage_size", "w_comp", "w_industry",
}


def test_appeal_head_has_exactly_the_same_free_rvs_as_before(cfg_pri):
    """20 flat weights collapse to 16 RVs (industry's five levels are one shape-(5,) RV).
    No cut_spacing, no p_rating: the binary head is untouched by this change."""
    cfg, pri = cfg_pri
    person, env, conf = _inputs()
    outcome = np.array([0, 1] * (N // 2))

    model = bm.build_model(person, env, conf, cfg, pri, outcome=outcome)

    assert {v.name for v in model.free_RVs} == EXPECTED_APPEAL_RVS
    assert {v.name for v in model.deterministics} == {"p_fit"}
    assert {v.name for v in model.observed_RVs} == {"fit_yes"}


def test_appeal_head_is_the_default_and_matches_an_explicit_head(cfg_pri):
    cfg, pri = cfg_pri
    person, env, conf = _inputs()
    outcome = np.array([0, 1] * (N // 2))

    implicit = bm.build_model(person, env, conf, cfg, pri, outcome=outcome)
    explicit = bm.build_model(person, env, conf, cfg, pri, outcome=outcome, head="appeal")

    assert {v.name for v in implicit.free_RVs} == {v.name for v in explicit.free_RVs}
    assert {v.name for v in implicit.observed_RVs} == {v.name for v in explicit.observed_RVs}


def test_appeal_head_prior_predictive_is_unchanged_by_the_new_params(cfg_pri):
    """Same seed, same draws -> the same p_fit, whether or not the new keyword
    arguments are mentioned. They default to the old behavior; this proves it."""
    cfg, pri = cfg_pri
    person, env, conf = _inputs()

    a = np.asarray(bm.prior_predictive(person, env, conf, cfg, pri, draws=50,
                                       random_seed=7))
    b = np.asarray(bm.prior_predictive(person, env, conf, cfg, pri, draws=50,
                                       random_seed=7, head="appeal", conf_missing=None))
    np.testing.assert_array_equal(a, b)
