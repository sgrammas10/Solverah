"""Semantic career path scoring algorithm.

Ranks O*NET occupations against a user's profile using a weighted sum of:
  (a) semantic skill overlap — cosine similarity between a proficiency-weighted
      user skill centroid and an importance-weighted role profile centroid.
      The role profile merges O*NET hot tech tools (trending tools only) with
      important generic competency skills into a single unified pool.
  (b) job-zone delta — rewards roles 1–2 zones above the user's current zone.

Zone delta carries more weight for first-job users (0.6) where zone direction
is highly predictive.  For experienced users the split is balanced (0.5/0.5)
because semantic skill matching is now an equally reliable signal.

LLM calls made per invocation (when openai_client is provided):
  1  (title normalisation, only if raw O*NET search returns no results)
  1–2 (batch embedding of all unique skill/tool strings, cached across requests)

O*NET call count:
  2  (current-zone resolution) + 3 × |candidates| (zone + tech_skills + skills per candidate)
"""
from __future__ import annotations

import logging
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from backend.services.onet_client import OnetAPIError, OnetClient, Occupation, Skill

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Skill signal vs. zone signal weights.
# first_job: zone direction is high-signal (1→2→3 maps to entry→mid→senior).
# experienced: skills are equally predictive; balanced 50/50 split.
_SKILLS_WEIGHT_EXPERIENCED: float = 0.5
_ZONE_WEIGHT_EXPERIENCED: float = 0.5
_SKILLS_WEIGHT_FIRST_JOB: float = 0.4
_ZONE_WEIGHT_FIRST_JOB: float = 0.6

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

# Hot tech tools from O*NET have no per-tool importance score — treat all uniformly.
# 75 = high but not max, since any individual tool is rarely a requirement for every
# practitioner in the role.
_HOT_TECH_IMPORTANCE: float = 75.0

# Generic skills with importance below this threshold are excluded from scoring
# to reduce noise from peripheral competencies.
_GENERIC_IMPORTANCE_THRESHOLD: float = 50.0

# Cosine similarity threshold for an embedding match to count.
_EMBED_THRESHOLD: float = 0.70

# Work activity importance threshold — activities below this are excluded.
_WORK_ACTIVITY_IMPORTANCE_THRESHOLD: float = 50.0

# Maximum share of final score contributed by the behavioral work-style signal.
# Kept low until validated against more profiles — enough to add nuance without
# overriding correct skill-based rankings.
_WORK_STYLE_WEIGHT: float = 0.10

# In-process embedding cache.  OrderedDict enables O(1) LRU eviction.
_EMBED_CACHE: OrderedDict[str, list[float]] = OrderedDict()
_EMBED_CACHE_MAX: int = 10_000


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
    # WorkPulse archetype label — carried for display purposes; not scored here.
    archetype: str
    move_intent: Literal["stay_in_field", "adjacent", "fresh_start"] | None = None
    seniority_intent: Literal["move_up", "stay_lateral", "open"] | None = None
    # Behavioral profile — populated from completed assessments, None if not yet taken.
    # These fields should store full description text (not short label names) so the
    # embedding model can find meaningful semantic distance against O*NET work activities.
    archetype_description: str = ""   # multi-sentence WPL archetype description
    focus_type: str | None = None     # FocusType label (no rich description available)
    manager_match: str | None = None  # ManagerMatch archetype_description text
    work_style_tags: list[str] = field(default_factory=list)  # WPL signal descriptions


@dataclass
class ScoredPath:
    onet_code: str
    title: str
    score: float  # 0.0–1.0, higher is a better match
    overlapping_skills: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Zone delta scoring
# ---------------------------------------------------------------------------


