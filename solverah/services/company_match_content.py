"""Authored content for the CompanyLens read: trait labels, the interview-question
bank, next-step categories and the company-size note.

Six-trait build, C6 (2026-10-13). PRODUCT_DECISIONS.md §2: "Manager/team uncertainty
becomes guidance: for the user's must-have traits, an authored interview-question bank
(trait x status x direction; best-guess drafts, Julie revises)."

Every string here is BEST-GUESS COPY. Julie owns the wording and revises it on the built
product; nothing in this module is load-bearing beyond being present and keyed right.
The keys ARE load-bearing: `company_match_service` looks a cell up by
``(trait, status, direction)`` and a missing cell is a bug, so a test pins the bank at
exactly 6 x 2 x 2 cells with two to three questions and one explanation each.

THE THREE AXES
--------------
* trait: the six keys in `solverah.domain.trait_preferences.TRAIT_KEYS`.
* status: ``unknown`` (too little evidence to read the company on this trait) or
  ``mixed`` (the evidence disagrees and is not averaged -- both ends are shown).
* direction: which pole the USER prefers, ``prefers_more`` (the high pole: self-directed,
  fast, collective, frequent/blunt, invent, data) or ``prefers_less`` (the low pole). The
  questions are what the user should ask to find out which end the actual team sits at,
  phrased from the side they care about.

The examples in Solverah_IP/match_model_alignment/05_USER_JOURNEYS.md (Daniel: autonomy,
mixed, prefers more) are the seeds; the rest follows their shape.
"""

from __future__ import annotations

from typing import Optional

from solverah.domain.trait_preferences import TRAIT_KEYS

__all__ = [
    "NEXT_STEPS",
    "STATUS_MIXED",
    "STATUS_UNKNOWN",
    "PREFERS_LESS",
    "PREFERS_MORE",
    "TRAIT_LABELS",
    "TRAIT_POLES",
    "direction_for_person",
    "explanation",
    "interview_questions",
    "size_note",
]

STATUS_UNKNOWN = "unknown"
STATUS_MIXED = "mixed"
PREFERS_MORE = "prefers_more"
PREFERS_LESS = "prefers_less"

#: Julie's next-step set (05_USER_JOURNEYS.md). `company_match_service.next_step` picks
#: one per company; the values are what goes on the wire.
NEXT_STEPS = ("decide", "investigate", "prepare", "explore", "act", "dont_act_yet")

#: Plain labels, matching 03_SIX_TRAIT_BOUNDARY.md.
TRAIT_LABELS: dict[str, str] = {
    "autonomy": "Autonomy",
    "pace": "Pace",
    "collaboration": "Collaboration",
    "feedback": "Feedback",
    "innovation": "Innovation",
    "decision": "Decision basis",
}

#: (low pole, high pole), in the user's words.
TRAIT_POLES: dict[str, tuple[str, str]] = {
    "autonomy": ("directed", "self-directed"),
    "pace": ("steady", "fast"),
    "collaboration": ("solo", "collective"),
    "feedback": ("sparse and gentle", "frequent and blunt"),
    "innovation": ("refine what exists", "invent what does not"),
    "decision": ("judgement", "data and analysis"),
}


def direction_for_person(person_score: float) -> str:
    """Which pole the user prefers, from their own core score (0..1). The midpoint
    counts as `prefers_more` -- a documented tie rule, not a measurement."""
    return PREFERS_MORE if float(person_score) >= 0.5 else PREFERS_LESS


# ---------------------------------------------------------------------------
# The bank: (trait, status, direction) -> (explanation, [questions])
# ---------------------------------------------------------------------------

