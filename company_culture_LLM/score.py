"""Culture fit scoring between a company and a user's culture preferences.

Each of the 8 dimensions is scored independently then combined into a
weighted total. Weights can be overridden per call.

Numeric dimensions (0.0–1.0 scale):
    empathy, creative_drive, adaptability, futuristic, harmony, data_orientation

Categorical dimensions:
    work_environment — comma-separated tags, e.g. "collaborative, high-autonomy"
    pace             — single label, e.g. "fast" | "moderate" | "slow"

User preference schema (dict):
    {
        # numeric — the user's ideal value for each dimension (0.0–1.0)
        "empathy": 0.7,
        "creative_drive": 0.9,
        "adaptability": 0.8,
        "futuristic": 0.85,
        "harmony": 0.6,
        "data_orientation": 0.5,

        # categorical — what the user wants
        "work_environment": ["collaborative", "high-autonomy"],   # list or comma str
        "pace": "fast",
    }

Any key may be omitted; missing dimensions are skipped (not penalised).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from company import CultureValues, Pace, PACE_TO_FLOAT

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

NUMERIC_DIMS = [
    "empathy",
    "creative_drive",
    "adaptability",
    "futuristic",
    "harmony",
    "data_orientation",
]

DEFAULT_WEIGHTS: dict[str, float] = {
    "empathy": 1.0,
    "creative_drive": 1.0,
    "adaptability": 1.0,
    "futuristic": 1.0,
    "harmony": 1.0,
    "data_orientation": 1.0,
    "work_environment": 1.5,  # slightly upweighted — strong signal for day-to-day fit
    "pace": 1.5,
}



# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CultureFitResult:
    total_score: float                    # 0.0–1.0, higher = better fit
    dimension_scores: dict[str, float]    # per-dimension 0.0–1.0
    scored_dimensions: int                # how many dims had data on both sides
    missing_company: list[str] = field(default_factory=list)
    missing_user: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        lines = [f"CultureFitResult(total={self.total_score:.3f})"]
        for dim, s in self.dimension_scores.items():
            lines.append(f"  {dim}: {s:.3f}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_tags(value: str | list[str] | None) -> set[str]:
    """Normalise a comma-string or list of tags to a lowercase set."""
    if value is None:
        return set()
    if isinstance(value, list):
        return {t.strip().lower() for t in value if t.strip()}
    return {t.strip().lower() for t in value.split(",") if t.strip()}


def _score_work_environment(company_val: str | None, user_val) -> Optional[float]:
    """Jaccard similarity between tag sets."""
    company_tags = _parse_tags(company_val)
    user_tags = _parse_tags(user_val)
    if not company_tags or not user_tags:
        return None
    intersection = company_tags & user_tags
    union = company_tags | user_tags
    return len(intersection) / len(union)


def _score_pace(company_val: str | None, user_val: str | None) -> Optional[float]:
    """Numeric proximity score using PACE_TO_FLOAT (0.0–1.0 scale)."""
    if not company_val or not user_val:
        return None
    try:
        c_float = PACE_TO_FLOAT[Pace(company_val.strip().lower())]
        u_float = PACE_TO_FLOAT[Pace(user_val.strip().lower())]
        return _score_numeric(c_float, u_float)
    except (ValueError, KeyError):
        return 1.0 if company_val.strip().lower() == user_val.strip().lower() else 0.0


def _score_numeric(company_val: float | None, user_val: float | None) -> Optional[float]:
    """Linear proximity: 1 - |company - user|."""
    if company_val is None or user_val is None:
        return None
    return max(0.0, 1.0 - abs(company_val - user_val))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def culture_fit_score(
    company_culture: CultureValues,
    user_prefs: dict,
    weights: dict[str, float] | None = None,
) -> CultureFitResult:
    """Score how well a company's culture matches a user's preferences.

    Args:
        company_culture: The company's CultureValues object.
        user_prefs:      Dict of user culture preferences (see module docstring).
        weights:         Optional per-dimension weight overrides.

    Returns:
        CultureFitResult with total_score (0–1) and per-dimension breakdown.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    raw_scores: dict[str, float] = {}
    missing_company: list[str] = []
    missing_user: list[str] = []

    # --- numeric dimensions ---
    for dim in NUMERIC_DIMS:
        company_val = getattr(company_culture, dim, None)
        user_val = user_prefs.get(dim)

        if company_val is None:
            missing_company.append(dim)
            continue
        if user_val is None:
            missing_user.append(dim)
            continue

        s = _score_numeric(float(company_val), float(user_val))
        if s is not None:
            raw_scores[dim] = s

    # --- work_environment ---
    we_score = _score_work_environment(
        company_culture.work_environment,
        user_prefs.get("work_environment"),
    )
    if we_score is None:
        if not company_culture.work_environment:
            missing_company.append("work_environment")
        if not user_prefs.get("work_environment"):
            missing_user.append("work_environment")
    else:
        raw_scores["work_environment"] = we_score

    # --- pace ---
    pace_score = _score_pace(
        company_culture.pace,
        user_prefs.get("pace"),
    )
    if pace_score is None:
        if not company_culture.pace:
            missing_company.append("pace")
        if not user_prefs.get("pace"):
            missing_user.append("pace")
    else:
        raw_scores["pace"] = pace_score

    # --- weighted average ---
    if not raw_scores:
        return CultureFitResult(
            total_score=0.0,
            dimension_scores={},
            scored_dimensions=0,
            missing_company=missing_company,
            missing_user=missing_user,
        )

    total_weight = sum(w.get(dim, 1.0) for dim in raw_scores)
    weighted_sum = sum(score * w.get(dim, 1.0) for dim, score in raw_scores.items())
    total = weighted_sum / total_weight

    return CultureFitResult(
        total_score=round(total, 4),
        dimension_scores={dim: round(s, 4) for dim, s in raw_scores.items()},
        scored_dimensions=len(raw_scores),
        missing_company=missing_company,
        missing_user=missing_user,
    )
