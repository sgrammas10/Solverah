"""Manager Decoder: diff manager *needs* against manager *style* (BUILD_PLAN C-2).

`questions.py`/`score.py` measure what the user needs from a manager.
`manager_profile.py` measures what their actual manager observably does. Both
run the same four dimensions on the same 0–1 scale with the same 0.25/0.80
anchors, which is what makes them subtractable. This module does the
subtraction and turns the result into a private managing-up playbook.

Pure: no Flask, no DB, no provider call, no clock, no randomness. Storage and
the API are C-3; rendering is C-4. Assembly here is a lookup over the static
content in `playbook_content.py` (ruling ⚑1, template-first) — the same profile
pair always produces byte-identical output.

**The diff rule.** Per dimension, `gap = manager_style − user_need`.

    |gap| <  MESH_THRESHOLDS[dim]   → mesh
    |gap| >= MESH_THRESHOLDS[dim]   → grind, with a direction:
        gap > 0  → over_supplied   (the manager runs higher on this dimension
                                    than the user needs)
        gap < 0  → under_supplied  (lower than the user needs)
    |gap| >= ACUTE_THRESHOLDS[dim]  → that grind is `acute` rather than `notable`

Neither direction is a fault. "Over-supplied" means more of a legitimate thing
than this particular person needs; "under-supplied" means less. The playbook
copy is written to hold that line — see `playbook_content.py`.

**Where the thresholds come from.** They are calibrated so that a single item
answered differently can never on its own manufacture a grind, because on a
forced-choice instrument with no pilot data that is the smallest movement that
is plainly noise. One item's worth of movement is the anchor spread divided by
the number of items on that dimension's *shorter* side:

    autonomy        4 user items,  4 manager items  → 0.55/4 = 0.1375
    feedback_style  4 user items,  4 manager items  → 0.55/4 = 0.1375
    growth_focus    4 user items,  4 manager items  → 0.55/4 ≈ 0.1375
    relationship    3 user items,  4 manager items  → 0.55/3 ≈ 0.1833

so `relationship` needs a wider mesh band than the other three purely on
arithmetic.

Two independent reasons used to land on the same number, which is why 0.20 was
the value rather than a hedge. The second was the bias review's **Finding 7**:
`mm-q11` keyed distance high while `mm-q9` and `mm-q10` keyed closeness and
advocacy high, so the relationship diff subtracted a clean manager-side scale
from a contaminated user-side one. That keying was corrected 2026-09-10 (C-1c,
`bf0f533`): `mm-q11` now keys availability — the closeness pole — high,
consistent with the other two items. The fix landed as a flip plus a stamped
rescore backfill (`score.SCORING_KEY`, `Scripts/backfill_manager_match_scoring_key.py`)
rather than a silent reinterpretation of stored sittings, because `manager_match`
submissions carry no era tag and a retake overwrites a single row in place.
Finding 7 is closed.

0.20 stands on the arithmetic alone now: it is the smallest threshold at which
a single item, mis-keyed or merely noisy, cannot on its own manufacture a
relationship grind — the derivation above (0.55/3 ≈ 0.1833) sets that floor
independent of how any one item is keyed. `test_no_single_item_can_manufacture_a_grind`
and `test_finding_7_contamination_cannot_manufacture_a_relationship_grind` pin
exactly that; the second now exercises it as a hypothetical — one relationship
item disagreeing with the other two, the shape Finding 7's bug produced —
rather than a live defect, so the margin is proven to hold against a future
keying mistake, not only against ordinary noise. The residual, stated rather
than papered over: a mis-keyed item can still push a gap that was already close
to the line across it, in either direction. No threshold on a three-item scale
escapes that.

The acute cut sits at 0.35 on every dimension: three items' worth of divergence
(≈0.41) is acute, two (≈0.275) is not, and 0.35 is the gap between them. It is
declared per-dimension so it can be tuned per-dimension once pilot data exists.

These are constants, not derived at import time from the item lists — an
instrument that gains or loses an item should force a deliberate revisit here,
not silently re-scale the thresholds under the content. `test_decoder.py` pins
the arithmetic the numbers were chosen from, so that revisit cannot be skipped
quietly.
"""
from __future__ import annotations

