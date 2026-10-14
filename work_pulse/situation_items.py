"""Environment-side instrument: what the user's ROLE offers (BUILD_PLAN A-1).

The other half of the Situation Report. Core asks twenty-four questions about
the person; this asks twelve about the job, plus four context items, and the
report is the gap between the two. `work_pulse/situation.py` (A-3) turns the
answers here into 0–1 dimension scores and diffs them against the sealed
person-side snapshot; `work_pulse/situation_content.py` (A-6) holds the words
that come back. This file holds only the questions.

Where the wording comes from
----------------------------
Every dimension item is recast from the live rater rubric,
`Solverah_IP/ground_truth/rater_app/anchors_v3_PROPOSED.json` — the same six
dimensions, the same five band values (0.1 / 0.3 / 0.5 / 0.7 / 0.9), the same
band texts, turned from third-person evidence prose ("postings stress *follow
established processes*") into second-person description ("your work is
assigned and specified for you"). The rubric's `keep_distinct` guardrails are
binding on the recast wording, not just on raters: they exist because two
blind raters bled these dimensions into each other, and an item that
reintroduces the bleed reintroduces it for every user at once. Where a rubric
*band text* itself contains a phrase its own `keep_distinct` forbids, the
guardrail wins — see SITUATION_ITEMS_BIAS_REVIEW.md, Finding 4.

`Solverah_Company_Rating_Rubric_v2.docx`, cited by BUILD_PLAN §3.1, does not
exist in the repo. The JSON above is the rubric artifact. `anchors.json` is
the frozen v1 and is comparison-only.

Item design rules (see SITUATION_ITEMS_BIAS_REVIEW.md)
-----------------------------------------------------
  * Every item describes what the ROLE offers, not what the user is, wants or
    deserves. Second person, present tense, with a past-tense variant carried
    alongside for a user who is not currently employed.
  * Both poles are legitimate. "Directed" is not worse than "self-directed",
    "steady" not worse than "fast" — the rubric's own first gate, applied to
    the user-facing text. An option that reads as *the good job* is a defect.
  * `experienced` is the single evaluative item in the whole instrument, on
    purpose: it is the model's outcome node. It is asked last so its verdict
    cannot colour the twelve descriptive items.
  * **Anchor-order balance.** Within every dimension exactly one item is
    presented low-pole-first and one high-pole-first, so a respondent who
    straight-lines a position lands every dimension on exactly 0.5 rather than
    at an anchor. This is `manager_profile.py`'s positional-key balance,
    carried over to a five-point anchored scale.

Not ground-truth-sensitive
--------------------------
Deliberately plain, in contrast with core. The user is describing a job, not
themselves, so none of the D-01 token-map machinery
(`assessment_form.py`'s per-sitting key material, the presentation shuffle,
re-derivation from stored tokens) applies here: no shuffle requirement, no
token map, plain string item ids straight into `EnvironmentReport.raw_answers`
(BUILD_PLAN §3.1). The gaming pressure core is built against — a self-profiling
user answering as the person they want matched — has no analogue on this side:
misdescribing your own job only corrupts your own report.

Pure: no Flask, no DB, no clock, no randomness, no I/O of any kind. Importable
by anything.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: The six model dimensions, in form order. Identical to the rubric's
#: `dimensions[*].key`, to `model.ENV_DIMENSIONS`, to
#: `work_pulse.situation.DIMENSIONS` and to the `dims` list
#: `causal_graph/v1_model/assemble_training_data.py` assembles training rows
#: over. A tripwire test asserts each of those agreements rather than trusting
#: the comment.
DIMENSIONS: tuple[str, ...] = (
    "autonomy",
    "pace",
    "collaboration",
    "feedback",
    "innovation",
    "decision",
)

#: `EnvironmentReport.version` — which item set produced a stored answer blob.
#: Same role as `assessment_response.form_version`, same naming shape.
#:
#: Bumped from `env-v1-2026-09-10` when `industry` joined the context items
#: (PRODUCT_DECISIONS.md §2, 2026-10-01). A NULL `industry` on a v1 row means
#: "never asked"; on a v2 row it means "not sure / prefer not to say". This
#: stamp is the only thing that tells the two apart.
FORM_VERSION = "env-v2-2026-10-01"

#: Option pole name -> 0–1 score. Five bands, not two: the rubric anchors on
#: five and the person-side scale is continuous in [0, 1], so collapsing to a
#: forced choice would throw away resolution the rubric already paid for. The
#: values ARE the rubric's `band_values`, unscaled and unshifted, so an
#: environment score and a rater's company score mean the same thing on the
#: same axis — which is the whole premise of E-4 assembling them into one
#: training row.
POLE_VALUES: dict[str, float] = {
    "low": 0.1,
    "leaning_low": 0.3,
    "mixed": 0.5,
    "leaning_high": 0.7,
    "high": 0.9,
}

#: Pole names ordered low -> high. `ASCENDING` items list their options in
#: this order, `DESCENDING` items in its reverse.
POLES_LOW_TO_HIGH: tuple[str, ...] = (
    "low",
    "leaning_low",
    "mixed",
    "leaning_high",
    "high",
)

ASCENDING = "ascending"
DESCENDING = "descending"

#: Positional option keys. Fixed length five for every dimension item — an
#: item with a different arity would silently weight itself differently under
#: A-3's mean.
OPTION_KEYS: tuple[str, ...] = ("a", "b", "c", "d", "e")

#: `career_status` -> whether the items render in past tense.
#: `career_status`'s vocabulary is `solverah.domain.profile.CAREER_STATUSES`
#: and `model.CAREER_STATUSES`; it is duplicated rather than imported because
#: both of those pull in Flask.
TENSE_BY_CAREER_STATUS: dict[str, bool] = {
    "employed": False,
    "between_jobs": True,
    "first_job": True,
}

Tense = Literal["present", "past"]


class EnvironmentOption(TypedDict):
    key: str        # positional, "a".."e"
    pole: str       # POLE_VALUES key — the score, never the position
    text: str       # employed / present tense
    text_past: str  # between_jobs / first_job


class EnvironmentItem(TypedDict):
    item_id: str
    dimension: str
    prompt: str
    prompt_past: str
    anchor_order: str  # ASCENDING | DESCENDING — see the balance rule above
    options: list[EnvironmentOption]


class ContextOption(TypedDict):
    # 1..5 stored raw for an ordinal item; a level key from INDUSTRY_LEVELS for
    # the one categorical item. This IS the answer. None == "not sure" (comp
    # and industry only).
    value: int | str | None
    text: str
    text_past: str


class ContextItem(TypedDict):
    item_id: str
    prompt: str
    prompt_past: str
    options: list[ContextOption]


# ---------------------------------------------------------------------------
# The twelve dimension items
# ---------------------------------------------------------------------------
# Two per dimension. Two rather than one because a single item makes a
# dimension score a single click, and two rather than four because the whole
# instrument is meant to be answerable in one sitting after a twenty-four-item
# core (BUILD_PLAN §3.1: "~10–12 items"). The two items of a dimension take
# different facets of it, both named in that dimension's rubric `measures`
# line, so they are not paraphrases of each other.
ENVIRONMENT_ITEMS: list[EnvironmentItem] = [
    # -- autonomy: Directed (0.1) <-> Self-directed (0.9) -------------------
    # keep_distinct: decision RIGHTS and process, never meeting density
    # (that is collaboration) and never novelty of output (innovation).
    {
        "item_id": "env-autonomy-1",
        "dimension": "autonomy",
        "prompt": "How much say do you have over how your work gets done?",
        "prompt_past": "How much say did you have over how your work got done?",
        "anchor_order": ASCENDING,
        "options": [
            {
                "key": "a",
                "pole": "low",
                "text": "Your work is assigned and specified for you, and most decisions go up for sign-off before you act.",
                "text_past": "Your work was assigned and specified for you, and most decisions went up for sign-off before you acted.",
            },
            {
                "key": "b",
                "pole": "leaning_low",
                "text": "Your manager sets the direction and the priorities; you choose your own tactics inside clear guardrails.",
                "text_past": "Your manager set the direction and the priorities; you chose your own tactics inside clear guardrails.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "Direction is set at the team level, and within that you pick how the work gets done.",
                "text_past": "Direction was set at the team level, and within that you picked how the work got done.",
            },
            {
                "key": "d",
                "pole": "leaning_high",
                "text": "You own the outcome and choose your own approach, with only light approval along the way.",
                "text_past": "You owned the outcome and chose your own approach, with only light approval along the way.",
            },
            {
                "key": "e",
                "pole": "high",
                "text": "You set your own priorities and your own methods, and almost nothing needs approval.",
                "text_past": "You set your own priorities and your own methods, and almost nothing needed approval.",
            },
        ],
    },
    {
        "item_id": "env-autonomy-2",
        "dimension": "autonomy",
        "prompt": "Who decides what you work on, and in what order?",
        "prompt_past": "Who decided what you worked on, and in what order?",
        "anchor_order": DESCENDING,
        "options": [
            {
                "key": "a",
                "pole": "high",
                "text": "You decide what you take on and in what order; nobody hands you a queue.",
                "text_past": "You decided what you took on and in what order; nobody handed you a queue.",
            },
            {
                "key": "b",
                "pole": "leaning_high",
                "text": "You’re given the outcomes to hit, and the sequence and the timing are yours.",
                "text_past": "You were given the outcomes to hit, and the sequence and the timing were yours.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "You and your manager set your priorities together, and either of you can move them.",
                "text_past": "You and your manager set your priorities together, and either of you could move them.",
            },
            {
                "key": "d",
                "pole": "leaning_low",
                "text": "Your priorities are set for you, though you can make the case for changing them.",
                "text_past": "Your priorities were set for you, though you could make the case for changing them.",
            },
            {
                "key": "e",
                "pole": "low",
                "text": "What you work on and when is scheduled for you, and changing it takes permission.",
                "text_past": "What you worked on and when was scheduled for you, and changing it took permission.",
            },
        ],
    },
    # -- pace: Steady (0.1) <-> Fast (0.9) ----------------------------------
    # keep_distinct: tempo only, never novelty (innovation). Response-time
    # expectations belong here and NOT under feedback — the rubric assigns
    # them to pace explicitly, which is why item 2 takes that facet.
    {
        "item_id": "env-pace-1",
        "dimension": "pace",
        "prompt": "What is the tempo of the work?",
        "prompt_past": "What was the tempo of the work?",
        "anchor_order": DESCENDING,
        "options": [
            {
                "key": "a",
                "pole": "high",
                "text": "The tempo is fast: aggressive deadlines, quick turnaround, and an intense week.",
                "text_past": "The tempo was fast: aggressive deadlines, quick turnaround, and an intense week.",
            },
            {
                "key": "b",
                "pole": "leaning_high",
                "text": "Urgency is regular — timelines are tight-ish and work goes out often, without being relentless.",
                "text_past": "Urgency was regular — timelines were tight-ish and work went out often, without being relentless.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "The tempo is ordinary: some stretches of crunch, some stretches of calm.",
                "text_past": "The tempo was ordinary: some stretches of crunch, some stretches of calm.",
            },
            {
                "key": "d",
                "pole": "leaning_low",
                "text": "The tempo is generally measured, with occasional pushes; deadlines exist but rarely dominate the week.",
                "text_past": "The tempo was generally measured, with occasional pushes; deadlines existed but rarely dominated the week.",
            },
            {
                "key": "e",
                "pole": "low",
                "text": "The tempo is deliberate: long planning horizons and an unhurried week.",
                "text_past": "The tempo was deliberate: long planning horizons and an unhurried week.",
            },
        ],
    },
    {
        "item_id": "env-pace-2",
        "dimension": "pace",
        "prompt": "How quickly are things expected to happen?",
        "prompt_past": "How quickly were things expected to happen?",
        "anchor_order": ASCENDING,
        "options": [
            {
                "key": "a",
                "pole": "low",
                "text": "Nothing is expected in a hurry — requests can wait until you get to them.",
                "text_past": "Nothing was expected in a hurry — requests could wait until you got to them.",
            },
            {
                "key": "b",
                "pole": "leaning_low",
                "text": "Most things can wait a day or two; a genuine rush is the exception.",
                "text_past": "Most things could wait a day or two; a genuine rush was the exception.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "Some things need an answer the same day, some can sit for a week.",
                "text_past": "Some things needed an answer the same day, some could sit for a week.",
            },
            {
                "key": "d",
                "pole": "leaning_high",
                "text": "Quick turnaround is the norm — you’re expected to respond and move within the day.",
                "text_past": "Quick turnaround was the norm — you were expected to respond and move within the day.",
            },
            {
                "key": "e",
                "pole": "high",
                "text": "Requests land expecting an answer now, and your week can be rearranged overnight.",
                "text_past": "Requests landed expecting an answer now, and your week could be rearranged overnight.",
            },
        ],
    },
    # -- collaboration: Solo (0.1) <-> Collective (0.9) ---------------------
    # keep_distinct: HOW MUCH joint work happens. Never decision rights
    # (autonomy) — the rubric's own 0.7 band says "decisions shared" and that
    # phrase is deliberately NOT carried across. Never warmth or the quality
    # of working relationships, which is the round-1 collision with feedback
    # and is not a signal on either axis.
    {
        "item_id": "env-collaboration-1",
        "dimension": "collaboration",
        "prompt": "How does the work actually get produced?",
        "prompt_past": "How did the work actually get produced?",
        "anchor_order": ASCENDING,
        "options": [
            {
                "key": "a",
                "pole": "low",
                "text": "You produce your work heads-down and alone; meetings are rare and there is no pairing or joint working time.",
                "text_past": "You produced your work heads-down and alone; meetings were rare and there was no pairing or joint working time.",
            },
            {
                "key": "b",
                "pole": "leaning_low",
                "text": "You produce the work alone and bring it to periodic syncs; those meetings are status and handoff, not joint problem-solving.",
                "text_past": "You produced the work alone and brought it to periodic syncs; those meetings were status and handoff, not joint problem-solving.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "Roughly half the work is done alone and half of it in a group; neither mode dominates how the work gets made.",
                "text_past": "Roughly half the work was done alone and half of it in a group; neither mode dominated how the work got made.",
            },
            {
                "key": "d",
                "pole": "leaning_high",
                "text": "Cross-functional work is common and meetings are frequent; most problems get worked through as a group.",
                "text_past": "Cross-functional work was common and meetings were frequent; most problems got worked through as a group.",
            },
            {
                "key": "e",
                "pole": "high",
                "text": "Almost everything is produced together — constant pairing, standing group sessions, a team you are working alongside all day.",
                "text_past": "Almost everything was produced together — constant pairing, standing group sessions, a team you were working alongside all day.",
            },
        ],
    },
    {
        "item_id": "env-collaboration-2",
        "dimension": "collaboration",
        "prompt": "How much of your working day is spent working with other people?",
        "prompt_past": "How much of your working day was spent working with other people?",
        "anchor_order": DESCENDING,
        "options": [
            {
                "key": "a",
                "pole": "high",
                "text": "Most of the day is live time with other people — calls, working sessions, back-and-forth throughout.",
                "text_past": "Most of the day was live time with other people — calls, working sessions, back-and-forth throughout.",
            },
            {
                "key": "b",
                "pole": "leaning_high",
                "text": "You’re in live working sessions with others most days, with time in between to work on your own.",
                "text_past": "You were in live working sessions with others most days, with time in between to work on your own.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "It is an even mix of live group time and written, work-on-your-own time.",
                "text_past": "It was an even mix of live group time and written, work-on-your-own time.",
            },
            {
                "key": "d",
                "pole": "leaning_low",
                "text": "It is mostly written and asynchronous, with a live session when something needs one.",
                "text_past": "It was mostly written and asynchronous, with a live session when something needed one.",
            },
            {
                "key": "e",
                "pole": "low",
                "text": "Written updates stand in for meetings almost entirely, and long stretches of solo time are the norm.",
                "text_past": "Written updates stood in for meetings almost entirely, and long stretches of solo time were the norm.",
            },
        ],
    },
    # -- feedback: Sparse / gentle (0.1) <-> Frequent / blunt (0.9) ---------
    # keep_distinct, the strictest of the six: CRITIQUE only — how often it
    # comes (item 1) and how it is delivered (item 2). Nothing about support,
    # recognition, mentorship, career development, psychological safety or how
    # pleasant the team is; warmth is orthogonal to this axis and appears at
    # both poles, so it appears at neither pole here. Response-time
    # expectations are pace, and how much people talk to each other is
    # collaboration.
    {
        "item_id": "env-feedback-1",
        "dimension": "feedback",
        "prompt": "How often do you hear how your work is landing?",
        "prompt_past": "How often did you hear how your work was landing?",
        "anchor_order": ASCENDING,
        "options": [
            {
                "key": "a",
                "pole": "low",
                "text": "Rarely — you hear about your work occasionally, and often only when something has gone wrong.",
                "text_past": "Rarely — you heard about your work occasionally, and often only when something had gone wrong.",
            },
            {
                "key": "b",
                "pole": "leaning_low",
                "text": "Feedback arrives mainly on a fixed cycle: a review, or a scheduled check-in.",
                "text_past": "Feedback arrived mainly on a fixed cycle: a review, or a scheduled check-in.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "A normal mix: scheduled reviews, plus comment in the moment when something comes up.",
                "text_past": "A normal mix: scheduled reviews, plus comment in the moment when something came up.",
            },
            {
                "key": "d",
                "pole": "leaning_high",
                "text": "Often — you get comment on your work well outside any review cycle.",
                "text_past": "Often — you got comment on your work well outside any review cycle.",
            },
            {
                "key": "e",
                "pole": "high",
                "text": "Constantly — you hear how the work is landing as you go, from whoever is looking at it.",
                "text_past": "Constantly — you heard how the work was landing as you went, from whoever was looking at it.",
            },
        ],
    },
    {
        "item_id": "env-feedback-2",
        "dimension": "feedback",
        "prompt": "How is criticism of your work delivered?",
        "prompt_past": "How was criticism of your work delivered?",
        "anchor_order": DESCENDING,
        "options": [
            {
                "key": "a",
                "pole": "high",
                "text": "Criticism is delivered straight and unsoftened, and open disagreement about the work is routine.",
                "text_past": "Criticism was delivered straight and unsoftened, and open disagreement about the work was routine.",
            },
            {
                "key": "b",
                "pole": "leaning_high",
                "text": "Criticism is fairly direct and debate about the work is normal; a thick skin helps.",
                "text_past": "Criticism was fairly direct and debate about the work was normal; a thick skin helped.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "Criticism is delivered plainly and in moderation — neither blunt nor heavily cushioned.",
                "text_past": "Criticism was delivered plainly and in moderation — neither blunt nor heavily cushioned.",
            },
            {
                "key": "d",
                "pole": "leaning_low",
                "text": "Criticism is delivered diplomatically; directness is the exception.",
                "text_past": "Criticism was delivered diplomatically; directness was the exception.",
            },
            {
                "key": "e",
                "pole": "low",
                "text": "Criticism is cushioned or indirect when it comes, and open disagreement is rare.",
                "text_past": "Criticism was cushioned or indirect when it came, and open disagreement was rare.",
            },
        ],
    },
    # -- innovation: Refine / optimize (0.1) <-> Invent / explore (0.9) -----
    # keep_distinct: novelty of the work only. Never speed (pace) and never
    # how prescribed the method is (autonomy) — a rigid playbook can govern
    # genuinely new work, so no process language appears in these items.
    {
        "item_id": "env-innovation-1",
        "dimension": "innovation",
        "prompt": "What kind of work is it — improving what exists, or making what doesn’t?",
        "prompt_past": "What kind of work was it — improving what existed, or making what didn’t?",
        "anchor_order": DESCENDING,
        "options": [
            {
                "key": "a",
                "pole": "high",
                "text": "Creating things that don’t exist yet — new offerings, new capabilities, bets that may not come off.",
                "text_past": "Creating things that didn’t exist yet — new offerings, new capabilities, bets that might not come off.",
            },
            {
                "key": "b",
                "pole": "leaning_high",
                "text": "Building something new comes up often, alongside the work of running what already exists.",
                "text_past": "Building something new came up often, alongside the work of running what already existed.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "A real split: part of the work improves what exists, part of it creates something new.",
                "text_past": "A real split: part of the work improved what existed, part of it created something new.",
            },
            {
                "key": "d",
                "pole": "leaning_low",
                "text": "Mostly improving what already exists, with the occasional genuinely new thing at the edges.",
                "text_past": "Mostly improving what already existed, with the occasional genuinely new thing at the edges.",
            },
            {
                "key": "e",
                "pole": "low",
                "text": "Making something that already exists work better — improvement and scale, not new territory.",
                "text_past": "Making something that already existed work better — improvement and scale, not new territory.",
            },
        ],
    },
    {
        "item_id": "env-innovation-2",
        "dimension": "innovation",
        "prompt": "How much of the work is a bet that might not pay off?",
        "prompt_past": "How much of the work was a bet that might not pay off?",
        "anchor_order": ASCENDING,
        "options": [
            {
                "key": "a",
                "pole": "low",
                "text": "Almost none — work that doesn’t pan out isn’t planned for, and what gets started is expected to land.",
                "text_past": "Almost none — work that didn’t pan out wasn’t planned for, and what got started was expected to land.",
            },
            {
                "key": "b",
                "pole": "leaning_low",
                "text": "The occasional experiment is tolerated, but the bulk of the effort goes to things with a known payoff.",
                "text_past": "The occasional experiment was tolerated, but the bulk of the effort went to things with a known payoff.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "Some of the work is a known quantity and some of it is a bet; both are normal.",
                "text_past": "Some of the work was a known quantity and some of it was a bet; both were normal.",
            },
            {
                "key": "d",
                "pole": "leaning_high",
                "text": "Experiments are a planned part of the work, and some of them are expected not to pan out.",
                "text_past": "Experiments were a planned part of the work, and some of them were expected not to pan out.",
            },
            {
                "key": "e",
                "pole": "high",
                "text": "Exploration is the point — a good share of what is tried is expected to fail, and that is budgeted for.",
                "text_past": "Exploration was the point — a good share of what was tried was expected to fail, and that was budgeted for.",
            },
        ],
    },
    # -- decision: Intuition / judgement (0.1) <-> Data / analysis (0.9) ----
    # keep_distinct: what a decision RESTS ON, never who has the authority to
    # make it. No approval, ownership, independence or process language
    # appears in these two items — all of that is autonomy, and the rubric
    # names it as this dimension's most common leak.
    {
        "item_id": "env-decision-1",
        "dimension": "decision",
        "prompt": "What do decisions actually rest on?",
        "prompt_past": "What did decisions actually rest on?",
        "anchor_order": ASCENDING,
        "options": [
            {
                "key": "a",
                "pole": "low",
                "text": "Taste, experience and vision — someone’s judgement carries the call.",
                "text_past": "Taste, experience and vision — someone’s judgement carried the call.",
            },
            {
                "key": "b",
                "pole": "leaning_low",
                "text": "Judgement leads, and numbers are brought in afterwards to confirm it.",
                "text_past": "Judgement led, and numbers were brought in afterwards to confirm it.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "Judgement and evidence both carry weight, depending on the call.",
                "text_past": "Judgement and evidence both carried weight, depending on the call.",
            },
            {
                "key": "d",
                "pole": "leaning_high",
                "text": "Measurement usually settles it, with judgement filling the gaps the numbers don’t cover.",
                "text_past": "Measurement usually settled it, with judgement filling the gaps the numbers didn’t cover.",
            },
            {
                "key": "e",
                "pole": "high",
                "text": "Numbers settle it — measured, tested, and not decided until the evidence is in.",
                "text_past": "Numbers settled it — measured, tested, and not decided until the evidence was in.",
            },
        ],
    },
    {
        "item_id": "env-decision-2",
        "dimension": "decision",
        "prompt": "When you want to make a case for something, what carries it?",
        "prompt_past": "When you wanted to make a case for something, what carried it?",
        "anchor_order": DESCENDING,
        "options": [
            {
                "key": "a",
                "pole": "high",
                "text": "Numbers — you’re expected to bring measurements, tests or analysis.",
                "text_past": "Numbers — you were expected to bring measurements, tests or analysis.",
            },
            {
                "key": "b",
                "pole": "leaning_high",
                "text": "Usually evidence, though a well-argued judgement call can carry.",
                "text_past": "Usually evidence, though a well-argued judgement call could carry.",
            },
            {
                "key": "c",
                "pole": "mixed",
                "text": "Either a strong argument or good numbers will carry a case; both are ordinary currency.",
                "text_past": "Either a strong argument or good numbers would carry a case; both were ordinary currency.",
            },
            {
                "key": "d",
                "pole": "leaning_low",
                "text": "Mostly reasoning and experience; numbers are supporting material.",
                "text_past": "Mostly reasoning and experience; numbers were supporting material.",
            },
            {
                "key": "e",
                "pole": "low",
                "text": "Argument and instinct — the numbers are rarely what decides it.",
                "text_past": "Argument and instinct — the numbers were rarely what decided it.",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# The four non-dimension items
# ---------------------------------------------------------------------------
# These are NOT scored into any dimension and never reach A-3's mean. Two are
# the model's continuous confounders, one its categorical confounder
# (`industry`), and one its outcome node. All four are stored raw, exactly as
# `causal_graph/v1_model/schema.sql` encodes them on the company side (1..5
# integers, or the level key for `industry`), so the two sides compare directly.
#
# The three ordinal items are presented in natural 1->5 order, with no
# anchor-order alternation: reversing a numeric ordinal scale confuses far
# more than it defends, and none of them is averaged with anything, so a
# straight-lined position cannot be laundered into a dimension score the way
# it could on the twelve.
STAGE_SIZE_ITEM: ContextItem = {
    "item_id": "stage_size",
    "prompt": "How big is the organization you work for — the whole organization, not your team?",
    "prompt_past": "How big was the organization you worked for in that role — the whole organization, not your team?",
    "options": [
        {
            "value": 1,
            "text": "An early-stage startup — a handful of people, still finding its footing.",
            "text_past": "An early-stage startup — a handful of people, still finding its footing.",
        },
        {
            "value": 2,
            "text": "A small company that has found its footing and is growing — tens of people.",
            "text_past": "A small company that had found its footing and was growing — tens of people.",
        },
        {
            "value": 3,
            "text": "A mid-sized organization — hundreds of people, with real structure in place.",
            "text_past": "A mid-sized organization — hundreds of people, with real structure in place.",
        },
        {
            "value": 4,
            "text": "A large organization — thousands of people, established in its market.",
            "text_past": "A large organization — thousands of people, established in its market.",
        },
        {
            "value": 5,
            "text": "A very large enterprise — tens of thousands of people and many layers.",
            "text_past": "A very large enterprise — tens of thousands of people and many layers.",
        },
    ],
}

#: MARKET-RELATIVE, not dollars. `schema.sql`'s `comp` confounder is defined
#: as "1 well below .. 3 at market .. 5 well above, vs. talent-market peers for
#: comparable roles" and this item asks exactly that question and no other. It
#: does not ask for a salary figure, a band, or a currency — see
#: SITUATION_ITEMS_BIAS_REVIEW.md, Finding 6.
#:
#: A sixth option, "not sure", stores `None` rather than guessing at a band —
#: PRODUCT_DECISIONS.md §2, "Environment-instrument rulings" (2026-09-10):
#: Finding 6's measurement error is non-random (isolated, underpaid people are
#: the least likely to know their market rate and the most likely to default
#: to "about the same"), so a forced 1–5 answer would under-report underpayment
#: exactly where it is worst. Listed last so the 1..5 ordinal scale itself
#: stays intact (`test_context_items_are_one_to_five_in_natural_order` checks
#: the first five separately from this one).
COMP_ITEM: ContextItem = {
    "item_id": "comp",
    "prompt": "Compared with what you could earn elsewhere doing similar work, how does this role pay?",
    "prompt_past": "Compared with what you could have earned elsewhere doing similar work, how did that role pay?",
    "options": [
        {
            "value": 1,
            "text": "Well below what you could get elsewhere for similar work.",
            "text_past": "Well below what you could have got elsewhere for similar work.",
        },
        {
            "value": 2,
            "text": "Somewhat below.",
            "text_past": "Somewhat below.",
        },
        {
            "value": 3,
            "text": "About the same — at market.",
            "text_past": "About the same — at market.",
        },
        {
            "value": 4,
            "text": "Somewhat above.",
            "text_past": "Somewhat above.",
        },
        {
            "value": 5,
            "text": "Well above what you could get elsewhere for similar work.",
            "text_past": "Well above what you could have got elsewhere for similar work.",
        },
        {
            "value": None,
            "text": "Not sure how this compares.",
            "text_past": "Not sure how that compared.",
        },
    ],
}

#: `solverah_model_config.yaml`'s `industry` levels, in config order. The model
#: indexes a per-level weight by position in that list, so these keys must be
#: the config's exactly; a tripwire test asserts it rather than trusting this
#: comment. Restated rather than read from the YAML because this module does
#: no I/O.
INDUSTRY_LEVELS: tuple[str, ...] = ("tech", "finance", "healthcare", "retail", "other")

#: The model's categorical confounder (`industry`, biasing `decision` and
#: `feedback`). Until 2026-10-01 the instrument never asked it, so every
#: training row was masked and its five weights only ever came back at their
#: prior. Optional by ruling (PRODUCT_DECISIONS.md §2, 2026-10-01): the last
#: option stores `None`, the same way `comp`'s "not sure" does, and the model
#: masks that row's term rather than guessing a sector. "Something else" is
#: NOT that option. It is a real level (`other`) with its own weight.
#:
#: The options are category labels, and those don't change with tense, so
#: both variants of each are identical. Only the stem is tensed.
INDUSTRY_ITEM: ContextItem = {
    "item_id": "industry",
    "prompt": "Which industry is the organization you work for in?",
    "prompt_past": "Which industry did the organization you worked for in that role belong to?",
    "options": [
        {
            "value": "tech",
            "text": "Technology — software, hardware, internet or IT services.",
            "text_past": "Technology — software, hardware, internet or IT services.",
        },
        {
            "value": "finance",
            "text": "Finance — banking, insurance, investment or accounting.",
            "text_past": "Finance — banking, insurance, investment or accounting.",
        },
        {
            "value": "healthcare",
            "text": "Healthcare — hospitals, clinics, pharma or health services.",
            "text_past": "Healthcare — hospitals, clinics, pharma or health services.",
        },
        {
            "value": "retail",
            "text": "Retail — shops, e-commerce or consumer goods.",
            "text_past": "Retail — shops, e-commerce or consumer goods.",
        },
        {
            "value": "other",
            "text": "Something else.",
            "text_past": "Something else.",
        },
        {
            "value": None,
            "text": "Not sure, or I’d rather not say.",
            "text_past": "Not sure, or I’d rather not say.",
        },
    ],
}

#: The model's outcome node — `outcome_experienced.working_scale`'s question,
#: asked of the user about their own role. The only evaluative item in the
#: instrument, and last in the form so its verdict cannot prime the twelve
#: descriptive items.
EXPERIENCED_ITEM: ContextItem = {
    "item_id": "experienced",
    "prompt": "Overall, how well is this role working for you?",
    "prompt_past": "Overall, how well was that role working for you?",
    "options": [
        {"value": 1, "text": "It isn’t working at all.", "text_past": "It wasn’t working at all."},
        {"value": 2, "text": "It isn’t working well.", "text_past": "It wasn’t working well."},
        {"value": 3, "text": "A mixed picture.", "text_past": "A mixed picture."},
        {"value": 4, "text": "It’s working well.", "text_past": "It was working well."},
        {"value": 5, "text": "It’s working very well.", "text_past": "It was working very well."},
    ],
}

#: Form order: the three neutral context facts, then the twelve descriptive
#: items, then the one evaluative item. `comp` sits at position two rather than
#: next to `experienced` on purpose — adjacency between a pay question and the
#: outcome question would inflate their correlation, and that correlation is a
#: weight the causal model is later asked to estimate. `industry` joins the
#: facts at position three for the same reason: it is a confounder too, and it
#: belongs far from the outcome.
CONTEXT_ITEMS: list[ContextItem] = [
    STAGE_SIZE_ITEM,
    COMP_ITEM,
    INDUSTRY_ITEM,
    EXPERIENCED_ITEM,
]

#: `ContextItem.item_id` -> its `environment_reports` column (A-2). `experienced`
#: is the only one whose names differ.
CONTEXT_COLUMNS: dict[str, str] = {
    "stage_size": "stage_size",
    "comp": "comp",
    "industry": "industry",
    "experienced": "experienced_outcome",
}

EXPECTED_DIMENSION_ITEM_COUNT = len(ENVIRONMENT_ITEMS)
EXPECTED_CONTEXT_ITEM_COUNT = len(CONTEXT_ITEMS)

_ITEMS_BY_ID: dict[str, EnvironmentItem] = {i["item_id"]: i for i in ENVIRONMENT_ITEMS}
_CONTEXT_BY_ID: dict[str, ContextItem] = {i["item_id"]: i for i in CONTEXT_ITEMS}


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

def is_past_tense(career_status: str) -> bool:
    """Whether this user's items render in past tense.

    `employed` describes the current role; `between_jobs` and `first_job`
    describe the most recent one, and A-5 renders the report needs-forward
    from the same flag (BUILD_PLAN A-1). A `first_job` user who has never held
    a role cannot answer these items at all — that is a skip path A-5 owes
    them, not a wording problem this module can solve. See
    SITUATION_ITEMS_BIAS_REVIEW.md, Finding 7.
    """
    if career_status not in TENSE_BY_CAREER_STATUS:
        raise ValueError(
            f"Unknown career_status {career_status!r}; expected one of "
            f"{', '.join(sorted(TENSE_BY_CAREER_STATUS))}"
        )
    return TENSE_BY_CAREER_STATUS[career_status]


#: `environment_reports.subject`'s values, restated (model.ENV_REPORT_SUBJECTS pulls in
#: Flask). `past` is the one job before the user's current or most recent one
#: (PRODUCT_DECISIONS.md §2, 2026-10-01).
SUBJECTS: tuple[str, ...] = ("current", "past")


def is_past_tense_for(career_status: str, subject: str = "current") -> bool:
    """Whether a report about *subject* renders in past tense for this user.

    A `past` report describes a job the user has left, whatever their status
    today, so it is always past tense. A `current` report follows
    `is_past_tense(career_status)` unchanged. `career_status` is validated
    either way, so an unknown status still raises.
    """
    past_by_status = is_past_tense(career_status)
    if subject not in SUBJECTS:
        raise ValueError(
            f"Unknown subject {subject!r}; expected one of {', '.join(SUBJECTS)}"
        )
    return True if subject == "past" else past_by_status


def option_score(item_id: str, option_key: str) -> float:
    """The 0–1 score for one chosen option of one dimension item.

    Independent of tense by construction: the score lives on the option's
    `pole`, and both tense variants of an option share it. A user who answered
    the past-tense form scores identically to one who answered the present-tense
    form.
    """
    item = _ITEMS_BY_ID.get(item_id)
    if item is None:
        raise ValueError(f"Unknown item id {item_id!r}")
    option = next((o for o in item["options"] if o["key"] == option_key), None)
    if option is None:
        raise ValueError(f"Item {item_id} has no option {option_key!r}")
    return POLE_VALUES[option["pole"]]


def context_value(item_id: str, value: int | None) -> int | None:
    """Validate a 1..5 answer to an ordinal context item and return it unchanged.

    A pass-through with a guard, not a transform: `stage_size`, `comp` and
    `experienced` are stored RAW and unscaled (`schema.sql`: "stored RAW /
    unscaled; the model standardizes via the `scale` in
    solverah_model_config.yaml"), so anything that rescaled here would put this
    side of the training pair on a different footing from the company side.

    `None` is accepted only where the item's own options carry it — today
    only `comp`'s "not sure" (PRODUCT_DECISIONS.md §2, 2026-09-10). Elsewhere
    it falls through to the same "must be an int" rejection any other
    non-int does, so `stage_size`/`experienced` stay non-nullable without a
    second code path.
    """
    item = _context_item(item_id)
    if is_categorical(item):
        raise ValueError(f"{item_id} is categorical; validate it with context_level")
    valid_values = {o["value"] for o in item["options"]}
    if value is None and None in valid_values:
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{item_id} answer must be an int, got {value!r}")
    if value not in valid_values:
        raise ValueError(f"{item_id} has no option with value {value!r}")
    return value


def context_level(item_id: str, value: str | None) -> str | None:
    """Validate an answer to a CATEGORICAL context item (today only
    `industry`) and return it unchanged: a level key, or `None` for the item's
    "not sure / prefer not to say" option.

    This is `context_value`'s twin, split off so each keeps an honest return
    type. The answer is stored raw as the level key, which is how `schema.sql`
    encodes the company side (`value_cat`). `match_core.preprocess_conf` turns
    the key into the model's level index, so this function doesn't.
    """
    item = _context_item(item_id)
    if not is_categorical(item):
        raise ValueError(f"{item_id} is ordinal; validate it with context_value")
    valid_values = {o["value"] for o in item["options"]}
    if value is None and None in valid_values:
        return value
    if not isinstance(value, str):
        raise ValueError(f"{item_id} answer must be a string, got {value!r}")
    if value not in valid_values:
        raise ValueError(f"{item_id} has no option with value {value!r}")
    return value


def is_categorical(item: ContextItem) -> bool:
    """Whether a context item answers with a level key rather than a 1..5 int.
    Read off the options themselves, so a new item cannot forget a flag."""
    return any(isinstance(o["value"], str) for o in item["options"])


def _context_item(item_id: str) -> ContextItem:
    item = _CONTEXT_BY_ID.get(item_id)
    if item is None:
        raise ValueError(f"Unknown context item id {item_id!r}")
    return item


def render_items(career_status: str) -> list[dict]:
    """The twelve dimension items with one tense resolved, in form order.

    Returns plain dicts with a single `prompt` and a single `text` per option —
    the shape a form renderer (A-7) wants, with the variant it must not show
    already dropped so it cannot show the wrong one by accident.
    """
    past = is_past_tense(career_status)
    return [
        {
            "item_id": item["item_id"],
            "dimension": item["dimension"],
            "prompt": item["prompt_past"] if past else item["prompt"],
            "anchor_order": item["anchor_order"],
            "options": [
                {
                    "key": o["key"],
                    "text": o["text_past"] if past else o["text"],
                }
                for o in item["options"]
            ],
        }
        for item in item_list_in_form_order()
    ]


def render_context_items(career_status: str) -> list[dict]:
    """The four non-dimension items with one tense resolved, in form order."""
    past = is_past_tense(career_status)
    return [
        {
            "item_id": item["item_id"],
            "prompt": item["prompt_past"] if past else item["prompt"],
            "options": [
                {
                    "value": o["value"],
                    "text": o["text_past"] if past else o["text"],
                }
                for o in item["options"]
            ],
        }
        for item in CONTEXT_ITEMS
    ]


def item_list_in_form_order() -> list[EnvironmentItem]:
    """The twelve dimension items, grouped by `DIMENSIONS` order.

    `ENVIRONMENT_ITEMS` is already written in this order; the function exists
    so a caller depends on the stated contract rather than on the literal's
    line order, and so a test can assert the two agree.
    """
    return [item for dim in DIMENSIONS for item in ENVIRONMENT_ITEMS if item["dimension"] == dim]


def item_spec(career_status: str = "employed") -> list[dict]:
    """The item bank as scoring data: `item_id`, `dimension`, and one
    `pole_values` entry per option key.

    The seam A-1 and A-3 meet on. A-3 (`work_pulse/situation.py`) does the
    mean_pole arithmetic and this module does not duplicate it — an item bank
    that scored itself would be a second implementation of the person side's
    `score_all_dimensions`, which is exactly what A-3 exists to avoid.

    **Resolved 2026-09-10 (reconciliation pass).** A-3's `score_environment`
    was already generalized to `EnvironmentItemSpec.pole_values: Mapping[str,
    float]` by the time this instrument landed — it never assumed a
    two-anchor `(low, high)` pair. The one real seam gap was a naming
    mismatch: this function used to emit the mapping under the key
    `anchor_values`, which `score_environment` does not read (it reads
    `pole_values`). Renamed here to close it; `tests/test_situation_items.py`
    proves the real end-to-end path (`situation.score_environment(answers,
    item_spec())`) rather than the tombstone that used to guard this seam.
    See SITUATION_ITEMS_BIAS_REVIEW.md, "Integration note", for the history.

    `text` is display wording only and no scorer reads it, so `career_status`
    changes it and changes nothing about the score.
    """
    past = is_past_tense(career_status)
    return [
        {
            "item_id": item["item_id"],
            "dimension": item["dimension"],
            "pole_values": {o["key"]: POLE_VALUES[o["pole"]] for o in item["options"]},
            "text": item["prompt_past"] if past else item["prompt"],
        }
        for item in ENVIRONMENT_ITEMS
    ]
