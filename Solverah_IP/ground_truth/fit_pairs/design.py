"""design.py -- the blind-rater fit task: fictional people, fictional company reads, pairs.

PRODUCT_DECISIONS.md section 2, "The six-trait match model", "What changes the weights",
step (3): raters who did not set the weights judge fit on person/company pairs, and their
judgements are compared with the model's ranking. Plan: docs/superpowers/plans/
2026-10-13-companylens-six-trait.md, lane C10. Analysis plan: PREREG_FIT_PAIRS_2026-10-13.md.

WHAT THIS MODULE IS
-------------------
The single source of truth for the task. `build_spec()` returns the pair specs that
(a) `build_fit_pages.py` renders for raters and (b) matching-model's ranking code scores
later (the hook: `pair_specs.json`, schema in the prereg). Nothing here ranks a pair:
no weights are read, no z is computed. `gate_check()` restates ONLY the weight-free gate
rules (snap, flat zone, must-have, known/mixed/unknown, 3-known minimum) so the tests can
prove each pair is the case it claims to be, and so the analysis can cross-check the
model's flags before comparing anything with raters.

DESIGN (prereg section 2)
-------------------------
10 blocks. A block is one fictional person and five fictional companies, so the model's
object -- an order over companies FOR ONE PERSON -- exists inside every block, and a rater
who stops after any block leaves complete blocks behind. 50 pairs. Four of them are shown
a second time, unchanged, after a later block (the within-rater consistency check).
B9 and B10 (added 2026-10-14) isolate the three weights 07_SENSITIVITY_RESULTS.md found
move rankings; they sit second and fourth in the order (BLOCKS order = presentation order).

Every company estimate sits ON a band value (0.1 .. 0.9). The words a rater reads map one
to one onto the number the model scores, so nothing is lost or added between the page and
the model. Every company has `headcount: None` and no confounders, so the only thing that
differs between companies in a block is the six trait reads.

THE REPEATS ARE THE SAME QUESTION, BY CONSTRUCTION
--------------------------------------------------
CLAUDE.md records the failure: the priors form's "repeated" vignette changed a NEED into a
TOLERANCE and so asked a different question. Here a repeat is not a copy and not a
rewording: it is a reference (`of_pair`) to an existing pair id. The page renders the
pair's card from the same person and company objects through the same function, and the
tests assert the two rendered cards are byte-identical. The cost of identity is
recognisability (a rater may remember the first answer), so consistency read off the
repeats is an UPPER bound on a rater's reliability -- stated in the prereg.

ASCII only: printed on a cp1252 console.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DESIGN_VERSION = "fp-v1-2026-10-13"
SPEC_SCHEMA = "fit_pairs_spec_v1"

#: The product's six traits, in its fixed order (solverah/domain/trait_preferences.py).
TRAIT_KEYS = ("autonomy", "pace", "collaboration", "feedback", "innovation", "decision")

#: Person lattice (core scores) and company bands (scorer band values).
PERSON_LEVELS = (0.0, 0.25, 0.5, 0.75, 1.0)
COMPANY_BANDS = (0.1, 0.3, 0.5, 0.7, 0.9)

#: The gate constants, restated (NOT imported: this lane never imports app code).
#: trait_preferences.ALIGNED_FLOOR / STEP_SIZE / MAX_STEPS / MAX_MUST_HAVES and
#: company_match_service.MIN_KNOWN_FOR_READ. test_fit_pairs.py pins them against the
#: app's source text so a drift there fails here.
ALIGNED_FLOOR = 0.15
STEP_SIZE = 0.25
MAX_STEPS = 2
MAX_MUST_HAVES = 2
MIN_KNOWN_FOR_READ = 3

#: Display: (label, low pole, high pole, one-line gloss). Poles follow
#: company_match_content.TRAIT_POLES and anchors v3.1, shortened for a table.
TRAITS: dict[str, dict[str, str]] = {
    "autonomy": {"label": "Autonomy", "low": "Directed", "high": "Self-directed",
                 "gloss": "Who decides how the work is done: set direction and sign-offs, or the person themselves."},
    "pace": {"label": "Pace", "low": "Steady", "high": "Fast",
             "gloss": "The tempo of the work: deliberate and sustainable, or urgent with quick turnarounds."},
    "collaboration": {"label": "Collaboration", "low": "Solo", "high": "Collective",
                      "gloss": "How work gets produced: heads-down on your own, or together in a group."},
    "feedback": {"label": "Feedback", "low": "Sparse and gentle", "high": "Frequent and blunt",
                 "gloss": "How performance feedback flows: occasional and softened, or frequent and direct."},
    "innovation": {"label": "Innovation", "low": "Refine what exists", "high": "Invent what does not",
                   "gloss": "Where the work sits: improving existing things, or building new ones."},
    "decision": {"label": "Decision basis", "low": "Judgement-led", "high": "Data-led",
                 "gloss": "What decisions rest on: experience and judgement, or metrics and analysis."},
}

#: How the job can differ from what the person wants, per trait: (less-direction words,
#: more-direction words). "Less" = toward the low pole.
DIRECTION_WORDS: dict[str, tuple[str, str]] = {
    "autonomy": ("More directed", "More self-directed"),
    "pace": ("Steadier", "Faster"),
    "collaboration": ("More solo", "More collective"),
    "feedback": ("Sparser or gentler", "More frequent or blunter"),
    "innovation": ("More refining", "More inventing"),
    "decision": ("More judgement-led", "More data-led"),
}

#: Tolerance steps in words (one step = one notch on the five-step company scale below).
TOLERANCE_WORDS = {0: "not OK, even a little", 1: "a little is OK, a lot is not", 2: "even a lot is OK"}


def person_phrase(trait: str, score: float) -> str:
    t = TRAITS[trait]
    return {
        0.0: "Strongly prefers %s" % t["low"],
        0.25: "Leans %s" % t["low"],
        0.5: "Prefers in between",
        0.75: "Leans %s" % t["high"],
        1.0: "Strongly prefers %s" % t["high"],
    }[score]


def band_phrase(trait: str, band: float) -> str:
    t = TRAITS[trait]
    return {
        0.1: "Clearly %s" % t["low"],
        0.3: "Leans %s" % t["low"],
        0.5: "In between",
        0.7: "Leans %s" % t["high"],
        0.9: "Clearly %s" % t["high"],
    }[band]


# ---------------------------------------------------------------------------
# Evidence: one short paraphrase per (trait, band), three variants. All fictional.
# A known read shows one line; a mixed read shows one line per side. Every known line is
# independent evidence (an employee review or news reporting) -- the production rule
# while Julie's ask 3 is open is that company-only evidence never makes a trait known.
# ---------------------------------------------------------------------------

EVIDENCE: dict[str, dict[float, tuple[tuple[str, str], ...]]] = {
    "autonomy": {
        0.1: (("Employee review", "Most work comes with a set procedure, and changes need sign-off from two levels up."),
              ("Employee review", "Staff say they are told what to work on each week and how to do it."),
              ("News report", "The firm runs on detailed standard procedures, with approval needed for most decisions.")),
        0.3: (("Employee review", "Some room to choose how to do a task, but managers set the priorities."),
              ("Employee review", "Clear processes, with a little flexibility for experienced staff."),
              ("News report", "Teams follow a central plan; local managers can adjust the details.")),
        0.5: (("Employee review", "Priorities come from above, but people mostly decide how to get there."),
              ("Employee review", "Some teams run themselves, others work to a checklist; overall a balance."),
              ("News report", "Staff have a say in how they work, within goals set by leadership.")),
        0.7: (("Employee review", "People are trusted to plan their own work; check-ins are light."),
              ("Employee review", "You are given a goal and mostly left to work out the approach."),
              ("News report", "Staff accounts describe small teams that make their own calls.")),
        0.9: (("Employee review", "Nobody tells you what to do; you set your own priorities and own the outcome."),
              ("Employee review", "Very little oversight; staff decide their own approach from start to finish."),
              ("News report", "Employees describe near-total freedom over what they work on and how.")),
    },
    "pace": {
        0.1: (("Employee review", "Deadlines are generous and the rhythm of the work is calm and predictable."),
              ("Employee review", "Reviewers mention a sustainable pace and rarely working late."),
              ("News report", "The firm is known for long planning cycles and few rush jobs.")),
        0.3: (("Employee review", "Mostly steady, with one busy stretch around year-end."),
              ("Employee review", "Work moves at a measured pace; urgent requests are uncommon."),
              ("News report", "Projects run on quarterly timelines with the occasional crunch.")),
        0.5: (("Employee review", "Busy weeks and quiet weeks in roughly equal measure."),
              ("Employee review", "Some urgency, but deadlines are usually realistic."),
              ("News report", "A moderate pace that picks up before launches.")),
        0.7: (("Employee review", "Things move quickly and priorities shift often."),
              ("Employee review", "Short deadlines are normal; some evenings are needed."),
              ("News report", "The company ships updates every couple of weeks.")),
        0.9: (("Employee review", "Constant urgency; everything is needed yesterday."),
              ("Employee review", "Very fast turnarounds and frequent late nights."),
              ("News report", "Staff describe a high-intensity, always-on environment.")),
    },
    "collaboration": {
        0.1: (("Employee review", "Most work is done alone and heads-down, with few meetings."),
              ("Employee review", "People own their pieces individually and rarely work in groups."),
              ("News report", "Work is organised around single owners rather than teams.")),
        0.3: (("Employee review", "Mostly individual work, with a weekly team meeting."),
              ("Employee review", "You work on your own tasks and pull others in when needed."),
              ("News report", "Staff mainly work independently, with some joint projects.")),
        0.5: (("Employee review", "A mix of solo work and group sessions."),
              ("Employee review", "Some projects are team efforts, others are individual."),
              ("News report", "Work splits between individual tasks and team projects.")),
        0.7: (("Employee review", "Lots of teamwork and regular group problem-solving."),
              ("Employee review", "Most tasks are done in small groups; meetings are frequent."),
              ("News report", "Work is organised in small cross-functional squads.")),
        0.9: (("Employee review", "Almost everything is done together, in the room, as a group."),
              ("Employee review", "Constant collaboration and very little time for solo work."),
              ("News report", "Staff describe a meeting-heavy, all-hands-on-deck culture.")),
    },
    "feedback": {
        0.1: (("Employee review", "Feedback is rare and very softly delivered; mostly the annual review."),
              ("Employee review", "Managers seldom comment on performance, and criticism is gentle."),
              ("News report", "Performance is discussed once a year, in a supportive tone.")),
        0.3: (("Employee review", "Occasional feedback, usually kind and indirect."),
              ("Employee review", "Reviews twice a year; criticism is softened."),
              ("News report", "Feedback is infrequent and diplomatic.")),
        0.5: (("Employee review", "Regular check-ins; feedback is honest but tactful."),
              ("Employee review", "Feedback comes about monthly, direct when it needs to be."),
              ("News report", "A middle-of-the-road approach to performance feedback.")),
        0.7: (("Employee review", "Frequent one-to-ones with direct, specific feedback."),
              ("Employee review", "Managers say what they think, quickly and plainly."),
              ("News report", "Staff describe candid feedback between colleagues as the norm.")),
        0.9: (("Employee review", "Blunt feedback, often in front of others, several times a week."),
              ("Employee review", "Very direct critique all the time; nothing is softened."),
              ("News report", "Staff describe daily, unfiltered critique.")),
    },
    "innovation": {
        0.1: (("Employee review", "The work is about running and improving existing products."),
              ("Employee review", "Little appetite for new ideas; the focus is reliability."),
              ("News report", "The firm grows by refining a long-standing product line.")),
        0.3: (("Employee review", "Mostly improving what exists, with small new features."),
              ("Employee review", "Some new projects, but the core is tuning current work."),
              ("News report", "Investment goes mainly to upgrading existing services.")),
        0.5: (("Employee review", "A balance of new projects and looking after existing ones."),
              ("Employee review", "Roughly half the roadmap is new; half is improvement."),
              ("News report", "Effort is split between new products and the core business.")),
        0.7: (("Employee review", "Many new projects; experiments are encouraged."),
              ("Employee review", "Teams often build things from scratch."),
              ("News report", "The company launches several new products a year.")),
        0.9: (("Employee review", "Almost all the work is building things that never existed."),
              ("Employee review", "Constant experimentation; failed bets are expected."),
              ("News report", "Described as a research-led firm focused on new inventions.")),
    },
    "decision": {
        0.1: (("Employee review", "Decisions rest on the founders' judgement and experience."),
              ("Employee review", "Leaders go with their gut; data is rarely asked for."),
              ("News report", "The company is known for taste-led, intuitive decisions.")),
        0.3: (("Employee review", "Experience matters most, with a few numbers to back it up."),
              ("Employee review", "Managers decide on judgement and check a couple of figures."),
              ("News report", "Decisions lean on the experience of senior staff.")),
        0.5: (("Employee review", "Data and judgement weigh about equally."),
              ("Employee review", "Some decisions use metrics, others rely on experience."),
              ("News report", "A mix of analysis and leadership judgement.")),
        0.7: (("Employee review", "Most decisions need a business case with numbers."),
              ("Employee review", "Teams test ideas and look at the metrics before deciding."),
              ("News report", "Staff accounts describe a data-driven company.")),
        0.9: (("Employee review", "Nothing ships without an experiment and a metrics review."),
              ("Employee review", "Every decision is backed by dashboards and analysis."),
              ("News report", "Decisions are gated on experiments and detailed analytics.")),
    },
}

#: Mixed reads: why the evidence splits, and how each side is labelled on the page.
SPLIT_WHY = {
    "scope": "The split follows where people work: head office versus field sites.",
    "time": "The split follows time: older reviews say one thing, recent ones the other.",
    None: "We could not find a reason for the split.",
}
SCOPE_SIDE_LABELS = ("At head office", "At field sites")      # (low side, high side)
NONE_SIDE_LABELS = ("Some sources", "Other sources")

# ---------------------------------------------------------------------------
# People. Scores are the person lattice; tolerance is (under_steps, over_steps) per trait
# exactly as trait_preferences.TraitPreference stores it; at most two must-haves.
# Names are invented, chosen not to collide with 05_USER_JOURNEYS.md (Maya, Daniel, Priya).
# ---------------------------------------------------------------------------

def _tol(**kw: tuple[int, int]) -> dict[str, dict[str, int]]:
    out = {}
    for k in TRAIT_KEYS:
        u, o = kw.get(k, (1, 1))
        out[k] = {"under_steps": u, "over_steps": o}
    return out


PERSONS: list[dict[str, Any]] = [
    {"person_id": "P1", "name": "Rosa",
     "scores": {"autonomy": 1.0, "pace": 0.5, "collaboration": 0.25, "feedback": 0.75,
                "innovation": 0.75, "decision": 0.5},
     "tolerance": _tol(autonomy=(0, 0), feedback=(1, 0), decision=(2, 2)),
     "must_haves": ["autonomy"]},
    {"person_id": "P2", "name": "Tom",
     "scores": {"autonomy": 0.5, "pace": 0.0, "collaboration": 0.75, "feedback": 0.25,
                "innovation": 0.25, "decision": 0.75},
     "tolerance": _tol(pace=(0, 0), feedback=(1, 0)),
     "must_haves": ["pace", "feedback"]},
    {"person_id": "P3", "name": "Lena",
     "scores": {"autonomy": 0.75, "pace": 0.75, "collaboration": 0.5, "feedback": 0.5,
                "innovation": 0.5, "decision": 0.25},
     "tolerance": _tol(**{k: (0, 0) for k in TRAIT_KEYS}),
     "must_haves": []},
    {"person_id": "P4", "name": "Marcus",
     "scores": {"autonomy": 0.5, "pace": 0.5, "collaboration": 0.75, "feedback": 0.25,
                "innovation": 0.5, "decision": 0.5},
     "tolerance": _tol(**{k: (0, 0) for k in TRAIT_KEYS}),
     "must_haves": []},
    {"person_id": "P5", "name": "Ade",
     "scores": {"autonomy": 0.75, "pace": 0.25, "collaboration": 0.25, "feedback": 0.25,
                "innovation": 0.5, "decision": 0.75},
     "tolerance": _tol(**{k: (0, 0) for k in TRAIT_KEYS}),
     "must_haves": ["innovation"]},
    {"person_id": "P6", "name": "Jun",
     "scores": {"autonomy": 0.25, "pace": 0.5, "collaboration": 0.5, "feedback": 0.75,
                "innovation": 0.5, "decision": 0.25},
     "tolerance": _tol(pace=(0, 0), innovation=(0, 0), feedback=(0, 1)),
     "must_haves": ["feedback", "collaboration"]},
    {"person_id": "P7", "name": "Sam",
     "scores": {"autonomy": 0.5, "pace": 0.5, "collaboration": 0.5, "feedback": 0.5,
                "innovation": 0.75, "decision": 0.5},
     "tolerance": _tol(autonomy=(0, 2), pace=(2, 0)),
     "must_haves": ["innovation"]},
    {"person_id": "P8", "name": "Nadia",
     "scores": {"autonomy": 0.25, "pace": 0.75, "collaboration": 0.75, "feedback": 0.5,
                "innovation": 0.25, "decision": 0.75},
     "tolerance": _tol(**{k: ((1, 1) if k == "innovation" else (0, 0)) for k in TRAIT_KEYS}),
     "must_haves": ["collaboration", "decision"]},
    # P9/P10 added 2026-10-14 for 07_SENSITIVITY_RESULTS.md: pace and innovation sit at the
    # midpoint with zero tolerance, so a 2-notch gap is possible in BOTH directions and every
    # single gap in their blocks is the same distance (0.4) outside the same zone (0.15).
    {"person_id": "P9", "name": "Ines",
     "scores": {"autonomy": 0.5, "pace": 0.5, "collaboration": 0.75, "feedback": 0.25,
                "innovation": 0.5, "decision": 0.75},
     "tolerance": _tol(autonomy=(0, 0), pace=(0, 0), innovation=(0, 0)),
     "must_haves": []},
    {"person_id": "P10", "name": "Kofi",
     "scores": {"autonomy": 0.75, "pace": 0.5, "collaboration": 0.25, "feedback": 0.75,
                "innovation": 0.5, "decision": 0.25},
     "tolerance": _tol(autonomy=(0, 0), pace=(0, 0), innovation=(0, 0)),
     "must_haves": ["feedback"]},
]


def snap(score: float) -> float:
    """match_core.closest_achievable for one value: the nearest company band."""
    return min(COMPANY_BANDS, key=lambda b: (abs(score - b), b))


# ---------------------------------------------------------------------------
# Companies. Each company is written as DEVIATIONS from the block person's own bands, so
# the aligned trait is the default and every case reads as what it changes.
#   ("k", band)                  known at that band
#   ("m", low, high, why[, recent_side])   mixed; why in {"scope", "time", None}
#   ("u",)                       unknown
# ---------------------------------------------------------------------------

#: (block, person, [(case, {trait: deviation})...]). Block order IS the presentation
#: order for every rater (fixed, like JULIE_ORDER: overlap between raters is a prefix).
BLOCKS: list[tuple[str, str, list[tuple[str, dict[str, tuple]]]]] = [
    ("B1", "P1", [
        ("aligned", {}),
        ("must_have_break", {"autonomy": ("k", 0.5)}),
        ("multi_big", {"pace": ("k", 0.9), "collaboration": ("k", 0.9), "innovation": ("k", 0.1)}),
        ("unknown_heavy", {"collaboration": ("u",), "innovation": ("u",), "decision": ("u",)}),
        ("inside_tolerance", {"decision": ("k", 0.1), "innovation": ("k", 0.5)}),
    ]),
    # B9/B10 (2026-10-14): one gap each, all the same size, isolating the three weights the
    # sensitivity test (07) found move rankings: pace size, innovation size, innovation
    # direction. Control = the same gap on autonomy, the smallest penalty in priors.yaml.
    # Placed second and fourth so a rater who stops at the 4-block minimum has both.
    ("B9", "P9", [
        ("aligned", {}),
        ("single_pace_faster", {"pace": ("k", 0.9)}),
        ("single_innovation_more", {"innovation": ("k", 0.9)}),
        ("single_innovation_less", {"innovation": ("k", 0.1)}),
        ("single_autonomy_control", {"autonomy": ("k", 0.1)}),
    ]),
    ("B2", "P2", [
        ("aligned", {}),
        ("mixed_must_have", {"pace": ("m", 0.1, 0.7, "scope")}),
        ("must_have_break_small", {"feedback": ("k", 0.5)}),
        ("inside_tolerance", {"autonomy": ("k", 0.7), "collaboration": ("k", 0.9),
                              "innovation": ("k", 0.5), "decision": ("k", 0.9)}),
        ("single_big", {"collaboration": ("k", 0.1)}),
    ]),
    ("B10", "P10", [
        ("aligned", {}),
        ("single_pace_steadier", {"pace": ("k", 0.1)}),
        ("single_innovation_less", {"innovation": ("k", 0.1)}),
        ("single_innovation_more", {"innovation": ("k", 0.9)}),
        ("single_autonomy_control", {"autonomy": ("k", 0.3)}),
    ]),
    ("B3", "P3", [
        ("aligned", {}),
        ("many_small", {"autonomy": ("k", 0.5), "pace": ("k", 0.5), "collaboration": ("k", 0.7),
                        "feedback": ("k", 0.3), "innovation": ("k", 0.7), "decision": ("k", 0.5)}),
        ("single_big", {"pace": ("k", 0.1)}),
        ("two_medium", {"autonomy": ("k", 0.3), "feedback": ("k", 0.9)}),
        ("thin_evidence", {"collaboration": ("u",), "feedback": ("u",), "innovation": ("u",),
                           "decision": ("u",)}),
    ]),
    ("B4", "P4", [
        ("aligned", {}),
        ("compound_1", {"autonomy": ("k", 0.1), "pace": ("k", 0.9)}),
        ("compound_1_reversed", {"autonomy": ("k", 0.9), "pace": ("k", 0.1)}),
        ("two_gap_control", {"decision": ("k", 0.1), "innovation": ("k", 0.9)}),
        ("single_pace", {"pace": ("k", 0.9)}),
    ]),
    ("B5", "P5", [
        ("aligned", {}),
        ("compound_2", {"pace": ("k", 0.7), "feedback": ("k", 0.7)}),
        ("compound_4", {"collaboration": ("k", 0.7), "feedback": ("k", 0.7)}),
        ("two_gap_control", {"autonomy": ("k", 0.3), "decision": ("k", 0.3)}),
        ("unknown_must_have", {"innovation": ("u",)}),
    ]),
    ("B6", "P6", [
        ("aligned", {}),
        ("compound_3", {"pace": ("k", 0.1), "innovation": ("k", 0.1)}),
        ("compound_3_reversed", {"pace": ("k", 0.9), "innovation": ("k", 0.9)}),
        ("mixed_must_have_time", {"feedback": ("m", 0.3, 0.7, "time", "high")}),
        ("mixed_wide", {"decision": ("m", 0.1, 0.9, None)}),
    ]),
    ("B7", "P7", [
        ("aligned", {}),
        ("tolerated_direction", {"autonomy": ("k", 0.9), "pace": ("k", 0.1)}),
        ("untolerated_direction", {"autonomy": ("k", 0.1), "pace": ("k", 0.9)}),
        ("unknown_heavy_must_have", {"autonomy": ("u",), "collaboration": ("u",), "innovation": ("u",)}),
        ("mixed_inside_tolerance", {"innovation": ("m", 0.5, 0.9, None)}),
    ]),
    ("B8", "P8", [
        ("aligned", {}),
        ("must_have_break", {"collaboration": ("k", 0.3)}),
        ("multi_big", {"autonomy": ("k", 0.9), "pace": ("k", 0.1), "feedback": ("k", 0.9)}),
        ("many_small", {"autonomy": ("k", 0.5), "pace": ("k", 0.9), "feedback": ("k", 0.7),
                        "innovation": ("k", 0.1)}),
        ("single_big", {"autonomy": ("k", 0.9)}),
    ]),
]

#: Repeats: (repeat_id, of_pair, shown at the END of this block). Each original sits two
#: blocks before its repeat, so a rater who stops after block k has every repeat whose
#: block <= k. Chosen from mid-range cases where a rater's answer is a real judgement
#: (an "aligned" pair would be answered the same from memory and tell us nothing).
REPEATS: list[tuple[str, str, str]] = [
    ("R1", "B1-C4", "B2"),   # unknown_heavy      (B1 is part 1, B2 part 3)
    ("R2", "B2-C2", "B3"),   # mixed_must_have    (B2 is part 3, B3 part 5)
    ("R3", "B3-C2", "B5"),   # many_small
    ("R4", "B4-C2", "B6"),   # compound_1
]

#: Pre-registered contrasts (prereg section 4). `rule` states what the model's WEIGHT-FREE
#: rules imply; "tie" means the model's z is equal by construction (no penalty inside the
#: zone, none for an unknown trait), "last" means the gate layer sorts `b` last. "weights"
#: means the direction depends on priors.yaml and is read from matching-model's output,
#: never asserted here.
CONTRASTS: list[dict[str, Any]] = [
    {"contrast_id": "K1", "name": "Known must-have break sorts below several big gaps",
     "a": ["B1-C3", "B8-C3"], "b": ["B1-C2", "B8-C2"], "rule": "b_last",
     "default_at_stake": "must-have break sorts last (lexicographic gate)"},
    {"contrast_id": "K2", "name": "A one-notch must-have break sorts below a single big gap and a split must-have",
     "a": ["B2-C5", "B2-C2"], "b": ["B2-C3", "B2-C3"], "rule": "b_last",
     "default_at_stake": "must-have break sorts last, however small the break"},
    {"contrast_id": "K3", "name": "Unknown traits cost nothing",
     "a": ["B1-C1", "B7-C1", "B5-C1"], "b": ["B1-C4", "B7-C4", "B5-C5"], "rule": "tie",
     "default_at_stake": "unknown = no gap, no penalty"},
    {"contrast_id": "K4", "name": "A gap inside stated tolerance costs nothing",
     "a": ["B1-C1", "B2-C1", "B7-C1"], "b": ["B1-C5", "B2-C4", "B7-C2"], "rule": "tie",
     "default_at_stake": "flat inside tolerance (the hinge)"},
    {"contrast_id": "K5", "name": "Many small gaps versus one big gap",
     "a": ["B3-C2", "B8-C4"], "b": ["B3-C3", "B8-C5"], "rule": "weights",
     "default_at_stake": "linear excess per trait, summed (no 'nothing quite fits' term)"},
    {"contrast_id": "K6", "name": "Same gap sizes, tolerated versus untolerated direction",
     "a": ["B7-C2"], "b": ["B7-C3"], "rule": "weights",
     "default_at_stake": "asymmetric tolerance"},
    {"contrast_id": "K7", "name": "Split evidence with both ends inside tolerance costs nothing",
     "a": ["B7-C1"], "b": ["B7-C5"], "rule": "tie",
     "default_at_stake": "mixed is scored at its worst end; no penalty for disagreement itself"},
    {"contrast_id": "K8", "name": "Compounding pairs (06 items 1-4) versus same-size controls",
     "a": ["B4-C3", "B4-C4", "B5-C4", "B5-C4", "B6-C3"],
     "b": ["B4-C2", "B4-C2", "B5-C2", "B5-C3", "B6-C2"], "rule": "weights",
     "default_at_stake": "gaps add; v1 ignores compounding (06)"},
    # K9-K11 (2026-10-14): the comparisons 07_SENSITIVITY_RESULTS.md says would change the
    # defaults. Every gap below is 2 notches outside a zero tolerance.
    {"contrast_id": "K9", "name": "A pace gap versus the same gap on autonomy",
     "a": ["B9-C5", "B10-C5"], "b": ["B9-C2", "B10-C2"], "rule": "weights",
     "default_at_stake": "pace.mag, the largest penalty (07: needs evidence before launch)"},
    {"contrast_id": "K10", "name": "An innovation gap (either direction) versus the same gap on autonomy",
     "a": ["B9-C5", "B10-C5", "B9-C5", "B10-C5"], "b": ["B9-C3", "B10-C3", "B9-C4", "B10-C4"],
     "rule": "weights",
     "default_at_stake": "innovation.mag (07: needs evidence before launch)"},
    {"contrast_id": "K11", "name": "Job more inventing than wanted versus job more refining than wanted",
     "a": ["B9-C3", "B10-C4"], "b": ["B9-C4", "B10-C3"], "rule": "weights",
     "default_at_stake": "innovation.dir = 0, elicited 5 v 5 (07: needs evidence before launch); "
                         "a is always the more-inventing side, so a tie is broken the same way in both"},
]

#: Not ranked by the model at all (fewer than 3 known traits). Analysed apart: do raters
#: abstain, or rate it like a company with nothing against it?
UNRANKED_EXPECTED = ("B3-C5",)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _trait_record(dev: tuple | None, aligned_band: float) -> dict[str, Any]:
    if dev is None:
        return {"status": "known", "estimate": aligned_band}
    kind = dev[0]
    if kind == "k":
        return {"status": "known", "estimate": dev[1]}
    if kind == "u":
        return {"status": "unknown"}
    if kind == "m":
        rec = {"status": "mixed", "low_end": dev[1], "high_end": dev[2],
               "split_explained_by": dev[3]}
        if dev[3] == "time":
            rec["recent_side"] = dev[4]
        return rec
    raise ValueError("unknown deviation kind %r" % (kind,))


def _evidence_for(company_index: int, trait_index: int, rec: dict[str, Any], trait: str) -> list[dict[str, str]]:
    """Deterministic pick from the bank: the same company always gets the same lines."""
    v = (company_index + 2 * trait_index) % 3
    if rec["status"] == "known":
        src, text = EVIDENCE[trait][rec["estimate"]][v]
        return [{"side": "only", "label": src, "text": text}]
    if rec["status"] == "mixed":
        why = rec["split_explained_by"]
        lo_src, lo_text = EVIDENCE[trait][rec["low_end"]][v]
        hi_src, hi_text = EVIDENCE[trait][rec["high_end"]][(v + 1) % 3]
        if why == "scope":
            lo_lab, hi_lab = SCOPE_SIDE_LABELS
        elif why == "time":
            recent_high = rec.get("recent_side") == "high"
            lo_lab = "Older reviews" if recent_high else "Recent reviews"
            hi_lab = "Recent reviews" if recent_high else "Older reviews"
        else:
            lo_lab, hi_lab = NONE_SIDE_LABELS
        return [{"side": "low", "label": "%s (%s)" % (lo_lab, lo_src.lower()), "text": lo_text},
                {"side": "high", "label": "%s (%s)" % (hi_lab, hi_src.lower()), "text": hi_text}]
    return []


def build_spec() -> dict[str, Any]:
    persons = {p["person_id"]: p for p in PERSONS}
    companies, pairs, blocks = [], [], []
    ci = 0
    for block_id, person_id, cases in BLOCKS:
        person = persons[person_id]
        pair_ids = []
        for n, (case, devs) in enumerate(cases, start=1):
            unknown = set(devs) - set(TRAIT_KEYS)
            if unknown:
                raise ValueError("%s case %s: unknown traits %s" % (block_id, case, sorted(unknown)))
            cid = "%s-C%d" % (block_id, n)
            traits = {}
            for ti, k in enumerate(TRAIT_KEYS):
                rec = _trait_record(devs.get(k), snap(person["scores"][k]))
                rec["evidence"] = _evidence_for(ci, ti, rec, k)
                traits[k] = rec
            companies.append({"company_id": cid, "headcount": None, "confounders": {},
                              "traits": traits})
            pair = {"pair_id": cid, "block": block_id, "person_id": person_id,
                    "company_id": cid, "case": case}
            pair["design_check"] = gate_check(person, traits)
            pairs.append(pair)
            pair_ids.append(cid)
            ci += 1
        blocks.append({"block_id": block_id, "person_id": person_id, "pair_ids": pair_ids})
    return {
        "schema": SPEC_SCHEMA,
        "design_version": DESIGN_VERSION,
        "generated_by": "Solverah_IP/ground_truth/fit_pairs/design.py",
        "trait_keys": list(TRAIT_KEYS),
        "conventions": {
            "person_scores": "core dimension score on the person lattice 0, 0.25, 0.5, 0.75, 1",
            "tolerance": "under_steps / over_steps as trait_preferences.TraitPreference; "
                         "under = company offers LESS than preferred (match_core gap > 0)",
            "company_estimates": "scorer band values 0.1..0.9; mixed records carry low_end/high_end",
            "headcount_and_confounders": "None / empty for every company: constant within a block",
            "design_check": "weight-free gate restatement from design.py; matching-model must "
                            "NOT read it; the analysis cross-checks the model's flags against it",
        },
        "persons": PERSONS,
        "companies": companies,
        "blocks": blocks,
        "pairs": pairs,
        "repeats": [{"repeat_id": r, "of_pair": p, "shown_after_block": b} for r, p, b in REPEATS],
        "contrasts": CONTRASTS,
    }


def gate_check(person: dict[str, Any], traits: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The weight-free part of company_match_service, restated: per trait, inside or outside
    the flat zone; must-have break / risk / investigate; coverage; rankable."""
    outside, inside_nonzero, flags = [], [], []
    known = mixed = unknown = 0
    must = set(person["must_haves"])
    for k in TRAIT_KEYS:
        rec = traits[k]
        tol = person["tolerance"][k]
        zone = (max(ALIGNED_FLOOR, tol["under_steps"] * STEP_SIZE),
                max(ALIGNED_FLOOR, tol["over_steps"] * STEP_SIZE))
        ps = snap(person["scores"][k])

        def within(est: float) -> bool:
            gap = ps - est                     # match_core convention: person - env
            side = zone[0] if gap > 0 else zone[1]
            return abs(gap) <= side + 1e-12

        if rec["status"] == "known":
            known += 1
            ok = within(rec["estimate"])
            if not ok:
                outside.append(k)
            elif abs(ps - rec["estimate"]) > 1e-9:
                inside_nonzero.append(k)
            if k in must and not ok:
                flags.append(("must_have_break", k))
        elif rec["status"] == "mixed":
            mixed += 1
            lo_ok, hi_ok = within(rec["low_end"]), within(rec["high_end"])
            if not (lo_ok and hi_ok):
                outside.append(k)
            if k in must and not (lo_ok and hi_ok):
                flags.append(("risk", k))
        else:
            unknown += 1
            if k in must:
                flags.append(("investigate", k))
    return {
        "known": known, "mixed": mixed, "unknown": unknown,
        "rankable": known >= MIN_KNOWN_FOR_READ,
        "must_have_break": any(f == "must_have_break" for f, _ in flags),
        "risk_flag": any(f == "risk" for f, _ in flags),
        "investigate": any(f == "investigate" for f, _ in flags),
        "outside_tolerance": outside,
        "gap_inside_tolerance": inside_nonzero,
    }


def spec_bytes(spec: dict[str, Any]) -> bytes:
    """The canonical serialisation: what is written to disk and what the hash covers."""
    return (json.dumps(spec, indent=2, sort_keys=False, ensure_ascii=True) + "\n").encode("ascii")


def spec_sha256(spec: dict[str, Any]) -> str:
    return hashlib.sha256(spec_bytes(spec)).hexdigest()


def write_spec(path: Path) -> str:
    spec = build_spec()
    path.write_bytes(spec_bytes(spec))
    return spec_sha256(spec)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "pair_specs.json"
    sha = write_spec(out)
    spec = build_spec()
    print("wrote %s  pairs=%d repeats=%d sha256=%s" % (out.name, len(spec["pairs"]),
                                                        len(spec["repeats"]), sha[:12]))