def _zone_delta_score(
    current_zone: int,
    candidate_zone: int,
    seniority_intent: Literal["move_up", "stay_lateral", "open"] | None = None,
) -> float:
    """Map the zone difference to a [-0.3, 1.0] score contribution."""
    delta = candidate_zone - current_zone

    if seniority_intent == "move_up":
        if delta >= 3:
            return 0.2
        if delta == 2:
            return 0.8
        if delta == 1:
            return 1.0
        if delta == 0:
            return 0.0
        if delta == -1:
            return 0.0
        return -0.3

    if seniority_intent == "stay_lateral":
        if delta >= 3:
            return 0.1
        if delta == 2:
            return 0.2
        if delta == 1:
            return 0.5
        if delta == 0:
            return 0.8
        if delta == -1:
            return 0.2
        return -0.3

    # "open" or None
    if delta >= 3:
        return 0.2
    if delta == 2:
        return 0.6
    if delta == 1:
        return 1.0
    if delta == 0:
        return 0.5
    if delta == -1:
        return 0.0
    return -0.3


# ---------------------------------------------------------------------------
# Role profile builder
# ---------------------------------------------------------------------------


def _build_role_profile(
    hot_tech_names: set[str],
    generic_skills: list[Skill],
) -> list[tuple[str, float]]:
    """Merge hot tech tools and important generic skills into one importance-weighted pool."""
    items: list[tuple[str, float]] = [
        (name, _HOT_TECH_IMPORTANCE) for name in hot_tech_names
    ]
    items += [
        (s.name, s.importance)
        for s in generic_skills
        if s.importance >= _GENERIC_IMPORTANCE_THRESHOLD
    ]
    return items


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def _batch_embed(texts: list[str], client) -> None:
    """Fetch embeddings for any texts not already in _EMBED_CACHE.

    Batches all missing texts into a single API call.  Silently no-ops on any
    API failure — callers receive 0 similarity for uncached texts.
    """
    missing = [t for t in texts if t not in _EMBED_CACHE]
    if not missing:
        return
    try:
        resp = client.embeddings.create(model="text-embedding-3-small", input=missing)
        evict_count = max(0, len(_EMBED_CACHE) + len(missing) - _EMBED_CACHE_MAX)
        for _ in range(evict_count):
            _EMBED_CACHE.popitem(last=False)
        for item in resp.data:
            _EMBED_CACHE[missing[item.index]] = item.embedding
    except Exception:
        _log.warning("embedding API call failed (%d texts)", len(missing), exc_info=True)


# ---------------------------------------------------------------------------
# Semantic overlap scoring
# ---------------------------------------------------------------------------


def _find_matched_skills(
    user_skills: list[UserSkill],
    role_items: list[tuple[str, float]],
) -> list[str]:
    """Return user skill names whose best cosine similarity to any role item >= _EMBED_THRESHOLD.

    Precondition: _batch_embed has been called for all texts.
    Used for UI display only — does not affect the centroid score.
    """
    available_role = [
        (name, _EMBED_CACHE[name])
        for name, _ in role_items
        if name in _EMBED_CACHE
    ]
    if not available_role:
        return []

    matched: list[str] = []
    for us in user_skills:
        user_emb = _EMBED_CACHE.get(us.name.lower())
        if user_emb is None:
            continue
        best_sim = max(
            (_cosine_similarity(user_emb, role_emb) for _, role_emb in available_role),
            default=0.0,
        )
        if best_sim >= _EMBED_THRESHOLD:
            matched.append(us.name)
    return matched


def _compute_centroid_score(
    user_skills: list[UserSkill],
    role_items: list[tuple[str, float]],
) -> tuple[float, list[str]]:
    """Cosine similarity between proficiency-weighted user centroid and importance-weighted role centroid.

    Precondition: _batch_embed has been called for all texts.
    Role items not in cache (partial API failure) are silently excluded.
    Returns (centroid_similarity, matched_skill_names_for_display).
    """
    user_vecs, user_weights = [], []
    for us in user_skills:
        emb = _EMBED_CACHE.get(us.name.lower())
        if emb is None:
            continue
        user_vecs.append(emb)
        user_weights.append(_SKILL_LEVEL_WEIGHTS.get(us.level, _SKILL_LEVEL_WEIGHTS["beginner"]))

    if not user_vecs:
        return 0.0, []

    role_vecs, role_weights = [], []
    for name, imp in role_items:
        emb = _EMBED_CACHE.get(name)
        if emb is None:
            continue
        role_vecs.append(emb)
        role_weights.append(imp / 100.0)

    if not role_vecs:
        return 0.0, []

    user_centroid = np.average(np.array(user_vecs), axis=0, weights=np.array(user_weights))
    role_centroid = np.average(np.array(role_vecs), axis=0, weights=np.array(role_weights))

    score = _cosine_similarity(user_centroid.tolist(), role_centroid.tolist())
    matched = _find_matched_skills(user_skills, role_items)
    return score, matched


