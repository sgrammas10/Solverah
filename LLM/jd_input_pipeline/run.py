"""Batch runner for job description parsing."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .extract_requirements import extract_requirements
from .normalize import remove_boilerplate, split_lines
from .schema import JobDescriptionOutput
from .sectionize import sectionize
from .validate import validate_output

DATASET_PATH = Path("datasets/v1/jddata.csv")
OUTPUT_PATH = Path("datasets/v1/jd_parsed.jsonl")

ID_COLUMNS = ["id", "jd_id", "job_id"]
TEXT_COLUMNS = ["text", "job_description", "description", "jd_text"]


def detect_columns(headers: Iterable[str]) -> Tuple[str, str]:
    header_map = {h.lower().strip(): h for h in headers}
    id_column = next((header_map[h] for h in ID_COLUMNS if h in header_map), "")
    text_column = next((header_map[h] for h in TEXT_COLUMNS if h in header_map), "")
    if not id_column or not text_column:
        available = ", ".join(headers)
        raise ValueError(
            "Could not detect required columns. "
            f"Available headers: {available}"
        )
    return id_column, text_column


def parse_job_description(raw_text: str, record_id: int) -> JobDescriptionOutput:
    lines = remove_boilerplate(split_lines(raw_text))
    sections = sectionize(lines)
    (
        years,
        education,
        skills,
        skills_by_category,
        certifications,
        clearance,
        experience_blocks,
    ) = extract_requirements(sections)

    payload: Dict[str, object] = {
        "id": record_id,
        "text": raw_text.strip(),
        "years_experience": years,
        "education": education,
        "skills": skills,
        "skills_by_category": skills_by_category,
        "experience": experience_blocks,
        "projects": [],
        "certifications": certifications,
        "clearances_or_work_auth": clearance,
    }
    return validate_output(payload)


def parse_csv(path: Path = DATASET_PATH) -> List[JobDescriptionOutput]:
    if not path.exists():
        raise FileNotFoundError(f"Job description CSV not found at {path}")

    outputs: List[JobDescriptionOutput] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV must include headers")
        id_column, text_column = detect_columns(reader.fieldnames)
        for idx, row in enumerate(reader, start=1):
            raw_id = (row.get(id_column) or "").strip()
            raw_text = (row.get(text_column) or "").strip()
            if not raw_text:
                continue
            try:
                record_id = int(raw_id)
            except ValueError:
                record_id = idx
            outputs.append(parse_job_description(raw_text, record_id))
    return outputs


def write_jsonl(outputs: List[JobDescriptionOutput], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for obj in outputs:
            handle.write(json.dumps(obj, ensure_ascii=False))
            handle.write("\n")


def run() -> None:
    outputs = parse_csv()
    write_jsonl(outputs)


if __name__ == "__main__":
    run()