"""Tier-2 deep fit: the full analysis of ONE occupation, run on click (F-5).

WHY THIS MODULE EXISTS
----------------------
``path_scoring`` is Tier 1.  Since F-4 it retrieves a ten-card shortlist out of
the 1,016-row corpus with **zero** per-candidate O*NET calls, because the
per-candidate fan-out that used to serve those signals is what produced the
2026-09-15 production OOM and ~160 HTTP requests per cold run.

The per-occupation *analysis* those calls fed was never wrong -- it was wrong to
run it forty times to show ten cards.  Design doc §2.3 (Sebastian, 2026-09-16)
is the fix: keep the analysis, spend it on the one occupation the user clicked.
The budget Tier 1 used to spread across ~40 candidates now goes to one, so the
analysis gets **better**, not merely rarer:

    per click      O*NET   0   W-9: the four answers are static per occupation
                                and now live in ``<artifact>.fit.json``.
                                Without the sidecar, or for a code it lacks,
                                it is 4 again: get_skills_profile,
                                get_hot_technologies, get_work_activities,
                                get_tasks -- all ``_OCC_CACHE``-backed (24h)
                   OpenAI  1   one batched embedding request
                   LLM     0   see "NARRATIVE" below

    Tier 1 cold    O*NET   0   (F-4; was ~160)

THE SIX FUNCTIONS BELOW CAME FROM ``path_scoring`` UNCHANGED.
F-4 left ``_build_role_profile``, ``_find_matched_skills``,
``_compute_centroid_score``, ``_compute_weighted_user_centroid``,
``_role_coverage_score`` and ``_work_style_similarity`` in that module,
uncalled, parked for this chunk.  They are here now with their maths and their
constants byte-identical, and their names are in
``tests/test_path_scoring.py::TestTombstones`` so they cannot drift back --
``path_scoring`` is Tier 1 only.

WHY THE CENTROID IS LEGITIMATE HERE AND WAS NOT IN TIER 1
---------------------------------------------------------
Design doc §1.1: O*NET's Skills taxonomy is a fixed ~35 elements that *every*
occupation carries, so across a candidate *pool* the centroid comparison
averages the discriminating signal away before any weight is applied.  Against
a **single** occupation the user has chosen to look at there is no pool to
average across: "how much of what this role rates highly do you already have"
is a statement about that one role, and the ~35 constants are the vocabulary
the answer is phrased in rather than noise drowning a ranking.

NARRATIVE: DELIBERATELY DEFERRED
--------------------------------
``path_narrative.generate_narratives`` is a *selection* prompt -- it takes the
scored shortlist and picks 2-3 -- so there is no per-path entry point to reuse
for one occupation, and reaching for it here would mean a new LLM call on every
click.  That is a latency and spend decision, not an implementation detail, so
this chunk ships the deterministic analysis only.  :attr:`DeepFit.narrative` is
present and always ``None`` so the wire shape does not have to change when it
lands.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

from backend.services import occupation_fit
from backend.services.occupation_retrieval import (
    CorpusUnavailable,
    OccupationCorpus,
    get_corpus,
    is_all_other_title,
)
from backend.services.onet_client import (
    OnetAPIError,
    OnetClient,
    OnetRateLimitError,
    Skill,
)
from backend.services.path_scoring import (
    InsufficientProfile,
    UserProfile,
    UserSkill,
    _EMBED_CACHE,
    _batch_embed,
    _build_behavioral_profile,
    _build_query,
    _cosine_similarity,
    _embed_one,
    _compose_profile_document,
    _compose_skills_document,
    _compose_title_document,
    _has_any_signal,
    _rescale_cosine,
    _resolve_current_zone,
    _weights,
    _zone_delta_score,
)

__all__ = [
    "CorpusUnavailable",
    "DeepFit",
    "SkillGap",
    "UnknownOccupation",
    "ZoneFit",
    "deep_fit",
    "skill_aliases",
]

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants -- moved from path_scoring unchanged (they served only Tier 2)
# ---------------------------------------------------------------------------

_SKILL_LEVEL_WEIGHTS: dict[str, float] = {
    "beginner": 0.33,
    "intermediate": 0.67,
    "advanced": 1.0,
}

# Cosine similarity threshold for an embedding match to count.
#
# Deliberately UNCHANGED by F-8 box 5. It is too strict for O*NET's verbose
# names, but there is no Tier-2 evaluation harness, so a threshold moved by
# feel is a number nothing can falsify. What box 5 changed instead is that
# the two list-producing functions settle IDENTITY before asking this
# question at all -- see `skill_aliases`.
_EMBED_THRESHOLD: float = 0.70

# Hot tech tools from O*NET have no per-tool importance score.
_HOT_TECH_IMPORTANCE: float = 75.0

# Generic skills below this importance are excluded from scoring.
_GENERIC_IMPORTANCE_THRESHOLD: float = 50.0

# Work activity importance threshold.
_WORK_ACTIVITY_IMPORTANCE_THRESHOLD: float = 50.0

# Role coverage signal top-K.
_COVERAGE_TOP_K: int = 5
_CENTROID_MIX: float = 0.5
_COVERAGE_MIX: float = 0.5


# ---------------------------------------------------------------------------
# Constants -- this chunk's own
# ---------------------------------------------------------------------------

#: O*NET-SOC, e.g. ``15-1252.00``.  Anything else is a malformed request rather
#: than a miss, and the caller tells the two apart -- see :class:`UnknownOccupation`.
_ONET_CODE_RE = re.compile(r"^\d{2}-\d{4}\.\d{2}$")

#: How much of the occupation to hand the UI.  Tasks arrive importance-sorted
#: from ``get_tasks``; hot technologies arrive ranked by the share of job
#: postings mentioning them (``get_hot_technologies``), so "top N" is meaningful
#: for both and neither needs re-sorting here.
_TOP_TASKS: int = 8
_TOP_TECH: int = 12

#: Gaps are the point of the panel, but a list of twenty is a wall, not advice.
_TOP_GAPS: int = 8


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Skill-name normalisation (BUILD_PLAN F-8 box 5)
# ---------------------------------------------------------------------------
#
# THE DEFECT, AS A USER SAW IT.  Somebody who listed "SQL" was told that
# "Structured query language SQL" was a gap -- in the deep-fit panel, in
# production.  The cause is :data:`_EMBED_THRESHOLD`: 0.70 cosine is a
# reasonable bar between two ordinary skill phrases and a poor one between a
# term and O*NET's expanded spelling of the same term.
#
# THE FIX IS NOT TO TUNE THE THRESHOLD.  There is no Tier-2 evaluation harness
# -- F-2's set measures Tier-1 ranking -- so a threshold moved by feel is a
# number nothing can falsify, which is the failure mode this whole workstream
# was built to avoid.  What CAN be settled without a harness is identity: if a
# user's term and a role item's term are the same string once O*NET's naming
# conventions are undone, that is a match, and no cosine needs consulting.
#
# THE CONVENTIONS ARE MEASURED, NOT GUESSED.  Mined 2026-09-16 from the corpus
# build's own `documents.jsonl` -- 176 distinct hot-technology names across
# 11,339 mentions.  Four shapes account for all of them:
#
#   54.0%  expansion + trailing token   Structured query language SQL
#                                       Microsoft Excel, The MathWorks MATLAB
#   31.2%  a single bare token          Python, Tableau, C++, R
#   10.8%  a " software" suffix         SAP software, Microsoft Office software
#    4.0%  plain multi-word             Adobe Illustrator, Shell script
#
# Two of those shapes are reversible, and the rules below reverse them.
#
# WHAT IS DELIBERATELY *NOT* REVERSIBLE, and why the rules are narrow.  "Take
# the last token of a multi-word name" would turn "Critical Thinking" into
# "Thinking", so a user who listed "Design Thinking" would be credited with
# O*NET's "Critical Thinking".  O*NET's ~35 generic skills are title-cased
# two-word English phrases and its technologies are title-cased two-word
# product names, so SHAPE alone cannot separate them.  Hence two narrow rules
# instead of one broad one:
#
#   A. expansion -> acronym: the last token, only when it is ALL-CAPS.
#      Measured: fires on 26 of the 176 names, every one of them correct
#      (SQL, AWS, CSS, HTML, XML, JSON, VBA, MATLAB, SSIS...).  "Thinking" is
#      not all-caps, so it never fires on a generic skill.
#   B. vendor prefix: the remainder after a leading vendor token.  The vendor
#      set is DERIVED, not authored -- see :data:`_VENDOR_PREFIXES`.
#
# NOTHING HERE TOUCHES A SCORE.  The aliases are consulted by
# :func:`_find_matched_skills` and :func:`_gap_skills`, which are the panel's
# two lists.  :func:`_role_coverage_score` and :func:`_compute_centroid_score`
# still use the cosine alone, deliberately: they produce the fit NUMBER, and
# changing a number with no harness to judge it is the thing this module's
# threshold comment refuses to do.  It is an asymmetry and it is recorded as
# one -- a user can now be told SQL is matched while the coverage term still
# does not count it.  Closing that is a measurement, not an edit.

#: Leading tokens that begin three or more distinct O*NET technology names.
#:
#: Derived by recurrence from the real vocabulary rather than authored, and
#: ``test_the_vendor_prefixes_are_what_the_corpus_says_they_are`` re-derives
#: them from the artifact so this cannot drift into a hand list.
#:
#: Measured counts: Microsoft 29, Apache 9, Oracle 8, Google 7, Adobe 6,
#: Amazon 5, IBM 4, Autodesk 3, Apple 3, Atlassian 3.
#:
#: **Three and not two.**  A threshold of 2 also admits "Red", which is half of
#: "Red Hat" -- it would rewrite "Red Hat Enterprise Linux" to "Hat Enterprise
#: Linux", an alias for nothing.  The names a 2-threshold would additionally
#: shorten (SAP, Spring, Intuit) are all already reachable by rule A or are
#: bare product names people say in full.
_VENDOR_PREFIXES: frozenset[str] = frozenset(
    {
        "adobe",
        "amazon",
        "apache",
        "apple",
        "atlassian",
        "autodesk",
        "google",
        "ibm",
        "microsoft",
        "oracle",
    }
)

#: The recurrence threshold :data:`_VENDOR_PREFIXES` was cut at.  Named so the
#: test that re-derives the set does not have to restate it.
_VENDOR_MIN_DISTINCT_NAMES: int = 3

_WHITESPACE = re.compile(r"\s+")
_SOFTWARE_SUFFIX = re.compile(r"\s+software$", re.I)
_PARENTHETICAL = re.compile(r"\s*\(([^()]{1,60})\)\s*")
#: An acronym: all caps, at least two characters, starting with a letter.
#: Digits and the punctuation O*NET actually uses (``PL/SQL``, ``ASP.NET``,
#: ``C++``, ``C#``, ``DB2``) are allowed after the first character.
_ACRONYM = re.compile(r"^[A-Z][A-Z0-9./#+-]+$")


def _tidy(name: str) -> str:
    """Collapse whitespace and drop trailing punctuation.  No case change."""
    return _WHITESPACE.sub(" ", name).strip().strip(".,;:")


def skill_aliases(name: str) -> frozenset[str]:
    """Every casefolded spelling of *name* that counts as the same skill.

    Always includes the name itself, so a term with no recognised convention
    aliases to exactly one thing and can only ever match itself.  That is what
    keeps the false-positive guard cheap: "R" produces ``{"r"}`` and "React"
    produces ``{"react"}``, and no rule below can ever bring the two together,
    because none of them shortens a single bare token.
    """
    base = _tidy(name)
    if not base:
        return frozenset()

    forms = {base}
    # A fixed point over the four rules: "Amazon Web Services AWS software"
    # needs the suffix gone before the acronym rule can see the acronym.
    for _ in range(3):
        grown: set[str] = set()
        for form in forms:
            stripped = _tidy(_SOFTWARE_SUFFIX.sub("", form))
            if stripped:
                grown.add(stripped)

            match = _PARENTHETICAL.search(form)
            if match:
                inner = _tidy(match.group(1))
                outer = _tidy(_PARENTHETICAL.sub(" ", form))
                grown.update(f for f in (inner, outer) if f)

            tokens = form.split()
            if len(tokens) >= 2:
                if _ACRONYM.match(tokens[-1]):           # rule A
                    grown.add(tokens[-1])
                if tokens[0].casefold() in _VENDOR_PREFIXES:  # rule B
                    grown.add(" ".join(tokens[1:]))
        if grown <= forms:
            break
        forms |= grown

    return frozenset(form.casefold() for form in forms if form)


def _aliases_of(names: Iterable[str]) -> set[str]:
    """The union of every alias of every name in *names*."""
    out: set[str] = set()
    for name in names:
        out |= skill_aliases(name)
    return out


class UnknownOccupation(ValueError):
    """The requested code is not something this tier can analyse.

    ``reason`` is what the caller branches on, because the three cases want
    three different things from the UI:

    ``malformed``
        Not an O*NET-SOC code at all.  A client bug; nothing to retry.
    ``unknown``
        Well-formed and not in the corpus.  The corpus is a build artifact, so
        this is also what a code from a *stale* shortlist looks like after a
        refresh -- the card should be dropped, not retried.
    ``residual``
        A "..., All Other" SOC residual bucket.  Retrieval already filters
        these out of shortlists (F-3, 75 rows), so a click on one can only come
        from a hand-built URL; and a ~50-character title-only document has no
        deep fit to compute.
    """

    def __init__(self, code: str, reason: str) -> None:
        super().__init__("%s: %s" % (reason, code))
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class SkillGap:
    """One thing this role rates highly that the user's skills do not cover."""

    name: str
    importance: float


