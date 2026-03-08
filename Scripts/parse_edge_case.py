"""Parse a resume edge case, append to datasets, and run regression.

Usage:
  # Just parse and show output (read-only, no files modified):
  python scripts/parse_edge_case.py path/to/resume.pdf

  # Parse and compare to an expected JSON:
  python scripts/parse_edge_case.py path/to/resume.pdf --expected expected.json

  # Parse, append to all dataset files, then run regression:
  python scripts/parse_edge_case.py path/to/resume.pdf --state CA --append

  # Full flow with expected comparison:
  python scripts/parse_edge_case.py path/to/resume.pdf --expected expected.json --state TX --append
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ── force UTF-8 output on Windows ─────────────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── repo root on sys.path ──────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from job_descr_LLM.parsers.pdf_extract import parse_pdf          # noqa: E402
from job_descr_LLM.parsers.docx_extract import parse_docx        # noqa: E402
from job_descr_LLM.user_input_pipeline.resume_parser import parse_resume  # noqa: E402

DIVIDER = "=" * 62


# ── file helpers ───────────────────────────────────────────────────────────────

def extract_text(path: Path) -> Tuple[str, str, str | None]:
    """Return (text, parser_name, error). Supports PDF, DOCX, and plain text."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        result = parse_pdf(path)
        return result.text, result.parser, result.error
    if suffix in {".doc", ".docx"}:
        result = parse_docx(path)
        return result.text, result.parser, result.error
    if suffix in {".txt", ""}:
        return path.read_text(encoding="utf-8"), "plaintext", None
    return "", "unknown", f"Unsupported file type: {suffix}"


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


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def next_id(intake_path: Path) -> int:
    """Return max existing ID + 1, or 1 if none exist."""
    if not intake_path.exists():
        return 1
    max_id = 0
    with intake_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                max_id = max(max_id, int(row["id"]))
            except (KeyError, ValueError):
                pass
    return max_id + 1


def append_intake(intake_path: Path, record_id: int, state: str) -> None:
    write_header = not intake_path.exists()
    with intake_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if write_header:
            writer.writerow(["id", "resume_key", "state"])
        writer.writerow([record_id, record_id, f" {state.strip()}"])


# ── diff helpers ───────────────────────────────────────────────────────────────

def compare(expected: Dict[str, Any], actual: Dict[str, Any]) -> Tuple[bool, List[str]]:
    mismatches = [k for k, v in expected.items() if k not in actual or actual[k] != v]
    return (len(mismatches) == 0, mismatches)


def format_diff(expected: Dict[str, Any], actual: Dict[str, Any], keys: List[str]) -> str:
    lines = []
    for key in keys:
        exp_val = json.dumps(expected.get(key, "<missing>"), indent=2, ensure_ascii=False)
        act_val = json.dumps(actual.get(key, "<missing>"), indent=2, ensure_ascii=False)
        diff = list(unified_diff(
            exp_val.splitlines(), act_val.splitlines(),
            fromfile=f"expected.{key}", tofile=f"actual.{key}", lineterm="",
        ))
        if diff:
            lines.append(f"\nField: {key}")
            lines.extend(f"  {d}" for d in diff)
    return "\n".join(lines)


# ── agent prompt ───────────────────────────────────────────────────────────────

