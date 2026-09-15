"""Follow-up: is rater B's data structured at all? Not pre-registered - exploratory,
opened only after A2 returned eta2 below the null baseline for B on BOTH main effects."""
import json,glob,os
from collections import defaultdict
RET=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","ground_truth","rater_app","returned","round1")
DIMS=["autonomy","pace","collaboration","feedback","innovation","decision"]
PKTS=["P-0%d"%i for i in range(1,7)]
D={}
for f in sorted(glob.glob(os.path.join(RET,"*.json"))):
    d=json.load(open(f,encoding="utf-8")); D[(d["rater"],d["packet_id"])]=d
def mean(x): return sum(x)/len(x) if x else float('nan')

print("=== effort proxies that are NOT duration ===")
print(f"{'rater':<6}{'quotes/cell':>12}{'cells w/ 0 quotes':>19}{'note chars/cell':>17}{'cells w/ empty note':>21}")
for r in "ABC":
    q=[];n=[];z=0;en=0
    for p in PKTS:
        for row in D[(r,p)]["scores"]:
            k=len(row.get("quotes") or []); q.append(k); z+= (k==0)
            t=(row.get("note") or "").strip(); n.append(len(t)); en+= (t=="")
    print(f"{r:<6}{mean(q):>12.2f}{z:>19}{mean(n):>17.1f}{en:>21}")

print()
print("=== per-packet duration (minutes) and free_note presence ===")
print(f"{'rater':<6}" + "".join(f"{p:>9}" for p in PKTS))
for r in "ABC":
    print(f"{r:<6}" + "".join(f"{D[(r,p)]['duration_seconds']/60:>9.0f}" for p in PKTS))

print()
print("=== score vs commit_position (order effect) ===")
for r in "ABC":
    pairs=[(row["commit_position"],row["score"]) for p in PKTS for row in D[(r,p)]["scores"]]
    for pos in range(1,7):
        v=[s for c,s in pairs if c==pos]
        print(f"  {r} pos{pos}: mean {mean(v):.3f} (n={len(v)})", end="")
    print()

print()
print("=== every rater-B cell: score, conf, #quotes, note ===")
for p in PKTS:
    for row in D[("B",p)]["scores"]:
        print(f"  {p} {row['dimension']:<14} s={row['score']} c={row['confidence']} "
              f"q={len(row.get('quotes') or [])}  note={ (row.get('note') or '')[:95] }")

print()
print("=== FEEDBACK: every quote B and C cited, against the frozen 0.1 band text ===")
print("  frozen feedback 0.1 = 'Feedback is occasional and softened. Harmony valued,")
print("                        conflict avoided, supportive or nurturing framing.'")
for r in "BC":
    for p in PKTS:
        row=[x for x in D[(r,p)]["scores"] if x["dimension"]=="feedback"][0]
        print(f"  --- {p}/{r}  score={row['score']} conf={row['confidence']}")
        for qq in (row.get("quotes") or []):
            print(f"        \"{qq['text'][:110]}\"")
        if row.get("note"): print(f"        note: {row['note'][:110]}")
