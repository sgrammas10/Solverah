"""Tests for manager_match scoring."""
from __future__ import annotations

import pytest

from manager_match.questions import QUESTIONS
from manager_match.score import SCORING_KEY, score_manager_match


def _answers(*choices: str) -> list[dict]:
    """Build 15-answer list from a sequence of 'a'/'b' choices (q1..q15)."""
    assert len(choices) == 15
    return [
        {"question_id": f"mm-q{i + 1}", "choice": c}
        for i, c in enumerate(choices)
    ]


# ---------------------------------------------------------------------------
# Archetype fixtures
# Dimension means for each fixture:
#   autonomy    = mean score of q1-q4  (A=0.25, B=0.80)
#   feedback    = mean score of q5-q8  (A=0.80, B=0.25)
#   relationship= mean score of q9-q11 (q9: A=0.25 B=0.80; q10: A=0.70 B=0.30;
#                                       q11: A=0.80 B=0.25)
#
# q11's anchors were the other way round until 2026-09-10, when Finding 7 of
# MANAGER_PROFILE_ITEMS_BIAS_REVIEW.md was corrected: it keyed *distance* high
# while q9 and q10 key closeness and advocacy high. The Nurtured and Collaborator
# fixtures below moved with it -- under the old key their q11 choice pulled
# `relationship` down, and both now need q11's "available and accessible" pole to
# clear their thresholds. See test_relationship_items_all_key_closeness_high.
#   growth_focus= mean score of q12-q15 (q12/q13/q15: A=0.80 B=0.25; q14: A=0.75 B=0.25)
# ---------------------------------------------------------------------------

# The Autonomist: autonomy > 0.65 AND feedback < 0.45
# autonomy  = (0.80*4)/4 = 0.80       (all B)
# feedback  = (0.25*4)/4 = 0.25       (all B)
# relationship = 0.45                 (q9=A, q10=B, q11=A)
# growth    = 0.25                    (all B)
_AUTONOMIST_ANSWERS = _answers(
    "b", "b", "b", "b",   # q1-q4  autonomy  → 0.80
    "b", "b", "b", "b",   # q5-q8  feedback  → 0.25
    "a", "b", "a",        # q9-q11 relationship → (0.25+0.30+0.80)/3 = 0.45
    "b", "b", "b", "b",   # q12-q15 growth   → 0.25
)

# The Operator: autonomy < 0.45 AND feedback > 0.60
# autonomy  = 0.25  (all A)
# feedback  = 0.80  (all A)
_OPERATOR_ANSWERS = _answers(
    "a", "a", "a", "a",   # autonomy → 0.25
    "a", "a", "a", "a",   # feedback → 0.80
    "a", "b", "a",        # relationship → 0.45
    "b", "b", "b", "b",   # growth → 0.25
)

# The Challenger: growth > 0.65 AND autonomy > 0.55
# Must not trigger Autonomist (autonomy > 0.65 AND feedback < 0.45):
#   autonomy = 0.6625 > 0.65, so feedback must be ≥ 0.45 → set feedback = 0.80
# autonomy = (0.80*3 + 0.25)/4 = 0.6625
# feedback = 0.80   (all A) — prevents Autonomist rule
# growth   = (0.80+0.80+0.75+0.80)/4 = 0.7875  (all A)
# relationship = 0.45  (keeps Nurtured from triggering: growth > 0.65 but relationship ≤ 0.60)
_CHALLENGER_ANSWERS = _answers(
    "b", "b", "b", "a",   # autonomy → (0.80+0.80+0.80+0.25)/4 = 0.6625
    "a", "a", "a", "a",   # feedback → 0.80  (blocks Autonomist: feedback not < 0.45)
    "a", "b", "a",        # relationship → 0.45  (blocks Nurtured: not > 0.60)
    "a", "a", "a", "a",   # growth → 0.7875
)

# The Nurtured: growth > 0.65 AND relationship > 0.60
# Must not trigger rules 1–3:
#   Autonomist: autonomy ≤ 0.65 or feedback ≥ 0.45
#   Operator:   autonomy ≥ 0.45 or feedback ≤ 0.60
#   Challenger: autonomy ≤ 0.55  (so Challenger's autonomy > 0.55 fails)
# autonomy = (0.25+0.25+0.80+0.80)/4 = 0.525  (blocks all three above)
# feedback = (0.80+0.80+0.25+0.25)/4 = 0.525
# relationship = (0.80+0.70+0.80)/3 ≈ 0.767  (> 0.60 ✓, and > 0.65 but Nurtured checked before Collaborator)
# growth   = 0.7875  (all A)
_NURTURED_ANSWERS = _answers(
    "a", "a", "b", "b",   # autonomy → 0.525
    "a", "a", "b", "b",   # feedback → 0.525
    "b", "a", "a",        # relationship → (0.80+0.70+0.80)/3 ≈ 0.767
    "a", "a", "a", "a",   # growth → 0.7875
)

# The Collaborator: relationship > 0.65  (rules 1–4 all fail)
# autonomy = 0.525  (avoids Autonomist low-autonomy and Operator high-autonomy)
# feedback = 0.525  (avoids Autonomist low-feedback and Operator high-feedback)
# growth   = 0.25   (blocks Challenger and Nurtured: growth not > 0.65)
# relationship = 0.767  (> 0.65 ✓)
_COLLABORATOR_ANSWERS = _answers(
    "a", "a", "b", "b",   # autonomy → 0.525
    "a", "a", "b", "b",   # feedback → 0.525
    "b", "a", "a",        # relationship → 0.767
    "b", "b", "b", "b",   # growth → 0.25
)

