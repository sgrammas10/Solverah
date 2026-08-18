#!/usr/bin/env python3
"""
check_assessment_items.py -- structural gate for any Solverah person-side item file.

This is a GATE, not a report. It exits non-zero on failure and is wired into pytest via
test_assessment_items.py, so a person-side item file cannot reach a pilot without passing.

Supersedes the one-off check_items_v2.py, which hardcoded a single filename. Rationale is
the same argument SOLVERAH_HANDOFF_2026-08-18.md sec.7 makes about seeds: a check that has to
be remembered is not a check. Both of the defects this catches (positional key imbalance,
difficulty-order transparency) were missed by a careful human read of the item TEXT, because
they live in the file's STRUCTURE. Content review and structural check are complements;
neither substitutes for the other, and only one of them can be automated.

What it CANNOT do: validate that real respondents' answers follow the difficulty ordering.
Only a pilot does that. Passing this gate means the file is not structurally broken -- it
does not mean the instrument works.

Usage:
    python check_assessment_items.py                          # all active/proposed item files
    python check_assessment_items.py assessment_items_v2_PROPOSED.yaml
    python check_assessment_items.py --allow-superseded assessment_items.yaml
"""
from __future__ import annotations

import argparse
import collections
import glob
import sys
from pathlib import Path

import numpy as np
import yaml

PERSON_LATTICE = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
RUNGS = [0.3, 0.5, 0.7, 0.9]

# Phrases the bias review (ASSESSMENT_ITEMS_BIAS_REVIEW.md findings 2 and 3) identified as
# carrying valence or prestige independent of the trait being measured.
BANNED = {
    "quality bar": "pa2 virtue term (finding 3)",
    "unfiltered": "fb3 negative valence on the high pole (finding 3)",
    "trusted you": "fb3 positive valence on the low pole (finding 3)",
    "gut": "decision-dimension prestige skew (finding 2)",
    "evidence and analysis": "de2 prestige skew (finding 2)",
    "judgment and experience": "de2 prestige skew (finding 2)",
}


class Report:
    def __init__(self, path):
        self.path, self.fails, self.warns = path, [], []

    def chk(self, cond, msg, warn_only=False):
        if cond:
            print(f"  PASS  {msg}")
        elif warn_only:
            self.warns.append(msg)
            print(f"  WARN  {msg}")
        else:
            self.fails.append(msg)
            print(f"  FAIL  {msg}")


def opt(item, key):
    return next(o for o in item["options"] if o["key"] == key)


def score(items, chosen):
    vals = [1.0 if opt(i, k)["pole"] == "high" else 0.0 for i, k in zip(items, chosen)]
    return float(np.mean(vals))


