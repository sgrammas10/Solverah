"""Tests for the environment-side instrument (BUILD_PLAN A-1).

Pure — no Flask, no DB, no network. Idioms from `tests/test_manager_profile.py`:
happy path, per-item arithmetic, straight-lining as the payoff of the balanced
key, then the structural guards that make item or key drift fail loudly rather
than quietly rescale everyone's report.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from work_pulse.situation_items import (
    ASCENDING,
    CONTEXT_COLUMNS,
    CONTEXT_ITEMS,
    DESCENDING,
    DIMENSIONS,
    ENVIRONMENT_ITEMS,
    EXPECTED_CONTEXT_ITEM_COUNT,
    EXPECTED_DIMENSION_ITEM_COUNT,
    FORM_VERSION,
    OPTION_KEYS,
    POLE_VALUES,
    POLES_LOW_TO_HIGH,
    INDUSTRY_ITEM,
    INDUSTRY_LEVELS,
    TENSE_BY_CAREER_STATUS,
    context_level,
    context_value,
    is_categorical,
    is_past_tense,
    item_spec,
    item_list_in_form_order,
    option_score,
    render_context_items,
    render_items,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUBRIC_PATH = REPO_ROOT / "Solverah_IP" / "ground_truth" / "rater_app" / "anchors_v3_PROPOSED.json"

ALL_TEXT_FIELDS = ("text", "text_past")


def _load_rubric() -> dict:
    if not RUBRIC_PATH.exists():
        pytest.skip(f"rubric not present at {RUBRIC_PATH}")
    return json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))


def _item_strings(item: dict) -> list[str]:
    """Every user-facing string on one item, both tenses."""
    out = [item["prompt"], item["prompt_past"]]
    for option in item["options"]:
        out.extend(option[field] for field in ALL_TEXT_FIELDS)
    return out


def _answers_at_position(index: int) -> dict[str, str]:
    """A straight-lined sitting: the same option position on every item."""
    return {item["item_id"]: OPTION_KEYS[index] for item in ENVIRONMENT_ITEMS}


def _dimension_means(answers: dict[str, str]) -> dict[str, float]:
    """mean_pole per dimension — A-3's arithmetic, reproduced locally so these
    tests do not depend on A-3 being importable."""
    by_dim: dict[str, list[float]] = {dim: [] for dim in DIMENSIONS}
    for item in ENVIRONMENT_ITEMS:
        by_dim[item["dimension"]].append(option_score(item["item_id"], answers[item["item_id"]]))
    return {dim: sum(vals) / len(vals) for dim, vals in by_dim.items()}


# ---------------------------------------------------------------------------
# Coverage: the six dimensions, and only those six
# ---------------------------------------------------------------------------

def test_every_dimension_has_at_least_one_item() -> None:
    covered = {item["dimension"] for item in ENVIRONMENT_ITEMS}

    assert covered == set(DIMENSIONS)


def test_dimension_keys_are_exactly_the_six() -> None:
    assert DIMENSIONS == (
        "autonomy", "pace", "collaboration", "feedback", "innovation", "decision",
    )


def test_no_item_names_a_dimension_outside_the_six() -> None:
    for item in ENVIRONMENT_ITEMS:
        assert item["dimension"] in DIMENSIONS, item["item_id"]


def test_items_are_evenly_split_across_dimensions() -> None:
    """Uneven counts would weight one dimension's items more heavily than
    another's inside the same mean, with no design reason for it."""
    counts = Counter(item["dimension"] for item in ENVIRONMENT_ITEMS)

    assert set(counts.values()) == {2}, dict(counts)


def test_item_count_is_in_the_specified_range() -> None:
    # BUILD_PLAN §3.1: "~10-12 items" across the six dimensions.
    assert 10 <= EXPECTED_DIMENSION_ITEM_COUNT <= 12


# ---------------------------------------------------------------------------
# Tripwires against the two authorities this instrument is keyed to
# ---------------------------------------------------------------------------

def test_dimension_keys_match_the_rater_rubric() -> None:
    """The rubric is where the wording comes from; if its keys move, the
    recast items are describing something else."""
    rubric = _load_rubric()

    assert tuple(d["key"] for d in rubric["dimensions"]) == DIMENSIONS


