"""Two-panel figure for the multi-seed 2x2 recovery sweep.

Encoding (2x2 factorial, so the factors are encoded separately rather than as
four arbitrary categorical series):
    color      -> data resolution   (blue = continuous uniform, orange = lattice)
    line style -> model             (solid = snap/patched, dashed = no snap/original)
Two categorical hues only; validated all-pairs, light surface:
    CVD dE 24.7, normal-vision dE 33.6, both >= 3:1 contrast. Line style is the
    secondary encoding, so identity is never carried by color alone.
"""
import numpy as np, pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TRUTH = -2.0
SURFACE   = "#fcfcfb"
INK       = "#0b0b0b"
INK_2     = "#52514e"
MUTED     = "#898781"
GRID      = "#e1e0d9"
BASELINE  = "#c3c2b7"
BLUE      = "#2a78d6"   # slot 1 - continuous uniform
ORANGE    = "#eb6834"   # slot 2 - lattice

ARMS = {
    "A_uniform_raw":  ("uniform, no snap (original)",  BLUE,   "--"),
    "C_uniform_snap": ("uniform, snap",                BLUE,   "-"),
    "D_lattice_raw":  ("lattice, no snap",             ORANGE, "--"),
    "B_lattice_snap": ("lattice, snap (current)",      ORANGE, "-"),
}
REPORTED = {200: 0.315, 800: 0.262, 2000: 0.116, 5000: 0.027}  # -17e sec.3 lattice - uniform

d = pd.read_csv("results/recovery_multiseed.csv")
ns = sorted(d.n.unique())
plt.rcParams.update({"font.family": "sans-serif", "font.size": 9,
                     "axes.edgecolor": BASELINE, "text.color": INK})

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.6), facecolor=SURFACE)

# ---- panel 1: recovery curves, mean |err| +/- SE across 5 seeds -------------
for arm, (lab, c, ls) in ARMS.items():
    g = d[d.arm == arm].groupby("n").abs_err
    m, se = g.mean(), g.std(ddof=1) / np.sqrt(g.count())
    ax1.errorbar(ns, m[ns], yerr=se[ns], color=c, ls=ls, lw=2, marker="o",
                 ms=5, capsize=3, elinewidth=1.2, label=lab, zorder=3,
                 markeredgecolor=SURFACE, markeredgewidth=1.2)
ax1.set_xscale("log"); ax1.set_xticks(ns); ax1.set_xticklabels([str(n) for n in ns])
ax1.set_xlabel("training rows (n)", color=INK_2)
ax1.set_ylabel("|posterior mean − planted truth|", color=INK_2)
ax1.set_title("All four arms recover identically\nmean of 5 paired seeds, ±1 SE",
              loc="left", fontsize=11, color=INK)
ax1.legend(frameon=False, fontsize=8.5, labelcolor=INK_2, loc="lower left")

# ---- panel 2: the contrast -17e actually reported --------------------------
w = d.pivot_table(index=["seed", "n"], columns="arm", values="abs_err")
mus, los, his = [], [], []
for n in ns:
    s = w.xs(n, level="n")
    diff = (s["B_lattice_snap"] - s["A_uniform_raw"]).dropna()
    m = diff.mean(); h = stats.t.ppf(.975, len(diff) - 1) * diff.std(ddof=1) / np.sqrt(len(diff))
    mus.append(m); los.append(m - h); his.append(m + h)

ax2.axhline(0, color=BASELINE, lw=1.5, zorder=1)
ax2.fill_between(ns, los, his, color=BLUE, alpha=0.16, zorder=2, lw=0)
ax2.plot(ns, mus, color=BLUE, lw=2, marker="o", ms=6, zorder=4,
         markeredgecolor=SURFACE, markeredgewidth=1.2,
         label="this sweep: observed difference (95% CI)")
ax2.plot(ns, [REPORTED[n] for n in ns], color=ORANGE, lw=0, marker="D", ms=8,
         zorder=5, markeredgecolor=SURFACE, markeredgewidth=1.2,
         label="−17e §3 reported (single seed)")
for i, n in enumerate(ns):
    inside = los[i] <= REPORTED[n] <= his[i]
    ax2.annotate(f"{REPORTED[n]:+.2f}" + ("" if inside else "  outside CI"),
                 (n, REPORTED[n]), textcoords="offset points", xytext=(11, -3),
                 fontsize=8, color=ORANGE if not inside else MUTED)
ax2.set_xscale("log"); ax2.set_xticks(ns); ax2.set_xticklabels([str(n) for n in ns])
ax2.set_xlim(150, 11000)
ax2.set_xlabel("training rows (n)", color=INK_2)
ax2.set_ylabel("|err| difference   (lattice − uniform)", color=INK_2)
ax2.set_title("Three of four reported differences fall outside\nthe CI of the repeated measurement",
              loc="left", fontsize=11, color=INK)
ax2.legend(frameon=False, fontsize=8.5, labelcolor=INK_2, loc="lower left",
           bbox_to_anchor=(0.0, 0.0))
ax2.text(0.02, 0.20, "above 0 = lattice data recovers worse\npooled effect: +0.005  [−0.049, +0.059]",
         transform=ax2.transAxes, fontsize=8.5, color=MUTED, va="bottom")

for ax in (ax1, ax2):
    ax.set_facecolor(SURFACE)
    ax.grid(True, which="major", axis="y", color=GRID, lw=0.8, zorder=0)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

fig.tight_layout()
fig.savefig("results/recovery_multiseed.png", dpi=150, facecolor=SURFACE)
print("saved results/recovery_multiseed.png")
