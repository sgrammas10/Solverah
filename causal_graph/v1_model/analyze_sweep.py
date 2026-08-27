import numpy as np, pandas as pd

# The seeds rule (D-21, S-04) applied where the numbers are born. Every contrast below is
# emitted as a Finding, so one that has not earned quoting prints its label and NOT its
# number -- which is what a session copying from this console output would paste.
from seed_discipline import Finding

pd.set_option("display.width", 200)
TRUTH = -2.0
d = pd.read_csv("results/recovery_multiseed.csv")
d["signed_err"] = d.post_mean - TRUTH

def piv(col, agg="mean"):
    return d.pivot_table(index="n", columns="arm", values=col, aggfunc=agg)

print("=== |err| : MEAN across 5 seeds ===");  print(piv("abs_err").round(3))
print("\n=== |err| : SD across 5 seeds ==="); print(piv("abs_err","std").round(3))
print("\n=== signed err (post_mean - truth), mean ==="); print(piv("signed_err").round(3))
print("\n=== RMSE across seeds ===")
print(d.groupby(["n","arm"]).signed_err.apply(lambda s: np.sqrt((s**2).mean())).unstack().round(3))
print("\n=== posterior SD, mean ==="); print(piv("post_sd").round(3))
print("\n=== diagnostics (mean over seeds+n) ===")
print(d.groupby("arm")[["gap_mean","gap_sd","p_true_mean","p_true_sd","y_rate","n_unique_gap","ess_bulk","r_hat"]].mean().round(3))
print("\n=== gap_sd / p_true_sd by arm x n ===")
print(d.pivot_table(index="n",columns="arm",values=["gap_sd","p_true_sd"]).round(3))

# ---- paired contrasts: per (seed,n) differences ----
w = d.pivot_table(index=["seed","n"], columns="arm", values="abs_err")
CONTRASTS = [
    ("A_uniform_raw","B_lattice_snap","-17e reported (CONFOUNDED: resolution+patch)"),
    ("A_uniform_raw","D_lattice_raw", "resolution effect, model UNPATCHED"),
    ("C_uniform_snap","B_lattice_snap","resolution effect, model PATCHED"),
    ("A_uniform_raw","C_uniform_snap","patch effect, data CONTINUOUS"),
    ("D_lattice_raw","B_lattice_snap","patch effect, data LATTICE"),
]
print("\n=== PAIRED contrasts on |err|  (positive = second arm is BETTER/closer to truth) ===")
print("Emitted through seed_discipline.Finding: a contrast that does not clear D-21 prints")
print("its label and no number. Per-n rows carry one draw per seed; the pooled row averages")
print("each seed's difference ACROSS n first, because the same seed appearing at four n's is")
print("four correlated observations, not four independent draws.\n")
for a, b, lab in CONTRASTS:
    print(f"-- {lab}")
    for n in sorted(d.n.unique()):
        s = w.xs(n, level="n")
        joined = pd.concat([s[a], s[b]], axis=1).dropna()   # align draw-for-draw on seed
        print("   ", Finding.paired_contrast(
            f"{a} vs {b} @ n={n}", joined[a], joined[b], draw_kind="seed"))
    # Pooled across n: collapse to ONE value per seed per arm first, so n_draws counts
    # independent seeds. (The earlier version differenced all 20 (seed, n) cells and treated
    # them as 20 independent draws, which overstates precision by reusing each seed 4x.)
    sa = w[a].groupby(level="seed").mean()
    sb = w[b].groupby(level="seed").mean()
    joined = pd.concat([sa, sb], axis=1).dropna()
    print("   ", Finding.paired_contrast(
        f"{a} vs {b} POOLED over n", joined[a], joined[b], draw_kind="seed"))
    print()

# ---- rows-multiplier question ----
print("=== rows-multiplier check: mean |err| by n, is there ANY n at which lattice matches uniform? ===")
m = piv("abs_err")
print(m.round(3).to_string())
print("\nper-seed |err| at n=5000 (shows seed-to-seed spread vs. the arm effect):")
print(d[d.n==5000].pivot_table(index="seed",columns="arm",values="abs_err").round(3))
