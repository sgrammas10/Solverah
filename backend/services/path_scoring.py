"""Tier-1 career path retrieval and scoring (BUILD_PLAN F-4).

WHAT CHANGED, AND WHY
---------------------
Until 2026-09-16 this module was a *funnel*: it asked O*NET for the user's own
job family, asked an LLM for five or six occupation titles, searched each of
them, threw away everything but the first result, pruned what was left through
a hand-written SOC prefix allow-list, and then spent **3-4 O*NET HTTP calls on
every surviving candidate** (~160 per cold run) to build a comparison target out
of O*NET's fixed ~35-element Skills taxonomy.

Three things were wrong with that, all measured rather than argued -- see
``docs/PATH_INTELLIGENCE_REDESIGN.md`` §1:

* **Structurally inaccurate.**  Every occupation in O*NET has all ~35 generic
  skills; only the importance number differs.  So most of the compared
  vocabulary was constant across the entire candidate pool and the
  discriminating signal was averaged away *before* any weight was applied.
* **Structurally unreachable.**  ``_DEFAULT_ALLOWED_SOC_PREFIXES`` barred whole
  occupational families from the users who are *in* those families.  F-2's
  ceiling analysis: an electrician could not reach one of their three primary
  labels, because ``47-`` and ``49-`` were not on the list.  Two of the twenty
  evaluation profiles returned nothing at all and became HTTP 500s.
* **Expensive.**  The per-candidate fan-out is what filled ``_EMBED_CACHE`` and
  is part of the 2026-09-15 production OOM.

Tier 1 now makes **zero per-candidate O*NET calls**.  Candidates come from
``occupation_retrieval.retrieve`` -- one ``matrix @ query`` over a precomputed
1,016 x 1536 corpus of *role documents* (title + description + tasks + hot
tech), which is sub-millisecond and exact.  Every signal is served from that
corpus, its Job Zone sidecar, and embeddings of **the user's own texts**:

    signal    served by
    ------    ---------
    role      the retrieval cosine itself (document-to-document, symmetric)
    coverage  cosine(user skills document, role document)
    style     cosine(user behavioural profile, role document)
    zone      corpus.zones[code] vs the user's resolved zone

The only O*NET traffic left is anchor resolution, and on the normal path there
is none of it: the corpus resolves the user's title to a code *and* carries its
Job Zone.  See :func:`_resolve_current_zone` for why the corpus turned out to be
a better title resolver than O*NET's own keyword search, which is the second
accuracy fix in this chunk.

WHAT IS *NOT* HERE ANY MORE
---------------------------
The per-occupation item analysis -- O*NET skills profile, hot tech, work
activities, and the centroid/coverage math over them -- is **Tier 2**, and
F-5 moved it out to ``backend/services/path_deep_fit.py``, which runs it for
the single occupation a user clicks.  What was deleted rather than moved is the
*fan-out* that ran those calls across ~40 candidates on every request.
``tests/test_path_scoring.py::TestTombstones`` pins every removed name -- the
funnel's and Tier 2's -- so neither can drift back into this module.

CALL BUDGET PER ``score_paths``
-------------------------------
    O*NET   0     normally.  1 if the resolved code is one of the 93 rows with
                  no zone in the sidecar; 1 if there is no OpenAI client at all,
                  where ``search_occupations`` is the degraded fallback.
                  Measured across the 20 F-2 profiles: **zero**.
    OpenAI  1     embedding request, batching the user's own texts -- up to four
                  short documents plus one per listed skill
    LLM     0     -- the keyword-generation and title-normalisation calls are
                     gone; the corpus resolves a free-form title for free

Against the funnel this replaces: ~160 O*NET requests, one LLM completion (two
or three when a title needed normalising), and an embedding batch over 300-700
texts rather than 5-15.

MEASURED QUALITY (BUILD_PLAN F-2 harness, 20 profiles, k=10)
-------------------------------------------------------------
                    nDCG@10  harm@10  P@10   MRR    coverage  primary_recall
    funnel (HEAD)    0.318    0.031   0.232  0.566    0.346       0.382
    this module      0.491    0.005   0.437  0.770    0.442       0.557

Better on every metric.  The two profiles the SOC allow-list made unscoreable --
an electrician and a graphic designer, both HTTP 500s in production -- now
return ten results each, and harmful suggestions are down from six across the
set to one.
"""
from __future__ import annotations

