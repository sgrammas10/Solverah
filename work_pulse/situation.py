"""Situation Report scoring: environment answers -> dimension scores, signed
gaps against the sealed person-side profile, and D-15-conforming buckets
(BUILD_PLAN A-3).

Pure: no Flask, no DB, no provider call, no clock, no randomness. Storage is
A-2's (a parallel, unbuilt chunk as of 2026-09-10); the full report payload
(guidance content, person-side snapshot pinning) is A-4/A-5's. This module
owns exactly three things: turning answered environment items into a 0-1
score per dimension, diffing that against a sealed person-side profile, and
classifying + ranking the result into the only shape D-15 allows out the
door -- no magnitudes, no person-side numbers
(docs/PRODUCT_DECISIONS.md §2, "What a D-15-conforming Situation Report
returns").

**A-1 does not exist. This module does not guess at it.** BUILD_PLAN A-1
(the environment-side item bank) shipped no files in wave 2 (see the
2026-09-10 "mark wave-2 chunks landed" commit) -- there is no real item text
and no real item ids to read or mirror. `score_environment` therefore takes
a generic **item spec** as a plain parameter (`EnvironmentItemSpec`, an
`{item_id, dimension, pole_values}` entry per item, where `pole_values` maps
each of that item's own answer tokens to a 0-1 score) rather than importing
anything, and scores strictly against whatever spec it is handed: the mean
of a dimension's answered items, each answer resolved through its own item's
`pole_values` (mean_pole -- the same shape
`causal_graph/v1_model/score_person_side.py` uses for the person-side
instrument's options+pole_values, without depending on that module or its
content). `pole_values` is a mapping rather than a fixed low/high pair
specifically so an item can carry any number of anchor bands, not just two
-- a two-entry `{"low": ..., "high": ...}` is one valid instance, not the
only one. Every spec used in this module's own tests is synthetic and says
so; A-1 landing later is then one import plus a spec-conformance test on the
caller's side, not a rewrite here.

**Dimensions.** Six, fixed, the same six BUILD_PLAN A-1 names for the
environment side and the six the sealed person-side profile must already be
keyed on for a gap to be well-defined.

**Bucket + direction (2026-09-10 rename, PRODUCT_DECISIONS.md §2 "The spine
is conditions" amendment).** `gap = env_score - person_score`. `bucket` is
magnitude-only -- `aligned` / `notable` / `straining`, in increasing order of
severity -- and never implies a sign: the bucket this replaced conflated
severity with over-supply being good, and it often is not (a pace above the
one you can hold, more autonomy than you want). `direction` is sign-only -- `under` / `over`
-- and is `None` exactly when `bucket` is `aligned`, since an aligned
dimension has no direction to report. Neither field is styled as good or bad
here -- that judgment, if any, belongs to A-4/A-6's guidance content, not to
this module.

**Tolerance and must-haves (PRODUCT_DECISIONS.md §2, "The six-trait match
model", 2026-10-13).** A user may state, per trait, how far a job may sit
from their preference in each direction, and flag up to two traits as
must-haves. `classify_gap` then reads a per-user, per-direction flat zone
(`solverah.domain.trait_preferences.flat_zones`) instead of the fixed 0.15 /
0.25, and `rank_dimensions` orders must-haves first within a severity tier.
A user who never answered passes `zones=None` and no must-haves, and gets
exactly the behaviour this module had before (pinned by
`test_unanswered_tolerance_is_bit_identical`).
"""
from __future__ import annotations

from typing import Collection, Mapping, Sequence, TypedDict

# Fixed, matching BUILD_PLAN A-1's six environment-side dimensions and the
# sealed person-side profile's own dimension keys. A gap is only meaningful
# while both sides agree on exactly this set.
DIMENSIONS: tuple[str, ...] = (
    "autonomy",
    "pace",
    "collaboration",
    "feedback",
    "innovation",
    "decision",
)


