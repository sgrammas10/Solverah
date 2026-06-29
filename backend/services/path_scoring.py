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
  1  (search term generation — maps full skill set to O*NET occupation titles)
  1  (title normalisation, only if raw O*NET search returns no results)
  1–2 (batch embedding of all unique skill/tool strings, cached across requests)

O*NET call count:
  2  (current-zone resolution) + 3 × |candidates| (zone + tech_skills + skills per candidate)
"""
from __future__ import annotations

import json
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

# Role coverage signal: fraction of the K most representative role items the user
# can cover.  "Most representative" = closest to the role's own embedding centroid,
# so comparison targets self-calibrate per role (concrete tools for tech roles,
# abstract competencies for non-tech roles).  Uses the same threshold as other
# embedding matches since we're now comparing like-to-like.
_COVERAGE_TOP_K: int = 5
_CENTROID_MIX: float = 0.35
_COVERAGE_MIX: float = 0.65

# In-process embedding cache.  OrderedDict enables O(1) LRU eviction.
_EMBED_CACHE: OrderedDict[str, list[float]] = OrderedDict()
_EMBED_CACHE_MAX: int = 10_000

# SOC code prefixes for life/physical/social-science occupations.
# These appear as keyword-search noise (searching "Data Scientists" returns
# Bioinformatics Scientists, Political Scientists, etc.) and are excluded from
# the candidate pool unless the user's skills indicate life-science expertise.
_LIFE_SCIENCE_SOC_PREFIXES: tuple[str, ...] = ("19-1", "19-2", "19-3", "19-4")

# Skill keywords that indicate the user has genuine life-science expertise.
_LIFE_SCIENCE_SKILL_KEYWORDS: frozenset[str] = frozenset({
    "biology", "chemistry", "biochemistry", "molecular biology", "genetics",
    "ecology", "geology", "meteorology", "physics", "microbiology",
    "anatomy", "physiology", "pharmacology", "lab", "laboratory",
})

# Accumulated LLM interaction log for the current score_paths invocation.
_LLM_DEBUG_LOG: list[str] = []


def _llm_log(section: str, content: str) -> None:
    _LLM_DEBUG_LOG.append(f"\n{'='*60}\n{section}\n{'='*60}\n{content}")


def _write_llm_debug_log() -> None:
    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "llm_debug.txt")
    out_path = os.path.normpath(out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(_LLM_DEBUG_LOG))
    _LLM_DEBUG_LOG.clear()


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
    priority: Literal["pay_title", "interesting_work", "work_life_balance", "learning_growth"] | None = None
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


def _role_coverage_score(
    user_skills: list[UserSkill],
    role_items: list[tuple[str, float]],
) -> float:
    """Coverage measured from the user's perspective.

    Finds the K user skills most similar to the role's centroid — the user's
    "best fits" for this role — then checks what fraction of those skills the
    role actually values at _EMBED_THRESHOLD.  A full-stack engineer's React/Python
    skills score high coverage against Software Developers (1.0) but near-zero
    against Atmospheric Scientists (0.0), spreading what the centroid compresses.

    Uses _EMBED_CACHE directly — call after _semantic_overlap_score has already
    populated the cache.  Returns 0.0 gracefully when no embeddings are available.
    """
    available_role = [
        (name, emb)
        for name, _ in role_items
        if (emb := _EMBED_CACHE.get(name)) is not None
    ]
    if not available_role:
        return 0.0

    available_user = [
        (us, emb)
        for us in user_skills
        if (emb := _EMBED_CACHE.get(us.name.lower())) is not None
    ]
    if not available_user:
        return 0.0

    role_centroid = np.mean([np.array(emb) for _, emb in available_role], axis=0)
    role_centroid_list = role_centroid.tolist()

    # Find the user's top-K skills most similar to this role's centroid.
    user_with_sims = sorted(
        [
            (us, emb, _cosine_similarity(emb, role_centroid_list))
            for us, emb in available_user
        ],
        key=lambda x: x[2],
        reverse=True,
    )
    top_k = user_with_sims[:_COVERAGE_TOP_K]

    # For each top-K user skill, check whether the role values it.
    matched = 0
    for _us, skill_emb, sim_to_centroid in top_k:
        if sim_to_centroid < _EMBED_THRESHOLD:
            continue  # user skill doesn't align with this role at all
        best_role_match = max(
            _cosine_similarity(skill_emb, r_emb) for _, r_emb in available_role
        )
        if best_role_match >= _EMBED_THRESHOLD:
            matched += 1

    return matched / len(top_k) if top_k else 0.0


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
    prompt = (
        "Map this job title to a standard O*NET occupation title.\n"
        "Use exact O*NET-style titles (e.g. 'Software Developers', 'Web Developers',\n"
        "'General and Operations Managers', 'Computer and Information Systems Managers').\n"
        "Use plural form as O*NET uses plural occupation names.\n"
        "No explanation. Output the title only.\n\n"
        "Examples:\n"
        "  'Co-Founder & CTO' → 'Computer and Information Systems Managers'\n"
        "  'Founder & Full Stack Engineer' → 'Software Developers'\n"
        "  'Senior Data Analyst' → 'Data Scientists'\n"
        "  'Head of Growth' → 'Marketing Managers'\n\n"
        f"Input: {raw_title}\n"
        "Output:"
    )
    try:
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_NARRATIVE_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0,
        )
        normalized = resp.choices[0].message.content.strip().strip('"\'')
        for prefix in ("output:", "title:"):
            if normalized.lower().startswith(prefix):
                normalized = normalized[len(prefix):].strip()
        _llm_log(
            "ZONE RESOLUTION — Title Normalization",
            f"Raw title input : {raw_title!r}\n"
            f"Prompt sent     :\n{prompt}\n"
            f"Raw LLM response: {resp.choices[0].message.content!r}\n"
            f"Parsed output   : {normalized!r}",
        )
        return normalized or None
    except Exception as exc:
        _llm_log(
            "ZONE RESOLUTION — Title Normalization FAILED",
            f"Raw title: {raw_title!r}\nError    : {exc!r}",
        )
        _log.warning("title normalisation LLM call failed for %r", raw_title, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Search term generation
# ---------------------------------------------------------------------------


def _generate_search_terms(profile: UserProfile, client) -> list[str]:
    """Return O*NET-searchable occupation titles spanning the profile's skill domains.

    When client is provided, one LLM call maps the full skill set to 5–7 occupation
    titles that cover distinct domains (ML Engineer, Security Analyst, Data Engineer,
    etc.) rather than searching by raw skill names.  Falls back to title + first-N-skills
    when client is None or the call fails.
    """
    def _fallback() -> list[str]:
        terms: list[str] = []
        if (
            profile.current_title
            and profile.career_status != "first_job"
            and profile.move_intent != "fresh_start"
        ):
            terms.append(profile.current_title)
        for skill in profile.skills[:_SKILL_SEARCH_COUNT]:
            terms.append(skill.name)
        return terms

    if client is None:
        return _fallback()

    prompt = f"""You are a career advisor with knowledge of O*NET occupations.

