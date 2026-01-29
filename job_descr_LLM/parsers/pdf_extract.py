"""PDF fallback extraction using pdfminer.six."""
from __future__ import annotations

import logging
from pathlib import Path

from pdfminer.high_level import extract_text

from job_descr_LLM.parsers.types import ParsedDocument

logger = logging.getLogger(__name__)


def parse_pdf(file_path: Path) -> ParsedDocument:
    file_path = Path(file_path)
    try:
        text = extract_text(file_path)
        if not text:
            raise ValueError("PDF extraction returned no text")
        return ParsedDocument(text=text, parser="pdfminer", error=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF fallback failed for %s: %s", file_path, exc)
        return ParsedDocument(text="", parser="pdfminer", error=str(exc))