def _substring_overlap_score(
    user_skills: list[UserSkill],
    onet_items: list[tuple[str, float]],
) -> tuple[float, list[str]]:
    """Fallback bidirectional substring overlap when embeddings are unavailable.

    User-centric denominator: sum of user proficiency weights.
    Contribution per match = proficiency_weight × (importance / 100).
    """
    eligible_user = [s for s in user_skills if len(s.name) >= _MIN_MATCH_LEN]
    eligible_onet = [(name, imp) for name, imp in onet_items if len(name) >= _MIN_MATCH_LEN]
    if not eligible_user or not eligible_onet:
        return 0.0, []

    user_weight_total = sum(
        _SKILL_LEVEL_WEIGHTS.get(us.level, _SKILL_LEVEL_WEIGHTS["beginner"])
        for us in eligible_user
    )
    if user_weight_total == 0:
        return 0.0, []

    weighted_sum = 0.0
    matched: list[str] = []
    matched_onet: set[str] = set()

    for us in eligible_user:
        name_lower = us.name.lower()
        prof_weight = _SKILL_LEVEL_WEIGHTS.get(us.level, _SKILL_LEVEL_WEIGHTS["beginner"])
        for onet_name, imp in eligible_onet:
            if onet_name in matched_onet:
                continue
            onet_lower = onet_name.lower()
            if name_lower in onet_lower or onet_lower in name_lower:
                weighted_sum += prof_weight * (imp / 100.0)
                matched.append(us.name)
                matched_onet.add(onet_name)
                break

    return min(weighted_sum / user_weight_total, 1.0), matched


def _semantic_overlap_score(
    user_skills: list[UserSkill],
    onet_items: list[tuple[str, float]],
    openai_client,
) -> tuple[float, list[str]]:
    """Dispatcher: embedding-based scoring with substring fallback.

    Uses embeddings when openai_client is provided and at least some user skill
    embeddings are available in cache after _batch_embed.  Falls back to
    substring matching otherwise (tests, missing API key, API failure).
    """
    if not onet_items or not user_skills:
        return 0.0, []

    if openai_client is not None:
        all_texts = [s.name.lower() for s in user_skills] + [name for name, _ in onet_items]
        _batch_embed(all_texts, openai_client)
        if (
            any(s.name.lower() in _EMBED_CACHE for s in user_skills)
            and any(name in _EMBED_CACHE for name, _ in onet_items)
        ):
            return _compute_centroid_score(user_skills, onet_items)

    return _substring_overlap_score(user_skills, onet_items)


# ---------------------------------------------------------------------------
# Behavioral profile helpers
# ---------------------------------------------------------------------------


def _build_behavioral_profile(profile: UserProfile) -> str | None:
    """Compose a single descriptive string from completed assessment results.

    Prefers full description text over short label names so the embedding lands
    in the right semantic neighbourhood relative to O*NET work-activity language.
    Returns None if no assessment data is present — callers skip work_style_score.
    """
    parts: list[str] = []
    # Use the rich multi-sentence description when available; fall back to the label.
    if profile.archetype_description:
        parts.append(profile.archetype_description)
    elif profile.archetype:
        parts.append(profile.archetype)
    if profile.focus_type:
        parts.append(profile.focus_type)
    if profile.manager_match:
        parts.append(profile.manager_match)
    parts.extend(profile.work_style_tags)
    return " ".join(parts) if parts else None


