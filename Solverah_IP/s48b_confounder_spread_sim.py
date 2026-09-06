"""
S-48(b) support: how much stage_size / comp SPREAD does the 15-20 ground-truth set need?

Built 2026-08-20 against the REAL model structure, not a generic one. Sources opened rather
than recalled (the S-35 discipline):

  causal_graph/v1_model/solverah_model_config.yaml
  causal_graph/v1_model/match_core.py   (outcome_logit, preprocess_conf, fit_gap)

WHAT THE ARTIFACTS ACTUALLY SAY -- three facts that reframe the question
------------------------------------------------------------------------
1. `stage_size` is a CONFOUNDER, and it `biases: [autonomy, pace, collaboration, feedback,
   innovation, decision]` -- ALL SIX dimensions. `comp` biases only `[pace, autonomy]`.
   Both contribute exactly ONE additive term to the logit (w * standardized_value); the
   `biases` list is the DAG pathway, i.e. WHICH dimensions' gap weights get biased if the
   confounder is badly adjusted. So a stage_size failure contaminates six dimensions'
   mag/dir weights; a comp failure contaminates two.

2. Both are standardized with FIXED scale constants from config, not batch statistics:
       stage_size: mean 3.0, sd 1.5   # "placeholder stage-index stats; replace with real"
       comp:       mean 3.0, sd 1.0   # "Replace with real distribution once ~15 companies
                                      #  are scored."
   That comment is independent corroboration of the 15-20 size decision from a source
   nobody in the S-48 discussion had cited -- and it creates a trap, see finding 3 below.

3. THE CLUSTERING FACT, which is the load-bearing one. A confounder value is a property of
   the COMPANY. Every training row for that company carries the same value. So the
   information available about w_stage_size and w_comp is driven by BETWEEN-COMPANY
   variation, and adding more respondents per company buys none of it. This is the same
   cluster structure that S-48's power sim already had to correct for, and the same shape
   as the seed/n confound corrected in STATE section 5.

MODEL SIMULATED
---------------
Faithful to match_core.outcome_logit:
    z = intercept
        + sum_d [ w_mag_d * |gap_d| + w_dir_d * gap_d ]
        + w_stage * z_stage + w_comp * z_comp
    y ~ Bernoulli(sigmoid(z))
with gap_d = person_d - env_d on the real lattices, env_d shifted by the confounders it
`biases` (that is what makes them confounders rather than mere covariates), and z_* the
FIXED-constant standardization from config.

D-21 COMPLIANCE
---------------
Every reported contrast is paired across seeds (same seed -> same person draws and same
outcome noise in both arms; only the company spread profile differs), >= 3 draws, dispersion
reported. Arms differ only in the confounder spread profile, which is the whole point.
"""

import numpy as np
from scipy.optimize import minimize

# ---- from solverah_model_config.yaml (opened, not recalled) -------------------
DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
STAGE_BIASES = set(DIMS)                    # stage_size biases all six
COMP_BIASES = {"pace", "autonomy"}          # comp biases pace + autonomy only
STAGE_SCALE = {"mean": 3.0, "sd": 1.5}
COMP_SCALE = {"mean": 3.0, "sd": 1.0}

# from match_core.py
PERSON_LATTICE = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
COMPANY_LATTICE = np.array([0.1, 0.3, 0.5, 0.7, 0.9])

# true generating weights (illustrative but fixed across all arms, so contrasts are fair)
TRUE_W_MAG = -1.2      # any mismatch lowers fit
TRUE_W_DIR = 0.3
TRUE_W_STAGE = 0.5
TRUE_W_COMP = 0.4
TRUE_INTERCEPT = 0.0

# how strongly a confounder shifts the env score of a dimension it biases
STAGE_ENV_SHIFT = 0.06     # per unit of standardized stage
COMP_ENV_SHIFT = 0.05

N_RESPONDENTS_PER_COMPANY = 20


