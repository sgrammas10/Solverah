"""S-58 free analyses A1-A4. Round-1 JSONs + frozen anchors only. No API calls.
Pre-registered in PREREG_S58_2026-09-01b.md BEFORE this was run."""
import json, glob, os, itertools, random
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RET  = os.path.join(HERE, "..", "ground_truth", "rater_app", "returned", "round1")
DIMS = ["autonomy","pace","collaboration","feedback","innovation","decision"]
PKTS = ["P-0%d" % i for i in range(1,7)]
BANDS = [0.1,0.3,0.5,0.7,0.9]
BIDX = {b:i for i,b in enumerate(BANDS)}

# LLM extractor per-cell 5-run means, transcribed from
# claude/LLM_VS_HUMAN_COMPARISON_2026-09-01.md "Full per-cell table".
LLM = {
 ("P-01","autonomy"):0.30,("P-01","pace"):0.70,("P-01","collaboration"):0.70,
 ("P-01","feedback"):0.58,("P-01","innovation"):0.54,("P-01","decision"):0.70,
 ("P-02","autonomy"):0.30,("P-02","pace"):0.70,("P-02","collaboration"):0.70,
 ("P-02","feedback"):0.42,("P-02","innovation"):0.30,("P-02","decision"):0.58,
 ("P-03","autonomy"):0.70,("P-03","pace"):0.90,("P-03","collaboration"):0.70,
 ("P-03","feedback"):0.50,("P-03","innovation"):0.70,("P-03","decision"):0.70,
 ("P-04","autonomy"):0.74,("P-04","pace"):0.90,("P-04","collaboration"):0.70,
 ("P-04","feedback"):0.50,("P-04","innovation"):0.90,("P-04","decision"):0.50,
 ("P-05","autonomy"):0.70,("P-05","pace"):0.30,("P-05","collaboration"):0.42,
 ("P-05","feedback"):0.30,("P-05","innovation"):0.30,("P-05","decision"):0.70,
 ("P-06","autonomy"):0.34,("P-06","pace"):0.38,("P-06","collaboration"):0.70,
 ("P-06","feedback"):0.34,("P-06","innovation"):0.30,("P-06","decision"):0.70,
}

score, conf, note, quotes = {}, {}, {}, {}
for f in sorted(glob.glob(os.path.join(RET,"*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    p, r = d["packet_id"], d["rater"]
    for row in d["scores"]:
        score[(r,p,row["dimension"])] = row["score"]
        conf[(r,p,row["dimension"])]  = row["confidence"]
        note[(r,p,row["dimension"])]  = row.get("note","") or ""
        quotes[(r,p,row["dimension"])]= row.get("quotes",[]) or []
for k,v in LLM.items(): score[("LLM",)+k] = v

RATERS = ["A","B","C","LLM"]
def cells(r): return [score[(r,p,d)] for p in PKTS for d in DIMS]

def mean(x): return sum(x)/len(x)
def ss(x):
    m = mean(x); return sum((v-m)**2 for v in x)

def decompose(vals):
    """vals indexed [p][d], 6x6."""
    flat = [v for row in vals for v in row]
    g = mean(flat)
    pk = [mean(row) for row in vals]
    dm = [mean([vals[i][j] for i in range(6)]) for j in range(6)]
    ss_tot = sum((v-g)**2 for v in flat)
    ss_pk  = 6*sum((m-g)**2 for m in pk)
    ss_dm  = 6*sum((m-g)**2 for m in dm)
    return ss_pk, ss_dm, ss_tot, [m-g for m in pk], [m-g for m in dm]

def perm_p(vals, observed, n=10000, seed=0):
    flat = [v for row in vals for v in row]
    rng = random.Random(seed); hits = 0
    for _ in range(n):
        rng.shuffle(flat)
        g = mean(flat)
        pk = [mean(flat[i*6:(i+1)*6]) for i in range(6)]
        tot = sum((v-g)**2 for v in flat)
        e = (6*sum((m-g)**2 for m in pk))/tot if tot else 0
        if e >= observed - 1e-12: hits += 1
    return (hits+1)/(n+1)

def pearson(a,b):
    ma,mb = mean(a),mean(b)
    num = sum((x-ma)*(y-mb) for x,y in zip(a,b))
    den = (sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))**0.5
    return num/den if den else float('nan')

def spearman(a,b):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i]); r=[0.0]*len(v); i=0
        while i < len(v):
            j=i
            while j+1<len(v) and v[s[j+1]]==v[s[i]]: j+=1
            avg=(i+j)/2.0+1
            for k in range(i,j+1): r[s[k]]=avg
            i=j+1
        return r
    return pearson(rank(a),rank(b))

print("="*78); print("A1 — DIRECTION OF DRIFT: band usage per labeller (36 cells each)"); print("="*78)
print(f"{'labeller':<9}" + "".join(f"{b:>7}" for b in BANDS) + f"{'0.1':>8}{'0.9':>7}{'mean':>8}")
for r in RATERS:
    v = cells(r)
    if r=="LLM":
        cnt=[0]*5
        for x in v:
            cnt[min(range(5), key=lambda i: abs(BANDS[i]-x))]+=1
    else:
        cnt=[0]*5
        for x in v: cnt[BIDX[x]]+=1
    print(f"{r:<9}" + "".join(f"{c:>7}" for c in cnt) + f"{cnt[0]:>8}{cnt[4]:>7}{mean(v):>8.3f}")

