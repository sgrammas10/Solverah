"""
S-48(b) selection tool — design the remaining ground-truth slots around the 6 already built.

Sebastian, 2026-08-20: only P-01..P-06 are fixed. The rest of the 15-20 is free choice.
That turns S-48(b) from "how bad is our skew" into "what should we deliberately pick",
which is a much better problem.

WHAT THIS ENFORCES (from S48b_CONFOUNDER_SPREAD_2026-08-20.md)
---------------------------------------------------------------
R1. >= 6 companies off the modal `comp` value, and present in BOTH tails
    (1-2 below market AND 4-5 above market). comp is self-centering (3 = at market),
    so one-sided spread leaves the coefficient poorly identified.
R2. >= 6 companies off stage 5, spread across stages 1-4.
R3. The off-mode companies for comp and for stage should NOT be the same companies.
    Concentrating both in one "unusual companies" bucket correlates the two confounders
    (|corr| 0.245 vs 0.136 disjoint) and costs ~25-30% precision on BOTH coefficients.
    Enforced here as a cap on |corr(stage, comp)| across the set.
R4. Keep D-08's criterion: at least one stage 1-2 company. (Currently P-05/Doist alone.)

>>> THE SIX BELOW ARE PLACEHOLDERS AND ALMOST CERTAINLY WRONG IN PLACES. <<<
They are my read of public knowledge, NOT the researcher-recorded values, which live on the
roster in Sebastian's Drive (ground_truth/roster/ on disk is empty). Per the 2026-07-25 rubric
split, confounders are researcher-recorded and never rater-recorded, so the real numbers exist
— they are just not in the repo. Correct FIXED_SIX below and re-run; every number this script
prints depends on it.

Scales, from solverah_model_config.yaml:
  stage_size : 1-5 stage/size index          (config placeholder scale mean 3.0, sd 1.5)
  comp       : 1-5 market-relative pay band  (1 well below ... 3 at market ... 5 well above)
"""

import itertools
import numpy as np

# --- PLACEHOLDER: replace with the roster's researcher-recorded values -------------
# (company, stage_size, comp, note explaining the guess so it is easy to challenge)
FIXED_SIX = [
    ("P-01 Oscar Health",    4, 4, "PLACEHOLDER: health insurtech, post-IPO but not incumbent-scale; tech-competitive pay"),
    ("P-02 Best Buy",        5, 2, "PLACEHOLDER: national retail incumbent; retail-floor pay below market (see S-51)"),
    ("P-03 Akuna Capital",   3, 5, "PLACEHOLDER: prop trading; mid-size but pays far above market"),
    ("P-04 RGA",             5, 3, "PLACEHOLDER: large reinsurer, at-market"),
    ("P-05 Doist",           2, 3, "PLACEHOLDER: ~100-person fully remote; published formula, near market"),
    ("P-06 Raymond James",   5, 3, "PLACEHOLDER: large financial services incumbent, at-market"),
]

COMP_MODE = 3
STAGE_MODE = 5
MIN_OFF_COMP = 6
MIN_OFF_STAGE = 6
MAX_ABS_CORR = 0.20          # keep the two confounders decorrelated (R3)
MIN_PER_COMP_TAIL = 2        # at least this many below-market AND above-market
MIN_STAGE_1_2 = 1            # D-08's criterion


def evaluate(companies):
    """companies: list of (name, stage, comp). Returns a dict of checks."""
    stage = np.array([c[1] for c in companies], float)
    comp = np.array([c[2] for c in companies], float)
    n = len(companies)

    off_comp = int(np.sum(comp != COMP_MODE))
    off_stage = int(np.sum(stage != STAGE_MODE))
    below = int(np.sum(comp <= 2))
    above = int(np.sum(comp >= 4))
    stage_1_2 = int(np.sum(stage <= 2))
    corr = float(abs(np.corrcoef(stage, comp)[0, 1])) if stage.std() > 0 and comp.std() > 0 else float("nan")

    checks = {
        "n": n,
        "off_comp": (off_comp, off_comp >= MIN_OFF_COMP),
        "comp_below_market": (below, below >= MIN_PER_COMP_TAIL),
        "comp_above_market": (above, above >= MIN_PER_COMP_TAIL),
        "off_stage": (off_stage, off_stage >= MIN_OFF_STAGE),
        "stage_1_or_2": (stage_1_2, stage_1_2 >= MIN_STAGE_1_2),
        "abs_corr_stage_comp": (round(corr, 3), (not np.isnan(corr)) and corr <= MAX_ABS_CORR),
        "stage_sd": round(float(stage.std(ddof=1)), 3),
        "comp_sd": round(float(comp.std(ddof=1)), 3),
    }
    checks["ALL_PASS"] = all(v[1] for k, v in checks.items()
                             if isinstance(v, tuple) and len(v) == 2)
    return checks


