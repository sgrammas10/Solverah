"""Tests for the ordered-outcome head -- the numpy half, which is what this suite can run.

`experienced` (1..5, "overall, how well is this role working for you") is the only
outcome the environment-report source produces, and D-20 locks it to an OrderedLogistic
likelihood -- never dichotomized into the Bernoulli path. The PyMC side of that head
lives in causal_graph/v1_model/build_model.py and is tested next to it
(causal_graph/v1_model/test_ordinal_head.py), because this suite's interpreter has no
pymc and CI does not install one. What IS testable here is the part that has to be true
for the expert's priors to keep their meaning:

    THE MAPPING.  priors.yaml's weights were elicited on a binary scale --
    sigmoid(z) = P(still doing well after a year), "doing well" being a rating of 4 or 5.
    build_model pins the cutpoint between ratings 3 and 4 at exactly 0, which makes

        P(rating >= 4) == sigmoid(z)

    an identity. match_core.ordinal_probs is the numpy twin of pymc's OrderedLogistic
    and is what serving will read, so the identity is pinned here against a grid of z
    rather than at one convenient point.

Also here: preprocess_conf's NULL-confounder handling, the other blocker
ASSEMBLE_TRAINING_DATA_NOTES.md named between the environment rows and a fit.
"""

import io
from pathlib import Path

import numpy as np
import pytest
import yaml

import match_scoring  # noqa: F401  -- installs causal_graph/v1_model on sys.path, making
                      # `from match_core import ...` valid regardless of test order

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "causal_graph" / "v1_model"
LIVE_PRIORS = MODEL_DIR / "priors.yaml"
NEUTRAL_PRIORS = MODEL_DIR / "priors_placeholder.yaml"

DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]

#: Julie's elicited baseline: a well-matched person was put at 8 in 10 still doing well
#: a year later. That is the number the whole pin exists to preserve.
DOING_WELL_BASELINE = 0.8

#: The cutpoint vector at the prior's central spacing (exp(0.405465) = 1.5), with the
#: rating-3/rating-4 boundary pinned at 0. Shape and pin, not the sampled values.
CUTPOINTS = np.array([-3.0, -1.5, 0.0, 1.5])


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def _load_yaml(path):
    with io.open(path, encoding="ascii") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 1. ordinal_probs is a probability distribution
# ---------------------------------------------------------------------------

def test_ordinal_probs_rows_are_distributions():
    from match_core import ordinal_probs

    z = np.linspace(-6.0, 6.0, 41)
    p = ordinal_probs(z, CUTPOINTS)

    assert p.shape == (41, 5)
    assert (p >= 0.0).all()
    np.testing.assert_allclose(p.sum(axis=-1), 1.0, atol=1e-12)


def test_ordinal_probs_accepts_a_scalar():
    from match_core import ordinal_probs

    p = ordinal_probs(0.0, CUTPOINTS)
    assert p.shape == (5,)
    np.testing.assert_allclose(p.sum(), 1.0, atol=1e-12)


# ---------------------------------------------------------------------------
# 2. THE MAPPING -- P(rating >= 4) == sigmoid(z), exactly, everywhere
# ---------------------------------------------------------------------------

def test_p_doing_well_equals_sigmoid_of_z():
    """The identity the whole design rests on. With the rating-3/4 cutpoint pinned at 0,
    the top two ordinal levels carry exactly the binary head's probability -- so the
    expert's logit-scale weights need no rescaling to serve the ordinal head, and
    sigmoid(z) in the serving path goes on meaning what it meant."""
    from match_core import ordinal_probs

    z = np.linspace(-8.0, 8.0, 161)
    p = ordinal_probs(z, CUTPOINTS)

    np.testing.assert_allclose(p[..., 3] + p[..., 4], _sigmoid(z), atol=1e-12, rtol=0)


