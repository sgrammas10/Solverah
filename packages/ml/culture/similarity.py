"""Cosine similarity between a user preference profile and a company culture profile.

The vector is the 7 numeric dimensions shared by both sides:
    empathy, creative_drive, adaptability, futuristic, harmony,
    data_orientation, pace_float

Input formats accepted:
    dict        — user_prefs dict (from synth.py, quiz submission, or DB profile_data)
    CultureValues — company object from company.py

Usage:
    from company_culture_LLM.similarity import profile_cosine_similarity

    score = profile_cosine_similarity(user_dict, company_culture_values)
    # returns float 0.0–1.0, or None if a dimension is missing on either side
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from company import CultureValues, Pace, PACE_TO_FLOAT

DIMS = [
    "empathy",
    "creative_drive",
    "adaptability",
    "futuristic",
    "harmony",
    "data_orientation",
    "pace_float",
]


def _pace_to_float(value: str | float | None) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return PACE_TO_FLOAT[Pace(str(value).strip().lower())]
    except (ValueError, KeyError):
        return None


def _to_vector(profile: dict | CultureValues) -> list[Optional[float]]:
    if isinstance(profile, CultureValues):
        return [
            profile.empathy,
            profile.creative_drive,
            profile.adaptability,
            profile.futuristic,
            profile.harmony,
            profile.data_orientation,
            profile.pace_float,
        ]
    d = profile
    return [
        d.get("empathy"),
        d.get("creative_drive"),
        d.get("adaptability"),
        d.get("futuristic"),
        d.get("harmony"),
        d.get("data_orientation"),
        d.get("pace_float") or _pace_to_float(d.get("pace")),
    ]


def _cosine(a: list[float], b: list[float]) -> float:
    u = np.array(a, dtype=float)
    v = np.array(b, dtype=float)
    mag_u = np.linalg.norm(u)
    mag_v = np.linalg.norm(v)
    # all-zero vector means no signal, treat as no match
    if mag_u == 0.0 or mag_v == 0.0:
        return 0.0
    return float(np.dot(u, v) / (mag_u * mag_v))


def profile_cosine_similarity(
    user: dict | CultureValues,
    company: dict | CultureValues,
) -> Optional[float]:
    """Return cosine similarity [0.0, 1.0] between a user and a company profile.

    Returns None if any of the 7 dimensions is missing on either side.
    """
    u_raw = _to_vector(user)
    c_raw = _to_vector(company)

    missing = [DIMS[i] for i in range(len(DIMS)) if u_raw[i] is None or c_raw[i] is None]
    if missing:
        return None

    return round(_cosine(u_raw, c_raw), 4)  # type: ignore[arg-type]
