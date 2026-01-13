"""Normalization and categorization helpers for JD extraction."""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

SKILL_ALIASES = {
    "ms excel": "Microsoft Excel",
    "excel": "Excel",
    "ms word": "Microsoft Word",
    "word": "Word",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "c sharp": "C#",
    "c#": "C#",
    "c++": "C++",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "sql": "SQL",
}

CATEGORY_RULES: List[Tuple[str, re.Pattern[str]]] = [
    (
        "Tools & Platforms",
        re.compile(
            r"\b(aws|gcp|azure|docker|kubernetes|git|linux|windows|jira|snowflake|tableau|power bi|spark)\b",
            re.I,
        ),
    ),
    (
        "Soft Skills",
        re.compile(r"\b(communication|collaboration|teamwork|leadership|stakeholder|problem[- ]solving)\b", re.I),
    ),
    (
        "Compliance & Regulations",
        re.compile(r"\b(hipaa|sox|pci|gdpr|soc 2|ferpa|itil)\b", re.I),
    ),
    (
        "Domain Knowledge",
        re.compile(r"\b(healthcare|finance|insurance|retail|logistics|manufacturing|education)\b", re.I),
    ),
]


WORD_CLEAN = re.compile(r"[^\w+#.&/\- ]+")


def normalize_skill(skill: str) -> str:
    cleaned = WORD_CLEAN.sub("", skill).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""
    alias = SKILL_ALIASES.get(cleaned.lower())
    return alias or cleaned


def dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        key = item.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def categorize_skills(skills: Iterable[str]) -> Dict[str, List[str]]:
    categorized: Dict[str, List[str]] = {}
    for skill in skills:
        added = False
        for category, pattern in CATEGORY_RULES:
            if pattern.search(skill):
                categorized.setdefault(category, []).append(skill)
                added = True
                break
        if not added:
            categorized.setdefault("Technical Skills", []).append(skill)
    return categorized