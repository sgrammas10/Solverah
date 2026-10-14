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

Since 2026-10-13 the predictor can also read a person's per-dimension flat zone
(`flat_zones`, the hinge -- see excess_gap) and skip a dimension whose env score is
unknown (`env_missing`). Both default to None and leave every existing caller
bit-identical. `point_z` serves the predictor alone, for ranking without a probability.

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

#: The pole-vs-pole gap: a person at the top of their ladder, snapped onto the
#: company lattice, against the lowest env score the lattice can produce. This is
#: the |gap| every one of Julie's twelve dimension answers was elicited at
#: (Solverah_IP/priors_elicitation/convert_priors_response.py, GAP), so it is the
#: one point on the gap axis where a cost is a measurement rather than our
#: extrapolation. Derived, not typed, so a lattice change moves it.
POLE_GAP = float(COMPANY_LATTICE.max() - COMPANY_LATTICE.min())


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
# THE HINGE (serving shape since 2026-10-13, PRODUCT_DECISIONS.md section 2,
# "The six-trait match model"): flat inside a person's tolerance, linear outside.
#
# A person states, per dimension, how much LESS than they want is still fine
# (the UNDER zone) and how much MORE (the OVER zone). In this file's sign
# convention gap = person - env, so gap > 0 means the environment provides
# less than the person wants and the under zone applies; gap < 0 means more,
# and the over zone applies. Inside the zone the dimension costs nothing --
# neither the symmetric `mag` term nor the directional `dir` term -- and
# outside it the cost grows linearly in the excess.
#
# THE RESCALING. Julie's twelve dimension answers were elicited at the pole
# gap (POLE_GAP, 0.8) and are the only measured points on the gap axis;
# everything between 0 and 0.8 is our extrapolation. So the hinge keeps the
# measured point fixed and moves only the extrapolation: the excess
# max(0, |gap| - zone) is multiplied by POLE_GAP / (POLE_GAP - zone), which
# makes a pole gap map to a pole gap whatever the zone, and therefore makes
# her twelve answers reproduce exactly under any zone (tests/test_match_hinge.py).
# The price is a steeper slope outside the zone (0.8/0.65 = 1.23x at the
# 0.15 floor, 0.8/0.3 = 2.67x at a 0.5 zone): the person said the first
# `zone` of mismatch is fine, so the same pole cost is reached over a shorter
# run. An unrescaled hinge would instead cut the pole cost by w * zone and
# silently re-weight her elicitation; a zone of 0.8 or more would leave no
# run at all, which is why zones must be < POLE_GAP.
#
# THE SNAP. The zone applies to fit_gap's output, i.e. AFTER the person-side
# snap onto COMPANY_LATTICE. The snap removes a structural artefact (a pole the
# env scale cannot reach), not a real mismatch, and the tolerance is a statement
# about real mismatch; a mid-scale person moves at most 0.02 under the snap,
# well inside the 0.15 floor. The Situation Report classifies the UNsnapped
# gap against the same 0.15 band (work_pulse/situation.py) -- a known, small
# difference between the two consumers, not a contradiction.
#
# Written with abs, +, -, * and / only -- no np.where, np.maximum or np.sign --
# so the same expression runs on numpy arrays AND on pytensor tensors inside
# build_model's pm.Model() context (checked 2026-10-13: np.maximum and np.where
# both fail on a TensorVariable; this algebra does not). build_model does not
# pass flat_zones yet; when the pre-registered Look 2 comparison needs it, the
# fit path can call outcome_logit(..., flat_zones=...) unchanged.
#
# With flat_zones=None, outcome_logit keeps the literal pre-2026-10-13
# expression behind a branch, so every existing caller is bit-identical
# (pinned against a verbatim copy of the old code, as the industry mask was).
# ---------------------------------------------------------------------------
def _positive_part(x):
    """max(0, x) without np.maximum: exact for finite x and tensor-safe."""
    return (x + abs(x)) / 2.0