# ---- company spread profiles --------------------------------------------------
# Each returns (stage_raw, comp_raw) arrays of length n_companies.

def profile_prior_roster(rng, n):
    """~78% at stage 5 and comp 3 -- the recorded shape of the 2026-07-25 19-company roster.

    ASSUMPTION, stated because it is not verifiable from the repo: STATE records the prior
    roster as "~78% stage-5 / comp-3", read here as 78% sitting at BOTH modes. The roster
    docx itself is in Sebastian's Drive (ground_truth/roster/ on disk is empty), so this
    profile is a reconstruction, not a measurement. If the real roster spreads comp more
    than this, the comp finding below softens proportionally.
    """
    n_mode = int(round(0.78 * n))
    stage = np.concatenate([np.full(n_mode, 5.0),
                            rng.choice([1., 2., 3., 4.], size=n - n_mode)])
    comp = np.concatenate([np.full(n_mode, 3.0),
                           rng.choice([2., 4., 5.], size=n - n_mode)])
    return stage, comp


def profile_stage_spread_only(rng, n):
    """Deliberate stage spread (D-08's guard honoured), comp left at its roster shape."""
    stage = rng.choice([1., 2., 3., 4., 5.], size=n)
    n_mode = int(round(0.78 * n))
    comp = np.concatenate([np.full(n_mode, 3.0),
                           rng.choice([2., 4., 5.], size=n - n_mode)])
    return stage, comp


def profile_comp_spread_only(rng, n):
    """Deliberate comp spread, stage left at its roster shape."""
    n_mode = int(round(0.78 * n))
    stage = np.concatenate([np.full(n_mode, 5.0),
                            rng.choice([1., 2., 3., 4.], size=n - n_mode)])
    comp = rng.choice([1., 2., 3., 4., 5.], size=n)
    return stage, comp


def profile_both_spread(rng, n):
    """Both confounders deliberately spread across their full range."""
    return rng.choice([1., 2., 3., 4., 5.], size=n), rng.choice([1., 2., 3., 4., 5.], size=n)


PROFILES = {
    "prior_roster (78% stage5+comp3)": profile_prior_roster,
    "stage spread only": profile_stage_spread_only,
    "comp spread only": profile_comp_spread_only,
    "both spread": profile_both_spread,
}


# ---- data generation ----------------------------------------------------------

def standardize(raw, scale):
    return (np.asarray(raw, float) - scale["mean"]) / scale["sd"]


def snap_to_company_lattice(x):
    idx = np.abs(x[:, None] - COMPANY_LATTICE[None, :]).argmin(axis=1)
    return COMPANY_LATTICE[idx]


# Company-level unobserved heterogeneity (SD on the logit scale).
#
# NOT a decorative addition -- solverah_model_config.yaml declares:
#     - key: manager_quality
#       measurable: false
#       biases: [feedback, autonomy]
# i.e. the design already acknowledges a company-level factor that moves outcomes and is
# never a model term. That is precisely a company random intercept. An earlier version of
# this script omitted it, which made rows within a company conditionally independent given
# the covariates -- and under that (wrong) model more respondents DO buy confounder
# precision without limit, because there is nothing shared left to be uncertain about.
# Omitting it silently deletes the clustering the design says exists.
COMPANY_RE_SD = 0.5


