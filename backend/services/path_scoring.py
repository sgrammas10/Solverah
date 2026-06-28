"""Deterministic career path scoring algorithm.

Ranks O*NET occupations against a user's profile using a weighted sum of:
  (a) skill overlap — tries O*NET technology tools first, falls back to O*NET
      generic competency skills.  Works for all fields: tech users get tool-name
      matching; non-tech users match against competency names; zone delta carries
      the score when neither finds an overlap.
  (b) a job-zone delta bonus that favours roles 1–2 zones above the user's
      current zone, and penalises lateral moves or regressions.

Zone delta is the primary signal (60 %) so that non-tech users get meaningful
differentiation even when no skill names match directly.  Skill overlap is a
secondary refinement (40 %) that rewards closer matches.

No LLM calls are made anywhere in this module.

Typical O*NET call count per invocation:
  2  (current-zone resolution) + 3 × |candidates| (zone + tech_skills + skills per candidate)
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

_SKILLS_WEIGHT: float = 0.4   # secondary signal — skill overlap (tech tools or generic names)
_ZONE_WEIGHT: float = 0.6     # primary signal  — zone progression (universal for all fields)

_SKILL_LEVEL_WEIGHTS: dict[str, float] = {
    "beginner": 0.33,
    "intermediate": 0.67,
    "advanced": 1.0,
}

# Maximum number of ScoredPath objects returned.
_TOP_N: int = 10

# Skill names searched as additional candidate-pool terms (beyond the title).
_SKILL_SEARCH_COUNT: int = 2

# Minimum token length for substring matching (prevents "R" from matching "reading").
_MIN_MATCH_LEN: int = 3


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
    move_intent: Literal["stay_in_field", "adjacent", "fresh_start"] | None = None
    seniority_intent: Literal["move_up", "stay_lateral", "open"] | None = None


@dataclass
class ScoredPath:
    onet_code: str
    title: str
    score: float  # 0.0–1.0, higher is a better match
    overlapping_skills: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _zone_delta_score(
    current_zone: int,
    candidate_zone: int,
    seniority_intent: Literal["move_up", "stay_lateral", "open"] | None = None,
) -> float:
    """Map the zone difference to a [-0.3, 1.0] score contribution.

    Scoring varies based on seniority_intent:
    - move_up: rewards forward progression, penalises lateral
    - stay_lateral: rewards lateral moves, reduces forward progression weight
    - open/None: original balanced behaviour
    """
    delta = candidate_zone - current_zone

    if seniority_intent == "move_up":
        if delta >= 3:
            return 0.2
        if delta == 2:
            return 0.8   # boost ambition (was 0.6)
        if delta == 1:
            return 1.0
        if delta == 0:
            return 0.0   # penalise lateral when user wants up (was 0.2)
        if delta == -1:
            return 0.0
        return -0.3

    if seniority_intent == "stay_lateral":
        if delta >= 3:
            return 0.1
        if delta == 2:
            return 0.2
        if delta == 1:
            return 0.5   # mild forward acceptable
        if delta == 0:
            return 0.8   # lateral is the sweet spot
        if delta == -1:
            return 0.2   # slight regression tolerable
        return -0.3

    # "open" or None — original behaviour
    if delta >= 3:
        return 0.2   # large leap — possible but uncertain
    if delta == 2:
        return 0.6   # ambitious stretch
    if delta == 1:
        return 1.0   # ideal single-step forward
    if delta == 0:
        return 0.5   # lateral — solid match, skill overlap differentiates
    if delta == -1:
        return 0.0   # slight regression — score driven entirely by skill overlap
    return -0.3      # significant regression — only high skill overlap saves it


def _tech_skills_overlap_score(
    user_skills: list[UserSkill],
    onet_tech_names: set[str],
) -> tuple[float, list[str]]:
    """Return a [0.0, 1.0] overlap score and matched user skill names.

    Measures what fraction of the role's tech tools the user covers, weighted
    by proficiency level. Normalised against the role's tech tool count so
    extra user skills beyond what the role needs don't dilute the score.
    """
    if not onet_tech_names or not user_skills:
        return 0.0, []

    eligible_techs = {t for t in onet_tech_names if len(t) >= _MIN_MATCH_LEN}
    if not eligible_techs:
        return 0.0, []

    eligible_user = [s for s in user_skills if len(s.name.lower()) >= _MIN_MATCH_LEN]
    if not eligible_user:
        return 0.0, []

    # Use the smaller set as the denominator — prevents a long O*NET tool list from
    # diluting the score when the user knows most of their relevant skills for the role,
    # and prevents extra user skills from diluting the score when the role has few tools.
    total_possible = float(min(len(eligible_techs), len(eligible_user)))

    weighted_overlap = 0.0
    matched: list[str] = []
    matched_techs: set[str] = set()

    for us in eligible_user:
        name_lower = us.name.lower()
        for tech in eligible_techs:
            if tech in matched_techs:
                continue
            if name_lower in tech or tech in name_lower:
                level_weight = _SKILL_LEVEL_WEIGHTS.get(
                    us.level, _SKILL_LEVEL_WEIGHTS["beginner"]
                )
                weighted_overlap += level_weight
                matched.append(us.name)
                matched_techs.add(tech)
                break

    return min(weighted_overlap / total_possible, 1.0), matched


def _generic_skills_overlap_score(
    user_skills: list[UserSkill],
    onet_skills: list[Skill],
) -> tuple[float, list[str]]:
    """Return a [0.0, 1.0] overlap score using O*NET generic competency names.

    Fallback for users whose profile skills don't match any O*NET tech tool
    (e.g. healthcare, education, trades).  Uses bidirectional substring
    matching so "Patient Care" can match "Care" in an O*NET skill name and
    vice versa.  Weighted by O*NET importance score so high-importance
    skills count more toward the final result.
    """
    if not onet_skills or not user_skills:
        return 0.0, []

    total_importance = sum(s.importance for s in onet_skills)
    if total_importance == 0.0:
        return 0.0, []

    user_tokens = [
        (us, us.name.lower())
        for us in user_skills
        if len(us.name) >= _MIN_MATCH_LEN
    ]
    weighted_overlap = 0.0
    matched: list[str] = []
    matched_onet: set[str] = set()

    for onet_skill in onet_skills:
        skill_lower = onet_skill.name.lower()
        if len(skill_lower) < _MIN_MATCH_LEN:
            continue
        for us, name_lower in user_tokens:
            if name_lower in skill_lower or skill_lower in name_lower:
                if onet_skill.name not in matched_onet:
                    level_weight = _SKILL_LEVEL_WEIGHTS.get(
                        us.level, _SKILL_LEVEL_WEIGHTS["beginner"]
                    )
                    weighted_overlap += level_weight * onet_skill.importance
                    matched.append(us.name)
                    matched_onet.add(onet_skill.name)
                break

    return min(weighted_overlap / total_importance, 1.0), matched


def _resolve_current_zone(
    profile: UserProfile,
    onet_client: OnetClient,
) -> tuple[int, str | None, bool]:
    """Return (current_zone, current_onet_code, zone_resolved).

    Searches O*NET for the user's current title and fetches its job zone.
    Falls back to zone 1 (entry-level) on first_job status, missing title,
    empty search results, or any O*NET API error.  zone_resolved is False
    whenever the zone is a fallback default rather than a real lookup result.
    """
    if profile.career_status == "first_job" or not profile.current_title:
        return 1, None, False

    try:
        occupations = onet_client.search_occupations(profile.current_title)
    except OnetAPIError:
        return 1, None, False

    if not occupations:
        return 1, None, False

    current_code = occupations[0].code
    try:
        zone = onet_client.get_job_zone(current_code)
    except OnetAPIError:
        # Return code so it can still be excluded from the candidate pool.
        return 1, current_code, False

    return zone, current_code, True


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
    intent = profile.move_intent

    if intent == "stay_in_field":
        if profile.current_title and profile.career_status != "first_job":
            search_terms.append(profile.current_title)
        # Skills ensure a relevant candidate pool when the title doesn't map
        # cleanly to O*NET (e.g. "Founder & Full Stack Engineer" → foundry roles).
        for skill in profile.skills[:_SKILL_SEARCH_COUNT]:
            search_terms.append(skill.name)
    elif intent == "fresh_start":
        for skill in profile.skills[:_SKILL_SEARCH_COUNT]:
            search_terms.append(skill.name)
    else:  # "adjacent" or None — original behaviour
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
    3. For each candidate fetch zone, tech tools, and generic competency skills,
       then compute:

           overlap  = max(tech_tools_overlap, generic_skills_overlap)
           combined = _SKILLS_WEIGHT × overlap + _ZONE_WEIGHT × zone_delta_score

       Zone delta is the primary signal (60 %) so non-tech users still get
       meaningful differentiation.  Skill overlap is secondary (40 %) and uses
       whichever O*NET dataset gives the better match for this user's field.

       Score is clamped to [0.0, 1.0].
    4. Return up to _TOP_N results sorted by score descending.

    Candidates that trigger an O*NET API error are silently skipped.

    Args:
        user_profile: Career snapshot of the user.
        onet_client:  Authenticated O*NET Web Services client.

    Returns:
        Up to 10 ScoredPath objects, best match first.
    """
    current_zone, current_code, zone_resolved = _resolve_current_zone(user_profile, onet_client)
    candidates = _gather_candidates(user_profile, onet_client, exclude_code=current_code)

    # Zone signal is reliable only when O*NET actually resolved the title, or when
    # the user is first_job (zone 1 is genuinely accurate by definition).
    # For established users whose title didn't map in O*NET, the fallback zone 1 is
    # meaningless — using it actively penalises high-zone tech roles vs low-zone
    # irrelevant roles, so we drop zone entirely and rank purely on skill overlap.
    zone_is_reliable = zone_resolved or user_profile.career_status == "first_job"
    if zone_is_reliable:
        skills_w, zone_w = _SKILLS_WEIGHT, _ZONE_WEIGHT
    else:
        skills_w, zone_w = 1.0, 0.0

    scored: list[ScoredPath] = []
    _debug: list[dict] = []

    for occ in candidates:
        try:
            zone = onet_client.get_job_zone(occ.code)
            onet_tech_names = onet_client.get_tech_skills(occ.code)
            onet_generic_skills = onet_client.get_skills_profile(occ.code)
        except OnetAPIError:
            continue

        tech_score, tech_matched = _tech_skills_overlap_score(
            user_profile.skills, onet_tech_names
        )
        generic_score, generic_matched = _generic_skills_overlap_score(
            user_profile.skills, onet_generic_skills
        )
        if tech_score >= generic_score:
            overlap_score, matched_skills = tech_score, tech_matched
            winning_signal = "tech"
        else:
            overlap_score, matched_skills = generic_score, generic_matched
            winning_signal = "generic"

        # Without a reliable zone signal, zero-overlap candidates would score 0
        # anyway — skip them to avoid polluting results with irrelevant roles.
        if not zone_is_reliable and overlap_score == 0.0:
            continue

        zone_score = _zone_delta_score(current_zone, zone, user_profile.seniority_intent)
        raw = skills_w * overlap_score + zone_w * zone_score
        final_score = round(max(0.0, min(1.0, raw)), 4)

        scored.append(
            ScoredPath(
                onet_code=occ.code,
                title=occ.title,
                score=final_score,
                overlapping_skills=matched_skills,
            )
        )
        _debug.append({
            "title": occ.title,
            "code": occ.code,
            "zone": zone,
            "zone_score": zone_score,
            "tech_score": tech_score,
            "tech_matched": tech_matched,
            "tech_tools": sorted(onet_tech_names),
            "generic_score": generic_score,
            "generic_matched": generic_matched,
            "generic_skills": [(s.name, s.importance) for s in onet_generic_skills],
            "winning_signal": winning_signal,
            "overlap_score": overlap_score,
            "final_score": final_score,
        })

    scored.sort(key=lambda p: p.score, reverse=True)
    _debug.sort(key=lambda d: d["final_score"], reverse=True)
    _print_scoring_debug(user_profile, current_zone, zone_resolved, zone_is_reliable, skills_w, zone_w, _debug[:3])

    return scored[:_TOP_N]


