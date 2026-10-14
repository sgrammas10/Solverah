"""power_sim.py -- how many blocks and raters the fit-pairs comparison needs.

Generative model, deliberately simple and stated so it can be argued with (the habit of
causal_graph/v1_model/prereg_power_sim.py):
  - B blocks of M=5 companies. The model's within-block value is z ~ N(0,1), coarsened to a
    0.5 grid so about one block pair in seven is a model tie (the design has exact ties:
    unknown and inside-tolerance cases).
  - The raters' shared truth is f = rho*z + sqrt(1-rho^2)*u, u ~ N(0,1) the same for every
    rater: the part where people systematically disagree with the model. rho is the
    quantity the study is about.
  - Each rater reads f with their own noise sigma and their own scale offset, cut into the
    five-point scale at fixed quantiles (10/30/60/85%), and abstains on 5% of pairs.
  - The statistic is the analysis module's own stratified tau-b (consensus = median).

Reference: for continuous data tau = (2/pi)*asin(rho): rho 0.9 -> 0.71, 0.7 -> 0.49,
0.5 -> 0.33, 0.3 -> 0.19.

Run:  python power_sim.py      (about a minute; ASCII output)
"""

from __future__ import annotations

import statistics
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_pairs_analysis import (DEFAULTS_STAND_TAU, GATE_INTER_RATER_TAU, REVIEW_TAU,  # noqa: E402
                                stratified_tau_b)

M = 5
CUTS = np.array([0.10, 0.30, 0.60, 0.85])
Z_QUANT = np.array([-1.2816, -0.5244, 0.2533, 1.0364])   # normal quantiles of CUTS


def one_run(B, R, rho, sigma, rng):
    z = np.round(rng.standard_normal((B, M)) * 2) / 2
    u = rng.standard_normal((B, M))
    f = rho * z + np.sqrt(1 - rho ** 2) * u
    scale = np.sqrt(1 + sigma ** 2)
    ratings = []
    for _ in range(R):
        y = f + sigma * rng.standard_normal((B, M)) + rng.normal(0, 0.3)
        r = 1 + np.searchsorted(Z_QUANT * scale, y)
        r = r.astype(float)
        r[rng.random((B, M)) < 0.05] = np.nan
        ratings.append(r)
    stack = np.stack(ratings)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        cnt = np.sum(~np.isnan(stack), axis=0)
        med = np.where(cnt >= 2, np.nanmedian(stack, axis=0), np.nan)

    def strata(xs, ys):
        return [[(None if np.isnan(x) else float(x), float(y)) for x, y in zip(xs[b], ys[b])]
                for b in range(B)]

    cons_tau = stratified_tau_b(strata(med, z))
    inter = []
    for i in range(R):
        for j in range(i + 1, R):
            t = stratified_tau_b([[(None if np.isnan(a) else float(a), None if np.isnan(b) else float(b))
                                   for a, b in zip(stack[i][k], stack[j][k])] for k in range(B)])
            if t is not None:
                inter.append(t)
    return cons_tau, (statistics.mean(inter) if inter else None)


def summarise(B, R, rho, sigma, sims=400, seed=20261013):
    rng = np.random.default_rng(seed)
    ts, gs = [], []
    for _ in range(sims):
        t, g = one_run(B, R, rho, sigma, rng)
        ts.append(t)
        gs.append(g)
    ts = np.array([np.nan if t is None else t for t in ts])
    gs = np.array([np.nan if g is None else g for g in gs])
    passed = gs >= GATE_INTER_RATER_TAU
    return {
        "tau_mean": np.nanmean(ts), "tau_p05": np.nanpercentile(ts, 5), "tau_p95": np.nanpercentile(ts, 95),
        "gate_pass": passed.mean(),
        "stand": np.mean(passed & (ts >= DEFAULTS_STAND_TAU)),
        "review": np.mean(passed & (ts < REVIEW_TAU)),
        "inter_mean": np.nanmean(gs),
    }


def main():
    print("B=blocks (5 pairs each), R=raters, sigma=rater noise; 400 sims per row")
    print("stand = P(gate passes and consensus tau >= %.2f); review = P(gate passes and tau < %.2f)"
          % (DEFAULTS_STAND_TAU, REVIEW_TAU))
    print("%3s %2s %5s %5s | %6s %6s %6s | %6s %6s | %5s %6s"
          % ("B", "R", "rho", "sig", "tau", "p05", "p95", "inter", "gate", "stand", "review"))
    for sigma in (0.5, 0.8):
        for R in (2, 3, 5):
            for B in (4, 6, 8, 10):
                for rho in (0.9, 0.7, 0.5, 0.3):
                    s = summarise(B, R, rho, sigma)
                    print("%3d %2d %5.2f %5.2f | %6.3f %6.3f %6.3f | %6.3f %6.2f | %5.2f %6.2f"
                          % (B, R, rho, sigma, s["tau_mean"], s["tau_p05"], s["tau_p95"],
                             s["inter_mean"], s["gate_pass"], s["stand"], s["review"]))


if __name__ == "__main__":
    main()