def test_anchor_values_match_the_rubric_band_values() -> None:
    """0.1 / 0.3 / 0.5 / 0.7 / 0.9, unscaled and unshifted — the premise of a
    user's environment score and a rater's company score being one axis."""
    rubric = _load_rubric()

    assert [POLE_VALUES[p] for p in POLES_LOW_TO_HIGH] == rubric["band_values"]


def test_every_dimension_has_five_bands_in_the_rubric() -> None:
    rubric = _load_rubric()

    for dimension in rubric["dimensions"]:
        assert len(dimension["bands"]) == len(POLES_LOW_TO_HIGH), dimension["key"]


def test_dimension_keys_match_the_a3_gap_engine() -> None:
    """A-3 diffs these scores against the person side; a key that exists on one
    side and not the other makes the gap undefined."""
    situation = pytest.importorskip(
        "work_pulse.situation", reason="A-3 (work_pulse/situation.py) not present"
    )

    assert tuple(situation.DIMENSIONS) == DIMENSIONS


# ---------------------------------------------------------------------------
# Anchors -> scores
# ---------------------------------------------------------------------------

def test_pole_values_are_the_five_bands() -> None:
    assert set(POLE_VALUES) == set(POLES_LOW_TO_HIGH)
    assert sorted(POLE_VALUES.values()) == [0.1, 0.3, 0.5, 0.7, 0.9]


def test_option_score_returns_the_bands_value_for_every_option() -> None:
    for item in ENVIRONMENT_ITEMS:
        for option in item["options"]:
            assert option_score(item["item_id"], option["key"]) == pytest.approx(
                POLE_VALUES[option["pole"]]
            ), f"{item['item_id']}/{option['key']}"


def test_every_item_carries_all_five_bands_exactly_once() -> None:
    for item in ENVIRONMENT_ITEMS:
        poles = [o["pole"] for o in item["options"]]
        assert sorted(poles) == sorted(POLES_LOW_TO_HIGH), item["item_id"]


def test_option_keys_are_positional_a_to_e_in_order() -> None:
    for item in ENVIRONMENT_ITEMS:
        assert [o["key"] for o in item["options"]] == list(OPTION_KEYS), item["item_id"]


def test_picking_the_high_band_everywhere_scores_every_dimension_at_the_top() -> None:
    answers = {
        item["item_id"]: next(o["key"] for o in item["options"] if o["pole"] == "high")
        for item in ENVIRONMENT_ITEMS
    }

    for dim, value in _dimension_means(answers).items():
        assert value == pytest.approx(0.9), f"{dim}={value}"


def test_picking_the_low_band_everywhere_scores_every_dimension_at_the_bottom() -> None:
    answers = {
        item["item_id"]: next(o["key"] for o in item["options"] if o["pole"] == "low")
        for item in ENVIRONMENT_ITEMS
    }

    for dim, value in _dimension_means(answers).items():
        assert value == pytest.approx(0.1), f"{dim}={value}"


def test_a_dimension_moves_independently_of_the_others() -> None:
    answers = {
        item["item_id"]: next(o["key"] for o in item["options"] if o["pole"] == "mixed")
        for item in ENVIRONMENT_ITEMS
    }
    base = _dimension_means(answers)

    autonomy_item = next(i for i in ENVIRONMENT_ITEMS if i["dimension"] == "autonomy")
    answers[autonomy_item["item_id"]] = next(
        o["key"] for o in autonomy_item["options"] if o["pole"] == "high"
    )
    moved = _dimension_means(answers)

    assert moved["autonomy"] == pytest.approx((0.9 + 0.5) / 2)
    for dim in DIMENSIONS:
        if dim != "autonomy":
            assert moved[dim] == pytest.approx(base[dim])


@pytest.mark.parametrize("position", range(len(OPTION_KEYS)))
def test_dimension_scores_stay_in_range(position: int) -> None:
    for dim, value in _dimension_means(_answers_at_position(position)).items():
        assert 0.0 <= value <= 1.0, f"{dim}={value}"


# ---------------------------------------------------------------------------
# Anchor-order balance: the payoff, and the property that buys it
# ---------------------------------------------------------------------------