def excess_gap(gap, under_zone, over_zone, pole_gap=POLE_GAP):
    """Signed gap with the flat zone removed and the pole cost preserved.

    gap        : signed, person - env (fit_gap's output); scalar, array, or tensor
    under_zone : how much LESS than wanted is free (applies where gap > 0)
    over_zone  : how much MORE than wanted is free (applies where gap < 0)
    Each zone is a float in [0, pole_gap), or an array broadcastable to `gap`.

    Returns a signed value with the sign of `gap`: 0 inside the zone,
    (|gap| - zone) * pole_gap / (pole_gap - zone) outside, so that
    excess_gap(+pole_gap, ...) == +pole_gap and excess_gap(-pole_gap, ...) ==
    -pole_gap for every zone. Zones are NOT validated here (see
    _prepare_flat_zones); a tensor cannot be checked at trace time.
    """
    short = _positive_part(gap)        # env provides this much less than wanted
    extra = _positive_part(-gap)       # ... or this much more
    # Divide by the run first, then multiply by the pole: at |gap| == pole_gap
    # the ratio is x / x == 1.0 exactly, so a pole gap stays a pole gap bitwise.
    e_under = (_positive_part(short - under_zone) / (pole_gap - under_zone)) * pole_gap
    e_over = (_positive_part(extra - over_zone) / (pole_gap - over_zone)) * pole_gap
    return e_under - e_over


def _check_zone(dim, side, value):
    arr = np.asarray(value, dtype=float)
    if arr.ndim > 1:
        raise ValueError(
            f"flat zone for '{dim}' ({side}) must be a scalar or a 1-d array, got "
            f"shape {arr.shape}"
        )
    bad = ~np.isfinite(arr) | (arr < 0.0) | (arr >= POLE_GAP)
    if np.atleast_1d(bad).any():
        raise ValueError(
            f"flat zone for '{dim}' ({side}) must satisfy 0 <= zone < {POLE_GAP} "
            f"(the pole gap, the only point where a cost was elicited), got "
            f"{np.atleast_1d(arr)[np.atleast_1d(bad)].tolist()} -- a zone of "
            f"{POLE_GAP} or more leaves no run for the pole cost to be reached over. "
            f"The 0.15 floor is applied upstream (solverah/domain/trait_preferences), "
            f"not here."
        )
    return float(arr) if arr.ndim == 0 else arr


def _prepare_flat_zones(flat_zones, cfg):
    """{dim: (under_zone, over_zone)} validated against the active dimensions,
    or None. STRICT both ways (D-07): a zone for every active dimension, no zone
    for anything else -- a partial dict is evidence the caller and the config
    disagree on the dimension set."""
    if flat_zones is None:
        return None
    dims = [d["key"] for d in active(cfg["dimensions"])]
    missing = [k for k in dims if k not in flat_zones]
    unexpected = sorted(set(flat_zones) - set(dims))
    if missing or unexpected:
        raise ValueError(
            f"flat_zones must carry exactly the active dimensions {dims}: "
            f"missing {missing}, unexpected {unexpected} (D-07). Pass None for the "
            f"linear-from-zero shape."
        )
    out = {}
    for k in dims:
        pair = flat_zones[k]
        try:
            under, over = pair
        except (TypeError, ValueError):
            raise ValueError(
                f"flat_zones['{k}'] must be a (under_zone, over_zone) pair, got {pair!r}"
            ) from None
        out[k] = (_check_zone(k, "under", under), _check_zone(k, "over", over))
    return out


