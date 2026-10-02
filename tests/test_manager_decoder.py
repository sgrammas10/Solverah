"""Tests for the Manager Decoder diff rule and playbook assembly (C-2)."""
from __future__ import annotations

from itertools import combinations, product

import pytest

from manager_match.decoder import (
    ACUTE,
    ACUTE_THRESHOLDS,
    DIMENSIONS,
    GRIND,
    MESH,
    MESH_THRESHOLDS,
    NOTABLE,
    OVER_SUPPLIED,
    UNDER_SUPPLIED,
    build_playbook,
    classify_dimension,
    decode,
    diff_profiles,
)
from manager_match.manager_profile import (
    MANAGER_PROFILE_QUESTIONS,
    score_manager_profile,
)
from manager_match.playbook_content import (
    CONSTRAINT_NOTES,
    MESH_NOTES,
    PRIVACY_NOTICE,
    PROTOCOL_CELLS,
)
from manager_match.questions import QUESTIONS
from manager_match.score import score_manager_match

DIRECTIONS = (OVER_SUPPLIED, UNDER_SUPPLIED)
SEVERITIES = (NOTABLE, ACUTE)
BANDS = ("low", "mid", "high")


# ---------------------------------------------------------------------------
# Helpers: reach the scores the way production does — through the scorers.
# ---------------------------------------------------------------------------

def _high_choice(question: dict) -> str:
    return "a" if question["score_a"] > question["score_b"] else "b"


def _low_choice(question: dict) -> str:
    return "b" if question["score_a"] > question["score_b"] else "a"


def _answers(questions: list[dict], high_ids: set[str]) -> list[dict]:
    """A full sitting where every id in `high_ids` takes its high pole."""
    return [
        {
            "question_id": q["question_id"],
            "choice": _high_choice(q) if q["question_id"] in high_ids else _low_choice(q),
        }
        for q in questions
    ]


def _achievable(questions: list[dict], scorer, dimension: str) -> list[float]:
    """Every dimension mean this instrument can actually produce.

    Enumerates all subsets of the dimension's own items rather than assuming a
    uniform step — `mm-q10` (0.70/0.30) and `mm-q14` (0.75/0.25) are not on the
    same anchors as the rest.
    """
    ids = [q["question_id"] for q in questions if q["dimension"] == dimension]
    values = set()
    for size in range(len(ids) + 1):
        for combo in combinations(ids, size):
            scores = scorer(_answers(questions, set(combo)))["dimension_scores"]
            values.add(round(scores[dimension], 6))
    return sorted(values)


def _user_scores(**overrides: float) -> dict[str, float]:
    return {dim: overrides.get(dim, 0.525) for dim in DIMENSIONS}


def _manager_scores(**overrides: float) -> dict[str, float]:
    return {dim: overrides.get(dim, 0.525) for dim in DIMENSIONS}


# ---------------------------------------------------------------------------
# The diff rule, per dimension, both directions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_identical_profiles_mesh_on_every_dimension(dimension: str) -> None:
    verdict = classify_dimension(dimension, 0.525, 0.525)

    assert verdict["classification"] == MESH
    assert verdict["direction"] is None
    assert verdict["severity"] is None
    assert verdict["gap"] == pytest.approx(0.0)


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_manager_above_need_is_over_supplied(dimension: str) -> None:
    """Manager runs higher on the dimension than the user needs."""
    verdict = classify_dimension(dimension, 0.25, 0.80)

    assert verdict["classification"] == GRIND
    assert verdict["direction"] == OVER_SUPPLIED
    assert verdict["gap"] == pytest.approx(0.55)


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_manager_below_need_is_under_supplied(dimension: str) -> None:
    verdict = classify_dimension(dimension, 0.80, 0.25)

    assert verdict["classification"] == GRIND
    assert verdict["direction"] == UNDER_SUPPLIED
    assert verdict["gap"] == pytest.approx(-0.55)


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_direction_is_symmetric_about_the_gap_sign(dimension: str) -> None:
    over = classify_dimension(dimension, 0.30, 0.80)
    under = classify_dimension(dimension, 0.80, 0.30)

    assert over["direction"] == OVER_SUPPLIED
    assert under["direction"] == UNDER_SUPPLIED
    assert over["gap"] == pytest.approx(-under["gap"])
    assert over["severity"] == under["severity"]


