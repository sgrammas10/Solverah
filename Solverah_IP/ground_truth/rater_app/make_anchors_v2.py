"""Generate anchors_v2_PROPOSED.json as a MINIMAL, auditable diff from the frozen
anchors.json. Every edit is asserted against the exact v1 string it replaces, so this
script fails loudly rather than silently drifting if anchors.json changes underneath it.

WHY A SEPARATE FILE: anchors.json is 'FROZEN 2026-08-15 for ground-truth round 1' by its
own _note, and raters have P-01..P-06 outstanding. Editing it now would invalidate the
round in progress. The file's _note already anticipates a post-round-1 rewrite by Julie
targeting anchors that disagreement shows to be ambiguous -- this is input to that pass,
not a substitute for it.
"""
import json, copy, sys
from pathlib import Path

src = json.loads(Path("anchors.json").read_text(encoding="utf-8"))
v2 = copy.deepcopy(src)
edits = []

def dim(d, key):
    for x in d["dimensions"]:
        if x["key"] == key: return x
    raise KeyError(key)

def swap(obj, field, old, new, why):
    assert obj[field] == old, (
        f"v1 text for {obj.get('key')}.{field} is not what this patch was written "
        f"against.\n  expected: {old!r}\n  found:    {obj[field]!r}")
    obj[field] = new
    edits.append((obj.get("key"), field, old, new, why))

def swap_band(d, value, field, old, new, why):
    b = next(b for b in d["bands"] if b["value"] == value)
    assert b[field] == old, (
        f"v1 text for {d['key']} band {value}.{field} is not what this patch expects.\n"
        f"  expected: {old!r}\n  found:    {b[field]!r}")
    b[field] = new
    edits.append((f"{d['key']} band {value}", field, old, new, why))

C = dim(v2, "collaboration")
A = dim(v2, "autonomy")
I = dim(v2, "innovation")

# --- 1. Collaboration's 0.1 band contradicts Collaboration's own keep_distinct. -------
# keep_distinct says: "Collective teams can still hand individuals full ownership of the
# how. Score meeting and team density here, decision rights under Autonomy."
# The 0.1 band then opens with the words "Individual ownership" -- the exact construct it
# just assigned to Autonomy. Band text is what the scorer matches against, so the band
# wins and the guard is dead letter. Measured effect: autonomy vignettes at 0.5 and above
# pulled collaboration down to 0.3 on 28 of 30 runs across rounds 1-3.
swap_band(C, 0.1, "text",
    "Individual ownership, heads-down norm, low meeting load. Async and individual contribution valued.",
    "Heads-down solo production is the norm. Very low meeting load, little or no pairing, "
    "written async updates in place of live working sessions.",
    "removes 'Individual ownership' -- the construct this dimension's own keep_distinct "
    "assigns to Autonomy. Rewritten purely in terms of interaction density, which is what "
    "keep_distinct says to score here.")

swap_band(C, 0.3, "text",
    "Mostly individual work with periodic syncs. Collaboration is coordination, not co-production.",
    "Work is produced alone and brought together at periodic syncs. Meetings are status "
    "and handoff, not joint problem-solving.",
    "same substitution one band up: 'produced alone' is an interaction fact, 'individual "
    "work' reads as an ownership fact.")

swap(C, "where_to_look",
    "Team structure (pods/squads vs. individual owners), meeting and pairing culture, open-plan vs. deep-work norms, “we win together” vs. “own your area” language, async-individual vs. sync-group.",
    "Team structure (pods/squads vs. single-threaded owners), meeting and pairing culture, "
    "open-plan vs. deep-work norms, “we win together” vs. “heads-down, protect your focus time” "
    "language, async-written vs. sync-group.",
    "'own your area' is verbatim the construct Autonomy's 0.7 band names ('Ownership'). "
    "Telling a rater to look for it under Collaboration guarantees the collision.")

