"""
test_three_way_dispersion.py -- 12 tests for the rebuilt three-way dispersion diagnostic.

REBUILT 2026-08-20 with the module (S-55). Two fixtures are load-bearing per S-40 (a check
whose fixture makes the failure invisible is not a check):

1. THE COVERAGE-GAP CELL -- Julie 0.1 / Carolynn 0.3 / George 0.5. The blind pair (B-C) sits
   one band apart, so the S-15 flag and any B-C-only computation see nothing; the A-C pair is
   two bands apart and the three-way spread is 2. A fixture where B and C already disagreed by
   two bands could NOT catch a mutation that quietly drops the Julie-involving pairs, because
   the B-C signal would mask it.

2. THE FLOAT TRAP -- 0.7 - 0.3 == 0.39999999999999997 in IEEE 754, so a genuine two-band gap
   FAILS a naive `> 0.4` float test. The fixture pins the integer-band path: distance must be
   exactly 2. (The S-35 incident as a regression test, same as D-12(a).)

Cell ids in multi-cell fixtures are chosen so that canonical (packet_id, dimension) order,
insertion order, and spread-magnitude order all DIFFER (S-40's zulu/mike/alfa lesson): a
planted sort-by-spread or a dropped sort both break an assertion.
"""

from __future__ import annotations

import json

import pytest

from rater_agreement import AgreementError, band_index
from three_way_dispersion import (
    PAIRS,
    RECORD_KEYS,
    SUMMARY_KEYS,
    ThreeWayCell,
    build_three_way_cells,
    dispersion_summary,
    per_cell_records,
    run,
)

BANDS = [0.1, 0.3, 0.5, 0.7, 0.9]


def _reading(packet, rater, dim, score):
    # Minimal stand-in matching rater_agreement.Reading's fields used here.
    from rater_agreement import RATER_ROLES, Reading

    return Reading(
        packet_id=packet,
        rater=rater,
        role=RATER_ROLES[rater],
        dimension=dim,
        score=score,
        band=band_index(score, BANDS),
        confidence=None,
        recognition=None,
    )


def _cells(rows):
    """rows: list of (packet, rater, dim, score)."""
    return build_three_way_cells([_reading(*r) for r in rows])


# ---------------------------------------------------------------------------
# 1-2: the two load-bearing fixtures
# ---------------------------------------------------------------------------

def test_float_trap_two_band_gap_is_exactly_2():
    # The naive float rule really is broken -- document it in the test itself:
    assert not ((0.7 - 0.3) > 0.4), "IEEE 754: 0.7-0.3 == 0.39999999999999997"
    cells, _ = _cells(
        [("P-01", "A", "autonomy", 0.7), ("P-01", "B", "autonomy", 0.7), ("P-01", "C", "autonomy", 0.3)]
    )
    (cell,) = cells
    # Integer bands: a two-band gap is exactly 2, never 0.399... compared to a float threshold.
    assert cell.pair_distances["B-C"] == 2
    assert cell.pair_distances["A-C"] == 2
    assert cell.three_way_spread == 2


def test_coverage_gap_cell_julie_pairs_carry_the_signal():
    cells, _ = _cells(
        [("P-01", "A", "pace", 0.1), ("P-01", "B", "pace", 0.3), ("P-01", "C", "pace", 0.5)]
    )
    (cell,) = cells
    # The blind pair sees only expected resolution (1 band) -- no S-15 signal here.
    assert cell.pair_distances["B-C"] == 1
    # The three-way view sees what B-C cannot:
    assert cell.pair_distances["A-B"] == 1
    assert cell.pair_distances["A-C"] == 2
    assert cell.three_way_spread == 2


# ---------------------------------------------------------------------------
# 3-5: the guard as executable tests
# ---------------------------------------------------------------------------

def test_summary_keys_are_frozen_no_flag_can_grow():
    cells, inc = _cells(
        [("P-01", "A", "pace", 0.1), ("P-01", "B", "pace", 0.3), ("P-01", "C", "pace", 0.5)]
    )
    summary = dispersion_summary(cells, n_incomplete=inc)
    # Exact equality: a grown `needs_review` (or any flag-shaped key) fails this test.
    assert set(summary) == SUMMARY_KEYS
    assert set(summary["licensed_inference"]) == {"mass_d_ge_2"}


def test_record_keys_are_frozen():
    cells, _ = _cells(
        [("P-01", "A", "pace", 0.1), ("P-01", "B", "pace", 0.3), ("P-01", "C", "pace", 0.5)]
    )
    (rec,) = per_cell_records(cells)
    assert set(rec) == RECORD_KEYS


def test_no_verdict_strings_anywhere():
    cells, inc = _cells(
        [("P-01", "A", "pace", 0.1), ("P-01", "B", "pace", 0.9), ("P-01", "C", "pace", 0.5)]
    )
    blob = json.dumps(dispersion_summary(cells, n_incomplete=inc)) + json.dumps(
        per_cell_records(cells)
    )
    for verdict in ("REVIEW", "WATCH", "needs_review", "flag"):
        assert verdict not in blob


