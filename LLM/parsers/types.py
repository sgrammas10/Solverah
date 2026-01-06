"""Shared parser response types for resume extraction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedDocument:
    """Normalized representation of extracted resume text."""

    text: str
    parser: str
    error: Optional[str]