class EnvironmentItemSpec(TypedDict):
    """One environment item, as data -- not A-1 content. `pole_values` maps
    this item's own answer tokens to a 0-1 score, e.g. `{"low": 0.25, "high":
    0.80}` for a forced two-way choice, or a five-entry mapping for a
    banded Likert item. Nothing here fixes the token vocabulary or the pole
    count; a caller's real item bank supplies both.
    """

    item_id: str
    dimension: str
    pole_values: Mapping[str, float]


class SituationDimensionReport(TypedDict):
    """The only shape D-15 allows out of this module: an echo of the user's
    own environment score, a coarse bucket, a direction, and a rank position.
    No person-side score, no numeric gap -- both stay inside `signed_gaps`,
    which nothing outside this module needs to call in production.
    """

    dimension: str
    env_score: float
    bucket: str
    direction: str | None
    rank: int
    must_have: bool
    within_tolerance: bool


def _items_by_dimension(
    item_spec: Sequence[EnvironmentItemSpec],
) -> dict[str, dict[str, EnvironmentItemSpec]]:
    by_dim: dict[str, dict[str, EnvironmentItemSpec]] = {dim: {} for dim in DIMENSIONS}
    seen_ids: set[str] = set()
    for entry in item_spec:
        item_id = entry["item_id"]
        if item_id in seen_ids:
            raise ValueError(f"item spec has a duplicate item_id: {item_id!r}")
        seen_ids.add(item_id)

        dim = entry["dimension"]
        if dim not in by_dim:
            raise ValueError(f"item {item_id!r} names unknown dimension {dim!r}")
        by_dim[dim][item_id] = entry
    return by_dim


def score_environment(
    answers: Mapping[str, str], item_spec: Sequence[EnvironmentItemSpec]
) -> dict[str, float]:
    """Environment answers -> {dimension: 0-1}, mean of that dimension's
    anchored items (mean_pole; the same shape
    causal_graph/v1_model/score_person_side.py's score_all_dimensions uses
    for the person-side instrument).

    `item_spec` is generic data, not A-1's item bank -- see the module
    docstring. `answers` maps `item_id -> pole token`, where the token must
    be one of that item's own `pole_values` keys.

    Requires every item `item_spec` assigns to a dimension to be present in
    `answers` -- the same full-coverage discipline score_all_dimensions
    enforces, except the required count is read from `item_spec` itself
    rather than a fixed constant, since A-1's real per-dimension item count
    is unknown (BUILD_PLAN A-1 says "~10-12 items" across six dimensions,
    not necessarily an even split).

    Tense variants (BUILD_PLAN A-1: employed vs. between_jobs wording) are
    invisible here by construction: this function only ever looks at
    `item_id -> dimension -> pole_values`, never at any wording field, so
    the same item id scores identically regardless of which tense variant's
    text the user actually saw -- a spec is free to carry a `text` (or
    `prompt`/`prompt_past`) field for display, and this function would still
    never read it.
    """
    by_dim = _items_by_dimension(item_spec)

    known_ids = {entry["item_id"] for entry in item_spec}
    unknown = sorted(set(answers) - known_ids)
    if unknown:
        raise ValueError(f"answers reference unknown item id(s): {', '.join(unknown)}")

    scores: dict[str, float] = {}
    for dim in DIMENSIONS:
        items = by_dim[dim]
        if not items:
            raise ValueError(f"item spec has no items for dimension {dim!r}")
        missing = [item_id for item_id in items if item_id not in answers]
        if missing:
            raise ValueError(
                f"dimension {dim!r} missing answer(s) for item(s): {', '.join(missing)}"
            )
        values = []
        for item_id, entry in items.items():
            choice = answers[item_id]
            pole_values = entry["pole_values"]
            if choice not in pole_values:
                raise ValueError(
                    f"item {item_id} has no pole {choice!r}; valid poles: "
                    f"{sorted(pole_values)}"
                )
            values.append(pole_values[choice])
        scores[dim] = sum(values) / len(values)

    return scores