import logging
import os
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from backend.services.occupation_retrieval import (
    CorpusUnavailable,
    Match,
    OccupationCorpus,
    get_corpus,
    is_all_other_title,
)
from backend.services.onet_client import (
    OnetAPIError,
    OnetClient,
    OnetRateLimitError,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: The ``(coverage_w, zone_w, style_w)`` split, before ``role_w`` is reserved
#: and the three are rescaled by ``(1 - role_w)``.  Selected by zone
#: reliability, whether the user has a behavioural profile, and whether their
#: stated priority is growth-flavoured (``learning_growth`` / ``pay_title``).
#:
#: The *shape* of this table is the pre-F-4 scheme, kept deliberately -- the
#: brief's instruction was to keep the weighting scheme as the starting point
#: and let the harness say whether to change it.  The harness did say, in one
#: place: **the zone weights came down**.  Zone delta is the one term with no
#: semantic content -- every zone+1 role scores identically on it regardless of
#: relevance, which the pre-F-4 code admitted in a comment -- and it was carrying
#: 0.40-0.65 of the budget because the signal it was competing against was a
#: centroid of ~35 constants that discriminated almost nothing.  Now that
#: coverage and role are real document similarities, a zone term that large
#: simply floats every one-zone-up role to the top together: measured on the
#: F-2 set, it put Electrical Engineers (a labelled *harmful* for a journeyman
#: electrician, because it needs a degree he does not have) at rank 1 with
#: Mechanical and Electronics Engineers behind it.
_WEIGHTS_BEHAVIORAL_GROWTH: tuple[float, float, float] = (0.45, 0.35, 0.20)
_WEIGHTS_BEHAVIORAL: tuple[float, float, float] = (0.55, 0.25, 0.20)
_WEIGHTS_GROWTH: tuple[float, float, float] = (0.60, 0.40, 0.00)
_WEIGHTS_BALANCED: tuple[float, float, float] = (0.70, 0.30, 0.00)
#: No reliable zone: the zone term is not merely small, it is unavailable.
_WEIGHTS_NO_ZONE_BEHAVIORAL: tuple[float, float, float] = (0.75, 0.00, 0.25)
_WEIGHTS_NO_ZONE: tuple[float, float, float] = (1.00, 0.00, 0.00)

#: Maximum number of ScoredPath objects returned.
_TOP_N: int = 10

#: How many corpus rows to retrieve before re-ranking.
#:
#: The retrieval cosine is only one of four signals, so the pool has to be wider
#: than the shortlist or zone/coverage/style have nothing to reorder.  Too wide
#: and the tail is pure noise that a lucky zone delta can float to the top.
#: Tuned on the F-2 harness (see the F-4 landing note in BUILD_PLAN §6).
_RETRIEVE_K: int = 30

#: Role-identity anchor weight, reserved by move_intent before the
#: coverage/zone/style split (see score_paths).  ``fresh_start`` zeroes it: the
#: user is explicitly asking to leave their occupation, and its retrieval query
#: is the skills document, so a role weight there would double-count coverage.
#: ``None`` (unspecified) is a real dict key, not a "missing" sentinel.
_ROLE_WEIGHT_BY_INTENT: dict[str | None, float] = {
    "stay_in_field": 0.50,
    None: 0.35,
    "adjacent": 0.45,
    "fresh_start": 0.0,
}
_ROLE_WEIGHT_DEFAULT: float = 0.35

#: ``adjacent`` rotates the query off the occupation anchor and toward the
#: user's own capabilities: ``q = (1-mix)*anchor + mix*skills_document``.
#:
#: This is the interim form of design doc §3.2.  F-6 replaces it with the real
#: Rocchio loop driven by inline card feedback; this is that loop with zero taps
#: -- a fixed rotation instead of a learned one.  It exists because the F-2
#: label set grades *the same job at a different grade band* as HARMFUL for
#: ``adjacent`` (a High School Teacher must not be shown Middle School
#: Teachers), and those siblings are exactly what a pure anchor query returns
#: first: measured, they sit at cosine 0.85-0.88 against the anchor, above every
#: genuinely adjacent role.  Rotating toward the skills document demotes them
#: without the hand-written sibling rules the allow-list era would have reached
#: for.
_ADJACENT_SKILLS_MIX: float = 0.45

#: ``fresh_start`` blends the behavioural profile into the skills query.
#:
#: Design doc §3.3 wants the behavioural profile to be the *primary* query for
#: this intent.  F-7 does that with a diverse k-means seed; here it is a blend,
#: because a behavioural-only query with no transferable-skill floor is how you
#: recommend Logging Worker.  Zero when the user has no assessment data.
_FRESH_START_BEHAVIORAL_MIX: float = 0.30

#: How much of the user's own SOC code ``fresh_start`` excludes from its
#: results: 3 characters is the major group ("43-"), 4 is the minor group
#: ("43-6"), 0 disables the filter.
#:
#: **Design doc §3.3 says major group, and the label set says that is too
#: wide.**  Worth recording, because it is the same *shape* of defect as the
#: allow-list F-4 deleted -- a hard structural exclusion making labelled-good
#: answers unreachable -- just pointed the other way.  Measured on the F-2 set
#: with the major group excluded:
#:
#:     profile                         relevant labels  unreachable
#:     p10_between_jobs_admin_fresh          11             8  (2 of 3 primaries)
#:     p16_between_jobs_warehouse_fresh      11             4  (2 of 4 primaries)
#:     p05_devops_fresh_start                10             1
#:
#: SOC major group 43 is "Office and Administrative Support" -- roughly a
#: hundred occupations.  An administrative assistant moving to Bookkeeping
#: Clerk or Dispatcher has changed jobs by any ordinary reading, and the label
#: set grades both as primary; the major group is simply too coarse a proxy for
#: "the field I am leaving".  The minor group keeps the constraint's intent --
#: do not return the user's own line of work -- at a width that does not bar a
#: third of the acceptable answers.
#:
#: This is F-7's decision to settle properly (it owns ``fresh_start``'s real
#: machinery, and the constraint is Sebastian's design call, not a tuning
#: knob).  F-4 needs ``fresh_start`` to *work*, so it takes the narrower filter
#: on the harness's evidence and flags the conflict rather than quietly
#: reversing the design.
_FRESH_START_EXCLUDE_PREFIX_LEN: int = 4

#: Cosine values are rescaled onto [0, 1] by a fixed affine map before the
#: weights are applied.
#:
#: Raw ``text-embedding-3-small`` cosines between a user document and a role
#: document occupy a narrow band -- measured over the real corpus, essentially
#: everything interesting falls between 0.30 and 0.85.  Left raw, a 0.10 spread
#: in coverage would be multiplied by a 0.4 weight and vanish underneath a zone
#: delta that swings a full 1.0, which is the "every zone+1 role floats to the
#: top together" failure the old ``_ZONE_DAMPENING_FRESH_START`` patch was
#: written over.  The map is fixed rather than per-pool min/max on purpose: a
#: pool-relative rescale would manufacture spread when every candidate really is
#: equally close, and would make one profile's scores depend on which other
#: candidates happened to be retrieved.
_COSINE_FLOOR: float = 0.30
_COSINE_CEILING: float = 0.85

#: How much of the anchor-resolution query is the bare title sentence, the rest
#: being the full profile document (title plus skills).
#:
#: Neither end is right on its own, which is why this is a blend and not a
#: choice.  At 0.0 the skills swamp a short title and "High School Teacher"
#: resolves into the middle of the teaching cluster rather than onto Secondary
#: School Teachers.  At 1.0 the title is one or two tokens again -- the exact
#: domination failure design doc §2.1 is about -- and "Journeyman Electrician"
#: resolves onto Helpers--Electricians, which is a *labelled harmful* for that
#: user, while "Senior Backend Engineer" drifts off Software Developers.  A
#: blend keeps the title's identity without letting two tokens decide.
_ANCHOR_TITLE_MIX: float = 0.40

#: How close a second resolution candidate has to be, in raw cosine, before it
#: counts as "possibly also the user's own job" and is excluded alongside the
#: anchor.
#:
#: Resolution picks one row, and on the F-2 set the top two are sometimes
#: separated by less than the noise floor: "Journeyman Electrician" scores
#: Helpers--Electricians 0.613 and Electricians 0.612, and "High School Teacher"
#: scores Middle School Teachers 0.596 and Secondary School Teachers 0.593.
#: Excluding only the winner of a coin flip leaves the user's actual occupation
#: sitting at rank 1 of their own suggestions -- which is what happened to the
#: electrician.
#:
#: **The F-2 metric cannot see this defect**, which is why it is fixed on
#: product grounds rather than measured ones: `score_profile` drops an
#: `anchor`-graded result from the denominator instead of penalising it, so
#: returning the user's own job costs a card and not a point.  Showing somebody
#: the job they already have is a visible failure; losing one card of ten is
#: not.
#:
#: Ambiguity is resolved conservatively -- exclude both -- rather than by
#: guessing harder.  That also removes the junior twin of the user's job for
#: free (Helpers--Electricians is a labelled *harmful* for that profile),
#: because "the same work at a different grade" is exactly the shape that ties
#: here.
_ANCHOR_TIE_MARGIN: float = 0.01

#: How many resolution candidates the margin is applied across.  Three is
#: enough: a tie four deep means the title carries no identity at all, and
#: excluding four rows starts costing real suggestions.
_ANCHOR_TIE_LOOKAHEAD: int = 3

#: Display-only: how many of the user's skills to name as "overlapping" on a
#: card, and the **raw** cosine one must clear to be named at all.
#:
#: Raw, not rescaled, and that distinction is the whole reason this constant
#: exists.  :data:`_COSINE_FLOOR`/:data:`_COSINE_CEILING` are calibrated for
#: *document against document* -- two pieces of prose of comparable length.  A
#: two-word skill name against a 300-token role document is a different
#: distribution entirely, and measured over the real corpus it is much lower:
#: mean 0.18, 99th percentile 0.37, and even the single best-matching role for
#: a given skill averages only 0.40.  Pushing that through the document-scale
#: rescale put the bar at 0.49 raw, which named **nothing on any card** -- and
#: since `overlapping_skills` is what `path_narrative` is handed to write the
#: "why this path" text with, an empty list is a quietly worse product rather
#: than a visible bug.
#:
#: 0.30 sits near the 99th percentile of the overall skill-vs-role
#: distribution, so a named skill is one this role genuinely uses.  The top-K
#: cap does the rest of the work; the floor only has to suppress the case where
#: a role uses none of the user's skills at all.
_OVERLAP_TOP_K: int = 5
_OVERLAP_MIN_COSINE: float = 0.30

#: The Job Zone delta curve, per ``seniority_intent``, as six bands::
#:
#:     (delta >= +3, +2, +1, 0, -1, delta <= -2)
#:
#: **The shape changed in F-4, and the reason is the point.**  The pre-F-4 curve
#: paid its biggest bonus for climbing (+1 scored 1.0 while a lateral move
#: scored 0.5) and barely penalised descending (-1 scored 0.0, the same as a
#: lateral move under ``move_up``).  That made zone a *climbing bonus*, and
#: because zone delta is the one term in the formula with no semantic content,
#: it floated every one-zone-up occupation to the top together -- which the
#: pre-F-4 code admitted in a comment and then patched with
#: ``_ZONE_DAMPENING_FRESH_START``.
#:
#: Measured on the F-2 set, that shape is what put Electrical Engineers at rank
#: 1 for a journeyman electrician: a labelled *harmful*, because it is a
#: four-year degree away, arriving top because it was one zone up.  And it is
#: what let Bookkeeping Clerks sit at rank 3 for an accountant who asked to move
#: up, because a demotion scored the same as standing still.
#:
#: The new shape makes zone a **soft feasibility signal**: every plausible
#: direction clusters near the top, so zone barely reorders candidates that are
#: all reachable, while wrong-direction and over-reach moves go clearly
#: negative, so zone can still veto.  Design doc §2.2 wants feasibility as a
#: hard filter at this tier; a hard ``zone_max`` would break the ``move_up``
#: users who are explicitly asking to climb, so F-4 expresses it as a signal
#: that can subtract.  F-7 owns the hard-filter form.
#: Two properties of the numbers below are load-bearing and were each worth
#: about +0.04 nDCG on the F-2 set, independently:
#:
#: * **Flat across the plausible band.**  Under ``move_up``, +1 scores 1.0 and
#:   standing still scores 0.9 -- a preference, not a landslide.  The stated
#:   ``seniority_intent`` still orders them (``stay_lateral`` inverts the pair),
#:   so the user's answer is not inert, but zone can no longer outvote a real
#:   similarity difference.
#: * **Sharply negative below.**  A move *down* a zone is not "no bonus", it is
#:   a penalty, and going down two is worse.  That is what demotes the junior
#:   twin of the user's own job -- Helpers--Electricians, Bookkeeping Clerks --
#:   which sits at a very high document similarity precisely *because* it is the
#:   same work at a lower grade, and which the label set grades harmful.
_ZONE_BANDS: dict[str | None, tuple[float, float, float, float, float, float]] = {
    "move_up":      (0.20, 0.90, 1.00, 0.90, -0.40, -0.80),
    "stay_lateral": (0.00, 0.30, 0.90, 1.00, -0.30, -0.80),
    None:           (0.10, 0.80, 1.00, 1.00, -0.30, -0.80),
}

#: The Job Zone assumed when the user's own zone cannot be resolved.
#:
#: **This was 1, and 1 no longer exists.**  O*NET v2 merged Job Zones 1 and 2,
#: so the live range across all 923 zoned occupations is 2-5 (verified against
#: the corpus sidecar, F-3).  A fallback of 1 made every candidate look like at
#: least a one-zone step up, inflating every delta by one and steering first-job
#: users a full zone too low.
_UNKNOWN_ZONE_FALLBACK: int = 2

#: The lowest and highest Job Zone the live O*NET taxonomy uses.  Recorded as
#: constants so the arithmetic below states its own domain.
_MIN_JOB_ZONE: int = 2
_MAX_JOB_ZONE: int = 5

# In-process embedding cache, bounded by MEMORY rather than by entry count.
#
# THE 2026-09-15 PRODUCTION OOM.  This cache was an OrderedDict[str, list[float]]
# capped at 10,000 *entries*.  A 1536-dim text-embedding-3-small vector held as a
# plain list[float] costs 48.50 KB -- the list itself is only 12 KB of pointers,
# but the cache holds the only reference to 1536 separate float objects at 24
# bytes each -- so a full cache was 473.6 MB against a 512 MB dyno, i.e. the cap
# permitted a cache almost as large as the whole instance.  (Measured 2026-09-16
# with tracemalloc; the floats must be created inside the traced region or the
# cost is under-reported as 12 KB, because copying a list copies pointers to
# float objects that already exist.)
#
# TWO CHANGES FIXED IT.  Entries are stored as np.float32 (6.18 KB/entry, a 7.8x
# reduction -- see _batch_embed), and the bound is a byte budget rather than an
# entry count, so no future change to the vector's dimension or dtype can quietly
# restore the leak.
#
# F-4 REMOVED THE DEMAND THAT MADE IT DANGEROUS.  The cache used to hold every
# role item of every candidate: the ~35 generic skills and ~41 work activities
# per occupation across ~40 candidates, 300-700 unique texts per cold run.  It
# now holds **only the user's own documents** -- the skills document, the
# behavioural profile, and at most the title -- which is at most 3 entries per
# distinct user scored, about 18 KB.  The budget below is left where it is
# rather than shrunk, because `path_deep_fit` (F-5) populates this same cache
# with Tier-2 role items again -- for ONE occupation per click, not forty per
# request -- and F-8 retires it.  One cache, shared across both tiers: two would
# double the budget arithmetic below without halving anything.
#
# WHERE 32 MB COMES FROM (measured 2026-09-16, not guessed).
#
# The instance is a Render Starter: 0.5 CPU, 512 MB, and gunicorn.conf.py runs
# `workers = 1` on it.  One worker means one copy of this module global, so the
# budget is the whole of what is left rather than a third of it:
#
#   dyno                                        512 MB
#   one booted worker, empty caches           - 148 MB
#                                             ---------
#   headroom for requests AND every cache       364 MB
#
# 148 MB is measured RSS after `import app` under production config -- the
# scientific stack alone (pandas/numpy/sklearn) is 179.6 MB RSS, of which only
# 80.4 MB is traced Python heap; the rest is C-extension and mapped-image memory
# tracemalloc cannot see, which is why the traced figure alone understates it.
#
# All four per-worker caches at their caps, measured (see tests/test_cache_bounds.py):
#
#   _EMBED_CACHE   32.00 MB     _OCC_CACHE               11.36 MB
#   path_cache      4.17 MB     agent_service._resume     0.76 MB
#                                                        ---------
#   total                                                 48.3 MB
#
# That is 13% of the 364 MB headroom and 9.4% of the dyno, leaving ~316 MB for
# request handling across this worker's 8 threads -- a 7.5x margin over the
# caches rather than a budget spent to its limit.
#
# WORKER COUNT IS THE LOAD-BEARING INPUT, so record how to check it.  Production
# logs cannot tell you: `celery_configured` is emitted once per worker at import,
# but its payload carries no pid -- `process` and `processName` sit in
# _RESERVED_RECORD_ATTRS in solverah/observability/logging.py, and PROCESS_ID is
# defined there but never stamped.  N workers therefore emit N byte-identical
# lines differing only in milliseconds, which any log viewer collapses, so a
# single line is not evidence of a single worker.  The check that settles it is
# gunicorn's own `Booting worker with pid` lines, which do carry pids.  If
# `workers` ever goes back above 1, divide this budget by the new W -- or set
# SOLVERAH_EMBED_CACHE_MAX_BYTES from the dashboard, which needs no deploy.
#
# THIS IS A STOPGAP.  docs/PATH_INTELLIGENCE_REDESIGN.md §2 removes this cache
# entirely; F-8 is the chunk that does it.
_EMBED_CACHE: OrderedDict[str, "np.ndarray | list[float]"] = OrderedDict()

#: Per-worker byte budget for _EMBED_CACHE.  Env-overridable so the dyno can be
#: retuned without a deploy of this file.
_EMBED_CACHE_MAX_BYTES: int = int(
    os.environ.get("SOLVERAH_EMBED_CACHE_MAX_BYTES", 32 * 1024 * 1024)
)

#: Per-entry cost of the OrderedDict itself: the hash-table slot plus the
#: doubly-linked-list node OrderedDict keeps for ordering.
#:
#: Calibrated, not assumed.  At 100 the accounting under-counted by ~62 bytes an
#: entry, and a full 8 MB cache measured 8.07 MB by tracemalloc -- a 0.9%
#: overshoot of its own budget.  200 errs high, which is the direction that
#: makes the bound tighter rather than leakier, and is still a rounding error
#: against a 6 KB vector.
_EMBED_ENTRY_OVERHEAD_BYTES: int = 200

_EMBED_BATCH_MAX_INPUTS: int = 2048  # OpenAI embeddings API cap on inputs per request


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class InsufficientProfile(ValueError):
    """The profile carries no signal at all to retrieve on.

    Raised by :func:`score_paths` when there is neither a usable job title nor a
    single skill -- there is nothing to embed and nothing to anchor to, so any
    ranking would be invented.

    **This is the typed outcome the ACC-4 / S16.11 defect needed.**  Returning
    ``[]`` here made ``intelligence_service.path_suggestions`` answer
    ``500 "Unable to score career paths"``, and the SPA's ``stateForFailure()``
    has no branch for that string, so the user saw a generic retry box for a
    condition retrying cannot fix.  The caller turns this into
    ``profile_incomplete``, whose frontend branch already exists and was dead
    only because the backend never sent it.  Everything *else* that produces an
    empty list -- an unreachable corpus, an embedding outage -- stays a 500,
    because those really are transient.
    """


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
    # WorkPulse archetype label -- carried for display purposes; not scored here.
    archetype: str
    move_intent: Literal["stay_in_field", "adjacent", "fresh_start"] | None = None
    seniority_intent: Literal["move_up", "stay_lateral", "open"] | None = None
    priority: Literal["pay_title", "interesting_work", "work_life_balance", "learning_growth"] | None = None
    # Behavioral profile -- populated from completed assessments, None if not yet taken.
    # These fields should store full description text (not short label names) so the
    # embedding model can find meaningful semantic distance against O*NET role documents.
    archetype_description: str = ""   # multi-sentence WPL archetype description
    focus_type: str | None = None     # FocusType label (no rich description available)
    manager_match: str | None = None  # ManagerMatch archetype_description text
    work_style_tags: list[str] = field(default_factory=list)  # WPL signal descriptions


@dataclass
class ScoredPath:
    onet_code: str
    title: str
    score: float  # 0.0-1.0, higher is a better match
    overlapping_skills: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Anchor:
    """Where the user sits today, as far as retrieval is concerned.

    ``zone_resolved`` is False whenever ``zone`` is the
    :data:`_UNKNOWN_ZONE_FALLBACK` guess rather than a real O*NET value; the
    weighting scheme reads it to decide whether the zone term is worth anything.
    """

    zone: int
    code: str | None
    zone_resolved: bool
    title_used: str | None
    #: True when ``code`` names a SOC residual bucket ("..., All Other").  Such
    #: a row is a ~50-character title-only document, so it is a fine *identity*
    #: and a poor *query* -- see :func:`_build_query`.
    code_is_all_other: bool = False
    #: Every code that might be the user's own job, ``code`` included.  More
    #: than one when resolution could not separate the top candidates; see
    #: :data:`_ANCHOR_TIE_MARGIN`.  This, not ``code``, is what retrieval
    #: excludes.
    same_job_codes: tuple[str, ...] = ()

    @property
    def excluded_codes(self) -> tuple[str, ...]:
        """Codes retrieval must not return: the anchor and any tie with it."""
        if self.same_job_codes:
            return self.same_job_codes
        return (self.code,) if self.code else ()


@dataclass
class _Signals:
    """The four per-candidate terms, already rescaled onto [0, 1]."""

    match: Match
    role: float
    coverage: float
    style: float
    zone: float
    zone_raw: int | None


# ---------------------------------------------------------------------------
# Zone delta scoring
# ---------------------------------------------------------------------------


def _zone_delta_score(
    current_zone: int,
    candidate_zone: int | None,
    seniority_intent: Literal["move_up", "stay_lateral", "open"] | None = None,
) -> float:
    """Map the Job Zone difference to a [-0.3, 1.0] score contribution.

    THE LIVE SCALE IS 2-5, NOT 1-5.  O*NET v2 merged Job Zones 1 and 2, and the
    corpus sidecar confirms it: every one of the 923 zoned occupations carries a
    2, 3, 4 or 5.  Three consequences, all of which this function now states
    rather than assumes:

    * **"One step up" (delta +1) still means one zone up, but the bottom step is
      wider than it used to be.**  Zone 2 absorbed the old zone 1, so 2 -> 3 now
      spans what was once most of two steps: "little or no preparation" through
      "some preparation" up to "medium preparation".  The +1 band is therefore
      the most common *and* the most heterogeneous, which is a reason to keep
      reading it as "a reachable step up" and not to subdivide it.
    * **The largest possible climb is +3** (2 -> 5), not +4.  So the
      ``delta >= 3`` over-reach band is now reachable only from the floor, and
      it means exactly one thing: "no formal preparation" to "doctoral or
      professional".  Scoring it low is more obviously right than it was when
      +3 could also mean 2 -> 5's much milder neighbours.
    * **The floor is 2.**  See :data:`_UNKNOWN_ZONE_FALLBACK`.

    A MISSING CANDIDATE ZONE IS NEUTRAL, NOT A CRASH AND NOT A PENALTY.  93 of
    1,016 corpus rows have no zone; 75 are "..., All Other" residuals that
    retrieval already drops, and of the 18 real ones, 17 are the military group
    (SOC ``55-``).  An unknown zone is scored as **delta 0** -- the same value a
    role at the user's own level gets -- which is the honest reading of "we
    cannot measure the step, so assume there is not one".  It is not zero: under
    ``stay_lateral`` a lateral move is the *best* outcome (0.8), and silently
    handing a soldier 0.0 there would be a penalty wearing neutrality's clothes.
    """
    delta = 0 if candidate_zone is None else candidate_zone - current_zone
    up3, up2, up1, level, down1, down2 = _ZONE_BANDS.get(
        seniority_intent, _ZONE_BANDS[None]
    )
    if delta >= 3:
        return up3
    if delta == 2:
        return up2
    if delta == 1:
        return up1
    if delta == 0:
        return level
    if delta == -1:
        return down1
    return down2


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------


def _cosine_similarity(
    a: "np.ndarray | list[float]",
    b: "np.ndarray | list[float]",
) -> float:
    """Cosine similarity, accepting either a cached np.float32 vector or a list.

    asarray rather than array: cache entries are already ndarrays, so copying
    6 KB per call is real waste.  Lists still arrive here from
    ``path_deep_fit``'s centroid helpers' ``.tolist()`` results and from tests
    that plant vectors directly.
    """
    va, vb = np.asarray(a), np.asarray(b)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def _embed_entry_bytes(key: str, vec: "np.ndarray | list[float]") -> int:
    """Resident cost of one _EMBED_CACHE entry, in bytes.

    sys.getsizeof already covers the data buffer for an ndarray, but a list holds
    only *pointers* -- its 1536 float objects are separate allocations at 24 bytes
    each, and the cache holds the only reference to them.  Summing them is what
    makes the real cost of the pre-2026-09-16 list[float] storage visible instead
    of under-reporting a 48 KB entry as 12 KB.
    """
    total = sys.getsizeof(key) + sys.getsizeof(vec) + _EMBED_ENTRY_OVERHEAD_BYTES
    if isinstance(vec, list):
        total += sum(sys.getsizeof(f) for f in vec)
    return total


def _evict_to_budget() -> None:
    """Evict oldest-first until _EMBED_CACHE fits _EMBED_CACHE_MAX_BYTES.

    Eviction order is insertion order, not true recency -- nothing calls
    move_to_end on a cache hit, so this is FIFO wearing an LRU's name.  Left as
    it was: changing the eviction policy is a behaviour change, and this bound
    is about the budget.

    The total is summed once and then decremented, so the O(n) walk happens once
    per _batch_embed call rather than once per evicted entry.
    """
    total = sum(_embed_entry_bytes(k, v) for k, v in _EMBED_CACHE.items())
    while total > _EMBED_CACHE_MAX_BYTES and _EMBED_CACHE:
        key, vec = _EMBED_CACHE.popitem(last=False)
        total -= _embed_entry_bytes(key, vec)


def _batch_embed(texts: list[str], client) -> None:
    """Fetch embeddings for any texts not already in _EMBED_CACHE.

    Deduplicates the missing texts and batches them into as few API calls as
    the per-request input cap allows -- one call in the typical case.  Silently
    no-ops on any API failure -- callers receive 0 similarity for uncached texts.

    Vectors are stored as np.float32, which is the one place a plain list from
    the OpenAI SDK is converted.  float32 costs 6.18 KB/entry against 48.50 KB
    for list[float] (see the _EMBED_CACHE comment), and the precision loss is
    negligible for cosine similarity: these vectors are unit-normalised and a
    float32 mantissa carries ~7 decimal digits, far finer than any ranking
    decision made downstream.  numpy rather than array.array or packed bytes
    because every consumer already feeds numpy, so this avoids a per-read
    conversion at no memory cost.
    """
    missing = list(dict.fromkeys(t for t in texts if t not in _EMBED_CACHE))
    if not missing:
        return
    try:
        for start in range(0, len(missing), _EMBED_BATCH_MAX_INPUTS):
            chunk = missing[start:start + _EMBED_BATCH_MAX_INPUTS]
            resp = client.embeddings.create(model="text-embedding-3-small", input=chunk)
            for item in resp.data:
                _EMBED_CACHE[chunk[item.index]] = np.asarray(
                    item.embedding, dtype=np.float32
                )
            # Evict after inserting, not before: the pre-insert arithmetic this
            # replaced could only bound an entry *count*, and a budget in bytes
            # cannot be predicted from len(chunk) alone.
            _evict_to_budget()
    except Exception:
        _log.warning("embedding API call failed (%d texts)", len(missing), exc_info=True)


def _embed_one(text: str, client) -> "np.ndarray | None":
    """Return the unit-normalised embedding of *text*, or None if unavailable."""
    if client is None or not text:
        return None
    _batch_embed([text], client)
    vec = _EMBED_CACHE.get(text)
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    return arr / norm if norm > 0 else None


def _rescale_cosine(value: float) -> float:
    """Map a raw cosine onto [0, 1] through the fixed band in :data:`_COSINE_FLOOR`.

    Clipped at both ends, so an unusually close or unusually distant pair
    saturates rather than escaping the weight budget the caller allocated.
    """
    span = _COSINE_CEILING - _COSINE_FLOOR
    return float(min(1.0, max(0.0, (value - _COSINE_FLOOR) / span)))


# ---------------------------------------------------------------------------
# User documents -- the query side, composed entirely from the user's own text
# ---------------------------------------------------------------------------


def _compose_skills_document(profile: UserProfile) -> str | None:
    """Compose the user's skills into one document, grouped by proficiency.

    Grouped rather than weighted, because the comparison target is now a
    *document* -- O*NET's description and tasks prose -- and the symmetric thing
    to compare it against is prose, not a proficiency-weighted centroid of
    thirty separate one-word embeddings (which is the averaging failure
    ``_compute_centroid_score`` fell into; design doc §1.1).  Proficiency
    survives as the natural-language hedge in front of each group, which is
    signal the embedding model does read.

    Returns None when the user has listed no skills at all.
    """
    by_level: dict[str, list[str]] = {"advanced": [], "intermediate": [], "beginner": []}
    for skill in profile.skills:
        name = skill.name.strip()
        if not name:
            continue
        by_level.get(skill.level, by_level["beginner"]).append(name)

    clauses: list[str] = []
    if by_level["advanced"]:
        clauses.append("Highly skilled in " + ", ".join(by_level["advanced"]) + ".")
    if by_level["intermediate"]:
        clauses.append("Experienced with " + ", ".join(by_level["intermediate"]) + ".")
    if by_level["beginner"]:
        clauses.append("Some familiarity with " + ", ".join(by_level["beginner"]) + ".")
    return " ".join(clauses) if clauses else None


def _compose_title_document(profile: UserProfile) -> str | None:
    """The title as a sentence -- the identity half of the anchor query."""
    title = (profile.current_title or "").strip()
    return f"Works as a {title}." if title else None


def _compose_profile_document(profile: UserProfile) -> str | None:
    """Title plus skills -- the query used when there is no usable corpus anchor.

    Reaching for this rather than the bare title is the whole lesson of design
    doc §2.1: a two-word title is dominated by one token, and comparing it to
    300-token role documents is the asymmetry that produced "Data Scientists ->
    Political Scientists".  A title *sentence* with the user's skills after it
    is a document, and documents compare to documents.
    """
    skills_doc = _compose_skills_document(profile)
    title = (profile.current_title or "").strip()
    if title and skills_doc:
        return f"Works as a {title}. {skills_doc}"
    if title:
        return f"Works as a {title}."
    return skills_doc


def _build_behavioral_profile(profile: UserProfile) -> str | None:
    """Compose a single descriptive string from completed assessment results.

    Prefers full description text over short label names so the embedding lands
    in the right semantic neighbourhood relative to O*NET's task language.
    Returns None if no assessment data is present -- callers skip the style term.
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


def _has_any_signal(profile: UserProfile) -> bool:
    """True when there is *something* to retrieve on: a title or a skill."""
    if profile.current_title and profile.current_title.strip():
        return True
    return any(s.name.strip() for s in profile.skills)


# ---------------------------------------------------------------------------
# Anchor resolution -- the only O*NET traffic left in Tier 1
# ---------------------------------------------------------------------------


def _resolve_current_zone(
    profile: UserProfile,
    onet_client: OnetClient,
    openai_client=None,
    corpus: OccupationCorpus | None = None,
) -> _Anchor:
    """Resolve the user's own occupation to an O*NET code and a Job Zone.

    **The corpus resolves the title, not O*NET's keyword search.**  That is a
    change from every previous version of this function and it is the single
    largest accuracy fix in F-4 after the candidate source itself, so it is
    worth recording what was measured.  ``search_occupations`` is a fuzzy match
    over occupation *titles*, which is the surface-form matching this whole
    redesign exists to remove -- and on the F-2 profile set its first result is
    wrong often enough to poison the anchor everything else hangs off::

        "Senior Backend Engineer" -> Biofuels/Biodiesel Technology and
                                     Product Development Managers
        "DevOps Engineer"         -> Nuclear Engineers
        "Growth Ninja"            -> Soil and Plant Scientists
        "Journeyman Electrician"  -> Helpers--Electricians

    The old funnel survived those because the candidate pool came from the job
    family *and* an LLM keyword search *and* a SOC allow-list, so three other
    mechanisms were papering over the bad anchor.  With retrieval anchored on
    one vector there is nothing left to paper over it: a Senior Backend Engineer
    anchored on Biofuels Managers is shown Fuel Cell Engineers and Biomass Power
    Plant Managers, which is exactly what this scorer did before the change.

    Embedding the user's *profile document* (title plus skills) and taking the
    nearest corpus row fixes all four cases above, resolves "Growth Ninja" to
    Search Marketing Strategists -- a labelled primary for that profile -- and
    costs **zero** O*NET calls.  ``include_all_other=True``: this asks "which
    O*NET code *is* this person", and "Engineers, All Other" is a truthful
    answer for someone whose title maps nowhere else.

    O*NET calls, therefore:

    * **0** on the normal path -- the corpus answers both the code and the zone.
    * **1** if the resolved code is one of the 93 rows with no zone in the
      sidecar (75 are "..., All Other" residuals, 17 are military), which falls
      back to ``get_job_zone``.
    * **1** when there is no OpenAI client at all, where ``search_occupations``
      remains as the degraded path -- keeping the module's promise that a
      missing ``OPENAI_API_KEY`` degrades rather than fails.

    This also retires the two-step LLM ladder the function used to run
    (``_normalize_title_for_onet``, then a broad-category prompt): asking a model
    to guess an O*NET title, then searching for that guess, is a worse and more
    expensive way to do what one dot product against the 1,016 codes that
    actually exist does exactly.  It is the fix for the live ACC-4 / S22 failure
    too, where an unresolvable title produced no anchor at all.
    """
    if profile.career_status == "first_job" or not profile.current_title:
        return _Anchor(
            zone=_UNKNOWN_ZONE_FALLBACK, code=None, zone_resolved=False, title_used=None
        )

    title = profile.current_title
    code: str | None = None
    same_job: tuple[str, ...] = ()
    if corpus is not None and openai_client is not None:
        same_job = _resolve_code_from_corpus(profile, corpus, openai_client)
        code = same_job[0] if same_job else None

    if code is None:
        try:
            results = onet_client.search_occupations(title)
            if results:
                code = results[0].code
                same_job = (code,)
        except (OnetAPIError, OnetRateLimitError):
            _log.warning("O*NET title search failed for %r", title, exc_info=True)

    if code is None:
        return _Anchor(
            zone=_UNKNOWN_ZONE_FALLBACK,
            code=None,
            zone_resolved=False,
            title_used=title,
        )

    all_other = _code_is_all_other(code, corpus)
    zone = corpus.zones.get(code) if corpus is not None else None
    if zone is not None:
        return _Anchor(
            zone=zone,
            code=code,
            zone_resolved=True,
            title_used=title,
            code_is_all_other=all_other,
            same_job_codes=same_job,
        )

    try:
        return _Anchor(
            zone=onet_client.get_job_zone(code),
            code=code,
            zone_resolved=True,
            title_used=title,
            code_is_all_other=all_other,
            same_job_codes=same_job,
        )
    except (OnetAPIError, OnetRateLimitError):
        return _Anchor(
            zone=_UNKNOWN_ZONE_FALLBACK,
            code=code,
            zone_resolved=False,
            title_used=title,
            code_is_all_other=all_other,
            same_job_codes=same_job,
        )


def _resolve_code_from_corpus(
    profile: UserProfile,
    corpus: OccupationCorpus,
    openai_client,
) -> tuple[str, ...]:
    """Codes that might be the user's own job, best first.

    Usually one.  More when the top candidates are within
    :data:`_ANCHOR_TIE_MARGIN` of each other, which means resolution cannot
    tell them apart and all of them have to be kept out of the results.

    See :func:`_resolve_current_zone` for why this is the primary resolver and
    what O*NET's own keyword search does instead.  A residual bucket is a
    truthful *identity* and a poor *query*; :func:`_build_query` is what keeps
    those two uses apart.
    """
    document = _compose_profile_document(profile)
    vec = _embed_one(document, openai_client) if document else None
    if vec is None:
        return ()
    title_document = _compose_title_document(profile)
    vec = _blend(
        vec,
        _embed_one(title_document, openai_client) if title_document else None,
        _ANCHOR_TITLE_MIX,
    )
    try:
        matches = corpus.retrieve(
            vec, k=_ANCHOR_TIE_LOOKAHEAD, include_all_other=True
        )
    except (CorpusUnavailable, ValueError):
        return ()
    if not matches:
        return ()
    best = matches[0].score
    return tuple(
        match.code for match in matches if best - match.score <= _ANCHOR_TIE_MARGIN
    )


def _code_is_all_other(code: str, corpus: OccupationCorpus | None) -> bool:
    if corpus is None:
        return False
    row = corpus.index_of(code)
    return row is not None and is_all_other_title(corpus.titles[row])


# ---------------------------------------------------------------------------
# Query construction -- one vector per request, per move_intent
# ---------------------------------------------------------------------------


def _blend(
    primary: "np.ndarray", secondary: "np.ndarray | None", mix: float
) -> "np.ndarray":
    """``(1-mix)*primary + mix*secondary``, re-normalised.  Identity if secondary is None."""
    if secondary is None or mix <= 0.0:
        return primary
    blended = (1.0 - mix) * primary + mix * secondary
    norm = float(np.linalg.norm(blended))
    return blended / norm if norm > 0 else primary


def _build_query(
    profile: UserProfile,
    anchor: _Anchor,
    corpus: OccupationCorpus,
    skills_vec: "np.ndarray | None",
    behavioral_vec: "np.ndarray | None",
    openai_client,
) -> tuple["np.ndarray | None", bool]:
    """Return ``(query_vector, query_carries_role_identity)`` for this request.

    ``stay_in_field`` / unspecified
        The user's own corpus row.  Document-to-document and symmetric, which
        is design doc §3.1 -- and the thing the funnel this replaced asked for
        in a comment of its own: "replace this block with
        ``get_related_occupations(current_code)`` when O*NET adds that
        endpoint; it will produce a tighter, skills-similarity-based pool."
        F-3 is that endpoint, self-built.

    ``adjacent``
        The same anchor rotated toward the skills document by
        :data:`_ADJACENT_SKILLS_MIX`.  Interim; F-6 makes the rotation learned.

    ``fresh_start``
        The skills document, blended with the behavioural profile, with the
        user's own SOC major group excluded at retrieval (see
        :func:`_retrieve_candidates`).  **Never** distance-from-current-job:
        "far from software engineering" includes Logging Worker, and the
        ``_ZONE_DAMPENING_FRESH_START`` constant this replaces was the patch
        over exactly that mistake.

    The second element of the tuple is False whenever the query is not built
    from the user's occupation, so ``score_paths`` knows the retrieval cosine is
    not measuring role identity and can zero ``role_w`` instead of
    double-counting the skills document.
    """
    anchor_vec: "np.ndarray | None" = None
    if (
        anchor.code is not None
        and not anchor.code_is_all_other
        and corpus.index_of(anchor.code) is not None
    ):
        anchor_vec = corpus.vector_for(anchor.code)

    if profile.move_intent == "fresh_start":
        if skills_vec is None:
            # No skills to transfer.  The anchor is all there is; the SOC-family
            # exclusion still keeps the results out of the field being left.
            return anchor_vec, anchor_vec is not None
        return _blend(skills_vec, behavioral_vec, _FRESH_START_BEHAVIORAL_MIX), False

    if anchor_vec is None:
        # No usable corpus anchor: an All-Other row (a ~50-character title-only
        # document, a poor query however good an identity), a code outside the
        # corpus, or no code at all.  The user's own composed document is the
        # better query in every one of those cases.
        document = _compose_profile_document(profile)
        vec = _embed_one(document, openai_client) if document else None
        carries_identity = vec is not None and bool(profile.current_title)
        return vec, carries_identity

    if profile.move_intent == "adjacent":
        return _blend(anchor_vec, skills_vec, _ADJACENT_SKILLS_MIX), True

    return anchor_vec, True


def _retrieve_candidates(
    profile: UserProfile,
    anchor: _Anchor,
    corpus: OccupationCorpus,
    query: "np.ndarray",
) -> list[Match]:
    """One ``matrix @ query``, with the two hard filters this tier is allowed.

    The user's own occupation is excluded -- they have that job -- along with
    anything resolution could not tell apart from it.  For ``fresh_start`` the
    user's SOC minor group goes too, which is design doc §3.3's "different
    field, same capabilities" constraint expressed as F-3's named filter rather
    than as an allow-list; see :data:`_FRESH_START_EXCLUDE_PREFIX_LEN` for why
    the minor group and not the major one.

    **There is no SOC allow-list here and there must never be one again.**  The
    old ``_DEFAULT_ALLOWED_SOC_PREFIXES`` listed eight families and silently
    made every other occupation unreachable; F-2 measured what that cost the
    users inside the excluded families (an electrician: zero of three primary
    labels reachable) and F-1 showed the title-domination failure it was written
    to patch does not occur against role documents.
    """
    exclude_codes = list(anchor.excluded_codes)
    exclude_prefixes: tuple[str, ...] = ()
    if (
        profile.move_intent == "fresh_start"
        and anchor.code
        and _FRESH_START_EXCLUDE_PREFIX_LEN > 0
    ):
        # "15-1252.00" -> "15-1": the SOC minor group. See
        # _FRESH_START_EXCLUDE_PREFIX_LEN for why not the major group.
        exclude_prefixes = (anchor.code[:_FRESH_START_EXCLUDE_PREFIX_LEN],)
    return corpus.retrieve(
        query,
        k=_RETRIEVE_K,
        exclude_codes=exclude_codes,
        exclude_soc_prefixes=exclude_prefixes,
    )


# ---------------------------------------------------------------------------
# Per-candidate signals -- all served from the corpus, no per-candidate I/O
# ---------------------------------------------------------------------------


def _dot_rows(corpus: OccupationCorpus, rows: list[int], vec: "np.ndarray | None") -> "np.ndarray":
    """Cosine of *vec* against the given corpus rows.  Zeros when vec is None.

    The corpus matrix is L2-normalised on write and *vec* is normalised by
    :func:`_embed_one`, so the dot product is already the cosine.
    """
    if vec is None or not rows:
        return np.zeros(len(rows), dtype=np.float32)
    return corpus.matrix[rows] @ np.asarray(vec, dtype=np.float32)


def _build_signals(
    profile: UserProfile,
    anchor: _Anchor,
    corpus: OccupationCorpus,
    matches: list[Match],
    skills_vec: "np.ndarray | None",
    behavioral_vec: "np.ndarray | None",
) -> list[_Signals]:
    """Score every retrieved candidate on all four terms, in two matrix products.

    ``role`` is the retrieval cosine itself.  ``coverage`` and ``style`` are the
    user's skills document and behavioural profile against the same role
    document.  ``zone`` reads the corpus sidecar.  No candidate is fetched, and
    nothing here can raise on a candidate the corpus already returned.
    """
    rows = [m.row for m in matches]
    coverage_raw = _dot_rows(corpus, rows, skills_vec)
    style_raw = _dot_rows(corpus, rows, behavioral_vec)

    signals: list[_Signals] = []
    for i, match in enumerate(matches):
        candidate_zone = corpus.zones.get(match.code)
        signals.append(
            _Signals(
                match=match,
                role=_rescale_cosine(match.score),
                coverage=_rescale_cosine(float(coverage_raw[i])),
                style=_rescale_cosine(float(style_raw[i])),
                zone=_zone_delta_score(
                    anchor.zone, candidate_zone, profile.seniority_intent
                ),
                zone_raw=candidate_zone,
            )
        )
    return signals


def _overlapping_skills(
    profile: UserProfile,
    corpus: OccupationCorpus,
    matches: list[Match],
    openai_client,
) -> dict[str, list[str]]:
    """Per-candidate display list: which of the user's skills this role uses.

    One embedding per distinct user skill -- the user's *own* text, which is
    what ``_EMBED_CACHE`` is for -- dotted against the retrieved role documents
    as a single matrix product.  Zero extra API calls per candidate, which is
    the point: the old implementation read this off each candidate's fetched
    O*NET skills profile, and that fetch is what moved to F-5.

    The threshold is :data:`_OVERLAP_MIN_COSINE`, not the 0.70 the item-based
    matcher used and not the document-scale rescale either: a two-word skill
    against a 300-token role document lands far lower than the same skill
    against another skill *name*, and both of those bars name nothing at all.
    """
    names = list(dict.fromkeys(s.name.strip() for s in profile.skills if s.name.strip()))
    if not names or openai_client is None or not matches:
        return {}

    _batch_embed(names, openai_client)
    vectors: list["np.ndarray"] = []
    embedded: list[str] = []
    for name in names:
        cached = _EMBED_CACHE.get(name)
        if cached is None:
            continue
        arr = np.asarray(cached, dtype=np.float32)
        norm = float(np.linalg.norm(arr))
        if norm > 0:
            vectors.append(arr / norm)
            embedded.append(name)
    if not vectors:
        return {}

    rows = [m.row for m in matches]
    # (candidates x dims) @ (dims x skills) -> (candidates x skills)
    sims = corpus.matrix[rows] @ np.asarray(vectors, dtype=np.float32).T

    out: dict[str, list[str]] = {}
    for i, match in enumerate(matches):
        ranked = sorted(
            ((float(sims[i][j]), embedded[j]) for j in range(len(embedded))),
            key=lambda pair: pair[0],
            reverse=True,
        )
        out[match.code] = [
            name
            for score, name in ranked[:_OVERLAP_TOP_K]
            if score >= _OVERLAP_MIN_COSINE
        ]
    return out


# ---------------------------------------------------------------------------
# Weighting
# ---------------------------------------------------------------------------


def _weights(
    profile: UserProfile,
    zone_is_reliable: bool,
    has_behavioral: bool,
    has_role_identity: bool,
) -> tuple[float, float, float, float]:
    """Return ``(role_w, coverage_w, zone_w, style_w)``, summing to 1.0.

    The scheme is the shape that was here before F-4 -- zone reliability x
    behavioural presence x stated priority selects a split, ``move_intent``
    reserves ``role_w`` first, and the other three are rescaled by
    ``(1 - role_w)`` so the four always sum to one.  (``career_status`` reaches
    this only through ``zone_is_reliable``: a first-job user has no zone to
    resolve, and their fallback zone is treated as reliable because "entry
    level" is the right answer for them rather than a guess.)  What is gone is
    ``_ZONE_DAMPENING_FRESH_START``: it existed because ``fresh_start`` forced
    ``role_w`` to zero and left the field-blind zone delta as the largest
    remaining term, so every zone+1 role floated to the top together.  That is
    no longer true -- ``fresh_start``'s coverage term is a real similarity
    against a real query -- so the patch is deleted rather than ported.
    """
    growth_focused = profile.priority in ("learning_growth", "pay_title")
    if zone_is_reliable and has_behavioral:
        split = _WEIGHTS_BEHAVIORAL_GROWTH if growth_focused else _WEIGHTS_BEHAVIORAL
    elif zone_is_reliable:
        split = _WEIGHTS_GROWTH if growth_focused else _WEIGHTS_BALANCED
    elif has_behavioral:
        split = _WEIGHTS_NO_ZONE_BEHAVIORAL
    else:
        split = _WEIGHTS_NO_ZONE
    coverage_w, zone_w, style_w = split

    role_w = (
        _ROLE_WEIGHT_BY_INTENT.get(profile.move_intent, _ROLE_WEIGHT_DEFAULT)
        if has_role_identity
        else 0.0
    )
    rest = 1.0 - role_w
    return role_w, coverage_w * rest, zone_w * rest, style_w * rest


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
    1. Embed the user's own texts in ONE batched request -- the skills
       document, the title sentence, the combined profile document, and the
       behavioural profile when assessments exist, plus one per listed skill.
       Everything downstream reads the cache.
    2. Resolve the user's own occupation to an O*NET code and Job Zone.  The
       corpus answers both, so this normally makes **no** O*NET call; see
       :func:`_resolve_current_zone` for the two cases that make one.
    3. Build one query vector per :attr:`UserProfile.move_intent` and retrieve
       ``_RETRIEVE_K`` candidates from the corpus -- one matrix product, no
       network.
    4. Score each candidate on four terms, all read off the corpus::

           role     = the retrieval cosine (document-to-document)
           coverage = cosine(user skills document, role document)
           style    = cosine(user behavioural profile, role document)
           zone     = _zone_delta_score(anchor zone, corpus.zones[code], ...)

           final    = role_w*role + coverage_w*coverage
                      + zone_w*zone + style_w*style

    5. Return up to ``_TOP_N`` results sorted by score descending.

    Args:
        user_profile:  Career snapshot of the user.
        onet_client:   Authenticated O*NET Web Services client, used only for
                       anchor resolution.
        openai_client: Optional OpenAI client.  When None, a user whose own
                       occupation resolved still gets anchor-based retrieval
                       and a zone signal; coverage, style and the per-card skill
                       list are unavailable, which is a degrade rather than a
                       failure.

    Raises:
        InsufficientProfile: The profile has neither a usable title nor a single
            skill.  The caller turns this into ``profile_incomplete``.
        CorpusUnavailable: The occupation corpus could not be loaded.  A genuine
            service outage; the caller answers 500 and the client retries.
    """
    if not _has_any_signal(user_profile):
        raise InsufficientProfile(
            "profile has neither a job title nor any skills to retrieve on"
        )

    corpus = get_corpus()

    skills_document = _compose_skills_document(user_profile)
    behavioral_document = _build_behavioral_profile(user_profile)
    profile_document = _compose_profile_document(user_profile)
    title_document = _compose_title_document(user_profile)

    # ONE OpenAI request per invocation, sent before anything else needs a
    # vector, so every later `_embed_one` / `_overlapping_skills` call is a cache
    # read.  The inputs are the user's own texts and nothing else: up to four
    # short documents plus one per listed skill.  Measured across the 20 F-2
    # profiles that is 3-14 entries and 19-90 KB in _EMBED_CACHE per distinct
    # user, against the 300-700 the per-candidate role-item embedding used to
    # add on every cold run -- which is the demand behind the 2026-09-15 OOM,
    # removed rather than capped.
    if openai_client is not None:
        _batch_embed(
            [
                text
                for text in (
                    skills_document,
                    behavioral_document,
                    profile_document,
                    title_document,
                )
                if text
            ]
            + [s.name.strip() for s in user_profile.skills if s.name.strip()],
            openai_client,
        )

    anchor = _resolve_current_zone(user_profile, onet_client, openai_client, corpus)

    skills_vec = _embed_one(skills_document, openai_client) if skills_document else None
    behavioral_vec = (
        _embed_one(behavioral_document, openai_client) if behavioral_document else None
    )

    query, has_role_identity = _build_query(
        user_profile, anchor, corpus, skills_vec, behavioral_vec, openai_client
    )
    if query is None:
        # Nothing to retrieve on: no corpus anchor and no embeddings.  The
        # profile is fine; the dependency is not.  An empty list here is the
        # caller's transient-failure path, deliberately NOT InsufficientProfile.
        _log.warning(
            "no query vector for user profile (title=%r, skills=%d, openai=%s)",
            user_profile.current_title,
            len(user_profile.skills),
            openai_client is not None,
        )
        return []

    try:
        matches = _retrieve_candidates(user_profile, anchor, corpus, query)
    except ValueError:
        _log.warning("retrieval rejected the query vector", exc_info=True)
        return []

    zone_is_reliable = (
        anchor.zone_resolved or user_profile.career_status == "first_job"
    )
    role_w, coverage_w, zone_w, style_w = _weights(
        user_profile, zone_is_reliable, behavioral_vec is not None, has_role_identity
    )

    signals = _build_signals(
        user_profile, anchor, corpus, matches, skills_vec, behavioral_vec
    )
    overlaps = _overlapping_skills(user_profile, corpus, matches, openai_client)

    scored: list[ScoredPath] = []
    for sig in signals:
        raw = (
            role_w * sig.role
            + coverage_w * sig.coverage
            + zone_w * sig.zone
            + style_w * sig.style
        )
        scored.append(
            ScoredPath(
                onet_code=sig.match.code,
                title=sig.match.title,
                score=round(max(0.0, min(1.0, raw)), 4),
                overlapping_skills=overlaps.get(sig.match.code, []),
            )
        )

    scored.sort(key=lambda p: p.score, reverse=True)

    if os.environ.get("SOLVERAH_SCORING_DEBUG"):
        _print_scoring_debug(
            user_profile,
            anchor,
            (role_w, coverage_w, zone_w, style_w),
            zone_is_reliable,
            behavioral_vec is not None,
            signals,
            scored,
        )

    return scored[:_TOP_N]


# ---------------------------------------------------------------------------
# Debug output (env-gated)
# ---------------------------------------------------------------------------


def _print_scoring_debug(
    profile: UserProfile,
    anchor: _Anchor,
    weights: tuple[float, float, float, float],
    zone_is_reliable: bool,
    has_behavioral: bool,
    signals: list[_Signals],
    scored: list[ScoredPath],
) -> None:
    """Write scoring_debug.txt.  Gated on SOLVERAH_SCORING_DEBUG.

    The unconditional ``llm_debug.txt`` write this replaced ran on **every**
    request in production, not just when debugging -- a disk write per scored
    user, for a log whose subject (the keyword-generation and title-normalisation
    LLM calls) no longer exists.
    """
    out_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "scoring_debug.txt")
    )
    role_w, coverage_w, zone_w, style_w = weights
    by_code = {s.match.code: s for s in signals}
    lines = [
        "=" * 60,
        "PATH SCORING DEBUG (F-4 corpus retrieval)",
        "=" * 60,
        f"Title      : {profile.current_title!r}",
        f"Status     : {profile.career_status}",
        f"Anchor     : code={anchor.code!r} zone={anchor.zone} "
        f"(resolved={anchor.zone_resolved}, reliable={zone_is_reliable}, "
        f"all_other={anchor.code_is_all_other})",
        f"Weights    : role={role_w:.2f} coverage={coverage_w:.2f} "
        f"zone={zone_w:.2f} style={style_w:.2f}",
        f"Intent     : move={profile.move_intent} "
        f"seniority={profile.seniority_intent} priority={profile.priority}",
        f"Behavioral : {has_behavioral}",
        f"Retrieved  : {len(signals)} candidates (k={_RETRIEVE_K})",
        "",
    ]
    for rank, path in enumerate(scored[:_TOP_N], 1):
        sig = by_code[path.onet_code]
        lines.append(
            f"#{rank:<2} {path.score:.4f}  [{path.onet_code}] {path.title}"
        )
        lines.append(
            f"      role={sig.role:.3f} (cos {sig.match.score:.3f})  "
            f"coverage={sig.coverage:.3f}  style={sig.style:.3f}  "
            f"zone={sig.zone:.3f} (z{sig.zone_raw} vs z{anchor.zone})"
        )
        lines.append(f"      skills: {path.overlapping_skills}")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
