"""Validation and coercion for job description outputs."""
from __future__ import annotations

from typing import Dict, List, Mapping

from .schema import DEFAULT_OUTPUT, JobDescriptionOutput


def validate_output(payload: Mapping[str, object]) -> JobDescriptionOutput:
    output: Dict[str, object] = dict(DEFAULT_OUTPUT)
    output.update(payload)

    output["years_experience"] = float(output.get("years_experience") or 0)

    for key in ["skills", "experience", "projects", "certifications"]:
        if not isinstance(output.get(key), list):
            output[key] = []

    if not isinstance(output.get("skills_by_category"), dict):
        output["skills_by_category"] = {}

    for key in ["education", "text", "clearances_or_work_auth"]:
        if output.get(key) is None:
            output[key] = ""

    if not isinstance(output.get("id"), int):
        output["id"] = int(output.get("id") or 0)

    return output  # type: ignore[return-value]