# Gaps are rounded before they meet a threshold, so float dust never decides
# which bucket a user lands in (manager_match.decoder.GAP_PRECISION's
# precedent).
GAP_PRECISION = 6


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


def signed_gaps(
    env_scores: Mapping[str, float], person_scores: Mapping[str, float]
) -> dict[str, float]:
    """{dimension: env_score - person_score}, rounded to GAP_PRECISION.

    `person_scores` is a plain input dict: the caller seals/pins the
    person-side snapshot (BUILD_PLAN A-4's pinning rule) and this module
    never fetches or stores it.
    """
    _validate_scores(env_scores, "environment")
    _validate_scores(person_scores, "person")
    return {
        dim: round(env_scores[dim] - person_scores[dim], GAP_PRECISION)
        for dim in DIMENSIONS
    }


ALIGNED = "aligned"
NOTABLE = "notable"
STRAINING = "straining"
GAP_BUCKETS: tuple[str, ...] = (ALIGNED, NOTABLE, STRAINING)

UNDER = "under"
OVER = "over"
GAP_DIRECTIONS: tuple[str, ...] = (UNDER, OVER)

# |gap| below this is aligned. BUILD_PLAN A-1 (2026-09-10) fixed the item
# count this arithmetic needed: two items per dimension, five bands
# (0.1/0.3/0.5/0.7/0.9) 0.2 apart. A dimension score is the MEAN of its two
# items, so one item moving one band shifts the dimension mean by
# 0.2 / 2 = 0.10 -- pure per-item noise, indistinguishable from a respondent
# picking an adjacent band on a re-read. One item moving two bands, or both
# items moving one band each, shifts it 0.20 -- a real, reproducible signal.
# 0.15 sits strictly between the two, so a single band's worth of movement on
# a single item can never push a dimension out of `aligned`
# (test_no_single_band_move_can_manufacture_a_nonaligned_bucket, in
# tests/test_situation.py, pins this -- manager_match.decoder.MESH_THRESHOLD's
# same-shaped guard is the precedent).
# Named per dimension (decoder.py's house style) so a later revisit to one
# dimension can't silently move the other five, even though today all six
# share one value.
ALIGNED_THRESHOLD_AUTONOMY = 0.15
ALIGNED_THRESHOLD_PACE = 0.15
ALIGNED_THRESHOLD_COLLABORATION = 0.15
ALIGNED_THRESHOLD_FEEDBACK = 0.15
ALIGNED_THRESHOLD_INNOVATION = 0.15
ALIGNED_THRESHOLD_DECISION = 0.15

ALIGNED_THRESHOLDS: dict[str, float] = {
    "autonomy": ALIGNED_THRESHOLD_AUTONOMY,
    "pace": ALIGNED_THRESHOLD_PACE,
    "collaboration": ALIGNED_THRESHOLD_COLLABORATION,
    "feedback": ALIGNED_THRESHOLD_FEEDBACK,
    "innovation": ALIGNED_THRESHOLD_INNOVATION,
    "decision": ALIGNED_THRESHOLD_DECISION,
}

# |gap| at or above this makes the bucket `straining` rather than `notable`.
# Picked the way manager_match.decoder picked its ACUTE_THRESHOLD: on the
# same 0.10-per-step arithmetic above, two items' worth of divergence is 0.20
# and three items' worth is 0.30, so 0.25 -- the midpoint -- is the boundary
# that sits no closer to one step count than the other.
STRAINING_THRESHOLD_AUTONOMY = 0.25
STRAINING_THRESHOLD_PACE = 0.25
STRAINING_THRESHOLD_COLLABORATION = 0.25
STRAINING_THRESHOLD_FEEDBACK = 0.25
STRAINING_THRESHOLD_INNOVATION = 0.25
STRAINING_THRESHOLD_DECISION = 0.25