def check_file(path: Path, allow_superseded: bool) -> Report:
    r = Report(path)
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    print(f"\n{'=' * 70}\n{path}   form_version={doc.get('form_version')!r} "
          f"status={doc.get('status')!r}\n{'=' * 70}")

    status = doc.get("status")
    if status == "superseded" and not allow_superseded:
        r.chk(False, "file is marked status: superseded -- must not be used for scoring "
                     "(pass --allow-superseded only to reproduce a historical run)")
        return r

    items = doc["items"]
    by_dim = collections.defaultdict(list)
    for it in items:
        by_dim[it["dimension"]].append(it)

    # ---- presentation contract (design rule 3) ----------------------------
    print("\n-- presentation contract --")
    p = doc.get("presentation")
    r.chk(isinstance(p, dict), "a presentation block is declared")
    if isinstance(p, dict):
        r.chk(p.get("randomize_item_order_within_dimension") is True,
              "item order is randomized within each dimension (else the ladder is "
              "transparent and consistency-based confidence is gameable)")
        r.chk(bool(p.get("order_seed")),
              "an order_seed is declared (a resumed session must not reshuffle)")
        nd = set(p.get("never_display") or [])
        for f in ("id", "difficulty_target", "pole"):
            r.chk(f in nd, f"'{f}' is in never_display "
                           + ("(sequential ids re-leak the rung order)" if f == "id" else ""))
        if p.get("randomize_option_order") is True:
            r.chk(False, "randomize_option_order is true -- then responses must be stored "
                         "as the chosen POLE, not the letter, and every probe file's "
                         "person_item_choices is invalid. Confirm this is intended.",
                  warn_only=True)

    # ---- per-dimension structure ------------------------------------------
    for dim in DIMS:
        its = by_dim.get(dim, [])
        print(f"\n-- {dim} (n={len(its)}) --")
        r.chk(len(its) == 4,
              "exactly 4 items -- LOAD-BEARING: mean_pole over 4 reproduces "
              "build_model.py's PERSON_LATTICE")
        if len(its) != 4:
            continue
        tg = [i.get("difficulty_target") for i in its]
        r.chk(all(t is not None for t in tg),
              "every item carries difficulty_target (true rung order must survive the shuffle)")
        r.chk(tg == sorted(tg) and len(set(tg)) == 4, f"difficulty targets strictly increasing: {tg}")
        r.chk(tg == RUNGS, f"targets are the {RUNGS} rungs")
        rk = [bool(i.get("reverse_keyed")) for i in its]
        r.chk(sum(rk) == 1, "exactly one reverse-keyed item")
        r.chk(rk[-1], "the reverse-keyed item is the hardest rung")
        a_high = sum(1 for i in its if opt(i, "A")["pole"] == "high")
        r.chk(a_high == 2, f"key balance 2/2 (A=high on {a_high} of 4) -- an imbalanced "
                           f"dimension lets a positional straight-liner score an extreme "
                           f"with perfect internal consistency")
        for i in its:
            r.chk(sorted(o["pole"] for o in i["options"]) == ["high", "low"],
                  f"{i['id']}: exactly one high and one low option")
            r.chk(sorted(o["key"] for o in i["options"]) == ["A", "B"],
                  f"{i['id']}: options keyed A/B")

    # ---- global ------------------------------------------------------------
    print("\n-- global --")
    ids = [i["id"] for i in items]
    r.chk(len(ids) == len(set(ids)), "all item ids unique")
    r.chk(set(by_dim) == set(DIMS), f"exactly the six dimensions present: {sorted(by_dim)}")
    gv = doc.get("grading_variables", {})
    r.chk(set(gv) == set(DIMS), "a grading variable declared for every dimension")
    r.chk(len(set(gv.values())) == len(DIMS),
          "all grading variables distinct -- a shared one manufactures person-side "
          "cross-dimension correlation out of the instrument's construction")

    # ---- response-pattern simulation --------------------------------------
    print("\n-- response-pattern simulation --")
    if all(len(by_dim.get(d, [])) == 4 for d in DIMS):
        a = [score(by_dim[d], "AAAA") for d in DIMS]
        b = [score(by_dim[d], "BBBB") for d in DIMS]
        print(f"  always-A profile: {a}\n  always-B profile: {b}")
        r.chk(all(v == 0.5 for v in a), "always-A scores 0.50 everywhere (midpoint, not an extreme)")
        r.chk(all(v == 0.5 for v in b), "always-B scores 0.50 everywhere (midpoint, not an extreme)")

        print("\n-- Guttman prefix-endorsement reproduces PERSON_LATTICE --")
        ok = True
        for dim in DIMS:
            got = []
            for k in range(5):
                chosen = "".join(
                    next(o for o in it["options"] if o["pole"] == ("high" if j < k else "low"))["key"]
                    for j, it in enumerate(by_dim[dim])
                )
                got.append(score(by_dim[dim], chosen))
            good = np.allclose(got, PERSON_LATTICE)
            ok &= good
            print(f"     {dim:<14} {got}  {'OK' if good else 'MISMATCH'}")
        r.chk(ok, "every dimension's prefix ladder reproduces PERSON_LATTICE exactly")

    # ---- text hygiene ------------------------------------------------------
    print("\n-- flagged-vocabulary sweep --")
    hits = []
    for it in items:
        blob = (it["prompt"] + " " + " ".join(o["text"] for o in it["options"])).lower()
        for w, why in BANNED.items():
            if w in blob:
                hits.append(f"{it['id']}: '{w}' ({why})")
    for h in hits:
        print(f"  FAIL  {h}")
    r.chk(not hits, "none of the phrases the bias review flagged survive")

    # ---- option length balance --------------------------------------------
    print("\n-- option length balance (a much longer option draws the eye) --")
    rows = sorted(((max(len(o["text"]) for o in i["options"])
                    / min(len(o["text"]) for o in i["options"]), i["id"]) for i in items),
                  reverse=True)
    for ratio, iid in rows[:3]:
        print(f"     {iid:<8} ratio {ratio:.2f}")
    r.chk(rows[0][0] <= 2.0, f"worst option length ratio {rows[0][0]:.2f} <= 2.0 "
                             f"({rows[0][1]})", warn_only=True)
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="item YAMLs; default = every assessment_items*.yaml here")
    ap.add_argument("--allow-superseded", action="store_true",
                    help="permit files marked status: superseded (historical reproduction only)")
    a = ap.parse_args()

    here = Path(__file__).resolve().parent
    paths = [Path(p) for p in a.paths] or sorted(
        Path(p) for p in glob.glob(str(here / "assessment_items*.yaml"))
    )
    if not paths:
        print("no item files found"); return 1

    reports = [check_file(p, a.allow_superseded) for p in paths]
    print(f"\n{'=' * 70}\nSUMMARY")
    bad = 0
    for r in reports:
        bad += bool(r.fails)
        print(f"  {r.path.name:<40} {len(r.fails)} fail  {len(r.warns)} warn")
        for m in r.fails:
            print(f"      fail: {m}")
        for m in r.warns:
            print(f"      warn: {m}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
