"""
s48_ground_truth_size_power_sim.py -- how many ground-truth companies does the calibration need?

REBUILT 2026-08-20 (S-55). The original delivered file was lost before it was placed on disk;
this is a reconstruction from its recorded writeup (`S48_ground_truth_size_power_sim_2026-08-20.md`).
The rebuilt run's numbers were checked against the writeup's recorded conclusions at rebuild
time; exact figures differ by seed and implementation detail, the qualitative result must not.

THE QUESTION
------------
For a candidate ground-truth set of N companies (6 dimensions each), can we reliably tell
whether the LLM extractor is systematically miscalibrated against the human-rater consensus, at
a magnitude that matters -- half a rubric band (0.10) or a full band (0.20, the D-12 ambiguity
threshold)?

MODEL AND ASSUMPTIONS (flagged, not hidden)
-------------------------------------------
- True latent score per company-dimension cell; human rater noise SD = 0.098 (measured, STATE
  section 5 lineage); human consensus = mean of n_raters draws; LLM = true + bias + noise.
- n_raters is SWEPT at 2 and 3, not asserted -- writeup: "it is exactly the value under dispute";
  sweeping both means this result does not need that question resolved first. (It turned out not
  to be the load-bearing variable here.)
- sigma_llm (the extractor's post-mean-of-5 noise) is SWEPT at 0.05 / 0.098 / 0.15 -- it has
  never been measured. Round 1 plus this calibration is what would measure it.
- THIS SCRIPT TREATS EVERY COMPANY x DIMENSION CELL AS INDEPENDENT. That assumption is exactly
  what `s48_clustering_check.py` interrogates -- read that before trusting any number here.
  (Its result: at moderate-to-severe packet-level correlation the naive pooled test's
  false-positive rate inflates to ~0.35-0.49, and the honest planning number becomes N~15-19.)

D-21: 400 trials/cell; power reported with its binomial SE; false-positive row (bias=0)
reported so calibration is visible, not assumed. Deterministic under SEED.
"""

from __future__ import annotations

import numpy as np

SEED = 48
TRIALS = 400
ALPHA = 0.05
DIMS = 6
RATER_SD = 0.098

N_COMPANIES = (6, 10, 15, 19)
N_RATERS = (2, 3)
SIGMA_LLM = (0.05, 0.098, 0.15)
BIAS = (0.0, 0.05, 0.10, 0.20)


def one_trial(rng, n_companies, n_raters, sigma_llm, bias):
    """One simulated calibration check. Returns True if the test rejects (bias detected)."""
    cells = n_companies * DIMS
    # true latent cancels in the delta; simulate it anyway so the structure is explicit
    true = rng.uniform(0.1, 0.9, size=cells)
    human = true + rng.normal(0.0, RATER_SD, size=(n_raters, cells)).mean(axis=0)
    llm = true + bias + rng.normal(0.0, sigma_llm, size=cells)
    delta = llm - human
    # One-sample test of mean(delta) == 0, two-sided, cells pooled as independent draws.
    # numpy-only: the critical value is the NORMAL 0.975 quantile (1.96), not the t quantile --
    # at the pooled df here (>= 35) the difference is negligible; at small df (the clustered
    # check's per-company collapse) it makes the test mildly anti-conservative, which is why
    # calibration (the bias=0 row) is REPORTED rather than assumed.
    n = delta.size
    t = delta.mean() / (delta.std(ddof=1) / np.sqrt(n))
    return abs(t) > 1.959964


def main():
    rng = np.random.default_rng(SEED)
    print(f"{'n_raters':>8} {'sigma_llm':>9} {'bias':>5} " + " ".join(f"N={n:<4}" for n in N_COMPANIES))
    for n_raters in N_RATERS:
        for sigma in SIGMA_LLM:
            for bias in BIAS:
                row = []
                for n in N_COMPANIES:
                    hits = sum(one_trial(rng, n, n_raters, sigma, bias) for _ in range(TRIALS))
                    p = hits / TRIALS
                    se = np.sqrt(p * (1 - p) / TRIALS)
                    row.append(f"{p:.3f}±{se:.3f}")
                label = "FP  " if bias == 0.0 else "pow "
                print(f"{n_raters:>8} {sigma:>9} {bias:>5} {label}" + " ".join(row))


if __name__ == "__main__":
    main()