def test_anchor_order_matches_the_declared_direction() -> None:
    for item in ENVIRONMENT_ITEMS:
        poles = [o["pole"] for o in item["options"]]
        expected = (
            list(POLES_LOW_TO_HIGH)
            if item["anchor_order"] == ASCENDING
            else list(reversed(POLES_LOW_TO_HIGH))
        )
        assert poles == expected, item["item_id"]


def test_anchor_order_is_balanced_within_every_dimension() -> None:
    by_dimension: dict[str, Counter] = {}
    for item in ENVIRONMENT_ITEMS:
        by_dimension.setdefault(item["dimension"], Counter())[item["anchor_order"]] += 1

    for dim, orders in by_dimension.items():
        assert orders[ASCENDING] == orders[DESCENDING] == 1, f"{dim}: {dict(orders)}"


def test_anchor_order_is_balanced_overall() -> None:
    orders = Counter(item["anchor_order"] for item in ENVIRONMENT_ITEMS)

    assert orders[ASCENDING] == orders[DESCENDING], dict(orders)


@pytest.mark.parametrize("position", range(len(OPTION_KEYS)))
def test_straight_lining_any_position_lands_every_dimension_on_the_midpoint(
    position: int,
) -> None:
    """What the balanced anchor order is for. A respondent who picks the first
    option throughout — or the last, or the middle — produces 0.5 on all six
    dimensions, so satisficing reads as no signal instead of as an extreme
    profile. `manager_profile.py`'s midpoint property, on a five-point scale.
    """
    for dim, value in _dimension_means(_answers_at_position(position)).items():
        assert value == pytest.approx(0.5), f"position {OPTION_KEYS[position]}: {dim}={value}"


# ---------------------------------------------------------------------------
# Tense variants
# ---------------------------------------------------------------------------

def test_career_status_vocabulary_is_the_apps_own() -> None:
    assert set(TENSE_BY_CAREER_STATUS) == {"employed", "between_jobs", "first_job"}


def test_employed_is_present_tense_and_the_other_two_are_past() -> None:
    assert is_past_tense("employed") is False
    assert is_past_tense("between_jobs") is True
    assert is_past_tense("first_job") is True


def test_unknown_career_status_raises() -> None:
    with pytest.raises(ValueError, match="career_status"):
        is_past_tense("retired")


# A past-job report (PRODUCT_DECISIONS.md §2, 2026-10-01) describes a job the
# user has left, so it is past tense even for an employed user.
@pytest.mark.parametrize(
    "career_status, subject, expected",
    [
        ("employed", "current", False),
        ("between_jobs", "current", True),
        ("first_job", "current", True),
        ("employed", "past", True),
        ("between_jobs", "past", True),
    ],
)
def test_is_past_tense_for_subject(career_status, subject, expected) -> None:
    from work_pulse.situation_items import is_past_tense_for

    assert is_past_tense_for(career_status, subject) is expected


def test_is_past_tense_for_defaults_to_current_and_validates_both_args() -> None:
    from work_pulse.situation_items import is_past_tense_for

    assert is_past_tense_for("employed") is False
    with pytest.raises(ValueError, match="career_status"):
        is_past_tense_for("retired", "past")
    with pytest.raises(ValueError, match="subject"):
        is_past_tense_for("employed", "previous")


def test_past_context_stems_do_not_assume_the_last_job() -> None:
    """A past-job report is about the job BEFORE the most recent one, so a stem that
    says "the organization you last worked for" names the wrong job for it."""
    for item in CONTEXT_ITEMS + ENVIRONMENT_ITEMS:
        assert "last worked" not in item["prompt_past"], item["item_id"]


def test_every_item_carries_both_tense_variants_non_empty() -> None:
    for item in ENVIRONMENT_ITEMS + CONTEXT_ITEMS:
        assert item["prompt"].strip(), item["item_id"]
        assert item["prompt_past"].strip(), item["item_id"]
        for option in item["options"]:
            for field in ALL_TEXT_FIELDS:
                assert option[field].strip(), f"{item['item_id']}: {field}"


