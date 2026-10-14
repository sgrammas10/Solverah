"""Every constant the CompanyLens research pipeline runs on, in one versioned module.

The aggregation rules are PROVISIONAL (PRODUCT_DECISIONS.md section 2: "'Known'
thresholds (min count, recency, consistency) are ours, provisional, and go through the
sensitivity test"). A change to any constant below that changes what a trait record
says is a new ``AGGREGATION_VERSION``: the version is written on every
``company_trait_record`` row, so a rule change is visible per row rather than inferred
from a date.

Five of the rules are PROVISIONAL IN A SECOND SENSE: they stand in for an answer Julie
has not given yet. Each is marked "PROVISIONAL -- awaiting Julie ask N" (the asks went
to her through the orchestrator on 2026-10-13, from research-ground-truth's review of
C5). When she answers, the constant changes here and the version bumps.

Sign convention, restated per the plan's global constraint: nothing here reads a gap.
Scores are the scorer's 0..1 band values on the company's own trait; the person side
is never seen by this package.
"""

from __future__ import annotations

__all__ = [
    "AGGREGATION_VERSION",
    "COUNT_CONFIDENCE_BASE",
    "COUNT_CONFIDENCE_PER_ITEM",
    "EMPLOYER_SPEAKER_PATTERN",
    "INDEPENDENT_SOURCE_TYPES",
    "JOB_POSTING_MIN_DISTINCT_POSTINGS",
    "MIN_SCORED_ITEMS",
    "MIXED_MIN_SIDE_COUNT",
    "MIXED_MIN_SIDE_FRACTION",
    "PARAPHRASE_MAX_SHARED_WORDS",
    "PARAPHRASE_MAX_TRIGRAM_REUSE",
    "POSTING_JOB_HARD_LIMIT_SECONDS",
    "POSTING_JOB_SOFT_LIMIT_SECONDS",
    "RECENCY_DAYS",
    "RESEARCH_CACHE_DAYS",
    "RESEARCH_JOB_HARD_LIMIT_SECONDS",
    "RESEARCH_JOB_SOFT_LIMIT_SECONDS",
    "RESEARCH_MAX_FETCHES",
    "RESEARCH_MAX_SEARCHES",
    "RESEARCH_MAX_TOKENS",
    "RESEARCH_THREAD_WORKERS",
    "SCORING_BATCH_SIZE",
    "SCRUB_MIN_LABEL_CHARS",
    "SCRUB_REPLACEMENT",
    "SIZE_DISCOUNT_BY_BAND",
    "SIZE_DISCOUNT_UNKNOWN",
    "SOURCE_YIELD_TARGETS",
    "SPLIT_POINT",
    "SPREAD_FULL_STD",
    "SPREAD_MAX_PENALTY",
    "STALE_QUEUED_MINUTES",
    "TIME_SPLIT_KNOWN_MIN_INDEPENDENT_RECENT",
    "VERIFY_MIN_CITED_CHARS",
    "VERIFY_MIN_COVERAGE",
    "VERIFY_MIN_RUN_WORDS",
]

# ---------------------------------------------------------------------------
# Aggregation (aggregate.py). Plan 2026-10-13, C5, "REVISED to Julie's anchors ruling 5";
# agg-v2 is C5b (2026-10-13), research-ground-truth's review findings F4-F8 applied.
# ---------------------------------------------------------------------------

#: Stamped on every trait record this module's rules produced.
AGGREGATION_VERSION = "agg-v2-2026-10-13"

#: A trait is `unknown` with fewer than this many NON-abstaining item scores.
MIN_SCORED_ITEMS = 3

#: ...or with no INDEPENDENT non-abstaining item dated inside this window (24 months).
#: Recency is read from `published_at`; an item with no publication date (an
#: access-dated careers page, rubric v4.11 rule 3) counts toward the item count but
#: never toward recency, because its vintage is unknown and v4.11 forbids letting a bare
#: date stand in for it. Company-authored items never count toward recency either
#: (review F8): a careers page is current by construction and says nothing about when
#: the described culture was last observed.
RECENCY_DAYS = 730

