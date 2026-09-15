"""
s48_clustering_check.py -- naive-vs-clustered correction for the S-48 size question.

REBUILT 2026-08-20 (S-55). The original delivered file was lost before it was placed on disk;
reconstruction from `S48_ground_truth_size_power_sim_2026-08-20.md`. Rebuilt numbers were
checked against the writeup's recorded table at rebuild time; exact figures differ by seed,
the qualitative result must not.

WHY THIS EXISTS
---------------
`s48_ground_truth_size_power_sim.py` pools every company x dimension cell as an independent
draw. That is questionable for the same reason STATE section 5 already documents once (the
pooled seed-sweep contrast): if a single company's packet is unusually clear or unusually
ambiguous, it can push the LLM (or a human rater) off in the same direction on several of that
company's dimensions at once. A packet-level effect is a company-level unit correlated across
its 6 sub-observations -- not a per-dimension coincidence.

THE COMPARISON
--------------
At within-company noise correlation rho in {0, 0.5, 0.9}:
  NAIVE      -- pool all N*6 deltas, one-sample test.
  CLUSTERED  -- collapse to ONE value per company first (mean delta), test over N values.
                (Same fix pattern as `paired_contrast` / D-21(b): effective N for a
                company-level quantity is distinct companies, not row count.)

The false-positive rows (bias=0) are the important ones: an anti-conservative naive test
produces a false "the extractor is miscalibrated" verdict from nothing more than one confusing
or one unusually clean packet.

D-21: 400 trials/cell, binomial SE printed, calibration reported not assumed. Deterministic
under SEED. numpy-only; the 1.96 normal critical value makes the clustered small-N test mildly
anti-conservative, visible in its own bias=0 row.
"""

from __future__ import annotations

import numpy as np

SEED = 4848
TRIALS = 400
DIMS = 6
RATER_SD = 0.098
SIGMA_LLM = 0.098
N_RATERS = 2
CRIT = 1.959964

N_COMPANIES = (6, 10, 15, 19)
RHO = (0.0, 0.5, 0.9)
BIAS = (0.0, 0.10)


def one_trial(rng, n_companies, rho, bias):
    """Returns (naive_rejects, clustered_rejects) for one simulated round."""
    true = rng.uniform(0.1, 0.9, size=(n_companies, DIMS))
    # A packet-level effect pushes the LLM *or a human rater* off in the same direction across
    # that company's dimensions (writeup, Result 2). Each side gets its own company-level shared
    # component (they are different readings of the same packet, not the same error), with total
    # noise SD held constant: shared^2 + idiosyncratic^2 = sigma^2.
    h_shared = rng.normal(0.0, RATER_SD * np.sqrt(rho), size=(n_companies, 1))
    h_idio = rng.normal(0.0, RATER_SD * np.sqrt(1.0 - rho), size=(N_RATERS, n_companies, DIMS))
    human = true + h_shared + h_idio.mean(axis=0)
    l_shared = rng.normal(0.0, SIGMA_LLM * np.sqrt(rho), size=(n_companies, 1))
    l_idio = rng.normal(0.0, SIGMA_LLM * np.sqrt(1.0 - rho), size=(n_companies, DIMS))
    llm = true + bias + l_shared + l_idio
    delta = llm - human

    flat = delta.ravel()
    t_naive = flat.mean() / (flat.std(ddof=1) / np.sqrt(flat.size))

    per_company = delta.mean(axis=1)
    t_clust = per_company.mean() / (per_company.std(ddof=1) / np.sqrt(per_company.size))

    return abs(t_naive) > CRIT, abs(t_clust) > CRIT


def main():
    rng = np.random.default_rng(SEED)
    print(f"{'rho':>4} {'bias':>5} {'N':>3} {'naive':>13} {'clustered':>13}")
    for rho in RHO:
        for bias in BIAS:
            for n in N_COMPANIES:
                hits_n = hits_c = 0
                for _ in range(TRIALS):
                    rn, rc = one_trial(rng, n, rho, bias)
                    hits_n += rn
                    hits_c += rc
                pn, pc = hits_n / TRIALS, hits_c / TRIALS
                sen = np.sqrt(pn * (1 - pn) / TRIALS)
                sec = np.sqrt(pc * (1 - pc) / TRIALS)
                tag = "FP " if bias == 0.0 else "pow"
                print(f"{rho:>4} {bias:>5} {n:>3} {tag} {pn:.3f}±{sen:.3f}  {tag} {pc:.3f}±{sec:.3f}")


if __name__ == "__main__":
    main()
