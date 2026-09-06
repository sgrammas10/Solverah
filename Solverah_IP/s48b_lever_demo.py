"""
S-48(b), the decision-relevant half: WHICH LEVER buys confounder precision, and does the
model-reported precision mean anything?

Companion to s48b_confounder_spread_sim.py.

TWO QUANTITIES, AND THE GAP BETWEEN THEM IS THE POINT
------------------------------------------------------
  model SE   -- what a naive logistic fit reports. Computed assuming rows are independent.
  empirical  -- the SD of the point estimate across independently drawn rosters+datasets.
                This is the truth: "if I built one such ground-truth set, how far off could
                my w_stage be?"

`stage_size` and `comp` are COMPANY-level (solverah_model_config.yaml), so every row for a
company shares the value; and `manager_quality` is declared `measurable: false`, i.e. the
design admits company-level unobserved heterogeneity that is never a model term. Under that
structure rows within a company are NOT independent, so the naive model SE is understated
and shrinks with rows without limit, while the true uncertainty has a floor set by the
number and spread of COMPANIES.

If that is right: LEVER 1's model SE keeps falling while its empirical SD flattens, and the
ratio between them widens -- which is overconfidence, measured. This is the same failure
already corrected twice in this project (the seed/n pooled-CI confound in STATE section 5,
and the per-cell pooling in the S-48 size sim), arriving a third time in a new costume.
"""

import numpy as np

from s48b_confounder_spread_sim import (
    profile_prior_roster, profile_both_spread, simulate, fit_logistic,
    IDX_STAGE, IDX_COMP, TRUE_W_STAGE, TRUE_W_COMP,
)


def _sweep(profile, n_companies, n_per_company, n_seeds):
    """Return (mean model SE, empirical SD of estimate, mean |bias|) for stage and comp."""
    b_stage, b_comp, se_stage, se_comp = [], [], [], []
    for s in range(n_seeds):
        rng_co = np.random.default_rng(1000 + s)
        rng_sim = np.random.default_rng(50_000 + s)
        stage_raw, comp_raw = profile(rng_co, n_companies)
        X, y = simulate(rng_sim, stage_raw, comp_raw, n_per_company)
        b, se = fit_logistic(X, y)
        b_stage.append(b[IDX_STAGE]); b_comp.append(b[IDX_COMP])
        se_stage.append(se[IDX_STAGE]); se_comp.append(se[IDX_COMP])
    b_stage = np.asarray(b_stage); b_comp = np.asarray(b_comp)
    return {
        "model_se_stage": float(np.median(se_stage)),
        "emp_sd_stage": float(b_stage.std(ddof=1)),
        "model_se_comp": float(np.median(se_comp)),
        "emp_sd_comp": float(b_comp.std(ddof=1)),
        "bias_stage": float(b_stage.mean() - TRUE_W_STAGE),
        "bias_comp": float(b_comp.mean() - TRUE_W_COMP),
    }


def lever_respondents(n_companies=19, n_seeds=40, grid=(20, 80, 320, 1280)):
    return [(npc, n_companies * npc, _sweep(profile_prior_roster, n_companies, npc, n_seeds))
            for npc in grid]


def lever_companies(n_seeds=40, grid=(10, 15, 19, 25, 40), n_per_company=80):
    return [(n_co, n_co * n_per_company, _sweep(profile_prior_roster, n_co, n_per_company, n_seeds))
            for n_co in grid]


def spread_at_fixed_n(n_companies=19, n_per_company=80, n_seeds=40):
    return {
        "skewed (78% stage5+comp3)": _sweep(profile_prior_roster, n_companies, n_per_company, n_seeds),
        "deliberately spread": _sweep(profile_both_spread, n_companies, n_per_company, n_seeds),
    }


def _row(label, rows, r):
    return (f"  {label:<11}{rows:<7}"
            f"{r['model_se_stage']:.3f} / {r['emp_sd_stage']:.3f}  "
            f"(x{r['emp_sd_stage'] / max(r['model_se_stage'], 1e-9):.1f})      "
            f"{r['model_se_comp']:.3f} / {r['emp_sd_comp']:.3f}  "
            f"(x{r['emp_sd_comp'] / max(r['model_se_comp'], 1e-9):.1f})")


if __name__ == "__main__":
    N_SEEDS = 40
    hdr = (f"  {'':<11}{'rows':<7}{'stage: modelSE / empSD  (ratio)':<34}"
           f"{'comp: modelSE / empSD  (ratio)'}")

    print(f"LEVER 1 -- more RESPONDENTS per company (19 companies, skewed profile, "
          f"{N_SEEDS} seeds)")
    print(hdr)
    r1 = lever_respondents(n_seeds=N_SEEDS)
    for npc, rows, r in r1:
        print(_row(f"{npc}/co", rows, r))
    a, b = r1[0][2], r1[-1][2]
    print(f"  -> rows x64: model SE(stage) {a['model_se_stage']:.3f} -> {b['model_se_stage']:.3f} "
          f"({a['model_se_stage'] / b['model_se_stage']:.1f}x better)   "
          f"BUT empirical SD {a['emp_sd_stage']:.3f} -> {b['emp_sd_stage']:.3f} "
          f"({a['emp_sd_stage'] / b['emp_sd_stage']:.1f}x)")

    print()
    print(f"LEVER 2 -- more COMPANIES (80 respondents each, skewed profile, {N_SEEDS} seeds)")
    print(hdr)
    r2 = lever_companies(n_seeds=N_SEEDS)
    for n_co, rows, r in r2:
        print(_row(f"{n_co} co", rows, r))
    a2, b2 = r2[0][2], r2[-1][2]
    print(f"  -> companies 10->40: empirical SD(stage) {a2['emp_sd_stage']:.3f} -> "
          f"{b2['emp_sd_stage']:.3f}   SD(comp) {a2['emp_sd_comp']:.3f} -> {b2['emp_sd_comp']:.3f}")

    print()
    print(f"LEVER 3 -- SPREAD, holding 19 companies x 80 respondents fixed ({N_SEEDS} seeds)")
    print(hdr)
    for label, r in spread_at_fixed_n(n_seeds=N_SEEDS).items():
        print(_row(label[:11], 1520, r))
    s = spread_at_fixed_n(n_seeds=N_SEEDS)
    sk, sp = s["skewed (78% stage5+comp3)"], s["deliberately spread"]
    print(f"  -> spreading the SAME 19 companies: empirical SD(stage) {sk['emp_sd_stage']:.3f} -> "
          f"{sp['emp_sd_stage']:.3f}   SD(comp) {sk['emp_sd_comp']:.3f} -> {sp['emp_sd_comp']:.3f}")
