"""Deterministic career path scoring algorithm.

Ranks O*NET occupations against a user's profile using a weighted sum of:
  (a) skill overlap between the user's skills and O*NET required skills
  (b) a job-zone delta bonus that favours roles 1–2 zones above the user's
      current zone, and penalises lateral moves or regressions.

No LLM calls are made anywhere in this module.

Typical O*NET call count per invocation:
  2  (current-zone resolution) + 2 × |candidates| (zone + skills per candidate)
Keep _SKILL_SEARCH_COUNT small to avoid hitting the O*NET rate limit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from backend.services.onet_client import OnetAPIError, OnetClient, Occupation, Skill

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SKILLS_WEIGHT: float = 0.7   # fraction of score driven by skill overlap
_ZONE_WEIGHT: float = 0.3     # fraction of score driven by zone progression

_SKILL_LEVEL_WEIGHTS: dict[str, float] = {
    "beginner": 0.33,
    "intermediate": 0.67,
    "advanced": 1.0,
}

# Maximum number of ScoredPath objects returned.
_TOP_N: int = 10

# Skill names searched as additional candidate-pool terms (beyond the title).
_SKILL_SEARCH_COUNT: int = 2


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class UserSkill:
    name: str
    level: Literal["beginner", "intermediate", "advanced"]


@dataclass
class UserProfile:
    # None signals a first-job user who has no prior occupation.
    current_title: str | None
    career_status: Literal["employed", "between_jobs", "first_job"]
    skills: list[UserSkill]
    # WorkPulse archetype label — carried for display purposes; not scored here
    # because mapping a free-form archetype string to occupations deterministically
    # would require an LLM or a hardcoded lookup that would drift quickly.
    archetype: str


@dataclass
class ScoredPath:
    onet_code: str
    title: str
    score: float  # 0.0–1.0, higher is a better match
    overlapping_skills: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _zone_delta_score(current_zone: int, candidate_zone: int) -> float:
    """Map the zone difference to a [-0.5, 1.0] score contribution.

    Single-step forward (delta = 1) is the sweet spot and scores 1.0.
    Lateral moves and regressions return negative values; callers clamp the
    final combined score to [0.0, 1.0] so those candidates rank near zero.
    """
    delta = candidate_zone - current_zone
    if delta >= 3:
        return 0.3   # large leap — possible but uncertain
    if delta == 2:
        return 0.7   # ambitious stretch
    if delta == 1:
        return 1.0   # ideal single-step forward
    if delta == 0:
        return -0.2  # lateral — low but not impossible
    return -0.5      # regression


def _skills_overlap_score(
    user_skills: list[UserSkill],
    onet_skills: list[Skill],
) -> tuple[float, list[str]]:
    """Return a [0.0, 1.0] overlap score and matching skill names.

    Score is the sum of (user_level_weight × onet_importance) for each
    matched skill, normalised by the total O*NET importance across the
    occupation.  Matching is case-insensitive on skill name.

    Returns:
        (score, list of matched skill names in original O*NET casing)
    """
    if not onet_skills:
        return 0.0, []

    total_importance = sum(s.importance for s in onet_skills)
    if total_importance == 0.0:
        return 0.0, []

    user_map = {s.name.lower(): s for s in user_skills}
    weighted_overlap = 0.0
    matched: list[str] = []

    for onet_skill in onet_skills:
        user_skill = user_map.get(onet_skill.name.lower())
        if user_skill is not None:
            level_weight = _SKILL_LEVEL_WEIGHTS.get(
                user_skill.level, _SKILL_LEVEL_WEIGHTS["beginner"]
            )
            weighted_overlap += level_weight * onet_skill.importance
            matched.append(onet_skill.name)

    return min(weighted_overlap / total_importance, 1.0), matched


def _resolve_current_zone(
    profile: UserProfile,
    onet_client: OnetClient,
) -> tuple[int, str | None]:
    """Return (current_zone, current_onet_code).

    Searches O*NET for the user's current title and fetches its job zone.
    Falls back to zone 1 (entry-level) on first_job status, missing title,
    empty search results, or any O*NET API error.
    """
    if profile.career_status == "first_job" or not profile.current_title:
        return 1, None

    try:
        occupations = onet_client.search_occupations(profile.current_title)
    except OnetAPIError:
        return 1, None

    if not occupations:
        return 1, None

    current_code = occupations[0].code
    try:
        zone = onet_client.get_job_zone(current_code)
    except OnetAPIError:
        # Return code so it can still be excluded from the candidate pool.
        return 1, current_code

    return zone, current_code


def _gather_candidates(
    profile: UserProfile,
    onet_client: OnetClient,
    exclude_code: str | None,
) -> list[Occupation]:
    """Build a deduplicated candidate pool by searching O*NET.

    Searches the user's current title (unless first_job) plus up to
    _SKILL_SEARCH_COUNT skill names to reach a broad cross-zone pool.
    The current occupation is excluded by *exclude_code* if known.
    """
    seen: set[str] = {exclude_code} if exclude_code else set()
    candidates: list[Occupation] = []

    search_terms: list[str] = []
    if profile.current_title and profile.career_status != "first_job":
        search_terms.append(profile.current_title)
    for skill in profile.skills[:_SKILL_SEARCH_COUNT]:
        search_terms.append(skill.name)

    api_errors = 0
    for term in search_terms:
        try:
            results = onet_client.search_occupations(term)
            _log.debug("O*NET search %r → %d results", term, len(results))
            for occ in results:
                if occ.code not in seen:
                    seen.add(occ.code)
                    candidates.append(occ)
        except OnetAPIError as exc:
            _log.warning("O*NET search failed for term %r: %s", term, exc)
            api_errors += 1

    if api_errors:
        _log.warning("%d/%d O*NET search(es) failed", api_errors, len(search_terms))

    return candidates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_paths(
    user_profile: UserProfile,
    onet_client: OnetClient,
) -> list[ScoredPath]:
    """Score candidate career paths against *user_profile* and return the top 10.

    Algorithm
    ---------
    1. Resolve the user's current job zone (zone 1 for first-job / unknown).
    2. Build a candidate pool from O*NET keyword searches.
    3. For each candidate fetch its zone and skills, then compute:

           combined = _SKILLS_WEIGHT × overlap_score
                    + _ZONE_WEIGHT   × zone_delta_score

       clamped to [0.0, 1.0].
    4. Return up to _TOP_N results sorted by score descending.

    Candidates that trigger an O*NET API error are silently skipped.

    Args:
        user_profile: Career snapshot of the user.
        onet_client:  Authenticated O*NET Web Services client.

    Returns:
        Up to 10 ScoredPath objects, best match first.
    """
    current_zone, current_code = _resolve_current_zone(user_profile, onet_client)
    candidates = _gather_candidates(user_profile, onet_client, exclude_code=current_code)

    scored: list[ScoredPath] = []
    for occ in candidates:
        try:
            zone = onet_client.get_job_zone(occ.code)
            onet_skills = onet_client.get_skills_profile(occ.code)
        except OnetAPIError:
            continue

        overlap_score, matched_skills = _skills_overlap_score(
            user_profile.skills, onet_skills
        )
        zone_score = _zone_delta_score(current_zone, zone)
        raw = _SKILLS_WEIGHT * overlap_score + _ZONE_WEIGHT * zone_score
        final_score = round(max(0.0, min(1.0, raw)), 4)

        scored.append(
            ScoredPath(
                onet_code=occ.code,
                title=occ.title,
                score=final_score,
                overlapping_skills=matched_skills,
            )
        )

    scored.sort(key=lambda p: p.score, reverse=True)
    return scored[:_TOP_N]
