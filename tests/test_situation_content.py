"""Structural + tone guards for the Situation Report guidance content (A-6).

Mirrors `test_manager_decoder.py`'s content half. There is no scoring here to
test — A-3 does not exist yet — so every test in this file is a guard on the
words: that the grid is complete, that no two cells are the same words, that
nothing reads as a verdict on an employer, and that the cells which are
supposed to hand over to the Manager Decoder actually do.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from manager_match import decoder as manager_decoder
from work_pulse import situation as gap_engine
from work_pulse import situation_items
from work_pulse.situation_content import (
    ALIGNED_BAND_HIGH_MIN,
    ALIGNED_BAND_LOW_MAX,
    ALIGNED_NOTES,
    BANDS,
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
    aligned_note_for,
    band_for_env_score,
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


# ---------------------------------------------------------------------------
# Aligned notes — the third table. Guards mirror C-2's on MESH_NOTES, plus the
# ones that only bite here: the band is content (low and high must not be one
# sentence with a word swapped), and there is no needs-forward rendering.
# ---------------------------------------------------------------------------

ALIGNED_KEYS = sorted(ALIGNED_NOTES)

# A dimension score is the mean of A-1's two items, each anchored on the five
# band values 0.1/0.3/0.5/0.7/0.9 — so every score a real answer sheet can
# produce, in 0.1 steps across the closed anchor range.
ATTAINABLE_SCORES = tuple(round(0.1 * n, 1) for n in range(1, 10))

# Diminishing the low pole is how a "both poles are legitimate" file fails on
# the aligned half specifically: nothing here characterizes an employer, but
# "a match, at least" quietly says the low end is the consolation one. The
# FAULT_WORDS list cannot see that, so this is its aligned-side companion.
DIMINISHING_PHRASES = (
    "settling", "settle for", "nothing wrong with", "at least you",
    "at least it", "makes up for", "could be worse", "on the bright side",
    "only so much", "lack of", "not much of a", "make do", "better than nothing",
)

# Every note has to end somewhere actionable — the thing to protect, or the
# thing to watch. A note that only says "you match here" is the blank row with
# a sentence in it.
PROTECT_OR_WATCH_MARKERS = (
    "worth", "watch", "keep an eye", "protect", "the thing to", "keeping an eye",
)


def _content_words(text: str) -> set[str]:
    stop = {
        "you", "your", "the", "and", "that", "a", "is", "it", "of", "to", "in",
        "be", "are", "what", "this", "here", "on", "for", "with", "as", "not",
        "or", "an", "at", "by",
    }
    return {
        word
        for word in re.findall(r"[a-z']+", text.lower())
        if word not in stop and len(word) > 2
    }


def test_there_are_eighteen_notes_covering_every_dimension_and_band() -> None:
    assert set(ALIGNED_NOTES) == {(dim, band) for dim in DIMENSIONS for band in BANDS}
    assert len(ALIGNED_NOTES) == 18


def test_bands_are_the_three_the_decoder_named() -> None:
    """Same three-band vocabulary as C-2's mesh half, so the two report pages
    do not describe the same idea with different words."""
    assert BANDS == ("low", "mid", "high")
    assert set(BANDS) == {band for _, band in manager_decoder.MESH_NOTES}


def test_band_edges_are_thirds_of_the_instruments_own_anchors() -> None:
    """The method C-2 uses, on A-1's anchors rather than the decoder's.

    A-1 anchors at 0.1/0.9, not 0.25/0.80, so the numbers must differ — what
    must not differ is the arithmetic, which is why this asserts the formula
    and not two literals.

    Worth knowing that this is the *only* test that separates anchor-thirds
    from thirds of a notional [0, 1]: at A-1's current two-items-of-five-bands
    the edges land at 0.3667/0.6333 against 0.3333/0.6667, and those band all
    nine attainable scores identically
    (`test_every_score_a_real_answer_sheet_can_produce_bands_evenly` passes
    either way). They diverge the moment A-1 re-anchors or changes its item
    count, which is exactly when nobody will be re-deriving this by hand.
    """
    width = (0.9 - 0.1) / 3
    assert ALIGNED_BAND_LOW_MAX == pytest.approx(0.1 + width)
    assert ALIGNED_BAND_HIGH_MIN == pytest.approx(0.9 - width)

    decoder_width = (manager_decoder.ANCHOR_HIGH - manager_decoder.ANCHOR_LOW) / 3
    assert manager_decoder.MESH_BAND_LOW_MAX == pytest.approx(
        manager_decoder.ANCHOR_LOW + decoder_width
    )


def test_the_anchors_are_the_instruments_anchors() -> None:
    """If A-1 ever re-anchors, these edges are wrong and this fails first."""
    poles = situation_items.POLE_VALUES.values()

    assert min(poles) == 0.1
    assert max(poles) == 0.9


def test_every_score_a_real_answer_sheet_can_produce_bands_evenly() -> None:
    """Three of the nine attainable dimension scores per band — the check that
    the edges sit *between* A-1's steps rather than on one. An edge on a step
    is the failure this catches: it makes one band four scores wide and its
    neighbour two, so a whole band's worth of users read the wrong note."""
    banded: dict[str, list[float]] = {band: [] for band in BANDS}
    for score in ATTAINABLE_SCORES:
        banded[band_for_env_score(score)].append(score)

    assert banded == {
        "low": [0.1, 0.2, 0.3],
        "mid": [0.4, 0.5, 0.6],
        "high": [0.7, 0.8, 0.9],
    }