def test_mapping_holds_for_any_free_spacings():
    """The identity comes from the PIN alone, not from the spacings being 1.5. Vary the
    three free spacings widely; only the middle cutpoint staying at 0 matters."""
    from match_core import ordinal_probs

    rng = np.random.default_rng(0)
    z = np.linspace(-5.0, 5.0, 21)
    for _ in range(25):
        d_low1, d_low2, d_high = rng.lognormal(0.405465, 0.5, size=3)
        cutpoints = np.array([-(d_low1 + d_low2), -d_low2, 0.0, d_high])
        assert np.all(np.diff(cutpoints) > 0)          # ascending by construction
        p = ordinal_probs(z, cutpoints)
        np.testing.assert_allclose(
            p[..., 3:].sum(axis=-1), _sigmoid(z), atol=1e-12, rtol=0
        )


def test_higher_z_never_lowers_any_upper_tail():
    """Monotonicity: a better-fitting pair can never be given a lower probability of
    reaching rating k or above, for any k."""
    from match_core import ordinal_probs

    z = np.linspace(-6.0, 6.0, 121)
    p = ordinal_probs(z, CUTPOINTS)
    # upper tails P(Y >= k) for k = 2..5, one column each
    tails = np.cumsum(p[:, ::-1], axis=-1)[:, ::-1][:, 1:]
    diffs = np.diff(tails, axis=0)
    assert (diffs >= -1e-15).all(), "P(Y >= k) fell as z rose"


# ---------------------------------------------------------------------------
# 3. The LIVE priors land on the expert's own baseline
# ---------------------------------------------------------------------------

def test_live_intercept_reproduces_the_elicited_baseline():
    """A perfectly matched person under the live priors: every gap is 0, so z is the
    intercept alone, and the ordinal head must put them at 8 in 10 doing well -- the
    exact answer the intercept was elicited from."""
    from match_core import ordinal_probs

    pri = _load_yaml(LIVE_PRIORS)
    z = float(pri["intercept"]["mean"])

    p = ordinal_probs(z, CUTPOINTS)
    assert p[3] + p[4] == pytest.approx(DOING_WELL_BASELINE, abs=1e-6)


# ---------------------------------------------------------------------------
# 4. Both priors files carry the cutpoint block, identically, in ASCII
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [LIVE_PRIORS, NEUTRAL_PRIORS])
def test_priors_file_is_ascii(path):
    """match_core.load() opens these with no encoding= argument, which on the dev
    machine means cp1252. Keeping them ASCII is what makes that harmless."""
    path.read_bytes().decode("ascii")


@pytest.mark.parametrize("path", [LIVE_PRIORS, NEUTRAL_PRIORS])
def test_priors_file_carries_the_cutpoint_block(path):
    pri = _load_yaml(path)
    spacing = pri["cutpoints"]["spacing"]
    assert spacing["mu_log"] == pytest.approx(np.log(1.5), abs=1e-5)
    assert spacing["sigma_log"] > 0


def test_both_priors_files_agree_on_the_cutpoints():
    """The cutpoint priors are structural, not elicited -- the live file and the neutral
    test fixture must not drift apart on them, or the fixture stops testing the model
    that actually serves."""
    assert _load_yaml(LIVE_PRIORS)["cutpoints"] == _load_yaml(NEUTRAL_PRIORS)["cutpoints"]


def test_cutpoint_block_did_not_disturb_the_weights():
    """weights_from_priors reads three top-level keys and ignores the rest. Pinned
    because the flat weight naming is a database interface: 20 rows, no more."""
    from match_core import flatten_weights, load, weights_from_priors

    for path in (LIVE_PRIORS, NEUTRAL_PRIORS):
        cfg, pri = load(pri_path=str(path))
        rows = flatten_weights(cfg, weights_from_priors(cfg, pri))
        assert len(rows) == 20
        assert not any("cut" in name for name, _, _ in rows)


# ---------------------------------------------------------------------------
# 5. The config's two heads
# ---------------------------------------------------------------------------

def test_config_declares_both_heads_and_keeps_the_legacy_alias():
    from match_core import load

    cfg, _ = load()
    heads = cfg["settings"]["heads"]

    # the legacy alias every existing reader (recovery_multiseed.py) still uses
    assert cfg["settings"]["outcome"] == heads["appeal"]

    experienced = heads["experienced"]
    assert experienced["type"] == "ordinal"
    assert experienced["link"] == "ordered_logistic"
    assert experienced["levels"] == 5
    assert experienced["doing_well_at"] == 4


