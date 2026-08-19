"""Power simulation for the S-18 feedback two-factor test and the S-17 correlation test.

Generative model, deliberately simple and stated so it can be argued with:
  - each respondent has a true rung position k in {0..4} per dimension
  - true pattern = Guttman prefix with k ones (rung order)
  - each of the 4 items flips independently with probability eps (response noise)
  - under H1 for feedback, a fraction phi of respondents are "rule-6 people": they endorse
    rungs 1-2 (delay) and decline rung 3 (audience), then resolve fb4 toward the withholder
    -> deterministic {1,1,0,0}.  (The mirror resolution gives {1,1,0,1}, score 0.75, which the
    PRIMARY test does not see -- that is why it is a secondary cell.)
"""
import numpy as np

DIMS = 6
FEEDBACK = 0  # index of the feedback dimension

# Rung-position distribution: mode in the middle, not uniform. A ladder where nobody sits at
# the extremes would make score=0.5 the only stratum; this is a moderate, defensible shape.
RUNG_P = np.array([0.10, 0.22, 0.36, 0.22, 0.10])


def simulate(n, eps=0.10, phi=0.0, rng=None):
    """Return observed 4-bit patterns, shape (n, DIMS, 4), in rung order."""
    rng = rng or np.random.default_rng(0)
    k = rng.choice(5, size=(n, DIMS), p=RUNG_P)
    idx = np.arange(4)[None, None, :]
    pat = (idx < k[:, :, None]).astype(int)          # Guttman prefix
    flips = rng.random((n, DIMS, 4)) < eps
    pat = np.abs(pat - flips.astype(int))
    if phi > 0:                                       # inject rule-6 people into feedback
        is_r6 = rng.random(n) < phi
        pat[is_r6, FEEDBACK, :] = np.array([1, 1, 0, 0])
    return pat


def share_1100_at_half(pat, dim):
    """P(pattern == {1,1,0,0} | score == 0.5) for one dimension. None if the stratum is empty."""
    p = pat[:, dim, :]
    at_half = p.sum(axis=1) == 2
    if at_half.sum() == 0:
        return None, 0
    sel = p[at_half]
    hits = np.all(sel == np.array([1, 1, 0, 0]), axis=1).sum()
    return hits / at_half.sum(), at_half.sum()


def statistic(pat):
    """delta = share_feedback - share_pooled_others, both within their 0.5 strata."""
    sf, nf = share_1100_at_half(pat, FEEDBACK)
    others = [d for d in range(DIMS) if d != FEEDBACK]
    p = pat[:, others, :]
    at_half = p.sum(axis=2) == 2
    if at_half.sum() == 0 or sf is None:
        return None, None, nf
    hits = np.all(p[at_half] == np.array([1, 1, 0, 0]), axis=1).sum()
    so = hits / at_half.sum()
    return sf - so, so, nf


def bootstrap_ci(pat, n_boot=2000, rng=None, alpha=0.05):
    """Resample RESPONDENTS (not rows) -- respondents appear in all six dimensions, so the
    cluster is the person. This is also exactly D-21's draw_kind='bootstrap'."""
    rng = rng or np.random.default_rng(1)
    n = pat.shape[0]
    deltas = np.empty(n_boot)
    for b in range(n_boot):
        take = rng.integers(0, n, n)
        d, _, _ = statistic(pat[take])
        deltas[b] = np.nan if d is None else d
    deltas = deltas[~np.isnan(deltas)]
    lo, hi = np.quantile(deltas, [alpha / 2, 1 - alpha / 2])
    return lo, hi, deltas.std(ddof=1)


def power_at(n, phi, trials=300, n_boot=600, eps=0.10, seed=0):
    """Fraction of trials whose 95% bootstrap CI excludes 0 in the predicted direction."""
    rng = np.random.default_rng(seed)
    wins = 0
    for t in range(trials):
        pat = simulate(n, eps=eps, phi=phi, rng=rng)
        lo, hi, _ = bootstrap_ci(pat, n_boot=n_boot, rng=rng)
        if lo > 0:
            wins += 1
    return wins / trials


if __name__ == "__main__":
    rng = np.random.default_rng(7)
    base = simulate(200000, phi=0.0, rng=rng)
    d0, so, nf = statistic(base)
    print(f"H0 baseline: P({{1,1,0,0}} | score=0.5) = {so:.3f}; delta at H0 = {d0:+.4f}")
    print(f"  fraction of respondents at score 0.5 on a given dimension "
          f"= {nf/200000:.3f}\n")

    print("Effect size delta produced by each rule-6 prevalence phi (large-sample):")
    for phi in (0.05, 0.10, 0.15, 0.20, 0.30):
        p = simulate(200000, phi=phi, rng=rng)
        d, _, _ = statistic(p)
        print(f"  phi={phi:.2f} -> delta={d:+.3f}")


# ---------------------------------------------------------------------------
# Alternative statistic: the conditional CLIMB at the variable-change rung.
# ---------------------------------------------------------------------------
# In feedback, and only in feedback, the step from rung 2 to rung 3 crosses a change of
# grading variable (delay -> audience). Under a homogeneous ladder the conditional
# probability of climbing one more rung should be comparable across dimensions. Under
# two-factor structure the audience-averse stop at rung 2 no matter how far up the DELAY
# ladder they went, so feedback's climb probability should be anomalously low.
#
# It uses everyone who endorsed rungs 1 and 2, not only the score=0.5 stratum, and it is
# not pinned near a ceiling.

def climb_q(pat, dim):
    p = pat[:, dim, :]
    base = (p[:, 0] == 1) & (p[:, 1] == 1)
    if base.sum() == 0:
        return None, 0
    return p[base, 2].mean(), base.sum()


def statistic_climb(pat):
    """delta_climb = q_pooled_others - q_feedback  (positive = feedback climbs LESS)."""
    qf, nf = climb_q(pat, FEEDBACK)
    others = [d for d in range(DIMS) if d != FEEDBACK]
    p = pat[:, others, :]
    base = (p[:, :, 0] == 1) & (p[:, :, 1] == 1)
    if base.sum() == 0 or qf is None:
        return None, None, nf
    qo = p[:, :, 2][base].mean()
    return qo - qf, qo, nf


def bootstrap_ci_generic(pat, stat_fn, n_boot=2000, rng=None, alpha=0.05):
    rng = rng or np.random.default_rng(1)
    n = pat.shape[0]
    vals = np.empty(n_boot)
    for b in range(n_boot):
        take = rng.integers(0, n, n)
        d, _, _ = stat_fn(pat[take])
        vals[b] = np.nan if d is None else d
    vals = vals[~np.isnan(vals)]
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return lo, hi, vals.std(ddof=1)


def power_generic(n, phi, stat_fn, trials=200, n_boot=400, eps=0.10, seed=0):
    rng = np.random.default_rng(seed)
    wins = 0
    for _ in range(trials):
        pat = simulate(n, eps=eps, phi=phi, rng=rng)
        lo, hi, _ = bootstrap_ci_generic(pat, stat_fn, n_boot=n_boot, rng=rng)
        if lo > 0:
            wins += 1
    return wins / trials
