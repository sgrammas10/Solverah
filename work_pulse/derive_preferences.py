"""Translate a completed WorkPulse answer set into culture_preferences."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Contribution tables  (question_id -> option_suffix -> score)
# ---------------------------------------------------------------------------

_PACE: dict[str, dict[str, float]] = {
    "wp-q2": {"a": 0.85, "b": 0.55, "c": 0.30, "d": 0.10},
    "wp-q5": {"a": 0.75, "b": 0.55, "c": 0.30, "d": 0.10},
}

_EMPATHY: dict[str, dict[str, float]] = {
    "wp-q4": {"a": 0.40, "b": 0.55, "c": 0.75, "d": 0.90},
    "wp-q2": {"a": 0.40, "b": 0.50, "c": 0.65, "d": 0.80},
    "wp-q9": {"a": 0.45, "b": 0.50, "c": 0.45, "d": 0.70},
}

_ADAPTABILITY: dict[str, dict[str, float]] = {
    "wp-q1": {"a": 0.80, "b": 0.55, "c": 0.35, "d": 0.20},
    "wp-q9": {"a": 0.80, "b": 0.65, "c": 0.50, "d": 0.40},
}

_HARMONY: dict[str, dict[str, float]] = {
    "wp-q8": {"a": 0.35, "b": 0.70, "c": 0.50, "d": 0.75},
    "wp-q4": {"a": 0.40, "b": 0.50, "c": 0.65, "d": 0.75},
}

_DATA_ORIENTATION: dict[str, dict[str, float]] = {
    "wp-q5":  {"a": 0.60, "b": 0.65, "c": 0.80, "d": 0.85},
    "wp-q10": {"a": 0.55, "b": 0.60, "c": 0.75, "d": 0.80},
}

_CREATIVE_DRIVE: dict[str, dict[str, float]] = {
    "wp-q11": {"a": 0.60, "b": 0.65, "c": 0.78, "d": 0.85},
    "wp-q12": {"a": 0.55, "b": 0.65, "c": 0.80, "d": 0.85},
}

_FUTURISTIC: dict[str, dict[str, float]] = {
    "wp-q12": {"a": 0.55, "b": 0.68, "c": 0.82, "d": 0.88},
    "wp-q11": {"a": 0.55, "b": 0.65, "c": 0.75, "d": 0.85},
}

_NUMERIC_DIMS: list[tuple[str, dict]] = [
    ("empathy", _EMPATHY),
    ("adaptability", _ADAPTABILITY),
    ("harmony", _HARMONY),
    ("data_orientation", _DATA_ORIENTATION),
    ("creative_drive", _CREATIVE_DRIVE),
    ("futuristic", _FUTURISTIC),
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_answer_map(wp_answers: list[dict]) -> dict[str, str]:
    """Map question_id -> option_suffix (last character of option_id)."""
    result: dict[str, str] = {}
    for ans in wp_answers:
        qid = ans.get("question_id", "")
        oid = ans.get("option_id", "")
        if qid and oid:
            result[qid] = oid[-1]
    return result


def _avg_contributions(
    answer_map: dict[str, str],
    table: dict[str, dict[str, float]],
) -> float | None:
    """Average the contributions from answered questions present in *table*."""
    contributions = []
    for qid, opts in table.items():
        suffix = answer_map.get(qid)
        if suffix in opts:
            contributions.append(opts[suffix])
    return sum(contributions) / len(contributions) if contributions else None


def _pace_bucket(avg: float) -> str:
    if avg < 0.35:
        return "slow"
    if avg <= 0.65:
        return "moderate"
    return "fast"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def derive_culture_preferences(wp_answers: list[dict]) -> dict:
    """
    Translate a completed WorkPulse answer set into a culture_preferences dict
    compatible with company_culture_LLM/score.py.

    Args:
        wp_answers: list of {"question_id": "wp-q1", "option_id": "wp-q1-c"}

    Returns:
        culture_preferences dict ready for culture_fit_score()
    """
    answer_map = _build_answer_map(wp_answers)
    prefs: dict = {}

    # --- Pace ---
    pace_avg = _avg_contributions(answer_map, _PACE)
    if pace_avg is not None:
        prefs["pace"] = _pace_bucket(pace_avg)

    # --- Numeric dimensions ---
    for dim, table in _NUMERIC_DIMS:
        val = _avg_contributions(answer_map, table)
        if val is not None:
            prefs[dim] = round(val, 4)

    # --- Work environment tags ---
    tags: set[str] = set()
    q1 = answer_map.get("wp-q1")
    q3 = answer_map.get("wp-q3")
    q6 = answer_map.get("wp-q6")
    q7 = answer_map.get("wp-q7")
    q8 = answer_map.get("wp-q8")

    if q1 in {"c", "d"}:
        tags.add("structured")
    if q1 == "d":
        tags.add("focused")
    if q6 == "a":
        tags.add("high-autonomy")
    if q6 == "b":
        tags.add("collaborative")
    if q7 == "a":
        tags.add("high-autonomy")
        tags.add("flexible")
    if q8 == "a":
        tags.add("independent")
    if q8 in {"b", "d"}:
        tags.add("collaborative")
    if q3 in {"c", "d"}:
        tags.add("high-autonomy")

    if tags:
        prefs["work_environment"] = sorted(tags)

    return prefs
