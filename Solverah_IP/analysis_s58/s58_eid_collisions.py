r"""
Cross-dimension citation collisions measured by EXCERPT ID, not by text. ZERO API CALLS.

WHY. Arm B's primary outcome came back v1 = 0 and was read as "the extractor never cites the
same passage under two dimensions." That may be a metric artifact: raters SELECT from a fixed
excerpt inventory, while the model GENERATES spans, so two model quotes drawn from the same
excerpt but with different spans would not match under exact-text comparison. Every excerpt has
an `eid`, the rater JSONs record it, and sp.verify_quote() re-derives it for model quotes with no
API call. Measuring by eid puts humans and the model in the same units for the first time.

If eid collisions are also ~0 for the model, "the collision defect is human-specific" stands and
belongs in STATE. If they are not, Arm B's primary outcome is measurable after all.

STRUCTURAL ASYMMETRY, recorded before the numbers: the model scores all six dimensions in ONE
call and can see its own other dimensions; the raters committed dimensions sequentially. A model
zero could be an artifact of that, not evidence of cleaner construct separation. This script
cannot separate those and does not claim to.

Read-only on the Solverah repo. Run from Solverah_IP/analysis_s58 with the venv python.
"""
import json, glob, os, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
IP   = HERE.parent
DIMS = ["autonomy","pace","collaboration","feedback","innovation","decision"]
PKTS = ["P-0%d" % i for i in range(1,7)]

import argparse
ap = argparse.ArgumentParser()
ap.add_argument("--repo-causal-graph", default=str(IP.parent / "Solverah" / "causal_graph"))
ap.add_argument("--evidence-v1", default="")
ap.add_argument("--evidence-v3", default=str(HERE / "results" / "all_dims_evidence_v3_2026-09-01b.json"))
ap.add_argument("--returned", default=str(IP / "ground_truth" / "rater_app" / "returned" / "round1"))
a = ap.parse_args()
sys.path.insert(0, str(Path(a.repo_causal_graph).resolve()))
# scorer_pipeline resolves packets relative to its own location; pin it explicitly so this
# works regardless of layout. READ-ONLY -- nothing is written under this path.
os.environ.setdefault("SOLVERAH_IP_DIR", str(IP))
import scorer_pipeline as sp
print("packets read from:", sp.REPO_IP / "ground_truth" / "anonymization")

def find_v1():
    if a.evidence_v1: return Path(a.evidence_v1)
    for c in [HERE/"all_dims_evidence_2026-09-01.json", HERE/"results"/"all_dims_evidence_2026-09-01.json"]:
        if c.exists(): return c
    h = list(IP.parent.glob("**/all_dims_evidence_2026-09-01.json"))
    return h[0] if h else None

# ---- excerpts per packet, once -------------------------------------------
EX = {}
for pk in PKTS:
    txt = sp.load_packet_section1(sp.packet_path_for(pk))
    EX[pk] = sp.parse_excerpts(txt)
print("excerpts parsed per packet:", {pk: len(EX[pk]) for pk in PKTS})

def eids_from_quotes(pk, quotes):
    """quotes: list of dicts with 'quote' (model) -- re-derive eid offline."""
    out = []
    for q in quotes:
        t = q["quote"] if isinstance(q, dict) else q
        matched, eid, _ = sp.verify_quote(t, EX[pk])
        out.append(eid if matched else None)
    return out

# ---- build {label: {packet: {dim: set(eid)}}} -----------------------------
sets = {}