# ---------------------------------------------------------------------------
# 6. preprocess_conf: the NULL-confounder blocker
# ---------------------------------------------------------------------------

CONF_RAW = {"stage_size": [1.0, 3.0, 5.0], "comp": [2.0, 3.0, 4.0], "industry": ["tech"] * 3}


def _cfg():
    from match_core import load

    return load()[0]


def test_default_path_is_unchanged():
    """No mask, no NaN: bit-identical to the pre-change output. score_pairs() and
    point_p_fit() run this on every request, so 'bit-identical' is the requirement, not
    'close'."""
    from match_core import preprocess_conf

    cfg = _cfg()
    expected = {
        # (raw - mean) / sd with the config's fixed scales
        "stage_size": (np.array([1.0, 3.0, 5.0]) - 3.0) / 1.5,
        "comp": (np.array([2.0, 3.0, 4.0]) - 3.0) / 1.0,
        "industry": np.array([0, 0, 0], dtype="int64"),
    }
    out = preprocess_conf(CONF_RAW, cfg)

    assert set(out) == set(expected)
    for key, want in expected.items():
        assert out[key].tolist() == want.tolist()
        assert out[key].dtype == want.dtype

    # and passing an explicit all-False mask changes nothing -- including adding no
    # "__present" companion array for the categorical (2026-09-21): a mask with no
    # True in it must leave serving on the exact pre-mask path.
    masked = preprocess_conf(
        CONF_RAW, cfg, conf_missing={k: np.zeros(3, dtype=bool) for k in CONF_RAW}
    )
    assert set(masked) == set(expected)
    for key in expected:
        assert masked[key].tolist() == out[key].tolist()
        assert masked[key].dtype == out[key].dtype


def test_masked_continuous_value_drops_the_term():
    """A 'not sure' comp is a signed product ruling, so the row stays in the training
    set carrying NaN plus a mask. The model's ruling (2026-09-17) is to exclude the
    term: the standardized value becomes exactly 0.0, and since the confounder enters
    the logit as w * value, the row's comp term vanishes from z."""
    from match_core import outcome_logit, preprocess_conf

    cfg = _cfg()
    conf = {"stage_size": [3.0, 3.0], "comp": [np.nan, 4.0], "industry": ["tech", "tech"]}
    mask = {
        "stage_size": np.array([False, False]),
        "comp": np.array([True, False]),
        "industry": np.array([False, False]),
    }

    out = preprocess_conf(conf, cfg, conf_missing=mask)
    assert out["comp"][0] == 0.0          # exactly, not approximately
    assert out["comp"][1] == 1.0
    assert not np.isnan(out["comp"]).any()

    # and the term really is gone from z: a huge comp weight moves row 1 and not row 0
    weights = {
        "intercept": 0.0,
        "dimensions": {d: {"mag": 0.0, "dir": 0.0} for d in DIMS},
        "confounders": {"stage_size": 0.0, "comp": 0.0, "industry": np.zeros(5)},
    }
    person = {d: np.array([0.5, 0.5]) for d in DIMS}
    env = {d: np.array([0.5, 0.5]) for d in DIMS}
    base = np.asarray(outcome_logit(person, env, out, cfg, weights))

    weights["confounders"]["comp"] = 10.0
    moved = np.asarray(outcome_logit(person, env, out, cfg, weights))
    assert moved[0] == base[0]            # masked row: term excluded
    assert moved[1] != base[1]


def test_nan_without_a_mask_raises_and_names_the_confounder():
    """Before this, a NaN standardized into a NaN and propagated through the whole
    linear predictor into p_fit, unflagged."""
    from match_core import preprocess_conf

    cfg = _cfg()
    conf = {"stage_size": [3.0, 3.0], "comp": [np.nan, 4.0], "industry": ["tech", "tech"]}

    with pytest.raises(ValueError) as exc:
        preprocess_conf(conf, cfg)
    assert "comp" in str(exc.value)

    # a mask that does not cover the NaN is just as wrong
    with pytest.raises(ValueError):
        preprocess_conf(
            conf, cfg, conf_missing={k: np.zeros(2, dtype=bool) for k in conf}
        )


