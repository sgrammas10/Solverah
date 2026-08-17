"""
lattice_gap_analysis.py -- offline analysis of fit_gap() over the two lattices the real
instruments actually produce. No API calls, no PyMC; numpy/scipy only. Answers `-17c`
open item 6, now merged with round 7's pace<->innovation finding (one problem, not two --
see ANCHOR_BLEED_FIX.md §9).

METHOD NOTE, recorded because the first version of this script got two of four sections
wrong and the errors were invisible in the output:

  * The correlation section applied a correlation to a latent, tanh-squashed it, then
    SNAPPED IT TO THE LATTICE -- which destroyed most of the correlation before it reached
    the design matrix. Standard errors "barely moved" and that read as a null result. It
    was a broken instrument. This version measures the REALIZED correlation of the design
    matrix columns and refuses to report a rho it did not actually induce.
  * It also judged estimator degradation from a single draw per rho, so ordinary sampling
    noise looked like signal (pace estimates bounced -0.95, -1.31, -0.42 with no trend).
    This version runs many seeds per condition and reports the empirical SD of the
    estimate, which is the quantity that actually answers "is the split recoverable".
  * The mag/dir section forced sign imbalance artificially and only reached collinearity
    at literally 100% one-sided. That is degenerate, not a finding. This version reports
    the variance inflation factor of the real 12-column design under plausible imbalance
    and states the honest, smaller conclusion.
"""
from __future__ import annotations

import itertools
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

PERSON_LATTICE = np.array([0.0, 0.25, 0.5, 0.75, 1.0])      # 4-item mean_pole ladder
BANDS = np.array([0.1, 0.3, 0.5, 0.7, 0.9])                  # company rubric bands
N_RUNS = 5                                                   # locked mean-of-5 aggregator
DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
W_MAG_TRUE = -1.0                                            # priors.yaml placeholder mean
IP, IN = DIMS.index("pace"), DIMS.index("innovation")


def company_lattice() -> np.ndarray:
    vals = {round(float(np.mean(c)), 6)
            for c in itertools.combinations_with_replacement(BANDS, N_RUNS)}
    return np.array(sorted(vals))


COMPANY = company_lattice()


def snap(x, lat):
    return lat[np.abs(np.asarray(x)[..., None] - lat).argmin(-1)]


def section(t):
    print("\n" + "=" * 80); print(t); print("=" * 80)


def vif(X):
    """Variance inflation factor per column, via the inverse correlation matrix."""
    C = np.corrcoef(X, rowvar=False)
    return np.diag(np.linalg.pinv(C))


# ===========================================================================
section("A. POLE PENALTY -- fit_gap() cannot return 0 for an extreme person")
# ===========================================================================
print(f"person lattice  : {PERSON_LATTICE}  ({len(PERSON_LATTICE)} values, spacing 0.25)")
print(f"company lattice : {len(COMPANY)} values in [{COMPANY.min():.2f}, {COMPANY.max():.2f}], "
      f"min spacing {np.diff(COMPANY).min():.3f}")
print("\nSmallest |gap| a PERFECTLY matched person can achieve, per person value:")
print(f"{'person':>8}{'nearest company':>18}{'min |gap|':>12}{'logit penalty':>16}")
floors = {}
for p in PERSON_LATTICE:
    e = COMPANY[np.abs(COMPANY - p).argmin()]
    floors[p] = abs(p - e)
    print(f"{p:>8.2f}{e:>18.2f}{floors[p]:>12.3f}{W_MAG_TRUE*floors[p]:>16.3f}")

z_pole = 6 * W_MAG_TRUE * floors[1.0]
z_mid = 6 * W_MAG_TRUE * floors[0.5]
print("\nSix dimensions, perfectly matched candidate, w_mag=-1, intercept=0:")
print(f"  pole candidate (every dim 0.0 or 1.0): sum|gap|={6*floors[1.0]:.2f}  "
      f"logit={z_pole:+.3f}  P(fit)={expit(z_pole):.4f}")
print(f"  mid  candidate (every dim 0.5)       : sum|gap|={6*floors[0.5]:.2f}  "
      f"logit={z_mid:+.3f}  P(fit)={expit(z_mid):.4f}")
print(f"\n  ==> odds ratio {np.exp(z_pole-z_mid):.3f} -- the pole candidate loses "
      f"{(1-np.exp(z_pole-z_mid))*100:.0f}% of its odds for being DECISIVE, not for misfitting.")
print(f"  ==> the artifact is {floors[1.0]/0.25:.0%} of one genuine ladder rung, on all six "
      f"dimensions at once.")
print("  ==> deterministic, present in shipped code, unfixable by more data.")

# ===========================================================================
section("B. mag + dir COLLINEARITY -- real magnitude, not the worst case")
# ===========================================================================
print("outcome_logit adds BOTH w_mag*|g| and w_dir*g per dimension (12 columns for 6 dims).")
print("Measured on the real lattices, sweeping how one-sided the gaps are.\n")
print(f"{'P(person>company)':>19}{'corr(|g|,g)':>14}{'max VIF (12 col)':>19}"
      f"{'cond. number':>15}")
