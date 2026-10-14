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


# ---------------------------------------------------------------------------
# 6. The MASKED CATEGORICAL, through PyMC (ruled 2026-09-21)
#
# The environment instrument never asks `industry`, so every row off that source
# carries None for an active categorical confounder. The ruling is the one
# already applied to a missing `comp`: exclude the term. A masked row indexes
# level 0 as a PLACEHOLDER and preprocess_conf emits a companion
# `industry__present` array, 0.0 there, so `w[level] * present` contributes
# nothing. build_model turns every key preprocess_conf returns into pm.Data, so
# the companion arrives as `conf_industry__present` with no special-casing here.
#
# The arithmetic is pinned in tests/test_ordinal_head.py, which runs in CI. What
# is pinned HERE is the half that suite cannot reach: that pytensor accepts the
# masked expression at all, that the unmasked model is byte-for-byte the same
# set of containers and RVs it always was, and that masked data teaches the
# masked weight nothing.
# ---------------------------------------------------------------------------

#: Every pm.Data container build_model creates with nothing masked. Written out
#: rather than derived, so a container appearing or vanishing has to be typed here
#: deliberately -- an accidental extra pm.Data is exactly the regression this guards.
EXPECTED_DATA_NO_MASK = {
    "person_autonomy", "person_pace", "person_collaboration",
    "person_feedback", "person_innovation", "person_decision",
    "env_autonomy", "env_pace", "env_collaboration",
    "env_feedback", "env_innovation", "env_decision",
    "conf_stage_size", "conf_comp", "conf_industry",
}

EXPECTED_EXPERIENCED_RVS = EXPECTED_APPEAL_RVS | {"cut_spacing"}


def _masked_inputs(n=N, seed=0, comp_every=3):
    """The environment source's shape: `industry` absent on every row (the
    instrument does not ask it) and `comp` absent on some ("not sure")."""
    person, env, conf = _inputs(n, seed)
    conf = dict(conf)
    conf["industry"] = np.array([None] * n, dtype=object)
    comp_mask = np.array([i % comp_every == 0 for i in range(n)])
    conf["comp"] = np.where(comp_mask, np.nan, conf["comp"])
    conf_missing = {
        "stage_size": np.zeros(n, dtype=bool),
        "comp": comp_mask,
        "industry": np.ones(n, dtype=bool),
    }
    return person, env, conf, conf_missing


def test_masked_industry_builds_and_prior_predictive_is_finite(cfg_pri):
    """pytensor has to accept `w[level] * present` on symbolic pm.Data. If it did
    not, the only way out would be a second implementation of the predictor -- which
    is the thing match_core exists to prevent."""
    cfg, pri = cfg_pri
    person, env, conf, conf_missing = _masked_inputs()
    outcome = np.array([1, 2, 3, 4, 5] + [3] * (N - 5))

    model = bm.build_model(person, env, conf, cfg, pri, outcome=outcome,
                           head="experienced", conf_missing=conf_missing)

    data_names = {v.name for v in model.data_vars}
    assert data_names == EXPECTED_DATA_NO_MASK | {"conf_industry__present"}
    assert {v.name for v in model.free_RVs} == EXPECTED_EXPERIENCED_RVS

    with model:
        idata = pm.sample_prior_predictive(draws=40, random_seed=0)

    p_fit = idata.prior["p_fit"].values
    p_rating = idata.prior["p_rating"].values
    assert np.isfinite(p_fit).all()
    assert np.isfinite(p_rating).all()
    np.testing.assert_allclose(p_rating.sum(axis=-1), 1.0, atol=1e-9)


