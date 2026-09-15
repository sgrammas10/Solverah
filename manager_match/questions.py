from __future__ import annotations
from typing import TypedDict


class Question(TypedDict):
    question_id: str
    option_a_text: str
    option_b_text: str
    dimension: str
    score_a: float
    score_b: float


QUESTIONS: list[Question] = [
    {
        "question_id": "mm-q1",
        "option_a_text": "Your manager provides a detailed brief for every task, including how to approach it.",
        "option_b_text": "Your manager gives you the goal and leaves the approach entirely up to you.",
        "dimension": "autonomy",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mm-q2",
        "option_a_text": "Your manager checks in with you daily to monitor progress.",
        "option_b_text": "Your manager trusts you to flag them when you need input.",
        "dimension": "autonomy",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mm-q3",
        "option_a_text": "When you’re stuck, you prefer your manager to guide you step-by-step to the answer.",
        "option_b_text": "When you’re stuck, you prefer to solve it yourself and report back with the outcome.",
        "dimension": "autonomy",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mm-q4",
        "option_a_text": "You prefer knowing exactly what success looks like before you start a task.",
        "option_b_text": "You prefer to define success as you go, based on what you discover.",
        "dimension": "autonomy",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mm-q5",
        "option_a_text": "You want feedback delivered as soon as your manager notices something, even mid-task.",
        "option_b_text": "You prefer feedback bundled into scheduled check-ins – not delivered in the moment.",
        "dimension": "feedback_style",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mm-q6",
        "option_a_text": "Direct, blunt feedback – even if it stings – is more useful to you than softened feedback.",
        "option_b_text": "You need feedback framed constructively before you can absorb and act on it.",
        "dimension": "feedback_style",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mm-q7",
        "option_a_text": "You want your manager to review your work before you consider it done.",
        "option_b_text": "You consider your work done when you’re satisfied with it, regardless of manager review.",
        "dimension": "feedback_style",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mm-q8",
        "option_a_text": "Frequent positive reinforcement from your manager meaningfully affects your motivation.",
        "option_b_text": "Your own judgment of your work is what motivates you – you don’t need external validation.",
        "dimension": "feedback_style",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mm-q9",
        "option_a_text": "You prefer a manager relationship that stays professional – minimal personal overlap.",
        "option_b_text": "You perform better when your manager knows you as a person, not just a direct report.",
        "dimension": "relationship",
        "score_a": 0.25,
        "score_b": 0.80,
    },
    {
        "question_id": "mm-q10",
        "option_a_text": "You’d rather have a manager who advocates strongly for your interests in the org.",
        "option_b_text": "You’d rather have a manager who holds you to high standards without softening expectations.",
        "dimension": "relationship",
        "score_a": 0.70,
        "score_b": 0.30,
    },
    {
        "question_id": "mm-q11",
        "option_a_text": "A manager who is available and accessible gives you confidence.",
        "option_b_text": "A manager who trusts you enough to be hard to reach gives you confidence.",
        "dimension": "relationship",
        # Corrected 2026-09-10 -- MANAGER_PROFILE_ITEMS_BIAS_REVIEW.md, Finding 7.
        # This item keyed `relationship` backwards: "hard to reach" scored 0.80
        # while mm-q9's "knows you as a person" and mm-q10's "advocates strongly"
        # also score high, so one of the scale's three items ran against the other
        # two and depressed a genuinely high relational need by up to 0.183.
        # Availability is the closeness pole and now scores with them.
        #
        # Sittings stored under the old key are re-derived from the answers they
        # kept, by `Scripts/backfill_manager_match_scoring_key.py`;
        # `score.SCORING_KEY` is what tells the two eras apart on a stored row.
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mm-q12",
        "option_a_text": "You want your manager to actively plan your development – setting learning goals with you.",
        "option_b_text": "You take full ownership of your own development and don’t need your manager’s direction.",
        "dimension": "growth_focus",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mm-q13",
        "option_a_text": "Regular career conversations with your manager make you more invested in your work.",
        "option_b_text": "Career conversations feel like overhead – you’d rather focus on doing excellent work.",
        "dimension": "growth_focus",
        "score_a": 0.80,
        "score_b": 0.25,
    },
    {
        "question_id": "mm-q14",
        "option_a_text": "Being pushed outside your comfort zone by your manager energizes you.",
        "option_b_text": "You do your best work in areas where you already have confidence and established skills.",
        "dimension": "growth_focus",
        "score_a": 0.75,
        "score_b": 0.25,
    },
    {
        "question_id": "mm-q15",
        "option_a_text": "You want a manager who challenges your ideas and pushes back when they disagree.",
        "option_b_text": "You want a manager who supports your ideas and helps you execute them.",
        "dimension": "growth_focus",
        "score_a": 0.80,
        "score_b": 0.25,
    },
]
