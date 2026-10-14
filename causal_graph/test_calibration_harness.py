"""
test_calibration_harness.py -- SYNTHETIC data only. No real round-2 data exists, and none may
be used to fit a mapping until PREREG_ROUND2 section 9's packet floor is met.
"""
from __future__ import annotations

import pytest

import calibration_harness as ch


def _cells(n_packets, llm_of):
    """Every packet carries one cell per reference band 0-4; the LLM band is llm_of(ref)."""
    return [ch.Cell(f"P-{p:02d}", llm_of(r), r) for p in range(n_packets) for r in range(5)]


def shifted_up(r):
    """A round-1-shaped bias: the LLM reads one band high and so never reaches the floor."""
    return min(r + 1, 4)


def test_refuses_below_the_preregistered_packet_floor():
    cells = _cells(ch.MIN_PACKETS - 1, shifted_up)
    with pytest.raises(ch.CalibrationRefused, match=str(ch.MIN_PACKETS)):
        ch.fit_mapping(cells)
    with pytest.raises(ch.CalibrationRefused):
        ch.evaluate(cells)


def test_many_cells_from_few_packets_are_still_refused():
    # 14 packets x 50 cells: plenty of rows, too few independent units.
    cells = [c for c in _cells(ch.MIN_PACKETS - 1, shifted_up) for _ in range(10)]
    with pytest.raises(ch.CalibrationRefused):
        ch.fit_mapping(cells)


def test_learns_to_undo_a_one_band_upward_shift():
    mapping = ch.fit_mapping(_cells(ch.MIN_PACKETS, shifted_up))
    assert mapping[1] == 0 and mapping[2] == 1 and mapping[3] == 2
    assert list(mapping.values()) == sorted(mapping.values())      # monotone
    assert all(0 <= v <= 4 for v in mapping.values())


def test_out_of_sample_evaluation_shows_the_improvement():
    res = ch.evaluate(_cells(ch.MIN_PACKETS + 1, shifted_up))
    assert res["packets"] == ch.MIN_PACKETS + 1
    assert res["llm_floor_uses_raw"] == 0
    assert res["calibrated_mean_distance"] < res["raw_mean_distance"]


def test_an_unbiased_llm_is_left_alone():
    mapping = ch.fit_mapping(_cells(ch.MIN_PACKETS, lambda r: r))
    assert mapping == {b: b for b in range(5)}


def test_out_of_range_band_is_refused():
    cells = _cells(ch.MIN_PACKETS, lambda r: r) + [ch.Cell("P-99", 5, 0)]
    with pytest.raises(ValueError):
        ch.fit_mapping(cells)


def test_the_module_has_no_way_to_save_a_mapping():
    public = {n for n in dir(ch) if not n.startswith("_")}
    assert not {n for n in public if any(w in n.lower() for w in ("save", "write", "dump", "persist"))}