def test_one_dimension_grinding_leaves_the_others_meshing() -> None:
    verdicts = diff_profiles(
        _user_scores(autonomy=0.80), _manager_scores(autonomy=0.25)
    )
    by_dim = {v["dimension"]: v for v in verdicts}

    assert by_dim["autonomy"]["classification"] == GRIND
    for dim in ("feedback_style", "relationship", "growth_focus"):
        assert by_dim[dim]["classification"] == MESH


def test_diff_returns_every_dimension_in_a_fixed_order() -> None:
    verdicts = diff_profiles(_user_scores(), _manager_scores())

    assert [v["dimension"] for v in verdicts] == list(DIMENSIONS)


# ---------------------------------------------------------------------------
# Threshold edges
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dimension", DIMENSIONS)
@pytest.mark.parametrize("sign", [1, -1])
def test_just_inside_the_mesh_threshold_is_a_mesh(dimension: str, sign: int) -> None:
    gap = sign * (MESH_THRESHOLDS[dimension] - 0.001)
    verdict = classify_dimension(dimension, 0.525, 0.525 + gap)

    assert verdict["classification"] == MESH


@pytest.mark.parametrize("dimension", DIMENSIONS)
@pytest.mark.parametrize("sign", [1, -1])
def test_exactly_on_the_mesh_threshold_is_a_grind(dimension: str, sign: int) -> None:
    """The band is `|gap| < threshold`; the boundary itself grinds."""
    gap = sign * MESH_THRESHOLDS[dimension]
    verdict = classify_dimension(dimension, 0.525, 0.525 + gap)

    assert verdict["classification"] == GRIND
    assert verdict["severity"] == NOTABLE


@pytest.mark.parametrize("dimension", DIMENSIONS)
@pytest.mark.parametrize("sign", [1, -1])
def test_just_inside_the_acute_threshold_is_notable(dimension: str, sign: int) -> None:
    gap = sign * (ACUTE_THRESHOLDS[dimension] - 0.001)
    verdict = classify_dimension(dimension, 0.400, 0.400 + gap)

    assert verdict["classification"] == GRIND
    assert verdict["severity"] == NOTABLE


@pytest.mark.parametrize("dimension", DIMENSIONS)
@pytest.mark.parametrize("sign", [1, -1])
def test_exactly_on_the_acute_threshold_is_acute(dimension: str, sign: int) -> None:
    gap = sign * ACUTE_THRESHOLDS[dimension]
    verdict = classify_dimension(dimension, 0.400, 0.400 + gap)

    assert verdict["severity"] == ACUTE


def test_relationship_carries_a_wider_mesh_band_than_the_others() -> None:
    """Its user side has three items, so one item moves it further."""
    for dim in ("autonomy", "feedback_style", "growth_focus"):
        assert MESH_THRESHOLDS["relationship"] > MESH_THRESHOLDS[dim]


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_no_single_item_can_manufacture_a_grind(dimension: str) -> None:
    """The stated reason the thresholds are the numbers they are.

    Flipping one answer on either instrument must never, by itself, push a
    dimension out of the mesh band. If an instrument gains or loses an item and
    this goes red, the threshold needs a deliberate revisit — not a nudge.
    """
    for questions, scorer, label in (
        (QUESTIONS, score_manager_match, "manager-match"),
        (MANAGER_PROFILE_QUESTIONS, score_manager_profile, "manager-profile"),
    ):
        ids = [q["question_id"] for q in questions if q["dimension"] == dimension]
        baseline = scorer(_answers(questions, set()))["dimension_scores"][dimension]
        for qid in ids:
            moved = scorer(_answers(questions, {qid}))["dimension_scores"][dimension]
            step = abs(moved - baseline)
            assert step < MESH_THRESHOLDS[dimension], (
                f"{label} {qid} moves {dimension} by {step:.4f}, at or past the "
                f"{MESH_THRESHOLDS[dimension]} mesh threshold"
            )


