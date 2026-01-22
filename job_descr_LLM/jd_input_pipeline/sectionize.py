"""Section detection for job descriptions."""
from __future__ import annotations

import re
from typing import Dict, Iterable, List

SECTION_PATTERNS = {
    "responsibilities": re.compile(r"^(responsibilities|what you will do|duties|role)\b", re.I),
    "requirements": re.compile(r"^(requirements|required qualifications|must have)\b", re.I),
    "qualifications": re.compile(r"^(qualifications|minimum qualifications)\b", re.I),
    "preferred": re.compile(r"^(preferred qualifications|preferred|nice to have)\b", re.I),
    "education": re.compile(r"^education\b", re.I),
    "certifications": re.compile(r"^(certifications?|licensure|licenses?)\b", re.I),
    "benefits": re.compile(r"^benefits\b", re.I),
    "about": re.compile(r"^(about us|about the role|company|who we are)\b", re.I),
}


def detect_heading(line: str) -> str | None:
    stripped = line.strip().rstrip(":")
    for name, pattern in SECTION_PATTERNS.items():
        if pattern.match(stripped):
            return name
    return None


def sectionize(lines: Iterable[str]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {"general": []}
    current = "general"
    for line in lines:
        if not line:
            continue
        heading = detect_heading(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections