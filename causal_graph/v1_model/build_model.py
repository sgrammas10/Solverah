"""
build_model.py -- reads the config + priors and builds the Solverah outcome model.

This is a real Bayesian model: every weight in priors.yaml is a prior
distribution (mean, sd), not a point estimate. `prior_predictive()` samples
predictions from the expert hypothesis alone (no data yet). `fit_posterior()`
conditions the same model on observed (person, env, conf) -> outcome rows and
returns the updated posterior via PyMC's NUTS sampler -- this is how real
placement outcomes are meant to pull the weights away from the expert guess
over time (see ../cbm_notes.txt).

Adding a dimension or confounder requires NO change here -- only the two
YAMLs (plus, for a new confounder, declaring its `kind` in
solverah_model_config.yaml so this file knows how to treat it: continuous
values get standardized, categorical values get one-hot per level).

    pip install pyyaml numpy pymc --break-system-packages
    python build_model.py
"""

import os

import numpy as np
import pymc as pm
import yaml

MODEL_DIR = os.path.dirname(os.path.abspath(__file__))


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
def fit_gap(person_score, env_score):
    return person_score - env_score            # signed, range -1..1


# ---------------------------------------------------------------------------
# Preprocess raw confounder values into what outcome_logit expects:
#   continuous  -> standardized with a FIXED {mean, sd} from config (fixed,
#                  not batch-computed, so a single-row prediction doesn't
#                  divide by an undefined std, and fit-time/predict-time
#                  scaling always agree)
#   categorical -> integer level-index array (for indexing a per-level
#                  weight vector)
# Called from both build_model() and the synthetic-data generator in
# sanity_check(), so the two can never apply different preprocessing.
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
#                 the synthetic data-generating process below) -- the
#                 arithmetic here (+, -, *, abs, indexing) doesn't care which.
# ---------------------------------------------------------------------------
def outcome_logit(person, env, conf, cfg, weights):
    feats = cfg["settings"]["gap_features"]     # e.g. ["mag", "dir"]
    z = weights["intercept"]

    for d in active(cfg["dimensions"]):
        k = d["key"]
        g = fit_gap(person[k], env[k])
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


def p_fit(person, env, conf, cfg, weights):
    """Symbolic only (pytensor sigmoid) -- for use inside a pm.Model() context.
    The synthetic-data generator below needs plain numpy and computes its own
    sigmoid from outcome_logit() directly instead of calling this."""
    return pm.math.sigmoid(outcome_logit(person, env, conf, cfg, weights))


# ---------------------------------------------------------------------------
# Turn priors.yaml's {mean, sd} pairs into actual PyMC random variables.
# Must be called inside a pm.Model() context. Mirrors pri's nested shape so
# outcome_logit() works unchanged whether it's given priors.yaml's point
# values or these RVs.
# ---------------------------------------------------------------------------
def sample_weights_from_priors(cfg, pri):
    feats = cfg["settings"]["gap_features"]
    weights = {
        "intercept": pm.Normal("intercept", mu=pri["intercept"]["mean"], sigma=pri["intercept"]["sd"]),
        "dimensions": {},
        "confounders": {},
    }

    for d in active(cfg["dimensions"]):
        k = d["key"]
        p = pri["dimensions"][k]
        weights["dimensions"][k] = {
            feat: pm.Normal(f"{k}_{feat}", mu=p[feat]["mean"], sigma=p[feat]["sd"])
            for feat in feats
        }

    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue
        k = c["key"]
        p = pri["confounders"][k]
        if c.get("kind") == "categorical":
            weights["confounders"][k] = pm.Normal(
                f"w_{k}", mu=p["mean"], sigma=p["sd"], shape=len(c["levels"])
            )
        else:
            weights["confounders"][k] = pm.Normal(f"w_{k}", mu=p["mean"], sigma=p["sd"])

    return weights


def build_model(person, env, conf, cfg, pri, outcome=None):
    """
    person, env : dict {dim_key: array-like, length N}
    conf        : dict {confounder_key: array-like, length N} -- RAW values
                  (preprocess_conf() is called internally)
    outcome     : optional array-like of 0/1, length N. If given, attaches a
                  Bernoulli likelihood so pm.sample() updates the priors into
                  a posterior; if omitted the model is prior-only.
    """
    with pm.Model() as model:
        weights = sample_weights_from_priors(cfg, pri)

        person_data = {
            d["key"]: pm.Data(f"person_{d['key']}", np.asarray(person[d["key"]], dtype=float))
            for d in active(cfg["dimensions"])
        }
        env_data = {
            d["key"]: pm.Data(f"env_{d['key']}", np.asarray(env[d["key"]], dtype=float))
            for d in active(cfg["dimensions"])
        }
        conf_data = {
            k: pm.Data(f"conf_{k}", v) for k, v in preprocess_conf(conf, cfg).items()
        }

        z = outcome_logit(person_data, env_data, conf_data, cfg, weights)
        pm.Deterministic("p_fit", pm.math.sigmoid(z))

        if outcome is not None:
            outcome_name = cfg["settings"]["outcome"]["name"]
            pm.Bernoulli(outcome_name, logit_p=z, observed=np.asarray(outcome))

    return model


