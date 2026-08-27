#!/usr/bin/env python3
"""
check_state.py -- verifies that STATE.md's claims are still true. S-28.

WHAT PROBLEM THIS SOLVES, precisely
-----------------------------------
Seven incidents on this project have the same shape and it is NOT "stale prose":

  1. S-35   STATE carried `ABS(A-B) > 0.15` as a locked rule while the live frozen
            anchors.json said band distance. A CITATION that did not match its source.
  2.        STATE said "6 rater HTML files" where 18 exist. A COUNT that did not match
            the filesystem.
  3. S-18   STATE described rule 6's prediction in terminology the yaml contradicted.
            Another citation that did not match its source.
  4. S-34   "nothing from 08-19 committed" survived the commit that falsified it. A
            claim about GIT that git disagreed with.
  5. S-44   An inherited deadline outlived its cause. A claim about PRIORITY.
  6. S-40   A test asserted an order it could not detect losing. A claim about a TEST.
  7. 08-19b A recorded CI was computed from correlated observations. A claim about
            STATISTICAL VALIDITY.

Note what those have in common: 1-4 are claims about things that exist and can be opened.
5-7 are not. This checker addresses 1-4 and says so out loud; see "HONEST LIMITS" below and
the final section of its own output. A checker that implied it covered 5-7 would be worse
than none, because the six incidents happened to people who believed they had checked.

THE ANTI-DRIFT MECHANISM (the part that makes this more than a linter)
----------------------------------------------------------------------
The registered claims in CLAIMS are TRIPLES, and both halves must hold:

    state_text  -- an exact substring that MUST appear in STATE
    verify      -- a callable that MUST find the same fact in the artifact

If the artifact stops matching, STATE is wrong -> FAIL.
If STATE stops SAYING it, this check is stale -> FAIL, loudly, as CHECK-STALE.

That second half is the one that matters. A registry that only validated artifacts would
itself rot the moment STATE was rewritten -- the exact failure mode being guarded against,
reintroduced one level up. Here, rewriting STATE past a registered claim breaks the build
and forces the claim to be updated or deliberately deleted.

WHERE STATE LIVES
-----------------
STATE.md is a claude.ai Project doc, not a repo file, and it must stay that way -- a
permanent second copy on disk would be two sources of truth, which is the drift this file
exists to catch. So this is a FUNCTION OVER TEXT: pass the current STATE in via --state
(a path, or `-` for stdin). Nothing here reads or writes a canonical STATE.

HONEST LIMITS -- read before trusting a green run
--------------------------------------------------
* It cannot tell you STATE is COMPLETE. Nothing here notices a decision that was made and
  never written down; only claims that ARE present get checked.
* It cannot check reasoning, priority, or statistical validity (incidents 5-7).
* Registered claims are a hand-curated subset. `--list-claims` prints exactly what is
  covered; everything else in STATE is unverified prose.
* Artifact existence is checked by name. A file that exists but says something different is
  only caught if a registered claim looks inside it.

Usage:
    python check_state.py --state STATE.md
    ... | python check_state.py --state -
    python check_state.py --state STATE.md --repo ~/Solverah --ip ~/Solverah_IP
    python check_state.py --list-claims
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------

class Report:
    def __init__(self):
        self.fails: list[str] = []
        self.warns: list[str] = []
        self.skips: list[str] = []
        self.passes = 0
        self.quiet = False

    def chk(self, cond, msg, warn_only=False):
        if cond:
            self.passes += 1
            if not self.quiet:
                print(f"  PASS  {msg}")
        elif warn_only:
            self.warns.append(msg)
            print(f"  WARN  {msg}")
        else:
            self.fails.append(msg)
            print(f"  FAIL  {msg}")
        return bool(cond)

    def skip(self, msg):
        self.skips.append(msg)
        print(f"  SKIP  {msg}")

    @property
    def ok(self) -> bool:
        return not self.fails


# --------------------------------------------------------------------------------------
# Section splitting
# --------------------------------------------------------------------------------------

SECTION_RE = re.compile(r"^## (\d)\.\s*(.+)$", re.M)


def split_sections(state: str) -> dict[int, str]:
    """{section_number: body}. STATE's headings are '## 1. ...' through '## 7. ...'."""
    marks = [(int(m.group(1)), m.start(), m.end()) for m in SECTION_RE.finditer(state)]
    out = {}
    for i, (num, _start, end) in enumerate(marks):
        stop = marks[i + 1][1] if i + 1 < len(marks) else len(state)
        out[num] = state[end:stop]
    return out