@dataclass(frozen=True)
class ZoneFit:
    """Job Zone feasibility of this occupation for this user.

    The live scale is **2-5**: O*NET v2 merged zones 1 and 2 (F-3 measured it
    across all 923 zoned rows).  ``occupation_zone`` is ``None`` for the 93
    corpus rows with no zone, and a missing zone is **neutral** -- ``delta`` is
    ``None`` and ``score`` is the same value a role at the user's own level
    gets, which is what :func:`path_scoring._zone_delta_score` does and why.
    """

    user_zone: int
    user_zone_resolved: bool
    occupation_zone: int | None
    delta: int | None
    score: float


@dataclass
class DeepFit:
    """The full analysis of one occupation for one user.

    ``fit_score`` uses the same weighting scheme Tier 1 uses -- role, coverage,
    zone, style, selected by :func:`path_scoring._weights` -- with the Tier-2
    signals substituted for the corpus-only ones.  **It is not the Tier-1 card
    score and will not equal it**, which is the entire point of a second tier:
    coverage here is measured against the occupation's own rated skills and hot
    technologies rather than against its role document.
    """

    onet_code: str
    title: str
    fit_score: float
    retrieval_cosine: float
    centroid_score: float
    coverage_score: float
    skills_score: float
    work_style_score: float
    zone: ZoneFit
    matched_skills: list[str] = field(default_factory=list)
    gap_skills: list[SkillGap] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    tech_stack: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    onet_calls: int = 0
    #: Reserved.  Always ``None`` in F-5 -- see the module docstring.
    narrative: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """The stored and served payload.  Plain JSON types only."""
        return {
            "onet_code": self.onet_code,
            "title": self.title,
            "fit_score": self.fit_score,
            "retrieval_cosine": self.retrieval_cosine,
            "centroid_score": self.centroid_score,
            "coverage_score": self.coverage_score,
            "skills_score": self.skills_score,
            "work_style_score": self.work_style_score,
            "zone": {
                "user_zone": self.zone.user_zone,
                "user_zone_resolved": self.zone.user_zone_resolved,
                "occupation_zone": self.zone.occupation_zone,
                "delta": self.zone.delta,
                "score": self.zone.score,
            },
            "matched_skills": list(self.matched_skills),
            "gap_skills": [
                {"name": gap.name, "importance": gap.importance}
                for gap in self.gap_skills
            ],
            "tasks": list(self.tasks),
            "tech_stack": list(self.tech_stack),
            "weights": dict(self.weights),
            "onet_calls": self.onet_calls,
            "narrative": self.narrative,
        }