STRAINING_THRESHOLDS: dict[str, float] = {
    "autonomy": STRAINING_THRESHOLD_AUTONOMY,
    "pace": STRAINING_THRESHOLD_PACE,
    "collaboration": STRAINING_THRESHOLD_COLLABORATION,
    "feedback": STRAINING_THRESHOLD_FEEDBACK,
    "innovation": STRAINING_THRESHOLD_INNOVATION,
    "decision": STRAINING_THRESHOLD_DECISION,
}


#: Per-user flat zones, `{dimension: (under_zone, over_zone)}` --
#: `solverah.domain.trait_preferences.flat_zones`' return shape. Each zone is
#: `max(0.15, steps * 0.25)`, so never below today's aligned band.
FlatZones = Mapping[str, tuple[float, float]]

#: Width of the `notable` band above a user's flat zone (PRODUCT_DECISIONS.md
#: §2, "The six-trait match model", 2026-10-13). Today's 0.15 / 0.25 split is
#: the special case zone = 0.15: 0.15 + 0.10 = 0.25.
NOTABLE_WIDTH = 0.10


def _zone_for(dimension: str, gap: float, zones: FlatZones) -> float:
    """The flat zone for the direction `gap` points in. UNDER (the role gives
    less than the user prefers) is `gap < 0` in THIS module's convention
    (`gap = env - person`); OVER is `gap > 0`. A zero gap is aligned under
    either zone, since every zone is at least 0.15."""
    if dimension not in zones:
        raise ValueError(f"zones missing dimension {dimension!r}")
    under_zone, over_zone = zones[dimension]
    return under_zone if gap < 0 else over_zone


def classify_gap(dimension: str, gap: float, zones: FlatZones | None = None) -> str:
    """One of `aligned` / `notable` / `straining`, by |gap| magnitude alone --
    never by sign (2026-09-10 rename, PRODUCT_DECISIONS.md §2). `gap` must
    already be rounded (see `signed_gaps`) -- this function does not round
    again. See `gap_direction` for the sign.

    `zones` is the user's stated tolerance (`flat_zones`), or None for a user
    who never answered it. None takes exactly today's path: the per-dimension
    0.15 / 0.25 thresholds, untouched (`test_unanswered_tolerance_is_bit_identical`
    pins it against a frozen copy). With zones the classification becomes
    sign-aware: the zone for the gap's own direction decides, `aligned` below
    it, `notable` below it plus `NOTABLE_WIDTH`, `straining` beyond. The sign
    only picks the zone; the bucket is still magnitude.
    """
    if dimension not in ALIGNED_THRESHOLDS:
        raise ValueError(f"Unknown dimension {dimension!r}")
    magnitude = abs(gap)
    if zones is None:
        if magnitude < ALIGNED_THRESHOLDS[dimension]:
            return ALIGNED
        if magnitude < STRAINING_THRESHOLDS[dimension]:
            return NOTABLE
        return STRAINING
    zone = _zone_for(dimension, gap, zones)
    if magnitude < zone:
        return ALIGNED
    # Rounded like the gap itself, so float dust in the sum never moves a boundary.
    if magnitude < round(zone + NOTABLE_WIDTH, GAP_PRECISION):
        return NOTABLE
    return STRAINING


def gap_direction(dimension: str, gap: float, zones: FlatZones | None = None) -> str | None:
    """`under` / `over` from the sign of `gap`, or `None` exactly where
    `classify_gap` (with the same `zones`) returns `aligned` -- an aligned
    dimension has no direction to report (PRODUCT_DECISIONS.md §2).
    """
    if classify_gap(dimension, gap, zones) == ALIGNED:
        return None
    return OVER if gap > 0 else UNDER


def within_tolerance(dimension: str, gap: float, zones: FlatZones | None) -> bool:
    """True when the user's stated tolerance is what makes this gap `aligned`:
    aligned under `zones`, but not under today's thresholds. False for a user
    with no zones, and for a gap that is aligned either way -- a gap inside the
    measurement-noise floor is not something the tolerance did.

    Carries no more resolution than the bucket already does: it says the gap is
    past the 0.15 floor, which is the same boundary `notable` reports today.
    """
    if zones is None:
        return False
    return classify_gap(dimension, gap, zones) == ALIGNED and classify_gap(dimension, gap) != ALIGNED


