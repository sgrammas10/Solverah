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

    # and passing an explicit all-False mask changes nothing
    masked = preprocess_conf(
        CONF_RAW, cfg, conf_missing={k: np.zeros(3, dtype=bool) for k in CONF_RAW}
    )
    for key in expected:
        assert masked[key].tolist() == out[key].tolist()


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
