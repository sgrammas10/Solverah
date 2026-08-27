"""
match_core.py -- the deterministic core of the Solverah match model, numpy-only.

Extracted from build_model.py (2026-08-19, S-45 item 6) so the app can score matches
WITHOUT importing PyMC: the linear predictor, the lattices, the gap correction, and the
confounder preprocessing are pure arithmetic that does not care whether a weight is a
PyMC random variable or a float. build_model.py imports everything here and remains the
research/training harness; this file must never import pymc, flask, or sqlalchemy.

There is exactly ONE implementation of the linear predictor (outcome_logit). The Monte
Carlo band in score_pairs() calls it per draw rather than keeping a second vectorized
copy -- slower, but two implementations of the same formula is how they diverge, and
serving precomputes into match_recommendation rows anyway.

Weight naming convention, shared with PyMC and the weight_posterior table
-------------------------------------------------------------------------
flatten_weights() / unflatten_weights() translate between the nested weight structure
and flat (name, mean, sd) rows using EXACTLY the names build_model.py gives its PyMC
RVs -- "intercept", "{dim}_mag", "{dim}_dir", "w_{conf}" -- with one extension: a
categorical confounder's per-level vector becomes one row per level, "w_{conf}[{level}]"
(PyMC holds it as one shape-(L,) RV, a table cannot). This is what makes exporting a
fitted posterior into weight_posterior a mechanical mean/sd dump under the same names.

Both directions are STRICT (D-07): a missing weight raises, an unrecognized weight
raises. A weight row the config does not expect is evidence the run was fitted under a
different dimension set, and reading around it silently is how a stale weight serves
predictions.
"""

from __future__ import annotations

import os

import numpy as np
import yaml