def test_tense_variants_render_the_same_items_in_the_same_order() -> None:
    present = render_items("employed")
    past = render_items("between_jobs")

    assert [i["item_id"] for i in present] == [i["item_id"] for i in past]
    assert [i["dimension"] for i in present] == [i["dimension"] for i in past]
    for p, q in zip(present, past):
        assert [o["key"] for o in p["options"]] == [o["key"] for o in q["options"]]


def test_tense_never_changes_a_score() -> None:
    """The whole point of keying the score to `pole` and never to the wording:
    the same answer from an employed and a between-jobs user scores alike."""
    for item in ENVIRONMENT_ITEMS:
        for option in item["options"]:
            assert option_score(item["item_id"], option["key"]) == pytest.approx(
                POLE_VALUES[option["pole"]]
            )

    employed = {e["item_id"]: e for e in item_spec("employed")}
    between = {e["item_id"]: e for e in item_spec("between_jobs")}

    assert set(employed) == set(between)
    for item_id, entry in employed.items():
        other = between[item_id]
        assert entry["dimension"] == other["dimension"]
        assert entry["pole_values"] == other["pole_values"]


def test_between_jobs_and_first_job_render_identically() -> None:
    assert render_items("between_jobs") == render_items("first_job")
    assert render_context_items("between_jobs") == render_context_items("first_job")


def test_rendered_items_expose_one_tense_only() -> None:
    """A renderer that can see both variants can show the wrong one."""
    for item in render_items("employed") + render_items("between_jobs"):
        assert "prompt_past" not in item
        for option in item["options"]:
            assert set(option) == {"key", "text"}


def test_past_tense_prompts_differ_from_present_tense_prompts() -> None:
    """Every stem is tensed, so an identical pair means a variant was missed.

    Option texts are exempt: a few anchors are tense-neutral fragments
    ("Somewhat below.") where an artificial difference would be worse writing.
    """
    for item in ENVIRONMENT_ITEMS + CONTEXT_ITEMS:
        assert item["prompt"] != item["prompt_past"], item["item_id"]


def test_render_items_rejects_an_unknown_career_status() -> None:
    with pytest.raises(ValueError):
        render_items("freelance")


# ---------------------------------------------------------------------------
# The four non-dimension items
# ---------------------------------------------------------------------------

def test_context_items_are_the_four_the_model_lane_expects() -> None:
    """Order is load-bearing: `industry` sits with the context facts, after
    `comp`, and `experienced` (the outcome) stays last."""
    assert [i["item_id"] for i in CONTEXT_ITEMS] == [
        "stage_size", "comp", "industry", "experienced",
    ]
    assert EXPECTED_CONTEXT_ITEM_COUNT == 4


def _ordinal_context_items() -> list:
    return [i for i in CONTEXT_ITEMS if not is_categorical(i)]


def test_context_items_are_one_to_five_in_natural_order() -> None:
    for item in _ordinal_context_items():
        values = [o["value"] for o in item["options"]]
        if item["item_id"] == "comp":
            # comp's sixth option is "not sure" -> None, kept last so the 1..5
            # ordinal scale itself is untouched (PRODUCT_DECISIONS.md §2,
            # 2026-09-10).
            assert values == [1, 2, 3, 4, 5, None], item["item_id"]
        else:
            assert values == [1, 2, 3, 4, 5], item["item_id"]


def test_context_columns_cover_every_context_item() -> None:
    """A-2's `environment_reports` columns; `experienced` is the one rename."""
    assert set(CONTEXT_COLUMNS) == {i["item_id"] for i in CONTEXT_ITEMS}
    assert CONTEXT_COLUMNS["experienced"] == "experienced_outcome"


def test_context_value_accepts_the_whole_scale() -> None:
    for item in _ordinal_context_items():
        for value in (1, 2, 3, 4, 5):
            assert context_value(item["item_id"], value) == value


@pytest.mark.parametrize("value", [0, 6, -1])
def test_context_value_rejects_out_of_range(value: int) -> None:
    with pytest.raises(ValueError, match="no option with value"):
        context_value("comp", value)


@pytest.mark.parametrize("value", [True, 3.0, "3", None])
def test_context_value_rejects_non_ints(value: object) -> None:
    with pytest.raises(ValueError, match="must be an int"):
        context_value("stage_size", value)


