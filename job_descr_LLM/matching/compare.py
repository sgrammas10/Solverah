"""Skills-fit matching between a job description profile and a candidate profile.

This module implements Model 1 of Solverah's two-model matching pipeline.
Given a structured ``JobDescriptionOutput`` (extracted by the JD input pipeline)
and a candidate profile dict (from the resume parser), it produces a weighted
composite score along five dimensions:

Dimensions and default weights:
    skills              (0.50) — Jaccard-like overlap between required and candidate skills.
    years_experience    (0.20) — Candidate years vs. required; capped at 1.0 if over-qualified.
    certifications      (0.10) — Required certifications the candidate holds.
    education           (0.10) — Boolean: required degree level present in candidate profile.
    clearance           (0.10) — Boolean: required clearance/work-auth tokens match.

Public API:
    compare_profiles(jd_profile, candidate_profile, *, weights=None) -> dict
    compare_records(jd_record, candidate_record, *, weights=None)     -> dict
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple

from job_descr_LLM.jd_input_pipeline.schema import JobDescriptionOutput


@dataclass(frozen=True)
class MatchWeights:
    """Weights for scoring each match dimension."""

    skills: float = 0.5
    years_experience: float = 0.2
    certifications: float = 0.1
    education: float = 0.1
    clearance: float = 0.1


def _normalize_token(value: str) -> str:
    """Lowercase, strip, and collapse internal whitespace in a single token."""
    return " ".join(value.lower().strip().split())


def _normalize_tokens(values: Iterable[str]) -> List[str]:
    """Normalize a collection of token strings, dropping empty entries."""
    normalized: List[str] = []
    for value in values:
        if not value:
            continue
        token = _normalize_token(value)
        if token:
            normalized.append(token)
    return normalized


def _set_overlap(left: Iterable[str], right: Iterable[str]) -> Tuple[set[str], set[str], set[str]]:
    """Return (overlap, left_only, right_only) after normalizing both token sets."""
    left_set = set(_normalize_tokens(left))
    right_set = set(_normalize_tokens(right))
    overlap = left_set & right_set
    return overlap, left_set - right_set, right_set - left_set


def _ratio(numerator: int, denominator: int) -> float:
    """Return numerator/denominator, or 0.0 if denominator is zero."""
    return (numerator / denominator) if denominator else 0.0


def _education_match(jd_education: str, candidate_education: str) -> bool:
    """Return True if the candidate's education string satisfies the JD requirement.

    Uses substring containment in either direction so "BS Computer Science"
    matches a JD that simply says "Bachelor's degree".  If the JD specifies no
    education requirement, the candidate always passes.
    """
    if not jd_education:
        return True
    if not candidate_education:
        return False
    jd_norm = _normalize_token(jd_education)
    cand_norm = _normalize_token(candidate_education)
    return jd_norm in cand_norm or cand_norm in jd_norm


def _clearance_match(jd_clearance: str, candidate_clearance: str) -> bool:
    """Return True if any clearance/work-auth token from the JD appears in the candidate's string.

    Token-level matching handles variations like "TS/SCI" where a candidate
    lists individual components.  If no clearance is required, always returns True.
    """
    if not jd_clearance:
        return True
    if not candidate_clearance:
        return False
    jd_tokens = set(_normalize_token(jd_clearance).split())
    cand_tokens = set(_normalize_token(candidate_clearance).split())
    return bool(jd_tokens & cand_tokens)


def compare_profiles(
    jd_profile: JobDescriptionOutput,
    candidate_profile: Mapping[str, object],
    *,
    weights: MatchWeights | None = None,
) -> Dict[str, object]:
    """Score a candidate against a structured job description profile.

    Args:
        jd_profile:        Extracted job description (``JobDescriptionOutput``).
        candidate_profile: Candidate profile dict (keys: skills, certifications,
                           years_experience, education, clearances_or_work_auth).
        weights:           Optional override for dimension weights.  Unspecified
                           dimensions keep their ``MatchWeights`` defaults.

    Returns:
        Dict with keys:
            score           — Weighted composite [0.0, 1.0].
            skills          — {"overlap", "missing", "extra", "match_ratio"}
            certifications  — {"overlap", "missing", "extra", "match_ratio"}
            years_experience — {"job_required", "candidate", "gap", "match_ratio"}
            education_match — bool
            clearance_match — bool
    """
    weights = weights or MatchWeights()

    jd_skills = jd_profile.get("skills", [])
    candidate_skills = candidate_profile.get("skills", [])
    overlap, missing, extras = _set_overlap(jd_skills, candidate_skills)

    jd_certs = jd_profile.get("certifications", [])
    candidate_certs = candidate_profile.get("certifications", [])
    cert_overlap, cert_missing, cert_extras = _set_overlap(jd_certs, candidate_certs)

    jd_years = float(jd_profile.get("years_experience", 0) or 0)
    candidate_years = float(candidate_profile.get("years_experience", 0) or 0)
    years_ratio = min(candidate_years / jd_years, 1.0) if jd_years else 1.0

    education_match = _education_match(
        str(jd_profile.get("education", "")),
        str(candidate_profile.get("education", "")),
    )
    clearance_match = _clearance_match(
        str(jd_profile.get("clearances_or_work_auth", "")),
        str(candidate_profile.get("clearances_or_work_auth", "")),
    )

    skill_ratio = _ratio(len(overlap), len(set(_normalize_tokens(jd_skills))))
    cert_ratio = _ratio(len(cert_overlap), len(set(_normalize_tokens(jd_certs))))

    score = (
        skill_ratio * weights.skills
        + years_ratio * weights.years_experience
        + cert_ratio * weights.certifications
        + (1.0 if education_match else 0.0) * weights.education
        + (1.0 if clearance_match else 0.0) * weights.clearance
    )

    return {
        "score": round(score, 4),
        "skills": {
            "overlap": sorted(overlap),
            "missing": sorted(missing),
            "extra": sorted(extras),
            "match_ratio": round(skill_ratio, 4),
        },
        "certifications": {
            "overlap": sorted(cert_overlap),
            "missing": sorted(cert_missing),
            "extra": sorted(cert_extras),
            "match_ratio": round(cert_ratio, 4),
        },
        "years_experience": {
            "job_required": jd_years,
            "candidate": candidate_years,
            "gap": round(candidate_years - jd_years, 2),
            "match_ratio": round(years_ratio, 4),
        },
        "education_match": education_match,
        "clearance_match": clearance_match,
    }


def compare_records(
    jd_record: Mapping[str, object],
    candidate_record: Mapping[str, object],
    *,
    weights: MatchWeights | None = None,
) -> Dict[str, object]:
    """Convenience wrapper that accepts raw dicts instead of typed objects.

    Constructs a ``JobDescriptionOutput`` from *jd_record* before delegating to
    ``compare_profiles``.  Useful for scripts and tests that work with raw
    database rows or CSV data without going through the full JD pipeline.

    Args:
        jd_record:        Dict with the same keys as ``JobDescriptionOutput``.
        candidate_record: Same as ``compare_profiles``.
        weights:          Same as ``compare_profiles``.

    Returns:
        Same dict structure as ``compare_profiles``.
    """
    jd_profile = JobDescriptionOutput(
        id=int(jd_record.get("id", 0) or 0),
        text=str(jd_record.get("text", "")),
        years_experience=float(jd_record.get("years_experience", 0) or 0),
        education=str(jd_record.get("education", "")),
        skills=list(jd_record.get("skills", []) or []),
        skills_by_category=dict(jd_record.get("skills_by_category", {}) or {}),
        experience=list(jd_record.get("experience", []) or []),
        projects=list(jd_record.get("projects", []) or []),
        certifications=list(jd_record.get("certifications", []) or []),
        clearances_or_work_auth=str(jd_record.get("clearances_or_work_auth", "")),
    )

    return compare_profiles(jd_profile, candidate_record, weights=weights)