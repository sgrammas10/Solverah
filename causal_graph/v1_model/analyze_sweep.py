import numpy as np, pandas as pd
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
print(f"{'contrast':<34} {'n':>6} {'mean d':>8} {'sd':>7} {'t':>7} {'signs':>7}")
for a,b,lab in CONTRASTS:
    print(f"-- {lab}")
    for n in sorted(d.n.unique()):
        s = w.xs(n, level="n")
        diff = (s[a] - s[b]).dropna()
        t = diff.mean()/(diff.std(ddof=1)/np.sqrt(len(diff))) if diff.std(ddof=1)>0 else np.nan
        pos = int((diff>0).sum())
        print(f"{a+' vs '+b:<34} {n:>6} {diff.mean():>8.3f} {diff.std(ddof=1):>7.3f} {t:>7.2f} {pos:>4}/{len(diff)}")
    # pooled across n
    dd = (w[a]-w[b]).dropna()
    t = dd.mean()/(dd.std(ddof=1)/np.sqrt(len(dd)))
    print(f"{'  POOLED all n':<34} {'':>6} {dd.mean():>8.3f} {dd.std(ddof=1):>7.3f} {t:>7.2f} {int((dd>0).sum()):>4}/{len(dd)}\n")

# ---- rows-multiplier question ----
print("=== rows-multiplier check: mean |err| by n, is there ANY n at which lattice matches uniform? ===")
m = piv("abs_err")
print(m.round(3).to_string())
print("\nper-seed |err| at n=5000 (shows seed-to-seed spread vs. the arm effect):")
print(d[d.n==5000].pivot_table(index="seed",columns="arm",values="abs_err").round(3))
