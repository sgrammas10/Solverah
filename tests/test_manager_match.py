"""Tests for manager_match scoring."""
from __future__ import annotations

import pytest

from manager_match.score import score_manager_match


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
#   relationship= mean score of q9-q11 (q9/q11: A=0.25 B=0.80; q10: A=0.70 B=0.30)
#   growth_focus= mean score of q12-q15 (q12/q13/q15: A=0.80 B=0.25; q14: A=0.75 B=0.25)
# ---------------------------------------------------------------------------

# The Autonomist: autonomy > 0.65 AND feedback < 0.45
# autonomy  = (0.80*4)/4 = 0.80       (all B)
# feedback  = (0.25*4)/4 = 0.25       (all B)
# relationship = 0.267                (q9=A, q10=B, q11=A)
# growth    = 0.25                    (all B)
_AUTONOMIST_ANSWERS = _answers(
    "b", "b", "b", "b",   # q1-q4  autonomy  → 0.80
    "b", "b", "b", "b",   # q5-q8  feedback  → 0.25
    "a", "b", "a",        # q9-q11 relationship → (0.25+0.30+0.25)/3 ≈ 0.267
    "b", "b", "b", "b",   # q12-q15 growth   → 0.25
)

# The Operator: autonomy < 0.45 AND feedback > 0.60
# autonomy  = 0.25  (all A)
# feedback  = 0.80  (all A)
_OPERATOR_ANSWERS = _answers(
    "a", "a", "a", "a",   # autonomy → 0.25
    "a", "a", "a", "a",   # feedback → 0.80
    "a", "b", "a",        # relationship → 0.267
    "b", "b", "b", "b",   # growth → 0.25
)

# The Challenger: growth > 0.65 AND autonomy > 0.55
# Must not trigger Autonomist (autonomy > 0.65 AND feedback < 0.45):
#   autonomy = 0.6625 > 0.65, so feedback must be ≥ 0.45 → set feedback = 0.80
# autonomy = (0.80*3 + 0.25)/4 = 0.6625
# feedback = 0.80   (all A) — prevents Autonomist rule
# growth   = (0.80+0.80+0.75+0.80)/4 = 0.7875  (all A)
# relationship = 0.267  (keeps Nurtured from triggering: growth > 0.65 but relationship ≤ 0.60)
_CHALLENGER_ANSWERS = _answers(
    "b", "b", "b", "a",   # autonomy → (0.80+0.80+0.80+0.25)/4 = 0.6625
    "a", "a", "a", "a",   # feedback → 0.80  (blocks Autonomist: feedback not < 0.45)
    "a", "b", "a",        # relationship → 0.267  (blocks Nurtured: not > 0.60)
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
    "b", "a", "b",        # relationship → (0.80+0.70+0.80)/3 ≈ 0.767
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
    "b", "a", "b",        # relationship → 0.767
    "b", "b", "b", "b",   # growth → 0.25
)

# Default (The Operator fallback): none of rules 1–5 trigger
# autonomy = 0.525  (not > 0.65, not < 0.45)
# feedback = 0.525  (not < 0.45, not > 0.60)
# relationship = 0.267  (not > 0.65 and not > 0.60)
# growth   = 0.25   (not > 0.65)
_DEFAULT_ANSWERS = _answers(
    "a", "a", "b", "b",   # autonomy → 0.525
    "a", "a", "b", "b",   # feedback → 0.525
    "a", "b", "a",        # relationship → 0.267
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