# --- 2. Innovation has no guard against Autonomy, and its low pole is a common verb. ---
# Measured effect: innovation tracked the autonomy level monotonically at the extremes
# (autonomy 0.1 -> innovation 0.1; autonomy 0.9 -> innovation 0.7) on 19 of 20 runs
# across two independently written vignette sets. The round-1 autonomy-low vignette says
# a brief "spells out exactly how to EXECUTE it" -- which is the literal name of
# Innovation's low pole.
swap(I, "low_pole", "Execute / optimize", "Refine / optimize",
    "'Execute' is the ordinary English verb for doing assigned work, so ANY directed-work "
    "evidence lexically matches Innovation's low pole by accident. 'Refine' carries the "
    "same optimize-vs-invent meaning without the collision.")
swap_band(I, 0.1, "reads_as", "Execute / optimize", "Refine / optimize",
    "keeps the band label consistent with the renamed pole.")
swap(I, "keep_distinct",
    "Not the same as Pace. Optimizing can be frantic; inventing can be slow. Score novelty of the work, not its speed.",
    "Not the same as Pace. Optimizing can be frantic; inventing can be slow. Score novelty "
    "of the work, not its speed. Also not the same as Autonomy. How prescribed the method "
    "is says nothing about how novel the output is — a rigid playbook can govern genuinely "
    "new work, and a fully self-directed team can spend all of it refining what exists. Do "
    "not read “follows a detailed brief” as low Innovation or “builds their own approach” "
    "as high Innovation; those are decision-rights facts and belong under Autonomy.",
    "adds the missing Autonomy guard. Pace was guarded and Autonomy was not, yet the "
    "measured coupling is with Autonomy.")

# --- 3. Symmetric guard on Autonomy. --------------------------------------------------
swap(A, "keep_distinct",
    "Not the same as Collaboration. A person can be highly self-directed AND work collectively. Autonomy is about who decides the how; Collaboration is about alone vs. together.",
    "Not the same as Collaboration. A person can be highly self-directed AND work "
    "collectively. Autonomy is about who decides the how; Collaboration is about alone vs. "
    "together — score meeting and pairing density there, never here. Not the same as "
    "Innovation either: a prescribed method can produce novel work and a self-directed team "
    "can spend all its time optimizing.",
    "makes the Collaboration guard directional (it previously stated the distinction "
    "without saying which evidence goes where) and adds the matching Innovation guard.")

v2["rubric_version"] = "v2-PROPOSED-2026-08-17"
v2["_note"] = (
    "PROPOSED, NOT ADOPTED. Generated from anchors.json v1-frozen-2026-08-15 by "
    "make_anchors_v2.py. anchors.json itself is UNTOUCHED and remains frozen while raters "
    "are mid-round on P-01..P-06 — adopting this file mid-round would invalidate the "
    "ground-truth round in progress. This exists to be (a) A/B-tested against the frozen "
    "anchors on identical vignettes via run_vignette_probe.py --anchors, and (b) handed to "
    "Julie as input to the post-round-1 anchor rewrite the frozen file's own _note already "
    "anticipates. Every change targets a measured cross-dimension bleed, not a style "
    "preference; see ANCHOR_BLEED_FIX.md for the evidence behind each one."
)

Path("anchors_v2_PROPOSED.json").write_text(
    json.dumps(v2, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"Wrote anchors_v2_PROPOSED.json  ({len(edits)} edits)\n")
for where, field, old, new, why in edits:
    print(f"[{where}] {field}")
    print(f"  -  {old}")
    print(f"  +  {new}")
    print(f"  WHY: {why}\n")

# guardrail: nothing else moved
a, b = json.loads(Path("anchors.json").read_text()), json.loads(Path("anchors_v2_PROPOSED.json").read_text())
changed = []
def walk(x, y, p=""):
    if isinstance(x, dict):
        for k in x:
            walk(x[k], y[k], f"{p}.{k}")
    elif isinstance(x, list):
        for i,(xi,yi) in enumerate(zip(x,y)): walk(xi, yi, f"{p}[{i}]")
    elif x != y:
        changed.append(p)
walk(a, b)
print(f"total leaf fields changed: {len(changed)} (expected {len(edits)} edits + _note + rubric_version)")
for c in changed: print("   ", c)