def test_context_value_rejects_an_unknown_item() -> None:
    with pytest.raises(ValueError, match="Unknown context item"):
        context_value("tenure", 3)
    with pytest.raises(ValueError, match="Unknown context item"):
        context_level("tenure", "tech")


# -- industry: the one categorical context item (PRODUCT_DECISIONS.md §2, 2026-10-01)

def _model_config_industry_levels() -> list[str]:
    import yaml

    cfg = yaml.safe_load(
        (REPO_ROOT / "causal_graph" / "v1_model" / "solverah_model_config.yaml").read_text(
            encoding="utf-8"
        )
    )
    return next(c for c in cfg["confounders"] if c["key"] == "industry")["levels"]


def test_industry_options_are_exactly_the_model_config_levels_then_not_sure() -> None:
    """The model indexes a per-level weight by position in the config's list,
    so the stored keys must be the config's keys, in its order. "Not sure"
    (None) is last and is NOT the `other` level."""
    values = [o["value"] for o in INDUSTRY_ITEM["options"]]
    assert values[:-1] == _model_config_industry_levels()
    assert values[-1] is None
    assert tuple(values[:-1]) == INDUSTRY_LEVELS


def test_industry_is_categorical_and_the_others_are_not() -> None:
    assert [i["item_id"] for i in CONTEXT_ITEMS if is_categorical(i)] == ["industry"]


@pytest.mark.parametrize("level", ["tech", "finance", "healthcare", "retail", "other"])
def test_context_level_accepts_every_industry_level(level: str) -> None:
    assert context_level("industry", level) == level


def test_industry_accepts_not_sure_as_none() -> None:
    assert context_level("industry", None) is None


@pytest.mark.parametrize("value", ["Tech", "crypto", "", 1, True])
def test_context_level_rejects_anything_but_a_level(value: object) -> None:
    with pytest.raises(ValueError, match="industry"):
        context_level("industry", value)  # type: ignore[arg-type]


def test_the_two_validators_refuse_each_others_items() -> None:
    with pytest.raises(ValueError, match="categorical"):
        context_value("industry", None)
    with pytest.raises(ValueError, match="ordinal"):
        context_level("comp", None)


def test_industry_sits_with_the_context_facts_far_from_the_outcome() -> None:
    ids = [i["item_id"] for i in CONTEXT_ITEMS]
    assert ids.index("industry") == ids.index("comp") + 1
    assert ids[-1] == "experienced"


def test_comp_accepts_not_sure_as_none() -> None:
    """PRODUCT_DECISIONS.md §2, "Environment-instrument rulings" (2026-09-10):
    comp's "not sure" option stores None rather than a guessed posture."""
    assert context_value("comp", None) is None


@pytest.mark.parametrize("item_id", ["stage_size", "experienced"])
def test_only_comp_accepts_none(item_id: str) -> None:
    """The nullability is comp's alone -- stage_size and experienced still
    reject None exactly as they reject any other non-int."""
    with pytest.raises(ValueError, match="must be an int"):
        context_value(item_id, None)


def test_comp_item_is_market_relative_and_asks_for_no_figure() -> None:
    """`schema.sql`: comp is a 1..5 market-relative posture, NOT dollars."""
    comp = next(i for i in CONTEXT_ITEMS if i["item_id"] == "comp")
    blob = " ".join(_item_strings(comp)).lower()

    assert "elsewhere" in comp["prompt"].lower()
    assert "at market" in blob
    for forbidden in ("salary", "$", "per year", "annual", "usd", "how much do you earn"):
        assert forbidden not in blob, forbidden


def test_experienced_is_the_only_evaluative_item_and_it_is_last() -> None:
    assert CONTEXT_ITEMS[-1]["item_id"] == "experienced"
    assert "how well" in CONTEXT_ITEMS[-1]["prompt"].lower()


# ---------------------------------------------------------------------------
# Cross-dimension bleed: the rubric's keep_distinct guardrails, enforced on
# the user-facing wording rather than only on raters
# ---------------------------------------------------------------------------