def test_masking_one_confounder_leaves_the_others_alone():
    from match_core import preprocess_conf

    cfg = _cfg()
    out = preprocess_conf(
        CONF_RAW, cfg, conf_missing={"comp": np.array([False, True, False])}
    )
    assert out["comp"].tolist() == [-1.0, 0.0, 1.0]
    assert out["stage_size"].tolist() == ((np.array([1.0, 3.0, 5.0]) - 3.0) / 1.5).tolist()


# ---------------------------------------------------------------------------
# 7. The MASKED CATEGORICAL -- the last code blocker between the environment
#    rows and a fit (ruled 2026-09-21).
#
# The environment instrument never asks `industry`, so every row off that source
# carries None for an ACTIVE categorical confounder. The ruling is the one
# already applied to a missing `comp`: exclude the term. A categorical has no
# neutral level index, so the exclusion rides on a second array -- a masked row
# indexes level 0 as a placeholder and `industry__present` is 0.0 there, so
# `w[level] * present` contributes exactly nothing.
#
# An `unknown` LEVEL was rejected: shared by every row off a source it is
# perfectly collinear with the intercept, which currently means "8 in 10 doing
# well". Deactivating the confounder was rejected: it would strip industry from
# the company-side path too and move the 20-row flat weight set that
# tests/test_match_scoring.py pins.
# ---------------------------------------------------------------------------

#: solverah_model_config.yaml's industry levels, in order. Spelled out so a
#: silently-reordered config fails here rather than mis-indexing a weight.
INDUSTRY_LEVELS = ["tech", "finance", "healthcare", "retail", "other"]

#: Deliberately distinct and nonzero, so a wrong level index cannot pass.
INDUSTRY_W = [1.3, -0.9, 0.5, 2.1, -1.7]


def test_config_industry_levels_are_what_these_tests_assume():
    cfg = _cfg()
    industry = next(c for c in cfg["confounders"] if c["key"] == "industry")
    assert industry["levels"] == INDUSTRY_LEVELS
    assert industry["kind"] == "categorical"
    assert industry["active"] and industry["measurable"]


def _weights(industry_w):
    """Point weights (no {mean, sd} leaves) with a distinct per-level industry vector."""
    return {
        "intercept": 0.3,
        "dimensions": {d: {"mag": -0.4, "dir": 0.2} for d in DIMS},
        "confounders": {
            "stage_size": 0.1,
            "comp": -0.2,
            "industry": np.asarray(industry_w, dtype=float),
        },
    }


def _pairs(n):
    person = {d: np.linspace(0.0, 1.0, n) for d in DIMS}
    env = {d: np.linspace(0.9, 0.1, n) for d in DIMS}
    return person, env


# --- the old code, kept verbatim, so "unchanged" is checked against it -------

def _old_preprocess_conf(conf, cfg):
    """The literal pre-2026-09-21 preprocess_conf. A re-derivation of what the
    old code was *meant* to do would not catch a change in what it did."""
    from match_core import active

    out = {}
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue
        k = c["key"]
        raw = conf[k]
        if c.get("kind") == "categorical":
            levels = c["levels"]
            out[k] = np.array([levels.index(v) for v in raw], dtype="int64")
        else:
            scale = c["scale"]
            out[k] = (np.asarray(raw, dtype=float) - scale["mean"]) / scale["sd"]
    return out


def _old_outcome_logit(person, env, conf, cfg, weights):
    """The literal pre-2026-09-21 outcome_logit, categorical branch `z += w[conf[k]]`."""
    from match_core import active, fit_gap

    feats = cfg["settings"]["gap_features"]
    z = weights["intercept"]
    for d in active(cfg["dimensions"]):
        k = d["key"]
        g = fit_gap(person[k], env[k], snap_person=True)
        w = weights["dimensions"][k]
        if "mag" in feats:
            z += w["mag"] * abs(g)
        if "dir" in feats:
            z += w["dir"] * g
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue
        k = c["key"]
        w = weights["confounders"][k]
        if c.get("kind") == "categorical":
            z += w[conf[k]]
        else:
            z += w * conf.get(k, 0.0)
    return z


