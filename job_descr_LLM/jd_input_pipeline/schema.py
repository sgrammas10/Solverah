"""Schema definitions for parsed job descriptions."""
from __future__ import annotations

from typing import Dict, List, TypedDict


class ExperienceBlock(TypedDict):
    title: str
    company: str
    duration: str
    impact_bullets: List[str]


class JobDescriptionOutput(TypedDict):
    id: int
    text: str
    years_experience: float
    education: str
    skills: List[str]
    skills_by_category: Dict[str, List[str]]
    experience: List[ExperienceBlock]
    projects: List[str]
    certifications: List[str]
    clearances_or_work_auth: str


DEFAULT_OUTPUT: JobDescriptionOutput = {
    "id": 0,
    "text": "",
    "years_experience": 0,
    "education": "",
    "skills": [],
    "skills_by_category": {},
    "experience": [],
    "projects": [],
    "certifications": [],
    "clearances_or_work_auth": "",
}