# An item DEFINITION looks like  **S-45 — title**  at the start of a line (em dash or hyphen,
# optionally preceded by a list bullet as in section 6). A bare "S-45" inside prose is a
# REFERENCE and must not be counted as a definition.
DEF_RE = re.compile(r"^\s*(?:[-*]\s*)?\*\*(S-\d+)\s*[—-]", re.M)
REF_RE = re.compile(r"\b(S-\d+)\b")
DDEF_RE = re.compile(r"^\s*[-*]\s*\*\*(D-\d+)\.", re.M)
DREF_RE = re.compile(r"\b(D-\d+)\b")
CARRIED_RE = re.compile(r"`carried:\s*(\d+)`")


# --------------------------------------------------------------------------------------
# Group 1 -- STATE's internal structure. No filesystem needed.
# --------------------------------------------------------------------------------------

def check_structure(state: str, rep: Report) -> None:
    print("\n[1] STATE internal structure")
    sections = split_sections(state)

    for n in range(1, 8):
        rep.chk(n in sections, f"section {n} is present")
    if not {3, 4, 6, 7} <= set(sections):
        rep.chk(False, "cannot continue structural checks without sections 3, 4, 6 and 7")
        return

    open_ids = DEF_RE.findall(sections[3])
    closed_ids = DEF_RE.findall(sections[6])
    wontdo_ids = DEF_RE.findall(sections[7])

    rep.chk(bool(open_ids), f"section 3 defines open items ({len(open_ids)} found)")
    rep.chk(bool(closed_ids), f"section 6 defines closed items ({len(closed_ids)} found)")

    # An ID in two places is the drift that makes "is this open?" unanswerable.
    for a_name, a, b_name, b in (
        ("open", open_ids, "closed", closed_ids),
        ("open", open_ids, "won't-do", wontdo_ids),
        ("closed", closed_ids, "won't-do", wontdo_ids),
    ):
        both = sorted(set(a) & set(b))
        rep.chk(not both, f"no item is both {a_name} and {b_name}" + (f" -- {both}" if both else ""))

    all_defs = open_ids + closed_ids + wontdo_ids
    dupes = sorted({i for i in all_defs if all_defs.count(i) > 1})
    rep.chk(not dupes, "every S-id is defined exactly once" + (f" -- {dupes}" if dupes else ""))

    # Every S-id mentioned anywhere must be defined somewhere, or a reader follows a dead
    # pointer. (S-nn IDs are permanent precisely so references keep resolving.)
    referenced = set(REF_RE.findall(state))
    dangling = sorted(referenced - set(all_defs))
    rep.chk(not dangling, "every referenced S-id is defined" + (f" -- {dangling}" if dangling else ""))

    # Every open item carries the defect counter -- it is what stops an item drifting for
    # weeks while collecting adjectives.
    missing_carried = []
    body = sections[3]
    for m in DEF_RE.finditer(body):
        chunk = body[m.start(): m.start() + 900]
        if not CARRIED_RE.search(chunk):
            missing_carried.append(m.group(1))
    rep.chk(
        not missing_carried,
        "every open item declares `carried:`" + (f" -- {missing_carried}" if missing_carried else ""),
    )

    # The carried:5 limit is the rule STATE states about itself. Written as a plain loop: the
    # comprehension this replaced dereferenced the match before its own guard and crashed on
    # exactly the input the check above had just flagged (an item with no counter at all).
    over = []
    for m in DEF_RE.finditer(body):
        found = CARRIED_RE.search(body[m.start(): m.start() + 900])
        if found and int(found.group(1)) > 5:
            over.append((m.group(1), int(found.group(1))))
    rep.chk(not over, "no open item exceeds the carried:5 limit" + (f" -- {over}" if over else ""))

    d_defined = set(DDEF_RE.findall(sections[4]))
    d_referenced = set(DREF_RE.findall(state))
    d_dangling = sorted(d_referenced - d_defined)
    rep.chk(bool(d_defined), f"section 4 defines locked decisions ({len(d_defined)} found)")
    rep.chk(
        not d_dangling,
        "every referenced D-id is defined in section 4" + (f" -- {d_dangling}" if d_dangling else ""),
    )