def simulate(rng, stage_raw, comp_raw, n_per_company, company_re_sd=COMPANY_RE_SD):
    n_co = len(stage_raw)
    z_stage_co = standardize(stage_raw, STAGE_SCALE)
    z_comp_co = standardize(comp_raw, COMP_SCALE)

    rows_gap = {d: [] for d in DIMS}
    rows_zstage, rows_zcomp, rows_re = [], [], []
    company_re = rng.normal(0.0, company_re_sd, size=n_co)

    for i in range(n_co):
        for d in DIMS:
            base_env = rng.choice(COMPANY_LATTICE, size=n_per_company)
            shift = 0.0
            if d in STAGE_BIASES:
                shift = shift + STAGE_ENV_SHIFT * z_stage_co[i]
            if d in COMP_BIASES:
                shift = shift + COMP_ENV_SHIFT * z_comp_co[i]
            env = snap_to_company_lattice(np.clip(base_env + shift, 0.1, 0.9))
            person = rng.choice(PERSON_LATTICE, size=n_per_company)
            person_snapped = snap_to_company_lattice(person)
            rows_gap[d].append(person_snapped - env)
        rows_zstage.append(np.full(n_per_company, z_stage_co[i]))
        rows_zcomp.append(np.full(n_per_company, z_comp_co[i]))
        rows_re.append(np.full(n_per_company, company_re[i]))

    gaps = {d: np.concatenate(rows_gap[d]) for d in DIMS}
    z_stage = np.concatenate(rows_zstage)
    z_comp = np.concatenate(rows_zcomp)
    re_rows = np.concatenate(rows_re)

    z = np.full(z_stage.shape, TRUE_INTERCEPT, dtype=float)
    for d in DIMS:
        z += TRUE_W_MAG * np.abs(gaps[d]) + TRUE_W_DIR * gaps[d]
    z += TRUE_W_STAGE * z_stage + TRUE_W_COMP * z_comp
    z += re_rows          # company-level unobserved heterogeneity; never a model term
    y = (rng.uniform(size=z.shape) < 1.0 / (1.0 + np.exp(-z))).astype(float)

    # design matrix: intercept, per-dim mag+dir, stage, comp
    cols = [np.ones_like(z_stage)]
    for d in DIMS:
        cols.append(np.abs(gaps[d]))
        cols.append(gaps[d])
    cols.append(z_stage)
    cols.append(z_comp)
    X = np.column_stack(cols)
    return X, y


def fit_logistic(X, y, ridge=1e-4):
    """MLE with a whisper of ridge so a degenerate (zero-variance) column cannot blow up.

    The ridge is deliberately tiny: it keeps the solve finite when a confounder column is
    near-constant, WITHOUT rescuing the estimate. A near-unidentified coefficient must show
    up as a huge standard error, not as a silently regularized small one -- otherwise this
    script would hide the exact failure it exists to measure (the S-40 rule).
    """
    def nll(b):
        z = X @ b
        return np.sum(np.logaddexp(0, z) - y * z) + ridge * np.sum(b ** 2)

    def grad(b):
        z = X @ b
        p = 1.0 / (1.0 + np.exp(-z))
        return X.T @ (p - y) + 2 * ridge * b

    b0 = np.zeros(X.shape[1])
    res = minimize(nll, b0, jac=grad, method="L-BFGS-B",
                   options={"maxiter": 500, "ftol": 1e-12})
    b = res.x
    p = 1.0 / (1.0 + np.exp(-(X @ b)))
    W = p * (1 - p)
    XtWX = X.T @ (X * W[:, None]) + 2 * ridge * np.eye(X.shape[1])
    cov = np.linalg.pinv(XtWX)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    return b, se


IDX_STAGE = -2
IDX_COMP = -1


def between_company_info(raw, scale):
    """Sum of squared deviations of the STANDARDIZED value, across COMPANIES.

    This -- not the row count -- is what the confounder coefficient's precision scales with,
    because the value is constant within company.
    """
    z = standardize(raw, scale)
    return float(np.sum((z - z.mean()) ** 2))