def report(companies, title):
    print(f"\n=== {title} ({len(companies)} companies) ===")
    print(f"  {'company':<24}{'stage':<7}{'comp'}")
    for row in companies:
        name, s, c = row[0], row[1], row[2]
        flags = []
        if c != COMP_MODE:
            flags.append("comp-off")
        if s != STAGE_MODE:
            flags.append("stage-off")
        print(f"  {name:<24}{s:<7}{c}   {' '.join(flags)}")
    r = evaluate(companies)
    print(f"\n  {'check':<24}{'value':<10}{'ok'}")
    for k, v in r.items():
        if isinstance(v, tuple) and len(v) == 2:
            print(f"  {k:<24}{str(v[0]):<10}{'PASS' if v[1] else 'FAIL'}")
    print(f"  {'stage_sd':<24}{r['stage_sd']}")
    print(f"  {'comp_sd':<24}{r['comp_sd']}")
    print(f"  -> {'ALL CHECKS PASS' if r['ALL_PASS'] else 'GAPS REMAIN (see FAIL rows)'}")
    return r


def gaps(companies):
    """What the remaining slots must supply."""
    r = evaluate(companies)
    need = {}
    if not r["off_comp"][1]:
        need["more companies off comp=3"] = MIN_OFF_COMP - r["off_comp"][0]
    if not r["comp_below_market"][1]:
        need["comp 1-2 (below market)"] = MIN_PER_COMP_TAIL - r["comp_below_market"][0]
    if not r["comp_above_market"][1]:
        need["comp 4-5 (above market)"] = MIN_PER_COMP_TAIL - r["comp_above_market"][0]
    if not r["off_stage"][1]:
        need["more companies off stage=5"] = MIN_OFF_STAGE - r["off_stage"][0]
    if not r["stage_1_or_2"][1]:
        need["stage 1-2 (D-08 criterion)"] = MIN_STAGE_1_2 - r["stage_1_or_2"][0]
    return need


def propose_slots(fixed, n_total, seed=7):
    """Greedy: fill n_total - len(fixed) slots to clear every check, keeping corr low.

    Deliberately simple and inspectable -- it searches (stage, comp) cells, not real
    companies. The output is a SHOPPING LIST of profiles to go find companies for, which is
    the actual bottleneck; picking which real company fills a cell is Sebastian's judgement
    (and interacts with S-51 heterogeneity and with what is researchable).
    """
    rng = np.random.default_rng(seed)
    slots = n_total - len(fixed)
    cells = [(s, c) for s in range(1, 6) for c in range(1, 6)]
    best, best_score = None, None

    for _ in range(4000):
        pick = [cells[i] for i in rng.integers(0, len(cells), size=slots)]
        cand = list(fixed) + [(f"NEW-{i+1}", s, c) for i, (s, c) in enumerate(pick)]
        r = evaluate(cand)
        if not r["ALL_PASS"]:
            continue
        stage = np.array([x[1] for x in cand], float)
        comp = np.array([x[2] for x in cand], float)
        # prefer: low |corr|, high spread on both
        score = (-abs(np.corrcoef(stage, comp)[0, 1]) * 3.0
                 + stage.std(ddof=1) + comp.std(ddof=1))
        if best_score is None or score > best_score:
            best, best_score = cand, score
    return best


if __name__ == "__main__":
    print(__doc__.split("Scales,")[0])
    r6 = report(FIXED_SIX, "THE SIX ALREADY BUILT (placeholder values!)")

    g = gaps(FIXED_SIX)
    print("\n  What the remaining slots must supply:")
    if not g:
        print("    (nothing — but that is only true if the placeholder values are right)")
    for k, v in g.items():
        print(f"    {k}: at least {v} more")

    for n_total in (15, 20):
        best = propose_slots(FIXED_SIX, n_total)
        if best is None:
            print(f"\n=== no passing set found at n={n_total} ===")
            continue
        new = [c for c in best if str(c[0]).startswith("NEW-")]
        print(f"\n=== SHOPPING LIST to reach {n_total} "
              f"({len(new)} new companies) ===")
        counts = {}
        for row in new:
            key = (row[1], row[2])
            counts[key] = counts.get(key, 0) + 1
        print(f"  {'stage':<8}{'comp':<8}{'how many'}")
        for (s, c), k in sorted(counts.items()):
            label = {1: "well below mkt", 2: "below mkt", 3: "at mkt",
                     4: "above mkt", 5: "well above mkt"}[c]
            print(f"  {s:<8}{c:<8}{k}    ({label})")
        report(best, f"RESULTING SET (n={n_total})")
