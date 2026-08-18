"""Structural checks on assessment_items_v2_PROPOSED.yaml.

Checks the things that are checkable without respondent data. Deliberately does NOT
claim to validate the difficulty ordering -- only a pilot can do that.
"""
import sys, itertools, collections
import numpy as np, yaml

PERSON_LATTICE = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]

doc = yaml.safe_load(open("assessment_items_v2_PROPOSED.yaml"))
items = doc["items"]
by_dim = collections.defaultdict(list)
for it in items:
    by_dim[it["dimension"]].append(it)

fails, warns = [], []
def chk(cond, msg):
    (print(f"  PASS  {msg}") if cond else (fails.append(msg), print(f"  FAIL  {msg}")))

print("=== per-dimension structure ===")
for dim in DIMS:
    its = by_dim.get(dim, [])
    print(f"\n[{dim}]  n={len(its)}")
    chk(len(its) == 4, "exactly 4 items (PERSON_LATTICE depends on this)")
    tg = [i["difficulty_target"] for i in its]
    chk(tg == sorted(tg) and len(set(tg)) == 4, f"difficulty targets strictly increasing: {tg}")
    chk(tg == [0.3, 0.5, 0.7, 0.9], "targets are the 0.3/0.5/0.7/0.9 rungs")
    rk = [i.get("reverse_keyed", False) for i in its]
    chk(sum(rk) == 1, "exactly one reverse-keyed item")
    chk(rk[-1] is True, "the reverse-keyed item is the hardest rung")
    a_high = sum(1 for i in its if [o for o in i["options"] if o["key"] == "A"][0]["pole"] == "high")
    chk(a_high == 2, f"key balance 2/2 (A=high on {a_high} of 4)")
    for i in its:
        poles = sorted(o["pole"] for o in i["options"])
        chk(poles == ["high", "low"], f"{i['id']}: exactly one high and one low option")
        keys = sorted(o["key"] for o in i["options"])
        chk(keys == ["A", "B"], f"{i['id']}: options keyed A/B")

print("\n=== global ===")
ids = [i["id"] for i in items]
chk(len(ids) == len(set(ids)), "all item ids unique")
chk(set(by_dim) == set(DIMS), f"exactly the six dimensions present: {sorted(by_dim)}")
gv = doc["grading_variables"]
chk(set(gv) == set(DIMS), "a grading variable declared for every dimension")
chk(len(set(gv.values())) == 6, "all six grading variables distinct (design rule 1)")

# straight-lining signature
print("\n=== response-pattern simulation ===")
def score(dim, chosen):
    v = []
    for i, key in zip(by_dim[dim], chosen):
        v.append(1.0 if [o for o in i["options"] if o["key"] == key][0]["pole"] == "high" else 0.0)
    return float(np.mean(v))

always_a = {d: score(d, "AAAA") for d in DIMS}
always_b = {d: score(d, "BBBB") for d in DIMS}
print(f"  always-A profile: {[always_a[d] for d in DIMS]}")
print(f"  always-B profile: {[always_b[d] for d in DIMS]}")
chk(all(v == 0.5 for v in always_a.values()), "always-A scores 0.50 on every dimension (not an extreme)")
chk(all(v == 0.5 for v in always_b.values()), "always-B scores 0.50 on every dimension (not an extreme)")

print("\n=== Guttman prefix-endorsement lands on PERSON_LATTICE ===")
ok = True
for dim in DIMS:
    got = []
    for k in range(5):  # endorse the first k rungs
        chosen = "".join(
            [o for o in it["options"] if o["pole"] == ("high" if j < k else "low")][0]["key"]
            for j, it in enumerate(by_dim[dim])
        )
        got.append(score(dim, chosen))
    exact = np.allclose(got, PERSON_LATTICE)
    ok &= exact
    print(f"  {dim:<14} {got}  {'OK' if exact else 'MISMATCH'}")
chk(ok, "every dimension's prefix ladder reproduces PERSON_LATTICE exactly")

# text hygiene: words the bias review flagged as valence-carrying
print("\n=== flagged-vocabulary sweep (bias review findings 2 and 3) ===")
BANNED = {
    "quality bar": "pa2 virtue term",
    "unfiltered": "fb3 negative valence on the high pole",
    "trusted you": "fb3 positive valence on the low pole",
    "gut": "de dimension prestige skew",
    "my gut says": "de3 quoted-dialogue format",
    "evidence and analysis": "de2 prestige skew",
    "judgment and experience": "de2 prestige skew",
}
hits = []
for it in items:
    blob = (it["prompt"] + " " + " ".join(o["text"] for o in it["options"])).lower()
    for w, why in BANNED.items():
        if w in blob:
            hits.append(f"{it['id']}: '{w}' ({why})")
for h in hits:
    print(f"  FAIL  {h}")
chk(not hits, "none of the flagged v1 phrases survive into v2")

# option length balance -- a much longer option draws the eye
print("\n=== option length balance ===")
worst = []
for it in items:
    a, b = (len(o["text"]) for o in it["options"])
    r = max(a, b) / min(a, b)
    worst.append((r, it["id"], a, b))
worst.sort(reverse=True)
for r, i, a, b in worst[:5]:
    tag = "WARN" if r > 2.0 else "ok  "
    if r > 2.0:
        warns.append(f"{i}: option length ratio {r:.1f} ({a} vs {b} chars)")
    print(f"  {tag}  {i:<8} ratio {r:.2f}  ({a} vs {b} chars)")

print("\n" + "=" * 60)
print(f"FAILS: {len(fails)}   WARNS: {len(warns)}")
for w in warns:
    print(f"  warn: {w}")
for f in fails:
    print(f"  fail: {f}")
sys.exit(1 if fails else 0)
