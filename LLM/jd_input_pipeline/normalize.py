"""Normalization helpers for job description parsing."""
from __future__ import annotations

import re
from typing import Iterable, List

BULLET_CHARS = {"·", "", "●", "•", "–", "—", "*", "•"}

BOILERPLATE_PATTERNS = [
    re.compile(r"equal opportunity employer", re.I),
    re.compile(r"eeo", re.I),
    re.compile(r"all qualified applicants", re.I),
    re.compile(r"reasonable accommodation", re.I),
    re.compile(r"veteran status", re.I),
    re.compile(r"disability", re.I),
    re.compile(r"genetic information", re.I),
    re.compile(r"gender identity", re.I),
    re.compile(r"sexual orientation", re.I),
    re.compile(r"pregnancy", re.I),
    re.compile(r"racial", re.I),
    re.compile(r"national origin", re.I),
]

WORK_AUTH_HINTS = re.compile(
    r"\b(us citizen|citizenship|authorized to work|work authorization|no sponsorship|sponsorship)\b",
    re.I,
)


def normalize_text(text: str) -> str:
    """Normalize bullets/dashes/whitespace for JD text."""
    replacements = {
        "·": "-",
        "": "-",
        "●": "-",
        "•": "-",
        "–": "-",
        "—": "-",
        "\t": " ",
        "\r": " ",
        "\f": " ",
    }
    for src, tgt in replacements.items():
        text = text.replace(src, tgt)

    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


def split_lines(text: str) -> List[str]:
    normalized = normalize_text(text)
    return [line.strip() for line in normalized.split("\n")]


def strip_bullet(line: str) -> str:
    return re.sub(r"^(?:[-*]\s+)+", "", line).strip()


def is_boilerplate_line(line: str) -> bool:
    if WORK_AUTH_HINTS.search(line):
        return False
    return any(pattern.search(line) for pattern in BOILERPLATE_PATTERNS)


def remove_boilerplate(lines: Iterable[str]) -> List[str]:
    """Remove obvious EEO boilerplate lines while preserving requirements."""
    cleaned: List[str] = []
    for line in lines:
        if not line.strip():
            continue
        if is_boilerplate_line(line):
            continue
        cleaned.append(line)
    return cleaned