def prior_predictive(person, env, conf, cfg, pri, draws=2000, random_seed=None):
    """P(fit) under the expert priors alone -- no observed outcomes yet."""
    model = build_model(person, env, conf, cfg, pri)
    with model:
        idata = pm.sample_prior_predictive(draws=draws, random_seed=random_seed)
    return idata.prior["p_fit"]


def fit_posterior(person, env, conf, outcome, cfg, pri, **sample_kwargs):
    """Update the priors on observed (person, env, conf) -> outcome data."""
    model = build_model(person, env, conf, cfg, pri, outcome=outcome)
    with model:
        idata = pm.sample(**sample_kwargs)
    return idata


# ---------------------------------------------------------------------------
# Derived views the config gives you for free
# ---------------------------------------------------------------------------
def dag_edges(cfg):
    """Confounder -> env-node edges, for DAGitty / drawing / adjustment sets."""
    edges = []
    for c in active(cfg["confounders"]):
        for dim in c["biases"]:
            edges.append((c["key"], f"env_{dim}"))
    return edges


def _synthetic_conf(confs, n, rng):
    out = {}
    for c in confs:
        if c.get("kind") == "categorical":
            out[c["key"]] = rng.choice(c["levels"], size=n)
        else:
            scale = c["scale"]
            out[c["key"]] = rng.normal(scale["mean"], scale["sd"], size=n)
    return out


def sanity_check(cfg, pri):
    dims = active(cfg["dimensions"])
    confs = [c for c in active(cfg["confounders"]) if c.get("measurable")]
    print(f"Active dimensions ({len(dims)}): {[d['key'] for d in dims]}")
    print(f"Active measurable confounders ({len(confs)}): {[c['key'] for c in confs]}")
    print(f"Outcome parents = {len(dims)} fits + {len(confs)} confounders "
          f"= {len(dims) + len(confs)}")

    rng = np.random.default_rng(0)

    # synthetic person/company: perfect match vs bad match, priors only
    perfect_p = {d["key"]: [0.5] for d in dims}
    perfect_e = {d["key"]: [0.5] for d in dims}
    bad_p = {d["key"]: [0.9] for d in dims}
    bad_e = {d["key"]: [0.1] for d in dims}
    conf_one = _synthetic_conf(confs, 1, rng)

    perfect_samples = np.asarray(
        prior_predictive(perfect_p, perfect_e, conf_one, cfg, pri, draws=1000, random_seed=0)
    ).flatten()
    bad_samples = np.asarray(
        prior_predictive(bad_p, bad_e, conf_one, cfg, pri, draws=1000, random_seed=1)
    ).flatten()

    print(f"\nP(fit) perfect match (gap=0 everywhere), prior-predictive: "
          f"{perfect_samples.mean():.3f} +/- {perfect_samples.std():.3f}")
    print(f"P(fit) large mismatch (gap=0.8 everywhere), prior-predictive: "
          f"{bad_samples.mean():.3f} +/- {bad_samples.std():.3f}")

    print(f"\nConfounder->env edges: {dag_edges(cfg)}")

    # --- synthetic-data fit: prove the posterior actually updates on data ---
    n = 200
    person = {d["key"]: rng.uniform(0, 1, n) for d in dims}
    env = {d["key"]: rng.uniform(0, 1, n) for d in dims}
    conf = _synthetic_conf(confs, n, rng)

    true_weights = {
        "intercept": 0.0,
        "dimensions": {d["key"]: {"mag": -1.0, "dir": 0.0} for d in dims},
        "confounders": {
            c["key"]: (np.zeros(len(c["levels"])) if c.get("kind") == "categorical" else 0.0)
            for c in confs
        },
    }
    true_weights["dimensions"]["pace"]["mag"] = -2.0  # deliberately off the prior mean (-1.0)

    z_true = outcome_logit(person, env, preprocess_conf(conf, cfg), cfg, true_weights)
    p_true = 1.0 / (1.0 + np.exp(-z_true))
    outcome = rng.binomial(1, p_true)

    print(f"\nFitting synthetic dataset (n={n}) -- planted pace.mag = -2.0 "
          f"(prior mean -1.0) ...")
    idata = fit_posterior(
        person, env, conf, outcome, cfg, pri,
        draws=1000, tune=1000, chains=2, target_accept=0.9,
        random_seed=0, progressbar=False,
    )

    pace_mag = idata.posterior["pace_mag"].values
    print(f"Posterior pace.mag: mean={pace_mag.mean():.3f}, sd={pace_mag.std():.3f} "
          f"(prior was mean=-1.0, sd=0.5; planted truth=-2.0)")


if __name__ == "__main__":
    cfg, pri = load()
    sanity_check(cfg, pri)
