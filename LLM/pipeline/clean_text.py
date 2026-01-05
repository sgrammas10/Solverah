"""Normalize raw resume text for downstream ML tasks."""
from __future__ import annotations

import json
import re
from pathlib import Path


def normalize_text(text: str) -> str:
    """Normalize whitespace while keeping section breaks intact."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in normalized.split("\n"):
        compact = re.sub(r"\s+", " ", line).strip()
        lines.append(compact)
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def clean_raw_resumes(dataset_root: Path) -> None:
    raw_path = dataset_root / "resumes_raw.jsonl"
    output_path = dataset_root / "resumes_clean.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with raw_path.open("r", encoding="utf-8") as raw_fh, output_path.open(
        "w", encoding="utf-8"
    ) as clean_fh:
        for line in raw_fh:
            record = json.loads(line)
            clean_text = normalize_text(record.get("text", ""))
            cleaned_record = {**record, "text": clean_text}
            clean_fh.write(json.dumps(cleaned_record) + "\n")


def clean_from_env(version: str = "v1") -> None:
    dataset_root = Path("datasets") / version
    clean_raw_resumes(dataset_root)


if __name__ == "__main__":
    clean_from_env()