# --------------------------------------------------------------------------------------
# Group 2 -- artifacts named in STATE exist on disk
# --------------------------------------------------------------------------------------

# Backticked tokens that look like files. Deliberately conservative: a known code extension,
# so prose in backticks (`carried:`, `mean_pole`, `status: active`) is not mistaken for a path.
PATHISH_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|yaml|yml|json|sql|md|ts|tsx|ini|csv|png|docx|xlsx))`")

# Named in STATE but deliberately not on disk. Each entry must say WHY, and each is a claim
# in its own right -- if one of these turns up, STATE should be updated to stop excusing it.
EXPECTED_ABSENT = {
    "Solverah_Ground_Truth_Roster_v2.md": "STATE records it as UNKNOWN/missing (S-16)",
    "SOLVERAH_HANDOFF.md": "the stray copy is the subject of S-20, path deliberately unresolved",
    "check_state.py": "self-reference; resolved separately",
    "CLAUDE.md": "not a Solverah artifact",
}


def _index_files(roots: list[Path]) -> dict[str, list[Path]]:
    """basename -> paths, skipping vendored/dead trees."""
    skip = {"node_modules", ".git", "__pycache__", "_to_delete", "dist", ".pytest_cache",
            "venv", ".venv", "_quarantine_not_ground_truth", "_build_env"}
    index: dict[str, list[Path]] = {}
    for root in roots:
        if not root or not root.exists():
            continue
        for p in root.rglob("*"):
            if any(part in skip for part in p.parts):
                continue
            if p.is_file():
                index.setdefault(p.name, []).append(p)
    return index


def check_artifacts(state: str, roots: list[Path], rep: Report) -> None:
    print("\n[2] Artifacts named in STATE exist on disk")
    if not any(r and r.exists() for r in roots):
        rep.skip("no readable repo/IP root given -- artifact existence unverified")
        return

    index = _index_files(roots)
    named = sorted({Path(m).name for m in PATHISH_RE.findall(state)})
    missing, excused = [], []
    for name in named:
        if name in index:
            continue
        if name in EXPECTED_ABSENT:
            excused.append(f"{name} ({EXPECTED_ABSENT[name]})")
        else:
            missing.append(name)

    rep.chk(
        not missing,
        f"all {len(named)} artifact names in STATE resolve on disk"
        + (f" -- MISSING: {missing}" if missing else ""),
    )
    for e in excused:
        rep.skip(f"expected-absent: {e}")


# --------------------------------------------------------------------------------------
# Group 3 -- registered claims: STATE says X AND the artifact confirms X
# --------------------------------------------------------------------------------------

def _find(roots: list[Path], *rel_candidates: str) -> Path | None:
    for root in roots:
        if not root or not root.exists():
            continue
        for rel in rel_candidates:
            p = root / rel
            if p.exists():
                return p
    index = _index_files(roots)
    for rel in rel_candidates:
        hits = index.get(Path(rel).name)
        if hits:
            return hits[0]
    return None


def _anchors(roots):
    p = _find(roots, "ground_truth/rater_app/anchors.json", "anchors.json")
    return (json.loads(p.read_text(encoding="utf-8")), p) if p else (None, None)


def _items(roots):
    import yaml
    p = _find(roots, "causal_graph/v1_model/assessment_items_v2.yaml", "assessment_items_v2.yaml")
    return (yaml.safe_load(p.read_text(encoding="utf-8")), p) if p else (None, None)


def _v_anchors_rubric_version(roots):
    d, p = _anchors(roots)
    if d is None:
        return None, "anchors.json not found"
    return d.get("rubric_version") == "v1-frozen-2026-08-15", f"rubric_version={d.get('rubric_version')!r} in {p}"


def _v_anchors_band_values(roots):
    d, p = _anchors(roots)
    if d is None:
        return None, "anchors.json not found"
    return d.get("band_values") == [0.1, 0.3, 0.5, 0.7, 0.9], f"band_values={d.get('band_values')} in {p}"


def _v_agreement_rule_is_band_distance(roots):
    """The S-35 incident itself: STATE once carried a numeric threshold (0.15) that the live
    rule never contained. Assert the live rule is keyed on BAND DISTANCE and carries no
    numeric threshold at all."""
    d, p = _anchors(roots)
    if d is None:
        return None, "anchors.json not found"
    rule = d.get("agreement_rule")
    if not isinstance(rule, dict):
        return False, f"agreement_rule is {type(rule).__name__}, expected an object keyed by band distance"
    keys = set(rule)
    band_keyed = {"same_band", "one_band_apart", "two_or_more_bands_apart"} <= keys
    numeric = [t for t in json.dumps(rule).split() if re.fullmatch(r"0\.\d+", t.strip('",'))]
    return band_keyed and not numeric, (
        f"agreement_rule keys={sorted(keys)}, stray numeric thresholds={numeric or 'none'} in {p}"
    )


def _v_rater_html_count(roots):
    """The '6 rater HTML files' incident: 6 packets x 3 raters = 18."""
    for root in roots:
        if not root or not root.exists():
            continue
        for rel in ("ground_truth/rater_app/out", "rater_app/out"):
            d = root / rel
            if d.exists():
                n = len(list(d.glob("*.html")))
                return n == 18, f"{n} .html files in {d}"
    return None, "rater_app/out not found"


def _v_items_form_version(roots):
    d, p = _items(roots)
    if d is None:
        return None, "assessment_items_v2.yaml not found"
    return d.get("form_version") == "v2-2026-08-18", f"form_version={d.get('form_version')!r} in {p}"


def _v_items_active(roots):
    d, p = _items(roots)
    if d is None:
        return None, "assessment_items_v2.yaml not found"
    return d.get("status") == "active", f"status={d.get('status')!r} in {p}"


def _v_items_scoring_method(roots):
    d, p = _items(roots)
    if d is None:
        return None, "assessment_items_v2.yaml not found"
    m = (d.get("scoring") or {}).get("method")
    return m == "mean_pole", f"scoring.method={m!r} in {p}"


def _v_items_arity(roots):
    """D-02: exactly four items per dimension, six dimensions, 24 total."""
    import collections
    d, p = _items(roots)
    if d is None:
        return None, "assessment_items_v2.yaml not found"
    items = d.get("items") or []
    per = collections.Counter(i["dimension"] for i in items)
    ok = len(items) == 24 and len(per) == 6 and set(per.values()) == {4}
    return ok, f"{len(items)} items across {len(per)} dimensions, per-dimension={dict(per)} in {p}"


def _v_items_v1_superseded(roots):
    import yaml
    p = _find(roots, "causal_graph/v1_model/assessment_items.yaml", "assessment_items.yaml")
    if p is None:
        return None, "assessment_items.yaml not found"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    return d.get("status") == "superseded", f"status={d.get('status')!r} in {p}"


def _v_min_draws(roots):
    p = _find(roots, "causal_graph/v1_model/seed_discipline.py", "seed_discipline.py")
    if p is None:
        return None, "seed_discipline.py not found"
    m = re.search(r"^MIN_DRAWS\s*=\s*(\d+)", p.read_text(encoding="utf-8"), re.M)
    return (m is not None and m.group(1) == "3"), f"MIN_DRAWS={m.group(1) if m else 'absent'} in {p}"


def _v_confidence_pending_feedback(roots):
    """D-17(a): feedback's stored confidence stays NULL, enforced in code."""
    p = _find(roots, "assessment_form.py")
    if p is None:
        return None, "assessment_form.py not found"
    m = re.search(r"CONFIDENCE_PENDING_DIMENSIONS\s*=\s*frozenset\(\{([^}]*)\}\)",
                  p.read_text(encoding="utf-8"))
    inner = m.group(1) if m else "absent"
    return (m is not None and "feedback" in inner), \
        f"CONFIDENCE_PENDING_DIMENSIONS={{{inner}}} in {p}"


def _v_person_lattice(roots):
    p = _find(roots, "causal_graph/v1_model/match_core.py", "match_core.py")
    if p is None:
        return None, "match_core.py not found"
    m = re.search(r"PERSON_LATTICE\s*=\s*np\.array\(\[([^\]]*)\]\)", p.read_text(encoding="utf-8"))
    if not m:
        return False, f"PERSON_LATTICE not found in {p}"
    vals = [float(x) for x in m.group(1).split(",")]
    return vals == [0.0, 0.25, 0.5, 0.75, 1.0], f"PERSON_LATTICE={vals} in {p}"


# Each entry: (name, state_text_that_must_be_present, verifier)
CLAIMS = [
    ("anchors.rubric_version",
     "FROZEN `v1-frozen-2026-08-15`", _v_anchors_rubric_version),
    ("anchors.band_values",
     "`band_values` `[0.1,0.3,0.5,0.7,0.9]`", _v_anchors_band_values),
    ("anchors.agreement_rule_is_band_distance",
     "Band distance, compared as integers", _v_agreement_rule_is_band_distance),
    ("rater_html_count_18",
     "P-01`–`P-06` × A, B, C = 18", _v_rater_html_count),
    ("items.form_version",
     "`form_version: v2-2026-08-18`", _v_items_form_version),
    ("items.status_active",
     "`status: active`", _v_items_active),
    ("items.scoring_method",
     "mean_pole", _v_items_scoring_method),
    ("items.arity_D02",
     "Exactly four items per dimension", _v_items_arity),
    ("items_v1.superseded",
     "`status: superseded`", _v_items_v1_superseded),
    ("seed_discipline.min_draws_3",
     "≥3 independent draws", _v_min_draws),
    ("confidence.feedback_pending",
     "CONFIDENCE_PENDING_DIMENSIONS", _v_confidence_pending_feedback),
    ("match_core.person_lattice",
     "`PERSON_LATTICE`", _v_person_lattice),
]