def test_no_mask_is_bit_identical_to_the_old_code():
    """point_p_fit / score_pairs run this on every request. The requirement is
    bit-identity against the OLD expression, not closeness -- which is why
    outcome_logit keeps a `present is None` branch instead of multiplying by 1.0."""
    from match_core import load, point_p_fit, point_weights, preprocess_conf, \
        weights_from_priors

    cfg, pri = load()
    person, env = _pairs(3)
    conf = {"stage_size": [1.0, 3.0, 5.0], "comp": [2.0, 3.0, 4.0],
            "industry": ["tech", "finance", "other"]}

    new = preprocess_conf(conf, cfg)
    old = _old_preprocess_conf(conf, cfg)
    assert set(new) == set(old)
    assert "industry__present" not in new
    for k in old:
        np.testing.assert_array_equal(new[k], old[k])
        assert new[k].dtype == old[k].dtype

    weights = weights_from_priors(cfg, pri)
    want = _sigmoid(_old_outcome_logit(person, env, old, cfg, point_weights(weights)))
    np.testing.assert_array_equal(point_p_fit(person, env, conf, cfg, weights), want)

    # the new keyword argument, left at its default, is the same path
    np.testing.assert_array_equal(
        point_p_fit(person, env, conf, cfg, weights, conf_missing=None), want
    )
    # and so is an all-False mask
    np.testing.assert_array_equal(
        point_p_fit(person, env, conf, cfg, weights,
                    conf_missing={"industry": np.zeros(3, dtype=bool)}),
        want,
    )


def test_all_masked_categorical_is_the_same_as_zero_industry_weights():
    """Excluding the term means exactly that: with every row masked, z is what it
    would be if all five industry weights were 0.0. Checked with NONZERO weights,
    so the assertion can fail."""
    from match_core import outcome_logit, preprocess_conf

    cfg = _cfg()
    n = 4
    person, env = _pairs(n)
    conf = {"stage_size": [1.0, 2.0, 3.0, 4.0], "comp": [2.0, 3.0, 4.0, 5.0],
            "industry": [None] * n}

    out = preprocess_conf(conf, cfg, conf_missing={"industry": np.ones(n, dtype=bool)})
    assert out["industry"].tolist() == [0] * n            # placeholder index
    assert out["industry"].dtype == np.dtype("int64")
    assert out["industry__present"].tolist() == [0.0] * n

    z_masked = np.asarray(outcome_logit(person, env, out, cfg, _weights(INDUSTRY_W)))

    supplied = preprocess_conf({**conf, "industry": ["tech"] * n}, cfg)
    z_zeroed = np.asarray(outcome_logit(person, env, supplied, cfg,
                                        _weights(np.zeros(5))))
    np.testing.assert_array_equal(z_masked, z_zeroed)

    # the weights really are live: unmasked, they move z
    z_live = np.asarray(outcome_logit(person, env, supplied, cfg,
                                      _weights(INDUSTRY_W)))
    assert not np.array_equal(z_live, z_zeroed)


def test_partly_masked_categorical_keeps_every_unmasked_row_on_its_own_level():
    from match_core import outcome_logit, preprocess_conf

    cfg = _cfg()
    person, env = _pairs(5)
    conf = {"stage_size": [3.0] * 5, "comp": [3.0] * 5,
            "industry": ["tech", None, "healthcare", None, "other"]}
    mask = {"industry": np.array([False, True, False, True, False])}

    out = preprocess_conf(conf, cfg, conf_missing=mask)
    assert out["industry"].tolist() == [0, 0, 2, 0, 4]
    assert out["industry__present"].tolist() == [1.0, 0.0, 1.0, 0.0, 1.0]

    z = np.asarray(outcome_logit(person, env, out, cfg, _weights(INDUSTRY_W)))
    base = np.asarray(outcome_logit(person, env, out, cfg, _weights(np.zeros(5))))
    np.testing.assert_allclose(
        z - base,
        [INDUSTRY_W[0], 0.0, INDUSTRY_W[2], 0.0, INDUSTRY_W[4]],
        atol=1e-12, rtol=0,
    )