# humans: eid is recorded directly in the rater JSONs
for f in sorted(glob.glob(os.path.join(a.returned, "*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    lab = f"rater {d['rater']}"
    sets.setdefault(lab, {}).setdefault(d["packet_id"], {})
    for row in d["scores"]:
        sets[lab][d["packet_id"]][row["dimension"]] = {
            q.get("eid") for q in (row.get("quotes") or []) if q.get("eid")}

# model v1 (eid already in the file) and v3 (re-derived)
V1P = find_v1()
if V1P:
    raw = json.loads(Path(V1P).read_text(encoding="utf-8"))
    sets["LLM v1"] = {pk: {r["dimension"]: {q.get("eid") for q in r.get("quotes",[]) if q.get("eid")}
                           for r in rows} for pk, rows in raw.items()}
if not Path(a.evidence_v3).exists():
    print(f"\n!! v3 evidence not found at {a.evidence_v3} -- skipping the LLM v3 arm.")
    raw3 = {}
else:
    raw3 = json.loads(Path(a.evidence_v3).read_text(encoding="utf-8"))
sets["LLM v3"] = {} if not raw3 else {pk: {r["dimension"]: {e for e in eids_from_quotes(pk, r["quotes"]) if e}
                       for r in rows} for pk, rows in raw3.items()}

# how many model quotes failed to resolve to an eid at all?
unres = sum(1 for pk, rows in raw3.items() for r in rows
            for e in eids_from_quotes(pk, r["quotes"]) if e is None)
tot3  = sum(len(r["quotes"]) for rows in raw3.values() for r in rows)
print(f"v3 quotes that resolve to an eid: {tot3-unres}/{tot3}"
      f"{'   <-- unresolved quotes cannot collide; treat the v3 number as a FLOOR' if unres else ''}")

# ---- collisions by eid ----------------------------------------------------
def score(label):
    tot=0; distinct=0; pair=defaultdict(int)
    for pk, dd in sets[label].items():
        by=defaultdict(set)
        for d, es in dd.items():
            for e in es: by[e].add(d)
        distinct += len(by)
        for e, ds in by.items():
            if len(ds)>1:
                tot+=1; ds=sorted(ds)
                for i in range(len(ds)):
                    for j in range(i+1,len(ds)): pair[(ds[i],ds[j])]+=1
    return tot, distinct, pair

hum = set(); mod = set()
for lab in ("rater A","rater B","rater C"):
    for pk, dd in sets.get(lab, {}).items():
        for d, es in dd.items(): hum |= {(pk,e) for e in es}
for pk in PKTS: mod |= {(pk, ex.eid) for ex in EX[pk]}
missing = hum - mod
print(f"\nEID NAMESPACE CHECK: {len(hum)} distinct (packet,eid) cited by humans; "
      f"{len(hum & mod)} exist in the model's parsed excerpts ({len(hum & mod)/len(hum):.0%} overlap)")
if missing:
    print(f"  {len(missing)} human eids NOT in parse_excerpts:", sorted(missing)[:12])
    print("  ** If this is large the two sides are not in the same namespace and the comparison below is void. **")
print()
print("="*80)
print("CROSS-DIMENSION COLLISIONS BY EXCERPT ID -- humans and model, same units")
print("="*80)
print(f"{'labeller':<12}{'distinct eids cited':>21}{'eids on 2+ dims':>18}{'rate':>9}")
res={}
for lab in ["rater A","rater B","rater C","LLM v1","LLM v3"]:
    if lab not in sets: continue
    t,dst,pair = score(lab); res[lab]=(t,dst,pair)
    print(f"{lab:<12}{dst:>21}{t:>18}{(t/dst if dst else 0):>9.0%}")

print()
print("top colliding pairs, by labeller:")
for lab,(t,dst,pair) in res.items():
    top=sorted(pair.items(), key=lambda x:-x[1])[:4]
    print(f"  {lab:<9} " + ("  ".join(f"{x[0][0][:4]}/{x[0][1][:4]}={x[1]}" for x in top) if top else "(none)"))

print()
print("="*80)
print("THE ARM B QUESTION: did the v3 edit change the model's collisions?")
print("="*80)
for lab in ("LLM v1","LLM v3"):
    if lab in res: print(f"  {lab}: {res[lab][0]} collisions over {res[lab][1]} distinct eids")
if "LLM v1" in res and "LLM v3" in res:
    if res["LLM v1"][0]==0 and res["LLM v3"][0]==0:
        print("  BOTH ZERO -> the text-matching result was not an artifact. The collision defect")
        print("  S-58 measures does not appear in this extractor at all, which limits how far the")
        print("  extractor can proxy for human anchor readability. Arm B's primary outcome stays void")
        print("  (a floor effect, not a null result) and the qualitative read rests on scores only.")
    else:
        print("  NON-ZERO -> the text-matched 0 WAS an artifact. Arm B's primary outcome is live;")
        print("  compare the two counts above, and note D-21 still applies: one draw per arm, so")
        print("  this is a pilot and the difference is not quotable without >=3 paired draws.")
