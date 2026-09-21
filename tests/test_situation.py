"""Tests for Situation Report scoring: env answers -> scores, gaps, buckets,
ranking (BUILD_PLAN A-3)."""
from __future__ import annotations

import pytest

from work_pulse.situation import (
    ALIGNED,
    ALIGNED_THRESHOLDS,
    DIMENSIONS,
    FLAT_DIR,
    FLAT_MAG,
    NOTABLE,
    OVER,
    STRAINING,
    STRAINING_THRESHOLDS,
    UNDER,
    DimensionWeight,
    build_situation_report,
    classify_gap,
    dimension_cost,
    gap_direction,
    rank_dimensions,
    score_environment,
    signed_gaps,
)


def _flat_dimension_weights() -> dict[str, DimensionWeight]:
    """The module's own neutral default, spelled out -- `cost` collapses to
    `abs(gap)`, so ranking within a tier is by raw gap width."""
    return {dim: {"mag": FLAT_MAG, "dir": FLAT_DIR} for dim in DIMENSIONS}


def _live_dimension_weights() -> dict[str, DimensionWeight]:
    """The real elicited weights, read from the repo's own priors.yaml rather
    than transcribed -- so a later re-elicitation moves these tests instead of
    leaving them asserting numbers nothing uses any more. Means only; the sd
    describes the expert's confidence and does not order anything.
    """
    from match_scoring import load, weights_from_priors

    cfg, pri = load()
    return {
        dim: {"mag": float(w["mag"]["mean"]), "dir": float(w["dir"]["mean"])}
        for dim, w in weights_from_priors(cfg, pri)["dimensions"].items()
    }

# ---------------------------------------------------------------------------
# FIXTURE DISCLAIMER: this is a SYNTHETIC item spec, invented purely for
# these tests. BUILD_PLAN A-1 (the real environment-side item bank) does not
# exist -- it shipped no files in wave 2 (2026-09-10 "mark wave-2 chunks
# landed" commit) -- so nothing below (item ids, dimension-to-item mapping,
# pole tokens, pole values) is drawn from, or should be read as a preview of,
# A-1's actual content. It exists only to exercise score_environment's
# generic mean_pole arithmetic against SOME spec shaped like
# `EnvironmentItemSpec`. When A-1 lands, production wires its real spec
# through the same parameter; this fixture is not it and is not meant to be
# reused as it.
# ---------------------------------------------------------------------------

ANCHOR_LOW = 0.25
ANCHOR_HIGH = 0.80
TWO_POLE_VALUES = {"low": ANCHOR_LOW, "high": ANCHOR_HIGH}


def _synthetic_spec() -> list[dict]:
    return [
        {"item_id": f"synthetic-{dim}-{n}", "dimension": dim, "pole_values": TWO_POLE_VALUES}
        for dim in DIMENSIONS
        for n in (1, 2)
    ]


SYNTHETIC_SPEC = _synthetic_spec()


def _full_answers(high_ids: set[str]) -> dict[str, str]:
    """A full sitting: items in `high_ids` answer high, the rest low."""
    return {
        entry["item_id"]: ("high" if entry["item_id"] in high_ids else "low")
        for entry in SYNTHETIC_SPEC
    }


def _flat_scores(value: float = 0.5) -> dict[str, float]:
    return {dim: value for dim in DIMENSIONS}


# ---------------------------------------------------------------------------
# score_environment: mean_pole arithmetic, against the synthetic spec above
# ---------------------------------------------------------------------------


def test_all_low_answers_score_every_dimension_at_the_low_anchor() -> None:
    scores = score_environment(_full_answers(set()), SYNTHETIC_SPEC)

    for dim in DIMENSIONS:
        assert scores[dim] == pytest.approx(ANCHOR_LOW)


def test_all_high_answers_score_every_dimension_at_the_high_anchor() -> None:
    high_ids = {entry["item_id"] for entry in SYNTHETIC_SPEC}
    scores = score_environment(_full_answers(high_ids), SYNTHETIC_SPEC)

    for dim in DIMENSIONS:
        assert scores[dim] == pytest.approx(ANCHOR_HIGH)


def test_one_high_item_of_two_lands_on_the_dimension_midpoint() -> None:
    scores = score_environment(_full_answers({"synthetic-autonomy-1"}), SYNTHETIC_SPEC)

    assert scores["autonomy"] == pytest.approx((ANCHOR_LOW + ANCHOR_HIGH) / 2)