def test_a_masked_row_never_reads_the_placeholder_levels_weight():
    """Level 0 is an implementation placeholder, not a value the row claims. Give it
    a weight big enough to dominate z and the masked row must not move at all."""
    from match_core import outcome_logit, preprocess_conf

    cfg = _cfg()
    person, env = _pairs(2)
    conf = {"stage_size": [3.0, 3.0], "comp": [3.0, 3.0],
            "industry": [None, "finance"]}

    out = preprocess_conf(conf, cfg, conf_missing={"industry": np.array([True, False])})
    assert out["industry"][0] == 0

    quiet = np.array([0.0, -0.9, 0.5, 2.1, -1.7])
    loud = quiet.copy()
    loud[0] = 1000.0
    np.testing.assert_array_equal(
        np.asarray(outcome_logit(person, env, out, cfg, _weights(quiet))),
        np.asarray(outcome_logit(person, env, out, cfg, _weights(loud))),
    )


def test_unmasked_none_categorical_raises_and_names_the_confounder():
    """The masked path must not become a way for an unasked-for None to reach a fit
    quietly. Before 2026-09-21 this raised list.index's bare 'None is not in list'."""
    from match_core import preprocess_conf

    cfg = _cfg()
    conf = {"stage_size": [3.0, 3.0], "comp": [3.0, 3.0], "industry": [None, "tech"]}

    with pytest.raises(ValueError) as exc:
        preprocess_conf(conf, cfg)
    message = str(exc.value)
    assert "industry" in message
    assert "None" in message
    assert "[0]" in message                      # the offending row, named

    # a mask covering the WRONG row is just as wrong
    with pytest.raises(ValueError):
        preprocess_conf(conf, cfg,
                        conf_missing={"industry": np.array([False, True])})

    # and an unknown level is not laundered by masking some other row
    unknown = {"stage_size": [3.0, 3.0], "comp": [3.0, 3.0],
               "industry": [None, "crypto"]}
    with pytest.raises(ValueError) as exc2:
        preprocess_conf(unknown, cfg,
                        conf_missing={"industry": np.array([True, False])})
    assert "crypto" in str(exc2.value)


# ---------------------------------------------------------------------------
# 8. END TO END -- real environment rows, the live priors, a finite z.
#
# The point of the whole exercise. Everything above is unit arithmetic; this is
# the assembler's own output going through preprocess_conf + outcome_logit with
# nothing hand-built in between, which is the thing that was impossible before.
# ---------------------------------------------------------------------------


@pytest.fixture
def _form_token_secret(monkeypatch):
    # Read at call time in assessment_store.respondent_id_for_user, with no default
    # by design (D-05). Deliberately NOT in tests/conftest.py: test_assessment_form.py
    # deletes the variable to prove the no-default rule, and a suite-wide default
    # would make that test unable to fail.
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


def test_environment_rows_reach_a_finite_z(client, monkeypatch, _form_token_secret):
    from match_core import (load, outcome_logit, point_weights, preprocess_conf,
                            weights_from_priors)

    # The E-4 suite's helpers rather than hand-rolled arrays: they drive the real
    # shuffled core form and the real POST /me/environment-report, which is where
    # the None `industry` actually comes from.
    import test_assemble_environment_training_data as e4

    for i in range(3):
        csrf = e4._register_and_login(client, monkeypatch, "ordz%d@example.com" % i)
        e4._set_career_status(client, csrf, "employed")
        e4._complete_core(client, csrf, e4._UNIFORM if i % 2 == 0 else e4._VARIED)
        assert e4._post_env(
            client, csrf, stage_size=1 + i, comp=2 + i, experienced=3 + i
        ).status_code == 200

    result = e4._assemble()
    assert result.dropped == []
    assert len(result.rows) == 3
    assert result.unsupplied_confounders == ("industry",)
    assert np.asarray(result.conf_missing["industry"]).all()

    cfg, pri = load()
    conf = preprocess_conf(result.conf, cfg, conf_missing=result.conf_missing)
    assert conf["industry__present"].tolist() == [0.0] * 3

    z = np.asarray(
        outcome_logit(result.person, result.env, conf, cfg,
                      point_weights(weights_from_priors(cfg, pri)))
    )
    assert z.shape == (3,)
    assert np.isfinite(z).all()