rng = np.random.default_rng(0)
for skew in [0.50, 0.70, 0.85, 0.95, 0.99]:
    n = 20000
    p = rng.choice(PERSON_LATTICE, (n, 6))
    e = snap(rng.random((n, 6)), COMPANY)
    up = rng.random((n, 6)) < skew
    lo, hi = np.minimum(p, e), np.maximum(p, e)
    P = np.where(up, hi, lo); E = np.where(up, lo, hi)
    g = P - E
    X = np.hstack([np.abs(g), g])
    keep = X.std(0) > 1e-12
    v = vif(X[:, keep])
    print(f"{skew:>19.2f}{np.corrcoef(np.abs(g[:,0]), g[:,0])[0,1]:>14.3f}"
          f"{v.max():>19.1f}{np.linalg.cond(np.corrcoef(X[:,keep], rowvar=False)):>15.1f}")
print("\n  ==> HONEST READ, weaker than it first looked: |g| and g only become genuinely")
print("      collinear as sign balance approaches 100% one-sided. At a realistic 70-85%")
print("      imbalance the VIF is elevated but workable. This is a WATCH ITEM, not a defect:")
print("      it will bite specifically on any dimension where applicants sit almost entirely")
print("      on one side of employers, and it will present as a 'wide posterior / need more")
print("      data' symptom rather than as an obvious error.")
print("  ==> Cheap insurance: priors.yaml already sets every dir mean to 0.0 'until the")
print("      expert says otherwise', so not estimating dir yet costs nothing.")

# ===========================================================================
section("C. CORRELATED DIMENSIONS -- is the per-dimension SPLIT recoverable?")
# ===========================================================================


def one_fit(n, rho_env, rho_person, rng):
    """Correlate pace<->innovation on the ENV side, the PERSON side, or both, by copying
    one dimension onto the other with probability rho. Returns the fitted mag weights and
    the REALIZED correlation of the two |gap| design columns.

    THIS IS THE CORRECTED TEST. Two earlier versions correlated only env and both reported
    a realized design-matrix correlation near zero even at rho=1.0. That is not a bug --
    it is the answer. |gap| = |person - env|, so if person is drawn independently across
    dimensions its variance dominates and env correlation does not propagate into the
    design matrix at all. The correlation only reaches fit_gap() if BOTH sides correlate
    on the same pair."""
    e = snap(rng.random((n, 6)), COMPANY)
    p = rng.choice(PERSON_LATTICE, (n, 6))
    ce = rng.random(n) < rho_env
    e[ce, IN] = e[ce, IP]
    cp = rng.random(n) < rho_person
    p[cp, IN] = p[cp, IP]
    X = np.abs(p - e)
    y = rng.binomial(1, expit(W_MAG_TRUE * X.sum(1)))
    nll = lambda w: -np.sum(y * (X @ w) - np.logaddexp(0, X @ w))
    w = minimize(nll, np.full(6, -0.5), method="BFGS").x
    return w, np.corrcoef(X[:, IP], X[:, IN])[0, 1]


print("True w_mag = -1.0 on every dimension. n=3000, 150 simulations per condition.")
print("'realized corr' = correlation of the two |gap| DESIGN COLUMNS -- the only correlation")
print("that can affect the estimator. Round 7 measured correlation on the ENV side only.\n")
print(f"{'env rho':>8}{'person rho':>11}{'realized corr':>15}{'pace SD':>10}{'innov SD':>10}"
      f"{'others SD':>11}{'SUM SD':>9}")
others = [k for k in range(6) if k not in (IP, IN)]
for rho_e, rho_p in [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.6, 0.6), (0.9, 0.9), (1.0, 1.0)]:
    est, corrs = [], []
    for s in range(150):
        w, c = one_fit(3000, rho_e, rho_p, np.random.default_rng(1000 * s + 7))
        est.append(w); corrs.append(c)
    E = np.array(est); tot = E[:, IP] + E[:, IN]
    print(f"{rho_e:>8.1f}{rho_p:>11.1f}{np.mean(corrs):>15.3f}{E[:,IP].std():>10.3f}"
          f"{E[:,IN].std():>10.3f}{E[:,others].std(0).mean():>11.3f}{tot.std():>9.3f}")
print("\n  ==> READ ROW 2 FIRST, it is the one that matters. Correlating the ENV side alone --")
print("      which is exactly and only what round 7 measured -- produces a realized design")
print("      correlation of ~0 and no estimator degradation whatsoever. The person side is")
print("      drawn independently per dimension, and its variance swamps the env correlation.")
print("  ==> The degradation appears only when BOTH sides correlate on the same pair. Then")
print("      the per-dimension SDs inflate while the SD on their SUM stays flat: the joint")
print("      effect on fit stays recoverable, the attribution between the two does not.")
print("  ==> CONSEQUENCE, and it downgrades what I claimed after round 7: round 7 is NOT")
print("      sufficient to establish a fit_gap() problem. It measured env-side correlation")
print("      only. Whether real respondents' pace and innovation answers correlate is an")
print("      empirical question about people, and no Solverah data exists on it yet. This")
print("      is now a question the pilot must answer, not a defect to fix.")
print("  ==> Ignore the rho=1.0/1.0 row's small SDs. At exact identity the two design")
print("      columns are the same vector, the Hessian is singular, and BFGS lands on an")
print("      arbitrary even split -- a low SD there reflects a degenerate optimum, not")
print("      good recovery. The 0.9/0.9 row is the informative one.")

