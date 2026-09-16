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
from typing import Literal, Mapping, Sequence

import numpy as np

from backend.services import occupation_clusters
from backend.services.occupation_retrieval import (
    CorpusUnavailable,
    Match,
    OccupationCorpus,
    get_corpus,
    is_all_other_title,
    soc_prefix_excluded,
    zone_within_ceiling,
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
#: This is design doc §3.2's query **with zero taps**, and F-6 keeps it as the
#: ``q`` the Rocchio update starts from rather than replacing it.  It exists
#: because the F-2 label set grades *the same job at a different grade band* as
#: HARMFUL for ``adjacent`` (a High School Teacher must not be shown Middle
#: School Teachers), and those siblings are exactly what a pure anchor query
#: returns first: measured, they sit at cosine 0.85-0.88 against the anchor,
#: above every genuinely adjacent role.  Rotating toward the skills document
#: demotes them without the hand-written sibling rules the allow-list era would
#: have reached for -- and a user with no judgements yet must still get a full,
#: sensible list, which is the product constraint in design doc §3.2's second
#: bullet.
_ADJACENT_SKILLS_MIX: float = 0.45

# ---------------------------------------------------------------------------
# F-6 -- the `adjacent` feedback loop
# ---------------------------------------------------------------------------
#
# Three constants' worth of algorithm, so the shape is worth stating once here
# rather than three times below.  A user taps verdicts on the cards; those are
# stored as JUDGEMENTS (`path_feedback`, one row per occupation) and turned back
# into arithmetic on every request.  Two of the verdicts are different KINDS of
# signal, which design doc §3.2 is emphatic about and which is the mistake it
# was written to prevent:
#
#   too_similar  a RADIUS.     Exclude everything at least this close to the
#                              user's own occupation.  A hard filter.
#   interesting  a DIRECTION.  Rotate the query toward it.
#   not_for_me   a DIRECTION.  Rotate the query away from it.
#
# Building only the radius is the obvious half-implementation: two occupations
# equidistant from the anchor can lie in opposite directions, and a radius cannot
# tell them apart.  Building only the rotation is the other half: a role that is
# a near-copy of the user's own job scores highly on every similarity term by
# construction, and no amount of rotating demotes it reliably.

#: Rocchio: ``q' = alpha*q + beta*mean(liked) - gamma*mean(disliked)``.
#:
#: Normalised after the sum, so only the ratios matter.  Manning's *Introduction
#: to Information Retrieval* §9.1.1 suggests alpha 1.0, beta 0.75, gamma 0.15;
#: that was the starting point and the F-2 harness was the arbiter.
#:
#: **READ THE SIMULATION BEFORE THE NUMBERS.**  Six ``adjacent`` profiles, one
#: simulated ``interesting`` and one ``too_similar`` each, **both taken from cards
#: the profile was actually shown** -- because a user can only tap what is in
#: front of them, and an earlier sweep that let ``interesting`` land on a labelled
#: primary the scorer had *not* returned reported roughly twice the gain from a
#: tap nobody can make.  Macro nDCG@10 under the realistic simulation, against
#: 0.5278 with zero taps:
#:
#:     beta   0.00     0.15     0.25     0.40     0.60     0.75     1.00
#:     nDCG   0.4767   0.4943   0.5050   0.5416   0.5427   0.5424   0.5431
#:
#: * **beta elbows at 0.40.**  0.25 -> 0.40 is worth +0.037 and everything above
#:   0.40 is worth +0.002 in total, so 0.40 buys the whole effect without letting
#:   one liked occupation weigh as much as the entire base query.
#: * **gamma is flat across its useful range** (at beta 0.40: 0.5523 at 0.10,
#:   0.5506 at 0.15, 0.5497 at 0.20, 0.5425 at 0.35), a spread well inside noise
#:   at n=6, and it degrades steadily above.  So the literature's 0.15 is taken
#:   rather than the sample maximum -- picking 0.10 off a 0.003 difference would
#:   be fitting six profiles.
#:
#: **What one round of feedback is worth, honestly: +0.023 macro nDCG, and two of
#: the six profiles get most of it while four get slightly worse.**  See
#: :func:`_radius_exclusions` for why that is the metric's limit rather than the
#: feature's, and `tests/test_path_scoring.TestSimulatedFeedbackAgainstTheRealCorpus`
#: for the per-profile numbers and the assertions that follow from them.
_ROCCHIO_ALPHA: float = 1.0
_ROCCHIO_BETA: float = 0.40
_ROCCHIO_GAMMA: float = 0.15

#: How far *below* the closest-to-the-anchor rejection the radius is drawn.
#:
#: **The threshold is the MINIMUM cosine among the rejected cards, not the
#: maximum**, and that is the one part of this rule that is easy to get backwards.
#: Higher cosine means more similar to the user's own job.  If they reject a card
#: at 0.85 and another at 0.70, a threshold of 0.85 would still show them
#: everything between 0.70 and 0.85 -- including the 0.70 card they explicitly
#: rejected.  The minimum is the only reading under which every rejected card is
#: actually excluded, and it is the honest reading of the sentence the user is
#: uttering: "anything at least this close to my job is too close".
#:
#: The margin then puts the threshold just under the rejected card rather than
#: exactly on it, so a near-tie with the rejected card goes with it.  0.01 is
#: `_ANCHOR_TIE_MARGIN`'s value for `_ANCHOR_TIE_MARGIN`'s reason: it is about
#: the resolution of these cosines, not about strength of preference -- and the
#: harness agrees that it is not a preference knob.  Measured at the tuned
#: Rocchio constants, macro nDCG over the six `adjacent` profiles:
#:
#:     margin   0.00     0.01     0.03     0.06     0.10
#:     nDCG     0.6116   0.6116   0.6031   0.5550   0.5524
#:
#: Flat to 0.01 and monotonically worse after: a bigger margin is not a stronger
#: signal, it is the radius eating occupations the user said nothing about.
_RADIUS_MARGIN: float = 0.01

#: The radius never removes the last few options.
#:
#: Measured against the real corpus (941 retrievable rows): a rejection at cosine
#: 0.75 excludes 5-27 rows, at 0.60 excludes 9-151, at 0.50 excludes 88-625 --
#: the spread is by anchor, and the trades are the dense end.  So a plausible tap
#: is safe and an implausible one ("too similar" on something at 0.35, which is
#: the corpus median) could empty the result set and turn a tap into an HTTP 500.
#: When the threshold would leave fewer than this many rows, it is raised to the
#: value that admits exactly this many.  A short list is a real answer; an empty
#: one is a failure.
_RADIUS_MIN_SURVIVORS: int = 10

#: How many corpus rows the ``adjacent`` path retrieves, instead of
#: :data:`_RETRIEVE_K`.
#:
#: **Only the radius makes this matter, and only once it is active.**  With zero
#: taps every value from 20 to 120 produces a byte-identical shortlist -- the
#: re-rank's four terms simply do not reorder the tail past rank 30.  Once a
#: "too similar" judgement removes a slice of the corpus, the pool that used to
#: hold thirty re-rankable candidates holds fewer of the ones the user still
#: wants, and widening it pays until it saturates.  Macro nDCG over the six
#: ``adjacent`` profiles after one round of simulated feedback:
#:
#:     k        20       30       40       50       80      120
#:     nDCG   0.5873   0.6045   0.6116   0.6116   0.6116   0.6116
#:
#: 50 is one step past the saturation point, which costs nothing: `retrieve`
#: sorts the whole 1,016-row score vector whatever *k* is, so this bounds how
#: many `Match` objects are built and nothing else.
#:
#: :data:`_RETRIEVE_K` itself is left alone.  It is shared by `stay_in_field` and
#: `fresh_start`, which F-6 does not own and where the measurement above does not
#: apply -- there is no radius on those paths to make the pool too narrow.
#:
#: *F-7: `fresh_start` now reads this too, from its first tap onward, because
#: from that point it IS this path -- same radius, same rotation, same reason for
#: a wider pool.  The name is kept as it is rather than generalised: the
#: measurement above was made on the `adjacent` profiles and renaming it would
#: quietly claim otherwise.  Before any tap `fresh_start` retrieves the whole
#: corpus instead; see `_fresh_start_seed`.*
_RETRIEVE_K_ADJACENT: int = 50


# THERE IS NO MMR HERE, AND THAT IS A MEASUREMENT RATHER THAN AN OMISSION.
#
# BUILD_PLAN F-6's fourth box asks for Maximal Marginal Relevance on the returned
# ten -- "top-K teaches nothing, random teaches nothing" -- on the reasoning that
# an `adjacent` shortlist is a set of PROBES and ten variations on one occupation
# ask the user nothing.  The reasoning is sound.  It was built, measured on the
# F-2 harness, and it does not pay.
#
# THE EXPERIMENT.  Six `adjacent` profiles, two rounds.  Round 1 is the zero-tap
# list; round 2 is the list after one simulated "interesting" and one simulated
# "too similar".  **The taps are held fixed across arms** -- derived once from the
# MMR-off list -- because deriving them per arm lets MMR change both the probe set
# and the feedback, and the first version of this experiment made exactly that
# mistake and produced a flattering answer.  Variants are `keep` (how many ranks
# are taken by score before MMR selects the rest) and lambda.
#
#   arm                  r1 nDCG   r2 nDCG   r1 P@10   mean pairwise cos
#   ------------------   -------   -------   -------   -----------------
#   no MMR                0.5278    0.6074    0.4833         0.648
#   keep=5 lambda=0.80    0.5085    0.5988    0.4833         0.630
#   keep=4 lambda=0.80    0.5097    0.5918    0.4833         0.630
#   keep=4 lambda=0.70    0.5231    0.5826    0.5000         0.612
#   keep=0 lambda=0.70    0.4878    0.5610    0.4667         0.605
#   keep=2 lambda=0.70    0.5393    0.5364    0.5167         0.605
#   keep=0 lambda=0.50    0.3536    0.3860    0.3000         0.560
#
# **No configuration beats "no MMR" on the round that matters.**  The two that
# come close (0.5988, 0.5918) barely diversify -- 0.630 against 0.648, where a
# random corpus pair sits at 0.43 -- and the ones that genuinely spread the list
# cost 0.05-0.17 nDCG.  Diversity and relevance trade smoothly and the exchange
# rate is bad at every point on the curve.  Harm stayed 0.000 throughout, so
# nothing here is a safety argument either way.
#
# WHY, AND WHY THE RADIUS IS THE BETTER ANSWER.  MMR diversifies by guessing which
# clustering the user does not care about.  `too_similar` diversifies by being
# *told*, and it is a hard exclusion rather than a score penalty, so it removes
# the cluster the user actually objects to and leaves every other candidate
# ranked on merit.  Measured, the feedback loop gains +0.080 nDCG in round 2 with
# no MMR at all; MMR's whole claim was that it would make that number bigger, and
# it makes it smaller.
#
# WHAT WOULD CHANGE THIS.  The harness measures "is this a reasonable suggestion",
# not "did this set of ten teach the system where the user wants to go", so a
# real defence of MMR needs an instrument the label set does not contain -- taps
# per useful result, or round-3 quality.  F-7 shares this machinery and may build
# one.  Until then, shipping a feature that loses on every metric available is
# the "weights are opinion" failure F-2 exists to prevent.

# ---------------------------------------------------------------------------
# F-7 -- `fresh_start`: a diverse seed, then F-6's loop
# ---------------------------------------------------------------------------
#
# Someone leaving their field wants to leave the DOMAIN, not their CAPABILITIES.
# So the occupation anchor is dropped, everything else about the person is kept,
# and because there is no anchor to probe around the first page is seeded with a
# maximally diverse spanning set (`occupation_clusters`) which F-6's loop then
# rotates toward whatever they tap.  Design doc §3.3.
#
# THE TRAP, STATED ONCE: DISTANCE FROM THE CURRENT JOB IS NEVER A POSITIVE
# SIGNAL.  "Far from software engineering" includes Logging Worker.  Nothing in
# this intent's path scores distance, ranks by it, or breaks a tie with it --
# the only thing the user's own occupation does here is *exclude* its own minor
# group, which removes candidates and can never promote one.
# `TestDistanceIsNotASignal` pins that.

#: How much of ``fresh_start``'s query is the behavioural profile, the rest
#: being the skills document: ``q0 = (1-mix)*skills + mix*behavioural``.
#:
#: **Design doc §3.3 wants the behavioural profile DOMINANT here**, and F-4's
#: interim 0.30 was the opposite of that -- deliberately, because a
#: behavioural-only query with no transferable-skill floor is how you recommend
#: Logging Worker.  F-7 adds the floor as a hard filter, which is what makes
#: dominance safe against *that* failure: the capabilities constraint no longer
#: has to be expressed as a weight, so the query is free to be about what the
#: person wants.  0.60 is the near edge of "dominant" and is what ships.
#:
#: WHAT THE HARNESS CAN AND CANNOT SAY ABOUT IT
#: --------------------------------------------
#: Only ONE of the four ``fresh_start`` evaluation profiles has a behavioural
#: profile at all (p05; p07, p10 and p16 have no assessment data), so every
#: number below is n=1 -- the "weights are opinion" failure F-2 exists to
#: prevent, in the one place this chunk could not avoid it.
#:
#: * **On the zero-tap page it is inert, and provably so.**  Seeding retrieves
#:   *every* surviving row rather than a top-k, so ``q0`` selects nothing and the
#:   page is ordered by the four-term score -- in which the behavioural profile
#:   already appears, as the ``style`` term.  Measured: mix 0.00, 0.30, 0.50,
#:   0.60, 0.75 and 1.00 all produce macro nDCG@10 0.2420 and the same four
#:   pages, card for card.
#: * **On the TAPPED page it is load-bearing, and F-8 REVERSED WHICH VALUE THE
#:   MEASUREMENT PREFERS.**  Macro nDCG after one round of simulated feedback:
#:
#:       mix                     0.00     0.30     0.60     1.00
#:       F-7 (prose document)   0.3282   0.3282   0.3147   0.3147
#:       F-8 (structured)       0.3409   0.3403   0.3535   0.3147
#:
#:   F-7 shipped 0.60 as the design's value while recording that its own n=1
#:   evidence preferred 0.30.  With the behavioural document composed from the
#:   structured fields instead of from LLM prose (F-8 box 8, see
#:   :func:`_build_behavioral_profile`), **0.60 is now the best measured value
#:   and by the largest margin in the sweep** -- and it was the prose, not the
#:   weight, that had been pulling the other way.  The whole difference is
#:   still p05, which is still n=1; what changed is that the one profile now
#:   agrees with the design instead of contradicting it.
#:
#: WHAT THAT DOES TO F-7's NEGATIVE RESULT
#: ---------------------------------------
#: F-7 recorded that the design's trajectory claim -- feedback recovers more
#: than the diverse seed costs -- "does not hold as stated", because one round
#: reached 0.3147 against the interim's static 0.3322.  At the same constants
#: with the metaphor hazard removed, one round reaches **0.3535, above the
#: interim**.  p05 goes 0.000 -> 0.155 where it was 0.000 -> 0.000: with the
#: fire occupations gone its first page contains a card the label set can
#: judge, so a positive tap exists where before there was none.  The claim
#: holds at n=4.  It is still n=4, and F-2's sample-size rule still forbids
#: reading this as a per-axis result.
#:
#: WHAT HAS NOT CHANGED
#: --------------------
#: The behavioural document is a description of *how* someone works compared
#: against role documents describing *what* the work is, so its cosines sit at
#: 0.34-0.42 against the skills document's 0.52-0.60.  A weaker signal by
#: construction, whatever weight it carries and however it is composed.
_FRESH_START_BEHAVIORAL_MIX: float = 0.60

#: The transferable-skill floor: a candidate whose skills-document cosine is
#: below this is dropped before ranking.
#:
#: "Feasible and different" must never mean "nothing in common".  The floor is
#: the design doc's transferable-skill constraint as a hard filter -- the same
#: move F-3 made for Job Zone, and for the same reason: expressed as a weight it
#: is tradeable against three other terms, and a diverse seed trades it away by
#: construction, because the whole point of the seed is to reach regions the
#: query does not already favour.
#:
#: **This constant is a dial between the spread and the interim, and the metric
#: prefers the interim, so read the second row before the first.**  Measured
#: over the four ``fresh_start`` profiles -- macro nDCG@10 of the zero-tap page,
#: and how many of the eight clusters that page still spans:
#:
#:     floor     0.00     0.25     0.30     0.40     0.45     0.50
#:     nDCG     0.2420   0.2420   0.2404   0.2500   0.3212   0.3330
#:     spread   8/8/8/8  8/8/8/8  8/8/8/7  7/8/8/4  5/5/5/3  5/4/3/3
#:
#: A floor of 0.50 scores 0.3330 -- indistinguishable from the interim scorer's
#: 0.3322 -- and it gets there by leaving so few occupations reachable that the
#: survivor guard hands the seed a pool it cannot spread across.  That is not
#: the floor working, it is the floor switching the chunk off: the interim's own
#: spread is 5/4/2/3.  0.25 is the highest value that costs neither nDCG nor a
#: single cluster, which is the property actually wanted from a filter whose job
#: is to remove nonsense rather than to express a preference.
#:
#: Below ``_COSINE_FLOOR`` on purpose for the same reason: everything
#: interesting lands between 0.30 and 0.85, so a floor inside that band would be
#: a weight wearing a filter's clothes.
_FRESH_START_SKILL_FLOOR: float = 0.25

#: How many candidates the floor may never take the pool below.
#:
#: `_RADIUS_MIN_SURVIVORS`' argument, for the other hard filter that a user's own
#: data can drive: a short list is a real answer and an empty one is an HTTP
#: 500.  A user with two generic skills ("Customer service", "Microsoft Excel")
#: can sit far from every role document in the corpus, and a fixed floor would
#: answer them with nothing.  When fewer than this many rows clear the floor it
#: is lowered to admit exactly this many -- so the filter degrades into "the
#: closest N" rather than into a failure.  `_TOP_N` rather than a new number:
#: the page holds ten, so ten is the fewest that can fill it.
_FRESH_START_FLOOR_MIN_SURVIVORS: int = _TOP_N

#: How far above the user's own Job Zone ``fresh_start`` will look.
#:
#: Feasibility as a HARD filter, design doc §2.2 and §3.3.  A fresh start from
#: zone 2 into a doctoral occupation is not a suggestion, and the zone term in
#: the re-rank cannot express that -- it is one weighted term among four, so a
#: strong coverage score buys a candidate past it.  +1 is the same "one
#: reachable step up" the zone curve is built around; see `_zone_delta_score`
#: for why the live scale is 2-5 and why the bottom step is the wide one.
#:
#: **Measured, it costs nothing, which is what a safety filter should look like
#: when the scorer underneath it is working.**  Macro nDCG@10 over the four
#: ``fresh_start`` profiles is 0.2420 at +1, at +2 and with no ceiling at all --
#: byte-identical pages, because the ranking was already below the ceiling.  It
#: is here for the profile the harness does not contain: 0 (a hard lateral) is
#: the only setting that changes anything, and it costs the administrative
#: assistant 0.300 -> 0.107 by barring the step up she explicitly asked for.
#:
#: **An unknown zone means no ceiling, never a guess.**  Filtering on missing
#: information is how `zone_within_ceiling` describes its own worst case, and a
#: user whose title did not resolve would otherwise be silently held to the
#: `_UNKNOWN_ZONE_FALLBACK` of 2.
_FRESH_START_ZONE_HEADROOM: int = 1

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
# THIS CACHE DOES NOT RETIRE, AND F-8 RE-DERIVED WHY (box 3).
#
# The old note here said it was a stopgap that F-8 would delete.  That was
# wrong on the facts: F-5's deep fit and F-6's re-rank both use it for the
# user's own texts, and tests/test_cache_bounds.py asserts the two tiers share
# one object.  Two caches would double the arithmetic below without halving
# anything.  What F-8 changed is the justification, because the DEMAND changed
# out of all recognition in F-4 and the 32 MB predates that.
#
# WHAT THE DEMAND ACTUALLY IS NOW.  Measured 2026-09-16 over all 20 F-2
# evaluation profiles and five real deep-fit clicks, counting exactly the way
# _evict_to_budget counts -- entry cost 6,553 bytes mean (a 1536-dim float32
# vector plus its key and the OrderedDict's node):
#
#   Tier 1, one cold score_paths, cache cleared between users
#       3-14 entries, 19.6-91.7 KB per distinct user
#       (was 300-700 entries / 15-35 MB before F-4 -- the OOM demand, removed
#       rather than capped)
#   Tier 1, accumulating across 19 distinct users
#       158 entries, 1.04 MB total -- so ~8.3 entries / 55 KB MARGINAL per new
#       user, because users share skill names ("Python", "SQL", "Excel")
#   Tier 2, one deep_fit per click, same user
#       1st click  +97 entries   2nd +68   3rd +25   4th +15   5th +16
#       It converges fast, and the reason is F-4's central finding: O*NET's ~35
#       generic skills and ~41 work activities are the SAME names for every
#       occupation.  Those ~76 names are a fixed core (~0.50 MB) shared by every
#       occupation and every user; only the hot-technology names vary.
#   Tier 2, a DIFFERENT user clicking the SAME five occupations
#       +7 entries on the first, then +0, +0, +0, +0.
#
# WHY 32 MB SURVIVES THAT RE-DERIVATION, ON A BETTER ARGUMENT THAN BEFORE.
#
# The old argument was "one cold run is 15-35 MB, so 32 MB is about one run".
# That argument is gone: one cold run is now 90 KB, and a budget 370x the thing
# it was sized against is not conservative, it is unexamined.  The number stays
# for a different reason, and it is the eviction policy.
#
# _evict_to_budget is FIFO, not LRU -- nothing calls move_to_end on a hit, and
# that is left alone deliberately (see the function).  Under FIFO the budget is
# not "how much can be cached", it is **a residency window**: how long the fixed
# ~76-name Tier-2 core survives a stream of one-off user documents arriving
# behind it.  Evicting that core is the one thing that makes this cache stop
# paying for itself, because it is re-embedded on the next deep fit anyone asks
# for.
#
#   32 MB / 6,553 bytes                  ~5,120 entries of window
#   at ~8.3 marginal entries per user    ~615 distinct users before the core
#                                        is pushed out
#   the core itself                      76 entries, 1.5% of the window
#
# Halving the budget would halve that window and buy 16 MB of a 364 MB
# headroom -- 4% of headroom, against doubling how often the most-shared
# entries in the cache are re-bought from OpenAI.  So: unchanged number,
# replaced reasoning.
#
# The bound still has to exist, and the worst case says why: a worker lives
# ~2,000 requests (gunicorn.conf.py `max_requests`), and 2,000 requests from
# 2,000 distinct users would be ~16,600 entries / 109 MB unbounded.  The budget
# is what turns that into eviction instead of an outage.
#
# WHERE THE HEADROOM FIGURE COMES FROM (measured 2026-09-16, not guessed).
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
    """Compose the behavioural document from the profile's STRUCTURED fields.

    Returns None if no assessment data is present -- callers skip the style term.

    WHY ``archetype_description`` IS NOT IN HERE (F-8 box 8; it used to be first)
    ----------------------------------------------------------------------------
    ``archetype_description`` is 2-3 sentences an LLM writes **per user**
    (``solverah/services/assessment_prompts.py``), and the embedder reads it
    literally.  F-7 measured the consequence on evaluation profile p05, whose
    description contains "you would rather *prevent a fire* than be praised for
    putting one out".  The five corpus rows nearest that document were:

        0.384  First-Line Supervisors of Firefighting and Prevention Workers
        0.369  Firefighters
        0.367  Fire-Prevention and Protection Engineers
        0.356  Forest Fire Inspectors and Prevention Specialists
        0.355  Fire Inspectors and Investigators

    A figure of speech about temperament, retrieved as a career in fire safety.
    That is a **production** input, not a fixture artefact: the sentence is
    generated for a real user from a real assessment, and nothing in the
    pipeline constrains it to literal language.

    Composed from the structured fields instead, the same profile's five
    nearest rows are First-Line Supervisors of Production and Operating
    Workers, Millwrights, Woodworking Machine Setters, Maintenance and Repair
    Workers, and Team Assemblers -- operations and supervision, which is what
    the rest of the profile actually says.  Zero ``33-`` rows.

    **Dropped rather than sanitised, and the choice was between those two.**
    Stripping "figurative sentences" from free prose means a detector with no
    ground truth and no harness to judge it by -- the same unfalsifiable tuning
    this workstream refuses elsewhere (see ``path_deep_fit._EMBED_THRESHOLD``),
    and one that fails open: a metaphor it does not recognise goes straight
    through.  The structured fields need no detector because the product
    already controls their vocabulary.

    WHAT IT COST, MEASURED ON F-2's HARNESS (real corpus, real embedder)
    -------------------------------------------------------------------
    Macro nDCG@10 over the 19 non-degenerate profiles: **0.472 -> 0.473**,
    harmful_rate 0.005 -> 0.005 (the same single p17 label), every other metric
    byte-identical.  Four profiles moved at all and only p01 by more than
    0.003 (0.482 -> 0.501).  On the ``fresh_start`` page after one simulated
    round of taps the macro goes **0.3147 -> 0.3535** at the shipped mix, which
    is what re-opened :data:`_FRESH_START_BEHAVIORAL_MIX` -- see there.

    THE RESIDUAL, RECORDED RATHER THAN CLAIMED FIXED
    ------------------------------------------------
    ``manager_match`` and ``work_style_tags`` are also LLM-written, so this
    narrows the hazard rather than closing it.  They are kept because they are
    the only statement of *how* the person works that survives, because they
    describe management and working conditions rather than occupations -- the
    domain where a metaphor turns into a job title -- and because F-7's finding
    was about ``archetype_description`` specifically, which is the one field
    whose brief is to be evocative.  The deeper point stands: behavioural
    documents cosine at 0.34-0.42 against role documents where skills documents
    reach 0.52-0.60, so this is a weak signal whatever it is composed of.
    """
    parts: list[str] = []
    if profile.archetype:
        parts.append(f"Work archetype: {profile.archetype}.")
    if profile.focus_type:
        parts.append(f"Focus type: {profile.focus_type}.")
    if profile.work_style_tags:
        tags = "; ".join(tag for tag in profile.work_style_tags if tag.strip())
        if tags:
            parts.append(f"Working style: {tags}.")
    if profile.manager_match:
        parts.append(f"Preferred management: {profile.manager_match}")
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


def _anchor_vector(
    anchor: _Anchor, corpus: OccupationCorpus
) -> "np.ndarray | None":
    """The user's own occupation as a corpus vector, or None when there is none.

    None for the three cases :func:`_build_query` enumerates: an All-Other row
    (a truthful identity and a poor query), a code the corpus does not carry, and
    no code at all.  A writable copy, so the Rocchio arithmetic in
    :func:`_rocchio_query` cannot reach the shared read-only matrix.
    """
    if (
        anchor.code is not None
        and not anchor.code_is_all_other
        and corpus.index_of(anchor.code) is not None
    ):
        return corpus.vector_for(anchor.code)
    return None


# ---------------------------------------------------------------------------
# F-6 -- rebuilding the query from stored judgements
# ---------------------------------------------------------------------------


def _judged_codes(feedback: "Mapping[str, str]", verdict: str) -> list[str]:
    """Every code this user gave *verdict* to, in a stable order.

    Sorted rather than dict-ordered: two requests with the same judgements must
    build the same query, and floating-point addition is not associative, so an
    unstable order is a list that reshuffles itself on refresh.
    """
    return sorted(code for code, value in feedback.items() if value == verdict)


def _mean_vector(
    corpus: OccupationCorpus, codes: list[str]
) -> "np.ndarray | None":
    """The mean corpus vector over *codes*, or None if none of them are in it.

    Codes the corpus does not carry are skipped rather than raising: judgements
    outlive corpus builds (see ``path_feedback_repository``'s module docstring),
    and a retired occupation should stop contributing, not break the request.
    """
    vectors = [
        corpus.vector_for(code) for code in codes if corpus.index_of(code) is not None
    ]
    if not vectors:
        return None
    return np.mean(np.asarray(vectors, dtype=np.float32), axis=0)


def _rocchio_query(
    base: "np.ndarray",
    corpus: OccupationCorpus,
    feedback: "Mapping[str, str]",
) -> "np.ndarray":
    """``q' = alpha*base + beta*mean(liked) - gamma*mean(disliked)``, normalised.

    Returns *base* unchanged when there is nothing to rotate toward or away from,
    which is the zero-tap case and has to be the identity: design doc §3.2's
    "valid half-finished" constraint is that no answers still yields the default
    list, not a degraded one.

    ``too_similar`` is **not** the negative term.  It is a radius
    (:func:`_radius_exclusions`), and using it here as well would be a bug
    wearing a plausible face: a card the user called too similar sits *next to
    the anchor* by definition, so subtracting it subtracts the anchor -- and a
    user asking for something less like their current job has not asked to stop
    being a person with their skills.  That is what ``not_for_me`` is for, and
    why the verdict set has three members rather than the two the plan named.
    """
    liked = _mean_vector(corpus, _judged_codes(feedback, "interesting"))
    disliked = _mean_vector(corpus, _judged_codes(feedback, "not_for_me"))
    if liked is None and disliked is None:
        return base

    rotated = _ROCCHIO_ALPHA * base
    if liked is not None:
        rotated = rotated + _ROCCHIO_BETA * liked
    if disliked is not None:
        rotated = rotated - _ROCCHIO_GAMMA * disliked

    norm = float(np.linalg.norm(rotated))
    if norm <= 0.0 or not np.all(np.isfinite(rotated)):
        # Exactly cancelling terms.  Vanishingly unlikely with real embeddings
        # and not worth a failure if it ever happens: the un-rotated query is a
        # worse answer, not a wrong one.
        _log.warning("Rocchio update produced a degenerate query; using the base")
        return base
    return rotated / norm


def _radius_exclusions(
    corpus: OccupationCorpus,
    anchor_vec: "np.ndarray | None",
    feedback: "Mapping[str, str]",
) -> tuple[float | None, list[str]]:
    """``(r_min, codes_at_or_above_it)`` -- the "too similar" radius, as a filter.

    Returns ``(None, [])`` when there is nothing to measure from: no
    ``too_similar`` judgement, or no anchor vector to measure *against*.

    See :data:`_RADIUS_MARGIN` for why the threshold is the minimum of the
    rejected cosines and not the maximum, and :data:`_RADIUS_MIN_SURVIVORS` for
    the floor that stops an implausible tap from emptying the corpus.

    The result is handed to ``corpus.retrieve(exclude_codes=...)`` rather than
    applied to what retrieval returns.  Both are "a hard exclusion on the
    retrieved set", but only the first is independent of ``k``: filtering
    afterwards would mean a user whose radius excluded the whole top 50 got a
    short list, while one whose radius excluded the top 49 got a full one.

    **THE HARNESS SCORES THIS SIGNAL AS A LOSS, AND THAT IS THE METRIC'S LIMIT
    RATHER THAN THE FEATURE'S.**  Measured on the six ``adjacent`` profiles, the
    radius *alone* -- Rocchio switched off -- takes macro nDCG from 0.5278 to
    0.4767.  The reason is structural, not a defect: the card sitting nearest a
    user's own occupation is very often one the label set grades *primary*, and
    the label set encodes "is this a reasonable suggestion for this profile" as a
    fixed truth about the profile.  Honouring "yes, and I do not want it" deletes
    a labelled-good result by construction, and nDCG can only read that as a
    mistake.  There is no version of this metric that can score a user
    overriding it, which is precisely what this feature is for.  So the gates
    here are the ones the labels *can* answer -- harmful_rate stays 0.000 in
    every arm measured, the list stays populated, and nothing the user dismissed
    comes back -- and the rest is a product judgement recorded rather than a
    number defended.
    """
    marked = [
        code
        for code in _judged_codes(feedback, "too_similar")
        if corpus.index_of(code) is not None
    ]
    if not marked or anchor_vec is None:
        return None, []

    sims = corpus.matrix @ np.asarray(anchor_vec, dtype=np.float32)
    r_min = min(float(sims[corpus.index_of(code)]) for code in marked) - _RADIUS_MARGIN

    # The floor.  Measured against what retrieval can actually return, so the
    # 75 residual buckets it filters anyway do not count as survivors.
    eligible = np.array(
        [not is_all_other_title(title) for title in corpus.titles], dtype=bool
    )
    ascending = np.sort(sims[eligible])
    if int((ascending < r_min).sum()) < _RADIUS_MIN_SURVIVORS:
        r_min = float(ascending[min(_RADIUS_MIN_SURVIVORS, len(ascending) - 1)])
        _log.info(
            "radius floor applied: a too-similar judgement would have left "
            "fewer than %d occupations reachable",
            _RADIUS_MIN_SURVIVORS,
        )

    excluded = [corpus.codes[i] for i in np.nonzero(sims >= r_min)[0].tolist()]
    return r_min, excluded


# ---------------------------------------------------------------------------
# F-7 -- `fresh_start`'s hard filters and its diverse seed
# ---------------------------------------------------------------------------


def _fresh_start_soc_exclusions(anchor: _Anchor) -> tuple[str, ...]:
    """The user's own SOC minor group, which ``fresh_start`` retrieval drops.

    ``"15-1252.00" -> "15-1"``.  See :data:`_FRESH_START_EXCLUDE_PREFIX_LEN` for
    why the minor group and not the major one (⚑9).  One definition, because the
    transferable-skill floor's survivor guard has to count the same rows
    retrieval will actually return.
    """
    if not anchor.code or _FRESH_START_EXCLUDE_PREFIX_LEN <= 0:
        return ()
    return (anchor.code[:_FRESH_START_EXCLUDE_PREFIX_LEN],)


def _fresh_start_zone_max(
    profile: UserProfile, anchor: _Anchor, corpus: OccupationCorpus
) -> int | None:
    """The Job Zone ceiling for this user, or None when there is no basis for one.

    ``anchor.zone_resolved`` is the honest test, with one addition this module
    already makes elsewhere: a ``first_job`` user has no occupation to resolve
    and their fallback zone is nevertheless the right answer, because "entry
    level" is a fact about them rather than a guess (``score_paths`` reads the
    same pair for ``zone_is_reliable``).  Everyone else with an unresolved zone
    gets no ceiling at all -- see :data:`_FRESH_START_ZONE_HEADROOM`.

    A corpus with no zone sidecar also gets no ceiling, asked rather than
    caught: ``retrieve`` raises ``CorpusUnavailable`` for ``zone_max`` without
    zones, and turning an optional file into a 503 would make feasibility an
    availability risk.  It is logged at WARNING because a ``fresh_start`` served
    without a ceiling is the one that can suggest a doctorate.
    """
    if not corpus.zones_available:
        _log.warning(
            "no job-zone sidecar beside %s; fresh_start is answering without a "
            "feasibility ceiling.  Run `flask corpus zones`",
            corpus.matrix_path.name,
        )
        return None
    if not (anchor.zone_resolved or profile.career_status == "first_job"):
        return None
    return min(anchor.zone + _FRESH_START_ZONE_HEADROOM, _MAX_JOB_ZONE)


def _skill_floor_exclusions(
    corpus: OccupationCorpus,
    skills_vec: "np.ndarray | None",
    zone_max: int | None = None,
    exclude_prefixes: "Sequence[str]" = (),
) -> list[str]:
    """Codes below the transferable-skill floor -- as an exclusion list.

    Returns ``[]`` when there is no skills document to measure against, which is
    the only honest answer: a user who listed no skills has not told us what
    transfers, and a floor against nothing would be a floor against everything.

    Computed over the whole corpus and handed to ``retrieve(exclude_codes=...)``
    rather than applied to what retrieval returned, for the reason
    :func:`_radius_exclusions` gives: filtering afterwards makes how much the
    filter removes depend on *k*, so one user's page would be short and
    another's full for no reason either of them could see.

    **The survivor guard counts rows that can actually be returned**, which is
    why it needs the other two filters rather than just the residual one.  A
    floor that leaves ten occupations standing corpus-wide leaves none at all if
    a Job Zone ceiling and the user's own minor group take those ten -- measured
    while tuning: at a floor of 0.50 two of the four evaluation profiles came
    back with three and four cards while the corpus-wide count said the floor was
    safe.  See :data:`_FRESH_START_FLOOR_MIN_SURVIVORS`.
    """
    if skills_vec is None:
        return []

    sims = corpus.matrix @ np.asarray(skills_vec, dtype=np.float32)
    eligible = np.array(
        [
            not is_all_other_title(title)
            and zone_within_ceiling(corpus.zones.get(code), zone_max)
            and not soc_prefix_excluded(code, exclude_prefixes)
            for code, title in zip(corpus.codes, corpus.titles)
        ],
        dtype=bool,
    )
    floor = _FRESH_START_SKILL_FLOOR
    reachable = np.sort(sims[eligible])[::-1]
    if len(reachable) and int((reachable >= floor).sum()) < _FRESH_START_FLOOR_MIN_SURVIVORS:
        floor = float(reachable[min(_FRESH_START_FLOOR_MIN_SURVIVORS, len(reachable)) - 1])
        _log.info(
            "transferable-skill floor lowered to %.3f: fewer than %d reachable "
            "occupations cleared %.2f",
            floor,
            _FRESH_START_FLOOR_MIN_SURVIVORS,
            _FRESH_START_SKILL_FLOOR,
        )
    return [corpus.codes[i] for i in np.nonzero(sims < floor)[0].tolist()]


def _fresh_start_seed(
    profile: UserProfile,
    anchor: _Anchor,
    corpus: OccupationCorpus,
    ranked: list[Match],
    skills_vec: "np.ndarray | None",
    behavioral_vec: "np.ndarray | None",
    weights: tuple[float, float, float, float],
    limit: int,
) -> list[Match]:
    """The first page for a ``fresh_start`` with no taps yet: one per region.

    *ranked* is every row that survived the hard filters -- so every candidate
    here is feasible, outside the user's own minor group, and above the
    transferable-skill floor.  They are scored with **the same four terms and
    the same weights the cards are sorted by**, and the best of each cluster is
    taken.  Ranking on the retrieval cosine instead would let the seed pick a
    region's representative on a signal the re-rank then disagrees with; scoring
    first costs two matrix products over ~900 rows (sub-millisecond) and means
    the card standing for a region is the best one there *for this user*.

    Measured on the F-2 ``fresh_start`` set, macro nDCG@10 of the zero-tap page:
    no seed at all 0.3322, this seed 0.2420, and **the same 0.2420 when the seed
    ranks on the retrieval cosine instead** -- with eight regions this large the
    two rankings pick the same representative.  So scoring first is not defended
    as a gain; it is defended as one definition of "best" instead of two, which
    is a property `test_the_seed_ranks_on_the_same_score_the_cards_are_sorted_by`
    can hold and a number at n=4 cannot.

    The 0.090 the seed costs is the WHOLE of what F-7 gives up: the behavioural
    mix, the Job Zone ceiling and the transferable-skill floor were each measured
    at exactly zero (rank every survivor by the full score with no cluster
    constraint and the interim's four numbers come back to four decimal places).
    What it buys is the page spanning 8 of 8 regions for every profile instead of
    5, 4, 2 and 3 -- and the 2 is an administrative assistant being shown eight
    cards of Office and Administrative Support after asking to leave it.

    A corpus the clusterer cannot serve is not a failure: ``get_assignment``
    already falls back to an in-process fit, and if even that raised, the plain
    ranking is a real answer -- a page with less spread, not a broken one.
    """
    signals = _build_signals(
        profile, anchor, corpus, ranked, skills_vec, behavioral_vec
    )
    order = sorted(
        range(len(signals)), key=lambda i: _final_score(signals[i], weights), reverse=True
    )
    codes = [signals[i].match.code for i in order]
    try:
        assignment = occupation_clusters.get_assignment(
            corpus, k=occupation_clusters.CLUSTER_COUNT
        )
    except Exception:  # noqa: BLE001 -- logged; the plain ranking is a real answer
        _log.warning("cluster assignment unavailable; seeding by rank", exc_info=True)
        return [signals[i].match for i in order[:limit]]
    picked = occupation_clusters.diverse_seed(codes, assignment, limit)
    return [signals[order[position]].match for position in picked]


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
        ``q0 = normalise(w_b*behavioural + w_s*skills)`` with the **behavioural
        profile dominant** (:data:`_FRESH_START_BEHAVIORAL_MIX`) -- design doc
        §3.3: with the occupation anchor dropped, what the person wants is the
        only statement of intent left, and their skills are what makes the
        answer feasible rather than aspirational.  No assessment data (three of
        the four evaluation profiles, and most new users) falls back to the
        skills document alone rather than to the anchor, because the anchor is
        the one thing this intent has ruled out.

        **Never** distance-from-current-job: "far from software engineering"
        includes Logging Worker, and the ``_ZONE_DAMPENING_FRESH_START``
        constant this replaces was the patch over exactly that mistake.  The
        hard filters that go with this query are in
        :func:`_retrieve_candidates`, and the diverse seed built on top of it is
        in :func:`_fresh_start_seed`.

    The second element of the tuple is False whenever the query is not built
    from the user's occupation, so ``score_paths`` knows the retrieval cosine is
    not measuring role identity and can zero ``role_w`` instead of
    double-counting the skills document.
    """
    anchor_vec = _anchor_vector(anchor, corpus)

    if profile.move_intent == "fresh_start":
        if skills_vec is None:
            # No skills document.  The behavioural profile alone is a statement
            # of what they want with nothing tethering it to what they can do,
            # which is how you recommend Logging Worker -- but it is still about
            # the person rather than about the job they are leaving, so it wins
            # over the anchor.  The anchor is the last resort, and only because
            # the SOC-minor-group exclusion keeps its results out of the field
            # being left; without that it would be the opposite of this intent.
            if behavioral_vec is not None:
                return behavioral_vec, False
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
    extra_exclusions: "Sequence[str]" = (),
    k: int | None = None,
    zone_max: int | None = None,
) -> list[Match]:
    """One ``matrix @ query``, with the hard filters this tier is allowed.

    The user's own occupation is excluded -- they have that job -- along with
    anything resolution could not tell apart from it.  For ``fresh_start`` the
    user's SOC minor group goes too, which is design doc §3.3's "different
    field, same capabilities" constraint expressed as F-3's named filter rather
    than as an allow-list; see :data:`_FRESH_START_EXCLUDE_PREFIX_LEN` for why
    the minor group and not the major one.

    *zone_max* is F-7's feasibility ceiling and is set for ``fresh_start`` only
    (:func:`_fresh_start_zone_max`).  The other intents keep reading the zone as
    one weighted term, which is right for them: someone staying in their field
    has already demonstrated their own zone, so a step past it is an ambition
    rather than an impossibility.  Someone starting over has demonstrated
    nothing in the new field, and "you could be a surgeon" is not a suggestion.

    **There is no SOC allow-list here and there must never be one again.**  The
    old ``_DEFAULT_ALLOWED_SOC_PREFIXES`` listed eight families and silently
    made every other occupation unreachable; F-2 measured what that cost the
    users inside the excluded families (an electrician: zero of three primary
    labels reachable) and F-1 showed the title-domination failure it was written
    to patch does not occur against role documents.

    *extra_exclusions* is F-6's: the radius from a "too similar" judgement, plus
    the cards the user has already dismissed.  It arrives as an exclusion list
    rather than as a filter over the result, so how much the radius removes does
    not silently depend on *k* -- see :func:`_radius_exclusions`.
    """
    exclude_codes = list(anchor.excluded_codes) + list(extra_exclusions)
    exclude_prefixes = (
        _fresh_start_soc_exclusions(anchor)
        if profile.move_intent == "fresh_start"
        else ()
    )
    return corpus.retrieve(
        query,
        k=k if k is not None else _RETRIEVE_K,
        exclude_codes=exclude_codes,
        exclude_soc_prefixes=exclude_prefixes,
        zone_max=zone_max,
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


def _final_score(
    signals: _Signals, weights: tuple[float, float, float, float]
) -> float:
    """``role_w*role + coverage_w*coverage + zone_w*zone + style_w*style``.

    One definition, because F-7's seed has to rank candidates on exactly the
    number the cards are then sorted by; two copies of this expression would
    drift and the seed would quietly start choosing on a different scorer.
    """
    role_w, coverage_w, zone_w, style_w = weights
    return (
        role_w * signals.role
        + coverage_w * signals.coverage
        + zone_w * signals.zone
        + style_w * signals.style
    )


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
    feedback: "Mapping[str, str] | None" = None,
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
       network.  For ``adjacent`` and ``fresh_start`` this is also where
       *feedback* is applied: the query is rotated by :func:`_rocchio_query` and
       the "too similar" radius becomes an exclusion list
       (:func:`_radius_exclusions`).  ``fresh_start`` adds two hard filters of
       its own -- a Job Zone ceiling and a transferable-skill floor -- and, with
       no taps yet, replaces the top-K with a cluster-spanning seed
       (:func:`_fresh_start_seed`).
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
        feedback:      ``{onet_code: verdict}`` from ``path_feedback`` (F-6,
                       widened to ``fresh_start`` by F-7).  NOT read by
                       ``stay_in_field``, which is answering a question the user
                       asked directly; reordering it by judgements made about a
                       different question would be the scorer overriding the
                       request.  ``None`` or empty is the zero-tap case and must
                       produce a full default list -- design doc §3.2.

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

    # F-6, widened to `fresh_start` by F-7.  ONE implementation, two
    # initialisers: `adjacent` starts from an annulus around the user's own
    # occupation and `fresh_start` from a diverse spanning set, and from the
    # first tap onward they are the same loop -- same Rocchio rotation, same
    # radius, same exclusions.  That is the architectural payoff design doc §3.3
    # names, and it is why nothing below branches on which intent it is.
    #
    # `stay_in_field` is still excluded, for the reason the `feedback` argument
    # documents: it is answering a question the user asked directly, and
    # reordering it by judgements made about a different question would be the
    # scorer overriding the request.
    takes_feedback = user_profile.move_intent in ("adjacent", "fresh_start")
    is_fresh_start = user_profile.move_intent == "fresh_start"
    judgements: "Mapping[str, str]" = feedback or {}
    radius_exclusions: list[str] = []
    if takes_feedback and judgements and query is not None:
        anchor_vec = _anchor_vector(anchor, corpus)
        # No corpus anchor (an All-Other row, an unresolvable title): fall back
        # to the UN-rotated query, which is the user's own profile document and
        # is the same sentence "too similar to what I already do" is about.  A
        # worse referent than their actual occupation, and a far better one than
        # refusing the signal.  Rotating first and measuring against the result
        # would make the radius chase its own tail across taps.
        _, radius_exclusions = _radius_exclusions(
            corpus, anchor_vec if anchor_vec is not None else query, judgements
        )
        query = _rocchio_query(query, corpus, judgements)
        # A card they dismissed does not come back.  An "interesting" one does:
        # tapping it should pull it up and surround it with more of the same, not
        # make it disappear.
        radius_exclusions += [
            code
            for verdict in ("too_similar", "not_for_me")
            for code in _judged_codes(judgements, verdict)
        ]
        # AN EXPLICIT YES OUTRANKS AN INFERRED RADIUS, and this line is not
        # defensive tidying -- without it the feature contradicts itself.  The
        # radius is a statement about a *region*: "anything at least this close to
        # my job is too close".  An occupation the user separately called
        # interesting can sit inside that region, and on the F-2 set it routinely
        # does -- Art Directors is nearer to Graphic Designers than the card that
        # drew the "too similar", so a designer who liked Art Directors and
        # dismissed a different card watched the one they liked vanish.  Measured
        # before this line existed: three of the six `adjacent` profiles lost
        # their `interesting` pick out of the results, nDCG 0.808 -> 0.655 on that
        # designer.  A radius is inferred from one tap about one card; "I like
        # this" is said about the card itself, so it wins.
        liked = set(_judged_codes(judgements, "interesting"))
        radius_exclusions = [code for code in radius_exclusions if code not in liked]

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

    # F-7's two extra hard filters, both `fresh_start`-only and both expressed
    # as F-3's named filters rather than as weights: feasibility (a ceiling on
    # Job Zone) and transferable skill (a floor on the skills cosine).
    zone_max = (
        _fresh_start_zone_max(user_profile, anchor, corpus) if is_fresh_start else None
    )
    if is_fresh_start:
        radius_exclusions = radius_exclusions + _skill_floor_exclusions(
            corpus, skills_vec, zone_max, _fresh_start_soc_exclusions(anchor)
        )

    # The first page of a `fresh_start` with no taps yet is a SPANNING SET, not
    # a top-10: there is no anchor to probe around, so the page's job is to find
    # out which region the person is heading for.  That needs every survivor
    # ranked, not the best thirty of them -- a cluster whose best member sits at
    # rank 200 is still a region the user might pick.  Once a tap exists the
    # query carries a direction and the loop is `adjacent`'s exactly.
    seeding = is_fresh_start and not judgements
    try:
        matches = _retrieve_candidates(
            user_profile,
            anchor,
            corpus,
            query,
            extra_exclusions=radius_exclusions,
            # A wider pool where the radius can take a slice out of it.  See
            # _RETRIEVE_K_ADJACENT.
            k=(
                corpus.count
                if seeding
                else _RETRIEVE_K_ADJACENT if takes_feedback else None
            ),
            zone_max=zone_max,
        )
    except ValueError:
        _log.warning("retrieval rejected the query vector", exc_info=True)
        return []

    zone_is_reliable = (
        anchor.zone_resolved or user_profile.career_status == "first_job"
    )
    role_w, coverage_w, zone_w, style_w = _weights(
        user_profile, zone_is_reliable, behavioral_vec is not None, has_role_identity
    )

    if seeding:
        matches = _fresh_start_seed(
            user_profile,
            anchor,
            corpus,
            matches,
            skills_vec,
            behavioral_vec,
            (role_w, coverage_w, zone_w, style_w),
            _TOP_N,
        )

    signals = _build_signals(
        user_profile, anchor, corpus, matches, skills_vec, behavioral_vec
    )
    overlaps = _overlapping_skills(user_profile, corpus, matches, openai_client)

    scored: list[ScoredPath] = []
    for sig in signals:
        raw = _final_score(sig, (role_w, coverage_w, zone_w, style_w))
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
