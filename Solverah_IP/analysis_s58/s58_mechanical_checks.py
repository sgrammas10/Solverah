"""S-58: two fully mechanical checks that involve no judgement by the analyst,
plus one lexical check whose token lists are written into the file (auditable).
Exploratory, opened after A1-A4. No API calls."""
import json,glob,os,re
from collections import defaultdict
RET=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ground_truth","rater_app","returned","round1")
DIMS=["autonomy","pace","collaboration","feedback","innovation","decision"]
PKTS=["P-0%d"%i for i in range(1,7)]
D={}
for f in sorted(glob.glob(os.path.join(RET,"*.json"))):
    d=json.load(open(f,encoding="utf-8")); D[(d["rater"],d["packet_id"])]=d
def norm(s): return re.sub(r"\s+"," ",re.sub(r"[^\w\s]","",(s or "").lower())).strip()[:120]

print("="*78)
print("M1 — SAME QUOTE CITED UNDER TWO DIFFERENT DIMENSIONS (fully mechanical)")
print("="*78)
print("  Within one rater on one packet: the same passage supporting two constructs.")
tot_w=0
for r in "ABC":
    for p in PKTS:
        by=defaultdict(list)
        for row in D[(r,p)]["scores"]:
            for q in (row.get("quotes") or []): by[norm(q["text"])].append((row["dimension"],row["score"]))
        for k,v in by.items():
            if len({d for d,_ in v})>1:
                tot_w+=1
                print(f"  {p}/{r}: " + " + ".join(f"{d}={s}" for d,s in v))
                print(f"      \"{k[:100]}\"")
print(f"  within-rater reuse across dimensions: {tot_w} instances")
print()
print("  ACROSS raters: same passage, different dimension, same packet")
tot_a=0
for p in PKTS:
    by=defaultdict(list)
    for r in "ABC":
        for row in D[(r,p)]["scores"]:
            for q in (row.get("quotes") or []): by[norm(q["text"])].append((r,row["dimension"],row["score"]))
    for k,v in by.items():
        dims={d for _,d,_ in v}
        if len(dims)>1:
            tot_a+=1
            print(f"  {p}: " + " | ".join(f"{r}:{d}={s}" for r,d,s in v))
            print(f"      \"{k[:100]}\"")
print(f"  cross-rater same-passage-different-dimension: {tot_a} instances")

print()
print("="*78)
print("M2 — EXCERPT REUSE: how concentrated is each rater's evidence base?")
print("="*78)
print(f"{'rater':<6}{'total quotes':>14}{'distinct excerpts (eid)':>26}{'quotes/cell':>13}")
for r in "ABC":
    qs=[q for p in PKTS for row in D[(r,p)]["scores"] for q in (row.get("quotes") or [])]
    eids={(p,q.get('eid')) for p in PKTS for row in D[(r,p)]["scores"] for q in (row.get("quotes") or [])}
    print(f"{r:<6}{len(qs):>14}{len(eids):>26}{len(qs)/36:>13.2f}")

print()
print("="*78)
print("M3 — LEXICAL SIGN CHECK: note uses vocabulary from the OPPOSITE end of the")
print("     same dimension's own band text. Token lists are verbatim-ish from anchors.json.")
print("="*78)
LOW={  # tokens drawn from each dimension's 0.1/0.3 band text
 "autonomy":["micromanag","top-down","top down","sign-off","sign off","established process","rigid procedure","direct supervision","close supervision","mandatory procedure","following procedure","follow procedure"],
 "pace":["deliberate cadence","long planning","calm","sustainable pace","steady"],
 "collaboration":["heads-down","heads down","low meeting","async","individual ownership","work alone"],
 "feedback":["harmony","conflict avoided","softened","nurturing","occasional"],
 "innovation":["operational excellence","refine and scale","efficiency focus","mature offering","conservative","outdated"],
 "decision":["founder gut","trust your judgement","trust your judgment","taste","intuition"],
}
HIGH={
 "autonomy":["minimal approval","high-trust","flat decision","set their own priorities","own their outcomes"],
 "pace":["move fast","rapid iteration","aggressive deadline","long hours","hypergrowth","fast paced","fast-paced","intensity","quick turnaround","quick dec"],
 "collaboration":["pairing","consensus culture","cross-functional","we win together","meetings frequent","teamwork"],
 "feedback":["radical candor","unfiltered","tell it straight","blunt","thicker skin","direct feedback"],
 "innovation":["0-to-1","research culture","novel product","failed experiment","invent","new ideas","challenge status quo"],
 "decision":["data-driven","data driven","experiment-gated","metrics-first","metrics","a/b","analytics"],
}
hits=0
for r in "ABC":
    for p in PKTS:
        for row in D[(r,p)]["scores"]:
            n=(row.get("note") or "").lower(); d=row["dimension"]; s=row["score"]
            if not n: continue
            lo=[t for t in LOW[d] if t in n]; hi=[t for t in HIGH[d] if t in n]
            if lo and s>=0.7:
                hits+=1; print(f"  {p}/{r} {d:<14} score={s} but note has LOW-band term {lo}")
                print(f"      note: {row['note'][:110]}")
            if hi and s<=0.3:
                hits+=1; print(f"  {p}/{r} {d:<14} score={s} but note has HIGH-band term {hi}")
                print(f"      note: {row['note'][:110]}")
print(f"  sign-inconsistent notes: {hits} (out of {sum(1 for r in 'ABC' for p in PKTS for row in D[(r,p)]['scores'] if (row.get('note') or '').strip())} non-empty notes)")
