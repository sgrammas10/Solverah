"""The hinge, the unknown-trait mask, point_z, and the penalty table's reasons --
C2 of the CompanyLens six-trait build (PRODUCT_DECISIONS.md section 2, 2026-10-13).

Four contracts:

1. BIT-IDENTITY. With no flat zone and no env mask, point_p_fit / score_pairs /
   outcome_logit produce exactly what HEAD produced -- pinned against VERBATIM copies
   of the pre-change functions on hundreds of random rows, the way
   tests/test_ordinal_head.py pins the industry mask. Every existing caller (the
   Situation Report's weights, devfit, explain_user) runs this path.

2. THE POLE IS SACRED. Julie's twelve dimension answers were elicited at |gap| = 0.8,
   so under ANY flat zone a pole gap must still cost exactly what she said. That is
   what the rescaling in match_core.excess_gap exists for, and it is checked here
   against her answers as numbers out of ten, not against the converter's output.

3. THE ZONE IS FLAT, AND DIRECTED. Inside the zone a dimension costs nothing, exactly;
   gap > 0 (env provides less than wanted) reads the UNDER zone and gap < 0 the OVER
   zone; outside the zone the cost grows and never exceeds the linear cost.

4. THE MASK EXCLUDES THE TERM. A dimension whose env score is unknown contributes
   exactly 0 to z, its NaN never reaches the arithmetic, and an unmasked NaN raises.

Plus: priors.yaml carries `why` and `date` on every weight entry, and the numbers are
the ones her answers reproduce (contract 2 is the byte-identity guard on the table).
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
import yaml

import match_scoring  # noqa: F401  -- installs causal_graph/v1_model on sys.path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "causal_graph" / "v1_model"
LIVE_PRIORS = MODEL_DIR / "priors.yaml"
NEUTRAL_PRIORS = MODEL_DIR / "priors_placeholder.yaml"

DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]

#: Julie's twelve answers (2026-09-17), out of ten: (person-high/role-low,
#: person-low/role-high). In match_core's convention gap = person - env, so the
#: first is gap = +0.8 and the second gap = -0.8.
JULIE = {
    "autonomy": (7, 7),
    "pace": (3, 4),
    "collaboration": (7, 6),
    "feedback": (7, 3),
    "innovation": (5, 5),
    "decision": (8, 5),
}

#: Confounders that contribute exactly 0 at point weights: stage_size 3.0 and comp 3.0
#: standardize to 0 under the config's fixed scales; "tech" indexes a weight whose live
#: prior mean is 0.
NEUTRAL_CONF = {"stage_size": [3.0], "comp": [3.0], "industry": ["tech"]}


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def _load_yaml(path):
    with io.open(path, encoding="ascii") as f:
        return yaml.safe_load(f)


def _live():
    from match_core import load, weights_from_priors

    cfg, pri = load()
    return cfg, weights_from_priors(cfg, pri)


def _neutral():
    from match_core import load, weights_from_priors

    cfg, pri = load(pri_path=str(NEUTRAL_PRIORS))
    return cfg, weights_from_priors(cfg, pri)


def _zones(under, over=None):
    over = under if over is None else over
    return {d: (under, over) for d in DIMS}


def _conf(n):
    return {"stage_size": [3.0] * n, "comp": [3.0] * n, "industry": ["tech"] * n}


# ---------------------------------------------------------------------------
# 1. BIT-IDENTITY against verbatim copies of the pre-2026-10-13 code
# ---------------------------------------------------------------------------

def _head_outcome_logit(person, env, conf, cfg, weights, snap_person=True):
    """VERBATIM match_core.outcome_logit at HEAD (commit 2010721), before flat_zones
    and env_missing existed. A re-derivation would not catch a change in what it did."""
    from match_core import active, fit_gap

    feats = cfg["settings"]["gap_features"]     # e.g. ["mag", "dir"]
    z = weights["intercept"]

    for d in active(cfg["dimensions"]):
        k = d["key"]
        g = fit_gap(person[k], env[k], snap_person=snap_person)
        w = weights["dimensions"][k]
        if "mag" in feats:
            z += w["mag"] * abs(g)              # any mismatch hurts (symmetric)
        if "dir" in feats:
            z += w["dir"] * g                   # directional asymmetry
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue                            # unmeasurable -> not a term
        k = c["key"]
        w = weights["confounders"][k]
        if c.get("kind") == "categorical":
            term = w[conf[k]]                   # one weight per level
            present = conf.get(k + "__present")
            z += term if present is None else term * present
        else:
            z += w * conf.get(k, 0.0)

    return z


def _head_point_p_fit(person, env, conf_raw, cfg, weights, conf_missing=None):
    """VERBATIM match_core.point_p_fit at HEAD."""
    from match_core import _validate_inputs, point_weights, preprocess_conf

    _validate_inputs(person, env, conf_raw, cfg)
    conf = preprocess_conf(conf_raw, cfg, conf_missing=conf_missing)
    z = _head_outcome_logit(person, env, conf, cfg, point_weights(weights), snap_person=True)
    return _sigmoid(z)


def _head_score_pairs(person, env, conf_raw, cfg, weights, draws=2000, seed=0,
                      interval=0.90, conf_missing=None):
    """VERBATIM match_core.score_pairs at HEAD."""
    from match_core import _draw_weights, _validate_inputs, preprocess_conf

    _validate_inputs(person, env, conf_raw, cfg)
    conf = preprocess_conf(conf_raw, cfg, conf_missing=conf_missing)
    rng = np.random.default_rng(seed)

    p = np.empty((draws, len(np.atleast_1d(next(iter(person.values()))))))
    for i in range(draws):
        w = _draw_weights(weights, rng)
        p[i] = _sigmoid(_head_outcome_logit(person, env, conf, cfg, w, snap_person=True))

    tail = (1.0 - interval) / 2.0
    return {
        "p_fit": p.mean(axis=0),
        "p_fit_low": np.quantile(p, tail, axis=0),
        "p_fit_high": np.quantile(p, 1.0 - tail, axis=0),
    }


def _random_rows(n, seed):
    from match_core import COMPANY_LATTICE, PERSON_LATTICE

    rng = np.random.default_rng(seed)
    person = {d: rng.choice(PERSON_LATTICE, n) for d in DIMS}
    env = {d: rng.choice(COMPANY_LATTICE, n) for d in DIMS}
    conf = {
        "stage_size": rng.uniform(1.0, 5.0, n),
        "comp": rng.integers(1, 6, n).astype(float),
        "industry": rng.choice(["tech", "finance", "healthcare", "retail", "other"], n),
    }
    return person, env, conf


@pytest.mark.parametrize("seed", [0, 1])
def test_no_zone_no_mask_is_bit_identical_to_head_on_random_rows(seed):
    from match_core import outcome_logit, point_p_fit, point_weights, preprocess_conf

    cfg, weights = _live()
    n = 500
    person, env, conf = _random_rows(n, seed)

    want = _head_point_p_fit(person, env, conf, cfg, weights)
    assert want.shape == (n,)
    np.testing.assert_array_equal(point_p_fit(person, env, conf, cfg, weights), want)
    # the new keyword arguments at their defaults are the same path ...
    np.testing.assert_array_equal(
        point_p_fit(person, env, conf, cfg, weights, conf_missing=None, flat_zones=None,
                    env_missing=None),
        want,
    )
    # ... and so is an all-False env mask, on one dimension or on all of them
    np.testing.assert_array_equal(
        point_p_fit(person, env, conf, cfg, weights,
                    env_missing={"pace": np.zeros(n, dtype=bool)}),
        want,
    )
    np.testing.assert_array_equal(
        point_p_fit(person, env, conf, cfg, weights,
                    env_missing={d: np.zeros(n, dtype=bool) for d in DIMS}),
        want,
    )
    # outcome_logit itself, on the raw predictor
    pre = preprocess_conf(conf, cfg)
    np.testing.assert_array_equal(
        np.asarray(outcome_logit(person, env, pre, cfg, point_weights(weights))),
        np.asarray(_head_outcome_logit(person, env, pre, cfg, point_weights(weights))),
    )


def test_no_zone_no_mask_score_pairs_band_is_bit_identical_to_head():
    from match_core import score_pairs

    cfg, weights = _live()
    person, env, conf = _random_rows(40, 7)
    want = _head_score_pairs(person, env, conf, cfg, weights, draws=60, seed=11)
    got = score_pairs(person, env, conf, cfg, weights, draws=60, seed=11)
    for key in ("p_fit", "p_fit_low", "p_fit_high"):
        np.testing.assert_array_equal(got[key], want[key])
    # a mask with nothing in it: the same draws, the same band
    got2 = score_pairs(person, env, conf, cfg, weights, draws=60, seed=11,
                       env_missing={"feedback": np.zeros(40, dtype=bool)})
    for key in ("p_fit", "p_fit_low", "p_fit_high"):
        np.testing.assert_array_equal(got2[key], want[key])


def test_sigmoid_of_point_z_is_point_p_fit_bitwise():
    """point_z is the ranking entry point; point_p_fit is its sigmoid and nothing
    else, with and without a zone."""
    from match_core import point_p_fit, point_z

    cfg, weights = _live()
    person, env, conf = _random_rows(200, 3)
    for zones in (None, _zones(0.15), _zones(0.5, 0.25)):
        z = point_z(person, env, conf, cfg, weights, flat_zones=zones)
        assert z.shape == (200,) and z.dtype == np.float64
        np.testing.assert_array_equal(
            _sigmoid(z), point_p_fit(person, env, conf, cfg, weights, flat_zones=zones)
        )


# ---------------------------------------------------------------------------
# 2. THE POLE IS SACRED -- Julie's twelve answers under any zone
# ---------------------------------------------------------------------------

def test_pole_gap_is_derived_from_the_lattices_and_is_the_converters_gap():
    from match_core import COMPANY_LATTICE, POLE_GAP, closest_achievable

    assert POLE_GAP == 0.8                       # convert_priors_response.GAP
    assert POLE_GAP == closest_achievable(1.0) - COMPANY_LATTICE.min()


def _pole_pairs(dim):
    """Two rows: person at the top of the ladder vs the lowest env (gap +0.8), and
    person at the bottom vs the highest env (gap -0.8); every other dimension a
    perfect mid match."""
    person = {d: [0.5, 0.5] for d in DIMS}
    env = {d: [0.5, 0.5] for d in DIMS}
    person[dim] = [1.0, 0.0]
    env[dim] = [0.1, 0.9]
    return person, env


ZONE_SETS = [
    None,
    _zones(0.15),
    _zones(0.25),
    _zones(0.5),
    _zones(0.5, 0.15),
    _zones(0.15, 0.5),
    {d: (0.15 + 0.05 * i, 0.5 - 0.05 * i) for i, d in enumerate(DIMS)},
]


@pytest.mark.parametrize("dim", DIMS)
@pytest.mark.parametrize("zones", ZONE_SETS)
def test_julies_twelve_answers_reproduce_under_any_zone(dim, zones):
    from match_core import point_p_fit

    cfg, weights = _live()
    person, env = _pole_pairs(dim)
    p = point_p_fit(person, env, _conf(2), cfg, weights, flat_zones=zones)
    high_low, low_high = JULIE[dim]
    # The converter rounded the weights to six decimals; the baseline alone is
    # off by ~4e-8. 1e-5 is far inside that and far outside any zone effect.
    assert p[0] == pytest.approx(high_low / 10.0, abs=1e-5), (dim, zones, p)
    assert p[1] == pytest.approx(low_high / 10.0, abs=1e-5), (dim, zones, p)


@pytest.mark.parametrize("dim", DIMS)
def test_a_pole_gap_costs_the_same_under_every_zone_bitwise(dim):
    """The rescaling divides the excess by the run (pole - zone) BEFORE multiplying
    by the pole, so at the pole the ratio is x / x == 1.0 and the hinged gap is the
    pole gap to the bit -- not merely close."""
    from match_core import point_z

    cfg, weights = _live()
    person, env = _pole_pairs(dim)
    linear = point_z(person, env, _conf(2), cfg, weights)
    for zones in ZONE_SETS[1:]:
        np.testing.assert_array_equal(
            point_z(person, env, _conf(2), cfg, weights, flat_zones=zones), linear
        )


# ---------------------------------------------------------------------------
# 3. THE ZONE IS FLAT, AND DIRECTED
# ---------------------------------------------------------------------------

def test_excess_gap_unit_behaviour():
    from match_core import POLE_GAP, excess_gap

    # the pole maps to the pole, both signs, every zone
    for zu, zo in ((0.0, 0.0), (0.15, 0.15), (0.5, 0.15), (0.15, 0.5), (0.79, 0.79)):
        assert excess_gap(POLE_GAP, zu, zo) == POLE_GAP
        assert excess_gap(-POLE_GAP, zu, zo) == -POLE_GAP
    # zero zone is the identity (the linear shape)
    g = np.linspace(-0.8, 0.8, 33)
    np.testing.assert_array_equal(excess_gap(g, 0.0, 0.0), g)
    # inside the zone: exactly 0, with the sign-appropriate zone
    assert excess_gap(0.1, 0.15, 0.15) == 0.0
    assert excess_gap(-0.1, 0.15, 0.15) == 0.0
    assert excess_gap(0.4, 0.5, 0.15) == 0.0        # +0.4 reads the UNDER zone (0.5)
    assert excess_gap(-0.4, 0.5, 0.15) != 0.0       # -0.4 reads the OVER zone (0.15)
    assert excess_gap(-0.4, 0.15, 0.5) == 0.0
    assert excess_gap(0.4, 0.15, 0.5) != 0.0
    # outside: (|g| - zone) * pole / (pole - zone), sign kept
    assert excess_gap(0.5, 0.15, 0.15) == pytest.approx((0.5 - 0.15) * 0.8 / 0.65)
    assert excess_gap(-0.5, 0.15, 0.15) == pytest.approx(-(0.5 - 0.15) * 0.8 / 0.65)
    # arrays, including per-row zones
    out = excess_gap(np.array([0.3, -0.3]), np.array([0.15, 0.5]), np.array([0.5, 0.15]))
    assert out[0] == pytest.approx((0.3 - 0.15) * 0.8 / 0.65)
    assert out[1] == pytest.approx(-(0.3 - 0.15) * 0.8 / 0.65)
    # never steeper than linear inside the pole
    hinged = excess_gap(g, 0.15, 0.15)
    assert (np.abs(hinged) <= np.abs(g) + 1e-15).all()


def test_a_gap_inside_a_half_zone_costs_exactly_nothing():
    """Zone 0.5 with |gap| 0.4 -> zero cost, both directions: P(fit) is the
    perfect-match value to the bit, not approximately."""
    from match_core import point_p_fit

    cfg, weights = _live()
    perfect = point_p_fit({d: [0.5] for d in DIMS}, {d: [0.5] for d in DIMS},
                          NEUTRAL_CONF, cfg, weights)
    person = {d: [0.5, 0.9] for d in DIMS}
    env = {d: [0.9, 0.5] for d in DIMS}          # gaps -0.4 (over) and +0.4 (under)
    p = point_p_fit(person, env, _conf(2), cfg, weights, flat_zones=_zones(0.5))
    np.testing.assert_array_equal(p, [perfect[0], perfect[0]])
    # and the same pair under the linear shape is a real cost, so the test can fail
    linear = point_p_fit(person, env, _conf(2), cfg, weights)
    assert (linear < perfect[0] - 0.1).all()


def test_the_zone_is_read_by_direction():
    """gap = person - env. +0.4 (env provides LESS than wanted) must read the UNDER
    zone; -0.4 (MORE) the OVER zone."""
    from match_core import point_p_fit

    cfg, weights = _live()
    perfect = point_p_fit({d: [0.5] for d in DIMS}, {d: [0.5] for d in DIMS},
                          NEUTRAL_CONF, cfg, weights)[0]
    under_only = _zones(0.5, 0.15)       # generous when the env provides less
    over_only = _zones(0.15, 0.5)        # generous when the env provides more

    less = ({d: [0.9] for d in DIMS}, {d: [0.5] for d in DIMS})   # gap +0.4
    more = ({d: [0.5] for d in DIMS}, {d: [0.9] for d in DIMS})   # gap -0.4

    assert point_p_fit(*less, NEUTRAL_CONF, cfg, weights, flat_zones=under_only)[0] == perfect
    assert point_p_fit(*less, NEUTRAL_CONF, cfg, weights, flat_zones=over_only)[0] < perfect
    assert point_p_fit(*more, NEUTRAL_CONF, cfg, weights, flat_zones=over_only)[0] == perfect
    assert point_p_fit(*more, NEUTRAL_CONF, cfg, weights, flat_zones=under_only)[0] < perfect


def test_cost_is_continuous_at_the_zone_edge_and_monotone_outside():
    from match_core import point_p_fit

    cfg, weights = _neutral()
    # person 0.9 vs env sliding down: gaps 0.0, 0.08, 0.16, ..., 0.8 after the snap
    env_values = [0.9, 0.82, 0.74, 0.66, 0.58, 0.5, 0.42, 0.34, 0.26, 0.18, 0.1]
    n = len(env_values)
    person = {d: [0.9] * n for d in DIMS}
    env = {d: list(env_values) for d in DIMS}
    p = point_p_fit(person, env, _conf(n), cfg, weights, flat_zones=_zones(0.25))
    # gaps 0.0, 0.08, 0.16, 0.24 are inside the 0.25 zone: all exactly the baseline
    assert p[0] == p[1] == p[2] == p[3] == 0.5
    # 0.32 is just outside; then strictly decreasing to the pole
    assert (np.diff(p[3:]) < 0).all()
    # the first step outside is the closed form -- six dimensions, each paying
    # the neutral mag (-1.0) on the rescaled excess (0.32 - 0.25) * 0.8 / 0.55 --
    # and starts from zero rather than jumping: it is well under the linear cost
    excess = (0.32 - 0.25) * 0.8 / (0.8 - 0.25)
    assert p[4] == pytest.approx(_sigmoid(6 * -1.0 * excess), abs=1e-9)
    assert p[4] > _sigmoid(6 * -1.0 * 0.32)
    # and at the pole the hinge and the linear shape agree
    linear = point_p_fit(person, env, _conf(n), cfg, weights)
    assert p[-1] == linear[-1]


def test_the_additivity_illustration_softens_from_three_to_seven_in_ten():
    """The number that motivated the hinge (ordinal-head memo, 2026-09-17): a 0.2
    gap on all six, person wanting less than the role offers, is ~3.3/10 under the
    linear shape and ~6.8/10 under the 0.15 hinge."""
    from match_core import point_p_fit

    cfg, weights = _live()
    person = {d: [0.5] for d in DIMS}
    env = {d: [0.7] for d in DIMS}                # gap -0.2 on all six
    linear = point_p_fit(person, env, NEUTRAL_CONF, cfg, weights)[0]
    hinged = point_p_fit(person, env, NEUTRAL_CONF, cfg, weights, flat_zones=_zones(0.15))[0]
    assert linear == pytest.approx(0.333, abs=0.005)
    assert hinged == pytest.approx(0.678, abs=0.005)


def test_hinge_never_costs_more_than_linear_within_the_pole():
    from match_core import point_z

    cfg, weights = _live()
    person, env, conf = _random_rows(300, 5)
    linear = point_z(person, env, conf, cfg, weights)
    for zones in ZONE_SETS[1:]:
        hinged = point_z(person, env, conf, cfg, weights, flat_zones=zones)
        assert (hinged >= linear - 1e-12).all()


def test_score_pairs_band_under_a_zone_is_deterministic_and_ordered():
    from match_core import score_pairs

    cfg, weights = _live()
    person = {d: [0.5, 0.5] for d in DIMS}
    env = {d: [0.7, 0.9] for d in DIMS}
    a = score_pairs(person, env, _conf(2), cfg, weights, draws=200, seed=2,
                    flat_zones=_zones(0.15))
    b = score_pairs(person, env, _conf(2), cfg, weights, draws=200, seed=2,
                    flat_zones=_zones(0.15))
    for key in ("p_fit", "p_fit_low", "p_fit_high"):
        np.testing.assert_array_equal(a[key], b[key])
    assert (a["p_fit_low"] < a["p_fit"]).all() and (a["p_fit"] < a["p_fit_high"]).all()
    # the band of the hinged predictor, not the linear one
    lin = score_pairs(person, env, _conf(2), cfg, weights, draws=200, seed=2)
    assert (a["p_fit"] > lin["p_fit"]).all()


def test_per_row_zones_are_accepted_and_applied_per_row():
    from match_core import point_p_fit

    cfg, weights = _live()
    perfect = point_p_fit({d: [0.5] for d in DIMS}, {d: [0.5] for d in DIMS},
                          NEUTRAL_CONF, cfg, weights)[0]
    person = {d: [0.5, 0.5] for d in DIMS}
    env = {d: [0.9, 0.9] for d in DIMS}           # gap -0.4 on both rows
    zones = {d: (np.array([0.15, 0.15]), np.array([0.5, 0.15])) for d in DIMS}
    p = point_p_fit(person, env, _conf(2), cfg, weights, flat_zones=zones)
    assert p[0] == perfect                          # row 0: over zone 0.5 covers it
    assert p[1] < perfect                           # row 1: over zone 0.15 does not


@pytest.mark.parametrize("bad", [-0.01, 0.8, 1.0, float("nan"), float("inf")])
def test_an_invalid_zone_raises(bad):
    from match_core import point_p_fit

    cfg, weights = _live()
    person = {d: [0.5] for d in DIMS}
    env = {d: [0.5] for d in DIMS}
    zones = _zones(0.15)
    zones["pace"] = (bad, 0.15)
    with pytest.raises(ValueError) as exc:
        point_p_fit(person, env, NEUTRAL_CONF, cfg, weights, flat_zones=zones)
    assert "pace" in str(exc.value)
    zones["pace"] = (0.15, bad)
    with pytest.raises(ValueError):
        point_p_fit(person, env, NEUTRAL_CONF, cfg, weights, flat_zones=zones)


def test_a_partial_or_oversized_zone_dict_raises():
    from match_core import point_p_fit

    cfg, weights = _live()
    person = {d: [0.5] for d in DIMS}
    env = {d: [0.5] for d in DIMS}

    missing = _zones(0.15)
    del missing["decision"]
    with pytest.raises(ValueError, match="decision"):
        point_p_fit(person, env, NEUTRAL_CONF, cfg, weights, flat_zones=missing)

    extra = _zones(0.15)
    extra["structure"] = (0.15, 0.15)              # an inactive dimension
    with pytest.raises(ValueError, match="structure"):
        point_p_fit(person, env, NEUTRAL_CONF, cfg, weights, flat_zones=extra)

    not_a_pair = _zones(0.15)
    not_a_pair["pace"] = 0.15
    with pytest.raises(ValueError, match="pace"):
        point_p_fit(person, env, NEUTRAL_CONF, cfg, weights, flat_zones=not_a_pair)

    wrong_length = _zones(0.15)
    wrong_length["pace"] = (np.array([0.15, 0.15, 0.15]), 0.15)   # N is 1
    with pytest.raises(ValueError, match="length"):
        point_p_fit(person, env, NEUTRAL_CONF, cfg, weights, flat_zones=wrong_length)


# ---------------------------------------------------------------------------
# 4. THE MASK EXCLUDES THE TERM
# ---------------------------------------------------------------------------

def test_a_masked_dimension_contributes_exactly_zero():
    """With pace unknown (NaN under a mask), z equals z with pace's weights zeroed
    on finite env -- checked with pace's LIVE weights, the largest she gave, so a
    leak would be loud."""
    from match_core import point_z

    cfg, weights = _live()
    n = 4
    person, env, conf = _random_rows(n, 9)
    env_known = {d: np.array(env[d], dtype=float) for d in DIMS}
    env_unknown = dict(env_known)
    env_unknown["pace"] = np.full(n, np.nan)

    masked = point_z(person, env_unknown, conf, cfg, weights,
                     env_missing={"pace": np.ones(n, dtype=bool)})

    zeroed = {**weights, "dimensions": dict(weights["dimensions"])}
    zeroed["dimensions"]["pace"] = {"mag": {"mean": 0.0, "sd": 0.0},
                                    "dir": {"mean": 0.0, "sd": 0.0}}
    np.testing.assert_array_equal(masked, point_z(person, env_known, conf, cfg, zeroed))
    # the weights really are live: unmasked, pace moves z
    assert not np.array_equal(masked, point_z(person, env_known, conf, cfg, weights))


def test_a_partial_mask_changes_only_the_masked_rows():
    from match_core import point_z

    cfg, weights = _live()
    n = 6
    person, env, conf = _random_rows(n, 13)
    env = {d: np.array(env[d], dtype=float) for d in DIMS}
    base = point_z(person, env, conf, cfg, weights)

    mask = np.array([False, True, False, False, True, False])
    env_holes = dict(env)
    env_holes["feedback"] = np.where(mask, np.nan, env["feedback"])
    got = point_z(person, env_holes, conf, cfg, weights, env_missing={"feedback": mask})

    # known rows under a mask are BIT-identical to the unmasked path (x * 1.0 == x)
    np.testing.assert_array_equal(got[~mask], base[~mask])
    # masked rows lose exactly feedback's term: equal to z with feedback zeroed
    zeroed = {**weights, "dimensions": dict(weights["dimensions"])}
    zeroed["dimensions"]["feedback"] = {"mag": {"mean": 0.0, "sd": 0.0},
                                        "dir": {"mean": 0.0, "sd": 0.0}}
    without = point_z(person, env, conf, cfg, zeroed)
    np.testing.assert_array_equal(got[mask], without[mask])


def test_mask_and_zone_compose():
    """A masked dimension stays out under a zone; the others are hinged."""
    from match_core import point_z

    cfg, weights = _live()
    person = {d: [0.5] for d in DIMS}
    env = {d: [0.7] for d in DIMS}                # gap -0.2 everywhere
    env["innovation"] = [np.nan]
    mask = {"innovation": np.array([True])}
    zoned_masked = point_z(person, env, NEUTRAL_CONF, cfg, weights,
                           flat_zones=_zones(0.5), env_missing=mask)
    # every known gap (0.2) is inside the 0.5 zone, innovation is excluded: z is
    # exactly the intercept
    assert zoned_masked[0] == weights["intercept"]["mean"]


def test_all_six_masked_leaves_only_the_intercept_and_confounders():
    from match_core import point_z

    cfg, weights = _live()
    person = {d: [0.0, 1.0] for d in DIMS}
    env = {d: [np.nan, np.nan] for d in DIMS}
    z = point_z(person, env, _conf(2), cfg, weights,
                env_missing={d: np.array([True, True]) for d in DIMS})
    np.testing.assert_array_equal(z, [weights["intercept"]["mean"]] * 2)


def test_an_unmasked_nan_env_raises_and_names_the_dimension():
    from match_core import point_p_fit

    cfg, weights = _live()
    person = {d: [0.5, 0.5] for d in DIMS}
    env = {d: [0.5, 0.5] for d in DIMS}
    env["collaboration"] = [np.nan, 0.5]
    with pytest.raises(ValueError) as exc:
        point_p_fit(person, env, _conf(2), cfg, weights)
    assert "collaboration" in str(exc.value) and "[0]" in str(exc.value)
    # a mask on the wrong row is just as wrong
    with pytest.raises(ValueError):
        point_p_fit(person, env, _conf(2), cfg, weights,
                    env_missing={"collaboration": np.array([False, True])})


def test_a_mask_on_an_unknown_dimension_or_of_the_wrong_length_raises():
    from match_core import point_p_fit

    cfg, weights = _live()
    person = {d: [0.5] for d in DIMS}
    env = {d: [0.5] for d in DIMS}
    with pytest.raises(ValueError, match="structure"):
        point_p_fit(person, env, NEUTRAL_CONF, cfg, weights,
                    env_missing={"structure": np.array([True])})
    with pytest.raises(ValueError, match="length"):
        point_p_fit(person, env, NEUTRAL_CONF, cfg, weights,
                    env_missing={"pace": np.array([True, True, True])})


# ---------------------------------------------------------------------------
# 5. The doorway passes everything through
# ---------------------------------------------------------------------------

def test_match_scoring_passes_zones_and_masks_through_the_current_run(client):
    from app import app
    from match_scoring import (score_with_current_run, seed_priors_model_run,
                               z_with_current_run)
    from model import db

    with app.app_context():
        seed_priors_model_run(db)
        db.session.commit()

        person = {d: [0.5, 0.5] for d in DIMS}
        env = {d: [0.9, 0.5] for d in DIMS}       # gap -0.4, then a perfect match
        run, scores = score_with_current_run(db, person, env, _conf(2), draws=100, seed=4,
                                             flat_zones=_zones(0.5))
        assert run.model_version == "v1-priors-only"
        # inside the half zone the mismatched row prices exactly like the perfect one
        for key in ("p_fit", "p_fit_low", "p_fit_high"):
            assert scores[key][0] == scores[key][1]

        run_z, z = z_with_current_run(db, person, env, _conf(2), flat_zones=_zones(0.5))
        assert run_z.id == run.id
        assert z.shape == (2,) and z[0] == z[1]
        _, z_lin = z_with_current_run(db, person, env, _conf(2))
        assert z_lin[0] < z_lin[1]                 # linear: the mismatch costs

        # the mask reaches the predictor too
        holes = {d: [0.9, 0.5] for d in DIMS}
        holes["pace"] = [np.nan, 0.5]
        _, z_masked = z_with_current_run(db, person, holes, _conf(2),
                                         env_missing={"pace": np.array([True, False])})
        assert z_masked[1] == z_lin[1]
        assert z_masked[0] > z_lin[0]              # pace (her costliest) is excluded


# ---------------------------------------------------------------------------
# 6. The penalty table carries its reasons
# ---------------------------------------------------------------------------

def _weight_entries(pri):
    yield "intercept", pri["intercept"]
    for dim, feats in pri["dimensions"].items():
        for feat, entry in feats.items():
            yield f"dimensions.{dim}.{feat}", entry
    for key, entry in pri["confounders"].items():
        yield f"confounders.{key}", entry
    yield "cutpoints.spacing", pri["cutpoints"]["spacing"]


def test_every_live_priors_entry_carries_a_why_and_a_date():
    pri = _load_yaml(LIVE_PRIORS)
    entries = dict(_weight_entries(pri))
    assert len(entries) == 1 + 12 + 3 + 1
    for name, entry in entries.items():
        assert isinstance(entry.get("why"), str) and entry["why"].strip(), name
        date = entry.get("date")
        assert isinstance(date, str), (name, date)     # quoted: a str, not a date
        assert len(date) == 10 and date[4] == "-" and date[7] == "-", (name, date)
    # the elicited ones say so, and say when
    for dim in DIMS:
        for feat in ("mag", "dir"):
            entry = entries[f"dimensions.{dim}.{feat}"]
            assert entry["date"] == "2026-09-17", (dim, feat)
    assert entries["intercept"]["date"] == "2026-09-17"
    # the converter's constants are owned up to
    assert "converter" in entries["intercept"]["why"]
    assert "converter" in entries["confounders.stage_size"]["why"]
    assert "Placeholder" in entries["cutpoints.spacing"]["why"]


def test_the_why_keys_leave_every_loader_untouched():
    """weights_from_priors, flatten_weights and the placeholder fixture read mean/sd
    and ignore the rest: still 20 rows, still neutral, still equal cutpoints."""
    from match_core import flatten_weights, load, weights_from_priors

    for path in (LIVE_PRIORS, NEUTRAL_PRIORS):
        cfg, pri = load(pri_path=str(path))
        rows = flatten_weights(cfg, weights_from_priors(cfg, pri))
        assert len(rows) == 20
        assert all(isinstance(m, float) and isinstance(s, float) for _, m, s in rows)
    live = _load_yaml(LIVE_PRIORS)
    neutral = _load_yaml(NEUTRAL_PRIORS)
    assert live["cutpoints"] == neutral["cutpoints"]
    # the record file gained nothing but the shared cutpoint keys
    for name, entry in _weight_entries(neutral):
        if name != "cutpoints.spacing":
            assert set(entry) == {"mean", "sd"}, name
