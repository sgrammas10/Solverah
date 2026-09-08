"""Tests for the manager-profile instrument (observational, C-1)."""
from __future__ import annotations

from collections import Counter

import pytest

from manager_match.manager_profile import (
    EXPECTED_ANSWER_COUNT,
    MANAGER_PROFILE_QUESTIONS,
    score_manager_profile,
)
from manager_match.questions import QUESTIONS


def _answers(*choices: str) -> list[dict]:
    """Build a full answer list from a sequence of 'a'/'b' choices (q1..qN)."""
    assert len(choices) == EXPECTED_ANSWER_COUNT
    return [
        {"question_id": f"mp-q{i + 1}", "choice": c}
        for i, c in enumerate(choices)
    ]


_ALL_A = _answers(*(["a"] * EXPECTED_ANSWER_COUNT))
_ALL_B = _answers(*(["b"] * EXPECTED_ANSWER_COUNT))

# A manager read as high on every dimension: pick the 0.80 pole of each item.
# Position varies by item precisely because the key is positionally balanced.
_ALL_HIGH = _answers(
    "b", "a", "b", "a",   # autonomy
    "b", "a", "a", "b",   # feedback_style
    "b", "a", "b",        # relationship
    "b", "a", "a", "b",   # growth_focus
)
_ALL_LOW = _answers(*("b" if c["choice"] == "a" else "a" for c in _ALL_HIGH))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_returns_one_score_per_dimension() -> None:
    result = score_manager_profile(_ALL_HIGH)

    assert set(result) == {"dimension_scores"}
    assert set(result["dimension_scores"]) == {
        "autonomy", "feedback_style", "relationship", "growth_focus",
    }


def test_all_high_poles_score_at_the_top_anchor() -> None:
    scores = score_manager_profile(_ALL_HIGH)["dimension_scores"]

    for dim, val in scores.items():
        assert val == pytest.approx(0.80), f"{dim}={val}"


def test_all_low_poles_score_at_the_bottom_anchor() -> None:
    scores = score_manager_profile(_ALL_LOW)["dimension_scores"]

    for dim, val in scores.items():
        assert val == pytest.approx(0.25), f"{dim}={val}"


# ---------------------------------------------------------------------------
# Per-dimension math
# ---------------------------------------------------------------------------

def test_dimension_scores_are_the_mean_of_their_own_items() -> None:
    # autonomy: q1=b(0.80) q2=b(0.25) q3=a(0.25) q4=a(0.80)  -> 0.525
    # feedback: q5=a(0.25) q6=a(0.80) q7=b(0.25) q8=b(0.80)  -> 0.525
    # relationship: q9=b(0.80) q10=a(0.80) q11=b(0.80)       -> 0.80
    # growth: q12=a(0.25) q13=b(0.25) q14=b(0.25) q15=a(0.25)-> 0.25
    scores = score_manager_profile(_answers(
        "b", "b", "a", "a",
        "a", "a", "b", "b",
        "b", "a", "b",
        "a", "b", "b", "a",
    ))["dimension_scores"]

    assert scores["autonomy"] == pytest.approx(0.525)
    assert scores["feedback_style"] == pytest.approx(0.525)
    assert scores["relationship"] == pytest.approx(0.80)
    assert scores["growth_focus"] == pytest.approx(0.25)


def test_one_dimension_moves_independently_of_the_others() -> None:
    base = score_manager_profile(_ALL_HIGH)["dimension_scores"]

    # Flip a single autonomy item (mp-q1, high pole = b) to its low pole.
    flipped = list(_ALL_HIGH)
    flipped[0] = {"question_id": "mp-q1", "choice": "a"}
    moved = score_manager_profile(flipped)["dimension_scores"]

    assert moved["autonomy"] == pytest.approx((0.25 + 0.80 * 3) / 4)
    for dim in ("feedback_style", "relationship", "growth_focus"):
        assert moved[dim] == pytest.approx(base[dim])


@pytest.mark.parametrize("answers", [_ALL_A, _ALL_B, _ALL_HIGH, _ALL_LOW])
def test_dimension_scores_in_range(answers: list[dict]) -> None:
    for dim, val in score_manager_profile(answers)["dimension_scores"].items():
        assert 0.0 <= val <= 1.0, f"{dim}={val} out of [0, 1]"


