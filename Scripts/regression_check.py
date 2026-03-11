"""Re-run the resume parser against all test data and show a delta from the previous run.

Designed for the tight edit-verify loop:
  1. Edit resume_parser.py
  2. Run this script
  3. See exactly what regressed vs improved vs unchanged
  4. Repeat

Usage:
  python scripts/regression_check.py
  python scripts/regression_check.py --version v1
  python scripts/regression_check.py --show-diffs          # print field diffs for all failures
  python scripts/regression_check.py --show-diffs --id 9995 9998  # diffs for specific IDs only
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path
from difflib import unified_diff
from typing import Any, Dict, List, Optional, Set

# ── force UTF-8 output on Windows ─────────────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DIV = "=" * 62
DIV_SM = "-" * 62


# ── helpers ────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def snapshot_matches(rows: List[Dict[str, Any]]) -> Dict[str, Optional[bool]]:
    """Return {str(id): matches} for every row that has an expected value."""
    return {
        str(r["id"]): r.get("matches")
        for r in rows
        if r.get("expected")
    }


def format_field_diff(expected: Any, actual: Any, field: str) -> str:
    exp_s = json.dumps(expected, indent=2, ensure_ascii=False)
    act_s = json.dumps(actual, indent=2, ensure_ascii=False)
    diff = list(unified_diff(
        exp_s.splitlines(), act_s.splitlines(),
        fromfile=f"expected.{field}", tofile=f"actual.{field}", lineterm="",
    ))
    return "\n".join(f"    {d}" for d in diff) if diff else ""


def print_row_diffs(row: Dict[str, Any]) -> None:
    expected = row.get("expected", {})
    actual = row.get("actual", {})
    mismatches = row.get("mismatches") or []
    for field in mismatches:
        diff = format_field_diff(expected.get(field), actual.get(field), field)
        if diff:
            print(f"  Field: {field}")
            print(diff)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default="v1", help="Dataset version (default: v1)")
    parser.add_argument("--show-diffs", action="store_true",
                        help="Print field-level diffs for all failing resumes")
    parser.add_argument("--id", nargs="+", dest="ids", metavar="ID",
                        help="Limit --show-diffs to specific IDs")
    args = parser.parse_args()

    expected_path = REPO_ROOT / "datasets" / args.version / "resume_parser_expected.jsonl"
    regress_script = REPO_ROOT / "job_descr_LLM" / "user_input_pipeline" / "resume_parser_test.py"

    if not expected_path.exists():
        print(f"[ERROR] No expected file found: {expected_path}")
        return 1
    if not regress_script.exists():
        print(f"[ERROR] Regression script not found: {regress_script}")
        return 1

    # ── 1. Snapshot current state (before re-run) ──────────────────────────────
    before_rows = load_jsonl(expected_path)
    before = snapshot_matches(before_rows)

    print(f"\n{DIV}")
    print(f"Regression check  (version: {args.version})")
    print(DIV)
    print(f"Before: {sum(1 for v in before.values() if v is True)} passing, "
          f"{sum(1 for v in before.values() if v is False)} failing, "
          f"{sum(1 for v in before.values() if v is None)} pending "
          f"({len(before)} total with expected)")

    # ── 2. Re-run the parser against all test data ─────────────────────────────
    print("\nRunning parser...")
    result = subprocess.run(
        [sys.executable, str(regress_script), "--version", args.version],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[WARN] Regression script exited with code {result.returncode}")
        if result.stderr.strip():
            print(result.stderr.strip())

    # ── 3. Load updated state ──────────────────────────────────────────────────
    after_rows = load_jsonl(expected_path)
    after_index: Dict[str, Dict[str, Any]] = {str(r["id"]): r for r in after_rows}
    after = snapshot_matches(after_rows)

    # ── 4. Compute delta ───────────────────────────────────────────────────────
    regressed: List[str] = []   # true  -> false
    fixed:     List[str] = []   # false -> true
    still_failing: List[str] = []
    still_passing: List[str] = []
    new_pending: List[str] = []

    all_ids = sorted(set(before) | set(after), key=lambda x: int(x) if x.isdigit() else x)

    for id_str in all_ids:
        b = before.get(id_str)
        a = after.get(id_str)
        if b is True and a is False:
            regressed.append(id_str)
        elif b is False and a is True:
            fixed.append(id_str)
        elif a is False:
            still_failing.append(id_str)
        elif a is True:
            still_passing.append(id_str)
        elif a is None:
            new_pending.append(id_str)

    # ── 5. Print summary ───────────────────────────────────────────────────────
    print(f"After:  {len(still_passing) + len(fixed)} passing, "
          f"{len(still_failing) + len(regressed)} failing\n")
    print(DIV_SM)

    if regressed:
        print(f"\n[REGRESSED]  {len(regressed)} resume(s) newly broken:")
        for id_str in regressed:
            row = after_index.get(id_str, {})
            fields = ", ".join(row.get("mismatches") or [])
            print(f"  id={id_str}  fields={fields}")
    else:
        print("\n[OK] No regressions.")

    if fixed:
        print(f"\n[FIXED]  {len(fixed)} resume(s) newly passing:")
        for id_str in fixed:
            print(f"  id={id_str}")

    if still_failing:
        print(f"\n[STILL FAILING]  {len(still_failing)} resume(s):")
        for id_str in still_failing:
            row = after_index.get(id_str, {})
            fields = ", ".join(row.get("mismatches") or [])
            print(f"  id={id_str}  fields={fields}")

    print(f"\n[PASSING]  {len(still_passing) + len(fixed)} / "
          f"{len(still_passing) + len(fixed) + len(still_failing) + len(regressed)}")

    # ── 6. Field diffs ─────────────────────────────────────────────────────────
    if args.show_diffs:
        focus_ids: Set[str] = set(args.ids) if args.ids else set(still_failing + regressed)
        if focus_ids:
            print(f"\n{DIV}")
            print("Field diffs")
            print(DIV)
            for id_str in sorted(focus_ids, key=lambda x: int(x) if x.isdigit() else x):
                row = after_index.get(id_str)
                if not row or not row.get("mismatches"):
                    continue
                fields = ", ".join(row["mismatches"])
                print(f"\nid={id_str}  mismatches: {fields}")
                print(DIV_SM)
                print_row_diffs(row)

    # ── 7. Agent prompt (only if there are failures) ───────────────────────────
    if regressed or still_failing:
        failing_ids = [str(i) for i in (regressed + still_failing)]
        print(f"""
{DIV}
NEXT: Paste into Claude Code to diagnose and fix failures
{DIV}

Use two parallel subagents:

Agent A: Read datasets/v1/resume_parser_expected.jsonl and for these
failing IDs: {", ".join(failing_ids)}
Extract the mismatching fields and the delta between expected and
actual for each. Identify if the same field is failing across multiple
IDs (pattern) or if each failure is unique.

Agent B: Read job_descr_LLM/user_input_pipeline/resume_parser.py and
find the exact functions + line numbers responsible for the fields
that Agent A identified as failing.

After both finish: cross-reference the patterns with the code, then
propose the minimum targeted edits to resume_parser.py that fix the
failures without breaking the {len(still_passing) + len(fixed)} currently passing resumes.
{DIV}
""")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