def _work_style_similarity(
    behavioral_profile: str,
    work_activities: list[tuple[str, float]],
    openai_client,
) -> float:
    """Cosine similarity between the user's behavioral profile and the role's work activities.

    Embeds behavioral_profile as a single text. Computes importance-weighted centroid
    of work activity embeddings. Returns 0.0 if openai_client is None or embeddings fail.
    """
    if openai_client is None or not work_activities:
        return 0.0
    try:
        all_texts = [behavioral_profile] + [name for name, _ in work_activities]
        _batch_embed(all_texts, openai_client)
        profile_emb = _EMBED_CACHE.get(behavioral_profile)
        if profile_emb is None:
            return 0.0
        activity_vecs, activity_weights = [], []
        for name, imp in work_activities:
            emb = _EMBED_CACHE.get(name)
            if emb is None:
                continue
            activity_vecs.append(emb)
            activity_weights.append(imp / 100.0)
        if not activity_vecs:
            return 0.0
        activity_centroid = np.average(
            np.array(activity_vecs), axis=0, weights=np.array(activity_weights)
        )
        return _cosine_similarity(profile_emb, activity_centroid.tolist())
    except Exception:
        _log.warning("work_style_similarity failed", exc_info=True)
        return 0.0


# ---------------------------------------------------------------------------
# Title normalisation
# ---------------------------------------------------------------------------