#: Substrings that must not appear in a given dimension's items, each drawn
#: from that dimension's own `keep_distinct` in the rubric. These are the
#: collisions two blind raters actually produced; an item that reintroduces one
#: reintroduces it for every user at once.
FORBIDDEN_BY_DIMENSION: dict[str, tuple[str, ...]] = {
    # decision rights, not meeting density and not novelty
    "autonomy": ("pairing", "meeting", "cross-functional", "metrics", "data-driven", "invent", "novel"),
    # tempo, not novelty
    "pace": ("invent", "novel", "experiment", "0-to-1", "new capabilit"),
    # how much joint work happens; never decision rights, never critique or warmth
    "collaboration": ("decision", "decide", "sign-off", "approval", "permission", "feedback", "critic", "supportive"),
    # critique delivery and frequency ONLY — the round-1 collision list
    "feedback": (
        "support", "recognition", "mentor", "career", "psychological", "nurtur",
        "retaliat", "response time", "cross-functional", "pairing",
    ),
    # novelty of the work; never speed, never how prescribed the method is
    "innovation": ("deadline", "urgent", "fast", "tempo", "approval", "sign-off", "guardrail", "brief"),
    # what a decision rests on; never who has the authority to make it
    "decision": ("approval", "sign-off", "permission", "ownership", "own the", "guardrail"),
}


def test_no_item_reintroduces_a_bleed_its_rubric_guardrail_names() -> None:
    for item in ENVIRONMENT_ITEMS:
        blob = " ".join(_item_strings(item)).lower()
        for forbidden in FORBIDDEN_BY_DIMENSION[item["dimension"]]:
            assert forbidden not in blob, (
                f"{item['item_id']} ({item['dimension']}) uses {forbidden!r}, which its "
                "rubric keep_distinct assigns to another dimension"
            )


def test_the_forbidden_lists_cover_every_dimension() -> None:
    assert set(FORBIDDEN_BY_DIMENSION) == set(DIMENSIONS)


def test_no_dimension_item_asks_the_user_to_evaluate_the_job() -> None:
    """Twelve descriptive items; `experienced` carries the whole verdict."""
    for item in ENVIRONMENT_ITEMS:
        blob = " ".join(_item_strings(item)).lower()
        for forbidden in ("how happy", "how satisfied", "do you like", "how well is this working"):
            assert forbidden not in blob, f"{item['item_id']}: {forbidden!r}"


# ---------------------------------------------------------------------------
# Structural guards — item and key drift must fail loudly
# ---------------------------------------------------------------------------

def test_item_ids_are_unique() -> None:
    ids = [i["item_id"] for i in ENVIRONMENT_ITEMS] + [i["item_id"] for i in CONTEXT_ITEMS]

    assert len(ids) == len(set(ids))


def test_item_ids_are_stable_and_name_their_dimension() -> None:
    """Stored in `EnvironmentReport.raw_answers` as keys, so renaming one
    orphans every row already written under the old id."""
    for item in ENVIRONMENT_ITEMS:
        assert item["item_id"].startswith(f"env-{item['dimension']}-"), item["item_id"]


def test_the_item_list_is_written_in_form_order() -> None:
    assert item_list_in_form_order() == ENVIRONMENT_ITEMS


def test_form_order_groups_dimensions_in_the_declared_order() -> None:
    seen: list[str] = []
    for item in item_list_in_form_order():
        if not seen or seen[-1] != item["dimension"]:
            seen.append(item["dimension"])

    assert tuple(seen) == DIMENSIONS


def test_every_option_within_an_item_is_distinct() -> None:
    for item in ENVIRONMENT_ITEMS + CONTEXT_ITEMS:
        for field in ALL_TEXT_FIELDS:
            texts = [o[field] for o in item["options"]]
            assert len(texts) == len(set(texts)), f"{item['item_id']}: {field}"


def test_every_prompt_is_a_question() -> None:
    for item in ENVIRONMENT_ITEMS + CONTEXT_ITEMS:
        assert item["prompt"].endswith("?"), item["item_id"]
        assert item["prompt_past"].endswith("?"), item["item_id"]


def test_option_score_rejects_unknown_ids_and_keys() -> None:
    with pytest.raises(ValueError, match="Unknown item id"):
        option_score("env-autonomy-9", "a")
    with pytest.raises(ValueError, match="no option"):
        option_score("env-autonomy-1", "f")


