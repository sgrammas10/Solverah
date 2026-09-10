"""Structural + tone guards for the Situation Report guidance content (A-6).

Mirrors `test_manager_decoder.py`'s content half. There is no scoring here to
test — A-3 does not exist yet — so every test in this file is a guard on the
words: that the grid is complete, that no two cells are the same words, that
nothing reads as a verdict on an employer, and that the cells which are
supposed to hand over to the Manager Decoder actually do.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from manager_match import decoder as manager_decoder
from work_pulse import situation as gap_engine
from work_pulse.situation_content import (
    BUCKET_TO_DIRECTION,
    CHANGE_IN_PLACE,
    DECODER_CROSSREFS,
    DECODER_REFERENCE,
    DEFERRED_DIMENSIONS,
    DIAGNOSES,
    DIMENSIONS,
    GAP_DIRECTIONS,
    GUIDANCE_CELLS,
    GUIDANCE_NOTICE,
    NEGOTIATE,
    OVER_SUPPLIED,
    RARELY_MOVES,
    REGISTERS,
    UNDER_SUPPLIED,
    diagnosis_for,
    direction_for_bucket,
    guidance_for,
    is_deferred,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ANCHORS_V3 = (
    REPO_ROOT
    / "Solverah_IP"
    / "ground_truth"
    / "rater_app"
    / "anchors_v3_PROPOSED.json"
)

FIELDS_BY_REGISTER: dict[str, set[str]] = {
    CHANGE_IN_PLACE: {"experiment_name", "experiment", "steps", "signal"},
    NEGOTIATE: {"who_and_where", "opening", "scripts", "if_no"},
    RARELY_MOVES: {"why_fixed", "cost_of_staying", "what_it_implies"},
}

ALL_KEYS = sorted(GUIDANCE_CELLS)
DEFERRED_KEYS = sorted(k for k in GUIDANCE_CELLS if k[0] in DEFERRED_DIMENSIONS)
DIRECT_KEYS = sorted(k for k in GUIDANCE_CELLS if k[0] not in DEFERRED_DIMENSIONS)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _cell_text(cell: dict) -> str:
    parts: list[str] = []
    for value in cell.values():
        parts.extend(_strings(value))
    return " ".join(parts).lower()


def _diagnosis_text(diagnosis: dict) -> str:
    return " ".join(diagnosis.values()).lower()


# ---------------------------------------------------------------------------
# The grid
# ---------------------------------------------------------------------------

def test_there_are_twelve_diagnoses_covering_the_full_cross_product() -> None:
    expected = {(dim, direction) for dim in DIMENSIONS for direction in GAP_DIRECTIONS}

    assert set(DIAGNOSES) == expected
    assert len(DIAGNOSES) == 12


def test_there_are_thirty_six_cells_covering_the_full_cross_product() -> None:
    expected = {
        (dim, direction, register)
        for dim in DIMENSIONS
        for direction in GAP_DIRECTIONS
        for register in REGISTERS
    }

    assert set(GUIDANCE_CELLS) == expected
    assert len(GUIDANCE_CELLS) == 36


def test_the_six_dimensions_are_the_rubrics_six() -> None:
    """A-6's keys have to be the model's keys or assembly is not a lookup."""
    anchors = json.loads(ANCHORS_V3.read_text(encoding="utf-8"))
    rubric_keys = [dim["key"] for dim in anchors["dimensions"]]

    assert list(DIMENSIONS) == rubric_keys


def test_gap_directions_have_not_drifted_from_the_decoder() -> None:
    """C-2 and A-6 are separate modules that must agree on these two strings."""
    assert UNDER_SUPPLIED == manager_decoder.UNDER_SUPPLIED
    assert OVER_SUPPLIED == manager_decoder.OVER_SUPPLIED
    assert GAP_DIRECTIONS == (UNDER_SUPPLIED, OVER_SUPPLIED)


def test_registers_are_the_three_the_plan_names() -> None:
    assert REGISTERS == (CHANGE_IN_PLACE, NEGOTIATE, RARELY_MOVES)


# ---------------------------------------------------------------------------
# The A-3 join. Assembly is only a lookup while these two modules agree.
# ---------------------------------------------------------------------------

def test_dimension_keys_match_the_gap_engine_exactly() -> None:
    assert DIMENSIONS == gap_engine.DIMENSIONS


def test_the_bucket_mapping_is_total_over_the_gap_engines_buckets() -> None:
    """A bucket A-3 can return and this file cannot recognize is a blank
    section. Since the 2026-09-10 rename a bucket alone no longer determines
    a direction (`notable`/`straining` each pair with either), so this only
    asserts which buckets carry one at all -- see the module docstring.
    """
    assert set(BUCKET_TO_DIRECTION) == {
        gap_engine.ALIGNED,
        gap_engine.NOTABLE,
        gap_engine.STRAINING,
    }
    assert BUCKET_TO_DIRECTION[gap_engine.ALIGNED] is False
    assert BUCKET_TO_DIRECTION[gap_engine.NOTABLE] is True
    assert BUCKET_TO_DIRECTION[gap_engine.STRAINING] is True


def test_the_mapping_follows_the_gap_engines_own_sign_convention() -> None:
    """`gap = env - person`, so a positive gap is the over-supplied side.

    Driven through `classify_gap`/`gap_direction` rather than asserted from
    the docstring, so that flipping the sign in either module fails here.
    """
    for dimension in DIMENSIONS:
        threshold = gap_engine.STRAINING_THRESHOLDS[dimension]
        wide = round(threshold + 0.05, gap_engine.GAP_PRECISION)

        bucket = gap_engine.classify_gap(dimension, wide)
        direction = gap_engine.gap_direction(dimension, wide)
        assert direction_for_bucket(bucket, direction) == OVER_SUPPLIED

        bucket = gap_engine.classify_gap(dimension, -wide)
        direction = gap_engine.gap_direction(dimension, -wide)
        assert direction_for_bucket(bucket, direction) == UNDER_SUPPLIED

        bucket = gap_engine.classify_gap(dimension, 0.0)
        direction = gap_engine.gap_direction(dimension, 0.0)
        assert direction_for_bucket(bucket, direction) is None


def test_gap_directions_have_not_drifted_from_the_gap_engine() -> None:
    """A-3's own `under`/`over` vocabulary is shorter than this file's; the
    translation in `direction_for_bucket` is only correct while both modules
    agree on what those two short strings mean.
    """
    assert gap_engine.gap_direction("autonomy", gap_engine.STRAINING_THRESHOLDS["autonomy"] + 0.05) == gap_engine.OVER
    assert gap_engine.gap_direction("autonomy", -(gap_engine.STRAINING_THRESHOLDS["autonomy"] + 0.05)) == gap_engine.UNDER
    assert direction_for_bucket(gap_engine.STRAINING, gap_engine.OVER) == OVER_SUPPLIED
    assert direction_for_bucket(gap_engine.STRAINING, gap_engine.UNDER) == UNDER_SUPPLIED


def test_every_non_aligned_bucket_reaches_content_for_every_dimension() -> None:
    """The half-the-file failure mode: rendering only `under_supplied`."""
    for dimension in DIMENSIONS:
        for bucket in (gap_engine.NOTABLE, gap_engine.STRAINING):
            for engine_direction in (gap_engine.UNDER, gap_engine.OVER):
                direction = direction_for_bucket(bucket, engine_direction)
                assert direction is not None
                assert set(guidance_for(dimension, direction)["registers"]) == set(REGISTERS)


def test_unknown_bucket_raises() -> None:
    with pytest.raises(ValueError, match="Unknown gap bucket"):
        direction_for_bucket("grinding", None)


def test_aligned_bucket_rejects_a_direction() -> None:
    with pytest.raises(ValueError, match="carries no direction"):
        direction_for_bucket(gap_engine.ALIGNED, gap_engine.OVER)


def test_non_aligned_bucket_requires_a_known_direction() -> None:
    with pytest.raises(ValueError, match="Unknown gap direction"):
        direction_for_bucket(gap_engine.NOTABLE, "sideways")


# ---------------------------------------------------------------------------
# Nothing empty, nothing the wrong shape
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(DIAGNOSES))
def test_no_diagnosis_is_empty(key: tuple[str, str]) -> None:
    diagnosis = DIAGNOSES[key]

    assert set(diagnosis) == {"headline", "current_role", "needs_forward"}
    for field, value in diagnosis.items():
        assert value.strip(), f"{key} has an empty {field}"
    assert len(diagnosis["headline"]) <= 80
    assert len(diagnosis["current_role"]) > 200, f"{key} current_role is too thin"
    assert len(diagnosis["needs_forward"]) > 120, f"{key} needs_forward is too thin"


@pytest.mark.parametrize("key", ALL_KEYS)
def test_cell_has_exactly_its_registers_fields_and_none_are_empty(
    key: tuple[str, str, str]
) -> None:
    cell = GUIDANCE_CELLS[key]

    assert set(cell) == FIELDS_BY_REGISTER[key[2]]
    for field, value in cell.items():
        for text in _strings(value):
            assert text.strip(), f"{key} has an empty entry in {field}"
        if isinstance(value, list):
            assert value, f"{key} has an empty {field} list"


@pytest.mark.parametrize("key", sorted(k for k in ALL_KEYS if k[2] == CHANGE_IN_PLACE))
def test_change_in_place_cells_are_experiment_shaped(
    key: tuple[str, str, str]
) -> None:
    """B-5 builds experiment cards straight off these fields."""
    cell = GUIDANCE_CELLS[key]

    assert len(cell["experiment_name"]) <= 60
    assert 2 <= len(cell["steps"]) <= 5, f"{key} steps: {len(cell['steps'])}"
    assert len(cell["signal"]) > 80, f"{key} signal is too thin to measure against"

    if key[0] not in DEFERRED_DIMENSIONS:
        assert len(cell["experiment"]) > 200, f"{key} experiment is too thin to run"
        assert 3 <= len(cell["steps"]) <= 5
        # A two-week-shaped change says so somewhere the reader can see it.
        text = _cell_text(cell)
        assert any(m in text for m in ("two weeks", "fortnight")), (
            f"{key} does not name the window it runs over"
        )


@pytest.mark.parametrize("key", sorted(k for k in ALL_KEYS if k[2] == NEGOTIATE))
def test_negotiate_cells_carry_literal_sentences(key: tuple[str, str, str]) -> None:
    cell = GUIDANCE_CELLS[key]

    if key[0] in DEFERRED_DIMENSIONS:
        assert len(cell["scripts"]) == 1, "a deferral points, it does not script"
    else:
        assert 2 <= len(cell["scripts"]) <= 3, f"{key} scripts: {len(cell['scripts'])}"
        # "what to say" means something a user could read out, not a paraphrase.
        assert all(
            script.rstrip().endswith(("?", ".", "!")) for script in cell["scripts"]
        ), f"{key} has a script that is not a sentence"
    assert len(cell["if_no"]) > 120, f"{key} if_no is too thin to act on"


@pytest.mark.parametrize("key", sorted(k for k in ALL_KEYS if k[2] == RARELY_MOVES))
def test_rarely_moves_cells_name_the_ceiling_the_cost_and_the_fit_question(
    key: tuple[str, str, str]
) -> None:
    cell = GUIDANCE_CELLS[key]

    for field in ("why_fixed", "cost_of_staying", "what_it_implies"):
        assert len(cell[field]) > 150, f"{key} {field} is too thin to be honest"

    # C-2's acute cells end exactly here, and the review approved that wording.
    implies = cell["what_it_implies"].lower()
    assert "fit" in implies, f"{key} never reaches the fit question"
    assert "failure on either side" in implies, (
        f"{key} names the fit question without saying it is not a failure"
    )


def test_the_scope_notice_disclaims_a_verdict_on_the_employer() -> None:
    notice = GUIDANCE_NOTICE.lower()

    assert "legitimate" in notice
    assert "judgement about your employer" in notice
    assert "nobody at your company can see it" in notice


# ---------------------------------------------------------------------------
# No two cells are the same words
# ---------------------------------------------------------------------------

def test_no_two_pieces_of_content_share_text() -> None:
    """Twelve cells written from one template would pass every other test."""
    seen: dict[str, tuple] = {}
    duplicates: list[tuple[str, tuple, tuple]] = []

    def register(text: str, where: tuple) -> None:
        key = text.strip().lower()
        if key in seen:
            duplicates.append((text, seen[key], where))
        else:
            seen[key] = where

    for key, diagnosis in DIAGNOSES.items():
        for field, value in diagnosis.items():
            register(value, key + (field,))
    for key, cell in GUIDANCE_CELLS.items():
        for field, value in cell.items():
            for index, text in enumerate(_strings(value)):
                register(text, key + (field, index))
    for key, note in DECODER_CROSSREFS.items():
        register(note, key + ("crossref",))

    assert not duplicates, f"duplicated content: {duplicates}"


def test_no_two_diagnoses_share_a_headline() -> None:
    headlines = [d["headline"] for d in DIAGNOSES.values()]

    assert len(set(headlines)) == len(headlines)


def test_the_two_directions_of_a_dimension_are_not_the_same_advice() -> None:
    for dimension in DIMENSIONS:
        for register in REGISTERS:
            under = _cell_text(GUIDANCE_CELLS[(dimension, UNDER_SUPPLIED, register)])
            over = _cell_text(GUIDANCE_CELLS[(dimension, OVER_SUPPLIED, register)])
            assert under != over, f"{dimension}/{register} says the same thing twice"


# ---------------------------------------------------------------------------
# Tone. FAULT_WORDS is C-2's list, ported, plus the words that would mean a
# cell had crossed the line about a *company* rather than about a manager.
# ---------------------------------------------------------------------------

FAULT_WORDS = (
    # ported verbatim from test_manager_decoder.py
    "toxic", "incompetent", "lazy", "neglect", "negligent", "bad manager",
    "bad boss", "poor manager", "weak manager", "character flaw", "your fault",
    "their fault", "to blame", "abusive", "hostile", "micromanag",
    "controlling", "uncaring", "cold", "unreasonable", "insecure", "petty",
    "bully", "dysfunction", "red flag", "failing you",
    # the environment-side additions: both poles legitimate applies to a
    # company too, so none of these can appear about one
    "bad company", "bad culture", "bad employer", "bad workplace",
    "bad place to work", "wrong company", "broken culture", "sweatshop",
    "exploitative", "burnout factory", "poorly run", "badly run", "mismanag",
    "disorganis", "disorganiz", "chaotic", "amateur", "clueless", "backward",
    "should know better",
)

# The honest register is honest in both directions: it must not promise the
# ceiling will lift, and it must not tell the user what to do about their job.
DOOM_WORDS = (
    "hopeless", "no point", "waste of your time", "cut your losses",
    "give up", "you should quit", "you should leave", "start looking",
    "will never change", "never going to change", "dead end", "trapped",
    "no future", "get out",
)
FALSE_HOPE_WORDS = (
    "simply ", "just ask", "all you have to", "easy fix", "quick win",
    "guaranteed", "will definitely", "always works", "bound to",
)

# Every cell that explains a mismatch has to say, in some form, that the way
# the environment runs is a real position and not a defect.
LEGITIMACY_MARKERS = (
    "legitimate", "deliberate", "on purpose", "real position", "real way",
    "real ways", "correct decision", "point of pride", "considered",
    "reasonable things to want", "both pay off", "two different",
)


@pytest.mark.parametrize("key", ALL_KEYS)
def test_no_cell_reads_as_your_employer_is_bad(key: tuple[str, str, str]) -> None:
    text = _cell_text(GUIDANCE_CELLS[key])

    found = [word for word in FAULT_WORDS if word in text]
    assert not found, f"{key} characterizes the employer: {found}"


@pytest.mark.parametrize("key", sorted(DIAGNOSES))
def test_no_diagnosis_reads_as_your_employer_is_bad(key: tuple[str, str]) -> None:
    text = _diagnosis_text(DIAGNOSES[key])

    found = [word for word in FAULT_WORDS if word in text]
    assert not found, f"{key} characterizes the employer: {found}"


def test_the_scope_notice_carries_no_fault_words() -> None:
    text = GUIDANCE_NOTICE.lower()

    assert not [word for word in FAULT_WORDS if word in text]


@pytest.mark.parametrize("key", sorted(DIAGNOSES))
def test_every_diagnosis_says_the_environment_is_a_real_way_to_work(
    key: tuple[str, str]
) -> None:
    current_role = DIAGNOSES[key]["current_role"].lower()

    assert any(marker in current_role for marker in LEGITIMACY_MARKERS), (
        f"{key} describes the mismatch without saying the environment's side is "
        f"a real position — the fit-not-fault line"
    )


@pytest.mark.parametrize("key", sorted(k for k in ALL_KEYS if k[2] == RARELY_MOVES))
def test_rarely_moves_explains_the_ceiling_without_faulting_the_place(
    key: tuple[str, str, str]
) -> None:
    why_fixed = GUIDANCE_CELLS[key]["why_fixed"].lower()

    assert any(marker in why_fixed for marker in LEGITIMACY_MARKERS), (
        f"{key} explains why it is fixed without saying the setting is legitimate"
    )


@pytest.mark.parametrize("key", sorted(k for k in ALL_KEYS if k[2] == RARELY_MOVES))
def test_rarely_moves_is_neither_doom_nor_false_hope(
    key: tuple[str, str, str]
) -> None:
    text = _cell_text(GUIDANCE_CELLS[key])

    assert not [word for word in DOOM_WORDS if word in text], (
        f"{key} tells the user what to do about their job"
    )
    assert not [word for word in FALSE_HOPE_WORDS if word in text], (
        f"{key} promises the ceiling will lift"
    )


# ---------------------------------------------------------------------------
# ⚑4 — link, do not duplicate
# ---------------------------------------------------------------------------

def test_feedback_is_the_dimension_that_defers() -> None:
    """The plan names the manager-behaviour dimension; this is the one."""
    assert DEFERRED_DIMENSIONS == frozenset({"feedback"})
    assert all(is_deferred(dim) is (dim in DEFERRED_DIMENSIONS) for dim in DIMENSIONS)


@pytest.mark.parametrize("key", DEFERRED_KEYS)
def test_every_deferral_cell_actually_links_to_the_decoder(
    key: tuple[str, str, str]
) -> None:
    assert DECODER_REFERENCE.lower() in _cell_text(GUIDANCE_CELLS[key]), (
        f"{key} defers to nothing"
    )


@pytest.mark.parametrize("key", sorted(k for k in DIAGNOSES if k[0] in DEFERRED_DIMENSIONS))
def test_the_deferred_diagnoses_say_where_the_protocol_lives(
    key: tuple[str, str]
) -> None:
    assert DECODER_REFERENCE.lower() in _diagnosis_text(DIAGNOSES[key])


# Only two of the three registers carry protocol. `rarely_moves` is the
# environment-level honest register — an org's feedback norm and its ceiling
# are not something the Decoder speaks to at all — so a deferral there is a
# full cell, not a pointer, and the shortness guard would be wrong to bind it.
PROTOCOL_REGISTERS = (CHANGE_IN_PLACE, NEGOTIATE)


@pytest.mark.parametrize("key", [k for k in DEFERRED_KEYS if k[2] in PROTOCOL_REGISTERS])
def test_a_deferral_is_short_because_it_does_not_duplicate_the_protocol(
    key: tuple[str, str, str]
) -> None:
    """The failure mode this guards is a deferral that grew its own playbook."""
    deferred = len(_cell_text(GUIDANCE_CELLS[key]))
    direct = [
        len(_cell_text(GUIDANCE_CELLS[k])) for k in DIRECT_KEYS if k[2] == key[2]
    ]

    assert deferred < min(direct), (
        f"{key} is longer than the shortest cell that writes its own protocol"
    )


@pytest.mark.parametrize("key", DIRECT_KEYS)
def test_only_the_deferred_dimension_mentions_the_decoder_in_a_cell(
    key: tuple[str, str, str]
) -> None:
    """Elsewhere the pointer belongs in DECODER_CROSSREFS, attached at assembly."""
    assert DECODER_REFERENCE.lower() not in _cell_text(GUIDANCE_CELLS[key])


def test_crossrefs_sit_exactly_where_the_decoder_has_a_counterpart() -> None:
    """autonomy is the one dimension both instruments measure and neither owns."""
    assert set(DECODER_CROSSREFS) == {
        ("autonomy", UNDER_SUPPLIED),
        ("autonomy", OVER_SUPPLIED),
    }
    shared = set(DIMENSIONS) & set(manager_decoder.DIMENSIONS)
    assert shared == {"autonomy"}


@pytest.mark.parametrize("key", sorted(DECODER_CROSSREFS))
def test_crossrefs_hedge_and_point(key: tuple[str, str]) -> None:
    note = DECODER_CROSSREFS[key]
    lowered = note.lower()

    assert DECODER_REFERENCE.lower() in lowered
    assert not [word for word in FAULT_WORDS if word in lowered]
    # Same discipline as C-2's CONSTRAINT_NOTES: raise the possibility, then
    # say what changes if it holds. A hedge that does not hedge is a claim.
    assert "may be" in lowered
    assert "if that is the case" in lowered


def test_a_crossref_never_stands_in_for_a_deferral() -> None:
    assert not set(DECODER_CROSSREFS) & {
        (dim, direction)
        for dim in DEFERRED_DIMENSIONS
        for direction in GAP_DIRECTIONS
    }


# ---------------------------------------------------------------------------
# Separability — A-5/A-7 render the same cells needs-forward for between-jobs
# users, which only works if the situation and the actions are not interleaved
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(DIAGNOSES))
def test_both_renderings_of_the_situation_exist_and_differ(
    key: tuple[str, str]
) -> None:
    diagnosis = DIAGNOSES[key]

    assert diagnosis["current_role"] != diagnosis["needs_forward"]
    assert "what to seek" in diagnosis["needs_forward"].lower(), (
        f"{key} needs_forward does not read as what to seek"
    )


@pytest.mark.parametrize("key", ALL_KEYS)
def test_no_guidance_cell_restates_its_diagnosis(key: tuple[str, str, str]) -> None:
    """If a cell repeats the situation, swapping the situation breaks the cell."""
    dimension, direction, _ = key
    headline = DIAGNOSES[(dimension, direction)]["headline"].lower()

    assert headline not in _cell_text(GUIDANCE_CELLS[key])


@pytest.mark.parametrize("key", sorted(k for k in ALL_KEYS if k[2] == CHANGE_IN_PLACE))
def test_the_signal_line_reads_without_a_current_role(
    key: tuple[str, str, str]
) -> None:
    """`signal` is the field needs-forward keeps: it must not address a job."""
    signal = GUIDANCE_CELLS[key]["signal"].lower()

    for phrase in ("your manager", "ask your", "this role", "your company"):
        assert phrase not in signal, f"{key} signal presupposes a current role"


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def test_guidance_for_returns_the_whole_cell_set() -> None:
    assembled = guidance_for("pace", OVER_SUPPLIED)

    assert assembled["dimension"] == "pace"
    assert assembled["direction"] == OVER_SUPPLIED
    assert set(assembled["registers"]) == set(REGISTERS)
    assert assembled["diagnosis"] == DIAGNOSES[("pace", OVER_SUPPLIED)]
    assert assembled["defers_to_decoder"] is False
    assert assembled["decoder_crossref"] is None


def test_guidance_for_attaches_the_crossref_where_there_is_one() -> None:
    assembled = guidance_for("autonomy", UNDER_SUPPLIED)

    assert assembled["decoder_crossref"] == DECODER_CROSSREFS[
        ("autonomy", UNDER_SUPPLIED)
    ]


def test_guidance_for_flags_the_deferral() -> None:
    assembled = guidance_for("feedback", OVER_SUPPLIED)

    assert assembled["defers_to_decoder"] is True
    assert assembled["decoder_crossref"] is None


def test_every_cell_is_reachable_through_the_lookup() -> None:
    reached = {
        (dim, direction, register)
        for dim in DIMENSIONS
        for direction in GAP_DIRECTIONS
        for register in guidance_for(dim, direction)["registers"]
    }

    assert reached == set(GUIDANCE_CELLS)


def test_lookup_is_deterministic() -> None:
    assert guidance_for("innovation", UNDER_SUPPLIED) == guidance_for(
        "innovation", UNDER_SUPPLIED
    )


def test_assembled_content_is_a_copy_not_the_stored_content() -> None:
    assembled = guidance_for("collaboration", OVER_SUPPLIED)
    assembled["registers"][CHANGE_IN_PLACE]["steps"].append("mutated")
    assembled["diagnosis"]["headline"] = "mutated"

    assert "mutated" not in GUIDANCE_CELLS[
        ("collaboration", OVER_SUPPLIED, CHANGE_IN_PLACE)
    ]["steps"]
    assert DIAGNOSES[("collaboration", OVER_SUPPLIED)]["headline"] != "mutated"


@pytest.mark.parametrize(
    "dimension, direction",
    [
        ("growth_focus", UNDER_SUPPLIED),
        ("Autonomy", UNDER_SUPPLIED),
        ("", UNDER_SUPPLIED),
    ],
)
def test_unknown_dimension_raises(dimension: str, direction: str) -> None:
    with pytest.raises(ValueError, match="Unknown dimension"):
        guidance_for(dimension, direction)
    with pytest.raises(ValueError, match="Unknown dimension"):
        diagnosis_for(dimension, direction)
    with pytest.raises(ValueError, match="Unknown dimension"):
        is_deferred(dimension)


@pytest.mark.parametrize("direction", ["straining", "notable", "over supplied", ""])
def test_unknown_direction_raises(direction: str) -> None:
    with pytest.raises(ValueError, match="Unknown gap direction"):
        guidance_for("autonomy", direction)
    with pytest.raises(ValueError, match="Unknown gap direction"):
        diagnosis_for("autonomy", direction)
