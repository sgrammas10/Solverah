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

# setdefault, not a hard assignment: the original dev machine had no C++ compiler, so
# this forced the slow pure-Python linker unconditionally, even on machines (e.g. CI, this
# analysis environment) that have g++ and would sample far faster with it. Set
# PYTENSOR_FLAGS=cxx=<path> in the environment before running to opt into compiled mode;
# unset environments keep the original no-compiler-required behavior.
os.environ.setdefault("PYTENSOR_FLAGS", "cxx=")

import numpy as np
import pymc as pm
import yaml
import arviz as az

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


def p_fit(person, env, conf, cfg, weights, snap_person=True):
    """Symbolic only (pytensor sigmoid) -- for use inside a pm.Model() context.
    The synthetic-data generator below needs plain numpy and computes its own
    sigmoid from outcome_logit() directly instead of calling this. Pass
    snap_person=False if person is already-snapped pm.Data (see build_model())."""
    return pm.math.sigmoid(outcome_logit(person, env, conf, cfg, weights, snap_person=snap_person))


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

        # Snap person values onto COMPANY_LATTICE in plain numpy BEFORE they become
        # pm.Data -- closest_achievable() is a numpy argmin and cannot run on a pytensor
        # symbolic tensor, so this is the one place the fit_gap() correction can happen
        # for the model-fitting path. outcome_logit() is then called with
        # snap_person=False below so it isn't (and can't be) re-applied symbolically.
        person_data = {
            d["key"]: pm.Data(
                f"person_{d['key']}",
                closest_achievable(np.asarray(person[d["key"]], dtype=float)),
            )
            for d in active(cfg["dimensions"])
        }
        env_data = {
            d["key"]: pm.Data(f"env_{d['key']}", np.asarray(env[d["key"]], dtype=float))
            for d in active(cfg["dimensions"])
        }
        conf_data = {
            k: pm.Data(f"conf_{k}", v) for k, v in preprocess_conf(conf, cfg).items()
        }

        z = outcome_logit(person_data, env_data, conf_data, cfg, weights, snap_person=False)
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

    # synthetic person/company: perfect match vs bad match, priors only. person values are
    # PERSON_LATTICE points (0.9 isn't reachable on the real 5-point person ladder, unlike
    # before this pass -- see the pole-candidate check just below for why that distinction
    # now matters).
    perfect_p = {d["key"]: [0.5] for d in dims}
    perfect_e = {d["key"]: [0.5] for d in dims}
    bad_p = {d["key"]: [1.0] for d in dims}
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

    # Regression check for the Finding-1 fix (lattice_gap_analysis.py section A): a pole
    # candidate (person=1.0, every dimension) matched against the closest env CAN ever
    # offer (0.9) should now price in as a near-perfect match, not a structurally
    # mismatched one. Before the fix this printed P(fit)~0.35 despite being the best match
    # a 0.9-ceiling env can produce -- the same 45%-of-odds penalty the analysis quantified.
    pole_p = {d["key"]: [1.0] for d in dims}
    pole_e = {d["key"]: [0.9] for d in dims}  # closest achievable company value to 1.0
    pole_samples = np.asarray(
        prior_predictive(pole_p, pole_e, conf_one, cfg, pri, draws=1000, random_seed=2)
    ).flatten()
    print(f"P(fit) pole candidate, closest-achievable match (person=1.0, env=0.9), "
          f"prior-predictive: {pole_samples.mean():.3f} +/- {pole_samples.std():.3f}")
    print("  (pre-fix this read ~0.35, i.e. priced as a mismatch; should now sit close to "
          "the perfect-match number above, since 0.9 is the best this env can ever offer)")

    print(f"\nConfounder->env edges: {dag_edges(cfg)}")

    # --- synthetic-data fit: prove the posterior actually updates on data ---
    # Draw from the REAL lattices, not rng.uniform(0,1) (lattice_gap_analysis.py section
    # D / Finding 2): the instruments can only ever emit PERSON_LATTICE's 5 person values
    # and COMPANY_LATTICE's 53 achievable env values (~200k distinct |gap| values under
    # uniforms vs. 53 in reality), so validating against continuous uniforms assumes a gap
    # resolution the pipeline doesn't have and makes every n-needed figure optimistic by an
    # unmeasured amount.
    n = 200
    person = {d["key"]: rng.choice(PERSON_LATTICE, n) for d in dims}
    env = {d["key"]: closest_achievable(rng.random(n)) for d in dims}
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
        draws=1000, tune=1000, chains=4, target_accept=0.9,
        random_seed=0, progressbar=False,
    )

    pace_mag = idata.posterior["pace_mag"].values
    print(f"Posterior pace.mag: mean={pace_mag.mean():.3f}, sd={pace_mag.std():.3f} "
          f"(prior was mean=-1.0, sd=0.5; planted truth=-2.0)")