@dataclass
class _OccupationData:
    """What the four O*NET calls returned, with a count of how many were made.

    Every field degrades to empty rather than propagating: one occupation with
    no task data (74 of 1,016 have none) is a thinner panel, not a failed
    request.  ``calls`` is the budget this module promises to keep at four --
    **and at zero since W-9, whenever the fit sidecar has the code** -- and
    :func:`deep_fit` reports it so a regression is visible on the wire rather
    than only in a provider bill.  It counts the four fetches **this module**
    makes and nothing else: anchor resolution costs 0 on the normal path -- the
    corpus answers both the code and the Job Zone -- and at most 1 more in the
    two degraded cases ``path_scoring._resolve_current_zone`` documents.  Which
    of those happened cannot be read back off the returned anchor, and a number
    that is sometimes wrong is worse than a narrower one that never is.
    """

    generic_skills: list[Skill] = field(default_factory=list)
    hot_tech: list[str] = field(default_factory=list)
    work_activities: list[tuple[str, float]] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    calls: int = 0


# ---------------------------------------------------------------------------
# The six functions parked by F-4.  Maths and constants unchanged.
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


def _matched_role_items(
    user_skills: list[UserSkill],
    role_items: list[tuple[str, float]],
) -> list[tuple[str, str]]:
    """``(the user's name for a skill, the role item it matched)``, in user order.

    The whole of the panel's matching rule, and the *only* copy of it.
    :func:`_find_matched_skills` is the half of this the panel prints; W-12
    needed the other half -- **which** role item each skill accounted for --
    to stop "Tools people use" repeating a tool another section had already
    shown.  Recovering that from the two name lists afterwards is impossible in
    the case that matters: "Amazon Web Services" and "Amazon Web Services AWS
    software" match by cosine and share no alias, so nothing downstream can tell
    they are one tool.  Only the comparison that made the match knows.

    Precondition: _batch_embed has been called for all texts.
    Used for UI display only -- does not affect the centroid score.
    """
    role_aliases = [(name, skill_aliases(name)) for name, _ in role_items]
    available_role = [
        (name, _EMBED_CACHE[name])
        for name, _ in role_items
        if name in _EMBED_CACHE
    ]

    matched: list[tuple[str, str]] = []
    for us in user_skills:
        # F-8 box 5: identity first. If the user's term and one of the role's
        # terms are the same string once O*NET's naming conventions are undone,
        # that is a match and no cosine is consulted -- which is what stops a
        # user with "SQL" being told they lack "Structured query language SQL".
        # It also works with no embeddings at all, so an OpenAI outage degrades
        # to exact matching rather than to silence.
        user_alias_set = skill_aliases(us.name)
        identical = next(
            (name for name, aliases in role_aliases if user_alias_set & aliases),
            None,
        )
        if identical is not None:
            matched.append((us.name, identical))
            continue
        if not available_role:
            continue
        user_emb = _EMBED_CACHE.get(us.name.lower())
        if user_emb is None:
            continue
        best_name, best_sim = max(
            (
                (name, _cosine_similarity(user_emb, role_emb))
                for name, role_emb in available_role
            ),
            key=lambda pair: pair[1],
        )
        if best_sim >= _EMBED_THRESHOLD:
            matched.append((us.name, best_name))
    return matched


