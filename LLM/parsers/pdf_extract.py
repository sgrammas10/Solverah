"""PDF fallback extraction using pdfminer.six."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pdfminer.high_level import extract_text

logger = logging.getLogger(__name__)


@dataclass
class ParsedDocument:
    text: str
    parser: str
    error: Optional[str]


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