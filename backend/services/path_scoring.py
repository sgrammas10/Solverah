"""Semantic career path scoring algorithm.

Ranks O*NET occupations against a user's profile using a weighted sum of:
  (a) semantic skill overlap — embedding-based similarity between user skills
      and O*NET technology tools (hot-only) + generic competency skills,
      weighted by O*NET importance score and user proficiency level.
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

# Within the skill signal: how tech vs. generic competency scores are blended.
_TECH_MIX: float = 0.6
_GENERIC_MIX: float = 0.4

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

# Tech tools from O*NET have no per-tool importance score — treat all uniformly.
# 75 = high but not max, since any individual tool is rarely a requirement for every
# practitioner in the role.
_TECH_TOOL_IMPORTANCE: float = 75.0

# Generic skills with importance below this threshold are excluded from scoring
# to reduce noise from peripheral competencies.
_GENERIC_IMPORTANCE_THRESHOLD: float = 50.0

# Cosine similarity threshold for an embedding match to count.
_EMBED_THRESHOLD: float = 0.70

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


def _semantic_score_via_embeddings(
    user_skills: list[UserSkill],
    onet_items: list[tuple[str, float]],
) -> tuple[float, list[str]]:
    """Compute user-centric overlap score using cached embeddings.

    Precondition: _batch_embed has been called for all texts.
    O*NET items not in cache (partial API failure) are silently skipped.

    For each user skill, finds the single O*NET item with highest cosine
    similarity (greedy; one ONET item can match multiple user skills).
    Match counts only when similarity >= _EMBED_THRESHOLD.

    Denominator = sum of all user proficiency weights (user-centric: "what
    fraction of YOUR skills apply to this role").
    Contribution per match = proficiency_weight × (onet_importance / 100).
    """
    user_weight_total = sum(
        _SKILL_LEVEL_WEIGHTS.get(us.level, _SKILL_LEVEL_WEIGHTS["beginner"])
        for us in user_skills
    )
    if user_weight_total == 0:
        return 0.0, []

    available_onet = [
        (name, imp, emb)
        for name, imp in onet_items
        if (emb := _EMBED_CACHE.get(name)) is not None
    ]
    if not available_onet:
        return 0.0, []

    weighted_sum = 0.0
    matched: list[str] = []

    for us in user_skills:
        user_emb = _EMBED_CACHE.get(us.name.lower())
        if user_emb is None:
            continue
        prof_weight = _SKILL_LEVEL_WEIGHTS.get(us.level, _SKILL_LEVEL_WEIGHTS["beginner"])

        best_sim, best_imp = 0.0, 0.0
        for _, imp, onet_emb in available_onet:
            sim = _cosine_similarity(user_emb, onet_emb)
            if sim > best_sim:
                best_sim, best_imp = sim, imp

        if best_sim >= _EMBED_THRESHOLD:
            weighted_sum += prof_weight * (best_imp / 100.0)
            matched.append(us.name)

    return min(weighted_sum / user_weight_total, 1.0), matched


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
        if any(s.name.lower() in _EMBED_CACHE for s in user_skills):
            return _semantic_score_via_embeddings(user_skills, onet_items)

    return _substring_overlap_score(user_skills, onet_items)


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

           tech_score    = semantic_overlap(user_skills, hot_tech_items)
           generic_score = semantic_overlap(user_skills, important_generic_items)
           overlap_score = 0.6 × tech_score + 0.4 × generic_score

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

    scored: list[ScoredPath] = []
    _debug: list[dict] = []

    for occ in candidates:
        try:
            zone = onet_client.get_job_zone(occ.code)
            onet_generic_skills: list[Skill] = onet_client.get_skills_profile(occ.code)
            tech_names = onet_client.get_tech_skills(occ.code)
        except OnetAPIError:
            continue

        tech_items: list[tuple[str, float]] = [(name, _TECH_TOOL_IMPORTANCE) for name in tech_names]
        generic_items: list[tuple[str, float]] = [
            (s.name, s.importance)
            for s in onet_generic_skills
            if s.importance >= _GENERIC_IMPORTANCE_THRESHOLD
        ]

        tech_score, tech_matched = _semantic_overlap_score(
            user_profile.skills, tech_items, openai_client
        )
        generic_score, generic_matched = _semantic_overlap_score(
            user_profile.skills, generic_items, openai_client
        )

        overlap_score = _TECH_MIX * tech_score + _GENERIC_MIX * generic_score
        matched_skills = list(dict.fromkeys(tech_matched + generic_matched))

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
            "tech_items": sorted(name for name, _ in tech_items),
            "generic_score": generic_score,
            "generic_matched": generic_matched,
            "generic_items": [(s.name, s.importance) for s in onet_generic_skills],
            "overlap_score": overlap_score,
            "final_score": final_score,
        })

    scored.sort(key=lambda p: p.score, reverse=True)
    _debug.sort(key=lambda d: d["final_score"], reverse=True)
    _print_scoring_debug(
        user_profile, current_zone, zone_resolved, zone_is_reliable,
        skills_w, zone_w, _debug[:3]
    )

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
    import os as _os
    out_path = _os.path.join(_os.path.dirname(__file__), "..", "..", "scoring_debug.txt")
    out_path = _os.path.normpath(out_path)
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
        lines.append(f"\n    --- TECH TOOLS ({len(d['tech_items'])} total) ---")
        for tool in d["tech_items"]:
            lines.append(f"      {tool}")
        lines.append(f"    Tech matched: {d['tech_matched']}  →  tech_score={d['tech_score']:.4f}")
        lines.append(f"\n    --- GENERIC SKILLS (importance ≥ {_GENERIC_IMPORTANCE_THRESHOLD}) ---")
        for name, imp in sorted(d["generic_items"], key=lambda x: -x[1]):
            marker = "  *" if imp >= _GENERIC_IMPORTANCE_THRESHOLD else ""
            lines.append(f"      {name:<40} importance={imp:.1f}{marker}")
        lines.append(
            f"    Generic matched: {d['generic_matched']}  →  generic_score={d['generic_score']:.4f}"
        )
        lines.append(
            f"\n    overlap = {_TECH_MIX:.1f}×tech({d['tech_score']:.4f})"
            f" + {_GENERIC_MIX:.1f}×generic({d['generic_score']:.4f})"
            f" = {d['overlap_score']:.4f}"
        )
        lines.append(
            f"    final   = {skills_w:.2f}×overlap({d['overlap_score']:.4f})"
            f" + {zone_w:.2f}×zone({d['zone_score']:.4f})"
            f" = {d['final_score']:.4f}"
        )

    lines.append("\n" + "=" * 60)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