class DimensionWeight(TypedDict):
    """One dimension's pair of E-5 weights, on the match model's logit scale
    and in the match model's sign convention (`g = person - env`), exactly as
    `causal_graph/v1_model/priors.yaml` writes them.

    `mag` (< 0) is the symmetric penalty every mismatch pays; `dir` is the
    directional asymmetry -- `dir > 0` means wanting MORE than the role offers
    is the cheaper way to be wrong on this dimension, `dir < 0` the reverse.
    `abs(dir) <= abs(mag)` must hold or one direction would score as a benefit
    rather than a cost; `tests/test_match_scoring.py` guards that on the live
    priors file, and `dimension_cost` refuses a negative cost here.
    """

    mag: float
    dir: float


#: Severity order, worst first once negated. The bucket WORD is the only
#: magnitude a reader ever sees (D-15), so it -- not the weighted cost -- has
#: to be the outer sort key: a green `aligned` row sitting above an amber
#: `straining` one reads as a contradiction no weight can justify. Tiering
#: confines the weights to ordering same-severity rows against each other.
BUCKET_SEVERITY: dict[str, int] = {ALIGNED: 0, NOTABLE: 1, STRAINING: 2}

#: Neutral default: symmetric unit penalty, no directional asymmetry, so
#: `dimension_cost` collapses to plain `abs(gap)` and an un-weighted caller
#: keeps the flat within-tier ordering this module shipped with.
FLAT_MAG = -1.0
FLAT_DIR = 0.0


def _flat_weights() -> dict[str, DimensionWeight]:
    return {dim: {"mag": FLAT_MAG, "dir": FLAT_DIR} for dim in DIMENSIONS}


def dimension_cost(dimension: str, gap: float, weight: DimensionWeight) -> float:
    """How much this mismatch costs, on the match model's logit scale -- the
    negated logit contribution of `weight`, re-expressed in THIS module's sign
    convention. Never leaves the module: D-15 lets no magnitude out the door.

    **The two conventions are opposite, and this is where they meet.** Here
    `gap = env_score - person_score`, so a positive gap means the role offers
    MORE than the person wants. The match model uses `g = person - env` and
    contributes `mag*|g| + dir*g` to its linear predictor. Substituting
    `g = -gap` and negating (a lower logit is a higher cost) gives::

        cost = abs(mag) * abs(gap) + dir * gap

    -- so under `dir > 0` ("wanting more is the cheaper mistake") it is the
    OVER direction, `gap > 0`, that costs more. That is the intended reading,
    not a sign slip.

    Takes the same rounded `gap` `classify_gap` reads, and deliberately does
    NOT apply `match_core.fit_gap`'s `closest_achievable` snap to the sealed
    person-side value: bucket, direction and rank must all describe one gap,
    and ranking a payload on a second, differently-defined gap would be a
    worse inconsistency than the small pole effect the snap removes.

    Cost cannot go negative while `abs(dir) <= abs(mag)`; where the two are
    equal the cheap direction cancels to exactly 0.0 (IEEE negation is exact,
    so no float dust creeps in). A negative cost means a weight violated that
    invariant, and is raised rather than clamped -- silently flooring it would
    turn a broken weight into a plausible-looking ranking.
    """
    cost = abs(weight["mag"]) * abs(gap) + weight["dir"] * gap
    if cost < 0:
        raise ValueError(
            f"dimension {dimension!r} has a negative cost ({cost}): |dir| must not "
            f"exceed |mag| (mag={weight['mag']}, dir={weight['dir']})"
        )
    return cost