def test_finding_7_contamination_cannot_manufacture_a_relationship_grind() -> None:
    """The historical reason `relationship` gets the conservative threshold — now a tripwire.

    Finding 7 named a real defect: `mm-q11` used to key distance high while
    `mm-q9`/`mm-q10` keyed closeness and advocacy high, so a user whose
    relational need was genuinely high could answer `mm-q11` toward "hard to
    reach" and have their user-side score depressed for reasons unrelated to
    the construct. That keying was corrected 2026-09-10 (C-1c, `bf0f533`) —
    `mm-q11` now keys the same direction as the other two — so the scenario
    below is no longer live. It stays as a tripwire: one relationship item
    disagreeing with the other two, the shape Finding 7's bug produced, must
    still not be enough, by itself, to turn a mesh into a grind — whether that
    disagreement comes from ordinary variance or a future keying mistake like
    the one this fixes.
    """
    relationship_ids = {
        q["question_id"] for q in QUESTIONS if q["dimension"] == "relationship"
    }
    clean = score_manager_match(_answers(QUESTIONS, relationship_ids))
    contaminated = score_manager_match(
        _answers(QUESTIONS, relationship_ids - {"mm-q11"})
    )
    need_clean = clean["dimension_scores"]["relationship"]
    need_contaminated = contaminated["dimension_scores"]["relationship"]

    assert need_contaminated < need_clean, "mm-q11 is expected to be load-bearing"

    # A manager whose style exactly matches the user's true (clean) need.
    verdict = classify_dimension("relationship", need_contaminated, need_clean)

    assert verdict["classification"] == MESH, (
        f"mm-q11 alone moved relationship by {abs(verdict['gap']):.4f}, past the "
        f"{MESH_THRESHOLDS['relationship']} threshold — the diff would report a "
        f"grind that only the contaminated item produced"
    )


# ---------------------------------------------------------------------------
# Assembly: determinism
# ---------------------------------------------------------------------------

_MIXED_USER = {
    "autonomy": 0.80,
    "feedback_style": 0.25,
    "relationship": 0.525,
    "growth_focus": 0.6625,
}
_MIXED_MANAGER = {
    "autonomy": 0.25,
    "feedback_style": 0.6625,
    "relationship": 0.525,
    "growth_focus": 0.3875,
}


def test_the_same_profile_pair_assembles_identically_twice() -> None:
    first = build_playbook(_MIXED_USER, _MIXED_MANAGER)
    second = build_playbook(_MIXED_USER, _MIXED_MANAGER)

    assert first == second


def test_assembly_does_not_depend_on_input_dict_ordering() -> None:
    shuffled_user = {d: _MIXED_USER[d] for d in reversed(DIMENSIONS)}
    shuffled_manager = {d: _MIXED_MANAGER[d] for d in reversed(DIMENSIONS)}

    assert build_playbook(shuffled_user, shuffled_manager) == build_playbook(
        _MIXED_USER, _MIXED_MANAGER
    )


def test_assembled_lists_are_copies_not_the_stored_content() -> None:
    """A caller mutating a playbook must not edit the content for everyone."""
    playbook = build_playbook(_MIXED_USER, _MIXED_MANAGER)
    grind = next(e for e in playbook["dimensions"] if e["classification"] == GRIND)
    original = list(grind["agenda"])

    grind["agenda"].append("mutated")

    assert build_playbook(_MIXED_USER, _MIXED_MANAGER)["dimensions"][0]["agenda"] != [
        *original,
        "mutated",
    ]
    for cell in PROTOCOL_CELLS.values():
        assert "mutated" not in cell["agenda"]


def test_playbook_covers_all_four_dimensions_and_counts_them() -> None:
    playbook = build_playbook(_MIXED_USER, _MIXED_MANAGER)

    assert [e["dimension"] for e in playbook["dimensions"]] == list(DIMENSIONS)
    assert playbook["grind_count"] + playbook["mesh_count"] == len(DIMENSIONS)
    assert playbook["grind_count"] == 3
    assert playbook["mesh_count"] == 1