print()
print("="*78); print("A2 — GLOBAL IMPRESSION: variance decomposition, 10k permutation null"); print("="*78)
pk_eff = {}
print(f"{'labeller':<9}{'eta2_packet':>13}{'perm p':>9}{'eta2_dim':>10}{'perm p':>9}{'eta2_resid':>12}")
for r in RATERS:
    vals=[[score[(r,p,d)] for d in DIMS] for p in PKTS]
    ss_pk, ss_dm, ss_tot, pe, de = decompose(vals)
    pk_eff[r]=pe
    e_pk, e_dm = ss_pk/ss_tot, ss_dm/ss_tot
    # dimension-effect permutation uses the transpose
    valsT=[[score[(r,p,d)] for p in PKTS] for d in DIMS]
    p_pk = perm_p(vals, e_pk, seed=1)
    p_dm = perm_p(valsT, e_dm, seed=2)
    print(f"{r:<9}{e_pk:>13.3f}{p_pk:>9.4f}{e_dm:>10.3f}{p_dm:>9.4f}{1-e_pk-e_dm:>12.3f}")
print("  (null expectation for either eta2 with 6x6 and no structure = 5/35 = 0.143)")
print()
print("  packet effects (alpha_p), by labeller:")
print(f"  {'':<9}" + "".join(f"{p:>8}" for p in PKTS))
for r in RATERS:
    print(f"  {r:<9}" + "".join(f"{x:>8.3f}" for x in pk_eff[r]))
print()
print("  pairwise correlation of packet effects (n=6; |r|>=0.81 needed for p<0.05):")
for a,b in itertools.combinations(RATERS,2):
    print(f"    {a}-{b}: r = {pearson(pk_eff[a],pk_eff[b]):+.3f}")
print()
print("  for reference, cell-level correlation of raw scores (n=36):")
for a,b in itertools.combinations(RATERS,2):
    print(f"    {a}-{b}: r = {pearson(cells(a),cells(b)):+.3f}")

print()
print("="*78); print("A3 — WHERE THE 0.1 BAND IS USED (humans A,B,C)"); print("="*78)
print(f"{'dimension':<15}{'0.1 uses /18':>14}{'0.9 uses /18':>14}   which cells used 0.1")
for d in DIMS:
    lo=[(r,p) for r in "ABC" for p in PKTS if score[(r,p,d)]==0.1]
    hi=[(r,p) for r in "ABC" for p in PKTS if score[(r,p,d)]==0.9]
    print(f"{d:<15}{len(lo):>14}{len(hi):>14}   " + ", ".join(f"{p}/{r}" for r,p in lo))

print()
print("="*78); print("A4 — CONFIDENCE (free; not in STATE)"); print("="*78)
print(f"{'dimension':<15}" + "".join(f"{'rater '+r:>10}" for r in "ABC") + f"{'B+C mean':>11}")
dim_conf={}
for d in DIMS:
    row=[mean([conf[(r,p,d)] for p in PKTS]) for r in "ABC"]
    bc = mean([conf[(r,p,d)] for r in "BC" for p in PKTS]); dim_conf[d]=bc
    print(f"{d:<15}" + "".join(f"{x:>10.3f}" for x in row) + f"{bc:>11.3f}")
print(f"{'ALL':<15}" + "".join(f"{mean([conf[(r,p,d)] for p in PKTS for d in DIMS]):>10.3f}" for r in "ABC")
      + f"{mean([conf[(r,p,d)] for r in 'BC' for p in PKTS for d in DIMS]):>11.3f}")
print()
dist=[]; cavg=[]
for p in PKTS:
    for d in DIMS:
        dist.append(abs(BIDX[score[("B",p,d)]]-BIDX[score[("C",p,d)]]))
        cavg.append((conf[("B",p,d)]+conf[("C",p,d)])/2)
print(f"  Spearman(B-C band distance, mean B/C confidence) over 36 cells = {spearman(dist,cavg):+.3f}")
print(f"  Pearson  same                                                 = {pearson(dist,cavg):+.3f}")
print(f"  mean band distance = {mean(dist):.3f};  cells >=2 apart = {sum(1 for x in dist if x>=2)}/36")
print()
print("  mean B-C band distance by dimension, vs that dimension's mean B/C confidence:")
for d in DIMS:
    dd=[abs(BIDX[score[("B",p,d)]]-BIDX[score[("C",p,d)]]) for p in PKTS]
    print(f"    {d:<15} dist {mean(dd):.2f}   conf {dim_conf[d]:.3f}")
print()
print("  confidence=0.1 ('almost nothing bears on this dimension') counts:")
for r in "ABC":
    lows=[(p,d) for p in PKTS for d in DIMS if conf[(r,p,d)]==0.1]
    bydim=defaultdict(int)
    for p,d in lows: bydim[d]+=1
    print(f"    rater {r}: {len(lows)}/36  " + ", ".join(f"{k}={v}" for k,v in sorted(bydim.items())))
