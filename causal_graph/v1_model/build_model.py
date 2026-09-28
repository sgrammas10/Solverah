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

from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pymc as pm
import pytensor.tensor as pt
import arviz as az

# The deterministic core -- lattices, gap correction, confounder preprocessing, and THE
# linear predictor -- lives in match_core.py so the app can serve predictions without
# importing PyMC (S-45 item 6, 2026-08-19). It is imported (not duplicated) here, and
# re-exported under the original names so existing consumers (recovery_multiseed.py's
# `import build_model as bm`, run_vignette_probe, analysis scripts) keep working
# unchanged. Do NOT redefine any of these names in this file: two implementations of the
# same formula is how they diverge, and tests/test_match_scoring.py asserts this file
# does not grow its own copies.
from match_core import (  # noqa: F401  (re-exports are the compatibility surface)
    BAND_VALUES,
    COMPANY_LATTICE,
    MODEL_DIR,
    N_RUNS,
    PERSON_LATTICE,
    active,
    closest_achievable,
    fit_gap,
    load,
    outcome_logit,
    preprocess_conf,
)


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


# ---------------------------------------------------------------------------
# THE ORDINAL HEAD  (D-20, mapping ruled 2026-09-17)
#
# `experienced` -- "overall, how well is this role working for you", 1..5 -- is
# the only outcome the environment-report source produces, and it is never
# dichotomized into the Bernoulli path. It trains through OrderedLogistic over
# the SAME linear predictor z.
#
# priors.yaml's weights were elicited on a BINARY scale: sigmoid(z) = P(still
# doing well after a year), "doing well" being a rating of 4 or 5. The three
# functions below make that exact rather than approximate, so those numbers
# need no rescaling to serve the ordinal head:
#
#   pymc:   P(Y <= k) = sigmoid(c_k - eta)      (OrderedLogistic.compute_p;
#                                                verified in pymc 5.25.1, whose
#                                                source reads `pa = sigmoid(
#                                                cutpoints - shape_padright(eta))`)
#   here:   eta = z, the FULL linear predictor, intercept included
#           c_3 = 0, PINNED -- a constant, not a random variable
#   =>      P(Y >= 4) = 1 - sigmoid(0 - z) = sigmoid(z),  identically
#
# The pin is not a nicety. An intercept and a free cutpoint vector are jointly
# unidentified: shift every cutpoint by d and the intercept by d and the
# likelihood is unchanged. Nothing fails -- the sampler runs, and the intercept
# quietly stops meaning "8 in 10 still doing well". Pinning the cutpoint below
# `doing_well_at` is what ties the intercept back to the expert's answer.
#
# Dropping the intercept from eta instead would also identify the model, and is
# the wrong fix: sigmoid(z) in the SERVING path (match_core.point_p_fit /
# score_pairs, which the web layer calls) would stop being P(doing well).
# ---------------------------------------------------------------------------
def head_config(cfg: Mapping[str, Any], head: str) -> dict:
    """The `settings.heads` block for `head`, as a plain dict.

    `settings.outcome` is kept as the legacy alias of `heads.appeal` (see the
    config's own comment) -- this reads `heads`, and falls back to `outcome`
    for `appeal` so a config predating the `heads` block still builds the
    binary model.
    """
    heads = cfg["settings"].get("heads") or {}
    if head in heads:
        return dict(heads[head])
    if head == "appeal":
        return dict(cfg["settings"]["outcome"])
    raise ValueError(
        "unknown outcome head %r -- solverah_model_config.yaml defines %s"
        % (head, sorted(heads) or ["appeal (via the legacy settings.outcome block)"])
    )


def pinned_cutpoint_index(head_cfg: Mapping[str, Any]) -> int:
    """Index, into the length-(levels-1) cutpoint vector, of the cutpoint pinned at 0.

    DERIVED from `doing_well_at` rather than hardcoded to rating 4's position,
    so a config that moves the "doing well" threshold moves the pin with it and
    sigmoid(z) goes on meaning P(rating >= doing_well_at). Cutpoint j (0-based)
    separates rating j+1 from rating j+2, so the boundary just below rating D
    is index D - 2.
    """
    levels = int(head_cfg["levels"])
    doing_well_at = int(head_cfg["doing_well_at"])
    if levels < 3:
        raise ValueError(
            "ordinal head needs at least 3 levels, config says %d -- a 2-level "
            "ordinal is the Bernoulli head" % levels
        )
    if not 2 <= doing_well_at <= levels:
        raise ValueError(
            "doing_well_at=%d is out of range for a %d-level head: it must name a "
            "rating with at least one rating below it (2..%d), because the cutpoint "
            "below it is what gets pinned" % (doing_well_at, levels, levels)
        )
    return doing_well_at - 2


def ordinal_cutpoints(head_cfg: Mapping[str, Any],
                      pri: Mapping[str, Any],
                      name: str = "cut_spacing"):
    """Ascending cutpoint vector with the `doing_well_at` boundary pinned at 0.

    Built from POSITIVE spacings rather than from ordered random variables:
    ordering then holds by construction, and there is no `ordered` transform to
    fight the one element that must stay constant. The spacings are a single
    LogNormal vector RV, `cut_spacing`, read low cutpoint to high:

        cut_spacing[i < pin]   -- gaps below the pin, nearest-the-pin LAST
        cut_spacing[i >= pin]  -- gaps above the pin, nearest-the-pin FIRST

    At 5 levels / doing_well_at 4 that is [d_low1, d_low2, d_high], giving
    cutpoints [-(d_low1 + d_low2), -d_low2, 0, d_high].
    """
    levels = int(head_cfg["levels"])
    pin = pinned_cutpoint_index(head_cfg)
    n_below = pin
    n_above = (levels - 1) - pin - 1

    spacing = pri["cutpoints"]["spacing"]
    gaps = pm.LogNormal(
        name,
        mu=float(spacing["mu_log"]),
        sigma=float(spacing["sigma_log"]),
        shape=(n_below + n_above,),
    )

    # reversed cumulative sum: the gap nearest the pin contributes to every
    # cutpoint below it, the next one down to all but the nearest, and so on.
    below = -pt.cumsum(gaps[:n_below][::-1])[::-1]
    above = pt.cumsum(gaps[n_below:])
    return pt.concatenate([below, pt.zeros(1), above])