def recovery_curve(cfg, pri, ns=(200, 800, 2000, 5000),
                   planted_dim="pace", planted_val=-2.0, seed=0, **sample_kwargs):
    """Refit on growing prefixes of ONE synthetic dataset and watch the target
    weight converge from the prior toward the planted truth. This is the test
    that actually earns the claim 'data updates the weights'."""
    dims = active(cfg["dimensions"])
    confs = [c for c in active(cfg["confounders"]) if c.get("measurable")]
    rng = np.random.default_rng(seed)
    n_max = max(ns)

    # one big dataset; use prefixes so the curve is apples-to-apples. Drawn from the real
    # lattices, not rng.uniform(0,1) -- see the matching comment in sanity_check() and
    # lattice_gap_analysis.py section D. This is what Finding 2 says invalidates every
    # n-needed number quoted before this fix: the resolution of the validation data did
    # not match what the instruments can actually produce.
    person = {d["key"]: rng.choice(PERSON_LATTICE, n_max) for d in dims}
    env    = {d["key"]: closest_achievable(rng.random(n_max)) for d in dims}
    conf   = _synthetic_conf(confs, n_max, rng)

    true_weights = {
        "intercept": 0.0,
        "dimensions": {d["key"]: {"mag": -1.0, "dir": 0.0} for d in dims},
        "confounders": {c["key"]: (np.zeros(len(c["levels"]))
                        if c.get("kind") == "categorical" else 0.0) for c in confs},
    }
    true_weights["dimensions"][planted_dim]["mag"] = planted_val

    z = outcome_logit(person, env, preprocess_conf(conf, cfg), cfg, true_weights)
    y_all = rng.binomial(1, 1.0 / (1.0 + np.exp(-z)))

    target = f"{planted_dim}_mag"
    pm_ = pri["dimensions"][planted_dim]["mag"]
    kw = dict(draws=1000, tune=1000, chains=2, target_accept=0.9,
              random_seed=seed, progressbar=False)
    kw.update(sample_kwargs)

    print(f"\nRecovery curve for {target}  (prior {pm_['mean']}/{pm_['sd']}, truth {planted_val})")
    print(f"{'n':>7} {'post_mean':>10} {'post_sd':>9} {'|err|':>7} {'r_hat':>6}")
    rows = []
    for n in ns:
        sub = lambda d: {k: v[:n] for k, v in d.items()}
        idata = fit_posterior(sub(person), sub(env), sub(conf), y_all[:n], cfg, pri, **kw)
        s = idata.posterior[target].values
        m, sd = float(s.mean()), float(s.std())
        rhat = float(az.rhat(idata)[target].values)
        rows.append((n, m, sd))
        print(f"{n:>7} {m:>10.3f} {sd:>9.3f} {abs(m - planted_val):>7.3f} {rhat:>6.2f}")
    return rows

def plot_recovery(rows, planted_val=-2.0, prior_mean=-1.0, out="recovery_curve.png"):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ns, means, sds = zip(*rows)
    plt.figure(figsize=(7, 4.5))
    plt.errorbar(ns, means, yerr=sds, marker="o", capsize=4, label="posterior mean ± sd")
    plt.axhline(planted_val, ls="--", color="crimson", label=f"planted truth ({planted_val})")
    plt.axhline(prior_mean, ls=":", color="gray", label=f"prior mean ({prior_mean})")
    plt.xscale("log"); plt.xlabel("training rows (n)"); plt.ylabel("pace_mag")
    plt.title("Bayesian updating: posterior → truth as data grows")
    plt.legend(); plt.tight_layout(); plt.savefig(out, dpi=130)
    print("saved", out)

if __name__ == "__main__":
    cfg, pri = load()
    sanity_check(cfg, pri)

    # recovery_curve() now draws from PERSON_LATTICE/COMPANY_LATTICE (Finding 2), not
    # uniform(0,1) -- already re-run once this session with chains=2 to fit a reasonable
    # wall-clock budget (see SOLVERAH_HANDOFF_2026-08-17e.md for the full before/after
    # numbers and recovery_curve_LATTICE_FIXED.png vs recovery_curve_UNIFORM_ORIGINAL.png).
    # Left commented by default because a full run at chains=4 takes several minutes.
    #rows = recovery_curve(cfg, pri, ns=(200, 800, 2000, 5000), chains=4)
    #plot_recovery(rows)