def _normalize_title_for_onet(raw_title: str, client) -> str | None:
    """Ask GPT-4o-mini to map a free-form title to an O*NET-searchable equivalent.

    Returns the normalised title string, or None on any error.
    """
    try:
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_NARRATIVE_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": (
                "Map this job title to a clean, standard O*NET occupation title.\n"
                "Example: 'Co-Founder & Full Stack Engineer' → 'Software Developer'\n"
                f"Input: {raw_title}\n"
                "Output (title only):"
            )}],
            max_tokens=20,
            temperature=0,
        )
        normalized = resp.choices[0].message.content.strip().strip('"\'')
        for prefix in ("output:", "title:"):
            if normalized.lower().startswith(prefix):
                normalized = normalized[len(prefix):].strip()
        return normalized or None
    except Exception:
        _log.warning("title normalisation LLM call failed for %r", raw_title, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Zone resolution
# ---------------------------------------------------------------------------


def _resolve_current_zone(
    profile: UserProfile,
    onet_client: OnetClient,
    openai_client=None,
) -> tuple[int, str | None, bool]:
    """Return (current_zone, current_onet_code, zone_resolved).

    Searches O*NET for the user's current title.  If the raw title returns no
    results and openai_client is provided, retries once with an LLM-normalised
    title.  Falls back to zone 1 on first_job status, missing title, or any
    unresolvable case.  zone_resolved is False whenever the zone is a fallback.
    """
    if profile.career_status == "first_job" or not profile.current_title:
        return 1, None, False

    def _search_and_resolve(title: str) -> tuple[int, str | None, bool] | None:
        try:
            occupations = onet_client.search_occupations(title)
        except OnetAPIError:
            return None
        if not occupations:
            return None
        code = occupations[0].code
        try:
            zone = onet_client.get_job_zone(code)
        except OnetAPIError:
            return 1, code, False
        return zone, code, True

    result = _search_and_resolve(profile.current_title)
    if result is not None:
        return result

    if openai_client is not None:
        normalized = _normalize_title_for_onet(profile.current_title, openai_client)
        if normalized:
            result = _search_and_resolve(normalized)
            if result is not None:
                return result

    return 1, None, False


# ---------------------------------------------------------------------------
# Candidate pool
# ---------------------------------------------------------------------------


def _gather_candidates(
    profile: UserProfile,
    onet_client: OnetClient,
    exclude_code: str | None,
) -> list[Occupation]:
    """Build a deduplicated candidate pool by searching O*NET."""
    seen: set[str] = {exclude_code} if exclude_code else set()
    candidates: list[Occupation] = []

    search_terms: list[str] = []
    intent = profile.move_intent

    if intent == "stay_in_field":
        if profile.current_title and profile.career_status != "first_job":
            search_terms.append(profile.current_title)
        for skill in profile.skills[:_SKILL_SEARCH_COUNT]:
            search_terms.append(skill.name)
    elif intent == "fresh_start":
        for skill in profile.skills[:_SKILL_SEARCH_COUNT]:
            search_terms.append(skill.name)
    else:  # "adjacent" or None
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
    openai_client=None,
) -> list[ScoredPath]:
    """Score candidate career paths against *user_profile* and return the top 10.

    Algorithm
    ---------
    1. Resolve the user's current job zone (zone 1 for first-job / unknown).
       When openai_client is provided, retries with LLM-normalised title on
       O*NET search miss.
    2. Build a candidate pool from O*NET keyword searches.
    3. For each candidate, fetch zone, hot tech tools, and generic skills, then:

           role_items    = _build_role_profile(hot_tech_names, generic_skills)
           overlap_score = centroid_similarity(user_centroid, role_centroid)

           zone_score    = _zone_delta_score(...)

           # Weights depend on career_status and zone reliability:
           #   first_job + reliable zone  → skills 0.4 / zone 0.6
           #   experienced + reliable     → skills 0.5 / zone 0.5
           #   unresolvable zone          → skills 1.0 / zone 0.0

           final = skills_w × overlap_score + zone_w × zone_score

    4. Return up to _TOP_N results sorted by score descending.

    Args:
        user_profile:  Career snapshot of the user.
        onet_client:   Authenticated O*NET Web Services client.
        openai_client: Optional OpenAI client for title normalisation and
                       embedding-based skill matching.  When None, falls back
                       to substring matching and raw O*NET title search.
    """
    current_zone, current_code, zone_resolved = _resolve_current_zone(
        user_profile, onet_client, openai_client
    )
    candidates = _gather_candidates(user_profile, onet_client, exclude_code=current_code)

    zone_is_reliable = zone_resolved or user_profile.career_status == "first_job"
    if zone_is_reliable:
        if user_profile.career_status == "first_job":
            skills_w, zone_w = _SKILLS_WEIGHT_FIRST_JOB, _ZONE_WEIGHT_FIRST_JOB
        else:
            skills_w, zone_w = _SKILLS_WEIGHT_EXPERIENCED, _ZONE_WEIGHT_EXPERIENCED
    else:
        skills_w, zone_w = 1.0, 0.0

    behavioral_profile = _build_behavioral_profile(user_profile)
    has_behavioral = behavioral_profile is not None and openai_client is not None

    scored: list[ScoredPath] = []
    _debug: list[dict] = []

    for occ in candidates:
        try:
            zone = onet_client.get_job_zone(occ.code)
            onet_generic_skills: list[Skill] = onet_client.get_skills_profile(occ.code)
            hot_tech_names = onet_client.get_tech_skills(occ.code, hot_only=True)
        except OnetAPIError:
            continue

        role_items = _build_role_profile(hot_tech_names, onet_generic_skills)
        overlap_score, matched_skills = _semantic_overlap_score(
            user_profile.skills, role_items, openai_client
        )

        if not zone_is_reliable and overlap_score == 0.0:
            continue

        zone_score = _zone_delta_score(current_zone, zone, user_profile.seniority_intent)

        occ_has_behavioral = has_behavioral
        work_activities: list[tuple[str, float]] = []
        if occ_has_behavioral:
            try:
                work_activities = [
                    (a.name, a.importance)
                    for a in onet_client.get_work_activities(occ.code)
                    if a.importance >= _WORK_ACTIVITY_IMPORTANCE_THRESHOLD
                ]
            except OnetAPIError:
                occ_has_behavioral = False

        work_style_score = (
            _work_style_similarity(behavioral_profile, work_activities, openai_client)
            if occ_has_behavioral and work_activities
            else 0.0
        )

        if zone_is_reliable and occ_has_behavioral:
            # 0.10 behavioral; remaining 0.90 split evenly between skills and zone.
            raw = 0.45 * overlap_score + 0.45 * zone_score + _WORK_STYLE_WEIGHT * work_style_score
            formula_case = "zone_and_behavioral"
        elif occ_has_behavioral:
            raw = (1.0 - _WORK_STYLE_WEIGHT) * overlap_score + _WORK_STYLE_WEIGHT * work_style_score
            formula_case = "behavioral_only"
        else:
            raw = skills_w * overlap_score + zone_w * zone_score
            formula_case = "standard"

        final_score = round(max(0.0, min(1.0, raw)), 4)

        scored.append(
            ScoredPath(
                onet_code=occ.code,
                title=occ.title,
                score=final_score,
                overlapping_skills=matched_skills,
            )
        )
        generic_count = sum(
            1 for s in onet_generic_skills if s.importance >= _GENERIC_IMPORTANCE_THRESHOLD
        )
        _debug.append({
            "title": occ.title,
            "code": occ.code,
            "zone": zone,
            "zone_score": zone_score,
            "role_item_count": len(role_items),
            "hot_tech_count": len(hot_tech_names),
            "generic_count": generic_count,
            "matched_skills": matched_skills,
            "overlap_score": overlap_score,
            "work_activities_count": len(work_activities) if occ_has_behavioral else None,
            "work_style_score": work_style_score if occ_has_behavioral else None,
            "formula_case": formula_case,
            "final_score": final_score,
        })

    scored.sort(key=lambda p: p.score, reverse=True)
    _debug.sort(key=lambda d: d["final_score"], reverse=True)
    if os.environ.get("SOLVERAH_SCORING_DEBUG"):
        _print_scoring_debug(
            user_profile, current_zone, zone_resolved, zone_is_reliable,
            skills_w, zone_w, has_behavioral, _debug[:3]
        )

    return scored[:_TOP_N]