def test_context_items_are_not_scored_as_dimensions() -> None:
    """`stage_size`, `comp` and `experienced` are a confounder, a confounder and
    the outcome node — none of them belongs in a dimension mean."""
    scored_ids = {entry["item_id"] for entry in item_spec()}

    for item in CONTEXT_ITEMS:
        assert item["item_id"] not in scored_ids
        with pytest.raises(ValueError, match="Unknown item id"):
            option_score(item["item_id"], "a")


def test_form_version_is_set() -> None:
    """`EnvironmentReport.version` — a stored row must say which item set
    produced it, or a later item change silently rescores history."""
    assert FORM_VERSION.startswith("env-v")
    assert len(FORM_VERSION) > len("env-v")


# ---------------------------------------------------------------------------
# The A-3 seam
# ---------------------------------------------------------------------------

def test_item_spec_has_one_entry_per_dimension_item() -> None:
    spec = item_spec()

    assert [e["item_id"] for e in spec] == [i["item_id"] for i in ENVIRONMENT_ITEMS]
    assert [e["dimension"] for e in spec] == [i["dimension"] for i in ENVIRONMENT_ITEMS]


def test_item_spec_carries_one_anchor_value_per_option_key() -> None:
    for entry in item_spec():
        assert set(entry["pole_values"]) == set(OPTION_KEYS), entry["item_id"]
        assert sorted(entry["pole_values"].values()) == [0.1, 0.3, 0.5, 0.7, 0.9]
        for key, value in entry["pole_values"].items():
            assert option_score(entry["item_id"], key) == pytest.approx(value)


def test_item_spec_is_a_copy_not_the_module_literal() -> None:
    spec = item_spec()
    spec[0]["pole_values"]["a"] = 99.0

    assert option_score(ENVIRONMENT_ITEMS[0]["item_id"], "a") != 99.0


def test_a3_scores_the_real_twelve_item_environment_bank_end_to_end() -> None:
    """The real A-1/A-3 seam, proven — not the tombstone this used to be.

    `test_a3_cannot_yet_score_a_five_band_instrument` asserted A-3 could not
    yet consume this instrument. Resolved 2026-09-10 (reconciliation pass):
    A-3's `score_environment` was already generalized to a `pole_values`
    mapping by the time this instrument landed — it never assumed a
    two-anchor `(low, high)` pair. The only real gap was `item_spec()`
    emitting that mapping under a different key (`anchor_values`); renamed to
    `pole_values` above to close it. This is the real end-to-end assertion
    the tombstone's docstring promised, run against the real twelve items
    rather than a synthetic fixture.
    """
    situation = pytest.importorskip(
        "work_pulse.situation", reason="A-3 (work_pulse/situation.py) not present"
    )
    answers = {
        item["item_id"]: OPTION_KEYS[i % len(OPTION_KEYS)]
        for i, item in enumerate(ENVIRONMENT_ITEMS)
    }

    scores = situation.score_environment(answers, item_spec())

    assert scores == pytest.approx(_dimension_means(answers))


def test_item_spec_conforms_to_what_a3_actually_requires() -> None:
    """Spec conformance: everything `item_spec()` emits is something A-3's
    `score_environment` accepts — all twelve environment items, all six
    dimensions, every pole token at every straight-lined position scorable,
    and tense variants scoring identically end to end (not just at the
    `pole_values` level `test_tense_never_changes_a_score` already checks).
    """
    situation = pytest.importorskip(
        "work_pulse.situation", reason="A-3 (work_pulse/situation.py) not present"
    )

    spec = item_spec()
    assert {e["item_id"] for e in spec} == {i["item_id"] for i in ENVIRONMENT_ITEMS}
    assert {e["dimension"] for e in spec} == set(situation.DIMENSIONS) == set(DIMENSIONS)

    for position in range(len(OPTION_KEYS)):
        answers = _answers_at_position(position)
        scores = situation.score_environment(answers, item_spec())
        assert scores == pytest.approx(_dimension_means(answers)), (
            f"position {OPTION_KEYS[position]}"
        )

    answers = _answers_at_position(0)
    employed_scores = situation.score_environment(answers, item_spec("employed"))
    between_scores = situation.score_environment(answers, item_spec("between_jobs"))
    assert employed_scores == between_scores
