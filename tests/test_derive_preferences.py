"""Tests for work_pulse.derive_preferences.derive_culture_preferences."""

import pytest
from work_pulse.derive_preferences import derive_culture_preferences, _pace_bucket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _answers(option_map: dict) -> list[dict]:
    """Build a WP answer list from {question_number: option_suffix} mapping."""
    return [
        {"question_id": f"wp-q{n}", "option_id": f"wp-q{n}-{s}"}
        for n, s in option_map.items()
    ]


def _all(suffix: str) -> list[dict]:
    return _answers({n: suffix for n in range(1, 13)})


# ---------------------------------------------------------------------------
# All option a — low-friction, fast-paced profile
# ---------------------------------------------------------------------------

def test_all_option_a_pace():
    # q2=a(0.85) + q5=a(0.75) → avg=0.80 → "fast"
    result = derive_culture_preferences(_all("a"))
    assert result["pace"] == "fast"


def test_all_option_a_numeric_dims():
    result = derive_culture_preferences(_all("a"))
    # empathy: (0.40 + 0.40 + 0.45) / 3
    assert result["empathy"] == pytest.approx((0.40 + 0.40 + 0.45) / 3, abs=1e-4)
    # adaptability: (0.80 + 0.80) / 2
    assert result["adaptability"] == pytest.approx(0.80, abs=1e-4)
    # harmony: (0.35 + 0.40) / 2
    assert result["harmony"] == pytest.approx((0.35 + 0.40) / 2, abs=1e-4)
    # data_orientation: (0.60 + 0.55) / 2
    assert result["data_orientation"] == pytest.approx((0.60 + 0.55) / 2, abs=1e-4)
    # creative_drive: (0.60 + 0.55) / 2
    assert result["creative_drive"] == pytest.approx((0.60 + 0.55) / 2, abs=1e-4)
    # futuristic: (0.55 + 0.55) / 2
    assert result["futuristic"] == pytest.approx((0.55 + 0.55) / 2, abs=1e-4)


def test_all_option_a_work_environment():
    # q6=a → "high-autonomy"; q7=a → "high-autonomy", "flexible"; q8=a → "independent"
    # q1=a and q3=a add no tags
    result = derive_culture_preferences(_all("a"))
    assert result["work_environment"] == ["flexible", "high-autonomy", "independent"]


# ---------------------------------------------------------------------------
# All option d — high-friction, slow-paced profile
# ---------------------------------------------------------------------------

def test_all_option_d_pace():
    # q2=d(0.10) + q5=d(0.10) → avg=0.10 → "slow"
    result = derive_culture_preferences(_all("d"))
    assert result["pace"] == "slow"


def test_all_option_d_numeric_dims():
    result = derive_culture_preferences(_all("d"))
    # empathy: (0.90 + 0.80 + 0.70) / 3
    assert result["empathy"] == pytest.approx((0.90 + 0.80 + 0.70) / 3, abs=1e-4)
    # adaptability: (0.20 + 0.40) / 2
    assert result["adaptability"] == pytest.approx((0.20 + 0.40) / 2, abs=1e-4)
    # harmony: (0.75 + 0.75) / 2
    assert result["harmony"] == pytest.approx(0.75, abs=1e-4)
    # data_orientation: (0.85 + 0.80) / 2
    assert result["data_orientation"] == pytest.approx((0.85 + 0.80) / 2, abs=1e-4)
    # creative_drive: (0.85 + 0.85) / 2
    assert result["creative_drive"] == pytest.approx(0.85, abs=1e-4)
    # futuristic: (0.88 + 0.85) / 2
    assert result["futuristic"] == pytest.approx((0.88 + 0.85) / 2, abs=1e-4)


def test_all_option_d_work_environment():
    # q1=d → "structured", "focused"; q3=d → "high-autonomy"; q8=d → "collaborative"
    result = derive_culture_preferences(_all("d"))
    assert result["work_environment"] == [
        "collaborative", "focused", "high-autonomy", "structured"
    ]


# ---------------------------------------------------------------------------
# Mixed set: sustainability (q2) and recognition (q4) friction high;
# autonomy (q6, q7) and collaboration (q8) neutral
# ---------------------------------------------------------------------------

def test_mixed_high_friction_neutral_autonomy():
    answers = _answers({
        1: "b", 2: "c", 3: "b", 4: "c", 5: "b",
        6: "b", 7: "b", 8: "b", 9: "b", 10: "b", 11: "b", 12: "b",
    })
    result = derive_culture_preferences(answers)

    # pace: q2=c(0.30) + q5=b(0.55) → avg=0.425 → "moderate"
    assert result["pace"] == "moderate"

    # empathy: q4=c(0.75) + q2=c(0.65) + q9=b(0.50) → avg
    assert result["empathy"] == pytest.approx((0.75 + 0.65 + 0.50) / 3, abs=1e-4)

    # harmony: q8=b(0.70) + q4=c(0.65) → avg=0.675
    assert result["harmony"] == pytest.approx((0.70 + 0.65) / 2, abs=1e-4)

    # work_environment: q6=b → "collaborative"; q8=b → "collaborative" (deduped)
    assert result["work_environment"] == ["collaborative"]