# Default (The Operator fallback): none of rules 1–5 trigger
# autonomy = 0.525  (not > 0.65, not < 0.45)
# feedback = 0.525  (not < 0.45, not > 0.60)
# relationship = 0.45  (not > 0.65 and not > 0.60)
# growth   = 0.25   (not > 0.65)
_DEFAULT_ANSWERS = _answers(
    "a", "a", "b", "b",   # autonomy → 0.525
    "a", "a", "b", "b",   # feedback → 0.525
    "a", "b", "a",        # relationship → 0.45
    "b", "b", "b", "b",   # growth → 0.25
)


# ---------------------------------------------------------------------------
# Archetype tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("answers, expected_archetype", [
    (_AUTONOMIST_ANSWERS,  "The Autonomist"),
    (_OPERATOR_ANSWERS,    "The Operator"),
    (_CHALLENGER_ANSWERS,  "The Challenger"),
    (_NURTURED_ANSWERS,    "The Nurtured"),
    (_COLLABORATOR_ANSWERS, "The Collaborator"),
    (_DEFAULT_ANSWERS,     "The Operator"),
])
def test_archetype(answers: list[dict], expected_archetype: str) -> None:
    result = score_manager_match(answers)
    assert result["archetype"] == expected_archetype


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

def test_wrong_answer_count_raises() -> None:
    fourteen = [{"question_id": f"mm-q{i + 1}", "choice": "a"} for i in range(14)]
    with pytest.raises(ValueError, match="15"):
        score_manager_match(fourteen)


def test_invalid_choice_raises() -> None:
    bad = [{"question_id": f"mm-q{i + 1}", "choice": "a"} for i in range(15)]
    bad[3]["choice"] = "c"
    with pytest.raises(ValueError, match="choice"):
        score_manager_match(bad)


# ---------------------------------------------------------------------------
# Dimension score bounds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("answers", [
    _AUTONOMIST_ANSWERS,
    _OPERATOR_ANSWERS,
    _CHALLENGER_ANSWERS,
    _NURTURED_ANSWERS,
    _COLLABORATOR_ANSWERS,
    _DEFAULT_ANSWERS,
])
def test_dimension_scores_in_range(answers: list[dict]) -> None:
    result = score_manager_match(answers)
    for dim, val in result["dimension_scores"].items():
        assert 0.0 <= val <= 1.0, f"{dim}={val} out of [0, 1]"


# ---------------------------------------------------------------------------
# Keying: the Finding 7 regression
# ---------------------------------------------------------------------------

#: The closer of the two management relationships each `relationship` item
#: offers, identified by a fragment of the option's own text rather than by an
#: 'a'/'b' that would have to be re-checked every time an item is reworded.
_CLOSER_POLE_TEXT = {
    "mm-q9": "knows you as a person",
    "mm-q10": "advocates strongly for your interests",
    "mm-q11": "available and accessible",
}


def _choice_containing(question: dict, fragment: str) -> str:
    if fragment in question["option_a_text"]:
        return "a"
    assert fragment in question["option_b_text"], (
        f"{question['question_id']} no longer offers {fragment!r} in either option"
    )
    return "b"


def test_relationship_items_all_key_closeness_high() -> None:
    """No item on `relationship` may pull against the other two (Finding 7).

    All three name a closer and a more distant management relationship. Choosing
    the closer one has to raise the dimension on every one of them, or the mean
    of the three is not measuring one construct.

    Until 2026-09-10 `mm-q11` lowered it: "trusts you enough to be hard to reach"
    scored 0.80 while `mm-q9`'s "knows you as a person" and `mm-q10`'s "advocates
    strongly" also scored high. A respondent whose relational need was genuinely
    high and who valued availability had it read as distance.
    """
    by_id = {q["question_id"]: q for q in QUESTIONS}
    relationship_ids = [
        q["question_id"] for q in QUESTIONS if q["dimension"] == "relationship"
    ]
    assert set(relationship_ids) == set(_CLOSER_POLE_TEXT), (
        "the relationship scale gained or lost an item; this test's poles need a revisit"
    )

    distant = {
        qid: ("b" if _choice_containing(by_id[qid], _CLOSER_POLE_TEXT[qid]) == "a" else "a")
        for qid in relationship_ids
    }

    def sitting(overrides: dict[str, str]) -> list[dict]:
        return [
            {
                "question_id": q["question_id"],
                "choice": overrides.get(
                    q["question_id"], distant.get(q["question_id"], "a")
                ),
            }
            for q in QUESTIONS
        ]

    floor = score_manager_match(sitting({}))["dimension_scores"]["relationship"]

    for qid in relationship_ids:
        closer = _choice_containing(by_id[qid], _CLOSER_POLE_TEXT[qid])
        moved = score_manager_match(sitting({qid: closer}))["dimension_scores"]["relationship"]
        assert moved > floor, (
            f"{qid}: choosing {_CLOSER_POLE_TEXT[qid]!r} moved relationship "
            f"{moved:.4f} vs {floor:.4f} -- it keys against the rest of the scale"
        )


def test_every_result_is_stamped_with_the_scoring_key() -> None:
    """A stored `relationship` number has to say which key produced it.

    The stamp is what the backfill reads to tell a re-derived row from one still
    scored under the pre-2026-09-10 key, where the absence of this field is the
    only marker a v1 row has.
    """
    assert score_manager_match(_DEFAULT_ANSWERS)["scoring_key"] == SCORING_KEY
