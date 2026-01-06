#!/usr/bin/env python3
"""
pipeline_test.py

Interactive, step-by-step smoke test runner for your pipeline.
It runs one stage at a time and PAUSES so you can inspect outputs/logs,
then continue to the next stage.

How it works:
- Loads your scripts directly from file paths (no package/import headaches).
- Executes stages in this order:
    1) export_intake.py      -> intake.csv
    2) download_resumes.py   -> datasets/<version>/resumes/*
    3) extract_text.py       -> resumes_raw.jsonl
    4) clean_text.py         -> resumes_clean.jsonl
    5) build_model_inputs.py -> model_inputs.jsonl

Usage examples:
  python pipeline_test.py --version v1
  python pipeline_test.py --version v1 --steps export,download,extract
  python pipeline_test.py --version v1 --tika-url http://127.0.0.1:9998/tika  # force fallback if Tika down
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../Solverah
sys.path.insert(0, str(REPO_ROOT))

# --------- CONFIG: point these at where the scripts live in your repo ----------
# If you put this file in the same folder as the scripts, these defaults work.
DEFAULT_SCRIPT_PATHS = {
    "export": Path("export_intake.py"),
    "download": Path("download_resumes.py"),
    "extract": Path("extract_text.py"),
    "clean": Path("clean_text.py"),
    "build": Path("build_model_inputs.py"),
}


# --------- Utilities ----------
def load_module_from_path(name: str, path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Cannot find {name} script at: {path.resolve()}")
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module spec for {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def prompt_continue(msg: str) -> None:
    print()
    print("=" * 88)
    print(msg)
    print("=" * 88)
    input("Press ENTER to continue (Ctrl+C to stop)...")


def read_jsonl(path: Path, limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
            if i + 1 >= limit:
                break
    return out


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    # subtract header if present
    return max(0, len(rows) - 1)


def list_files(dir_path: Path, max_items: int = 10) -> List[str]:
    if not dir_path.exists():
        return []
    files = [p for p in dir_path.rglob("*") if p.is_file()]
    files_sorted = sorted(files, key=lambda p: str(p))
    return [str(p) for p in files_sorted[:max_items]]


def require_env(keys: List[str], stage: str) -> None:
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        print(f"\n[WARN] Missing env vars for stage '{stage}': {', '.join(missing)}")
        print("      You can still continue if you intend to skip this stage or set them later.")
        print("      To set in PowerShell (example):")
        print('        $env:DATABASE_URL="postgres://..."')
        print("      Or in bash:")
        print('        export DATABASE_URL="postgres://..."')


@dataclass
class Paths:
    datasets_root: Path
    version: str

    @property
    def version_dir(self) -> Path:
        return self.datasets_root / self.version

    @property
    def intake_csv(self) -> Path:
        return self.version_dir / "intake.csv"

    @property
    def resumes_dir(self) -> Path:
        return self.version_dir / "resumes"

    @property
    def raw_jsonl(self) -> Path:
        return self.version_dir / "resumes_raw.jsonl"

    @property
    def clean_jsonl(self) -> Path:
        return self.version_dir / "resumes_clean.jsonl"

    @property
    def model_inputs_jsonl(self) -> Path:
        return self.version_dir / "model_inputs.jsonl"


# --------- Stage runners (call your existing functions if present) ----------
def run_export_intake(mod, p: Paths) -> None:
    """
    Expected: export_intake.py defines export_intake(dataset_version=...).
    """
    func = getattr(mod, "export_intake", None)
    if not callable(func):
        raise AttributeError("export_intake.py must define a callable export_intake(dataset_version=...)")
    func(dataset_version=p.version)

    if not p.intake_csv.exists():
        raise RuntimeError(f"export stage did not produce {p.intake_csv}")
    print(f"[OK] Wrote: {p.intake_csv} ({count_csv_rows(p.intake_csv)} rows)")


def run_download_resumes(mod, p: Paths) -> None:
    """
    Expected: download_resumes.py defines download_resumes(dataset_version=...).
    """
    func = getattr(mod, "download_resumes", None)
    if not callable(func):
        raise AttributeError("download_resumes.py must define a callable download_resumes(dataset_version=...)")
    func(dataset_version=p.version)

    if not p.resumes_dir.exists():
        raise RuntimeError(f"download stage did not create resumes dir: {p.resumes_dir}")
    sample = list_files(p.resumes_dir, max_items=10)
    if not sample:
        print("[WARN] Resumes directory exists but is empty. Check intake.csv resume_key values and R2 access.")
    else:
        print(f"[OK] Downloaded files (showing up to 10):")
        for s in sample:
            print(f"  - {s}")


def run_extract_text(mod, p: Paths, tika_url: Optional[str]) -> None:
    """
    Expected: extract_text.py defines extract_from_env(dataset_version, tika_url).
    """
    func = getattr(mod, "extract_from_env", None)
    if not callable(func):
        raise AttributeError("extract_text.py must define a callable extract_from_env(dataset_version, tika_url)")
    func(dataset_version=p.version, tika_url=tika_url)

    if not p.raw_jsonl.exists():
        raise RuntimeError(f"extract stage did not produce {p.raw_jsonl}")
    n = count_jsonl(p.raw_jsonl)
    print(f"[OK] Wrote: {p.raw_jsonl} ({n} lines)")
    print("[INFO] Sample rows:")
    for row in read_jsonl(p.raw_jsonl, limit=3):
        print(f"  - id={row.get('id')} parser={row.get('parser')} error={bool(row.get('error'))} text_len={len((row.get('text') or ''))}")


def run_clean_text(mod, p: Paths) -> None:
    """
    Expected: clean_text.py defines clean_from_env(dataset_version).
    """
    func = getattr(mod, "clean_from_env", None)
    if not callable(func):
        raise AttributeError("clean_text.py must define a callable clean_from_env(dataset_version)")
    func(dataset_version=p.version)

    if not p.clean_jsonl.exists():
        raise RuntimeError(f"clean stage did not produce {p.clean_jsonl}")
    n = count_jsonl(p.clean_jsonl)
    print(f"[OK] Wrote: {p.clean_jsonl} ({n} lines)")
    print("[INFO] Sample rows:")
    for row in read_jsonl(p.clean_jsonl, limit=3):
        print(f"  - id={row.get('id')} text_len={len((row.get('text') or ''))}")


def run_build_inputs(mod, p: Paths) -> None:
    """
    Expected: build_model_inputs.py defines build_from_env(dataset_version).
    """
    func = getattr(mod, "build_from_env", None)
    if not callable(func):
        raise AttributeError("build_model_inputs.py must define a callable build_from_env(dataset_version)")
    func(dataset_version=p.version)

    if not p.model_inputs_jsonl.exists():
        raise RuntimeError(f"build stage did not produce {p.model_inputs_jsonl}")
    n = count_jsonl(p.model_inputs_jsonl)
    print(f"[OK] Wrote: {p.model_inputs_jsonl} ({n} lines)")
    print("[INFO] Sample rows (schema check):")
    for row in read_jsonl(p.model_inputs_jsonl, limit=3):
        keys = sorted(list(row.keys()))
        print(f"  - keys={keys}  id={row.get('id')}  text_len={len((row.get('text') or ''))}")


# --------- Main ----------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Dataset version folder name (e.g., v1)")
    parser.add_argument(
        "--datasets-root",
        default="datasets",
        help="Root datasets folder (default: datasets)",
    )
    parser.add_argument(
        "--steps",
        default="export,download,extract,clean,build",
        help="Comma-separated steps: export,download,extract,clean,build",
    )
    parser.add_argument(
        "--tika-url",
        default=os.getenv("TIKA_URL", None),
        help="Tika URL (e.g., http://127.0.0.1:9998/tika). If unset, uses env TIKA_URL or script default.",
    )
    parser.add_argument(
        "--script-dir",
        default=".",
        help="Directory where your pipeline scripts live (default: current directory).",
    )
    args = parser.parse_args()

    script_dir = Path(args.script_dir).resolve()
    scripts = {k: (script_dir / v) for k, v in DEFAULT_SCRIPT_PATHS.items()}
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]

    p = Paths(datasets_root=Path(args.datasets_root), version=args.version)
    p.version_dir.mkdir(parents=True, exist_ok=True)

    print("\nPipeline smoke test")
    print(f"  version:       {p.version}")
    print(f"  datasets root: {p.datasets_root.resolve()}")
    print(f"  version dir:   {p.version_dir.resolve()}")
    print(f"  steps:         {steps}")
    print(f"  tika-url:      {args.tika_url}")

    # Load modules only for steps that will run
    modules: Dict[str, Any] = {}

    if "export" in steps:
        require_env(["DATABASE_URL"], "export")
        modules["export"] = load_module_from_path("export_intake", scripts["export"])
        prompt_continue(
            "STEP 1: export_intake\n"
            f"- Will write: {p.intake_csv}\n"
            "- Check DB connectivity and output columns when it finishes."
        )
        run_export_intake(modules["export"], p)

    if "download" in steps:
        require_env(["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"], "download")
        modules["download"] = load_module_from_path("download_resumes", scripts["download"])
        prompt_continue(
            "STEP 2: download_resumes\n"
            f"- Requires: {p.intake_csv}\n"
            f"- Will create/populate: {p.resumes_dir}\n"
            "- After it runs, spot-check a couple resumes exist and open correctly."
        )
        run_download_resumes(modules["download"], p)

    if "extract" in steps:
        modules["extract"] = load_module_from_path("extract_text", scripts["extract"])
        prompt_continue(
            "STEP 3: extract_text\n"
            f"- Requires: {p.intake_csv} and resume files in {p.resumes_dir}\n"
            f"- Will write: {p.raw_jsonl}\n"
            "- After it runs, open resumes_raw.jsonl and check parser/error fields and text quality."
        )
        run_extract_text(modules["extract"], p, args.tika_url)

    if "clean" in steps:
        modules["clean"] = load_module_from_path("clean_text", scripts["clean"])
        prompt_continue(
            "STEP 4: clean_text\n"
            f"- Requires: {p.raw_jsonl}\n"
            f"- Will write: {p.clean_jsonl}\n"
            "- After it runs, verify text normalization didn’t destroy section breaks."
        )
        run_clean_text(modules["clean"], p)

    if "build" in steps:
        modules["build"] = load_module_from_path("build_model_inputs", scripts["build"])
        prompt_continue(
            "STEP 5: build_model_inputs\n"
            f"- Requires: {p.clean_jsonl}\n"
            f"- Will write: {p.model_inputs_jsonl}\n"
            "- After it runs, verify schema matches what your ML step expects."
        )
        run_build_inputs(modules["build"], p)

    print("\nAll requested steps completed.")
    print("Quick artifact summary:")
    print(f"  intake.csv rows:          {count_csv_rows(p.intake_csv)}")
    print(f"  resumes dir exists:       {p.resumes_dir.exists()}")
    print(f"  resumes_raw.jsonl lines:  {count_jsonl(p.raw_jsonl)}")
    print(f"  resumes_clean.jsonl lines:{count_jsonl(p.clean_jsonl)}")
    print(f"  model_inputs.jsonl lines: {count_jsonl(p.model_inputs_jsonl)}")

    return 0


if __name__ == "__main__":
    DATASET_VERSION = "v1"

    # ------------------------------------------------------------------
    # STEP 1 — Export intake data from Postgres → datasets/v1/intake.csv
    # ------------------------------------------------------------------
    # Requires: DATABASE_URL
    from export_intake import export_from_env
    # export_intake(version=DATASET_VERSION)


    # ------------------------------------------------------------------
    # STEP 2 — Download resumes from R2 → datasets/v1/resumes/*
    # ------------------------------------------------------------------
    # Requires: R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
    from download_resumes import download_from_env
    # download_resumes(version=DATASET_VERSION)


    # ------------------------------------------------------------------
    # STEP 3 — Extract raw text (Tika → PDF/DOCX fallback)
    # ------------------------------------------------------------------
    # Optional: set tika_url to a dead URL to force fallback testing
    from extract_text import extract_from_env
    extract_from_env(
        version=DATASET_VERSION,
        tika_url="http://127.0.0.1:9998/tika"  # or None
    )


    # ------------------------------------------------------------------
    # STEP 4 — Clean / normalize extracted text
    # ------------------------------------------------------------------
    from clean_text import clean_from_env
    clean_from_env(version=DATASET_VERSION)


    # ------------------------------------------------------------------
    # STEP 5 — Build ML-ready model inputs → model_inputs.jsonl
    # ------------------------------------------------------------------
    from build_model_inputs import build_from_env
    build_from_env(version=DATASET_VERSION)