@pytest.mark.parametrize("key", ALIGNED_KEYS)
def test_no_aligned_note_is_empty(key: tuple[str, str]) -> None:
    note = ALIGNED_NOTES[key]

    assert isinstance(note, str)
    assert note.strip()


@pytest.mark.parametrize("key", ALIGNED_KEYS)
def test_an_aligned_note_is_a_note_and_not_a_register_cell(
    key: tuple[str, str]
) -> None:
    """C-2's rule, ported: "not protocol cells". An aligned dimension has no
    problem to run a two-week experiment against, so a note that grew to the
    size of one has started solving something that is not wrong."""
    note = ALIGNED_NOTES[key]
    shortest_cell = min(len(_cell_text(cell)) for cell in GUIDANCE_CELLS.values())

    assert 240 <= len(note) <= 450, f"{key} is {len(note)} chars"
    assert len(note) < shortest_cell


@pytest.mark.parametrize("key", ALIGNED_KEYS)
def test_every_aligned_note_names_something_to_protect_or_watch(
    key: tuple[str, str]
) -> None:
    note = ALIGNED_NOTES[key].lower()

    assert any(marker in note for marker in PROTECT_OR_WATCH_MARKERS), (
        f"{key} names the match without naming what to do about it"
    )


@pytest.mark.parametrize("key", ALIGNED_KEYS)
def test_no_aligned_note_reads_as_your_employer_is_bad(key: tuple[str, str]) -> None:
    note = ALIGNED_NOTES[key].lower()

    found = [word for word in FAULT_WORDS if word in note]
    assert not found, f"{key} characterizes the employer: {found}"


@pytest.mark.parametrize("key", ALIGNED_KEYS)
def test_no_aligned_note_treats_one_pole_as_the_consolation_prize(
    key: tuple[str, str]
) -> None:
    note = ALIGNED_NOTES[key].lower()

    found = [phrase for phrase in DIMINISHING_PHRASES if phrase in note]
    assert not found, f"{key} makes a match sound like a compromise: {found}"


def test_no_aligned_note_duplicates_another_piece_of_content() -> None:
    """One note written per dimension and pasted across its three bands would
    pass every other guard in this section."""
    assert len(set(ALIGNED_NOTES.values())) == len(ALIGNED_NOTES)

    others = {d.strip().lower() for diag in DIAGNOSES.values() for d in diag.values()}
    others |= {note.strip().lower() for note in DECODER_CROSSREFS.values()}
    for cell in GUIDANCE_CELLS.values():
        for value in cell.values():
            others |= {text.strip().lower() for text in _strings(value)}

    clashes = [k for k, v in ALIGNED_NOTES.items() if v.strip().lower() in others]
    assert not clashes, f"aligned notes reused from elsewhere: {clashes}"


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_a_dimensions_three_bands_are_not_one_sentence_with_a_word_swapped(
    dimension: str
) -> None:
    """The band is the content. Aligned-low on pace is a match on calm and
    aligned-high is a match on intensity — if the two share most of their
    words, the table has six notes in it and not eighteen.
    """
    for first, second in (("low", "mid"), ("mid", "high"), ("low", "high")):
        left = _content_words(ALIGNED_NOTES[(dimension, first)])
        right = _content_words(ALIGNED_NOTES[(dimension, second)])
        overlap = len(left & right) / len(left | right)

        assert overlap < 0.35, (
            f"{dimension} {first}/{second} share {overlap:.0%} of their words — "
            f"one note templated across bands, not two"
        )


def test_an_aligned_note_never_hands_over_to_the_decoder() -> None:
    """`feedback` defers its *protocol* to C-2 (DEFERRED_DIMENSIONS), but an
    aligned dimension has no protocol to hand over — routing a user to a
    second report to be told again that nothing is wrong is the blank row
    with an extra click on it."""
    for key, note in ALIGNED_NOTES.items():
        assert DECODER_REFERENCE.lower() not in note.lower(), f"{key} routes away"
        assert "decoder" not in note.lower(), f"{key} routes away"


