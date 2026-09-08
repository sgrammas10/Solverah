"""
test_rater_agreement.py -- tests for the anchor-ambiguity flag.

Written before the raters returned anything, against synthetic files shaped like the real
schema. The point is that when 18 real JSONs land, the comparison is already known-correct
rather than being written and debugged against the only data that exists.

The two tests that matter most:
  - test_two_band_gap_would_be_missed_by_a_float_threshold pins the IEEE754 bug that made a
    numeric threshold the wrong shape for this rule.
  - test_expert_is_never_in_the_flag pins D-12(b): the rubric's author cannot evidence that
    her own wording is clear.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rater_agreement import (  # noqa: E402
    AgreementError,
    band_index,
    build_cells,
    load_band_values,
    load_readings,
    review_list,
)

BANDS = [0.1, 0.3, 0.5, 0.7, 0.9]
DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]


@pytest.fixture
def anchors(tmp_path):
    p = tmp_path / "anchors.json"
    p.write_text(json.dumps({
        "rubric_version": "v1-frozen-2026-08-15",
        "band_values": BANDS,
        "agreement_rule": {
            "same_band": "agreement",
            "one_band_apart": "expected instrument resolution, not ambiguity",
            "two_or_more_bands_apart": "anchor ambiguity - reword, do not average",
        },
    }), encoding="utf-8")
    return p


def _write(tmp_path, packet_id, rater, scores, recognition="no"):
    p = tmp_path / f"solverah_{packet_id}_rater{rater}.json"
    p.write_text(json.dumps({
        "packet_id": packet_id,
        "rater": rater,
        "rubric_version": "v1-frozen-2026-08-15",
        "recognition": recognition,
        "scores": [
            {"dimension": d, "score": s, "confidence": 0.6, "quotes": []}
            for d, s in scores.items()
        ],
    }), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# The rule's shape
# ---------------------------------------------------------------------------

def test_two_band_gap_would_be_missed_by_a_float_threshold():
    """PINS THE BUG that makes a numeric threshold wrong here, not merely inelegant.
    0.7 - 0.3 is 0.39999999999999997, so a genuine two-band gap fails `> 0.4` and drops
    silently out of the REVIEW list."""
    assert (0.7 - 0.3) > 0.4 is False or not ((0.7 - 0.3) > 0.4)
    assert band_index(0.7, BANDS) - band_index(0.3, BANDS) == 2


def test_achievable_differences_make_any_intermediate_threshold_identical():
    """Every threshold strictly inside (0.2, 0.4) partitions identically -- so a float
    threshold is a categorical rule wearing a number's clothing, and 0.25 is not a
    'moved band', it is the same rule spelled less clearly."""
    diffs = sorted({round(abs(a - b), 12) for a in BANDS for b in BANDS})
    assert diffs == [0.0, 0.2, 0.4, 0.6, 0.8]
    for threshold in (0.21, 0.25, 0.3, 0.39):
        flagged = {(a, b) for a in BANDS for b in BANDS if abs(a - b) > threshold}
        assert flagged == {(a, b) for a in BANDS for b in BANDS
                           if abs(band_index(a, BANDS) - band_index(b, BANDS)) >= 2}


def test_off_band_score_is_refused_not_snapped():
    """An off-band value means an edited file, a different anchors version, or an average.
    Snapping would launder exactly the corruption worth catching."""
    with pytest.raises(AgreementError, match="not one of the band values"):
        band_index(0.45, BANDS)


def test_anchors_without_the_rule_key_is_refused(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"band_values": BANDS, "agreement_rule": {}}), encoding="utf-8")
    with pytest.raises(AgreementError, match="two_or_more_bands_apart"):
        load_band_values(p)


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("b_score,c_score,expected", [
    (0.5, 0.5, "AGREE"),    # same band
    (0.3, 0.5, "WATCH"),    # one band -- expected resolution, explicitly NOT ambiguity
    (0.3, 0.7, "REVIEW"),   # two bands -- the float-threshold trap case
    (0.1, 0.9, "REVIEW"),   # four bands
])
def test_verdicts_follow_the_frozen_rule(tmp_path, anchors, b_score, c_score, expected):
    bands = load_band_values(anchors)
    paths = [
        _write(tmp_path, "P-01", "A", {"autonomy": 0.5}),
        _write(tmp_path, "P-01", "B", {"autonomy": b_score}),
        _write(tmp_path, "P-01", "C", {"autonomy": c_score}),
    ]
    cells = build_cells(load_readings(paths, bands))
    assert len(cells) == 1
    assert cells[0].verdict == expected


def test_one_band_apart_never_reaches_the_review_list(tmp_path, anchors):
    """The 0.15 threshold would have put every one-band pair here. The frozen rule says
    one band apart is the instrument working, not the anchor failing."""
    bands = load_band_values(anchors)
    paths = [
        _write(tmp_path, "P-01", "B", {d: 0.3 for d in DIMS}),
        _write(tmp_path, "P-01", "C", {d: 0.5 for d in DIMS}),
    ]
    cells = build_cells(load_readings(paths, bands))
    assert len(cells) == 6
    assert all(c.verdict == "WATCH" for c in cells)
    assert review_list(cells) == []


# ---------------------------------------------------------------------------
# D-12(b) -- who counts
# ---------------------------------------------------------------------------

def test_expert_is_never_in_the_flag(tmp_path, anchors):
    """Julie (rater A) owns the rubric. Her reading cannot evidence that her own wording is
    clear. Here she is four bands from both blind raters, who agree exactly -- and the cell
    must still read AGREE, because blind-vs-blind is what the flag measures."""
    bands = load_band_values(anchors)
    paths = [
        _write(tmp_path, "P-01", "A", {"autonomy": 0.9}),
        _write(tmp_path, "P-01", "B", {"autonomy": 0.1}),
        _write(tmp_path, "P-01", "C", {"autonomy": 0.1}),
    ]
    cells = build_cells(load_readings(paths, bands))
    assert cells[0].verdict == "AGREE"
    assert cells[0].blind == {"B": 0, "C": 0}
    assert cells[0].expert == {"A": 4}


def test_expert_divergence_catches_what_blind_agreement_hides(tmp_path, anchors):
    """The case above is not nothing -- it is arguably the strongest signal available. Both
    blind readers read the anchor consistently AND differently from its author, which means
    the text says something other than what it was written to say. Blind-vs-blind cannot see
    this, because the two of them agreeing looks like success."""
    bands = load_band_values(anchors)
    paths = [
        _write(tmp_path, "P-01", "A", {"autonomy": 0.9}),
        _write(tmp_path, "P-01", "B", {"autonomy": 0.1}),
        _write(tmp_path, "P-01", "C", {"autonomy": 0.1}),
    ]
    cells = build_cells(load_readings(paths, bands))
    assert cells[0].expert_divergence == -4


def test_expert_divergence_is_silent_when_the_blind_raters_disagree(tmp_path, anchors):
    """If the blind raters disagree, the cell is already REVIEW and the expert comparison
    would be reading a spread, not a divergence."""
    bands = load_band_values(anchors)
    paths = [
        _write(tmp_path, "P-01", "A", {"autonomy": 0.9}),
        _write(tmp_path, "P-01", "B", {"autonomy": 0.1}),
        _write(tmp_path, "P-01", "C", {"autonomy": 0.5}),
    ]
    cells = build_cells(load_readings(paths, bands))
    assert cells[0].verdict == "REVIEW"
    assert cells[0].expert_divergence is None


def test_unknown_rater_letter_is_refused(tmp_path, anchors):
    """A rater silently defaulting to 'blind' would put the rubric's author into the flag."""
    bands = load_band_values(anchors)
    paths = [_write(tmp_path, "P-01", "D", {"autonomy": 0.5})]
    with pytest.raises(AgreementError, match="no entry in RATER_ROLES"):
        load_readings(paths, bands)