_BANK: dict[tuple[str, str, str], tuple[str, list[str]]] = {
    # ---- autonomy -----------------------------------------------------------
    ("autonomy", STATUS_UNKNOWN, PREFERS_MORE): (
        "We found too little on how much latitude people here get, and you need room to "
        "run your own work. Ask about it directly.",
        [
            "What decisions would I make without checking with you first?",
            "Walk me through the last time someone on the team changed how a piece of work "
            "was done. Who proposed it, and who had to approve it?",
            "How are priorities set for someone in this role, and how often do they change "
            "from above?",
        ],
    ),
    ("autonomy", STATUS_UNKNOWN, PREFERS_LESS): (
        "We found too little on how much direction people here get, and you work best "
        "with clear direction. Ask about it directly.",
        [
            "How much of this role comes with a defined process, and how much is left to me "
            "to work out?",
            "When I am unsure how to approach something, who do I go to, and how quickly do "
            "I get an answer?",
            "How often do you and the person in this role go through priorities together?",
        ],
    ),
    ("autonomy", STATUS_MIXED, PREFERS_MORE): (
        "The evidence disagrees on autonomy: some parts of the company describe real "
        "ownership, others describe sign-off for everything. Find out which this team is.",
        [
            "Walk me through the last process change on this team. Who proposed it, and who "
            "had to approve it?",
            "What decisions would I make without checking with you first?",
            "Which parts of the company have the most approval layers, and is this team one "
            "of them?",
        ],
    ),
    ("autonomy", STATUS_MIXED, PREFERS_LESS): (
        "The evidence disagrees on autonomy: some parts of the company give a lot of "
        "latitude, others give clear direction. Find out which this team is.",
        [
            "How much structure does this team give a new person in the first few months?",
            "When someone is unsure how to approach a task, what usually happens next?",
            "Is this team run more like the corporate side or more like the field side of "
            "the company?",
        ],
    ),
    # ---- pace ---------------------------------------------------------------
    ("pace", STATUS_UNKNOWN, PREFERS_MORE): (
        "We could not read the pace here, and you want a fast one. Ask what a normal week "
        "looks like.",
        [
            "What did last week look like for the person in this role?",
            "How often do deadlines move, and what happens on the team when they do?",
            "How quickly does a decision made on Monday turn into something shipped?",
        ],
    ),
    ("pace", STATUS_UNKNOWN, PREFERS_LESS): (
        "We could not read the pace here, and you want a steady one. Ask what a normal "
        "week looks like, and what a bad one looks like.",
        [
            "What did last week look like for the person in this role?",
            "When was the last crunch, how long did it last, and what caused it?",
            "How much of the work is planned a month out versus decided that week?",
        ],
    ),
    ("pace", STATUS_MIXED, PREFERS_MORE): (
        "The evidence disagrees on pace: some teams or periods run fast, others steady. "
        "Find out which this team is right now.",
        [
            "Is this team in a build phase or a maintain phase, and how long has that been "
            "true?",
            "How does the pace here compare with the rest of the company?",
            "What did the last two weeks look like for the person in this role?",
        ],
    ),
    ("pace", STATUS_MIXED, PREFERS_LESS): (
        "The evidence disagrees on pace: some teams or periods run steady, others fast. "
        "Find out which this team is right now, and whether that holds.",
        [
            "When was the last crunch on this team, and what caused it?",
            "Which teams here run fastest, and is this one of them?",
            "How far ahead is the work planned, and how often does the plan change?",
        ],
    ),
    # ---- collaboration ------------------------------------------------------
    ("collaboration", STATUS_UNKNOWN, PREFERS_MORE): (
        "We could not read how work is shared here, and you want to work with people. "
        "Ask how a typical piece of work gets done.",
        [
            "Who would I work with day to day, and how much of my week would be with them?",
            "How does a piece of work move between people on this team?",
            "How much of the team's work is done together versus handed off?",
        ],
    ),
    ("collaboration", STATUS_UNKNOWN, PREFERS_LESS): (
        "We could not read how work is shared here, and you do your best work with "
        "heads-down time. Ask how much of the week is yours.",
        [
            "How much of a normal week is meetings or working sessions, and how much is "
            "uninterrupted work?",
            "Is there work on this team that one person owns end to end?",
            "How does the team protect focus time, if it does?",
        ],
    ),
    ("collaboration", STATUS_MIXED, PREFERS_MORE): (
        "The evidence disagrees on collaboration: some parts of the company work closely "
        "together, others are heads-down. Find out which this team is.",
        [
            "How much of this team's work is done together, in the room or on a call?",
            "Who would I work with most, and how often?",
            "Does this team work more like the parts of the company that build together or "
            "the parts that hand off?",
        ],
    ),
    ("collaboration", STATUS_MIXED, PREFERS_LESS): (
        "The evidence disagrees on collaboration: some parts of the company are heads-down, "
        "others are always together. Find out which this team is.",
        [
            "How much uninterrupted time does the person in this role get in a week?",
            "Is there work here that one person owns end to end, or is everything shared?",
            "How many standing meetings does this team have?",
        ],
    ),
    # ---- feedback -----------------------------------------------------------
    ("feedback", STATUS_UNKNOWN, PREFERS_MORE): (
        "We could not read how critique flows here, and you want frequent, direct "
        "feedback. Ask when you would last have heard what to improve.",
        [
            "When did someone on this team last get direct feedback on their work, and "
            "how was it given?",
            "How often would I hear what to do differently, outside a formal review?",
            "What happens here when a piece of work is not good enough?",
        ],
    ),
    ("feedback", STATUS_UNKNOWN, PREFERS_LESS): (
        "We could not read how critique flows here, and you prefer feedback that is "
        "considered and occasional. Ask how it is given.",
        [
            "How is feedback usually given on this team: in the moment, or set aside for "
            "later?",
            "What does a review conversation look like here?",
            "When work needs to change, how does that usually get raised?",
        ],
    ),
    ("feedback", STATUS_MIXED, PREFERS_MORE): (
        "The evidence disagrees on feedback: some describe frequent, direct critique, "
        "others say it is rare or softened. Find out which this manager does.",
        [
            "How often would I hear from you about what to do differently?",
            "Tell me about the last time you gave someone on the team hard feedback.",
            "Is feedback here more direct on some teams than others, and where is this one?",
        ],
    ),
    ("feedback", STATUS_MIXED, PREFERS_LESS): (
        "The evidence disagrees on feedback: some describe blunt, frequent critique, "
        "others say it is measured. Find out which this manager does.",
        [
            "How do you usually give feedback: in the moment, or set aside for a "
            "conversation?",
            "Tell me about the last time work on this team needed to change. How was that "
            "raised?",
            "Is the feedback style here the same across teams, or does it depend on the "
            "manager?",
        ],
    ),
    # ---- innovation ---------------------------------------------------------
    ("innovation", STATUS_UNKNOWN, PREFERS_MORE): (
        "We could not read whether the work here is new or established, and you want to "
        "build things that do not exist yet. Ask what the team made last.",
        [
            "What is the newest thing this team has built, and where did the idea come "
            "from?",
            "How much of the role is making something new versus improving what exists?",
            "What happens here when someone proposes something nobody has tried?",
        ],
    ),
    ("innovation", STATUS_UNKNOWN, PREFERS_LESS): (
        "We could not read whether the work here is new or established, and you do your "
        "best work refining what already works. Ask how much is settled.",
        [
            "How much of this role is improving an existing system versus starting from "
            "scratch?",
            "How settled is the way this team works, and how often does it get reinvented?",
            "What does a good quarter look like for this team?",
        ],
    ),
    ("innovation", STATUS_MIXED, PREFERS_MORE): (
        "The evidence disagrees on innovation: some parts of the company invent, others "
        "keep things running. Find out which this team does.",
        [
            "Is this team closer to the parts of the company that build new things or the "
            "parts that run existing ones?",
            "What is the newest thing this team has made in the last year?",
            "How much room is there to try something nobody has tried?",
        ],
    ),
    ("innovation", STATUS_MIXED, PREFERS_LESS): (
        "The evidence disagrees on innovation: some parts of the company reinvent "
        "constantly, others refine. Find out which this team does.",
        [
            "How settled is the way this team works?",
            "How much of the role is keeping something good working versus starting over?",
            "Which teams here change direction most, and is this one of them?",
        ],
    ),
    # ---- decision -----------------------------------------------------------
    ("decision", STATUS_UNKNOWN, PREFERS_MORE): (
        "We could not read how decisions get made here, and you want them to rest on "
        "data. Ask about the last big one.",
        [
            "Walk me through the last significant decision on this team. What evidence did "
            "it rest on?",
            "What would I need to show to change a decision that has already been made?",
            "How are disagreements settled here: by the numbers, or by whoever owns the "
            "call?",
        ],
    ),
    ("decision", STATUS_UNKNOWN, PREFERS_LESS): (
        "We could not read how decisions get made here, and you trust experience and "
        "judgement. Ask about the last big one.",
        [
            "Walk me through the last significant decision on this team. How was it made?",
            "How much analysis is expected before a call can be made?",
            "When the numbers and someone's experience disagree, which usually wins?",
        ],
    ),
    ("decision", STATUS_MIXED, PREFERS_MORE): (
        "The evidence disagrees on how decisions are made: some parts of the company go by "
        "the numbers, others by judgement. Find out which this team does.",
        [
            "Walk me through the last significant decision on this team and what it rested "
            "on.",
            "What would I need to show to change a decision here?",
            "Is this team more data-led or more judgement-led than the rest of the company?",
        ],
    ),
    ("decision", STATUS_MIXED, PREFERS_LESS): (
        "The evidence disagrees on how decisions are made: some parts of the company go by "
        "judgement, others demand analysis. Find out which this team does.",
        [
            "How much analysis is expected before a decision can be made here?",
            "Tell me about a decision this team made on experience rather than data.",
            "When the numbers and someone's judgement disagree on this team, which wins?",
        ],
    ),
}