def test_score_covers_every_dimension() -> None:
    scores = score_environment(_full_answers(set()), SYNTHETIC_SPEC)

    assert set(scores) == set(DIMENSIONS)


def test_items_can_carry_their_own_independent_pole_values() -> None:
    """A-1's real anchors are unknown and may differ item to item -- the spec
    is not required to reuse one pole_values mapping everywhere.
    """
    spec = [
        {"item_id": "x1", "dimension": "autonomy", "pole_values": {"low": 0.0, "high": 1.0}},
        {"item_id": "x2", "dimension": "autonomy", "pole_values": {"low": 0.4, "high": 0.6}},
        *[
            {"item_id": f"filler-{dim}", "dimension": dim, "pole_values": {"low": 0.0, "high": 1.0}}
            for dim in DIMENSIONS
            if dim != "autonomy"
        ],
    ]
    answers = {"x1": "high", "x2": "low", **{f"filler-{d}": "low" for d in DIMENSIONS if d != "autonomy"}}

    scores = score_environment(answers, spec)

    assert scores["autonomy"] == pytest.approx((1.0 + 0.4) / 2)


def test_items_can_carry_more_than_two_poles() -> None:
    """The generalization this module exists for: A-1's real item bank
    (discovered concurrently, uncommitted, in this same working tree as
    work_pulse/situation_items.py -- not imported or copied from here) uses
    a five-band scale (low/leaning_low/mixed/leaning_high/high -> 0.1-0.9),
    not a forced binary choice. A spec entry with five poles must score
    exactly like the person-side mean_pole over whatever token was chosen.
    """
    five_band = {
        "low": 0.1,
        "leaning_low": 0.3,
        "mixed": 0.5,
        "leaning_high": 0.7,
        "high": 0.9,
    }
    spec = [
        {"item_id": "banded-1", "dimension": "autonomy", "pole_values": five_band},
        {"item_id": "banded-2", "dimension": "autonomy", "pole_values": five_band},
        *[
            {"item_id": f"filler-{dim}", "dimension": dim, "pole_values": five_band}
            for dim in DIMENSIONS
            if dim != "autonomy"
        ],
    ]
    answers = {
        "banded-1": "leaning_high",
        "banded-2": "mixed",
        **{f"filler-{d}": "mixed" for d in DIMENSIONS if d != "autonomy"},
    }

    scores = score_environment(answers, spec)

    assert scores["autonomy"] == pytest.approx((0.7 + 0.5) / 2)


def test_missing_an_item_for_a_dimension_raises() -> None:
    answers = _full_answers(set())
    del answers["synthetic-autonomy-2"]

    with pytest.raises(ValueError, match="synthetic-autonomy-2"):
        score_environment(answers, SYNTHETIC_SPEC)


def test_unknown_item_id_in_answers_raises() -> None:
    answers = _full_answers(set())
    answers["not-a-real-item"] = "low"

    with pytest.raises(ValueError, match="not-a-real-item"):
        score_environment(answers, SYNTHETIC_SPEC)


def test_invalid_answer_token_raises() -> None:
    answers = _full_answers(set())
    answers["synthetic-autonomy-1"] = "maybe"

    with pytest.raises(ValueError, match="synthetic-autonomy-1"):
        score_environment(answers, SYNTHETIC_SPEC)


def test_spec_with_no_items_for_a_dimension_raises() -> None:
    sparse = [entry for entry in SYNTHETIC_SPEC if entry["dimension"] != "pace"]
    answers = {entry["item_id"]: "low" for entry in sparse}

    with pytest.raises(ValueError, match="pace"):
        score_environment(answers, sparse)


def test_spec_with_duplicate_item_id_raises() -> None:
    spec = [*SYNTHETIC_SPEC, SYNTHETIC_SPEC[0]]

    with pytest.raises(ValueError, match="duplicate"):
        score_environment(_full_answers(set()), spec)


def test_spec_naming_unknown_dimension_raises() -> None:
    spec = [{"item_id": "z1", "dimension": "vibes", "pole_values": {"low": 0.0, "high": 1.0}}]

    with pytest.raises(ValueError, match="vibes"):
        score_environment({"z1": "low"}, spec)