def test_priority_orders_grinds_widest_gap_first() -> None:
    playbook = build_playbook(_MIXED_USER, _MIXED_MANAGER)
    gaps = {e["dimension"]: abs(e["gap"]) for e in playbook["dimensions"]}

    assert playbook["priority"] == sorted(
        playbook["priority"], key=lambda d: -gaps[d]
    )
    assert set(playbook["priority"]) == {
        e["dimension"] for e in playbook["dimensions"] if e["classification"] == GRIND
    }


def test_priority_breaks_ties_by_fixed_dimension_order() -> None:
    """Equal gaps must not order by dict iteration."""
    user = {dim: 0.80 for dim in DIMENSIONS}
    manager = {dim: 0.25 for dim in DIMENSIONS}

    assert build_playbook(user, manager)["priority"] == list(DIMENSIONS)


def test_a_full_mesh_produces_no_grinds_and_still_renders() -> None:
    playbook = build_playbook(_user_scores(), _manager_scores())

    assert playbook["grind_count"] == 0
    assert playbook["priority"] == []
    assert all(e["classification"] == MESH for e in playbook["dimensions"])
    assert all(e["note"].strip() for e in playbook["dimensions"])


# ---------------------------------------------------------------------------
# Assembly: content resolution
# ---------------------------------------------------------------------------

def test_a_grind_entry_carries_the_whole_protocol_cell() -> None:
    entry = build_playbook(
        _user_scores(autonomy=0.80), _manager_scores(autonomy=0.25)
    )["dimensions"][0]

    assert entry["classification"] == GRIND
    assert entry["direction"] == UNDER_SUPPLIED
    for field in ("headline", "why", "ask"):
        assert entry[field].strip()
    assert len(entry["agenda"]) >= 2
    assert len(entry["scripts"]) >= 2


def test_a_mesh_entry_carries_a_note_and_no_protocol() -> None:
    entry = build_playbook(_user_scores(), _manager_scores())["dimensions"][0]

    assert entry["note"].strip()
    assert "ask" not in entry
    assert "scripts" not in entry


def test_the_privacy_line_is_on_every_playbook() -> None:
    for user, manager in (
        (_user_scores(), _manager_scores()),
        (_MIXED_USER, _MIXED_MANAGER),
    ):
        assert build_playbook(user, manager)["privacy_notice"] == PRIVACY_NOTICE

    assert "private" in PRIVACY_NOTICE.lower()
    assert "manager is never shown it" in PRIVACY_NOTICE


@pytest.mark.parametrize("direction", [UNDER_SUPPLIED, OVER_SUPPLIED])
@pytest.mark.parametrize(
    "dimension", ["autonomy", "feedback_style", "growth_focus", "relationship"]
)
def test_constraint_note_is_attached_exactly_where_the_bias_review_asked(
    dimension: str, direction: str
) -> None:
    """Bias review Finding 4: the environment, not the manager, may set this."""
    expected = CONSTRAINT_NOTES.get((dimension, direction))
    gap = -0.55 if direction == UNDER_SUPPLIED else 0.55
    user = _user_scores(**{dimension: 0.80 if gap < 0 else 0.25})
    manager = _manager_scores(**{dimension: 0.25 if gap < 0 else 0.80})

    entry = next(
        e for e in build_playbook(user, manager)["dimensions"]
        if e["dimension"] == dimension
    )

    assert entry["constraint_note"] == expected


def test_the_three_constrained_directions_are_the_ones_finding_4_named() -> None:
    assert set(CONSTRAINT_NOTES) == {
        ("autonomy", UNDER_SUPPLIED),
        ("feedback_style", UNDER_SUPPLIED),
        ("growth_focus", UNDER_SUPPLIED),
    }


# ---------------------------------------------------------------------------
# Every cell reachable, from real sittings
# ---------------------------------------------------------------------------