def check_claims(state: str, roots: list[Path], rep: Report) -> None:
    print("\n[3] Registered claims -- STATE says it AND the artifact confirms it")
    for name, state_text, verify in CLAIMS:
        if state_text not in state:
            rep.chk(False, (
                f"CHECK-STALE [{name}]: STATE no longer contains {state_text!r}. Either the "
                f"claim moved (update this check) or it was dropped (delete this check). A "
                f"registry that silently outlives STATE is the drift this file exists to catch."
            ))
            continue
        try:
            ok, detail = verify(roots)
        except Exception as exc:  # a verifier that crashes must not read as a pass
            rep.chk(False, f"[{name}] verifier raised {type(exc).__name__}: {exc}")
            continue
        if ok is None:
            rep.skip(f"[{name}] artifact unavailable -- {detail}")
        else:
            rep.chk(ok, f"[{name}] {detail}")


# --------------------------------------------------------------------------------------
# Group 4 -- claims about git (the S-34 incident)
# --------------------------------------------------------------------------------------

def _blocks(state: str) -> list[str]:
    """STATE split into units small enough that 'a filename and the word uncommitted appear
    together' means they are about each other: every table ROW is its own block, and prose is
    split on blank lines.

    The first version of this used a proximity regex (filename, then 'uncommitted' within 200
    non-period characters). Against real STATE it matched NOTHING and reported a cheerful
    'no claims to verify' while sixteen such claims sat in the file -- a check whose failure
    was invisible, in the checker written to catch exactly that (S-40). Blocks are dumber and
    they work.
    """
    out, buf = [], []
    for line in state.splitlines():
        if line.lstrip().startswith("|"):
            if buf:
                out.append("\n".join(buf))
                buf = []
            out.append(line)
        elif not line.strip():
            if buf:
                out.append("\n".join(buf))
                buf = []
        else:
            buf.append(line)
    if buf:
        out.append("\n".join(buf))
    return out