@pytest.mark.parametrize("head", ["appeal", "experienced"])
def test_no_mask_leaves_the_containers_and_rvs_exactly_as_they_were(cfg_pri, head):
    """Serving never passes conf_missing. With nothing masked the model must be the
    one that existed before the mask did -- no `__present` container, no extra RV."""
    cfg, pri = cfg_pri
    person, env, conf = _inputs()
    outcome = (np.array([0, 1] * (N // 2)) if head == "appeal"
               else np.array([1, 2, 3, 4, 5] + [3] * (N - 5)))

    expected_rvs = (EXPECTED_APPEAL_RVS if head == "appeal"
                    else EXPECTED_EXPERIENCED_RVS)

    for conf_missing in (None, {k: np.zeros(N, dtype=bool) for k in conf}):
        model = bm.build_model(person, env, conf, cfg, pri, outcome=outcome,
                               head=head, conf_missing=conf_missing)
        assert {v.name for v in model.data_vars} == EXPECTED_DATA_NO_MASK
        assert {v.name for v in model.free_RVs} == expected_rvs
        assert not any(name.endswith("__present") for name in model.named_vars)


# ---------------------------------------------------------------------------
# 7. Masked data must teach the masked weight NOTHING
#
# The slowest test in this file by a wide margin (a real NUTS fit), and the one
# that would actually catch a wrong sign or a leaked placeholder: if a masked row
# contributed w_industry[0], 200 rows of it would drag that level's posterior off
# its prior. `industry` is masked on every row here, so every one of the five
# levels must come back at Normal(0, 1) -- the prior, untouched.
# ---------------------------------------------------------------------------

FIT_N = 200
TRUE_INDUSTRY_W = np.array([1.3, -0.9, 0.5, 2.1, -1.7])


def test_a_short_fit_with_industry_masked_leaves_its_weight_at_the_prior(cfg_pri):
    import arviz as az
    from match_core import ordinal_probs, outcome_logit, preprocess_conf

    cfg, pri = cfg_pri
    person, env, conf, conf_missing = _masked_inputs(FIT_N, seed=11)

    # Generate ratings from a KNOWN z. The industry weights below are large and
    # distinct, but every row is masked, so none of them reaches z -- which is
    # the whole point: the data cannot carry information about them.
    true_weights = {
        "intercept": float(pri["intercept"]["mean"]),
        "dimensions": {d: {"mag": -1.0, "dir": 0.4} for d in DIMS},
        "confounders": {"stage_size": 0.0, "comp": 0.55,
                        "industry": TRUE_INDUSTRY_W},
    }
    processed = preprocess_conf(conf, cfg, conf_missing=conf_missing)
    assert processed["industry__present"].tolist() == [0.0] * FIT_N

    z = np.asarray(outcome_logit(person, env, processed, cfg, true_weights))
    probs = ordinal_probs(z, np.array([-3.0, -1.5, 0.0, 1.5]))
    rng = np.random.default_rng(5)
    outcome = np.array([rng.choice(5, p=row) + 1 for row in probs])

    idata = bm.fit_posterior(
        person, env, conf, outcome, cfg, pri, head="experienced",
        conf_missing=conf_missing,
        draws=300, tune=300, chains=2, cores=1, random_seed=17,
        progressbar=False, compute_convergence_checks=False,
    )

    divergences = int(idata.sample_stats["diverging"].values.sum())
    assert divergences == 0, "%d divergences" % divergences

    rhat = az.rhat(idata)
    worst = max(float(np.nanmax(rhat[name].values)) for name in rhat.data_vars)
    assert worst < 1.05, "worst r_hat %.4f" % worst

    # The prior is Normal(0, 1) per level (priors.yaml: industry mean 0, sd 1).
    post = idata.posterior["w_industry"].values.reshape(-1, 5)
    means = post.mean(axis=0)
    sds = post.std(axis=0, ddof=1)
    assert np.abs(means).max() < 0.15, "w_industry means moved: %s" % means.tolist()
    assert np.abs(sds - 1.0).max() < 0.15, "w_industry sds moved: %s" % sds.tolist()

    # ...and the weights that ARE supplied did learn something, so the assertion
    # above is about masking rather than about a fit that simply never ran.
    assert float(idata.posterior["w_comp"].values.std(ddof=1)) < 0.5


# ---------------------------------------------------------------------------
# 8. The flat_zones passthrough (C9, 2026-10-13)
#
# build_model(flat_zones=...) hands the person's tolerance to outcome_logit so
# the pre-registration's Look 2 hinge comparison can be FITTED. Two contracts:
# the default (None) is the model that existed before the argument did, and a
# zone that is given reaches the predictor and prices the gap exactly as the
# numpy serving path (match_core.point_p_fit) prices it.
# ---------------------------------------------------------------------------

FLOOR_ZONES = {d: (0.15, 0.15) for d in DIMS}


def _p_fit_at_prior_means(model):
    """p_fit evaluated at the model's initial point: every Normal weight at its mean."""
    point = model.initial_point()
    givens = {model[name]: value for name, value in point.items() if name in model.named_vars}
    return np.asarray(model["p_fit"].eval(givens), dtype=float)


@pytest.mark.parametrize("head", ["appeal", "experienced"])
def test_flat_zones_default_is_the_model_that_existed_before_the_argument(cfg_pri, head):
    cfg, pri = cfg_pri
    person, env, conf = _inputs()
    outcome = (np.array([0, 1] * (N // 2)) if head == "appeal"
               else np.array([1, 2, 3, 4, 5] + [3] * (N - 5)))

    before = bm.build_model(person, env, conf, cfg, pri, outcome=outcome, head=head)
    after = bm.build_model(person, env, conf, cfg, pri, outcome=outcome, head=head,
                           flat_zones=None)

    assert {v.name for v in before.data_vars} == {v.name for v in after.data_vars}
    assert {v.name for v in before.free_RVs} == {v.name for v in after.free_RVs}
    assert {v.name for v in before.observed_RVs} == {v.name for v in after.observed_RVs}
    np.testing.assert_array_equal(_p_fit_at_prior_means(before), _p_fit_at_prior_means(after))

    a = np.asarray(bm.prior_predictive(person, env, conf, cfg, pri, draws=50,
                                       random_seed=7, head=head))
    b = np.asarray(bm.prior_predictive(person, env, conf, cfg, pri, draws=50,
                                       random_seed=7, head=head, flat_zones=None))
    np.testing.assert_array_equal(a, b)


def test_flat_zones_reach_the_predictor_and_agree_with_the_numpy_serving_path(cfg_pri):
    """The PyMC graph with a zone prices every row exactly as match_core.point_p_fit
    does with the same zone -- the fit and the serving path read one hinge."""
    from match_core import point_p_fit, weights_from_priors

    cfg, pri = cfg_pri
    person, env, conf = _inputs(seed=3)
    weights = weights_from_priors(cfg, pri)

    linear = _p_fit_at_prior_means(bm.build_model(person, env, conf, cfg, pri))
    hinged = _p_fit_at_prior_means(
        bm.build_model(person, env, conf, cfg, pri, flat_zones=FLOOR_ZONES))
    assert not np.array_equal(linear, hinged), "the zone never reached the predictor"

    np.testing.assert_allclose(
        hinged, point_p_fit(person, env, conf, cfg, weights, flat_zones=FLOOR_ZONES),
        rtol=0, atol=1e-12,
    )
    np.testing.assert_allclose(
        linear, point_p_fit(person, env, conf, cfg, weights), rtol=0, atol=1e-12,
    )

    # A per-row zone (each person's own tolerance) is accepted by the graph too.
    rng = np.random.default_rng(1)
    per_row = {d: (rng.choice([0.15, 0.25, 0.5], N), rng.choice([0.15, 0.25, 0.5], N))
               for d in DIMS}
    np.testing.assert_allclose(
        _p_fit_at_prior_means(bm.build_model(person, env, conf, cfg, pri, flat_zones=per_row)),
        point_p_fit(person, env, conf, cfg, weights, flat_zones=per_row),
        rtol=0, atol=1e-12,
    )


def test_an_invalid_zone_is_refused_at_build_time(cfg_pri):
    cfg, pri = cfg_pri
    person, env, conf = _inputs()
    with pytest.raises(ValueError, match="flat_zones must carry exactly"):
        bm.build_model(person, env, conf, cfg, pri, flat_zones={"pace": (0.15, 0.15)})