from typing import Mapping, TypedDict

from .manager_profile import score_manager_profile
from .playbook_content import (
    CONSTRAINT_NOTES,
    MESH_NOTES,
    PRIVACY_NOTICE,
    PROTOCOL_CELLS,
)
from .score import score_manager_match

# Fixed, and the order the playbook renders in. Not derived from the
# instruments: the content is keyed on exactly these four, so a dimension
# appearing or disappearing must break loudly rather than be dropped.
DIMENSIONS: tuple[str, ...] = (
    "autonomy",
    "feedback_style",
    "relationship",
    "growth_focus",
)

# |gap| below this is a match, not a mismatch. See the module docstring.
MESH_THRESHOLD_AUTONOMY = 0.15
MESH_THRESHOLD_FEEDBACK_STYLE = 0.15
MESH_THRESHOLD_RELATIONSHIP = 0.20
MESH_THRESHOLD_GROWTH_FOCUS = 0.15

# |gap| at or above this makes the grind `acute` rather than `notable`.
ACUTE_THRESHOLD_AUTONOMY = 0.35
ACUTE_THRESHOLD_FEEDBACK_STYLE = 0.35
ACUTE_THRESHOLD_RELATIONSHIP = 0.35
ACUTE_THRESHOLD_GROWTH_FOCUS = 0.35

MESH_THRESHOLDS: dict[str, float] = {
    "autonomy": MESH_THRESHOLD_AUTONOMY,
    "feedback_style": MESH_THRESHOLD_FEEDBACK_STYLE,
    "relationship": MESH_THRESHOLD_RELATIONSHIP,
    "growth_focus": MESH_THRESHOLD_GROWTH_FOCUS,
}

ACUTE_THRESHOLDS: dict[str, float] = {
    "autonomy": ACUTE_THRESHOLD_AUTONOMY,
    "feedback_style": ACUTE_THRESHOLD_FEEDBACK_STYLE,
    "relationship": ACUTE_THRESHOLD_RELATIONSHIP,
    "growth_focus": ACUTE_THRESHOLD_GROWTH_FOCUS,
}

# The instrument anchors, shared by both sides. Used only to band a mesh —
# where on the scale the two of you jointly sit — into low/mid/high thirds.
ANCHOR_LOW = 0.25
ANCHOR_HIGH = 0.80
_BAND_WIDTH = (ANCHOR_HIGH - ANCHOR_LOW) / 3
MESH_BAND_LOW_MAX = ANCHOR_LOW + _BAND_WIDTH      # ≈ 0.4333
MESH_BAND_HIGH_MIN = ANCHOR_HIGH - _BAND_WIDTH    # ≈ 0.6167

# Gaps are rounded before they meet a threshold so that float dust never
# decides which cell a user is shown: 0.45 - 0.80 is -0.35, and it must classify
# as -0.35 rather than as -0.35000000000000003.
GAP_PRECISION = 6

MESH = "mesh"
GRIND = "grind"
OVER_SUPPLIED = "over_supplied"
UNDER_SUPPLIED = "under_supplied"
NOTABLE = "notable"
ACUTE = "acute"


class DimensionVerdict(TypedDict):
    """One dimension of the diff. Direction/severity are None on a mesh."""

    dimension: str
    user_need: float
    manager_style: float
    gap: float
    classification: str
    direction: str | None
    severity: str | None
    band: str | None


def _validate_scores(scores: Mapping[str, float], label: str) -> None:
    missing = [d for d in DIMENSIONS if d not in scores]
    if missing:
        raise ValueError(f"{label} scores missing dimension(s): {', '.join(missing)}")

    unexpected = sorted(set(scores) - set(DIMENSIONS))
    if unexpected:
        raise ValueError(f"{label} scores have unknown dimension(s): {', '.join(unexpected)}")

    for dim in DIMENSIONS:
        value = scores[dim]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} score for '{dim}' is not a number: {value!r}")
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{label} score for '{dim}' out of [0, 1]: {value}")