# ---------------------------------------------------------------------------
# Tense variants: same ids, same scoring (A-1 guarantees it; assert it anyway)
# ---------------------------------------------------------------------------


def test_score_environment_never_reads_a_text_field() -> None:
    """Simulates an employed-tense vs. between-jobs-tense item bank: two
    specs whose entries carry different display `text` for the same
    item_id/dimension/pole_values must score identically, because
    score_environment reads only item_id, dimension and pole_values -- never
    wording. A spec is free to carry `text` for display; this proves it is
    inert to scoring regardless.
    """
    present_tense = [{**entry, "text": f"How much {entry['dimension']} does this role offer?"} for entry in SYNTHETIC_SPEC]
    past_tense = [{**entry, "text": f"How much {entry['dimension']} did that role offer you?"} for entry in SYNTHETIC_SPEC]

    answers = _full_answers({"synthetic-feedback-1", "synthetic-decision-2"})

    assert score_environment(answers, present_tense) == score_environment(answers, past_tense)


# ---------------------------------------------------------------------------
# signed_gaps
# ---------------------------------------------------------------------------


def test_gap_is_positive_when_environment_exceeds_person() -> None:
    gaps = signed_gaps(_flat_scores(0.80), _flat_scores(0.25))

    for dim in DIMENSIONS:
        assert gaps[dim] == pytest.approx(0.55)


def test_gap_is_negative_when_environment_trails_person() -> None:
    gaps = signed_gaps(_flat_scores(0.25), _flat_scores(0.80))

    for dim in DIMENSIONS:
        assert gaps[dim] == pytest.approx(-0.55)


def test_identical_scores_gap_to_zero() -> None:
    gaps = signed_gaps(_flat_scores(0.6), _flat_scores(0.6))

    for dim in DIMENSIONS:
        assert gaps[dim] == pytest.approx(0.0)


def test_gaps_are_rounded_to_gap_precision() -> None:
    env = {**_flat_scores(), "autonomy": 0.1 + 0.2}  # classic float dust
    person = {**_flat_scores(), "autonomy": 0.0}

    gaps = signed_gaps(env, person)

    assert gaps["autonomy"] == round(0.1 + 0.2, 6)


@pytest.mark.parametrize("label_scores,label", [("environment", "environment"), ("person", "person")])
def test_missing_dimension_names_which_side(label_scores: str, label: str) -> None:
    partial = {d: 0.5 for d in DIMENSIONS if d != "pace"}
    complete = _flat_scores()

    args = (partial, complete) if label == "environment" else (complete, partial)

    with pytest.raises(ValueError, match=f"{label} scores missing"):
        signed_gaps(*args)


def test_out_of_range_score_raises() -> None:
    with pytest.raises(ValueError, match="out of"):
        signed_gaps({**_flat_scores(), "autonomy": 1.5}, _flat_scores())


def test_non_numeric_score_raises() -> None:
    with pytest.raises(ValueError, match="not a number"):
        signed_gaps({**_flat_scores(), "autonomy": "high"}, _flat_scores())


# ---------------------------------------------------------------------------
# classify_gap: bucket edges, magnitude only (2026-09-10 rename)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dimension", DIMENSIONS)
@pytest.mark.parametrize("sign", [1, -1])
def test_just_inside_the_aligned_threshold_is_aligned(dimension: str, sign: int) -> None:
    gap = sign * (ALIGNED_THRESHOLDS[dimension] - 0.001)

    assert classify_gap(dimension, gap) == ALIGNED


@pytest.mark.parametrize("dimension", DIMENSIONS)
@pytest.mark.parametrize("sign", [1, -1])
def test_exactly_on_the_aligned_threshold_is_notable_regardless_of_sign(
    dimension: str, sign: int
) -> None:
    gap = sign * ALIGNED_THRESHOLDS[dimension]

    assert classify_gap(dimension, gap) == NOTABLE


@pytest.mark.parametrize("dimension", DIMENSIONS)
@pytest.mark.parametrize("sign", [1, -1])
def test_just_inside_the_straining_threshold_is_notable(dimension: str, sign: int) -> None:
    gap = sign * (STRAINING_THRESHOLDS[dimension] - 0.001)

    assert classify_gap(dimension, gap) == NOTABLE