def _find_matched_skills(
    user_skills: list[UserSkill],
    role_items: list[tuple[str, float]],
) -> list[str]:
    """Return user skill names whose best cosine similarity to any role item >= _EMBED_THRESHOLD.

    Precondition: _batch_embed has been called for all texts.
    Used for UI display only -- does not affect the centroid score.
    """
    return [name for name, _ in _matched_role_items(user_skills, role_items)]


def _compute_centroid_score(
    user_skills: list[UserSkill],
    role_items: list[tuple[str, float]],
) -> tuple[float, list[str]]:
    """Cosine between a proficiency-weighted user centroid and an importance-weighted role centroid.

    Precondition: _batch_embed has been called for all texts.
    Role items not in cache (partial API failure) are silently excluded.
    Returns (centroid_similarity, matched_skill_names_for_display).

    See the module docstring for why this is a legitimate statement about one
    occupation and was not a legitimate way to rank a pool of forty.

    **The two are computed independently, which F-8 box 5 had to separate.**
    The score needs embeddings on both sides and is honestly 0.0 without them.
    The matched list does not -- since box 5 an exact-or-alias match settles it
    -- and returning ``[]`` alongside the 0.0 would tell a user whose provider
    was briefly unreachable that this role uses none of their skills. That is
    the judgement :func:`_gap_skills` already makes in the other direction.
    """
    matched = _find_matched_skills(user_skills, role_items)

    user_vecs, user_weights = [], []
    for us in user_skills:
        emb = _EMBED_CACHE.get(us.name.lower())
        if emb is None:
            continue
        user_vecs.append(emb)
        user_weights.append(_SKILL_LEVEL_WEIGHTS.get(us.level, _SKILL_LEVEL_WEIGHTS["beginner"]))

    if not user_vecs:
        return 0.0, matched

    role_vecs, role_weights = [], []
    for name, imp in role_items:
        emb = _EMBED_CACHE.get(name)
        if emb is None:
            continue
        role_vecs.append(emb)
        role_weights.append(imp / 100.0)

    if not role_vecs:
        return 0.0, matched

    user_centroid = np.average(np.array(user_vecs), axis=0, weights=np.array(user_weights))
    role_centroid = np.average(np.array(role_vecs), axis=0, weights=np.array(role_weights))

    score = _cosine_similarity(user_centroid.tolist(), role_centroid.tolist())
    return score, matched


def _compute_weighted_user_centroid(
    user_skills: list[UserSkill],
) -> (
    tuple[list[float], list[tuple["np.ndarray | list[float]", float]]]
    | tuple[None, None]
):
    """Proficiency-weighted centroid of cached user skill embeddings.

    Returns (centroid, [(emb, weight), ...]) so callers can reuse the per-skill
    (embedding, weight) pairs without re-fetching from the cache.
    Returns (None, None) when no embeddings are cached for any user skill.
    """
    available: list[tuple["np.ndarray | list[float]", float]] = []
    for us in user_skills:
        emb = _EMBED_CACHE.get(us.name.lower())
        if emb is None:
            continue
        weight = _SKILL_LEVEL_WEIGHTS.get(us.level, _SKILL_LEVEL_WEIGHTS["beginner"])
        available.append((emb, weight))
    if not available:
        return None, None
    vecs = np.array([e for e, _ in available])
    weights = np.array([w for _, w in available])
    centroid: list[float] = np.average(vecs, axis=0, weights=weights).tolist()
    return centroid, available


def _role_coverage_score(
    user_skills: list[UserSkill],
    role_items: list[tuple[str, float]],
) -> float:
    """Coverage: top-K role items closest to the user centroid, fraction matched by user.

    Asks "what does this role offer that is most relevant to this user?" then checks
    whether the user actually has those skills.  The user centroid is
    proficiency-weighted so advanced skills steer the direction more than beginner
    skills, and the match threshold tightens for beginner skills.

    Uses _EMBED_CACHE directly -- call after the role items have been embedded.
    Returns 0.0 gracefully when no embeddings are available.
    """
    available_role = [
        (name, emb)
        for name, _ in role_items
        if (emb := _EMBED_CACHE.get(name)) is not None
    ]
    if not available_role:
        return 0.0

    user_centroid, available_user = _compute_weighted_user_centroid(user_skills)
    if user_centroid is None:
        return 0.0

    role_sims = sorted(
        [
            (name, emb, _cosine_similarity(emb, user_centroid))
            for name, emb in available_role
        ],
        key=lambda x: x[2],
        reverse=True,
    )
    top_k = role_sims[:_COVERAGE_TOP_K]

    matched = 0
    for _, item_emb, _ in top_k:
        best_match = 0.0
        best_weight = _SKILL_LEVEL_WEIGHTS["beginner"]
        for u_emb, u_weight in available_user:  # type: ignore[union-attr]
            sim = _cosine_similarity(item_emb, u_emb)
            if sim > best_match:
                best_match = sim
                best_weight = u_weight
        effective_threshold = _EMBED_THRESHOLD + (1.0 - best_weight) * 0.05
        if best_match >= effective_threshold:
            matched += 1

    return matched / len(top_k) if top_k else 0.0