def _mesh_band(user_need: float, manager_style: float) -> str:
    """Where on the scale a meshing pair jointly sits: low, mid or high."""
    midpoint = (user_need + manager_style) / 2
    if midpoint <= MESH_BAND_LOW_MAX:
        return "low"
    if midpoint >= MESH_BAND_HIGH_MIN:
        return "high"
    return "mid"


def classify_dimension(
    dimension: str, user_need: float, manager_style: float
) -> DimensionVerdict:
    """Classify one dimension as mesh or grind, with direction and severity."""
    if dimension not in MESH_THRESHOLDS:
        raise ValueError(f"Unknown dimension '{dimension}'")

    gap = round(manager_style - user_need, GAP_PRECISION)
    magnitude = abs(gap)

    if magnitude < MESH_THRESHOLDS[dimension]:
        return {
            "dimension": dimension,
            "user_need": user_need,
            "manager_style": manager_style,
            "gap": gap,
            "classification": MESH,
            "direction": None,
            "severity": None,
            "band": _mesh_band(user_need, manager_style),
        }

    return {
        "dimension": dimension,
        "user_need": user_need,
        "manager_style": manager_style,
        "gap": gap,
        "classification": GRIND,
        "direction": OVER_SUPPLIED if gap > 0 else UNDER_SUPPLIED,
        "severity": ACUTE if magnitude >= ACUTE_THRESHOLDS[dimension] else NOTABLE,
        "band": None,
    }


def diff_profiles(
    user_scores: Mapping[str, float], manager_scores: Mapping[str, float]
) -> list[DimensionVerdict]:
    """Diff a need profile against a style profile, in `DIMENSIONS` order."""
    _validate_scores(user_scores, "user")
    _validate_scores(manager_scores, "manager")

    return [
        classify_dimension(dim, user_scores[dim], manager_scores[dim])
        for dim in DIMENSIONS
    ]


def _entry(verdict: DimensionVerdict) -> dict:
    """Attach the content a single verdict resolves to."""
    if verdict["classification"] == MESH:
        return {
            **verdict,
            "note": MESH_NOTES[(verdict["dimension"], verdict["band"])],
        }

    key = (verdict["dimension"], verdict["direction"], verdict["severity"])
    cell = PROTOCOL_CELLS[key]
    return {
        **verdict,
        "headline": cell["headline"],
        "why": cell["why"],
        "ask": cell["ask"],
        "agenda": list(cell["agenda"]),
        "scripts": list(cell["scripts"]),
        "constraint_note": CONSTRAINT_NOTES.get(
            (verdict["dimension"], verdict["direction"])
        ),
    }


def build_playbook(
    user_scores: Mapping[str, float], manager_scores: Mapping[str, float]
) -> dict:
    """Profile pair in, assembled playbook out. Deterministic and instant.

    `dimensions` is always all four in `DIMENSIONS` order, so the mesh half of
    the map is renderable too. `priority` orders the grinds by how wide the gap
    is, ties broken by `DIMENSIONS` order so it never depends on dict iteration.
    """
    verdicts = diff_profiles(user_scores, manager_scores)
    entries = [_entry(v) for v in verdicts]

    grinds = [v for v in verdicts if v["classification"] == GRIND]
    priority = [
        v["dimension"]
        for v in sorted(
            grinds,
            key=lambda v: (-abs(v["gap"]), DIMENSIONS.index(v["dimension"])),
        )
    ]

    return {
        "privacy_notice": PRIVACY_NOTICE,
        "dimensions": entries,
        "priority": priority,
        "grind_count": len(grinds),
        "mesh_count": len(verdicts) - len(grinds),
    }


def decode(manager_match_answers: list[dict], manager_profile_answers: list[dict]) -> dict:
    """Score both sittings and assemble the playbook.

    The only supported route from raw answers to a playbook: dimension scores
    come from each instrument's own scoring function, never from re-reading its
    item list here. An instrument that gains or loses an item stays invisible to
    this module.
    """
    user_scores = score_manager_match(manager_match_answers)["dimension_scores"]
    manager_scores = score_manager_profile(manager_profile_answers)["dimension_scores"]
    return build_playbook(user_scores, manager_scores)
