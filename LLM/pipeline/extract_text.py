"""Extract resume text using Tika with pdf/docx fallbacks."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from LLM.parsers.docx_fallback import parse_docx
from LLM.parsers.pdf_fallback import parse_pdf
from LLM.parsers.tika_server import ParsedDocument, TikaServerClient


@dataclass
class ExtractOptions:
    dataset_root: Path
    tika_url: str = "http://localhost:9998/tika"
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


def _detect_extension(resume_key: str, resume_mime: str | None) -> str:
    suffix = Path(resume_key).suffix.lower()
    if suffix:
        return suffix
    if resume_mime == "application/pdf":
        return ".pdf"
    if resume_mime and "wordprocessingml" in resume_mime:
        return ".docx"
    return ""


def _choose_parser(file_path: Path, tika_client: TikaServerClient) -> ParsedDocument:
    tika_result = tika_client.parse(file_path)
    if tika_result.text:
        return tika_result

    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(file_path)
    if suffix in {".doc", ".docx"}:
        return parse_docx(file_path)

    return ParsedDocument(text="", parser="unknown", error="No suitable parser")


def extract_resumes(options: ExtractOptions) -> None:
    tika_client = TikaServerClient(server_url=options.tika_url)
    df = pd.read_csv(options.intake_path)
    options.raw_output.parent.mkdir(parents=True, exist_ok=True)
    with options.raw_output.open("w", encoding="utf-8") as fh:
        for _, row in df.iterrows():
            submission_id = row["id"]
            resume_key = row["resume_key"]
            resume_mime = row.get("resume_mime")
            suffix = _detect_extension(resume_key, resume_mime) or ".bin"
            resume_path = options.resume_dir / f"{submission_id}{suffix}"
            parsed = _choose_parser(resume_path, tika_client)
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


def extract_from_env(version: str = "v1", tika_url: str | None = None) -> None:
    dataset_root = Path("datasets") / version
    options = ExtractOptions(dataset_root=dataset_root, tika_url=tika_url or "http://localhost:9998/tika")
    extract_resumes(options)


if __name__ == "__main__":
    extract_from_env()