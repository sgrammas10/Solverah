"""Manager-profile instrument: observational items about the user's actual manager.

Companion to `questions.py` / `score.py`. Where ManagerMatch asks what the user
*needs* from a manager, this asks what their current manager observably *does* —
same four dimensions, same 0-1 scale, so the two are directly comparable when the
Decoder diffs them (BUILD_PLAN C-2).

Item design rules (see MANAGER_PROFILE_ITEMS_BIAS_REVIEW.md):
  * Every item is behavioral and observational — "your manager does X" vs
    "your manager does Y" — never how the user feels about it, never a proxy for
    "is your manager good".
  * Both poles are legitimate management styles. An item where one pole is the
    obviously-correct answer is cut, not softened.
  * The high-scoring pole is balanced across option A and option B, per dimension
    and overall, so a respondent who straight-lines one position cannot produce a
    systematically high or low profile.

Scoring anchors are uniform (0.80 / 0.25) on purpose: no item is treated as a
stronger indicator than any other, matching the flat-weight stance the interim
gap engine takes while `priors.yaml` is still placeholder.
"""
from __future__ import annotations

from typing import TypedDict


class ManagerProfileQuestion(TypedDict):
    question_id: str
    option_a_text: str
    option_b_text: str
    dimension: str
    score_a: float
    score_b: float


# High pole per dimension (the 0.80 end):
#   autonomy      — manager grants latitude over goal, method and timing
#   feedback_style— manager gives frequent, immediate, unsoftened feedback
#   relationship  — manager engages with and advocates for the person, not just the output
#   growth_focus  — manager invests in what the user becomes, not only what they deliver
MANAGER_PROFILE_QUESTIONS: list[ManagerProfileQuestion] = [
    {
        "question_id": "mp-q1",
        "option_a_text": "Your manager sets both the goal and the method for your work.",
        "option_b_text": "Your manager sets the goal and leaves the method to you.",
        "dimension": "autonomy",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mp-q2",
        "option_a_text": "Your manager hears how you handled a problem after you’ve handled it.",
        "option_b_text": "Your manager works through a problem with you while you’re still in it.",
        "dimension": "autonomy",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mp-q3",
        "option_a_text": "Your manager signs off on your decisions before you act on them.",
        "option_b_text": "Your manager expects you to make the call and tell them afterwards.",
        "dimension": "autonomy",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mp-q4",
        "option_a_text": "Your manager tells you what has to be done by when, and leaves the order to you.",
        "option_b_text": "Your manager tells you what to do in what order as the work goes along.",
        "dimension": "autonomy",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mp-q5",
        "option_a_text": "Your manager saves feedback for scheduled reviews or set check-ins.",
        "option_b_text": "Your manager tells you the moment they notice something, mid-task if need be.",
        "dimension": "feedback_style",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mp-q6",
        "option_a_text": "Your manager states the problem with your work plainly, without cushioning it.",
        "option_b_text": "Your manager frames criticism carefully, and leads with what worked.",
        "dimension": "feedback_style",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mp-q7",
        "option_a_text": "Your manager comments on your work often — small things as well as large.",
        "option_b_text": "Your manager comments on your work rarely, and only when something matters a lot.",
        "dimension": "feedback_style",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mp-q8",
        "option_a_text": "Your manager speaks up when something needs to change, and otherwise leaves you to it.",
        "option_b_text": "Your manager tells you where you stand either way — when the work is on track and when it isn’t.",
        "dimension": "feedback_style",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mp-q9",
        "option_a_text": "Your manager keeps out of your life outside work unless you bring it up.",
        "option_b_text": "Your manager asks about things outside the work — how you’re doing generally.",
        "dimension": "relationship",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mp-q10",
        "option_a_text": "Your manager speaks up for you when decisions about you get made without you there.",
        "option_b_text": "Your manager expects your record to speak for you in those decisions.",
        "dimension": "relationship",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mp-q11",
        "option_a_text": "Your manager runs things the same way with everyone they manage.",
        "option_b_text": "Your manager adapts how they work with you to suit you specifically.",
        "dimension": "relationship",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mp-q12",
        "option_a_text": "Your manager talks with you about the job you’re doing now.",
        "option_b_text": "Your manager talks with you about where you’re heading after this job.",
        "dimension": "growth_focus",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mp-q13",
        "option_a_text": "Your manager puts you on work you haven’t done before.",
        "option_b_text": "Your manager puts you on work you’re already good at.",
        "dimension": "growth_focus",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mp-q14",
        "option_a_text": "Your manager pushes back on your ideas and makes you defend them.",
        "option_b_text": "Your manager takes your ideas as given and helps you get them done.",
        "dimension": "growth_focus",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mp-q15",
        "option_a_text": "Your manager leaves your learning to you and manages the work in front of you.",
        "option_b_text": "Your manager sets goals with you for what you’ll learn next, and asks about them later.",
        "dimension": "growth_focus",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mp-q16",
        "option_a_text": "Your manager keeps track of how you’re doing personally, whether or not you raise it.",
        "option_b_text": "Your manager takes you at your word about how you’re doing.",
        "dimension": "relationship",
        "score_a": 0.80,
        "score_b": 0.25,
    },
]