def _uncommitted_claims(state: str) -> list[str]:
    names = set()
    for block in _blocks(state):
        if "uncommitted" not in block.lower():
            continue
        names.update(Path(m).name for m in PATHISH_RE.findall(block))
    return sorted(names)


def check_git_claims(state: str, repo: Path | None, rep: Report) -> None:
    print("\n[4] Claims about git state")
    claimed = _uncommitted_claims(state)
    if not claimed:
        rep.skip("STATE makes no 'uncommitted' claims to verify")
        return
    if not repo or not (repo / ".git").exists():
        rep.skip(f"no git repo at {repo} -- {len(claimed)} 'uncommitted' claims unverified")
        return
    try:
        out = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                             capture_output=True, text=True, timeout=60)
    except Exception as exc:
        rep.skip(f"git unavailable ({type(exc).__name__}) -- {len(claimed)} claims unverified")
        return
    if out.returncode != 0:
        rep.skip(f"git status failed -- {len(claimed)} claims unverified")
        return
    dirty = {Path(line[3:].strip().strip('"')).name for line in out.stdout.splitlines() if line.strip()}
    contradicted = [c for c in claimed if c not in dirty]
    rep.chk(
        not contradicted,
        f"all {len(claimed)} files STATE calls uncommitted are dirty in git"
        + (f" -- CONTRADICTED (git says clean): {contradicted}" if contradicted else ""),
    )