def test_a_single_blind_rater_is_incomplete_not_agreement(tmp_path, anchors):
    """One rater's scores are indistinguishable from that rater's lens. A missing second
    blind reading must not read as consensus."""
    bands = load_band_values(anchors)
    paths = [
        _write(tmp_path, "P-01", "A", {"autonomy": 0.5}),
        _write(tmp_path, "P-01", "B", {"autonomy": 0.5}),
    ]
    cells = build_cells(load_readings(paths, bands))
    assert cells[0].verdict == "INCOMPLETE"
    assert review_list(cells) == []


# ---------------------------------------------------------------------------
# Shape over a full round
# ---------------------------------------------------------------------------

def test_full_round_produces_one_cell_per_packet_dimension(tmp_path, anchors):
    bands = load_band_values(anchors)
    paths = []
    for packet in [f"P-0{i}" for i in range(1, 7)]:
        for rater in "ABC":
            paths.append(_write(tmp_path, packet, rater, {d: 0.5 for d in DIMS}))
    cells = build_cells(load_readings(paths, bands))
    assert len(cells) == 36
    assert all(c.verdict == "AGREE" for c in cells)


def test_recognition_is_carried_through_for_the_reader_class_finding(tmp_path, anchors):
    """A mostly-'no' result from the two blind lawyers is a positive finding, not an absence.
    It must survive into the readings rather than being dropped as metadata."""
    bands = load_band_values(anchors)
    paths = [
        _write(tmp_path, "P-01", "B", {"autonomy": 0.5}, recognition="no"),
        _write(tmp_path, "P-01", "C", {"autonomy": 0.5}, recognition="yes"),
    ]
    readings = load_readings(paths, bands)
    assert {r.rater: r.recognition for r in readings} == {"B": "no", "C": "yes"}
