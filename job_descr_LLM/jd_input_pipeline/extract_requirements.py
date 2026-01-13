"""Requirement extraction for job descriptions."""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

from .normalize import strip_bullet
from .normalize_requirements import categorize_skills, dedupe_preserve_order, normalize_skill

YEARS_PATTERN = re.compile(
    r"(?P<years>\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)\s*(?:of\s+)?experience",
    re.I,
)
MIN_YEARS_PATTERN = re.compile(r"(?:minimum|at least)\s*(?P<years>\d+(?:\.\d+)?)\s*(?:years?|yrs?)", re.I)

EDU_PATTERN = re.compile(
    r"\b(bachelor|bs|ba|b\.s\.|b\.a\.|master|ms|m\.s\.|mba|phd|ph\.d|associate|associate's)\b",
    re.I,
)

CERT_PATTERN = re.compile(
    r"\b(certified|certification|license|licensure|aws|azure|gcp|cissp|pmp|cpa|cpcu|rn|bls|acls)\b",
    re.I,
)

CLEARANCE_PATTERN = re.compile(
    r"\b(us citizen|citizenship|authorized to work|work authorization|no sponsorship|sponsorship|security clearance|secret|top secret|ts/sci|public trust)\b",
    re.I,
)

ROLE_TITLE_PATTERN = re.compile(r"^(job title|position|role)\s*:\s*(?P<title>.+)$", re.I)
COMPANY_PATTERN = re.compile(r"^(company|employer)\s*:\s*(?P<company>.+)$", re.I)

SKILL_PHRASES = re.compile(
    r"\b(experience with|proficient in|knowledge of|skills in|familiar with|expertise in|using)\b",
    re.I,
)

DELIMITERS = re.compile(r"[,;/|]\s*")


SECTION_PRIORITY = ["requirements", "qualifications", "preferred", "responsibilities", "general", "education"]


def _lines_from_sections(sections: Dict[str, List[str]]) -> List[str]:
    ordered: List[str] = []
    for section in SECTION_PRIORITY:
        ordered.extend(sections.get(section, []))
    return ordered


def extract_years_experience(lines: Iterable[str]) -> float:
    years: List[float] = []
    for line in lines:
        for match in YEARS_PATTERN.finditer(line):
            years.append(float(match.group("years")))
        for match in MIN_YEARS_PATTERN.finditer(line):
            years.append(float(match.group("years")))
    if not years:
        return 0
    return max(years)


def extract_education(lines: Iterable[str]) -> str:
    for line in lines:
        if EDU_PATTERN.search(line):
            return strip_bullet(line)
    return ""


def extract_clearance(lines: Iterable[str]) -> str:
    matches: List[str] = []
    for line in lines:
        if CLEARANCE_PATTERN.search(line):
            matches.append(strip_bullet(line))
    return " ".join(dedupe_preserve_order(matches))


def extract_certifications(lines: Iterable[str]) -> List[str]:
    certs: List[str] = []
    for line in lines:
        if CERT_PATTERN.search(line):
            certs.append(strip_bullet(line))
    return dedupe_preserve_order(certs)


def extract_skills(lines: Iterable[str]) -> List[str]:
    skills: List[str] = []
    for line in lines:
        cleaned = strip_bullet(line)
        if SKILL_PHRASES.search(cleaned) or DELIMITERS.search(cleaned):
            fragments = DELIMITERS.split(cleaned)
            for fragment in fragments:
                if SKILL_PHRASES.search(fragment):
                    fragment = SKILL_PHRASES.sub("", fragment)
                fragment = fragment.strip(" .:")
                if len(fragment.split()) > 8:
                    continue
                normalized = normalize_skill(fragment)
                if normalized:
                    skills.append(normalized)
    return dedupe_preserve_order(skills)


def extract_role_title(lines: Iterable[str]) -> str:
    for line in lines:
        match = ROLE_TITLE_PATTERN.match(line.strip())
        if match:
            return match.group("title").strip()
    for line in lines:
        stripped = line.strip()
        if 2 <= len(stripped.split()) <= 8 and stripped.isupper() is False:
            return stripped
    return ""


def extract_company(lines: Iterable[str]) -> str:
    for line in lines:
        match = COMPANY_PATTERN.match(line.strip())
        if match:
            return match.group("company").strip()
    return ""


def _extract_duration(line: str) -> str:
    match = YEARS_PATTERN.search(line) or MIN_YEARS_PATTERN.search(line)
    if match:
        years = match.group("years")
        return f"{years}+ years"
    return ""


def build_experience_blocks(sections: Dict[str, List[str]], title: str, company: str) -> List[Dict[str, object]]:
    blocks: List[Dict[str, object]] = []
    for section in ["responsibilities", "requirements", "qualifications", "preferred"]:
        lines = sections.get(section, [])
        if not lines:
            continue
        bullets = [strip_bullet(line) for line in lines if line.strip()]
        bullets = [b for b in bullets if len(b.split()) >= 3]
        if not bullets:
            continue
        duration = ""
        for bullet in bullets:
            duration = _extract_duration(bullet)
            if duration:
                break
        blocks.append(
            {
                "title": title,
                "company": company,
                "duration": duration,
                "impact_bullets": bullets[:6],
            }
        )
        if len(blocks) >= 5:
            break
    if not blocks and sections.get("general"):
        bullets = [strip_bullet(line) for line in sections.get("general", []) if line.strip()]
        bullets = [b for b in bullets if len(b.split()) >= 3]
        if bullets:
            blocks.append(
                {
                    "title": title,
                    "company": company,
                    "duration": "",
                    "impact_bullets": bullets[:6],
                }
            )
    return blocks


def extract_requirements(sections: Dict[str, List[str]]) -> Tuple[float, str, List[str], Dict[str, List[str]], List[str], str, List[Dict[str, object]]]:
    prioritized_lines = _lines_from_sections(sections)
    years = extract_years_experience(prioritized_lines)
    education = extract_education(prioritized_lines)
    skills = extract_skills(prioritized_lines)
    skills_by_category = categorize_skills(skills) if skills else {}
    certifications = extract_certifications(prioritized_lines)
    clearance = extract_clearance(prioritized_lines)
    title = extract_role_title(sections.get("general", []) + prioritized_lines)
    company = extract_company(sections.get("general", []) + prioritized_lines)
    experience_blocks = build_experience_blocks(sections, title, company)
    return (
        years,
        education,
        skills,
        skills_by_category,
        certifications,
        clearance,
        experience_blocks,
    )