def _print_scoring_debug(
    profile: UserProfile,
    current_zone: int,
    zone_resolved: bool,
    zone_is_reliable: bool,
    skills_w: float,
    zone_w: float,
    has_behavioral: bool,
    top3_debug: list[dict],
) -> None:
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
        lines.append(
            f"#{rank}  {d['title']}  [{d['code']}]  "
            f"score={d['final_score']:.4f} ({d['final_score']*100:.1f}%)"
        )
        lines.append(
            f"    Role zone: {d['zone']}  |  delta: {d['zone'] - current_zone:+d}"
            f"  |  zone_score: {d['zone_score']:.3f}"
        )
        lines.append(
            f"\n    Role profile: {d['role_item_count']} items"
            f" ({d['hot_tech_count']} hot tech tools"
            f" + {d['generic_count']} generic skills)"
        )
        lines.append(f"    Centroid similarity: {d['overlap_score']:.4f}")
        lines.append(f"    Matched skills: {d['matched_skills']}")
        if has_behavioral and d.get("work_activities_count") is not None:
            lines.append(f"    Work Activities: {d['work_activities_count']} items")
            lines.append(f"    Behavioral similarity: {d['work_style_score']:.4f}")
        case = d.get("formula_case", "standard")
        ws = d.get("work_style_score") or 0.0
        if case == "zone_and_behavioral":
            formula_str = (
                f"0.45×overlap({d['overlap_score']:.4f})"
                f" + 0.45×zone({d['zone_score']:.4f})"
                f" + {_WORK_STYLE_WEIGHT:.2f}×behavioral({ws:.4f})"
                f" = {d['final_score']:.4f}"
            )
        elif case == "behavioral_only":
            formula_str = (
                f"{1.0 - _WORK_STYLE_WEIGHT:.2f}×overlap({d['overlap_score']:.4f})"
                f" + {_WORK_STYLE_WEIGHT:.2f}×behavioral({ws:.4f})"
                f" = {d['final_score']:.4f}"
            )
        else:
            formula_str = (
                f"{skills_w:.2f}×overlap({d['overlap_score']:.4f})"
                f" + {zone_w:.2f}×zone({d['zone_score']:.4f})"
                f" = {d['final_score']:.4f}"
            )
        lines.append(f"\n    final   = {formula_str}")

    lines.append("\n" + "=" * 60)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