def ordinal_observed(outcome: Sequence[Any], levels: int) -> np.ndarray:
    """1..levels ratings -> 0-based category indices for OrderedLogistic.

    Refuses anything that is not already an integer rating in range. Never
    clips and never rounds: a 3.5 means the caller thinks the scale is
    continuous and a 0 or a 6 means the row was assembled under a different
    instrument -- either one silently coerced is a wrong likelihood.
    """
    values = np.asarray(outcome, dtype=float)
    finite = np.isfinite(values)
    bad = ~finite
    bad = bad | (values != np.floor(np.where(finite, values, 0.0)))
    bad = bad | (np.where(finite, values, 1.0) < 1) | (np.where(finite, values, 1.0) > levels)
    if np.any(bad):
        flat_vals, flat_bad = np.atleast_1d(values), np.atleast_1d(bad)
        offenders = sorted({float(v) for v in flat_vals[flat_bad]})
        raise ValueError(
            "ordinal outcome must be an integer rating in 1..%d; got %s at row(s) %s"
            % (levels, offenders, np.flatnonzero(flat_bad).tolist())
        )
    return values.astype(int) - 1


def build_model(person, env, conf, cfg, pri, outcome=None, head: str = "appeal",
                conf_missing: Optional[Mapping[str, Any]] = None):
    """
    person, env : dict {dim_key: array-like, length N}
    conf        : dict {confounder_key: array-like, length N} -- RAW values
                  (preprocess_conf() is called internally)
    outcome     : optional observed outcomes, length N. If given, attaches the
                  head's likelihood so pm.sample() updates the priors into a
                  posterior; if omitted the model is prior-only.
                    head="appeal"      -> 0/1, Bernoulli
                    head="experienced" -> integer 1..levels, OrderedLogistic
    head        : which `settings.heads` block to attach. "appeal" is the
                  default and reproduces the pre-2026-09-17 model exactly.
                  "experienced" never dichotomizes -- that is D-20.
    conf_missing: optional dict {confounder_key: bool array, length N} marking
                  legitimately-absent confounder values (a "not sure" comp, an
                  `industry` the instrument never asked). A masked confounder's
                  term is excluded from z for that row, continuous or
                  categorical -- see match_core.preprocess_conf. A masked
                  categorical additionally yields a `conf_{key}__present`
                  pm.Data; with nothing masked the pm.Data names and free RVs
                  are exactly what they were before conf_missing existed.

    `p_fit` is a pm.Deterministic on BOTH heads and means the same thing on
    both: P(this goes well). On the ordinal head that is P(rating >=
    doing_well_at), which the pinned cutpoint makes exactly sigmoid(z).
    """
    head_cfg = head_config(cfg, head)
    is_ordinal = head_cfg.get("type") == "ordinal"

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
            k: pm.Data(f"conf_{k}", v)
            for k, v in preprocess_conf(conf, cfg, conf_missing=conf_missing).items()
        }

        z = outcome_logit(person_data, env_data, conf_data, cfg, weights, snap_person=False)
        pm.Deterministic("p_fit", pm.math.sigmoid(z))

        if not is_ordinal:
            if outcome is not None:
                pm.Bernoulli(head_cfg["name"], logit_p=z, observed=np.asarray(outcome))
            return model

        levels = int(head_cfg["levels"])
        cutpoints = ordinal_cutpoints(head_cfg, pri)
        # The same function pymc's own likelihood uses, so p_rating cannot drift
        # from what OrderedLogistic scores. compute_p=False below then avoids a
        # second, identically-valued `<name>_probs` deterministic.
        pm.Deterministic("p_rating", pm.OrderedLogistic.compute_p(z, cutpoints))

        if outcome is not None:
            pm.OrderedLogistic(
                head_cfg["name"],
                eta=z,
                cutpoints=cutpoints,
                observed=ordinal_observed(outcome, levels),
                compute_p=False,
            )

    return model


def prior_predictive(person, env, conf, cfg, pri, draws=2000, random_seed=None,
                     head: str = "appeal",
                     conf_missing: Optional[Mapping[str, Any]] = None):
    """P(fit) under the expert priors alone -- no observed outcomes yet.

    `head` and `conf_missing` are passed through to build_model() and default to
    the pre-2026-09-17 behavior. They go LAST because recovery_multiseed.py and
    the analysis scripts call this positionally.
    """
    model = build_model(person, env, conf, cfg, pri, head=head, conf_missing=conf_missing)
    with model:
        idata = pm.sample_prior_predictive(draws=draws, random_seed=random_seed)
    return idata.prior["p_fit"]


def fit_posterior(person, env, conf, outcome, cfg, pri, head: str = "appeal",
                  conf_missing: Optional[Mapping[str, Any]] = None, **sample_kwargs):
    """Update the priors on observed (person, env, conf) -> outcome data.

    head="experienced" fits the 1..5 ordinal through OrderedLogistic; see
    build_model(). `outcome` is passed to the head unchanged -- nothing here
    ever dichotomizes an experienced rating (D-20).
    """
    model = build_model(person, env, conf, cfg, pri, outcome=outcome, head=head,
                        conf_missing=conf_missing)
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