def _work_style_similarity(
    behavioral_profile: str,
    work_activities: list[tuple[str, float]],
    openai_client,
) -> float:
    """Cosine between the user's behavioural profile and a role's work activities.

    The Tier-2 form of the style signal: it compares against O*NET's *item* list
    for one occupation, which costs a ``get_work_activities`` call.  Tier 1 gets
    the same signal from the role document for free -- see
    ``path_scoring._build_signals``.
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
# New in F-5
# ---------------------------------------------------------------------------


def _require_well_formed(onet_code: str) -> None:
    """Refuse a code that is not O*NET-SOC, before anything is loaded or fetched.

    Deliberately ahead of ``get_corpus()`` in :func:`deep_fit`.  A malformed code
    is a client bug and its answer does not depend on the corpus being
    reachable; checking it second would mask a permanent 404 behind a transient
    503 for the whole duration of an outage, and send the caller retrying
    something that will never work.
    """
    if not _ONET_CODE_RE.match(onet_code or ""):
        raise UnknownOccupation(onet_code, "malformed")


def _resolve_row(onet_code: str, corpus: OccupationCorpus) -> int:
    """The corpus row for *onet_code*, or raise :class:`UnknownOccupation`.

    The corpus is the authority rather than O*NET, deliberately: a click can
    only reach here from a card the corpus produced, and asking O*NET whether a
    code exists would spend a request to learn what one array lookup already
    knows.
    """
    _require_well_formed(onet_code)
    row = corpus.index_of(onet_code)
    if row is None:
        raise UnknownOccupation(onet_code, "unknown")
    if is_all_other_title(corpus.titles[row]):
        raise UnknownOccupation(onet_code, "residual")
    return row


def _stored_occupation(onet_code: str) -> _OccupationData | None:
    """The same four answers out of W-9's sidecar, or None to go and fetch them.

    Everything the four calls return is static per occupation, so
    ``flask corpus fit`` fetches the whole catalog once and writes it beside the
    artifact.  On a hit this costs **zero** O*NET requests and the client is not
    touched at all; the click drops from 2,384 ms cold / 844 ms warm to the one
    embeddings batch.

    The sidecar stores what the endpoints returned, **unfiltered**: the
    importance threshold and the ``.title``/``.name`` projections below are the
    live path's own and are applied here byte-for-byte, so the two paths differ
    in nothing but ``calls``.  That is measured, not argued:
    ``tests/test_path_deep_fit.py::TestTheFitSidecar`` diffs the two ``DeepFit``s
    over the synthetic world, and W-9's landing note diffs them over five real
    codes against the real artifact.

    Two ways to answer None, and both are the live path unchanged: no sidecar at
    all (``get_fit_table`` logs one warning per corpus version), or a code the
    table lacks.  ``get_corpus`` is memoised and :func:`deep_fit` has already
    loaded it by the time this runs, so this costs a dict lookup.
    """
    table = occupation_fit.get_fit_table(get_corpus())
    if table is None:
        return None
    record = table.for_code(onet_code)
    if record is None:
        return None
    return _OccupationData(
        generic_skills=[
            Skill(
                element_id=element.element_id,
                name=element.name,
                importance=element.importance,
                level=element.level,
            )
            for element in record.generic_skills
        ],
        hot_tech=list(record.hot_tech),
        work_activities=[
            (element.name, element.importance)
            for element in record.work_activities
            if element.importance >= _WORK_ACTIVITY_IMPORTANCE_THRESHOLD
        ],
        tasks=[task.title for task in record.tasks if task.title],
        calls=0,
    )


def _fetch_occupation(onet_code: str, onet_client: OnetClient) -> _OccupationData:
    """One occupation's four answers: from the sidecar if it has them, else live.

    W-9 put the sidecar in front (see :func:`_stored_occupation`).  Below it,
    unchanged, are the four ``_OCC_CACHE``-backed calls.

    Each is isolated, because the four failure modes are not the same failure:
    losing hot tech thins the role profile, losing work activities disables the
    style term, losing tasks empties one list in the panel.  None of them is a
    reason to refuse a fit the other three can still describe -- which is the
    same judgement the funnel's ``_fetch_candidate_data`` made for work
    activities, extended to all four now that the request is about one
    occupation rather than forty.  The builder keeps the same isolation, so a
    code with a 404 on one endpoint is stored with the three it has.
    """
    stored = _stored_occupation(onet_code)
    if stored is not None:
        return stored

    data = _OccupationData()

    for label, call, apply in (
        (
            "skills",
            lambda: onet_client.get_skills_profile(onet_code),
            lambda value: setattr(data, "generic_skills", value),
        ),
        (
            "hot_technologies",
            lambda: onet_client.get_hot_technologies(onet_code),
            lambda value: setattr(data, "hot_tech", value),
        ),
        (
            "work_activities",
            lambda: onet_client.get_work_activities(onet_code),
            lambda value: setattr(
                data,
                "work_activities",
                [
                    (a.name, a.importance)
                    for a in value
                    if a.importance >= _WORK_ACTIVITY_IMPORTANCE_THRESHOLD
                ],
            ),
        ),
        (
            "tasks",
            lambda: onet_client.get_tasks(onet_code),
            lambda value: setattr(data, "tasks", [t.title for t in value if t.title]),
        ),
    ):
        data.calls += 1
        try:
            apply(call())
        except (OnetAPIError, OnetRateLimitError):
            _log.warning("O*NET %s failed for %s", label, onet_code, exc_info=True)

    return data


def _onet_ranks(data: _OccupationData) -> dict[str, int]:
    """Each role item's position in the order O*NET returned it.

    Both lists arrive ranked and both rankings are real: ``get_hot_technologies``
    orders by the share of job postings mentioning the tool (F-1 measured Data
    Scientists at Python 66%, SQL 51%, R 34%), and ``get_skills_profile`` orders
    by importance.  Hot technologies then all collapse to the single
    :data:`_HOT_TECH_IMPORTANCE` constant -- O*NET publishes no per-tool
    importance -- so *every* tool ties with every other and the ranking is the
    only thing left that can order them.
    """
    ranks = {name: index for index, name in enumerate(data.hot_tech)}
    offset = len(ranks)
    for index, skill in enumerate(data.generic_skills):
        ranks.setdefault(skill.name, offset + index)
    return ranks


def _role_items_for(data: _OccupationData) -> list[tuple[str, float]]:
    """``_build_role_profile`` over one occupation, in a reproducible order.

    ``_build_role_profile`` takes a ``set`` of tool names, and a set has no
    order -- which is exactly why F-1 added ``get_hot_technologies`` alongside
    ``get_tech_skills(hot_only=True)``.  Every consumer of ``role_items`` is
    order-independent apart from ``_role_coverage_score``'s similarity sort and
    :func:`_gap_skills`, and for those two the order is what the user reads.

    **Importance descending, then O*NET's own ranking -- never the alphabet.**
    Measured against live O*NET before this sort existed: a backend engineer's
    gap list for Data Scientists came back "Mathematics, Critical Thinking,
    Alteryx software, Amazon Elastic Compute Cloud EC2, Amazon Redshift, Amazon
    Web Services AWS software, Apache Airflow, Apache Cassandra" -- six of eight
    slots spent on the letter A, because every hot technology carries the same
    flat :data:`_HOT_TECH_IMPORTANCE` and the tie fell through to the name.  The
    tools O*NET actually ranks first for that occupation (R, Tableau, Power BI)
    were below the fold.  Same maths, same items, a panel worth reading.
    """
    items = _build_role_profile(set(data.hot_tech), data.generic_skills)
    ranks = _onet_ranks(data)
    items.sort(key=lambda pair: (-pair[1], ranks.get(pair[0], len(ranks)), pair[0]))
    return items


def _gap_skills(
    user_skills: list[UserSkill],
    role_items: list[tuple[str, float]],
) -> list[SkillGap]:
    """Role items no user skill reaches :data:`_EMBED_THRESHOLD` of, most important first.

    The mirror of :func:`_find_matched_skills`, and deliberately not its
    complement: that function answers "which of the user's skills does this role
    use", this one answers "what does this role want that the user has not
    named".  A user with no cached embeddings has no measurable gaps rather than
    a total gap -- reporting every requirement as missing because the embedding
    provider was down would read as a judgement about the person.
    """
    user_vecs = [
        emb
        for us in user_skills
        if (emb := _EMBED_CACHE.get(us.name.lower())) is not None
    ]
    user_alias_set = _aliases_of(us.name for us in user_skills)
    if not user_vecs and not user_alias_set:
        return []

    gaps: list[SkillGap] = []
    for name, importance in role_items:
        # F-8 box 5, and this is the half a user actually complained about:
        # naming something as missing that they have already listed. Checked
        # before the cosine, and before the `role_emb is None` skip, so an
        # embedding outage cannot resurrect a gap identity has ruled out.
        if skill_aliases(name) & user_alias_set:
            continue
        role_emb = _EMBED_CACHE.get(name)
        if role_emb is None:
            continue
        best = max(
            (_cosine_similarity(role_emb, user_emb) for user_emb in user_vecs),
            default=0.0,
        )
        if best < _EMBED_THRESHOLD:
            gaps.append(SkillGap(name=name, importance=round(float(importance), 2)))

    # Already in :func:`_role_items_for`'s order -- importance descending, then
    # O*NET's own ranking -- so this trims rather than re-sorts.  Re-sorting by
    # name here is what produced the six-tools-beginning-with-A list that
    # function's docstring records.
    return gaps[:_TOP_GAPS]


def _visible_tech_stack(
    hot_tech: list[str],
    matched_pairs: list[tuple[str, str]],
    gap_skills: list[SkillGap],
) -> list[str]:
    """The hot technologies no other section of the panel has already shown.

    W-12, from the first browser test.  "Tools people use" was the *raw* hot
    technology list, so the panel said three things about one tool at once: a
    user with SQL and AWS read "Skills you already have: SQL, Amazon Web
    Services", then "Worth picking up" repeating most of the role's tools, then
    "Tools people use: Structured query language SQL, Amazon Web Services AWS
    software" -- their own two skills again, under O*NET's cataloguing names,
    beside the short names they had just been shown.

    **A tool is shown once, in the most specific section that applies.**  The
    two specific sections are the ones that say something about *this user*:
    :func:`_find_matched_skills` ("you have this") and :func:`_gap_skills`
    ("this role wants it and you have not named it").  What is left over is the
    genuinely neutral remainder -- the role's other tools -- which is what the
    section was for.

    **What is compared is the ROLE's own name for the tool, not the user's.**
    The defect is precisely that the same tool has two names: the matched list
    prints the user's spelling ("SQL", "Amazon Web Services") and the hot
    technology list carries the catalogue's ("Structured query language SQL",
    "Amazon Web Services AWS software").  Comparing the two spellings needs a
    normalisation, and no normalisation gets that second pair -- they share no
    alias and were matched by cosine.  So this does not compare spellings at
    all: :func:`_matched_role_items` reports which role item each skill was
    matched *against*, and those names come from the same list ``hot_tech``
    does, so the comparison is exact by construction.  One mapping, the one the
    match was actually made under, rather than a second opinion about it.

    **Filtered, then trimmed** -- not trimmed and then filtered.  The section is
    a window on a ranked list, and removing an entry because it was shown
    elsewhere should let the next tool up into the window rather than leave a
    hole: a user who already has four of an occupation's tools should see more
    of the rest, not a shorter list.  Order is untouched, so what remains is
    still O*NET's own ranking.
    """
    shown = {role_name for _, role_name in matched_pairs}
    shown |= {gap.name for gap in gap_skills}
    return [name for name in hot_tech if name not in shown][:_TOP_TECH]


# ---------------------------------------------------------------------------
# W-13: O*NET's catalogue names, as a person would write them
# ---------------------------------------------------------------------------
#
# From the third browser test.  "Worth picking up" and "Tools people use" were
# printing "Hypertext markup language HTML", "Extensible markup language XML",
# "Cascading style sheets CSS" and "Border Gateway Protocol BGP" -- O*NET's own
# convention of writing the expansion and then the acronym, which nobody says
# out loud and which reads as a cataloguing error on a page of plain language.
#
# **Display only, and applied last.**  The matching, the dedup between the
# panel's three sections and the ordering all run on O*NET's spelling and are
# untouched: `_visible_tech_stack` compares role names against role names, and
# a shortened name would break that comparison in exactly the case it was built
# for.  This runs on the strings that are about to go on the wire and nothing
# else.  Matched skills are not put through it at all -- those already render
# under the user's own name for the skill.

#: An acronym O*NET appended to its own expansion: two to six capitals, and
#: letters only, so "Amazon Elastic Compute Cloud EC2" keeps its full name --
#: "EC2" is not spelled by any reading of the words before it.
_TRAILING_ACRONYM_RE = re.compile(r"^(.*?)\s+([A-Z]{2,6})$")

#: The two words O*NET puts after the acronym ("...AWS software").
_ACRONYM_SUFFIXES: tuple[str, ...] = ("software", "program")


def _spells_out(words: list[str], acronym: str) -> bool:
    """Do *words*, in order, spell *acronym* -- each word contributing at least one letter?

    Not "the initials match": O*NET's own names defeat that on the two most
    common ones.  "Hypertext markup language HTML" has initials H-M-L, and
    "Extensible markup language XML" has E-M-L, because the first word of each
    carries two of the acronym's letters or a letter from the middle of itself.

    So the acronym is split into consecutive non-empty runs, one per word, and
    each run must appear in its word in order.  Requiring *every* word to
    contribute is what keeps it tight: it is why "Adobe Systems Adobe AIR" is
    left alone, and why the number of words can never exceed the number of
    letters.
    """
    if not words or len(words) > len(acronym):
        return False

    def subsequence(letters: str, word: str) -> bool:
        position = 0
        for character in word:
            if position < len(letters) and character == letters[position]:
                position += 1
        return position == len(letters)

    # reachable[j]: the first j letters can be spelled by the words seen so far.
    reachable = {0}
    for word in (w.lower() for w in words):
        nxt: set[int] = set()
        for start in reachable:
            for end in range(start + 1, len(acronym) + 1):
                if subsequence(acronym[start:end].lower(), word):
                    nxt.add(end)
        if not nxt:
            return False
        reachable = nxt
    return len(acronym) in reachable


def _display_name(name: str) -> str:
    """O*NET's expansion-plus-acronym collapsed to the acronym, or *name* unchanged.

    "Hypertext markup language HTML" -> "HTML".  "Amazon Web Services AWS
    software" -> "AWS".  "Oracle Java", "Microsoft Azure software" and
    "Node.js" are not this pattern and come back exactly as O*NET wrote them.
    """
    stem = name.strip()
    if not stem:
        return name
    head, _, last = stem.rpartition(" ")
    if head and last.lower() in _ACRONYM_SUFFIXES:
        stem = head
    match = _TRAILING_ACRONYM_RE.match(stem)
    if match is None:
        return name
    expansion, acronym = match.group(1), match.group(2)
    words = [word for word in re.split(r"[\s/-]+", expansion) if word]
    return acronym if _spells_out(words, acronym) else name


def _retrieval_cosine(
    user_profile: UserProfile,
    anchor,
    corpus: OccupationCorpus,
    row: int,
    skills_vec: "np.ndarray | None",
    behavioral_vec: "np.ndarray | None",
    openai_client,
) -> tuple[float, bool]:
    """``(cosine, query_carries_role_identity)`` for this occupation.

    The *same* query vector Tier 1 built for this user and this ``move_intent``
    (:func:`path_scoring._build_query`), dotted against this occupation's corpus
    row -- so the number returned here is the one the card was ranked by rather
    than a second, differently-defined similarity that would disagree with the
    list the user just clicked in.  Costs nothing: the corpus matrix is
    L2-normalised on write and every embedding is already cached.
    """
    query, has_role_identity = _build_query(
        user_profile, anchor, corpus, skills_vec, behavioral_vec, openai_client
    )
    if query is None:
        return 0.0, False
    cosine = float(np.dot(corpus.matrix[row], np.asarray(query, dtype=np.float32)))
    return cosine, has_role_identity


def _embed_everything(
    user_profile: UserProfile,
    role_items: list[tuple[str, float]],
    data: _OccupationData,
    documents: list[str],
    openai_client,
) -> None:
    """One batched embedding request covering every text this fit needs.

    The keys matter, not just the texts: :func:`_find_matched_skills` and
    :func:`_compute_weighted_user_centroid` look user skills up **lowercased**
    and role items up verbatim, so both spellings are sent.  Batching them here
    means every later cache read is a read -- including the one inside
    :func:`_work_style_similarity`, which calls ``_batch_embed`` itself and
    finds nothing missing.
    """
    if openai_client is None:
        return
    texts = [s.name.lower() for s in user_profile.skills if s.name.strip()]
    texts += [name for name, _ in role_items]
    texts += [name for name, _ in data.work_activities]
    texts += [text for text in documents if text]
    if texts:
        _batch_embed(texts, openai_client)


def _user_documents(user_profile: UserProfile) -> tuple[str | None, str | None, list[str]]:
    """``(skills_document, behavioural_profile, every_text_to_embed)``.

    All four of the user's documents go in the batch, not only the two the
    signals read: anchor resolution embeds the profile document and the title
    sentence too, and leaving them out turns one embedding request into three
    (measured -- it did, until it was fixed).
    """
    skills_document = _compose_skills_document(user_profile)
    behavioral_document = _build_behavioral_profile(user_profile)
    documents = [
        text
        for text in (
            skills_document,
            behavioral_document,
            _compose_profile_document(user_profile),
            _compose_title_document(user_profile),
        )
        if text
    ]
    return skills_document, behavioral_document, documents


def _skills_signals(
    user_skills: list[UserSkill],
    role_items: list[tuple[str, float]],
    openai_client,
) -> tuple[float, float, float, list[str]]:
    """``(centroid, coverage, combined, matched_skill_names)``.

    The combination is the pre-F-4 one, unchanged: an even mix of "how close is
    the user's skill centroid to this role's" and "of the handful of things this
    role offers that are most relevant to this user, how many do they have".
    Without an OpenAI client there is no coverage term to mix, so the centroid
    stands alone rather than being halved by a zero.
    """
    centroid, matched = _compute_centroid_score(user_skills, role_items)
    if openai_client is None:
        return centroid, 0.0, centroid, matched
    coverage = _role_coverage_score(user_skills, role_items)
    return centroid, coverage, _CENTROID_MIX * centroid + _COVERAGE_MIX * coverage, matched


def deep_fit(
    user_profile: UserProfile,
    onet_code: str,
    onet_client: OnetClient,
    openai_client=None,
) -> DeepFit:
    """Analyse ONE occupation against *user_profile*.

    Synchronous by design (design doc §2.3): four ``_OCC_CACHE``-backed O*NET
    calls for one code and one batched embedding request is fast enough that a
    job/poll pair would cost the user more in round trips than it saved.  W-9
    took the four calls out of the common case entirely -- see
    :func:`_stored_occupation` -- leaving the one embeddings batch.

    Args:
        user_profile:  The same dataclass Tier 1 scores.
        onet_code:     The clicked occupation's O*NET-SOC code.
        onet_client:   Authenticated O*NET client.
        openai_client: Optional.  Without it the skills, gap and style terms are
                       unavailable and the fit degrades to zone and title --
                       the same degrade-don't-fail promise ``score_paths`` makes.

    Returns:
        A :class:`DeepFit`.  ``onet_calls`` reports the budget actually spent.

    Raises:
        InsufficientProfile: Neither a usable title nor a single skill.  The
            caller answers ``profile_incomplete``, the branch F-4 wired.
        UnknownOccupation: Malformed code, not in the corpus, or a residual
            bucket -- ``reason`` tells them apart.
        CorpusUnavailable: The corpus could not be loaded.  A service outage.
    """
    if not _has_any_signal(user_profile):
        raise InsufficientProfile(
            "profile has neither a job title nor any skills to fit against"
        )

    _require_well_formed(onet_code)
    corpus = get_corpus()
    row = _resolve_row(onet_code, corpus)

    data = _fetch_occupation(onet_code, onet_client)
    role_items = _role_items_for(data)

    skills_document, behavioral_document, documents = _user_documents(user_profile)
    _embed_everything(user_profile, role_items, data, documents, openai_client)

    skills_vec = _embed_one(skills_document, openai_client) if skills_document else None
    behavioral_vec = (
        _embed_one(behavioral_document, openai_client) if behavioral_document else None
    )

    anchor = _resolve_current_zone(user_profile, onet_client, openai_client, corpus)
    cosine, has_role_identity = _retrieval_cosine(
        user_profile, anchor, corpus, row, skills_vec, behavioral_vec, openai_client
    )

    centroid_score, coverage_score, skills_score, _ = _skills_signals(
        user_profile.skills, role_items, openai_client
    )
    # W-12: the printed list and the tech-stack dedup are two halves of ONE
    # matching, so both are read off one call to it. `_skills_signals`' fourth
    # value is the same list by a longer route (`_compute_centroid_score` ->
    # `_find_matched_skills` -> here), and it is discarded rather than used so
    # that the panel and the dedup cannot be looking at two different answers.
    # The cost of matching twice is a few hundred cached-vector dot products
    # against four O*NET-shaped calls and an embeddings batch -- unmeasurable.
    matched_pairs = _matched_role_items(user_profile.skills, role_items)
    matched_skills = [name for name, _ in matched_pairs]

    work_style_score = (
        _work_style_similarity(behavioral_document, data.work_activities, openai_client)
        if behavioral_document
        else 0.0
    )

    # Computed here rather than in the constructor call below: W-12's tech stack
    # is what the other two sections did not already show, so it needs both of
    # them in hand.
    gaps = _gap_skills(user_profile.skills, role_items)
    # W-13, and the order matters: `_visible_tech_stack` dedups by comparing
    # O*NET's own names, so it is given the raw gaps and the raw hot-tech list
    # and only what comes OUT of it is renamed for the screen.
    visible_tech = [_display_name(name) for name in
                    _visible_tech_stack(data.hot_tech, matched_pairs, gaps)]
    display_gaps = [
        SkillGap(name=_display_name(gap.name), importance=gap.importance)
        for gap in gaps
    ]

    zone_fit = _zone_fit(user_profile, anchor, corpus, onet_code)
    zone_is_reliable = (
        anchor.zone_resolved or user_profile.career_status == "first_job"
    )
    role_w, coverage_w, zone_w, style_w = _weights(
        user_profile, zone_is_reliable, behavioral_vec is not None, has_role_identity
    )

    raw = (
        role_w * _rescale_cosine(cosine)
        + coverage_w * skills_score
        + zone_w * zone_fit.score
        + style_w * work_style_score
    )

    return DeepFit(
        onet_code=onet_code,
        title=corpus.titles[row],
        fit_score=round(max(0.0, min(1.0, raw)), 4),
        retrieval_cosine=round(cosine, 4),
        centroid_score=round(centroid_score, 4),
        coverage_score=round(coverage_score, 4),
        skills_score=round(skills_score, 4),
        work_style_score=round(work_style_score, 4),
        zone=zone_fit,
        matched_skills=matched_skills,
        gap_skills=display_gaps,
        tasks=data.tasks[:_TOP_TASKS],
        tech_stack=visible_tech,
        weights={
            "role": round(role_w, 4),
            "coverage": round(coverage_w, 4),
            "zone": round(zone_w, 4),
            "style": round(style_w, 4),
        },
        onet_calls=data.calls,
    )


def _zone_fit(
    user_profile: UserProfile,
    anchor,
    corpus: OccupationCorpus,
    onet_code: str,
) -> ZoneFit:
    """Feasibility of *onet_code*'s Job Zone against the user's own."""
    occupation_zone = corpus.zones.get(onet_code)
    return ZoneFit(
        user_zone=anchor.zone,
        user_zone_resolved=anchor.zone_resolved,
        occupation_zone=occupation_zone,
        delta=None if occupation_zone is None else occupation_zone - anchor.zone,
        score=round(
            _zone_delta_score(
                anchor.zone, occupation_zone, user_profile.seniority_intent
            ),
            4,
        ),
    )