def _reachable_keys() -> tuple[set[tuple[str, str, str]], set[tuple[str, str]]]:
    """Classify every (need, style) pair the two instruments can actually make."""
    grinds: set[tuple[str, str, str]] = set()
    meshes: set[tuple[str, str]] = set()
    for dim in DIMENSIONS:
        needs = _achievable(QUESTIONS, score_manager_match, dim)
        styles = _achievable(MANAGER_PROFILE_QUESTIONS, score_manager_profile, dim)
        for need, style in product(needs, styles):
            verdict = classify_dimension(dim, need, style)
            if verdict["classification"] == GRIND:
                grinds.add((dim, verdict["direction"], verdict["severity"]))
            else:
                meshes.add((dim, verdict["band"]))
    return grinds, meshes


def test_every_protocol_cell_is_reachable_from_real_answer_sheets() -> None:
    reachable_grinds, _ = _reachable_keys()

    assert reachable_grinds == set(PROTOCOL_CELLS), (
        f"unreachable cells: {sorted(set(PROTOCOL_CELLS) - reachable_grinds)}; "
        f"reachable but uncontented: {sorted(reachable_grinds - set(PROTOCOL_CELLS))}"
    )


def test_every_mesh_note_is_reachable_from_real_answer_sheets() -> None:
    _, reachable_meshes = _reachable_keys()

    assert reachable_meshes == set(MESH_NOTES)


def test_no_reachable_classification_is_missing_content() -> None:
    """The assembly must never KeyError on a sitting a real user could produce."""
    for dim in DIMENSIONS:
        needs = _achievable(QUESTIONS, score_manager_match, dim)
        styles = _achievable(MANAGER_PROFILE_QUESTIONS, score_manager_profile, dim)
        for need, style in product(needs, styles):
            playbook = build_playbook(
                _user_scores(**{dim: need}), _manager_scores(**{dim: style})
            )
            entry = next(e for e in playbook["dimensions"] if e["dimension"] == dim)
            assert entry.get("note", entry.get("why", "")).strip()


# ---------------------------------------------------------------------------
# Structural: the content itself
# ---------------------------------------------------------------------------

def test_there_are_sixteen_cells_covering_the_full_cross_product() -> None:
    expected = {
        (dim, direction, severity)
        for dim in DIMENSIONS
        for direction in DIRECTIONS
        for severity in SEVERITIES
    }

    assert set(PROTOCOL_CELLS) == expected
    assert len(PROTOCOL_CELLS) == 16


def test_mesh_notes_cover_every_dimension_and_band() -> None:
    assert set(MESH_NOTES) == {(dim, band) for dim in DIMENSIONS for band in BANDS}


@pytest.mark.parametrize("key", sorted(PROTOCOL_CELLS))
def test_no_cell_is_empty(key: tuple[str, str, str]) -> None:
    cell = PROTOCOL_CELLS[key]

    assert set(cell) == {"headline", "why", "ask", "agenda", "scripts"}
    for field in ("headline", "why", "ask"):
        assert cell[field].strip(), f"{key} has an empty {field}"
    assert len(cell["why"]) > 200, f"{key} why is too thin to explain a grind"
    assert len(cell["ask"]) > 120, f"{key} ask is too thin to act on"


@pytest.mark.parametrize("key", sorted(PROTOCOL_CELLS))
def test_every_cell_has_agenda_items_and_two_or_three_scripts(
    key: tuple[str, str, str]
) -> None:
    cell = PROTOCOL_CELLS[key]

    assert 2 <= len(cell["agenda"]) <= 5, f"{key} agenda: {len(cell['agenda'])}"
    assert all(item.strip() for item in cell["agenda"])
    assert 2 <= len(cell["scripts"]) <= 3, f"{key} scripts: {len(cell['scripts'])}"
    assert all(script.strip() for script in cell["scripts"])


@pytest.mark.parametrize("key", sorted(PROTOCOL_CELLS))
def test_cell_headline_is_short_enough_to_render(key: tuple[str, str, str]) -> None:
    assert len(PROTOCOL_CELLS[key]["headline"]) <= 80