# ===========================================================================
section("D. THE MODEL HAS ONLY BEEN VALIDATED ON DATA THE INSTRUMENTS CANNOT PRODUCE")
# ===========================================================================
print("build_model.py sanity_check() and recovery_curve() draw person and env from")
print("rng.uniform(0,1). The real pipeline emits the two lattices above.\n")
print(f"{'':<24}{'mean |gap|':>12}{'sd':>8}{'P(gap=0)':>11}{'distinct |gap| values':>23}")
rng = np.random.default_rng(3)
for label, lat in [("uniform (as validated)", False), ("real lattices", True)]:
    if lat:
        p = rng.choice(PERSON_LATTICE, 200000); e = snap(rng.random(200000), COMPANY)
    else:
        p = rng.random(200000); e = rng.random(200000)
    g = np.abs(p - e)
    print(f"{label:<24}{g.mean():>12.3f}{g.std():>8.3f}{np.mean(g<1e-9):>11.3f}"
          f"{len(np.unique(np.round(g,6))):>23}")
print("\n  ==> The means and SDs match closely, which is why this was easy to miss. The")
print("      RESOLUTION does not: ~200k distinct |gap| values under uniforms vs 53 under the")
print("      real lattices. Recovery curves measured on continuous uniforms assume gap")
print("      resolution the instruments do not have, so every n-needed figure quoted so far")
print("      is optimistic by an unmeasured amount.")

# ===========================================================================
section("SUMMARY")
# ===========================================================================
print(f"""
Ranked by how much each changes a decision, not by how interesting it is.

1. POLE PENALTY -- real, deterministic, in shipped code. A perfectly matched candidate at
   either extreme carries |gap|={floors[1.0]:.2f} on every dimension and loses
   {(1-np.exp(z_pole-z_mid))*100:.0f}% of its odds against an identically well-matched mid
   candidate. In a fit product that means decisive candidates are systematically rated
   worse fits than bland ones, for no reason but the rubric having no band outside
   [0.1, 0.9]. FIX: gap against the closest ACHIEVABLE band. run_vignette_probe.py's
   closest_company_band() already does exactly this for the probe verdict -- the precedent
   and the reasoning are already in the repo, they just never reached build_model.py.

2. VALIDATION DISTRIBUTION MISMATCH -- real, cheap to fix, invalidates a published number.
   53 distinct |gap| values in reality vs ~200k in the validation harness. FIX: make
   sanity_check() and recovery_curve() draw from the lattices, then re-run recovery_curve
   before quoting a sample size to anyone.

3. CORRELATION -- DOWNGRADED, and this corrects what I claimed after round 7. Round 7
   measured correlation on the ENV (company scorer) side only. Env-side correlation does
   NOT propagate into fit_gap()'s design matrix: |gap| = |person - env|, and with person
   drawn independently per dimension its variance swamps the env correlation -- realized
   design correlation was 0.04 even at env rho = 1.0, with zero estimator degradation.
   Degradation requires BOTH sides to correlate on the same pair (at 0.9/0.9 the
   per-dimension SD nearly doubles while the SD on the SUM does not move at all: the joint
   fit effect stays recoverable, the per-dimension attribution does not -- and Solverah's
   per-dimension explanations to users are claims about the attribution).
   SO: round 7 is NOT sufficient to establish a fit_gap() problem. Whether real
   respondents' pace and innovation answers correlate is an empirical question about
   people and no Solverah data exists on it. This is a QUESTION FOR THE PILOT, not a
   defect to fix now -- and the pilot should be instrumented to answer it, which costs
   nothing if decided before fielding and is expensive afterwards.

4. mag/dir COLLINEARITY -- a watch item, not a defect. Only severe as sign balance
   approaches fully one-sided. Costs nothing to defer: priors.yaml already pins every dir
   mean at 0.0.

DELIBERATELY NOT ANSWERED: the right number of ladder rungs. It depends on finding 1 being
fixed first -- re-centering the gap changes what resolution buys you. That is the argument
for doing this analysis BEFORE extending the ladder to the other five dimensions, and it
held up: findings 1 and 2 are real and both would have forced a re-pilot if five more
ladders had been built first.

METHOD NOTE ON THIS SCRIPT ITSELF. Section C was wrong twice before it was right, and both
times the wrong version returned a clean-looking null. The first version destroyed the
correlation by snapping to the lattice after inducing it; the second induced it correctly on
env alone and reported ~0 realized correlation, which I nearly wrote up as "correlation
doesn't matter." It does matter -- just not for the reason round 7 suggested, and only under
a condition nobody has measured. The check that caught it both times was printing the
REALIZED quantity next to the nominal one, which is the same discipline that caught the
detector bug in ANCHOR_BLEED_FIX.md §1: never report an effect without reporting the
measurement of the thing you think is causing it.
""")
