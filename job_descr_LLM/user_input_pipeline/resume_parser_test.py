"""
Resume parser regression tester.

Reads datasets/<version>/resumes_clean.jsonl, parses each resume, and writes
datasets/<version>/resume_parser_expected.jsonl with expected + actual outputs.
Paths are resolved relative to the repo root so it can be run from any cwd.

Usage:
  python resume_parser_test.py --version v1
  python resume_parser_test.py --version v1 --limit 50
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

def resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


REPO_ROOT = resolve_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from job_descr_LLM.user_input_pipeline.resume_parser import parse_resume  # noqa: E402


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_intake_ids(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing intake file: {path}")
    ids: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            row_id = (row.get("id") or "").strip()
            if row_id:
                ids.add(row_id)
    return ids


def index_by_id(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        row_id = row.get("id")
        if row_id is None:
            continue
        indexed[str(row_id)] = row
    return indexed


def compare_expected(expected: Dict[str, Any], actual: Dict[str, Any]) -> Tuple[bool, List[str]]:
    mismatches: List[str] = []
    for key, expected_value in expected.items():
        if key not in actual or actual[key] != expected_value:
            mismatches.append(key)
    return (len(mismatches) == 0, mismatches)


def build_output_row(
    record: Dict[str, Any],
    existing: Dict[str, Any] | None,
    actual: Dict[str, Any],
    matches: bool | None,
    mismatches: List[str] | None,
) -> Dict[str, Any]:
    base: Dict[str, Any] = dict(existing or {})
    expected = base.get("expected")
    if not isinstance(expected, dict):
        expected = {}
    base.update(
        {
            "id": record.get("id"),
            "resume_key": record.get("resume_key"),
            "state": record.get("state"),
            "expected": expected,
            "actual": actual,
            "matches": matches,
            "mismatches": mismatches,
        }
    )
    return base


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1", help="Dataset version folder name (default: v1)")
    parser.add_argument("--datasets-root", default="datasets", help="Root datasets folder (default: datasets)")
    parser.add_argument("--expected-file", default="resume_parser_expected.jsonl", help="Expected/actual JSONL file name")
    parser.add_argument("--limit", type=int, default=None, help="Optional cap on number of resumes to test")
    args = parser.parse_args()

    repo_root = resolve_repo_root()
    datasets_root = resolve_path(repo_root, args.datasets_root)
    dataset_root = datasets_root / args.version
    clean_path = dataset_root / "resumes_clean.jsonl"
    intake_path = dataset_root / "intake.csv"
    expected_path = dataset_root / args.expected_file

    if not clean_path.exists():
        print(f"[ERROR] Missing clean resumes file: {clean_path}")
        return 1
    if not intake_path.exists():
        print(f"[ERROR] Missing intake file: {intake_path}")
        return 1

    allowed_ids = load_intake_ids(intake_path)
    expected_rows = load_jsonl(expected_path)
    expected_index = index_by_id(expected_rows)

    output_rows: List[Dict[str, Any]] = []
    total = 0
    with_expected = 0
    matched = 0
    mismatched = 0
    skipped = 0

    with clean_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if args.limit is not None and total >= args.limit:
                break
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            record_id = record.get("id")
            if record_id is None:
                continue

            if str(record_id) not in allowed_ids:
                continue

            total += 1
            actual = parse_resume(record.get("text", ""))
            existing = expected_index.get(str(record_id))
            expected = existing.get("expected", {}) if existing else {}
            if not isinstance(expected, dict):
                expected = {}

            if expected:
                with_expected += 1
                is_match, mismatch_keys = compare_expected(expected, actual)
                if is_match:
                    matched += 1
                    print(f"[MATCH] id={record_id} resume_key={record.get('resume_key')}")
                else:
                    mismatched += 1
                    mismatch_str = ", ".join(mismatch_keys)
                    print(f"[MISMATCH] id={record_id} resume_key={record.get('resume_key')} fields={mismatch_str}")
                output_rows.append(
                    build_output_row(record, existing, actual, is_match, mismatch_keys)
                )
            else:
                skipped += 1
                print(f"[SKIP] id={record_id} resume_key={record.get('resume_key')} (no expected output)")
                output_rows.append(
                    build_output_row(record, existing, actual, None, None)
                )

    # Preserve any expected entries that no longer exist in resumes_clean.jsonl
    seen_ids = {str(row.get("id")) for row in output_rows if row.get("id") is not None}
    for row in expected_rows:
        row_id = row.get("id")
        if row_id is None:
            continue
        if str(row_id) not in seen_ids:
            output_rows.append(row)

    write_jsonl(expected_path, output_rows)

    print()
    print("Resume parser regression summary")
    print(f"  total resumes:    {total}")
    print(f"  with expected:    {with_expected}")
    print(f"  matched:          {matched}")
    print(f"  mismatched:       {mismatched}")
    print(f"  skipped:          {skipped}")
    print(f"  output file:      {expected_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