AGENT_PROMPT = """
{divider}
NEXT: Paste this into Claude Code to analyze and fix failures
{divider}

Use two parallel subagents:

Agent A: Read datasets/v1/resume_parser_expected.jsonl and find all
records where "matches" is false. For each failing record extract:
- the id
- which fields are in "mismatches"
- the delta between expected and actual for those fields
Then summarize: which fields fail most often and what patterns you see
(e.g. wrong company name, missing skills category, truncated bullets).

Agent B: Read job_descr_LLM/user_input_pipeline/resume_parser.py and
identify the exact functions and line numbers responsible for parsing
each of these fields: skills, skills_by_category, experience
(title / company / duration / impact_bullets), education,
certifications, years_experience, projects, clearances_or_work_auth.

After both finish: cross-reference Agent A's failing fields with Agent
B's code locations, then propose the minimum targeted edits to
resume_parser.py that would fix the observed failures.
{divider}
""".strip()


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("resume", type=Path, help="Path to resume file (PDF, DOCX, or TXT)")
    parser.add_argument("--expected", type=Path, default=None,
                        help="Optional JSON file with the expected parse output")
    parser.add_argument("--state", default="NA",
                        help="Two-letter state code for this resume (required when --append)")
    parser.add_argument("--id", type=int, default=None, dest="record_id",
                        help="Override the auto-generated ID")
    parser.add_argument("--version", default="v1",
                        help="Dataset version folder (default: v1)")
    parser.add_argument("--append", action="store_true",
                        help="Append this resume to all dataset files")
    parser.add_argument("--no-regress", action="store_true",
                        help="Skip the full regression run after appending")
    args = parser.parse_args()

    resume_path: Path = args.resume.resolve()
    if not resume_path.exists():
        print(f"[ERROR] File not found: {resume_path}")
        return 1

    dataset_root = REPO_ROOT / "datasets" / args.version

    # ── 1. Extract text ────────────────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print(f"Resume:  {resume_path.name}")
    print(f"Version: {args.version}")
    print(DIVIDER)

    text, parser_name, extract_error = extract_text(resume_path)
    if extract_error:
        print(f"[WARN] Text extraction issue: {extract_error}")
    if not text.strip():
        print("[ERROR] No text extracted — check the file.")
        return 1
    print(f"Extracted {len(text)} chars via {parser_name}\n")

    # ── 2. Parse ───────────────────────────────────────────────────────────────
    actual = parse_resume(text)
    print("-- Parsed Output ----------------------------------------------")
    print(json.dumps(actual, indent=2, ensure_ascii=False))

    # ── 3. Compare to expected (if provided) ───────────────────────────────────
    expected: Dict[str, Any] = {}
    is_match: bool | None = None
    mismatch_keys: List[str] = []

    if args.expected:
        if not args.expected.exists():
            print(f"\n[WARN] Expected file not found: {args.expected}")
        else:
            with args.expected.open("r", encoding="utf-8") as fh:
                expected = json.load(fh)
            is_match, mismatch_keys = compare(expected, actual)
            print("\n-- Comparison -------------------------------------------------")
            if is_match:
                print("[MATCH] Actual output matches expected.")
            else:
                print(f"[MISMATCH] {len(mismatch_keys)} field(s) differ: {', '.join(mismatch_keys)}")
                diff_output = format_diff(expected, actual, mismatch_keys)
                if diff_output:
                    print(diff_output)

    # ── 4. Append to datasets ──────────────────────────────────────────────────
    record_id: int | None = None
    if args.append:
        intake_path = dataset_root / "intake.csv"
        record_id = args.record_id if args.record_id is not None else next_id(intake_path)
        state = args.state.strip()

        # Copy resume file to datasets/v1/resumes/<id><suffix>
        resume_dir = dataset_root / "resumes"
        resume_dir.mkdir(parents=True, exist_ok=True)
        dest_resume = resume_dir / f"{record_id}{resume_path.suffix.lower()}"
        shutil.copy2(resume_path, dest_resume)

        # intake.csv
        append_intake(intake_path, record_id, state)

        # resumes_clean.jsonl
        clean_record = {
            "id": record_id,
            "resume_key": record_id,
            "resume_mime": None,
            "state": f" {state}",
            "created_at": None,
            "parser": parser_name,
            "error": extract_error,
            "text": text,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }
        append_jsonl(dataset_root / "resumes_clean.jsonl", clean_record)

        # resume_parser_expected.jsonl
        expected_record = {
            "id": record_id,
            "resume_key": record_id,
            "state": f" {state}",
            "expected": expected if expected else {},
            "actual": actual,
            "matches": is_match,
            "mismatches": mismatch_keys if mismatch_keys else [],
        }
        append_jsonl(dataset_root / "resume_parser_expected.jsonl", expected_record)

        # model_inputs.jsonl
        model_record = {
            "id": record_id,
            "text": text,
            "state": f" {state}",
            "resume_key": record_id,
            "dataset_version": args.version,
            **actual,
        }
        append_jsonl(dataset_root / "model_inputs.jsonl", model_record)

        print(f"\n-- Appended to datasets ({args.version}) ----------------------------")
        print(f"  ID:                     {record_id}")
        print(f"  intake.csv              {intake_path}")
        print(f"  resumes_clean.jsonl     appended")
        print(f"  resume_parser_expected  appended (matches={is_match})")
        print(f"  model_inputs.jsonl      appended")
        print(f"  resume copy:            {dest_resume}")

        # ── 5. Run full regression ─────────────────────────────────────────────
        if not args.no_regress:
            print(f"\n-- Regression ({args.version}) ---------------------------------")
            regress_script = REPO_ROOT / "job_descr_LLM" / "user_input_pipeline" / "resume_parser_test.py"
            result = subprocess.run(
                [sys.executable, str(regress_script), "--version", args.version],
                capture_output=True, text=True,
            )
            output = (result.stdout + result.stderr).strip()
            print(output if output else "(no output)")
            if result.returncode != 0:
                print(f"[WARN] Regression exited with code {result.returncode}")

    # ── 6. Agent prompt ────────────────────────────────────────────────────────
    if mismatch_keys or args.append:
        print(f"\n{AGENT_PROMPT.format(divider=DIVIDER)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
