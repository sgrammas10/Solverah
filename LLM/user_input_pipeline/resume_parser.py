"""Lightweight resume parser for normalized text.

This module extracts structured fields from normalized resume text using
heading-based section splitting and simple regex heuristics. It deliberately
avoids remote model calls so it can run deterministically within the
user_input_pipeline.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)

SECTION_ALIASES = {
    "education": "education",
    "experience": "experience",
    "work experience": "experience",
    "professional experience": "experience",
    "skills": "skills",
    "technical skills": "skills",
    "projects": "projects",
    "project experience": "projects",
    "certifications": "certifications",
    "certification": "certifications",
    "certs": "certifications",
    "clearance": "clearances_or_work_auth",
    "clearances": "clearances_or_work_auth",
    "work authorization": "clearances_or_work_auth",
    "authorization": "clearances_or_work_auth",
    "tools": "tools_platforms",
    "tools & platforms": "tools_platforms",
    "platforms": "tools_platforms",
    "technologies": "tools_platforms",
    "tech stack": "tools_platforms",
}


def _match_heading(line: str) -> str | None:
    normalized = line.strip().lower()
    normalized = re.sub(r":+$", "", normalized)
    return SECTION_ALIASES.get(normalized)


def _split_sections(text: str) -> Dict[str, str]:
    sections: Dict[str, List[str]] = {}
    current: str | None = None
    for line in text.split("\n"):
        heading = _match_heading(line)
        if heading:
            current = heading
            if current not in sections:
                sections[current] = []
            continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def _parse_years_experience(text: str) -> int | float | None:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs)\b", text, flags=re.IGNORECASE)
    numeric = [float(m) for m in matches]
    if not numeric:
        return None
    max_years = max(numeric)
    # prefer integers when possible
    return int(max_years) if max_years.is_integer() else max_years


def _split_list_section(section_text: str) -> List[str]:
    items: List[str] = []
    for line in section_text.split("\n"):
        line = re.sub(r"^[\-\*•]\s*", "", line).strip()
        if not line:
            continue
        parts = re.split(r",|;|\|", line)
        for part in parts:
            cleaned = part.strip()
            if cleaned:
                items.append(cleaned)
    return items


def _parse_experience(section_text: str) -> List[Dict[str, object]]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", section_text) if block.strip()]
    experiences: List[Dict[str, object]] = []
    date_pattern = re.compile(
        r"(?P<duration>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[^\n]{0,40}?\d{2,4}(?:\s*(?:-|to|–|—)\s*(?:Present|Now|\w{3,9}\s+\d{2,4}))?)",
        flags=re.IGNORECASE,
    )
    for block in blocks:
        lines = block.split("\n")
        header = lines[0] if lines else ""
        duration_match = date_pattern.search(header)
        duration = duration_match.group("duration") if duration_match else ""
        header_no_dates = date_pattern.sub("", header).strip()

        # Attempt to split title/company from remaining header text
        title = ""
        company = ""
        parts = re.split(r"\s+(?:@|at|\-|–|—|\|)\s+", header_no_dates, maxsplit=1)
        if parts:
            title = parts[0].strip()
            if len(parts) > 1:
                company = parts[1].strip()

        impact_lines = []
        for bullet in lines[1:]:
            cleaned = re.sub(r"^[\-\*•]\s*", "", bullet).strip()
            if cleaned:
                impact_lines.append(cleaned)

        experiences.append(
            {
                "title": title,
                "company": company,
                "duration": duration,
                "impact_bullets": impact_lines,
            }
        )
    return experiences


def parse_resume(text: str) -> Dict[str, object]:
    """Parse normalized resume text into structured sections.

    Returns default values when sections are absent to keep the schema
    consistent for downstream consumers.
    """

    sections = _split_sections(text)

    years_experience = _parse_years_experience(text) or 0

    education = sections.get("education", "")
    skills = _split_list_section(sections.get("skills", ""))
    tools_platforms = _split_list_section(sections.get("tools_platforms", ""))
    experience = _parse_experience(sections.get("experience", ""))
    projects = _split_list_section(sections.get("projects", ""))
    certifications = _split_list_section(sections.get("certifications", ""))
    clearances_or_work_auth = sections.get("clearances_or_work_auth", "")

    missing_fields: List[str] = []
    if not education:
        missing_fields.append("education")
    if not skills:
        missing_fields.append("skills")
    if not tools_platforms:
        missing_fields.append("tools_platforms")
    if not experience:
        missing_fields.append("experience")
    if not projects:
        missing_fields.append("projects")
    if not certifications:
        missing_fields.append("certifications")
    if not clearances_or_work_auth:
        missing_fields.append("clearances_or_work_auth")

    if missing_fields:
        logger.info("Resume missing sections: %s", ", ".join(missing_fields))

    return {
        "years_experience": years_experience,
        "education": education,
        "skills": skills,
        "tools_platforms": tools_platforms,
        "experience": experience,
        "projects": projects,
        "certifications": certifications,
        "clearances_or_work_auth": clearances_or_work_auth,
    }


__all__ = ["parse_resume"]