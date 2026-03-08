"""Use Claude to review model_inputs.jsonl entries that have no expected value yet.

For each un-reviewed entry, Claude reads the raw resume text alongside the parsed
output and flags any fields that look wrong, missing, or over-extracted.
You then choose to promote the (optionally corrected) output as the expected value
in resume_parser_expected.jsonl.

Usage:
  # Review all pending entries interactively:
  python scripts/review_model_inputs.py

  # Review specific IDs only:
  python scripts/review_model_inputs.py --id 9990 9989

  # Review without promoting (just see Claude's assessment):
  python scripts/review_model_inputs.py --no-promote

  # Non-interactive: auto-accept Claude's suggested expected for all pending:
  python scripts/review_model_inputs.py --auto-accept

Requires: ANTHROPIC_API_KEY in your .env or environment.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# ── force UTF-8 output on Windows ─────────────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv()

try:
    import anthropic
except ImportError:
    print("[ERROR] anthropic package not found. Run: pip install anthropic")
    sys.exit(1)

DIV = "=" * 62
DIV_SM = "-" * 62

# Fields the parser is responsible for — used to scope Claude's review
PARSED_FIELDS = [
    "years_experience",
    "education",
    "skills",
    "skills_by_category",
    "experience",
    "projects",
    "certifications",
    "clearances_or_work_auth",
]

REVIEW_PROMPT = """\
You are reviewing the output of a rule-based resume parser. Given the raw resume \
text and the parser's output, evaluate each field and identify any errors.

Raw resume text:
<resume>
{resume_text}
</resume>

Parser output (JSON):
<parsed>
{parsed_json}
</parsed>

For each field in the parsed output, answer:
1. Is it correct? (yes / partial / no)
2. If partial or no, what is wrong and what should it be?

Focus on these fields: years_experience, education, skills, skills_by_category, \
experience (title, company, duration, impact_bullets), projects, certifications, \
clearances_or_work_auth.

Then output a JSON block that represents the CORRECT expected value for this resume.
The JSON must contain only the fields listed above (no id, text, state, etc).
Wrap it in ```json ... ``` markers.

Be precise. If a field looks correct, keep it exactly as-is in the expected JSON.
If something is wrong, fix only that field.
"""


# ── file helpers ───────────────────────────────────────────────────────────────

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


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first ```json ... ``` block out of Claude's response."""
    import re
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    # fallback: try parsing the whole response as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parsed_fields_only(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: row[k] for k in PARSED_FIELDS if k in row}


# ── Claude review ──────────────────────────────────────────────────────────────

def call_claude_review(client: anthropic.Anthropic, resume_text: str,
                       parsed: Dict[str, Any]) -> str:
    prompt = REVIEW_PROMPT.format(
        resume_text=resume_text[:6000],  # cap to avoid huge tokens
        parsed_json=json.dumps(parsed, indent=2, ensure_ascii=False),
    )
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ── promote to expected ────────────────────────────────────────────────────────

def promote_expected(
    expected_path: Path,
    record_id: int,
    expected_value: Dict[str, Any],
    actual_value: Dict[str, Any],
) -> None:
    rows = load_jsonl(expected_path)
    updated = False
    for row in rows:
        if str(row.get("id")) == str(record_id):
            row["expected"] = expected_value
            row["actual"] = actual_value
            # recompute matches/mismatches
            mismatches = [k for k, v in expected_value.items()
                          if k not in actual_value or actual_value[k] != v]
            row["matches"] = len(mismatches) == 0
            row["mismatches"] = mismatches
            updated = True
            break
    if not updated:
        # entry doesn't exist yet — create it
        mismatches = [k for k, v in expected_value.items()
                      if k not in actual_value or actual_value[k] != v]
        rows.append({
            "id": record_id,
            "resume_key": record_id,
            "state": "",
            "expected": expected_value,
            "actual": actual_value,
            "matches": len(mismatches) == 0,
            "mismatches": mismatches,
        })
    write_jsonl(expected_path, rows)


# ── interactive prompt ─────────────────────────────────────────────────────────

