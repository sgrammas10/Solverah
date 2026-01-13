"""Helper for extracting text via an Apache Tika server."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class ParsedDocument:
    """Container for parsed resume text."""

    text: str
    parser: str
    error: Optional[str]


class TikaServerClient:
    """Lightweight client for sending files to an Apache Tika server."""

    def __init__(self, server_url: str = "http://localhost:9998/tika", timeout: int = 30) -> None:
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout

    def parse(self, file_path: Path) -> ParsedDocument:
        file_path = Path(file_path)
        try:
            with file_path.open("rb") as fh:
                response = requests.put(
                    self.server_url,
                    data=fh,
                    headers={"Accept": "text/plain"},
                    timeout=self.timeout,
                )
            response.raise_for_status()
            text = response.text or ""
            if not text.strip():
                raise ValueError("Tika returned empty text")
            return ParsedDocument(text=text, parser="tika", error=None)
        except Exception as exc:  # noqa: BLE001 - allow any failure to trigger fallbacks
            logger.warning("Tika extraction failed for %s: %s", file_path, exc)
            return ParsedDocument(text="", parser="tika", error=str(exc))