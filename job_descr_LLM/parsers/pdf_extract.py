"""PDF fallback extraction using multiple parsers."""
from __future__ import annotations

import logging
from pathlib import Path

import fitz
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


def _extract_with_pymupdf(file_path: Path) -> ParsedDocument:
    doc = fitz.open(file_path)
    pages = []
    for page in doc:
        blocks = page.get_text("blocks") or []
        block_lines = []
        for block in sorted(blocks, key=lambda b: (b[1], b[0])):
            text = (block[4] or "").strip()
            if text:
                block_lines.append(text)
        if block_lines:
            pages.append("\n".join(block_lines))
    text = "\n".join(pages).strip()
    if not text:
        raise ValueError("PyMuPDF extraction returned no text")
    return ParsedDocument(text=text, parser="pymupdf", error=None)


def _extract_with_pypdf(file_path: Path) -> ParsedDocument:
    reader = PdfReader(str(file_path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages).strip()
    if not text:
        raise ValueError("PyPDF extraction returned no text")
    return ParsedDocument(text=text, parser="pypdf", error=None)


def _extract_with_pdfminer(file_path: Path) -> ParsedDocument:
    text = extract_text(file_path)
    if not text:
        raise ValueError("PDFMiner extraction returned no text")
    return ParsedDocument(text=text, parser="pdfminer", error=None)


def parse_pdf(file_path: Path) -> ParsedDocument:
    file_path = _resolve_case_insensitive_path(Path(file_path))
    last_error: Exception | None = None
    parser_order = ("pymupdf", "pypdf", "pdfminer")
    for parser_name in parser_order:
        try:
            if parser_name == "pymupdf":
                return _extract_with_pymupdf(file_path)
            if parser_name == "pypdf":
                return _extract_with_pypdf(file_path)
            if parser_name == "pdfminer":
                return _extract_with_pdfminer(file_path)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("%s failed for %s: %s", parser_name, file_path, exc)
    return ParsedDocument(
        text="",
        parser=parser_order[-1],
        error=(
            "PDF extraction returned no text (pymupdf, pypdf, pdfminer): "
            f"{last_error}"
        ),
    )