@pytest.mark.parametrize("dimension", DIMENSIONS)
@pytest.mark.parametrize("sign", [1, -1])
def test_exactly_on_the_straining_threshold_is_straining_regardless_of_sign(
    dimension: str, sign: int
) -> None:
    gap = sign * STRAINING_THRESHOLDS[dimension]

    assert classify_gap(dimension, gap) == STRAINING


def test_zero_gap_is_aligned() -> None:
    assert classify_gap("autonomy", 0.0) == ALIGNED


def test_unknown_dimension_raises() -> None:
    with pytest.raises(ValueError, match="Unknown dimension"):
        classify_gap("charisma", 0.5)


# ---------------------------------------------------------------------------
# gap_direction: sign only, None exactly on aligned
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_aligned_gaps_carry_no_direction(dimension: str) -> None:
    gap = ALIGNED_THRESHOLDS[dimension] - 0.001

    assert gap_direction(dimension, gap) is None
    assert gap_direction(dimension, -gap) is None


def test_zero_gap_carries_no_direction() -> None:
    assert gap_direction("autonomy", 0.0) is None


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_positive_non_aligned_gap_is_over(dimension: str) -> None:
    gap = STRAINING_THRESHOLDS[dimension] + 0.05

    assert gap_direction(dimension, gap) == OVER


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_negative_non_aligned_gap_is_under(dimension: str) -> None:
    gap = -(STRAINING_THRESHOLDS[dimension] + 0.05)

    assert gap_direction(dimension, gap) == UNDER


def test_gap_direction_unknown_dimension_raises() -> None:
    with pytest.raises(ValueError, match="Unknown dimension"):
        gap_direction("charisma", 0.5)


# ---------------------------------------------------------------------------
# Threshold grounding: measured through A-1's real item bank, not a
# synthetic fixture, so an item-count or band change there fails loudly here
# instead of silently re-scaling ALIGNED_THRESHOLD underneath. Mirrors
# manager_match.decoder.test_no_single_item_can_manufacture_a_grind.
# ---------------------------------------------------------------------------


def test_no_single_band_move_can_manufacture_a_nonaligned_bucket() -> None:
    situation_items = pytest.importorskip(
        "work_pulse.situation_items",
        reason="A-1 (work_pulse/situation_items.py) not present",
    )

    items = situation_items.ENVIRONMENT_ITEMS
    spec = situation_items.item_spec()
    poles = situation_items.POLES_LOW_TO_HIGH  # low .. high, one step apart

    def key_for_pole(item: dict, pole: str) -> str:
        return next(o["key"] for o in item["options"] if o["pole"] == pole)

    baseline_answers = {item["item_id"]: key_for_pole(item, "mixed") for item in items}
    baseline = score_environment(baseline_answers, spec)

    mid = poles.index("mixed")
    for item in items:
        dim = item["dimension"]
        for neighbor in (poles[mid - 1], poles[mid + 1]):
            moved_answers = {**baseline_answers, item["item_id"]: key_for_pole(item, neighbor)}
            moved = score_environment(moved_answers, spec)
            step = abs(moved[dim] - baseline[dim])
            assert step < ALIGNED_THRESHOLDS[dim], (
                f"{item['item_id']} moves {dim} by {step:.4f} on a single band alone, "
                f"at or past the {ALIGNED_THRESHOLDS[dim]} aligned threshold"
            )


# ---------------------------------------------------------------------------
# rank_dimensions: flat weights, and the weight seam
# ---------------------------------------------------------------------------


def test_flat_ranking_orders_by_gap_magnitude_widest_first() -> None:
    gaps = {
        "autonomy": 0.10,
        "pace": -0.50,
        "collaboration": 0.30,
        "feedback": 0.0,
        "innovation": -0.20,
        "decision": 0.05,
    }

    order = rank_dimensions(gaps)

    assert order == ["pace", "collaboration", "innovation", "autonomy", "decision", "feedback"]


def test_flat_ranking_ties_break_by_dimensions_order() -> None:
    gaps = {dim: 0.3 for dim in DIMENSIONS}

    assert rank_dimensions(gaps) == list(DIMENSIONS)


def test_default_weights_are_flat() -> None:
    gaps = {"autonomy": 0.2, "pace": -0.2, "collaboration": 0.0, "feedback": 0.0,
            "innovation": 0.0, "decision": 0.0}

    assert rank_dimensions(gaps) == rank_dimensions(gaps, weights=None)