def _prepare_env_present(env_missing, cfg):
    """{dim: float array, 1.0 where the env score is known and 0.0 where it is
    not}, for the dimensions that have at least one masked row; None when
    nothing is masked. Same self-reversing pattern as conf_missing: an absent
    key or an all-False mask is "known everywhere", and leaves no trace."""
    if env_missing is None:
        return None
    dims = [d["key"] for d in active(cfg["dimensions"])]
    unexpected = sorted(set(env_missing) - set(dims))
    if unexpected:
        raise ValueError(
            f"env_missing names {unexpected}, which are not active dimensions "
            f"{dims} (D-07)"
        )
    out = {}
    for k in dims:
        mask = env_missing.get(k)
        if mask is None:
            continue
        mask = np.atleast_1d(np.asarray(mask, dtype=bool))
        if mask.ndim > 1:
            raise ValueError(f"env_missing['{k}'] must be a scalar or 1-d bool array")
        if mask.any():
            out[k] = np.where(mask, 0.0, 1.0)
    return out or None


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
#
# MISSING CONTINUOUS VALUES (`conf_missing`, ruled 2026-09-17)
# ------------------------------------------------------------
# `comp` is nullable by a signed ruling ("not sure", PRODUCT_DECISIONS.md section 2),
# so `assemble_environment_training_data` hands back NaN plus an explicit
# boolean mask per confounder (EnvironmentAssembleResult.conf_missing) rather
# than imputing. The ruling for the model is EXCLUDE THE TERM: where the mask
# is True the standardized value becomes exactly 0.0, and since a continuous
# confounder enters the logit as `w * value`, a 0.0 drops that row's term out
# of z entirely. Deliberately NOT a missingness-indicator weight: that would be
# a 21st weight, and the flat weight naming (flatten_weights) is pinned at 20
# by tests/test_match_scoring.py -- modelling the missingness is a config
# change with its own sign-off, not a side effect of handling a NULL.
#
# Without a mask, a NaN RAISES. Before this it standardized into NaN and
# propagated silently through the whole linear predictor into p_fit.
#
# MISSING CATEGORICAL VALUES (ruled 2026-09-21)
# ---------------------------------------------
# Same ruling, EXCLUDE THE TERM, now for a masked categorical -- which is what
# unblocks the environment source, whose instrument never asks `industry` so
# every row of it is masked (ASSEMBLE_TRAINING_DATA_NOTES.md).
#
# A categorical has no neutral level index the way 0.0 is a neutral
# standardized value, so the exclusion is carried by a second array rather than
# by the value: a masked row indexes level 0 as a PLACEHOLDER and preprocess_conf
# additionally returns `{key}__present`, 1.0 where present and 0.0 where masked.
# outcome_logit then adds `w[level] * present`, so a masked row contributes
# exactly nothing -- the placeholder weight included.
#
# Two rejected alternatives, so they are not re-proposed:
#   * an `unknown` LEVEL. When every row off a source shares it, it is
#     perfectly collinear with the intercept -- unidentified, pure prior, and
#     it would bleed into the intercept that currently means "8 in 10 doing
#     well" (the elicited baseline the cutpoint pin exists to preserve).
#   * DEACTIVATING industry in the config. That removes it from the
#     company-side path too and changes the flat weight set, which
#     tests/test_match_scoring.py pins at 20 rows.
# The mask is self-reversing: when a source starts supplying industry, those
# rows stop being masked and the term returns with no code change.
#
# With no mask (or an all-False one) this path is EXACTLY what it was: the same
# int64 index array and no extra key, because serving (point_p_fit /
# score_pairs) runs it on every request. An unmasked None or unknown level
# still raises -- now naming the confounder, the values and the rows instead of
# list.index's bare "None is not in list".
# ---------------------------------------------------------------------------
def preprocess_conf(conf, cfg, conf_missing=None):
    out = {}
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue
        k = c["key"]
        raw = conf[k]
        if c.get("kind") == "categorical":
            levels = c["levels"]
            mask = None if conf_missing is None else conf_missing.get(k)
            if mask is not None:
                mask = np.atleast_1d(np.asarray(mask, dtype=bool))
                if not mask.any():
                    # No masked row -> the default path exactly, no extra key.
                    mask = None
            values = list(raw)
            idx = np.zeros(len(values), dtype="int64")
            bad = []
            for i, v in enumerate(values):
                if mask is not None and mask[i]:
                    continue               # placeholder 0; __present zeroes the term
                try:
                    idx[i] = levels.index(v)
                except ValueError:
                    bad.append((i, v))
            if bad:
                raise ValueError(
                    f"confounder '{k}' carries value(s) "
                    f"{[v for _, v in bad]!r} at row(s) {[i for i, _ in bad]} that are "
                    f"not among its configured levels {levels}, with no conf_missing "
                    f"mask marking those rows missing -- a categorical confounder "
                    f"indexes a per-level weight vector, so there is no weight to use. "
                    f"Pass conf_missing (EnvironmentAssembleResult.conf_missing) to "
                    f"exclude the term for those rows, or supply a level."
                )
            out[k] = idx
            if mask is not None:
                out[k + "__present"] = np.where(mask, 0.0, 1.0)
        else:
            scale = c["scale"]
            value = (np.asarray(raw, dtype=float) - scale["mean"]) / scale["sd"]
            mask = None if conf_missing is None else conf_missing.get(k)
            if mask is not None:
                # np.where, not in-place: a False mask leaves every value
                # bit-identical to the unmasked path above.
                value = np.where(np.asarray(mask, dtype=bool), 0.0, value)
            unmasked_nan = np.isnan(value)
            if unmasked_nan.any():
                raise ValueError(
                    f"confounder '{k}' carries NaN at row(s) "
                    f"{np.flatnonzero(np.atleast_1d(unmasked_nan)).tolist()} with no "
                    f"conf_missing mask marking them missing -- a NaN standardizes into "
                    f"the linear predictor and silently NaNs out p_fit. Pass "
                    f"conf_missing (EnvironmentAssembleResult.conf_missing) to exclude "
                    f"the term for those rows, or supply a value."
                )
            out[k] = value
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
def outcome_logit(person, env, conf, cfg, weights, snap_person=True,
                  flat_zones=None, env_missing=None):
    """The linear predictor z.

    flat_zones  : optional {dim_key: (under_zone, over_zone)} -- the person's
                  tolerance per dimension, every active dimension present, each
                  zone in [0, POLE_GAP). The gap enters through excess_gap()
                  (the hinge, see above). None: linear from zero, the literal
                  pre-2026-10-13 expression, bit-identical.
    env_missing : optional {dim_key: bool array length N} marking rows whose
                  env score for that dimension is UNKNOWN (a company trait with
                  no evidence). A masked row's mag and dir terms are excluded
                  from z entirely -- no gap, no penalty -- the same
                  exclude-the-term ruling as conf_missing. The env value under
                  a mask may be NaN or anything else; it is never read. None,
                  or an all-False mask: bit-identical to no mask. The masked
                  branch substitutes a placeholder with np.where and is
                  therefore numpy-only, like closest_achievable.
    Both are last and default to None so every existing caller is unchanged.
    """
    feats = cfg["settings"]["gap_features"]     # e.g. ["mag", "dir"]
    z = weights["intercept"]
    zones = _prepare_flat_zones(flat_zones, cfg)
    present = _prepare_env_present(env_missing, cfg)

    for d in active(cfg["dimensions"]):
        k = d["key"]
        w = weights["dimensions"][k]
        known = None if present is None else present.get(k)
        if zones is None and known is None:
            # The literal pre-2026-10-13 expression, kept as-is because serving
            # runs it on every request and must stay bit-identical when no zone
            # and no mask is given (tests/test_match_hinge.py pins this against
            # a verbatim copy, as tests/test_ordinal_head.py does for conf).
            g = fit_gap(person[k], env[k], snap_person=snap_person)
            if "mag" in feats:
                z += w["mag"] * abs(g)          # any mismatch hurts (symmetric)
            if "dir" in feats:
                z += w["dir"] * g               # directional asymmetry
            continue

        env_k = env[k]
        if known is not None:
            # A masked row's env may be NaN; NaN * 0.0 is NaN, so give the row a
            # finite placeholder before the gap. The term is multiplied by 0.0
            # below, so the placeholder's value never reaches z.
            env_k = np.where(known == 0.0, 0.5, np.asarray(env_k, dtype=float))
        g = fit_gap(person[k], env_k, snap_person=snap_person)
        if zones is not None:
            under_zone, over_zone = zones[k]
            g = excess_gap(g, under_zone, over_zone)
        # Two separate additions, in the same order as the branch above -- NOT
        # one combined term added once. Floating-point addition is not
        # associative, and the pole-gap and known-row bitwise identities
        # (tests/test_match_hinge.py) hold only under the same association.
        if known is None:
            if "mag" in feats:
                z += w["mag"] * abs(g)
            if "dir" in feats:
                z += w["dir"] * g
        else:
            # known is 1.0 (x * 1.0 == x exactly) or 0.0 (z + 0.0 == z exactly).
            if "mag" in feats:
                z += (w["mag"] * abs(g)) * known
            if "dir" in feats:
                z += (w["dir"] * g) * known
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue                            # unmeasurable -> not a term
        k = c["key"]
        w = weights["confounders"][k]
        if c.get("kind") == "categorical":
            term = w[conf[k]]                   # one weight per level
            present = conf.get(k + "__present")
            # The `present is None` branch is the literal pre-2026-09-21
            # expression, kept because serving runs it on every request and must
            # stay bit-identical when nothing is masked -- multiplying by 1.0
            # everywhere would not be. `term * present` works on numpy arrays AND
            # on pytensor tensors (build_model passes pm.Data); np.where does not.
            z += term if present is None else term * present
        else:
            z += w * conf.get(k, 0.0)

    return z