def test_aligned_notes_are_plain_strings_with_no_needs_forward_twin() -> None:
    """The ruling, pinned. `DIAGNOSES` carries two renderings because a gap
    survives the trip to a new job as a thing to seek; an aligned dimension
    does not. Every note's second half instructs a reader who currently holds
    the job, and a between-jobs user answered A-1 in the past tense about a
    role they have left — so A-5/A-7 drop aligned dimensions from the
    needs-forward rendering rather than rewording them. Anyone adding a
    `needs_forward` key here has to change this test on the way, which is the
    point of it.
    """
    for key, note in ALIGNED_NOTES.items():
        assert isinstance(note, str), f"{key} grew a second rendering: {type(note)}"
        assert "what to seek" not in note.lower(), f"{key} reads as needs-forward"


# ---------------------------------------------------------------------------
# Aligned lookup — A-7 must not be able to ask for a note that is not there
# ---------------------------------------------------------------------------

def test_aligned_note_for_is_total_over_every_dimension_and_score() -> None:
    """The lookup-key guard: any (dimension, env_score) A-3 can hand over
    resolves, including the scores between A-1's steps and the closed ends."""
    for dimension in DIMENSIONS:
        for score in ATTAINABLE_SCORES + (0.0, 0.15, 0.3667, 0.6333, 1.0):
            note = aligned_note_for(dimension, score)

            assert note in set(ALIGNED_NOTES.values())


def test_every_aligned_note_is_reachable_through_the_lookup() -> None:
    reached = {
        (dim, band_for_env_score(score))
        for dim in DIMENSIONS
        for score in ATTAINABLE_SCORES
    }

    assert reached == set(ALIGNED_NOTES)


def test_the_band_edges_belong_to_the_outer_bands() -> None:
    """Stated so a later refactor cannot flip them silently: C-2's
    `_mesh_band` puts its own edges in `low`/`high` the same way."""
    assert band_for_env_score(ALIGNED_BAND_LOW_MAX) == "low"
    assert band_for_env_score(ALIGNED_BAND_HIGH_MIN) == "high"
    assert band_for_env_score(ALIGNED_BAND_LOW_MAX + 0.001) == "mid"
    assert band_for_env_score(ALIGNED_BAND_HIGH_MIN - 0.001) == "mid"


def test_aligned_lookup_is_deterministic() -> None:
    assert aligned_note_for("decision", 0.5) == aligned_note_for("decision", 0.5)


@pytest.mark.parametrize("dimension", ["growth_focus", "Autonomy", "relationship", ""])
def test_aligned_note_for_rejects_an_unknown_dimension(dimension: str) -> None:
    with pytest.raises(ValueError, match="Unknown dimension"):
        aligned_note_for(dimension, 0.5)


@pytest.mark.parametrize("score", [-0.01, 1.01, 2.0, -1.0])
def test_a_score_off_the_scale_raises_rather_than_banding(score: float) -> None:
    with pytest.raises(ValueError, match=r"out of \[0, 1\]"):
        band_for_env_score(score)
    with pytest.raises(ValueError, match=r"out of \[0, 1\]"):
        aligned_note_for("pace", score)


@pytest.mark.parametrize("score", ["0.5", None, True, [0.5]])
def test_a_non_numeric_score_raises_rather_than_banding(score: object) -> None:
    with pytest.raises(ValueError, match="not a number"):
        band_for_env_score(score)  # type: ignore[arg-type]


def test_the_aligned_bucket_is_the_one_that_reaches_this_table() -> None:
    """The seam with A-3, asserted rather than commented: the bucket that
    `direction_for_bucket` returns `None` for is exactly the bucket
    `aligned_note_for` serves, so between them every A-3 report entry
    resolves to content and none resolves to both kinds.
    """
    directionless = [b for b, carries in BUCKET_TO_DIRECTION.items() if not carries]

    assert directionless == [gap_engine.ALIGNED]
    assert direction_for_bucket(gap_engine.ALIGNED) is None
    assert aligned_note_for("autonomy", 0.5)


def test_an_aligned_dimension_from_the_gap_engine_resolves_to_a_note() -> None:
    """End to end over A-3's real classifier, no hand-built buckets: a pair
    inside the aligned threshold produces a note and no directional guidance.
    """
    env = {dim: 0.7 for dim in gap_engine.DIMENSIONS}
    person = {dim: 0.7 for dim in gap_engine.DIMENSIONS}
    report = gap_engine.build_situation_report(env, person)

    for entry in report:
        assert entry["bucket"] == gap_engine.ALIGNED
        assert direction_for_bucket(entry["bucket"], entry["direction"]) is None
        assert aligned_note_for(entry["dimension"], entry["env_score"]) == (
            ALIGNED_NOTES[(entry["dimension"], "high")]
        )
