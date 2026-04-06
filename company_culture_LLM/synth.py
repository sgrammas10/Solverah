"""Generate synthetic user preference profiles and company culture profiles for
testing the culture-fit matching pipeline.

Usage:
    python -m company_culture_LLM.synth                     # 50 users, 15 companies
    python -m company_culture_LLM.synth --users 200 --companies 40
    python -m company_culture_LLM.synth --seed 42 --out path/to/dir

Outputs (written to company_culture_LLM/synth_data/ by default):
    users.json      — list of user_prefs dicts, plug directly into culture_fit_score()
    companies.json  — list of CultureValues dicts, construct CultureValues(**row) for each
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from company import Pace, PACE_TO_FLOAT

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUMERIC_DIMS = [
    "empathy",
    "creative_drive",
    "adaptability",
    "futuristic",
    "harmony",
    "data_orientation",
]

WORK_ENV_TAGS = [
    "collaborative",
    "high-autonomy",
    "structured",
    "fast-feedback",
    "mission-driven",
    "results-oriented",
    "flat-hierarchy",
    "process-heavy",
    "meritocratic",
    "inclusive",
]

PACE_VALUES = [p.value for p in Pace]

# ---------------------------------------------------------------------------
# Archetypes — each defines a mean vector; sampled profiles cluster around it.
# This keeps the synthetic data realistic (not pure noise) so the scorer has
# something meaningful to separate.
# ---------------------------------------------------------------------------

USER_ARCHETYPES = [
    # name, {dim: mean}, pace_weights, env_tags (preferred pool)
    ("mission-driven builder",
     {"empathy": 0.75, "creative_drive": 0.85, "adaptability": 0.80,
      "futuristic": 0.90, "harmony": 0.65, "data_orientation": 0.55},
     [0.05, 0.15, 0.45, 0.35],
     ["mission-driven", "high-autonomy", "collaborative", "flat-hierarchy"]),

    ("data-first analyst",
     {"empathy": 0.45, "creative_drive": 0.50, "adaptability": 0.60,
      "futuristic": 0.70, "harmony": 0.55, "data_orientation": 0.95},
     [0.10, 0.30, 0.40, 0.20],
     ["results-oriented", "structured", "meritocratic", "fast-feedback"]),

    ("collaborative people-person",
     {"empathy": 0.90, "creative_drive": 0.65, "adaptability": 0.70,
      "futuristic": 0.55, "harmony": 0.85, "data_orientation": 0.45},
     [0.15, 0.45, 0.30, 0.10],
     ["collaborative", "inclusive", "flat-hierarchy", "mission-driven"]),

    ("structured operator",
     {"empathy": 0.55, "creative_drive": 0.40, "adaptability": 0.45,
      "futuristic": 0.50, "harmony": 0.70, "data_orientation": 0.75},
     [0.20, 0.50, 0.25, 0.05],
     ["structured", "process-heavy", "results-oriented", "meritocratic"]),

    ("creative innovator",
     {"empathy": 0.60, "creative_drive": 0.95, "adaptability": 0.85,
      "futuristic": 0.88, "harmony": 0.60, "data_orientation": 0.40},
     [0.05, 0.10, 0.40, 0.45],
     ["high-autonomy", "flat-hierarchy", "fast-feedback", "mission-driven"]),

    ("balanced generalist",
     {"empathy": 0.65, "creative_drive": 0.65, "adaptability": 0.65,
      "futuristic": 0.65, "harmony": 0.65, "data_orientation": 0.65},
     [0.10, 0.25, 0.40, 0.25],
     ["collaborative", "results-oriented", "high-autonomy", "inclusive"]),
]

COMPANY_ARCHETYPES = [
    ("big tech",
     {"empathy": 0.60, "creative_drive": 0.80, "adaptability": 0.70,
      "futuristic": 0.90, "harmony": 0.65, "data_orientation": 0.90},
     [0.00, 0.05, 0.45, 0.50],
     ["results-oriented", "meritocratic", "high-autonomy", "fast-feedback"]),

    ("enterprise saas",
     {"empathy": 0.65, "creative_drive": 0.60, "adaptability": 0.55,
      "futuristic": 0.65, "harmony": 0.70, "data_orientation": 0.80},
     [0.10, 0.50, 0.35, 0.05],
     ["structured", "process-heavy", "collaborative", "results-oriented"]),

    ("high-growth startup",
     {"empathy": 0.55, "creative_drive": 0.85, "adaptability": 0.90,
      "futuristic": 0.85, "harmony": 0.50, "data_orientation": 0.65},
     [0.00, 0.05, 0.30, 0.65],
     ["high-autonomy", "fast-feedback", "mission-driven", "flat-hierarchy"]),

    ("mission-driven nonprofit / social impact",
     {"empathy": 0.90, "creative_drive": 0.65, "adaptability": 0.70,
      "futuristic": 0.60, "harmony": 0.85, "data_orientation": 0.50},
     [0.15, 0.50, 0.30, 0.05],
     ["mission-driven", "inclusive", "collaborative", "flat-hierarchy"]),

    ("finance / professional services",
     {"empathy": 0.50, "creative_drive": 0.45, "adaptability": 0.50,
      "futuristic": 0.55, "harmony": 0.60, "data_orientation": 0.85},
     [0.05, 0.30, 0.45, 0.20],
     ["structured", "process-heavy", "meritocratic", "results-oriented"]),
]

# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------

def _clamp(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 2)


def _sample_dims(means: dict[str, float], noise: float = 0.15) -> dict[str, float]:
    return {dim: _clamp(random.gauss(means[dim], noise)) for dim in NUMERIC_DIMS}


def _sample_pace(weights: list[float]) -> str:
    return random.choices(PACE_VALUES, weights=weights, k=1)[0]


def _sample_env_tags(pool: list[str], k_range: tuple[int, int] = (1, 3)) -> list[str]:
    k = random.randint(*k_range)
    return random.sample(pool, min(k, len(pool)))


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def _generate_user(archetype: tuple, idx: int) -> dict:
    name, means, pace_weights, env_pool = archetype
    profile = _sample_dims(means)
    pace_str = _sample_pace(pace_weights)
    profile["pace"] = pace_str
    profile["pace_float"] = PACE_TO_FLOAT[Pace(pace_str)]
    profile["work_environment"] = _sample_env_tags(env_pool)
    profile["_archetype"] = name
    profile["_id"] = f"user_{idx:04d}"
    return profile


def _generate_company(archetype: tuple, idx: int) -> dict:
    name, means, pace_weights, env_pool = archetype
    profile = _sample_dims(means)
    pace_str = _sample_pace(pace_weights)
    profile["pace"] = pace_str
    profile["pace_float"] = PACE_TO_FLOAT[Pace(pace_str)]
    profile["work_environment"] = ", ".join(_sample_env_tags(env_pool, k_range=(2, 3)))
    profile["_archetype"] = name
    profile["_id"] = f"company_{idx:04d}"
    return profile


def generate(
    n_users: int = 50,
    n_companies: int = 15,
    seed: int = 0,
) -> tuple[list[dict], list[dict]]:
    random.seed(seed)

    users = [
        _generate_user(USER_ARCHETYPES[i % len(USER_ARCHETYPES)], i)
        for i in range(n_users)
    ]

    companies = [
        _generate_company(COMPANY_ARCHETYPES[i % len(COMPANY_ARCHETYPES)], i)
        for i in range(n_companies)
    ]

    return users, companies


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic culture-fit test data.")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--companies", type=int, default=15)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=str, default=None,
                        help="Output directory (default: company_culture_LLM/synth_data/)")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else Path(__file__).parent / "synth_data"
    out_dir.mkdir(parents=True, exist_ok=True)

    users, companies = generate(args.users, args.companies, args.seed)

    users_path = out_dir / "users.json"
    companies_path = out_dir / "companies.json"

    users_path.write_text(json.dumps(users, indent=2))
    companies_path.write_text(json.dumps(companies, indent=2))

    print(f"Generated {len(users)} users      -> {users_path}")
    print(f"Generated {len(companies)} companies -> {companies_path}")


if __name__ == "__main__":
    main()