# --------------------------------------------------------------------------------------
# Coverage -- printed every run, pass or fail
# --------------------------------------------------------------------------------------

UNCHECKABLE = [
    "COMPLETENESS. A decision made and never written into STATE is invisible here. Nothing "
    "in this file can tell you what is missing -- only whether what is present is true.",
    "PRIORITY claims (S-44 class). 'This blocks launch' / 'must be done before X' cannot be "
    "verified mechanically; re-derive them by hand, per the rule in STATE's header.",
    "STATISTICAL VALIDITY (the 08-19b CI). Whether a number was computed from independent "
    "observations is not visible in the text that quotes it. D-21's Finding objects are the "
    "control for that, at the point of production -- not this checker.",
    "TEST QUALITY (S-40 class). Whether a test can detect its own failure is a property of "
    "its fixtures. Mutation testing is the control, not this checker.",
    "Prose that no registered claim covers. Run --list-claims to see the covered subset.",
]


def print_coverage():
    print("\n[coverage] What a green run does NOT mean:")
    for line in UNCHECKABLE:
        print(f"  - {line}")


def run_checks(state: str, repo: Path | None = None, ip: Path | None = None) -> Report:
    rep = Report()
    roots = [r for r in (repo, ip) if r is not None]
    check_structure(state, rep)
    check_artifacts(state, roots, rep)
    check_claims(state, roots, rep)
    check_git_claims(state, repo, rep)
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", help="path to STATE.md, or '-' for stdin")
    ap.add_argument("--repo", default=None, help="Solverah repo root")
    ap.add_argument("--ip", default=None, help="Solverah_IP root")
    ap.add_argument("--list-claims", action="store_true",
                    help="print the registered claims and exit")
    args = ap.parse_args()

    if args.list_claims:
        print("Registered claims (STATE text -> artifact verified):")
        for name, text, _ in CLAIMS:
            print(f"  {name:<42} STATE must contain: {text!r}")
        print(f"\n{len(CLAIMS)} claims. Everything else in STATE is unverified prose.")
        return 0

    if not args.state:
        ap.error("--state is required (or use --list-claims)")
    state = sys.stdin.read() if args.state == "-" else Path(args.state).read_text(encoding="utf-8")

    repo = Path(args.repo).expanduser() if args.repo else None
    ip = Path(args.ip).expanduser() if args.ip else None

    print(f"check_state.py -- {len(state.splitlines())} lines of STATE")
    rep = run_checks(state, repo, ip)
    print_coverage()

    print(f"\n{rep.passes} passed, {len(rep.fails)} failed, "
          f"{len(rep.warns)} warned, {len(rep.skips)} skipped")
    if rep.fails:
        print("\nFAILURES:")
        for f in rep.fails:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