EXPECTED_ANSWER_COUNT = len(MANAGER_PROFILE_QUESTIONS)

#: Which item set produced a stored sitting's `answers` (BUILD_PLAN C-3's
#: `manager_profiles.version`). Bump whenever an item is added, removed, or
#: reworded -- the same discipline `assessment_service.CLIENT_FORM_VERSION`
#: applies to the other client-rendered instruments.
INSTRUMENT_VERSION = "v1"

#: Which scoring key produced a stored sitting's `dimension_scores`
#: (BUILD_PLAN C-3's `manager_profiles.scoring_key`). Mirrors
#: `manager_match.score.SCORING_KEY` -- see that module for why the mm-q11
#: episode makes this a required, explicitly-stamped marker rather than an
#: implicit one. Not folded into `score_manager_profile`'s own return value:
#: that shape is pinned by `test_returns_one_score_per_dimension`, so the
#: storage layer stamps this alongside the scores instead of the scorer
#: mutating what it hands back.
#:
#: Bump whenever an item's anchors or dimension change.
SCORING_KEY = "mp-v1"

_SCORE_LOOKUP: dict[str, dict[str, float]] = {
    q["question_id"]: {"a": q["score_a"], "b": q["score_b"]}
    for q in MANAGER_PROFILE_QUESTIONS
}

_DIMENSION_QUESTIONS: dict[str, list[str]] = {}
for _q in MANAGER_PROFILE_QUESTIONS:
    _DIMENSION_QUESTIONS.setdefault(_q["dimension"], []).append(_q["question_id"])

_VALID_CHOICES = {"a", "b"}


def _validate(answers: list[dict]) -> None:
    """Reject anything that would make the dimension means meaningless."""
    if len(answers) != EXPECTED_ANSWER_COUNT:
        raise ValueError(f"Expected {EXPECTED_ANSWER_COUNT} answers, got {len(answers)}")

    seen: set[str] = set()
    for ans in answers:
        qid = ans.get("question_id")
        if qid not in _SCORE_LOOKUP:
            raise ValueError(f"Unknown question_id '{qid}'")
        if qid in seen:
            raise ValueError(f"Duplicate answer for question '{qid}'")
        seen.add(qid)
        if ans.get("choice") not in _VALID_CHOICES:
            raise ValueError(
                f"Invalid choice '{ans.get('choice')}' for question '{qid}'; must be 'a' or 'b'"
            )
    # A full-length run of unique, known ids covers every question, so a missing
    # answer is already impossible by the time we get here.


def score_manager_profile(answers: list[dict]) -> dict:
    """Score an observed-manager sitting into per-dimension means in [0, 1].

    Pure: no I/O, no Flask, no persistence. Mirrors `score.score_manager_match`,
    minus the archetype — the manager side is read as a profile and diffed
    against the user's ManagerMatch needs, not labelled.
    """
    _validate(answers)

    scores_by_question: dict[str, float] = {
        ans["question_id"]: _SCORE_LOOKUP[ans["question_id"]][ans["choice"]]
        for ans in answers
    }

    dimension_scores: dict[str, float] = {
        dim: sum(scores_by_question[qid] for qid in qids) / len(qids)
        for dim, qids in _DIMENSION_QUESTIONS.items()
    }

    return {"dimension_scores": dimension_scores}
