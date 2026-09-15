"""M4: passage-level construct agreement + permutation null. Fully mechanical."""
import json,glob,os,re,random
from collections import defaultdict
RET=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ground_truth","rater_app","returned","round1")
DIMS=["autonomy","pace","collaboration","feedback","innovation","decision"]
PKTS=["P-0%d"%i for i in range(1,7)]
D={}
for f in sorted(glob.glob(os.path.join(RET,"*.json"))):
    d=json.load(open(f,encoding="utf-8")); D[(d["rater"],d["packet_id"])]=d
def norm(s): return re.sub(r"\s+"," ",re.sub(r"[^\w\s]","",(s or "").lower())).strip()[:120]

# citations as (packet, rater, dimension, passage)
CIT=[(p,r,row["dimension"],norm(q["text"]))
     for r in "ABC" for p in PKTS for row in D[(r,p)]["scores"] for q in (row.get("quotes") or [])]
print(f"total citations: {len(CIT)}")

print()
print("="*78)
print("M4a — PASSAGES CITED BY 2+ RATERS: do they file it under the same dimension?")
print("="*78)
by=defaultdict(lambda: defaultdict(set))   # (packet,passage) -> rater -> {dims}
for p,r,d,q in CIT: by[(p,q)][r].add(d)
shared=[(k,v) for k,v in by.items() if len(v)>=2]
agree=sum(1 for k,v in shared if len(set.intersection(*v.values()))>0)
exact=sum(1 for k,v in shared if len({frozenset(s) for s in v.values()})==1)
print(f"  passages cited by >=2 raters: {len(shared)}")
print(f"  ...where the raters' dimension sets OVERLAP at all: {agree} ({agree/len(shared):.0%})")
print(f"  ...where they are IDENTICAL:                        {exact} ({exact/len(shared):.0%})")
print(f"  ...ZERO overlap (same words, entirely different constructs): {len(shared)-agree} ({1-agree/len(shared):.0%})")

# permutation null: reshuffle dimension labels within (packet,rater), preserving counts
def stat(cits):
    b=defaultdict(lambda: defaultdict(set))
    for p,r,d,q in cits: b[(p,q)][r].add(d)
    sh=[v for v in b.values() if len(v)>=2]
    return sum(1 for v in sh if len(set.intersection(*v.values()))>0)/len(sh)
rng=random.Random(7); null=[]
for _ in range(5000):
    perm=[]
    for r in "ABC":
        for p in PKTS:
            sub=[c for c in CIT if c[0]==p and c[1]==r]
            dims=[c[2] for c in sub]; rng.shuffle(dims)
            perm += [(c[0],c[1],dd,c[3]) for c,dd in zip(sub,dims)]
    null.append(stat(perm))
obs=agree/len(shared)
print(f"  permutation null (dimension labels shuffled within rater x packet, 5000 draws):")
print(f"    null mean overlap rate = {sum(null)/len(null):.3f}   observed = {obs:.3f}")
print(f"    p(null >= observed) = {(sum(1 for x in null if x>=obs-1e-12)+1)/(len(null)+1):.4f}")

print()
print("="*78)
print("M4b — the same statistic per DIMENSION PAIR: which constructs collide most?")
print("="*78)
coll=defaultdict(int)
for k,v in by.items():
    ds=sorted(set().union(*v.values()))
    for i in range(len(ds)):
        for j in range(i+1,len(ds)): coll[(ds[i],ds[j])]+=1
for (a,b),n in sorted(coll.items(), key=lambda x:-x[1])[:12]:
    print(f"  {a:<14} <-> {b:<14} {n:>4} shared passages")

print()
print("="*78)
print("M4c — within one rater, share of that rater's cited passages used on >1 dimension")
print("="*78)
for r in "ABC":
    b=defaultdict(set)
    for p,rr,d,q in CIT:
        if rr==r: b[(p,q)].add(d)
    multi=sum(1 for v in b.values() if len(v)>1)
    print(f"  rater {r}: {multi}/{len(b)} distinct passages ({multi/len(b):.0%}) filed under 2+ dimensions")