def rank_dimensions(
    gaps: Mapping[str, float],
    weights: Mapping[str, DimensionWeight] | None = None,
    zones: FlatZones | None = None,
    must_haves: Collection[str] = frozenset(),
) -> list[str]:
    """Dimensions ordered worst first: severity bucket, then must-have, then
    weighted directional cost within a bucket, then `DIMENSIONS` order.

    `zones` and `must_haves` are the user's tolerance and must-have traits
    (PRODUCT_DECISIONS.md §2, "The six-trait match model"). With neither --
    a user who never answered -- the must-have key is the same for every
    dimension and the ordering is exactly today's. A must-have never jumps a
    severity tier: it orders first among rows that share a bucket word.

    The bucket comes from `classify_gap` on these same gaps -- derived here,
    never a parameter, so a caller cannot rank one payload against a
    bucketing that payload does not carry.

    `weights` defaults to a flat `{mag: -1.0, dir: 0.0}` per dimension, which
    reduces the within-tier key to plain `abs(gap)`. It stays an explicit
    parameter rather than a module constant so E-5 can swap in elicited (and
    later fitted) weights through exactly this seam -- the same
    interim-to-destination pattern already used for culture_fit_score. Ties
    break by `DIMENSIONS` order, never dict iteration
    (manager_match.decoder.build_playbook's `priority` precedent).
    """
    if weights is None:
        weights = _flat_weights()

    missing = [d for d in DIMENSIONS if d not in weights]
    if missing:
        raise ValueError(f"weights missing dimension(s): {', '.join(missing)}")
    unknown = sorted(set(must_haves) - set(DIMENSIONS))
    if unknown:
        raise ValueError(f"must_haves name unknown dimension(s): {', '.join(unknown)}")

    def sort_key(dim: str) -> tuple[int, int, float, int]:
        bucket = classify_gap(dim, gaps[dim], zones)
        cost = dimension_cost(dim, gaps[dim], weights[dim])
        must_have_first = 0 if dim in must_haves else 1
        return (-BUCKET_SEVERITY[bucket], must_have_first, -cost, DIMENSIONS.index(dim))

    return sorted(DIMENSIONS, key=sort_key)


def build_situation_report(
    env_scores: Mapping[str, float],
    person_scores: Mapping[str, float],
    weights: Mapping[str, DimensionWeight] | None = None,
    zones: FlatZones | None = None,
    must_haves: Collection[str] = frozenset(),
) -> list[SituationDimensionReport]:
    """Env scores + sealed person scores -> the D-15-conforming per-dimension
    list, in `DIMENSIONS` order. Per entry: `env_score` (an echo of the
    user's own answer), `bucket`, `direction` (`None` on `aligned`), `rank`
    (0 = worst, by `rank_dimensions`' severity, must-have, cost order),
    `must_have`, and `within_tolerance` (see `within_tolerance`). No
    `person_score` or `gap` field anywhere in the return value.

    `zones` / `must_haves` are the user's tolerance and must-have traits, or
    None / empty for a user who never answered: then bucket, direction and rank
    are exactly today's, `must_have` and `within_tolerance` are False on every
    row.

    Rows come back in `DIMENSIONS` order, NOT rank order -- this module is
    order-stable by contract, and presentation order is the caller's to
    choose. `solverah.services.situation_report_service` sorts by `rank`
    before the payload leaves the API, because both frontends render the
    order they are handed.
    """
    _validate_scores(env_scores, "environment")
    gaps = signed_gaps(env_scores, person_scores)
    order = rank_dimensions(gaps, weights, zones, must_haves)
    rank_by_dim = {dim: position for position, dim in enumerate(order)}

    return [
        {
            "dimension": dim,
            "env_score": env_scores[dim],
            "bucket": classify_gap(dim, gaps[dim], zones),
            "direction": gap_direction(dim, gaps[dim], zones),
            "rank": rank_by_dim[dim],
            "must_have": dim in must_haves,
            "within_tolerance": within_tolerance(dim, gaps[dim], zones),
        }
        for dim in DIMENSIONS
    ]