MODEL_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Achievable-band lattices -- see lattice_gap_analysis.py, section A ("the pole
# penalty"). Person-side answers come off a 4-item mean_pole ladder with 5 possible
# values; env-side (company) scores are the mean of N_RUNS band draws from
# {0.1, 0.3, 0.5, 0.7, 0.9} and can therefore never fall below 0.1 or above 0.9.
# Deliberately duplicated here rather than imported from lattice_gap_analysis.py: that
# script is a frozen, side-effect-executing analysis snapshot (importing it re-runs the
# whole printed report), not a library. If BAND_VALUES or N_RUNS ever change, the two
# copies have to be reconciled by hand -- that's a smaller risk than a production model
# depending on an analysis script's module-level prints.
# ---------------------------------------------------------------------------
PERSON_LATTICE = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
BAND_VALUES = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
N_RUNS = 5


def _company_lattice():
    import itertools
    vals = {round(float(np.mean(c)), 6)
            for c in itertools.combinations_with_replacement(BAND_VALUES, N_RUNS)}
    return np.array(sorted(vals))


COMPANY_LATTICE = _company_lattice()


def closest_achievable(value, lattice=COMPANY_LATTICE):
    """Nearest value on `lattice` to `value` (elementwise; scalars, lists or arrays).
    numpy-only -- never call this on a pytensor/pm.Data symbolic value (see fit_gap()).
    """
    value = np.asarray(value, dtype=float)
    lattice = np.asarray(lattice, dtype=float)
    return lattice[np.abs(value[..., None] - lattice).argmin(-1)]


# ---------------------------------------------------------------------------
# Load structure + numbers separately (the whole point of the split)
# ---------------------------------------------------------------------------
def load(cfg_path=None, pri_path=None):
    cfg_path = cfg_path or os.path.join(MODEL_DIR, "solverah_model_config.yaml")
    pri_path = pri_path or os.path.join(MODEL_DIR, "priors.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    with open(pri_path) as f:
        pri = yaml.safe_load(f)
    return cfg, pri


def active(items):
    return [x for x in items if x.get("active")]


# ---------------------------------------------------------------------------
# Deterministic Fit layer: signed gap
# ---------------------------------------------------------------------------
def fit_gap(person_score, env_score, snap_person=True):
    """Signed gap, range -1..1.

    snap_person=True (the fix, default): person_score is first replaced by its closest
    achievable value on COMPANY_LATTICE. Without this, a person at either pole of their
    own 5-point ladder is compared against an env scale that structurally cannot reach
    past [0.1, 0.9] -- so even a PERFECTLY matched pole candidate carries a permanent
    |gap| floor of ~0.10 per dimension that a mid-scale candidate never pays. Across six
    dimensions that floor alone costs a decisive candidate 45% of their odds against an
    identically well-matched mid candidate (lattice_gap_analysis.py, section A). A
    mid-scale person's closest achievable value barely moves, so genuine gaps are not
    inflated by this -- only the structural pole penalty is removed.

    snap_person=False: raw signed difference, no correction. Required for pytensor/pm.Data
    symbolic inputs inside build_model()'s pm.Model() context, where the snap has already
    been applied in plain numpy before the value became pm.Data (closest_achievable() is
    numpy-only and cannot run on a symbolic tensor). Also useful for reproducing the old,
    unfixed behavior directly for comparison.
    """
    if snap_person:
        person_score = closest_achievable(person_score)
    return person_score - env_score


# ---------------------------------------------------------------------------
# Preprocess raw confounder values into what outcome_logit expects:
#   continuous  -> standardized with a FIXED {mean, sd} from config (fixed,
#                  not batch-computed, so a single-row prediction doesn't
#                  divide by an undefined std, and fit-time/predict-time
#                  scaling always agree)
#   categorical -> integer level-index array (for indexing a per-level
#                  weight vector)
# Called from build_model(), the synthetic-data generator in sanity_check(),
# and score_pairs() below, so the three can never apply different preprocessing.
# ---------------------------------------------------------------------------
def preprocess_conf(conf, cfg):
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


# ---------------------------------------------------------------------------
# Outcome: logistic linear predictor built from config + weights
#   person, env : dict {dim_key: array, length N}
#   conf        : dict {confounder_key: array, length N} -- pre-processed
#                 (see preprocess_conf); continuous = standardized value,
#                 categorical = integer level index
#   weights     : same nested shape as priors.yaml (intercept,
#                 dimensions[k]["mag"/"dir"], confounders[k]) but every leaf
#                 is a PyMC RV (inside a model) or a plain float/array (for
#                 the numpy paths) -- the arithmetic here (+, -, *, abs,
#                 indexing) doesn't care which.
# ---------------------------------------------------------------------------
def outcome_logit(person, env, conf, cfg, weights, snap_person=True):
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
            z += w[conf[k]]                     # one weight per level
        else:
            z += w * conf.get(k, 0.0)

    return z


# ---------------------------------------------------------------------------
# Weight structure: {mean, sd} leaves <-> flat (name, mean, sd) rows
# ---------------------------------------------------------------------------
def weights_from_priors(cfg, pri):
    """priors.yaml -> nested weights with {mean, sd} leaves. A categorical confounder's
    single shared {mean, sd} prior becomes per-level vectors, matching the shape PyMC
    gives its vector RV."""
    feats = cfg["settings"]["gap_features"]
    out = {
        "intercept": {"mean": float(pri["intercept"]["mean"]),
                      "sd": float(pri["intercept"]["sd"])},
        "dimensions": {},
        "confounders": {},
    }
    for d in active(cfg["dimensions"]):
        k = d["key"]
        p = pri["dimensions"][k]
        out["dimensions"][k] = {
            feat: {"mean": float(p[feat]["mean"]), "sd": float(p[feat]["sd"])}
            for feat in feats
        }
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue
        k = c["key"]
        p = pri["confounders"][k]
        if c.get("kind") == "categorical":
            L = len(c["levels"])
            out["confounders"][k] = {
                "mean": np.full(L, float(p["mean"])),
                "sd": np.full(L, float(p["sd"])),
            }
        else:
            out["confounders"][k] = {"mean": float(p["mean"]), "sd": float(p["sd"])}
    return out


def flatten_weights(cfg, weights):
    """Nested {mean, sd} weights -> list of (weight_name, mean, sd) rows, in a stable
    order. Names match build_model.py's PyMC RVs; categorical levels get one row each."""
    feats = cfg["settings"]["gap_features"]
    rows = [("intercept", weights["intercept"]["mean"], weights["intercept"]["sd"])]
    for d in active(cfg["dimensions"]):
        k = d["key"]
        for feat in feats:
            leaf = weights["dimensions"][k][feat]
            rows.append((f"{k}_{feat}", leaf["mean"], leaf["sd"]))
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue
        k = c["key"]
        leaf = weights["confounders"][k]
        if c.get("kind") == "categorical":
            for i, level in enumerate(c["levels"]):
                rows.append((f"w_{k}[{level}]", float(leaf["mean"][i]), float(leaf["sd"][i])))
        else:
            rows.append((f"w_{k}", leaf["mean"], leaf["sd"]))
    return [(name, float(m), float(s)) for name, m, s in rows]


def unflatten_weights(cfg, rows):
    """Flat {weight_name: (mean, sd)} mapping -> nested weights. STRICT both ways
    (D-07): a weight the config expects but the mapping lacks raises; a weight the
    mapping carries but the config does not expect raises. Either mismatch means the
    rows were fitted under a different dimension/confounder set than the one being
    served, and serving across that mismatch is a silent wrong answer."""
    mapping = dict(rows)
    expected = []

    def take(name):
        expected.append(name)
        if name not in mapping:
            raise ValueError(
                f"weight '{name}' is required by the active config but missing from the "
                f"weight rows -- refusing to serve a partially-weighted model (D-07)"
            )
        m, s = mapping[name]
        return {"mean": float(m), "sd": float(s)}

    feats = cfg["settings"]["gap_features"]
    out = {"intercept": take("intercept"), "dimensions": {}, "confounders": {}}
    for d in active(cfg["dimensions"]):
        k = d["key"]
        out["dimensions"][k] = {feat: take(f"{k}_{feat}") for feat in feats}
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue
        k = c["key"]
        if c.get("kind") == "categorical":
            leaves = [take(f"w_{k}[{level}]") for level in c["levels"]]
            out["confounders"][k] = {
                "mean": np.array([x["mean"] for x in leaves]),
                "sd": np.array([x["sd"] for x in leaves]),
            }
        else:
            out["confounders"][k] = take(f"w_{k}")

    unexpected = set(mapping) - set(expected)
    if unexpected:
        raise ValueError(
            f"weight rows carry names the active config does not define: "
            f"{sorted(unexpected)} -- the run was fitted under a different "
            f"dimension/confounder set (check dimension_set_version); refusing (D-07)"
        )
    return out


def point_weights(weights):
    """{mean, sd} leaves -> plain means, for a deterministic point prediction."""
    return {
        "intercept": weights["intercept"]["mean"],
        "dimensions": {
            k: {feat: leaf["mean"] for feat, leaf in feats.items()}
            for k, feats in weights["dimensions"].items()
        },
        "confounders": {
            k: (np.asarray(leaf["mean"]) if isinstance(leaf["mean"], np.ndarray)
                else leaf["mean"])
            for k, leaf in weights["confounders"].items()
        },
    }


def _draw_weights(weights, rng):
    """One realization of every weight from Normal(mean, sd)."""
    return {
        "intercept": rng.normal(weights["intercept"]["mean"], weights["intercept"]["sd"]),
        "dimensions": {
            k: {feat: rng.normal(leaf["mean"], leaf["sd"]) for feat, leaf in feats.items()}
            for k, feats in weights["dimensions"].items()
        },
        "confounders": {
            k: rng.normal(np.asarray(leaf["mean"], dtype=float),
                          np.asarray(leaf["sd"], dtype=float))
            for k, leaf in weights["confounders"].items()
        },
    }


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def _validate_inputs(person, env, conf_raw, cfg):
    dims = [d["key"] for d in active(cfg["dimensions"])]
    confs = [c["key"] for c in active(cfg["confounders"]) if c.get("measurable")]
    for k in dims:
        if k not in person:
            raise ValueError(f"person scores missing active dimension '{k}' (D-07)")
        if k not in env:
            raise ValueError(f"env scores missing active dimension '{k}' (D-07)")
    for k in confs:
        if k not in conf_raw:
            raise ValueError(
                f"confounder values missing active measurable confounder '{k}' -- "
                f"a silently-defaulted confounder is an invisible model change (D-07)"
            )
    lengths = {len(np.atleast_1d(person[k])) for k in dims}
    lengths |= {len(np.atleast_1d(env[k])) for k in dims}
    lengths |= {len(np.atleast_1d(conf_raw[k])) for k in confs}
    if len(lengths) != 1:
        raise ValueError(f"inputs disagree on N: lengths {sorted(lengths)}")


def point_p_fit(person, env, conf_raw, cfg, weights):
    """Deterministic P(fit) at the weight means. `weights` has {mean, sd} leaves."""
    _validate_inputs(person, env, conf_raw, cfg)
    conf = preprocess_conf(conf_raw, cfg)
    z = outcome_logit(person, env, conf, cfg, point_weights(weights), snap_person=True)
    return _sigmoid(z)


def score_pairs(person, env, conf_raw, cfg, weights, draws=2000, seed=0, interval=0.90):
    """P(fit) with an uncertainty band, for N (person, company) pairs.

    person, env : dict {dim_key: array-like length N} of dimension scores
    conf_raw    : dict {confounder_key: array-like length N} of RAW confounder values
    weights     : nested weights with {mean, sd} leaves (weights_from_priors() or
                  unflatten_weights() output). Under the priors-only run the band is a
                  prior-predictive band; after a real fit it is a posterior band --
                  same code either way, which is the point of the weight_posterior
                  design.

    Returns dict of float arrays length N: p_fit (mean over weight draws),
    p_fit_low / p_fit_high (central `interval` band), matching the
    match_recommendation columns.

    Each draw calls the SAME outcome_logit used for fitting -- slower than a
    hand-vectorized copy, but there is exactly one implementation of the linear
    predictor and this keeps it that way. Deterministic for a given seed.
    """
    _validate_inputs(person, env, conf_raw, cfg)
    conf = preprocess_conf(conf_raw, cfg)
    rng = np.random.default_rng(seed)

    p = np.empty((draws, len(np.atleast_1d(next(iter(person.values()))))))
    for i in range(draws):
        w = _draw_weights(weights, rng)
        p[i] = _sigmoid(outcome_logit(person, env, conf, cfg, w, snap_person=True))

    tail = (1.0 - interval) / 2.0
    return {
        "p_fit": p.mean(axis=0),
        "p_fit_low": np.quantile(p, tail, axis=0),
        "p_fit_high": np.quantile(p, 1.0 - tail, axis=0),
    }