def run(n_companies=19, n_seeds=8, n_per_company=N_RESPONDENTS_PER_COMPANY):
    names = list(PROFILES)
    se_stage = {k: [] for k in names}
    se_comp = {k: [] for k in names}
    info_stage = {k: [] for k in names}
    info_comp = {k: [] for k in names}
    bias_mag = {k: [] for k in names}

    for s in range(n_seeds):
        for name in names:
            # PAIRING, and it has to be structural rather than asserted (D-21(b)).
            # Two SEPARATE streams. The naive version -- one rng seeded per (seed, arm) --
            # is broken: the profile functions consume DIFFERENT amounts of randomness per
            # arm (prior_roster draws n-n_mode values, both_spread draws 2n), so the stream
            # state entering simulate() diverges and the person draws / outcome noise are
            # not matched across arms at all. That inflates every paired SD and silently
            # turns a paired contrast into an unpaired one -- the exact costume-change
            # D-21 was written to stop. Splitting the streams makes base_env, person draws
            # and outcome noise bitwise identical across arms, so the ONLY thing that
            # differs is the confounder spread, which is the treatment.
            rng_co = np.random.default_rng(1000 + s)        # company roster draw (differs by arm, by design)
            rng_sim = np.random.default_rng(50_000 + s)     # everything else (identical across arms)
            stage_raw, comp_raw = PROFILES[name](rng_co, n_companies)
            X, y = simulate(rng_sim, stage_raw, comp_raw, n_per_company)
            b, se = fit_logistic(X, y)
            se_stage[name].append(se[IDX_STAGE])
            se_comp[name].append(se[IDX_COMP])
            info_stage[name].append(between_company_info(stage_raw, STAGE_SCALE))
            info_comp[name].append(between_company_info(comp_raw, COMP_SCALE))
            mags = b[1:1 + 2 * len(DIMS):2]
            bias_mag[name].append(float(np.mean(mags - TRUE_W_MAG)))

    return names, se_stage, se_comp, info_stage, info_comp, bias_mag


def _fmt(vals):
    a = np.asarray(vals, float)
    return f"{a.mean():.3f} (SD {a.std(ddof=1):.3f}, n={len(a)})"


if __name__ == "__main__":
    N_CO = 19
    N_SEEDS = 8
    names, se_stage, se_comp, info_stage, info_comp, bias_mag = run(N_CO, N_SEEDS)

    print(f"Ground-truth set = {N_CO} companies x {N_RESPONDENTS_PER_COMPANY} respondents "
          f"= {N_CO * N_RESPONDENTS_PER_COMPANY} training rows")
    print(f"Paired across {N_SEEDS} seeds; arms differ ONLY in company spread profile (D-21).")
    print()
    print(f"{'profile':<34} {'SE(w_stage)':<24} {'SE(w_comp)':<24}")
    for k in names:
        print(f"{k:<34} {_fmt(se_stage[k]):<24} {_fmt(se_comp[k]):<24}")

    print()
    print("Between-COMPANY information (sum of squared standardized deviations).")
    print("This is what the coefficient precision scales with -- NOT the row count.")
    print(f"{'profile':<34} {'stage':<22} {'comp':<22}")
    for k in names:
        print(f"{k:<34} {_fmt(info_stage[k]):<22} {_fmt(info_comp[k]):<22}")

    print()
    print("Paired contrasts vs the prior-roster arm (per-seed differences, D-21):")
    base = "prior_roster (78% stage5+comp3)"
    for k in names:
        if k == base:
            continue
        d_stage = np.asarray(se_stage[base]) - np.asarray(se_stage[k])
        d_comp = np.asarray(se_comp[base]) - np.asarray(se_comp[k])
        print(f"  {k}")
        print(f"     SE(w_stage) reduction: {d_stage.mean():+.4f} "
              f"(paired SD {d_stage.std(ddof=1):.4f}, n={len(d_stage)})")
        print(f"     SE(w_comp)  reduction: {d_comp.mean():+.4f} "
              f"(paired SD {d_comp.std(ddof=1):.4f}, n={len(d_comp)})")

    print()
    print("Mean bias in recovered w_mag (all six dimensions), by profile:")
    for k in names:
        print(f"  {k:<34} {_fmt(bias_mag[k])}")