# ---------------------------------------------------------------------------
# 6-8: all three pairs, incompleteness, arithmetic
# ---------------------------------------------------------------------------

def test_all_three_pairs_present_in_distribution():
    cells, inc = _cells(
        [("P-01", "A", "pace", 0.1), ("P-01", "B", "pace", 0.3), ("P-01", "C", "pace", 0.5)]
    )
    summary = dispersion_summary(cells, n_incomplete=inc)
    assert set(summary["pair_distance_distribution"]) == {"A-B", "A-C", "B-C"}
    assert PAIRS == (("A", "B"), ("A", "C"), ("B", "C"))


def test_incomplete_cells_counted_not_silently_dropped():
    cells, inc = _cells(
        [
            ("P-01", "A", "pace", 0.1),
            ("P-01", "B", "pace", 0.3),
            ("P-01", "C", "pace", 0.5),
            ("P-02", "B", "pace", 0.5),  # no A, no C -- incomplete
            ("P-02", "C", "pace", 0.5),
        ]
    )
    assert len(cells) == 1
    assert inc == 1
    summary = dispersion_summary(cells, n_incomplete=inc)
    assert summary["n_cells"] == 1
    assert summary["cells_incomplete"] == 1


def test_distribution_counts_sum_to_n_cells_for_every_pair():
    cells, inc = _cells(
        [
            ("P-01", "A", "pace", 0.1), ("P-01", "B", "pace", 0.3), ("P-01", "C", "pace", 0.5),
            ("P-01", "A", "decision", 0.5), ("P-01", "B", "decision", 0.5), ("P-01", "C", "decision", 0.5),
            ("P-02", "A", "pace", 0.9), ("P-02", "B", "pace", 0.1), ("P-02", "C", "pace", 0.5),
        ]
    )
    summary = dispersion_summary(cells, n_incomplete=inc)
    for pair, dist in summary["pair_distance_distribution"].items():
        assert sum(dist.values()) == summary["n_cells"] == 3, pair


# ---------------------------------------------------------------------------
# 9-10: ordering -- canonical, never ranked
# ---------------------------------------------------------------------------

# Insertion order zulu, mike, alfa; spreads 1, 4, 2 -- so canonical order (alfa, mike, zulu)
# differs from BOTH insertion order and any spread ranking (asc: zulu,alfa,mike / desc:
# mike,alfa,zulu). A planted sort-by-spread and a dropped sort both fail.
_ORDERING_ROWS = [
    ("zulu", "A", "pace", 0.3), ("zulu", "B", "pace", 0.5), ("zulu", "C", "pace", 0.3),   # spread 1
    ("mike", "A", "pace", 0.1), ("mike", "B", "pace", 0.9), ("mike", "C", "pace", 0.5),   # spread 4
    ("alfa", "A", "pace", 0.1), ("alfa", "B", "pace", 0.5), ("alfa", "C", "pace", 0.3),   # spread 2
]


def test_records_in_canonical_order_not_ranked():
    cells, _ = _cells(_ORDERING_ROWS)
    recs = per_cell_records(cells)
    assert [r["packet_id"] for r in recs] == ["alfa", "mike", "zulu"]
    assert [r["three_way_spread"] for r in recs] == [2, 4, 1]  # not monotone: not a ranking


def test_records_canonical_even_from_shuffled_cell_list():
    cells, _ = _cells(_ORDERING_ROWS)
    shuffled = [cells[2], cells[0], cells[1]]
    assert [r["packet_id"] for r in per_cell_records(shuffled)] == ["alfa", "mike", "zulu"]


# ---------------------------------------------------------------------------
# 11-12: the licensed inference, and the off-band refusal
# ---------------------------------------------------------------------------

def test_licensed_inference_mass_at_two_or_more_bands():
    cells, inc = _cells(
        [
            # cell 1: A far from both, B-C adjacent -> A-B: 2, A-C: 3, B-C: 1
            ("P-01", "A", "pace", 0.1), ("P-01", "B", "pace", 0.5), ("P-01", "C", "pace", 0.7),
            # cell 2: unanimous -> all distances 0
            ("P-02", "A", "pace", 0.5), ("P-02", "B", "pace", 0.5), ("P-02", "C", "pace", 0.5),
        ]
    )
    mass = dispersion_summary(cells, n_incomplete=inc)["licensed_inference"]["mass_d_ge_2"]
    assert mass == {"A-B": 0.5, "A-C": 0.5, "B-C": 0.0}
    # The module reports masses; it does NOT verdict on them (guard clause 4).


def test_off_band_score_refused_not_snapped():
    with pytest.raises(AgreementError):
        _cells([("P-01", "A", "pace", 0.4), ("P-01", "B", "pace", 0.5), ("P-01", "C", "pace", 0.5)])