# ---------------------------------------------------------------------------
# The ORDINAL head, in numpy. Same linear predictor z, a different likelihood
# on top of it: the outcome is a 1..K rating rather than a 0/1 event.
#
# This is the exact formula pymc's OrderedLogistic.compute_p uses --
# `sigmoid(cutpoints - eta)` as the cumulative P(Y <= k), differenced -- kept
# here so serving never needs PyMC and so the mapping below can be tested in
# the main suite, which has no pymc.
#
# THE MAPPING (ruled 2026-09-17). priors.yaml's weights were elicited on a
# BINARY scale: sigmoid(z) = P(still doing well after a year), where "doing
# well" is a rating of 4 or 5. build_model PINS the cutpoint just below that
# rating at exactly 0, which makes
#
#     P(Y >= 4) = 1 - sigmoid(0 - z) = sigmoid(z)
#
# an identity rather than an approximation -- so the elicited numbers keep
# their meaning on the ordinal head with no rescaling, and the serving path
# (point_p_fit / score_pairs) keeps meaning exactly what it meant before.
# ---------------------------------------------------------------------------
def ordinal_probs(z, cutpoints):
    """Per-level probabilities for an ordered-logistic outcome.

    z         : array-like, shape (...) -- the linear predictor (eta)
    cutpoints : array-like, shape (K-1,) -- ASCENDING category boundaries

    Returns an array of shape (..., K) summing to 1 along the last axis, where
    column j is P(rating == j + 1).
    """
    z = np.asarray(z, dtype=float)
    cutpoints = np.asarray(cutpoints, dtype=float)
    cumulative = _sigmoid(cutpoints - z[..., None])      # P(Y <= k), k = 1..K-1
    pad = z.shape + (1,)
    padded = np.concatenate(
        [np.zeros(pad), cumulative, np.ones(pad)], axis=-1
    )
    return np.diff(padded, axis=-1)


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