# ---------------------------------------------------------------------------
# Straight-lining: the payoff of the balanced key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("answers, label", [(_ALL_A, "all-A"), (_ALL_B, "all-B")])
def test_straight_lining_cannot_produce_an_extreme_profile(
    answers: list[dict], label: str
) -> None:
    """Picking one position throughout must land mid-scale, not at an anchor."""
    for dim, val in score_manager_profile(answers)["dimension_scores"].items():
        assert 0.40 <= val <= 0.65, f"{label} {dim}={val} reads as a real signal"


# ---------------------------------------------------------------------------
# Edge cases / validation
# ---------------------------------------------------------------------------

def test_missing_answer_raises() -> None:
    short = _ALL_HIGH[:-1]
    with pytest.raises(ValueError, match=str(EXPECTED_ANSWER_COUNT)):
        score_manager_profile(short)


def test_duplicate_answer_standing_in_for_a_missing_one_raises() -> None:
    """Right length, wrong coverage — must not silently score 14 items."""
    dupe = [dict(a) for a in _ALL_HIGH]
    dupe[-1]["question_id"] = dupe[0]["question_id"]
    with pytest.raises(ValueError, match="Duplicate"):
        score_manager_profile(dupe)


def test_unknown_question_id_raises() -> None:
    bogus = [dict(a) for a in _ALL_HIGH]
    bogus[2]["question_id"] = "mm-q3"  # the *other* instrument's id
    with pytest.raises(ValueError, match="Unknown question_id"):
        score_manager_profile(bogus)


@pytest.mark.parametrize("choice", ["c", "A", "", None])
def test_invalid_choice_raises(choice: object) -> None:
    bad = [dict(a) for a in _ALL_HIGH]
    bad[3]["choice"] = choice
    with pytest.raises(ValueError, match="choice"):
        score_manager_profile(bad)


def test_empty_answers_raises() -> None:
    with pytest.raises(ValueError):
        score_manager_profile([])


# ---------------------------------------------------------------------------
# Structural: positional key balance (the v1 core items' failure mode)
# ---------------------------------------------------------------------------

def _high_pole_position(question: dict) -> str:
    return "a" if question["score_a"] > question["score_b"] else "b"


def test_high_pole_position_is_balanced_overall() -> None:
    positions = Counter(_high_pole_position(q) for q in MANAGER_PROFILE_QUESTIONS)

    assert abs(positions["a"] - positions["b"]) <= 1, (
        f"high pole sits in one position too often: {dict(positions)}"
    )


def test_high_pole_position_is_balanced_within_every_dimension() -> None:
    by_dimension: dict[str, Counter] = {}
    for q in MANAGER_PROFILE_QUESTIONS:
        by_dimension.setdefault(q["dimension"], Counter())[_high_pole_position(q)] += 1

    for dim, positions in by_dimension.items():
        assert abs(positions["a"] - positions["b"]) <= 1, (
            f"{dim} keys its high pole to one position: {dict(positions)}"
        )


def test_every_item_discriminates() -> None:
    for q in MANAGER_PROFILE_QUESTIONS:
        assert q["score_a"] != q["score_b"], f"{q['question_id']} scores both poles alike"
        assert 0.0 <= q["score_a"] <= 1.0 and 0.0 <= q["score_b"] <= 1.0


def test_item_ids_are_unique_and_sequential() -> None:
    ids = [q["question_id"] for q in MANAGER_PROFILE_QUESTIONS]

    assert ids == [f"mp-q{i + 1}" for i in range(EXPECTED_ANSWER_COUNT)]


def test_item_count_is_in_the_specified_range() -> None:
    assert 12 <= EXPECTED_ANSWER_COUNT <= 15


def test_dimensions_match_manager_match_exactly() -> None:
    """C-2 diffs the two instruments per dimension; the keys must line up."""
    assert (
        {q["dimension"] for q in MANAGER_PROFILE_QUESTIONS}
        == {q["dimension"] for q in QUESTIONS}
    )


def test_every_item_has_two_distinct_non_empty_options() -> None:
    for q in MANAGER_PROFILE_QUESTIONS:
        assert q["option_a_text"].strip()
        assert q["option_b_text"].strip()
        assert q["option_a_text"] != q["option_b_text"]