def ask(prompt: str, options: str = "(y/n/e/s)") -> str:
    """Prompt user and return their choice (lowercase, stripped)."""
    while True:
        try:
            answer = input(f"\n{prompt} {options}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)
        if answer:
            return answer


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default="v1", help="Dataset version (default: v1)")
    parser.add_argument("--id", nargs="+", dest="ids", metavar="ID",
                        help="Review specific IDs only")
    parser.add_argument("--no-promote", action="store_true",
                        help="Show review only, do not write to resume_parser_expected.jsonl")
    parser.add_argument("--auto-accept", action="store_true",
                        help="Automatically accept Claude's suggested expected for all entries")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] ANTHROPIC_API_KEY not set. Add it to your .env file.")
        return 1

    client = anthropic.Anthropic(api_key=api_key)

    dataset_root = REPO_ROOT / "datasets" / args.version
    model_inputs_path = dataset_root / "model_inputs.jsonl"
    expected_path = dataset_root / "resume_parser_expected.jsonl"

    if not model_inputs_path.exists():
        print(f"[ERROR] Not found: {model_inputs_path}")
        return 1

    # ── find pending entries (no expected value yet) ───────────────────────────
    model_rows = load_jsonl(model_inputs_path)
    expected_rows = load_jsonl(expected_path)

    has_expected: Set[str] = {
        str(r["id"]) for r in expected_rows
        if r.get("expected") and isinstance(r["expected"], dict) and r["expected"]
    }

    filter_ids: Optional[Set[str]] = set(args.ids) if args.ids else None

    pending = [
        r for r in model_rows
        if str(r["id"]) not in has_expected
        and (filter_ids is None or str(r["id"]) in filter_ids)
    ]

    if not pending:
        print("\nNo pending entries found — all model_inputs have expected values.")
        if filter_ids:
            print(f"  (searched IDs: {', '.join(filter_ids)})")
        return 0

    print(f"\n{DIV}")
    print(f"Review model_inputs  (version: {args.version})")
    print(DIV)
    print(f"Pending (no expected): {len(pending)} entr{'y' if len(pending) == 1 else 'ies'}")
    if not args.auto_accept and not args.no_promote:
        print("\nFor each entry you will be shown Claude's review and can:")
        print("  y  - accept suggested expected as-is and promote")
        print("  e  - edit the suggested JSON in your editor first, then promote")
        print("  n  - skip (do not promote)")
        print("  s  - stop reviewing")

    promoted = 0
    skipped = 0

    for i, row in enumerate(pending, 1):
        record_id = row["id"]
        resume_text = row.get("text", "")
        parsed = parsed_fields_only(row)

        print(f"\n{DIV}")
        print(f"[{i}/{len(pending)}]  id={record_id}  state={row.get('state', '').strip()}")
        print(DIV_SM)

        # Show the parsed output compactly
        for field in PARSED_FIELDS:
            val = parsed.get(field)
            if isinstance(val, list):
                print(f"  {field}: [{len(val)} items]")
            elif isinstance(val, dict):
                print(f"  {field}: {{{', '.join(val.keys())}}}")
            else:
                preview = str(val)[:80] if val else "(empty)"
                print(f"  {field}: {preview}")

        print(f"\n{DIV_SM}")
        print("Calling Claude to review...")

        try:
            review_text = call_claude_review(client, resume_text, parsed)
        except Exception as e:
            print(f"[ERROR] Claude API call failed: {e}")
            skipped += 1
            continue

        print(f"\n{DIV_SM}")
        print("Claude's review:")
        print(DIV_SM)
        print(review_text)

        # Extract the suggested expected JSON
        suggested = extract_json_block(review_text)
        if suggested is None:
            print("\n[WARN] Could not extract a JSON block from Claude's response.")
            print("       You can still manually promote this entry.")

        if args.no_promote:
            continue

        if args.auto_accept:
            if suggested is not None:
                promote_expected(expected_path, record_id, suggested, parsed)
                print(f"\n[AUTO-ACCEPTED] id={record_id} promoted to expected.")
                promoted += 1
            else:
                print(f"\n[SKIPPED] id={record_id} — no JSON block to auto-accept.")
                skipped += 1
            continue

        # Interactive mode
        choice = ask(f"Promote id={record_id}?", "(y=accept / e=edit / n=skip / s=stop)")

        if choice == "s":
            print("Stopping.")
            break
        elif choice == "n":
            skipped += 1
            continue
        elif choice in ("y", "e"):
            if suggested is None:
                print("[WARN] No suggested JSON available — cannot promote.")
                skipped += 1
                continue

            if choice == "e":
                # Write to a temp file and open in editor
                import tempfile, subprocess as sp
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, encoding="utf-8"
                ) as tf:
                    json.dump(suggested, tf, indent=2, ensure_ascii=False)
                    tmp_path = tf.name

                editor = os.getenv("EDITOR", "notepad" if sys.platform == "win32" else "nano")
                sp.run([editor, tmp_path])

                try:
                    with open(tmp_path, "r", encoding="utf-8") as f:
                        suggested = json.load(f)
                    print("[OK] Using edited JSON.")
                except Exception as exc:
                    print(f"[ERROR] Could not read edited file: {exc}")
                    skipped += 1
                    continue
                finally:
                    os.unlink(tmp_path)

            promote_expected(expected_path, record_id, suggested, parsed)
            matches_str = "MATCH" if all(
                parsed.get(k) == v for k, v in suggested.items()
            ) else "MISMATCH"
            print(f"[PROMOTED] id={record_id} -> resume_parser_expected.jsonl  ({matches_str})")
            promoted += 1

    print(f"\n{DIV}")
    print(f"Done.  Promoted: {promoted}  Skipped: {skipped}")
    if promoted > 0 and not args.no_promote:
        print(f"\nRun regression to see how the parser fares against the new expected values:")
        print(f"  python scripts/regression_check.py")
    print(DIV)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