def test_no_two_cells_share_a_headline_body_or_ask() -> None:
    """Severity bands must be genuinely different content, not the same words."""
    for field in ("headline", "why", "ask"):
        values = [cell[field] for cell in PROTOCOL_CELLS.values()]
        assert len(set(values)) == len(values), f"duplicate {field} across cells"

    assert len(set(MESH_NOTES.values())) == len(MESH_NOTES)


@pytest.mark.parametrize(
    "key", sorted(k for k in PROTOCOL_CELLS if k[2] == ACUTE)
)
def test_acute_cells_ask_for_more_than_their_notable_twin(
    key: tuple[str, str, str]
) -> None:
    dimension, direction, _ = key

    acute = PROTOCOL_CELLS[key]
    notable = PROTOCOL_CELLS[(dimension, direction, NOTABLE)]

    assert len(acute["agenda"]) >= len(notable["agenda"])
    assert acute["ask"] != notable["ask"]


# The tone guardrail PRODUCT_DECISIONS §6 and bias-review Finding 6 both name:
# describe behavior and what it costs, never the person. These are the words
# that would mean the line had been crossed — including ones introduced only to
# be denied, which leave the word with the reader either way.
FAULT_WORDS = (
    "toxic", "incompetent", "lazy", "neglect", "negligent", "bad manager",
    "bad boss", "poor manager", "weak manager", "character flaw", "your fault",
    "their fault", "to blame", "abusive", "hostile", "micromanag",
    "controlling", "uncaring", "cold", "unreasonable", "insecure", "petty",
    "bully", "dysfunction", "red flag", "failing you",
)

# Every cell has to say, in some form, that the manager's style is a real
# position and not a defect. This is the crudest possible check that it does.
LEGITIMACY_MARKERS = (
    "legitimate", "real way", "real ways", "real style", "real philosophy",
    "deliberate", "on purpose", "considered", "defensible", "respectful",
    "generous", "engaged", "warm", "trust", "genuine", "invested",
    "neither is wrong", "neither of those is the wrong", "demanding way",
    "very good managers", "strong managers",
)


def _cell_text(cell: dict) -> str:
    return " ".join(
        [cell["headline"], cell["why"], cell["ask"], *cell["agenda"], *cell["scripts"]]
    ).lower()


@pytest.mark.parametrize("key", sorted(PROTOCOL_CELLS))
def test_no_cell_reads_as_your_manager_is_bad(key: tuple[str, str, str]) -> None:
    text = _cell_text(PROTOCOL_CELLS[key])

    found = [word for word in FAULT_WORDS if word in text]
    assert not found, f"{key} characterizes the manager: {found}"


@pytest.mark.parametrize("key", sorted(PROTOCOL_CELLS))
def test_every_cell_affirms_the_managers_style_as_legitimate(
    key: tuple[str, str, str]
) -> None:
    why = PROTOCOL_CELLS[key]["why"].lower()

    assert any(marker in why for marker in LEGITIMACY_MARKERS), (
        f"{key} explains the grind without saying the manager's side is a real "
        f"position — the fit-not-fault line"
    )


@pytest.mark.parametrize("key", sorted(MESH_NOTES))
def test_no_mesh_note_is_empty_or_faulting(key: tuple[str, str]) -> None:
    note = MESH_NOTES[key]

    assert note.strip()
    assert not [word for word in FAULT_WORDS if word in note.lower()]


@pytest.mark.parametrize("key", sorted(CONSTRAINT_NOTES))
def test_constraint_notes_point_at_the_environment(key: tuple[str, str]) -> None:
    note = CONSTRAINT_NOTES[key].lower()

    assert not [word for word in FAULT_WORDS if word in note]
    # A hedge that does not hedge is just another claim: the note has to make
    # the environment a possibility and then say what changes if it holds.
    assert any(m in note for m in ("may not be", "may be", "worth checking"))
    assert "if that is the case" in note