# ---------------------------------------------------------------------------
# Partial answer set — should not raise; missing questions skipped
# ---------------------------------------------------------------------------

def test_partial_answers_does_not_raise():
    partial = _answers({1: "a", 2: "a", 3: "a", 4: "a", 5: "a", 6: "a"})
    result = derive_culture_preferences(partial)
    assert isinstance(result, dict)


def test_partial_answers_skips_missing_questions():
    partial = _answers({1: "a", 2: "a", 3: "a", 4: "a", 5: "a", 6: "a"})
    result = derive_culture_preferences(partial)
    # q11 and q12 not answered → creative_drive and futuristic omitted
    assert "creative_drive" not in result
    assert "futuristic" not in result
    # pace still resolved (q2 and q5 both present)
    assert result["pace"] == "fast"
    # work_environment only from answered questions
    assert result["work_environment"] == ["high-autonomy"]


def test_empty_answers_returns_empty_dict():
    result = derive_culture_preferences([])
    assert result == {}


# ---------------------------------------------------------------------------
# Pace bucketing at boundary values
# ---------------------------------------------------------------------------

def test_pace_bucket_below_lower_boundary():
    assert _pace_bucket(0.0) == "slow"
    assert _pace_bucket(0.34) == "slow"
    assert _pace_bucket(0.3499) == "slow"


def test_pace_bucket_at_lower_boundary():
    # 0.35 is inclusive for "moderate"
    assert _pace_bucket(0.35) == "moderate"


def test_pace_bucket_mid_range():
    assert _pace_bucket(0.50) == "moderate"


def test_pace_bucket_at_upper_boundary():
    # 0.65 is inclusive for "moderate"
    assert _pace_bucket(0.65) == "moderate"


def test_pace_bucket_above_upper_boundary():
    assert _pace_bucket(0.6501) == "fast"
    assert _pace_bucket(1.0) == "fast"


def test_pace_boundary_at_0_65_via_answers():
    # q2=b(0.55) + q5=a(0.75) → avg=0.65 → "moderate" (≤0.65 boundary)
    answers = _answers({
        1: "a", 2: "b", 3: "a", 4: "a", 5: "a",
        6: "a", 7: "a", 8: "a", 9: "a", 10: "a", 11: "a", 12: "a",
    })
    assert derive_culture_preferences(answers)["pace"] == "moderate"


def test_pace_above_0_65_via_answers():
    # q2=a(0.85) + q5=b(0.55) → avg=0.70 → "fast"
    answers = _answers({
        1: "a", 2: "a", 3: "a", 4: "a", 5: "b",
        6: "a", 7: "a", 8: "a", 9: "a", 10: "a", 11: "a", 12: "a",
    })
    assert derive_culture_preferences(answers)["pace"] == "fast"


# ---------------------------------------------------------------------------
# Work environment tags — deduplication and sorting
# ---------------------------------------------------------------------------

def test_work_environment_deduplication():
    # q6=a and q7=a both add "high-autonomy" → must appear exactly once
    answers = _answers({
        1: "c", 2: "a", 3: "c", 4: "a", 5: "a",
        6: "a", 7: "a", 8: "b", 9: "a", 10: "a", 11: "a", 12: "a",
    })
    result = derive_culture_preferences(answers)
    tags = result["work_environment"]
    assert tags.count("high-autonomy") == 1


def test_work_environment_sorted():
    answers = _answers({
        1: "c", 2: "a", 3: "c", 4: "a", 5: "a",
        6: "a", 7: "a", 8: "b", 9: "a", 10: "a", 11: "a", 12: "a",
    })
    result = derive_culture_preferences(answers)
    tags = result["work_environment"]
    assert tags == sorted(tags)


def test_work_environment_expected_tags():
    # q1=c → "structured"; q3=c → "high-autonomy"; q6=a → "high-autonomy";
    # q7=a → "high-autonomy","flexible"; q8=b → "collaborative"
    answers = _answers({
        1: "c", 2: "a", 3: "c", 4: "a", 5: "a",
        6: "a", 7: "a", 8: "b", 9: "a", 10: "a", 11: "a", 12: "a",
    })
    result = derive_culture_preferences(answers)
    assert set(result["work_environment"]) == {
        "collaborative", "flexible", "high-autonomy", "structured"
    }