def test_non_flat_weights_reorder_the_ranking() -> None:
    """The seam E-5 swaps elicited weights into: a dimension with a smaller
    raw gap but a much larger weight must be able to outrank one with a
    bigger raw gap and a small weight.

    Both gaps sit in the SAME bucket on purpose. Weights only order rows
    within a severity tier -- `test_tier_outranks_weight` pins the outer
    rule -- so a cross-tier fixture here would be testing the tier, not the
    weights.
    """
    gaps = {
        "autonomy": 0.16,   # notable, small gap, big weight below
        "pace": 0.24,       # notable, bigger gap, tiny weight below
        "collaboration": 0.0,
        "feedback": 0.0,
        "innovation": 0.0,
        "decision": 0.0,
    }
    assert classify_gap("autonomy", gaps["autonomy"]) == classify_gap("pace", gaps["pace"])

    flat_order = rank_dimensions(gaps)
    assert flat_order[0] == "pace"

    weights = {**_flat_dimension_weights(), "autonomy": {"mag": -10.0, "dir": 0.0},
               "pace": {"mag": -0.01, "dir": 0.0}}
    weighted_order = rank_dimensions(gaps, weights=weights)

    assert weighted_order[0] == "autonomy"
    assert weighted_order != flat_order


def test_weights_missing_a_dimension_raises() -> None:
    gaps = {dim: 0.0 for dim in DIMENSIONS}
    partial_weights = {d: w for d, w in _flat_dimension_weights().items() if d != "innovation"}

    with pytest.raises(ValueError, match="innovation"):
        rank_dimensions(gaps, weights=partial_weights)


# ---------------------------------------------------------------------------
# rank_dimensions: the severity tier, and E-5's elicited directional weights
# ---------------------------------------------------------------------------


def test_tier_outranks_weight() -> None:
    """D-15 leaves the bucket WORD as the only magnitude a reader sees, so a
    green `aligned` row must never be listed above an amber `straining` one --
    however heavily the expert weighted the aligned dimension. `pace` carries
    the heaviest `mag` in the live priors (-2.52) and `autonomy` the lightest
    (-0.67), which is exactly the pair that would invert under raw cost.
    """
    gaps = {
        "autonomy": 0.30,   # straining, feather-light weight
        "pace": 0.14,       # aligned, heaviest weight in the file
        "collaboration": 0.0, "feedback": 0.0, "innovation": 0.0, "decision": 0.0,
    }
    assert classify_gap("autonomy", gaps["autonomy"]) == STRAINING
    assert classify_gap("pace", gaps["pace"]) == ALIGNED

    weights = _live_dimension_weights()

    # Raw cost alone would put the aligned pace row on top; the tier forbids it.
    assert dimension_cost("pace", gaps["pace"], weights["pace"]) > dimension_cost(
        "autonomy", gaps["autonomy"], weights["autonomy"]
    )

    order = rank_dimensions(gaps, weights=weights)
    assert order[0] == "autonomy"
    assert order.index("autonomy") < order.index("pace")


def test_feedback_costs_more_over_than_under_at_equal_magnitude() -> None:
    """Julie's elicited asymmetry, end to end. She put "wants blunt feedback,
    role gives little" at 7/10 a year on and "wants gentle feedback, role is
    blunt" at 3/10. The costly case is the one where the role supplies MORE
    than the person wants -- `gap = env - person > 0`, i.e. `over`.

    `feedback` has mag -1.732868, dir +1.059122, so at equal |gap| the two
    directions cost (mag + dir) and (mag - dir) respectively. If this comes
    out reversed, the sign convention was flipped somewhere -- the test is
    not the thing to change.
    """
    weights = _live_dimension_weights()
    magnitude = 0.30

    over = dimension_cost("feedback", +magnitude, weights["feedback"])
    under = dimension_cost("feedback", -magnitude, weights["feedback"])

    assert over == pytest.approx((1.732868 + 1.059122) * magnitude)
    assert under == pytest.approx((1.732868 - 1.059122) * magnitude)
    assert over > under

    # ... and the ranking agrees, with both rows in one tier.
    gaps = {
        "autonomy": 0.0, "pace": 0.0, "collaboration": 0.0,
        "feedback": +magnitude, "innovation": -magnitude, "decision": 0.0,
    }
    weights_innovation_as_feedback = {**weights, "innovation": weights["feedback"]}
    order = rank_dimensions(gaps, weights=weights_innovation_as_feedback)
    assert order.index("feedback") < order.index("innovation")


