"""
recovery_multiseed.py -- multi-seed, 2x2 factorial replacement for the single-seed
recovery_curve() comparison reported in SOLVERAH_HANDOFF_2026-08-17e.md section 3.

WHY THIS IS NOT JUST "recovery_curve() in a for-loop over seeds":

(1) The -17e comparison changed TWO things at once. The "uniform (old)" column was
    uniform DGP + UNPATCHED model (no person snap); the "lattice (new)" column was
    lattice DGP + PATCHED model (person snapped onto COMPANY_LATTICE). So the 2.5x
    figure is attributed entirely to Finding 2 (data resolution) when it also
    contains whatever Finding 1's fix does to recovery. This script runs the full
    2x2 so the two effects can be separated:

        A  uniform_raw     = continuous uniform DGP, no snap   (the ORIGINAL pipeline)
        B  lattice_snap    = lattice DGP, snap                 (the CURRENT pipeline)
        C  uniform_snap    = continuous uniform DGP, snap      (isolates the patch)
        D  lattice_raw     = lattice DGP, no snap              (isolates resolution)

    A vs B  = exactly what -17e reported (confounded)
    A vs D  = resolution effect, model held unpatched
    C vs B  = resolution effect, model held patched
    A vs C  = patch effect, data held continuous
    D vs B  = patch effect, data held lattice

(2) The arms are PAIRED, not independently seeded. One latent uniform stream
    (u_person, u_env, u_y) is drawn per seed and shared by all four arms; the arms
    differ only in how those latents are discretised and whether the model snaps.
    Independent draws per arm would let sampling noise in the draws masquerade as an
    arm effect -- the exact failure mode lattice_gap_analysis.py section C documents.
    Pairing removes it, so a 5-seed paired sweep is worth far more than a 5-seed
    unpaired one.

(3) Extra per-run diagnostics are logged to chase the -17e section 3 anomaly
    (posterior SD came out TIGHTER under lattice data at every n, which does not fit
    a "coarser resolution therefore worse everywhere" story). Logged: spread of the
    planted dimension's |gap|, mean p_true, outcome base rate, r_hat, ess_bulk. If
    the SD result is a Fisher-information effect (lattice compresses |gap| toward 0,
    pushing p_true toward 0.5 where logistic information per row is maximal) these
    columns will show it directly instead of leaving it "unexplained".

Output: results/recovery_multiseed.csv (one row per arm x seed x n), plus a printed
summary. Resumable -- completed cells are skipped on re-run.

    python recovery_multiseed.py --seeds 5 --chains 2
"""

import argparse
import csv
import os
import time

os.environ.setdefault("PYTENSOR_FLAGS", "cxx=/usr/bin/g++")

import numpy as np
import pymc as pm
import arviz as az

import build_model as bm

MODEL_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(MODEL_DIR, "results")
OUT_CSV = os.path.join(OUT_DIR, "recovery_multiseed.csv")

FIELDS = [
    "arm", "data_mode", "snap", "seed", "n",
    "post_mean", "post_sd", "abs_err", "r_hat", "ess_bulk",
    "gap_sd", "gap_mean", "p_true_mean", "p_true_sd", "y_rate",
    "n_unique_gap", "secs",
]

ARMS = {
    "A_uniform_raw":  ("uniform", False),
    "B_lattice_snap": ("lattice", True),
    "C_uniform_snap": ("uniform", True),
    "D_lattice_raw":  ("lattice", False),
}


# ---------------------------------------------------------------------------
# Paired latent draws: one stream per seed, shared across all four arms.
# ---------------------------------------------------------------------------
def draw_latents(dims, confs, n_max, seed):
    rng = np.random.default_rng(seed)
    u_person = {d["key"]: rng.random(n_max) for d in dims}
    u_env = {d["key"]: rng.random(n_max) for d in dims}
    conf = bm._synthetic_conf(confs, n_max, rng)
    u_y = rng.random(n_max)
    return u_person, u_env, conf, u_y


def realize(u_person, u_env, data_mode):
    """Map the shared latents into one arm's observable person/env values."""
    if data_mode == "uniform":
        return dict(u_person), dict(u_env)
    if data_mode == "lattice":
        k = len(bm.PERSON_LATTICE)
        person = {
            key: bm.PERSON_LATTICE[np.minimum((u * k).astype(int), k - 1)]
            for key, u in u_person.items()
        }
        env = {key: bm.closest_achievable(u) for key, u in u_env.items()}
        return person, env
    raise ValueError(data_mode)


# ---------------------------------------------------------------------------
# build_model() hardcodes the snap. Rebuild it here with the snap switchable so
# the unpatched pipeline can be reproduced faithfully (DGP and fit must agree).
# ---------------------------------------------------------------------------
def build_model_snapswitch(person, env, conf, cfg, pri, outcome=None, snap=True):
    with pm.Model() as model:
        weights = bm.sample_weights_from_priors(cfg, pri)
        person_data = {}
        for d in bm.active(cfg["dimensions"]):
            v = np.asarray(person[d["key"]], dtype=float)
            if snap:
                v = bm.closest_achievable(v)
            person_data[d["key"]] = pm.Data(f"person_{d['key']}", v)
        env_data = {
            d["key"]: pm.Data(f"env_{d['key']}", np.asarray(env[d["key"]], dtype=float))
            for d in bm.active(cfg["dimensions"])
        }
        conf_data = {
            k: pm.Data(f"conf_{k}", v)
            for k, v in bm.preprocess_conf(conf, cfg).items()
        }
        z = bm.outcome_logit(person_data, env_data, conf_data, cfg, weights,
                             snap_person=False)
        if outcome is not None:
            pm.Bernoulli(cfg["settings"]["outcome"]["name"], logit_p=z,
                         observed=np.asarray(outcome))
    return model


