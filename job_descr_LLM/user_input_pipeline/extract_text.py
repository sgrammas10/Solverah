"""Extract resume text using local PDF/DOCX parsers."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from job_descr_LLM.parsers.docx_extract import parse_docx
from job_descr_LLM.parsers.pdf_extract import parse_pdf
from job_descr_LLM.parsers.types import ParsedDocument


@dataclass
class ExtractOptions:
    dataset_root: Path
    resume_dirname: str = "resumes"

    @property
    def intake_path(self) -> Path:
        return self.dataset_root / "intake.csv"

    @property
    def resume_dir(self) -> Path:
        return self.dataset_root / self.resume_dirname

    @property
    def raw_output(self) -> Path:
        return self.dataset_root / "resumes_raw.jsonl"


def _detect_extension(resume_key: object, resume_mime: str | None) -> str:
    if resume_key is None or pd.isna(resume_key):
        return ""
    resume_key_str = str(resume_key)
    suffix = Path(resume_key_str).suffix.lower()
    if suffix:
        return suffix
    if resume_mime == "application/pdf":
        return ".pdf"
    if resume_mime and "wordprocessingml" in resume_mime:
        return ".docx"
    return ""


def _choose_parser(file_path: Path) -> ParsedDocument:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(file_path)
    if suffix in {".doc", ".docx"}:
        return parse_docx(file_path)

    return ParsedDocument(text="", parser="unknown", error="No suitable parser")


def extract_resumes(options: ExtractOptions) -> None:
    df = pd.read_csv(options.intake_path)
    options.raw_output.parent.mkdir(parents=True, exist_ok=True)
    with options.raw_output.open("w", encoding="utf-8") as fh:
        for _, row in df.iterrows():
            submission_id = row["id"]
            resume_key = row["resume_key"]
            resume_mime = row.get("resume_mime")
            suffix = _detect_extension(resume_key, resume_mime)
            resume_path = options.resume_dir / f"{submission_id}{suffix}" if suffix else None
            if resume_path is None or not resume_path.exists():
                matches = list(options.resume_dir.glob(f"{submission_id}.*"))
                resume_path = matches[0] if matches else None
            if resume_path is None:
                resume_path = options.resume_dir / f"{submission_id}.bin"
            parsed = _choose_parser(resume_path)
            record = {
                "id": submission_id,
                "resume_key": resume_key,
                "resume_mime": resume_mime,
                "state": row.get("state"),
                "created_at": row.get("created_at"),
                "parser": parsed.parser,
                "error": parsed.error,
                "text": parsed.text,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            }
            fh.write(json.dumps(record) + "\n")


def extract_from_env(version: str = "v1") -> None:
    dataset_root = Path("datasets") / version
    options = ExtractOptions(dataset_root=dataset_root)
    extract_resumes(options)


if __name__ == "__main__":
    extract_from_env()