def test_decision_under_costs_nothing_and_sinks_within_its_tier() -> None:
    """`decision` came back mag -0.866434, dir +0.866434 -- her "person-high,
    role-low" answer equalled her own 8-in-10 baseline, so that direction
    carries no cost at all. Exactly 0.0, not nearly: the cheap direction
    cancels the symmetric penalty term by IEEE-exact negation. A real
    elicited answer, not a defect, so it ranks last among its equals rather
    than being floored away.
    """
    weights = _live_dimension_weights()

    assert dimension_cost("decision", -0.30, weights["decision"]) == 0.0
    assert dimension_cost("decision", +0.30, weights["decision"]) > 0.0

    gaps = {dim: -0.30 for dim in DIMENSIONS}  # every dimension straining, under
    order = rank_dimensions(gaps, weights=weights)

    assert order[-1] == "decision"


def test_pace_outranks_autonomy_at_equal_gap_in_one_tier() -> None:
    """The headline consequence of adopting the elicited numbers: pace is the
    dimension she judged most punishing (mag -2.52), autonomy the least
    (-0.67). Under flat weights an identical gap on each ties and falls back
    to DIMENSIONS order, which puts autonomy first.
    """
    gaps = {
        "autonomy": -0.30, "pace": -0.30, "collaboration": 0.0,
        "feedback": 0.0, "innovation": 0.0, "decision": 0.0,
    }
    assert rank_dimensions(gaps)[0] == "autonomy"  # flat: tie -> DIMENSIONS order

    order = rank_dimensions(gaps, weights=_live_dimension_weights())

    assert order[0] == "pace"
    assert order.index("pace") < order.index("autonomy")


def test_default_weights_reproduce_flat_within_tier_ordering() -> None:
    """`weights=None` must be behaviourally identical to an explicit flat
    `{mag: -1.0, dir: 0.0}`, and both must order a single tier by plain
    |gap| regardless of sign.
    """
    gaps = {
        "autonomy": 0.30, "pace": -0.50, "collaboration": 0.40,
        "feedback": -0.26, "innovation": 0.45, "decision": -0.35,
    }
    for dim in DIMENSIONS:
        assert classify_gap(dim, gaps[dim]) == STRAINING

    assert rank_dimensions(gaps) == rank_dimensions(gaps, weights=_flat_dimension_weights())
    assert rank_dimensions(gaps) == ["pace", "innovation", "collaboration",
                                     "decision", "autonomy", "feedback"]


def test_a_weight_that_would_make_a_mismatch_free_money_raises() -> None:
    """`abs(dir) <= abs(mag)` is the invariant that keeps cost non-negative.
    Break it and one direction of mismatch would read as a benefit; that is
    raised, never clamped to zero, so a bad weight cannot masquerade as a
    plausible ranking.
    """
    with pytest.raises(ValueError, match="negative cost"):
        dimension_cost("autonomy", 0.30, {"mag": -1.0, "dir": -2.0})

    bad = {**_flat_dimension_weights(), "autonomy": {"mag": -1.0, "dir": -2.0}}
    with pytest.raises(ValueError, match="negative cost"):
        rank_dimensions({dim: 0.30 for dim in DIMENSIONS}, weights=bad)


def test_zero_gap_costs_nothing_under_any_weight() -> None:
    for dim, weight in _live_dimension_weights().items():
        assert dimension_cost(dim, 0.0, weight) == 0.0


# ---------------------------------------------------------------------------
# build_situation_report: the D-15 payload shape
# ---------------------------------------------------------------------------


def test_report_covers_every_dimension_in_fixed_order() -> None:
    report = build_situation_report(_flat_scores(0.6), _flat_scores(0.6))

    assert [entry["dimension"] for entry in report] == list(DIMENSIONS)


def test_report_env_score_echoes_the_input_exactly() -> None:
    env = {
        "autonomy": 0.80, "pace": 0.25, "collaboration": 0.6625,
        "feedback": 0.3875, "innovation": 0.525, "decision": 0.70,
    }
    report = build_situation_report(env, _flat_scores(0.5))

    for entry in report:
        assert entry["env_score"] == env[entry["dimension"]]