def run_cell(cfg, pri, dims, confs, arm, data_mode, snap, seed, n, n_max,
             latents, planted_dim, planted_val, chains, draws, tune):
    u_person, u_env, conf, u_y = latents
    person_full, env_full = realize(u_person, u_env, data_mode)

    true_weights = {
        "intercept": 0.0,
        "dimensions": {d["key"]: {"mag": -1.0, "dir": 0.0} for d in dims},
        "confounders": {
            c["key"]: (np.zeros(len(c["levels"])) if c.get("kind") == "categorical"
                       else 0.0)
            for c in confs
        },
    }
    true_weights["dimensions"][planted_dim]["mag"] = planted_val

    # DGP uses the SAME snap setting as the fit -- an arm is a coherent pipeline,
    # not a mismatched DGP/model pair.
    z = bm.outcome_logit(person_full, env_full, bm.preprocess_conf(conf, cfg),
                         cfg, true_weights, snap_person=snap)
    p_true_full = 1.0 / (1.0 + np.exp(-z))
    y_full = (u_y < p_true_full).astype(int)   # paired binomial draw

    sub = lambda d: {k: v[:n] for k, v in d.items()}
    person, env, confn = sub(person_full), sub(env_full), sub(conf)
    y, p_true = y_full[:n], p_true_full[:n]

    g = bm.fit_gap(person[planted_dim][:n], env[planted_dim][:n], snap_person=snap)
    absg = np.abs(g)

    t0 = time.time()
    model = build_model_snapswitch(person, env, confn, cfg, pri, outcome=y, snap=snap)
    with model:
        idata = pm.sample(draws=draws, tune=tune, chains=chains, target_accept=0.9,
                          random_seed=seed, progressbar=False,
                          compute_convergence_checks=False)
    secs = time.time() - t0

    target = f"{planted_dim}_mag"
    s = idata.posterior[target].values
    m, sd = float(s.mean()), float(s.std())

    return {
        "arm": arm, "data_mode": data_mode, "snap": int(snap), "seed": seed, "n": n,
        "post_mean": round(m, 5), "post_sd": round(sd, 5),
        "abs_err": round(abs(m - planted_val), 5),
        "r_hat": round(float(az.rhat(idata)[target].values), 4),
        "ess_bulk": round(float(az.ess(idata)[target].values), 1),
        "gap_sd": round(float(absg.std()), 5),
        "gap_mean": round(float(absg.mean()), 5),
        "p_true_mean": round(float(p_true.mean()), 5),
        "p_true_sd": round(float(p_true.std()), 5),
        "y_rate": round(float(y.mean()), 5),
        "n_unique_gap": int(np.unique(np.round(absg, 6)).size),
        "secs": round(secs, 1),
    }


def load_done():
    if not os.path.exists(OUT_CSV):
        return set(), []
    with open(OUT_CSV) as f:
        rows = list(csv.DictReader(f))
    return {(r["arm"], int(r["seed"]), int(r["n"])) for r in rows}, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--ns", type=int, nargs="+", default=[200, 800, 2000, 5000])
    ap.add_argument("--arms", nargs="+", default=list(ARMS))
    ap.add_argument("--chains", type=int, default=2)
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--tune", type=int, default=1000)
    ap.add_argument("--planted-dim", default="pace")
    ap.add_argument("--planted-val", type=float, default=-2.0)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    cfg, pri = bm.load()
    dims = bm.active(cfg["dimensions"])
    confs = [c for c in bm.active(cfg["confounders"]) if c.get("measurable")]
    n_max = max(args.ns)

    done, _ = load_done()
    new_file = not os.path.exists(OUT_CSV)
    f = open(OUT_CSV, "a", newline="")
    w = csv.DictWriter(f, fieldnames=FIELDS)
    if new_file:
        w.writeheader()
        f.flush()

    total = len(args.arms) * args.seeds * len(args.ns)
    i = 0
    t_start = time.time()
    for seed in range(args.seeds):
        latents = draw_latents(dims, confs, n_max, seed)
        for arm in args.arms:
            data_mode, snap = ARMS[arm]
            for n in args.ns:
                i += 1
                if (arm, seed, n) in done:
                    print(f"[{i}/{total}] skip {arm} seed={seed} n={n}", flush=True)
                    continue
                row = run_cell(cfg, pri, dims, confs, arm, data_mode, snap, seed, n,
                               n_max, latents, args.planted_dim, args.planted_val,
                               args.chains, args.draws, args.tune)
                w.writerow(row)
                f.flush()
                el = time.time() - t_start
                print(f"[{i}/{total}] {arm} seed={seed} n={n} "
                      f"mean={row['post_mean']:.3f} sd={row['post_sd']:.3f} "
                      f"|err|={row['abs_err']:.3f} rhat={row['r_hat']:.3f} "
                      f"({row['secs']:.0f}s, elapsed {el/60:.1f}m)", flush=True)
    f.close()
    print("\nDONE ->", OUT_CSV, flush=True)


if __name__ == "__main__":
    main()