def _print_scoring_debug(
    profile: UserProfile,
    current_zone: int,
    zone_resolved: bool,
    zone_is_reliable: bool,
    skills_w: float,
    zone_w: float,
    top3_debug: list[dict],
) -> None:
    import os
    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "scoring_debug.txt")
    out_path = os.path.normpath(out_path)
    sep = "─" * 60
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("PATH SCORING DEBUG")
    lines.append("=" * 60)
    lines.append(f"Title      : {profile.current_title!r}")
    lines.append(f"Status     : {profile.career_status}")
    lines.append(f"Zone       : {current_zone}  (resolved={zone_resolved}, reliable={zone_is_reliable})")
    lines.append(f"Weights    : skills={skills_w:.2f}  zone={zone_w:.2f}")
    lines.append(f"Intent     : move={profile.move_intent}  seniority={profile.seniority_intent}")
    lines.append("User skills:")
    for s in profile.skills:
        lines.append(f"  {s.name!r:<25} ({s.level})")

    for rank, d in enumerate(top3_debug, 1):
        lines.append(f"\n{sep}")
        lines.append(f"#{rank}  {d['title']}  [{d['code']}]  score={d['final_score']:.4f} ({d['final_score']*100:.1f}%)")
        lines.append(f"    Role zone: {d['zone']}  |  delta: {d['zone'] - current_zone:+d}  |  zone_score: {d['zone_score']:.3f}")
        lines.append(f"    Winning signal: {d['winning_signal']}")
        lines.append(f"\n    --- TECH TOOLS ({len(d['tech_tools'])} total) ---")
        if d['tech_tools']:
            for tool in d['tech_tools']:
                lines.append(f"      {tool}")
        else:
            lines.append("      (none)")
        lines.append(f"    Tech matched: {d['tech_matched']}  ->  tech_score={d['tech_score']:.4f}")
        lines.append(f"\n    --- GENERIC SKILLS ({len(d['generic_skills'])} total) ---")
        for name, imp in sorted(d['generic_skills'], key=lambda x: -x[1]):
            lines.append(f"      {name:<40} importance={imp:.1f}")
        lines.append(f"    Generic matched: {d['generic_matched']}  ->  generic_score={d['generic_score']:.4f}")
        user_eligible = sum(1 for s in profile.skills if len(s.name) >= _MIN_MATCH_LEN)
        tech_eligible = sum(1 for t in d['tech_tools'] if len(t) >= _MIN_MATCH_LEN)
        denom = min(tech_eligible, user_eligible) if tech_eligible else 0
        lines.append(f"\n    overlap_score={d['overlap_score']:.4f}  (denom=min({tech_eligible},{user_eligible})={denom})")
        lines.append(f"    final = {skills_w:.2f}x{d['overlap_score']:.4f} + {zone_w:.2f}x{d['zone_score']:.4f} = {d['final_score']:.4f}")

    lines.append("\n" + "=" * 60)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