# ---------------------------------------------------------------------------
# Wiring to the instruments
# ---------------------------------------------------------------------------

def test_decoder_dimensions_match_both_instruments_exactly() -> None:
    """The diff is only meaningful while all three agree on the dimension set."""
    assert set(DIMENSIONS) == {q["dimension"] for q in QUESTIONS}
    assert set(DIMENSIONS) == {q["dimension"] for q in MANAGER_PROFILE_QUESTIONS}


def test_module_docstring_names_every_item_off_the_shared_anchors() -> None:
    """Regression (audit 2026-10-02, F8): the docstring claimed both
    instruments share the 0.25/0.80 anchors, which `mm-q10` and `mm-q14` do
    not. Any item off those anchors must be named there with its own pair, so
    the threshold derivation a reader checks is the true one."""
    import manager_match.decoder as decoder_module

    doc = decoder_module.__doc__ or ""
    off_anchor = [
        q
        for q in [*QUESTIONS, *MANAGER_PROFILE_QUESTIONS]
        if sorted((q["score_a"], q["score_b"])) != [0.25, 0.80]
    ]
    assert off_anchor, "no off-anchor items left: simplify the docstring and this test"
    for q in off_anchor:
        hi, lo = max(q["score_a"], q["score_b"]), min(q["score_a"], q["score_b"])
        assert f"`{q['question_id']}`" in doc, q["question_id"]
        assert f"{hi:.2f}/{lo:.2f}" in doc, q["question_id"]


def test_decode_runs_from_raw_answers_through_both_scorers() -> None:
    user_answers = _answers(QUESTIONS, {q["question_id"] for q in QUESTIONS})
    manager_answers = _answers(MANAGER_PROFILE_QUESTIONS, set())

    playbook = decode(user_answers, manager_answers)

    # Every need at the top anchor, every style at the bottom: four wide,
    # under-supplied grinds.
    assert playbook["grind_count"] == 4
    for entry in playbook["dimensions"]:
        assert entry["direction"] == UNDER_SUPPLIED
        assert entry["severity"] == ACUTE


def test_decode_is_deterministic() -> None:
    user_answers = _answers(QUESTIONS, {"mm-q1", "mm-q5", "mm-q9", "mm-q12"})
    manager_answers = _answers(
        MANAGER_PROFILE_QUESTIONS,
        {q["question_id"] for q in MANAGER_PROFILE_QUESTIONS[:6]},
    )

    assert decode(user_answers, manager_answers) == decode(
        user_answers, manager_answers
    )


def test_decode_surfaces_instrument_validation_errors() -> None:
    with pytest.raises(ValueError):
        decode([], _answers(MANAGER_PROFILE_QUESTIONS, set()))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_missing_dimension_raises() -> None:
    partial = {d: 0.5 for d in DIMENSIONS if d != "relationship"}

    with pytest.raises(ValueError, match="relationship"):
        build_playbook(partial, _manager_scores())


def test_unknown_dimension_raises() -> None:
    extra = {**_manager_scores(), "vibes": 0.5}

    with pytest.raises(ValueError, match="vibes"):
        build_playbook(_user_scores(), extra)


@pytest.mark.parametrize("value", [-0.01, 1.01, 12.0])
def test_out_of_range_score_raises(value: float) -> None:
    with pytest.raises(ValueError, match="out of"):
        build_playbook(_user_scores(autonomy=value), _manager_scores())


@pytest.mark.parametrize("value", ["0.5", None, True])
def test_non_numeric_score_raises(value: object) -> None:
    with pytest.raises(ValueError, match="not a number"):
        build_playbook({**_user_scores(), "autonomy": value}, _manager_scores())


def test_unknown_dimension_cannot_be_classified() -> None:
    with pytest.raises(ValueError, match="Unknown dimension"):
        classify_dimension("charisma", 0.5, 0.5)


def test_the_error_names_which_side_was_wrong() -> None:
    with pytest.raises(ValueError, match="manager"):
        build_playbook(_user_scores(), {d: 0.5 for d in DIMENSIONS if d != "autonomy"})