#: The source types whose author is NOT the company: an employee's own review, or
#: independent reporting. Everything else (careers page, job posting, first-person
#: company material, a 10-K, a pasted posting) is the company describing itself.
#: PROVISIONAL -- awaiting Julie ask 3 (company-authored-only evidence): until she
#: answers, a trait is `known` only when at least one of the items supporting the
#: estimate is independent (review F4, gate 5). An employer's reply on a review site is
#: company-authored whatever its source type says; `EMPLOYER_SPEAKER_PATTERN` is how a
#: reply is recognised from its `speaker`.
INDEPENDENT_SOURCE_TYPES = ("employee_review", "news")
EMPLOYER_SPEAKER_PATTERN = (
    r"employer|company(?:'s)?\s+(?:response|reply|representative)|"
    r"official\s+(?:response|reply)|management\s+(?:response|reply)|"
    r"(?:response|reply)\s+from|hr\s+(?:response|reply)|"
    r"\bceo\b|\bfounder\b|\bcofounder\b|co-founder|chief\s+\w+\s+officer|"
    r"spokesperson|press\s+release"
)

#: Items split into a low side (score < SPLIT_POINT) and a high side (score >
#: SPLIT_POINT). A score exactly at the split (the 0.5 "Mixed" band) sits on neither
#: side: it counts toward the item total and toward a `known` estimate (review F5),
#: never toward a side.
SPLIT_POINT = 0.5

#: `mixed` needs real support on BOTH sides: at least this many items on the smaller
#: side, and the smaller side at least this fraction of the non-abstaining items.
#: Anything less is `known` with the spread lowering confidence (ruling 5: strength,
#: recency and amount decide whether one pole predominates; contradiction alone does
#: not mean mixed).
#: PROVISIONAL -- awaiting Julie ask 1 (the 6:2 / 5:2 cases): a count rule, >= 2 per
#: side with the minority >= 25%, until she rules otherwise.
MIXED_MIN_SIDE_COUNT = 2
MIXED_MIN_SIDE_FRACTION = 0.25

#: A split explained by TIME (the recent items single-sided one way, the older ones the
#: other) is reported `known` in the RECENT direction when the recent side alone holds
#: at least this many independent items; `split_explained_by = 'time'` stays on the
#: known record as the "changed recently" note. With fewer, the record stays `mixed`
#: with the same note.
#: PROVISIONAL -- awaiting Julie ask 4 (time-explained splits).
TIME_SPLIT_KNOWN_MIN_INDEPENDENT_RECENT = 3

#: Confidence from the amount of evidence: 0.2 + 0.1 * n, capped at 1.0. Three items
#: (the minimum) give 0.5; eight or more give 1.0.
#: Weighting of items by the scorer's per-item confidence, by strength or by recency:
#: NONE in v1. The scorer's confidence is STORED on each score row and never read by
#: the aggregation. PROVISIONAL -- awaiting Julie ask 2 (weighting).
COUNT_CONFIDENCE_BASE = 0.2
COUNT_CONFIDENCE_PER_ITEM = 0.1

#: Spread lowers a `known` record's confidence: population standard deviation of the
#: scored values, scaled so SPREAD_FULL_STD (the widest spread the bands can produce is
#: 0.4, half the items at 0.1 and half at 0.9) costs SPREAD_MAX_PENALTY of the
#: confidence. Five items at 0.9 and one at 0.1 have std ~0.30 and lose ~37%.
SPREAD_FULL_STD = 0.4
SPREAD_MAX_PENALTY = 0.5

#: Size discount: the larger the company, the less a company-wide read says about the
#: team the user would join. Keyed by the Environment Report's own `stage_size` band
#: (company_evidence_store.stage_size_for_headcount). Provisional, like everything here.
SIZE_DISCOUNT_BY_BAND = {1: 1.0, 2: 0.95, 3: 0.85, 4: 0.75, 5: 0.65}
#: A company whose size the research did not find is treated as band 3 ("hundreds").
SIZE_DISCOUNT_UNKNOWN = 0.85

#: A single extreme item against a company-wide band: NO clamp in v1. A lone 0.9 among
#: 0.5s moves the estimate exactly as the mean says. PROVISIONAL -- awaiting Julie ask 5.

# ---------------------------------------------------------------------------
# Research (research.py, textcheck.py): excerpt verification and the paraphrase gate.
# Review F1 and F13 (2026-10-13) replaced the fragment-and-run rule with coverage.
# ---------------------------------------------------------------------------

#: An excerpt shorter than this (after normalisation) is never verified: the floor is
#: scorer_pipeline.verify_quote's own.
VERIFY_MIN_CITED_CHARS = 10

