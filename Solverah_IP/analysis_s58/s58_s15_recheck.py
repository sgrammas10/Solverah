"""S-15 headline recheck: is -0.195 a measurement, and does evidence-weighting help?"""
import json,glob,os,random
RET=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ground_truth","rater_app","returned","round1")
DIMS=["autonomy","pace","collaboration","feedback","innovation","decision"]
PKTS=["P-0%d"%i for i in range(1,7)]
S={};Q={}
for f in sorted(glob.glob(os.path.join(RET,"*.json"))):
    d=json.load(open(f,encoding="utf-8"))
    for r in d["scores"]:
        S[(d["rater"],d["packet_id"],r["dimension"])]=r["score"]
        Q[(d["rater"],d["packet_id"],r["dimension"])]=len(r.get("quotes") or [])
def mean(x): return sum(x)/len(x)
def pear(a,b,w=None):
    w=[1.0]*len(a) if w is None else w; W=sum(w)
    ma=sum(x*wi for x,wi in zip(a,w))/W; mb=sum(y*wi for y,wi in zip(b,w))/W
    num=sum(wi*(x-ma)*(y-mb) for x,y,wi in zip(a,b,w))
    den=(sum(wi*(x-ma)**2 for x,wi in zip(a,w))*sum(wi*(y-mb)**2 for y,wi in zip(b,w)))**0.5
    return num/den if den else float('nan')
cells=[(p,d) for p in PKTS for d in DIMS]
def v(r): return [S[(r,p,d)] for p,d in cells]

print("=== 1. does evidence weighting have anything to work with? ===")
for r in "ABC":
    q=[Q[(r,p,d)] for p,d in cells]
    print(f"  rater {r}: quotes/cell min={min(q)} max={max(q)} distinct={sorted(set(q))}")
wmin=[min(Q[("B",p,d)],Q[("C",p,d)]) for p,d in cells]
print(f"  min(B,C) per cell: distinct values {sorted(set(wmin))}, counts "
      f"{ {k:wmin.count(k) for k in sorted(set(wmin))} }")
print(f"  UNWEIGHTED r(B,C) = {pear(v('B'),v('C')):+.3f}")
print(f"  WEIGHTED   r(B,C) = {pear(v('B'),v('C'),wmin):+.3f}   <- weight has almost no variance")
print(f"  cells surviving a 'both raters cited >=2 quotes' filter: {sum(1 for x in wmin if x>=2)}/36")

print()
print("=== 2. is -0.195 distinguishable from zero? CLUSTER bootstrap on PACKETS (n=6) ===")
rng=random.Random(11)
def boot(ra,rb,n=20000):
    out=[]
    for _ in range(n):
        ps=[rng.choice(PKTS) for _ in range(6)]
        a=[S[(ra,p,d)] for p in ps for d in DIMS]; b=[S[(rb,p,d)] for p in ps for d in DIMS]
        r=pear(a,b)
        if r==r: out.append(r)
    out.sort(); return out[int(.025*len(out))], out[int(.975*len(out))]
for a,b in (("B","C"),("A","C"),("A","B")):
    lo,hi=boot(a,b)
    print(f"  r({a},{b}) = {pear(v(a),v(b)):+.3f}   95% CI [{lo:+.3f}, {hi:+.3f}]"
          f"   {'EXCLUDES 0' if (lo>0 or hi<0) else 'INCLUDES 0'}")
print("  (naive cell-level SE would be ~1/sqrt(35)=0.169; cells cluster within packet, so the")
print("   naive interval is too narrow. Resampling packets is the D-21 / clustering-error fix.)")

print()
print("=== 3. is each rater's series distinguishable from a reshuffle of itself? ===")
print("    null: permute rater X's 36 scores (own band distribution preserved), corr vs the other")
for a,b in (("B","C"),("A","C"),("A","B")):
    obs=pear(v(a),v(b)); base=v(a)[:]; other=v(b); hits=0; N=20000
    rg=random.Random(3)
    for _ in range(N):
        rg.shuffle(base)
        if abs(pear(base,other))>=abs(obs)-1e-12: hits+=1
    print(f"  r({a},{b}) = {obs:+.3f}   p(|null| >= |obs|) = {(hits+1)/(N+1):.4f}")
