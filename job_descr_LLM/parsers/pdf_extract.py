"""PDF fallback extraction using pdfminer.six."""
from __future__ import annotations

import logging
from pathlib import Path

from pdfminer.high_level import extract_text
from pypdf import PdfReader

from job_descr_LLM.parsers.types import ParsedDocument

logger = logging.getLogger(__name__)


def _resolve_case_insensitive_path(file_path: Path) -> Path:
    if file_path.exists():
        return file_path
    parent = file_path.parent
    target = file_path.name.lower()
    for candidate in parent.glob(f"{file_path.stem}.*"):
        if candidate.name.lower() == target:
            return candidate
    return file_path


def parse_pdf(file_path: Path) -> ParsedDocument:
    file_path = _resolve_case_insensitive_path(Path(file_path))
    try:
        text = extract_text(file_path)
        if not text:
            raise ValueError("PDF extraction returned no text")
        return ParsedDocument(text=text, parser="pdfminer", error=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF fallback failed for %s: %s", file_path, exc)

    try:
        reader = PdfReader(str(file_path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n".join(pages).strip()
        if not text:
            raise ValueError("PyPDF extraction returned no text")
        return ParsedDocument(text=text, parser="pypdf", error=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PyPDF fallback failed for %s: %s", file_path, exc)
        return ParsedDocument(
            text="",
            parser="pypdf",
            error=f"PDF extraction returned no text (pdfminer, pypdf): {exc}",
        )