def _validate_inputs(person, env, conf_raw, cfg, flat_zones=None, env_missing=None):
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
    n = lengths.pop()

    # Both optional inputs are validated here as well as in outcome_logit, because
    # only this layer knows N: a per-row zone or mask of the wrong length would
    # otherwise broadcast or fail deep inside the arithmetic.
    present = _prepare_env_present(env_missing, cfg)
    for k, known in (present or {}).items():
        if len(known) not in (1, n):
            raise ValueError(
                f"env_missing['{k}'] has length {len(known)}, inputs have N={n}"
            )
    zones = _prepare_flat_zones(flat_zones, cfg)
    for k, pair in (zones or {}).items():
        for side, zone in zip(("under", "over"), pair):
            if np.ndim(zone) == 1 and len(zone) not in (1, n):
                raise ValueError(
                    f"flat zone for '{k}' ({side}) has length {len(zone)}, inputs "
                    f"have N={n}"
                )

    # An env score that is NaN with no mask covering it would NaN out z silently
    # (the same trap preprocess_conf closes for a confounder).
    for k in dims:
        values = np.atleast_1d(np.asarray(env[k], dtype=float))
        unmasked_nan = np.isnan(values)
        known = None if present is None else present.get(k)
        if known is not None:
            unmasked_nan = unmasked_nan & (known != 0.0)
        if unmasked_nan.any():
            raise ValueError(
                f"env score for '{k}' is NaN at row(s) "
                f"{np.flatnonzero(unmasked_nan).tolist()} with no env_missing mask "
                f"marking them unknown -- pass env_missing to exclude the "
                f"dimension for those rows, or supply a score."
            )