def interview_questions(trait: str, status: str, direction: str) -> list[str]:
    """The questions for one cell. KeyError on a cell that does not exist: the service
    only asks for `unknown` and `mixed`, and a misspelt key must not come back empty."""
    return list(_BANK[(trait, status, direction)][1])


def explanation(trait: str, status: str, direction: str) -> str:
    """The one-line plain explanation for one cell."""
    return _BANK[(trait, status, direction)][0]


# ---------------------------------------------------------------------------
# Company size: how much a company-wide read says about one team
# ---------------------------------------------------------------------------

_SIZE_NOTES: dict[Optional[int], str] = {
    None: (
        "We do not know how big this company is. The bigger it is, the less a company-wide "
        "read says about any one team."
    ),
    1: "A handful of people: what we read about the company is close to what any team here "
       "is like.",
    2: "Tens of people: the company-wide read is a fair guide to most teams here.",
    3: "Hundreds of people: teams here can differ from the company-wide read. Ask about "
       "the team.",
    4: "Thousands of people: the company-wide read says less about any one team. Ask "
       "about the team, and the manager.",
    5: "Tens of thousands of people: the company-wide read says little about any one team. "
       "Treat it as background and ask about the team.",
}


def size_note(stage_size: Optional[int]) -> str:
    """The confidence note for a company's `stage_size` band (1..5, or None)."""
    return _SIZE_NOTES[stage_size]


def _check_bank() -> None:
    for trait in TRAIT_KEYS:
        for status in (STATUS_UNKNOWN, STATUS_MIXED):
            for direction in (PREFERS_MORE, PREFERS_LESS):
                text, questions = _BANK[(trait, status, direction)]
                assert text.strip() and 2 <= len(questions) <= 3, (trait, status, direction)


_check_bank()