#: An excerpt word counts as covered when it sits inside a run of at least this many
#: consecutive words that the excerpt shares with a citation FROM THE SAME SOURCE. Three
#: is short enough that one corrected typo costs one word, long enough that a stock
#: phrase ("of the company") cannot cover a sentence on its own.
VERIFY_MIN_RUN_WORDS = 3

#: Verified = at least this fraction of the excerpt's words covered by the item's own
#: source's citations (union over them). An invented sentence that contains one real
#: fragment covers that fragment and nothing else, and fails.
VERIFY_MIN_COVERAGE = 0.9

#: The paraphrase gate. A paraphrase may share with its excerpt (and with every other
#: citation from the same URL) no run of MORE than min(PARAPHRASE_MAX_SHARED_WORDS,
#: floor(words / 2)) consecutive words -- seven for a long excerpt, two for a four-word
#: one -- and may reuse at most PARAPHRASE_MAX_TRIGRAM_REUSE of the excerpt's word
#: trigrams overall, so a near-copy that changes every fifth word is still a copy. Any
#: quotation mark in a paraphrase rejects it: a quoted clause is a verbatim quote on a
#: page (GAP-14) whatever surrounds it.
PARAPHRASE_MAX_SHARED_WORDS = 7
PARAPHRASE_MAX_TRIGRAM_REUSE = 0.35

#: Per-call caps on the server tools. v4.11 opens a careers page, a title index, review
#: pages, three or more postings, a ladder of first-person sources, news and (public
#: companies) a 10-K: 10 fetches is too few to work the ladder. 12 searches is ~$0.12.
RESEARCH_MAX_SEARCHES = 12
RESEARCH_MAX_FETCHES = 20

#: Output ceiling for one research turn (thinking plus answer). A full v4.11 record is
#: 30-45 items, each quoted once as a cited line and once inside the JSON; 32k was
#: measured too tight for that (review F3b).
RESEARCH_MAX_TOKENS = 64_000

#: Collector v4.11's per-section yield, as (minimum, maximum); None = no maximum. The
#: run card compares what was kept per source type against these so a thin run is
#: visible as "B: 4 of 12" rather than as six unknowns.
SOURCE_YIELD_TARGETS = {
    "careers_page": (5, 8),
    "employee_review": (12, 15),
    "job_posting": (6, 10),
    "first_person": (3, None),
    "news": (2, 4),
    "disclosure": (3, 6),
}
#: Section C wants its excerpts from at least this many distinct open postings.
JOB_POSTING_MIN_DISTINCT_POSTINGS = 3

# ---------------------------------------------------------------------------
# Scoring (score_items.py)
# ---------------------------------------------------------------------------

#: Items per scorer call. Each item is scored independently inside the schema (one
#: object per item); batching only shares the rubric text across items.
SCORING_BATCH_SIZE = 8

#: Before scoring, the company's name, its domain and the domain's bare label are
#: replaced in the scorer's INPUT by this (review F9: the scorer must not recognise the
#: company and score from reputation; the harness scrubbed its packets for the same
#: reason). The stored excerpt is untouched.
SCRUB_REPLACEMENT = "the company"
#: A bare domain label shorter than this is not scrubbed on its own ("go.com" would
#: otherwise blank every "go"); the full name and the full domain always are.
SCRUB_MIN_LABEL_CHARS = 4

# ---------------------------------------------------------------------------
# Service (service.py, jobs.py)
# ---------------------------------------------------------------------------

#: A `done` run younger than this is served from cache instead of re-researched.
RESEARCH_CACHE_DAYS = 90

#: Celery time limits per job (soft raises SoftTimeLimitExceeded inside the task so the
#: run is marked failed; hard kills the worker process). A research turn streams for
#: minutes while searches and fetches run server-side; scoring is a handful of
#: structured calls on a 300 s client.
RESEARCH_JOB_SOFT_LIMIT_SECONDS = 1500
RESEARCH_JOB_HARD_LIMIT_SECONDS = 1560
POSTING_JOB_SOFT_LIMIT_SECONDS = 540
POSTING_JOB_HARD_LIMIT_SECONDS = 600

#: Bounded pool for the no-broker path (production runs Celery eager; see jobs.py).
RESEARCH_THREAD_WORKERS = 2

#: The sweep re-dispatches a `queued` run older than this (a lost enqueue) and fails a
#: `running` run older than the research hard limit (a dead worker or thread).
STALE_QUEUED_MINUTES = 5