def test_report_rank_matches_rank_dimensions() -> None:
    env = {
        "autonomy": 0.80, "pace": 0.25, "collaboration": 0.6625,
        "feedback": 0.3875, "innovation": 0.525, "decision": 0.70,
    }
    person = _flat_scores(0.525)

    report = build_situation_report(env, person)
    expected_order = rank_dimensions(signed_gaps(env, person))

    by_rank = {entry["rank"]: entry["dimension"] for entry in report}
    assert [by_rank[i] for i in range(len(DIMENSIONS))] == expected_order


def test_report_bucket_matches_classify_gap() -> None:
    env = {
        "autonomy": 0.80, "pace": 0.25, "collaboration": 0.6625,
        "feedback": 0.3875, "innovation": 0.525, "decision": 0.70,
    }
    person = _flat_scores(0.525)

    report = build_situation_report(env, person)
    gaps = signed_gaps(env, person)

    for entry in report:
        assert entry["bucket"] == classify_gap(entry["dimension"], gaps[entry["dimension"]])


def test_report_direction_matches_gap_direction() -> None:
    env = {
        "autonomy": 0.80, "pace": 0.25, "collaboration": 0.6625,
        "feedback": 0.3875, "innovation": 0.525, "decision": 0.70,
    }
    person = _flat_scores(0.525)

    report = build_situation_report(env, person)
    gaps = signed_gaps(env, person)

    for entry in report:
        assert entry["direction"] == gap_direction(entry["dimension"], gaps[entry["dimension"]])
        if entry["bucket"] == ALIGNED:
            assert entry["direction"] is None
        else:
            assert entry["direction"] in (UNDER, OVER)


def test_report_honors_a_custom_weight_seam() -> None:
    # Both movers land in the same bucket (|gap| 0.30 and 0.29, straining), so
    # the weights are what decides between them rather than the severity tier.
    env = {**_flat_scores(0.5), "autonomy": 0.80, "pace": 0.79}
    person = _flat_scores(0.5)
    weights = {**{d: {"mag": -1.0, "dir": 0.0} for d in DIMENSIONS},
               "autonomy": {"mag": -100.0, "dir": 0.0},
               "pace": {"mag": -0.001, "dir": 0.0}}

    report = build_situation_report(env, person, weights=weights)

    assert next(e for e in report if e["rank"] == 0)["dimension"] == "autonomy"


def test_report_entries_carry_no_person_score_or_numeric_gap() -> None:
    """The structural D-15 guarantee: PRODUCT_DECISIONS.md §2 forbids a
    person-side score or a numeric gap anywhere in the payload. `direction`
    is categorical only (`under` / `over` / `None`), never a signed number.
    """
    env = {
        "autonomy": 0.80, "pace": 0.25, "collaboration": 0.6625,
        "feedback": 0.3875, "innovation": 0.525, "decision": 0.70,
    }
    person = _flat_scores(0.1)  # deliberately far from env, to maximize gaps

    report = build_situation_report(env, person)

    for entry in report:
        assert set(entry) == {"dimension", "env_score", "bucket", "direction", "rank"}
        for key, value in entry.items():
            assert "gap" not in key.lower()
            assert "person" not in key.lower()
            if key == "direction":
                assert value in (None, UNDER, OVER)
        assert entry["bucket"] in (ALIGNED, NOTABLE, STRAINING)


def test_report_is_deterministic() -> None:
    env = _flat_scores(0.6)
    person = _flat_scores(0.4)

    assert build_situation_report(env, person) == build_situation_report(env, person)


def test_report_does_not_depend_on_input_dict_ordering() -> None:
    env = {
        "autonomy": 0.80, "pace": 0.25, "collaboration": 0.6625,
        "feedback": 0.3875, "innovation": 0.525, "decision": 0.70,
    }
    person = _flat_scores(0.525)
    shuffled_env = {d: env[d] for d in reversed(DIMENSIONS)}
    shuffled_person = {d: person[d] for d in reversed(DIMENSIONS)}

    assert build_situation_report(shuffled_env, shuffled_person) == build_situation_report(
        env, person
    )


def test_report_missing_environment_dimension_raises() -> None:
    partial_env = {d: 0.5 for d in DIMENSIONS if d != "decision"}

    with pytest.raises(ValueError, match="decision"):
        build_situation_report(partial_env, _flat_scores())