def point_z(person, env, conf_raw, cfg, weights, conf_missing=None, flat_zones=None,
            env_missing=None):
    """The linear predictor z at the weight means -- for RANKING.

    z is monotone in P(doing well) (sigmoid(z) is exactly that, see
    ordinal_probs), so ordering candidates by z orders them by fit without ever
    materialising a probability -- which is the rule for CompanyLens: no
    probability reaches a user until outcome data has trained the model
    (PRODUCT_DECISIONS.md section 2, 2026-10-13). Returns a float array length N.

    conf_missing / flat_zones / env_missing: see preprocess_conf and outcome_logit.
    """
    _validate_inputs(person, env, conf_raw, cfg, flat_zones=flat_zones,
                     env_missing=env_missing)
    conf = preprocess_conf(conf_raw, cfg, conf_missing=conf_missing)
    z = outcome_logit(person, env, conf, cfg, point_weights(weights), snap_person=True,
                      flat_zones=flat_zones, env_missing=env_missing)
    return np.asarray(z, dtype=float)


def point_p_fit(person, env, conf_raw, cfg, weights, conf_missing=None, flat_zones=None,
                env_missing=None):
    """Deterministic P(fit) at the weight means. `weights` has {mean, sd} leaves.

    conf_missing: optional {confounder_key: bool array length N} marking
    legitimately-absent confounder values, forwarded to preprocess_conf -- a masked
    row's term is excluded from z. Last and defaulting to None, so the serving path
    that never passes it is the unchanged path.
    flat_zones / env_missing: the hinge and the unknown-trait mask, see
    outcome_logit. Added after conf_missing, both defaulting to None.
    """
    return _sigmoid(point_z(person, env, conf_raw, cfg, weights, conf_missing=conf_missing,
                            flat_zones=flat_zones, env_missing=env_missing))


def score_pairs(person, env, conf_raw, cfg, weights, draws=2000, seed=0, interval=0.90,
                conf_missing=None, flat_zones=None, env_missing=None):
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

    conf_missing : optional {confounder_key: bool array length N} marking
                  legitimately-absent confounder values, forwarded to
                  preprocess_conf. Defaulting to None, so every existing
                  call is untouched.
    flat_zones / env_missing : the hinge and the unknown-trait mask, see
                  outcome_logit. Added after conf_missing, both defaulting to
                  None. With a zone, every draw prices the gap through the same
                  excess_gap, so the band is the band of the hinged predictor.
    """
    _validate_inputs(person, env, conf_raw, cfg, flat_zones=flat_zones,
                     env_missing=env_missing)
    conf = preprocess_conf(conf_raw, cfg, conf_missing=conf_missing)
    rng = np.random.default_rng(seed)

    p = np.empty((draws, len(np.atleast_1d(next(iter(person.values()))))))
    for i in range(draws):
        w = _draw_weights(weights, rng)
        p[i] = _sigmoid(outcome_logit(person, env, conf, cfg, w, snap_person=True,
                                      flat_zones=flat_zones, env_missing=env_missing))

    tail = (1.0 - interval) / 2.0
    return {
        "p_fit": p.mean(axis=0),
        "p_fit_low": np.quantile(p, tail, axis=0),
        "p_fit_high": np.quantile(p, 1.0 - tail, axis=0),
    }