Analyze the skills below and identify the distinct career domains they represent.
For each domain, output ONE standard O*NET occupation title.

Rules:
- Use exact O*NET-style titles (e.g. "Software Developers", "Information Security Analysts", "Registered Nurses", "Data Scientists")
- Target industry-practical roles, NOT academic research roles (not "Bioinformatics Scientists", not "Remote Sensing Scientists")
- Do NOT infer niche specializations (blockchain, quantum computing, biotech) unless the user lists core specialized skills for that field (e.g. Solidity for blockchain, lab techniques for biotech)
- Cover ALL distinct domains present — if the user has both programming skills AND security skills, include both
- Output ONLY a JSON array of strings, no explanation

Current title: {profile.current_title or "Not provided"}
Skills: {", ".join(s.name for s in profile.skills)}

Output:"""

    _llm_log(
        "SEARCH TERM GENERATION — LLM Input",
        f"Current title: {profile.current_title!r}\n"
        f"Skills ({len(profile.skills)}): {', '.join(s.name for s in profile.skills)}\n\n"
        f"Full prompt:\n{prompt}",
    )

    raw = ""
    try:
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_NARRATIVE_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw[raw.index("\n") + 1:] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:raw.rindex("```")].rstrip()
        raw = raw.strip()
        terms = json.loads(raw)
        if isinstance(terms, list) and terms and all(isinstance(t, str) for t in terms):
            cleaned = [t.strip() for t in terms if t.strip()]
            if cleaned:
                _log.debug("_generate_search_terms → %s", cleaned)
                _llm_log(
                    "SEARCH TERM GENERATION — LLM Output",
                    f"Raw response : {raw!r}\nParsed terms : {cleaned}",
                )
                return cleaned
    except json.JSONDecodeError as exc:
        fallback = _fallback()
        _llm_log(
            "SEARCH TERM GENERATION — Parse Failed, Using Fallback",
            f"Raw response : {raw!r}\nError        : {exc!r}\nFallback     : {fallback}",
        )
        _log.warning("_generate_search_terms: LLM returned invalid JSON", exc_info=True)
        return fallback
    except Exception as exc:
        fallback = _fallback()
        _llm_log(
            "SEARCH TERM GENERATION — Parse Failed, Using Fallback",
            f"Raw response : {raw!r}\nError        : {exc!r}\nFallback     : {fallback}",
        )
        _log.warning("_generate_search_terms LLM call failed", exc_info=True)
        return fallback

    fallback = _fallback()
    _llm_log(
        "SEARCH TERM GENERATION — Parse Failed, Using Fallback",
        f"Raw response : {raw!r}\nError        : (empty or invalid list)\nFallback     : {fallback}",
    )
    return fallback


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
            _llm_log(
                "ZONE RESOLUTION — O*NET Search Result",
                f"Search term  : {title!r}\nO*NET found  : False (API error)",
            )
            return None
        _llm_log(
            "ZONE RESOLUTION — O*NET Search Result",
            f"Search term  : {title!r}\n"
            f"O*NET found  : {bool(occupations)}\n"
            f"First result : "
            f"{(occupations[0].title + ' [' + occupations[0].code + ']') if occupations else 'N/A'}",
        )
        if not occupations:
            return None
        code = occupations[0].code
        try:
            zone = onet_client.get_job_zone(code)
        except OnetAPIError:
            return 1, code, False
        return zone, code, True

    # Save the raw result separately so LLM search assignments don't overwrite it.
    raw_result = _search_and_resolve(profile.current_title)
    # Only accept the raw match when O*NET returned a reliable zone.
    # When reliable=False (get_job_zone raised), fall through to LLM normalization
    # so a title like "Founder & Full Stack Engineer" → "Engineers, All Other" (zone fail)
    # still gets a second chance instead of being stuck at zone=1.
    if raw_result is not None and raw_result[2]:
        _llm_log(
            "ZONE RESOLUTION — Final Outcome",
            f"zone={raw_result[0]}  resolved={raw_result[2]}  reliable={raw_result[2]}\n"
            f"onet_code={raw_result[1]!r}",
        )
        return raw_result

    if openai_client is not None:
        normalized = _normalize_title_for_onet(profile.current_title, openai_client)
        if normalized:
            norm_result = _search_and_resolve(normalized)
            if norm_result is not None:
                _llm_log(
                    "ZONE RESOLUTION — Final Outcome",
                    f"zone={norm_result[0]}  resolved={norm_result[2]}  reliable={norm_result[2]}\n"
                    f"onet_code={norm_result[1]!r}",
                )
                return norm_result

        # Second attempt: broad category fallback prompt when first normalized title also misses.
        try:
            fallback_prompt = (
                f"What is the closest standard job category for: {profile.current_title}\n"
                "Reply with only a common job title, one of: Software Developers, "
                "Web Developers, Data Scientists, Registered Nurses, Accountants, "
                "Marketing Managers, Sales Representatives, Teachers, Engineers.\n"
                "Output:"
            )
            resp = openai_client.chat.completions.create(
                model=os.environ.get("OPENAI_NARRATIVE_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": fallback_prompt}],
                max_tokens=20,
                temperature=0,
            )
            broad = resp.choices[0].message.content.strip().strip('"\'')
            _llm_log(
                "ZONE RESOLUTION — Broad Category Fallback",
                f"Raw title : {profile.current_title!r}\n"
                f"Prompt    :\n{fallback_prompt}\n"
                f"LLM output: {broad!r}",
            )
            if broad:
                broad_result = _search_and_resolve(broad)
                if broad_result is not None:
                    _llm_log(
                        "ZONE RESOLUTION — Final Outcome",
                        f"zone={broad_result[0]}  resolved={broad_result[2]}  reliable={broad_result[2]}\n"
                        f"onet_code={broad_result[1]!r}",
                    )
                    return broad_result
        except Exception:
            _log.warning(
                "broad category fallback LLM call failed for %r",
                profile.current_title,
                exc_info=True,
            )

    # All LLM attempts exhausted. Fall back to the unreliable raw match if one
    # was found — preserves the code so the current role is excluded from candidates.
    if raw_result is not None:
        _llm_log(
            "ZONE RESOLUTION — Final Outcome (raw unreliable fallback)",
            f"zone={raw_result[0]}  resolved={raw_result[2]}  reliable={raw_result[2]}\n"
            f"onet_code={raw_result[1]!r}",
        )
        return raw_result

    _llm_log(
        "ZONE RESOLUTION — Final Outcome",
        "zone=1  resolved=False  reliable=False\nonet_code=None",
    )
    return 1, None, False


# ---------------------------------------------------------------------------
# Candidate pool
# ---------------------------------------------------------------------------


def _infer_user_has_life_science(profile: UserProfile) -> bool:
    skill_names = {s.name.lower() for s in profile.skills}
    return bool(skill_names & _LIFE_SCIENCE_SKILL_KEYWORDS)


def _filter_candidate_pool(
    candidates: list[Occupation],
    profile: UserProfile,
) -> list[Occupation]:
    """Remove life/physical/social-science roles unless the user has domain skills.

    O*NET keyword search is fuzzy: searching "Data Scientists" returns Bioinformatics
    Scientists, Political Scientists, Atmospheric Scientists, etc.  These are almost
    always irrelevant for software/business users and pollute the scored pool.
    Keep them only when the user's skills indicate genuine life-science expertise.
    """
    if _infer_user_has_life_science(profile):
        return candidates
    return [
        occ for occ in candidates
        if not any(occ.code.startswith(prefix) for prefix in _LIFE_SCIENCE_SOC_PREFIXES)
    ]


def _deduplicate(occupations: list[Occupation], exclude_code: str | None) -> list[Occupation]:
    """Return occupations with duplicates removed and *exclude_code* filtered out."""
    seen: set[str] = {exclude_code} if exclude_code else set()
    result: list[Occupation] = []
    for occ in occupations:
        if occ.code not in seen:
            seen.add(occ.code)
            result.append(occ)
    return result


def _profile_seeded_candidates(
    profile: UserProfile,
    onet_client: OnetClient,
    openai_client,
) -> list[Occupation]:
    """Search O*NET using LLM-generated occupation titles that span skill domains."""
    search_terms = _generate_search_terms(profile, openai_client)
    candidates: list[Occupation] = []
    for term in search_terms:
        try:
            results = onet_client.search_occupations(term)
            _log.debug("O*NET search %r → %d results", term, len(results))
            _llm_log(
                f"CANDIDATE SEARCH — Term: {term!r}",
                f"Results ({len(results)}): {[o.title for o in results]}",
            )
            candidates.extend(results)
        except OnetAPIError as exc:
            _log.warning("O*NET search failed for %r: %s", term, exc)
    _llm_log(
        "CANDIDATE POOL — Final",
        f"Total candidates: {len(candidates)}\n"
        + "\n".join(f"  [{o.code}] {o.title}" for o in candidates),
    )
    return candidates


def _gather_candidates(
    profile: UserProfile,
    onet_client: OnetClient,
    openai_client,
    current_code: str | None,
) -> list[Occupation]:
    """Build an intent-driven, deduplicated candidate pool.

    fresh_start  → Bright Outlook occupations (forward-looking pool).
                   Falls back to profile-seeded search if Bright Outlook is empty.
    adjacent     → Profile-seeded search + all occupations in the user's SOC family.
    stay_in_field / None → Profile-seeded search (keyword search on generated titles).
    """
    if profile.move_intent == "fresh_start":
        candidates = onet_client.get_bright_outlook_occupations()
        if not candidates:
            candidates = _profile_seeded_candidates(profile, onet_client, openai_client)
        return _filter_candidate_pool(_deduplicate(candidates, current_code), profile)

    if profile.move_intent == "adjacent":
        candidates = _profile_seeded_candidates(profile, onet_client, openai_client)
        if current_code:
            try:
                families = onet_client.get_job_families()
                user_soc_prefix = current_code[:2]
                for family in families:
                    if family["code"].startswith(user_soc_prefix):
                        family_occs = onet_client.get_job_family_occupations(family["code"])
                        candidates.extend(family_occs)
                        break
            except OnetAPIError:
                pass
        return _filter_candidate_pool(_deduplicate(candidates, current_code), profile)

    # stay_in_field or None
    candidates = _profile_seeded_candidates(profile, onet_client, openai_client)
    return _deduplicate(candidates, current_code)


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
    _LLM_DEBUG_LOG.clear()

    current_zone, current_code, zone_resolved = _resolve_current_zone(
        user_profile, onet_client, openai_client
    )
    candidates = _gather_candidates(user_profile, onet_client, openai_client, current_code)

    behavioral_profile = _build_behavioral_profile(user_profile)
    has_behavioral = behavioral_profile is not None and openai_client is not None

    _llm_log(
        "BEHAVIORAL PROFILE — Composed String",
        f"archetype      : {user_profile.archetype!r}\n"
        f"focus_type     : {user_profile.focus_type!r}\n"
        f"manager_match  : {user_profile.manager_match!r}\n"
        f"work_style_tags: {user_profile.work_style_tags}\n\n"
        f"Composed string:\n{behavioral_profile or '(None — no assessment data)'}",
    )

    zone_is_reliable = zone_resolved or user_profile.career_status == "first_job"
    growth_focused = user_profile.priority in ("learning_growth", "pay_title")

    if zone_is_reliable and has_behavioral:
        if growth_focused:
            skills_w, zone_w, style_w = 0.30, 0.50, 0.20
        else:
            skills_w, zone_w, style_w = 0.40, 0.40, 0.20
    elif zone_is_reliable:
        if growth_focused:
            skills_w, zone_w = 0.35, 0.65
        else:
            skills_w, zone_w = _SKILLS_WEIGHT_EXPERIENCED, _ZONE_WEIGHT_EXPERIENCED
        style_w = 0.0
    elif has_behavioral:
        skills_w, zone_w, style_w = 0.75, 0.00, 0.25
    else:
        skills_w, zone_w, style_w = 1.0, 0.0, 0.0

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
        centroid_score, matched_skills = _semantic_overlap_score(
            user_profile.skills, role_items, openai_client
        )

        if openai_client is not None:
            coverage_score = _role_coverage_score(user_profile.skills, role_items)
            overlap_score = _CENTROID_MIX * centroid_score + _COVERAGE_MIX * coverage_score
        else:
            coverage_score = 0.0
            overlap_score = centroid_score

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

        if occ_has_behavioral:
            raw = skills_w * overlap_score + zone_w * zone_score + style_w * work_style_score
            formula_case = "with_behavioral"
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
            "centroid_score": centroid_score,
            "coverage_score": coverage_score,
            "overlap_score": overlap_score,
            "work_activities_count": len(work_activities) if occ_has_behavioral else None,
            "work_style_score": work_style_score if occ_has_behavioral else None,
            "formula_case": formula_case,
            "final_score": final_score,
        })

    scored.sort(key=lambda p: p.score, reverse=True)
    _debug.sort(key=lambda d: d["final_score"], reverse=True)

    _llm_log(
        "CANDIDATE SCORES — Top 5 Detail",
        "\n".join(
            f"  [{d['code']}] {d['title']}\n"
            f"    centroid={d['centroid_score']:.4f}  coverage={d['coverage_score']:.4f}\n"
            f"    work_style={(d.get('work_style_score') or 0.0):.4f}  zone={d['zone_score']:.4f}\n"
            f"    final={d['final_score']:.4f}"
            for d in _debug[:5]
        ) or "(no candidates scored)",
    )

    if os.environ.get("SOLVERAH_SCORING_DEBUG"):
        _print_scoring_debug(
            user_profile, current_zone, zone_resolved, zone_is_reliable,
            skills_w, zone_w, style_w, growth_focused, has_behavioral,
            openai_client is not None, _debug[:3]
        )

    _write_llm_debug_log()
    return scored[:_TOP_N]


def _print_scoring_debug(
    profile: UserProfile,
    current_zone: int,
    zone_resolved: bool,
    zone_is_reliable: bool,
    skills_w: float,
    zone_w: float,
    style_w: float,
    growth_focused: bool,
    has_behavioral: bool,
    has_openai: bool,
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
    lines.append(f"Weights    : skills={skills_w:.2f}  zone={zone_w:.2f}  style={style_w:.2f}")
    lines.append(f"Intent     : move={profile.move_intent}  seniority={profile.seniority_intent}  priority={profile.priority}")
    lines.append(f"Growth focused: {growth_focused}")
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
        lines.append(f"    Centroid similarity: {d['centroid_score']:.4f}")
        if d.get("coverage_score") is not None and has_openai:
            lines.append(f"    Coverage score    : {d['coverage_score']:.4f}")
            lines.append(
                f"    Overlap = {_CENTROID_MIX:.1f}×centroid({d['centroid_score']:.4f})"
                f" + {_COVERAGE_MIX:.1f}×coverage({d['coverage_score']:.4f})"
                f" = {d['overlap_score']:.4f}"
            )
        lines.append(f"    Matched skills: {d['matched_skills']}")
        if has_behavioral and d.get("work_activities_count") is not None:
            lines.append(f"    Work Activities: {d['work_activities_count']} items")
            lines.append(f"    Behavioral similarity: {d['work_style_score']:.4f}")
        case = d.get("formula_case", "standard")
        ws = d.get("work_style_score") or 0.0
        if case == "with_behavioral":
            formula_str = (
                f"{skills_w:.2f}×overlap({d['overlap_score']:.4f})"
                f" + {zone_w:.2f}×zone({d['zone_score']:.4f})"
                f" + {style_w:.2f}×behavioral({ws:.4f})"
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
