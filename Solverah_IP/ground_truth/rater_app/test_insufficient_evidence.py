"""
test_insufficient_evidence.py -- the skip (Julie's ruling 4) through the agreement modules.

A skip is `score: null` + `insufficient_evidence: true`, legal only under an anchors file
that declares `insufficient_evidence` (v3.1 onward). It is neither agreement nor
disagreement: SKIPPED, counted on its own line, absent from every band distance.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rater_agreement import (  # noqa: E402
    AgreementError,
    build_cells,
    load_band_values,
    load_readings,
    permits_insufficient_evidence,
    review_list,
)
import three_way_dispersion as twd  # noqa: E402

BANDS = [0.1, 0.3, 0.5, 0.7, 0.9]
RULE = {
    "same_band": "agreement",
    "one_band_apart": "expected instrument resolution, not ambiguity",
    "two_or_more_bands_apart": "anchor ambiguity - reword, do not average",
}
SKIP = "SKIP"  # sentinel in the _write helper for an insufficient-evidence row


def _anchors(tmp_path, *, with_skip: bool) -> Path:
    doc = {"rubric_version": "test", "band_values": BANDS, "agreement_rule": dict(RULE)}
    if with_skip:
        doc["insufficient_evidence"] = {"label": "Insufficient evidence", "text": "..."}
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / ("anchors_v31.json" if with_skip else "anchors_v1.json")
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _row(dim, s):
    if s == SKIP:
        return {"dimension": dim, "score": None, "confidence": None, "quotes": [],
                "insufficient_evidence": True}
    return {"dimension": dim, "score": s, "confidence": 0.6, "quotes": []}


def _write(d: Path, packet, rater, scores: dict) -> Path:
    d.mkdir(exist_ok=True)
    p = d / f"solverah_{packet}_rater{rater}.json"
    p.write_text(json.dumps({"packet_id": packet, "rater": rater,
                             "scores": [_row(k, v) for k, v in scores.items()]}),
                 encoding="utf-8")
    return p


def _cells(tmp_path, b, c, a=None):
    anchors = _anchors(tmp_path, with_skip=True)
    paths = [_write(tmp_path / "r", "P-07", "B", {"decision": b}),
             _write(tmp_path / "r", "P-07", "C", {"decision": c})]
    if a is not None:
        paths.append(_write(tmp_path / "r", "P-07", "A", {"decision": a}))
    return build_cells(load_readings(paths, load_band_values(anchors), allow_insufficient=True))


# --- what the rubric permits ---------------------------------------------------------

def test_permission_comes_from_the_anchors_file(tmp_path):
    assert permits_insufficient_evidence(_anchors(tmp_path, with_skip=True))
    assert not permits_insufficient_evidence(_anchors(tmp_path, with_skip=False))


def test_the_real_v31_file_permits_it_and_v1_does_not():
    assert permits_insufficient_evidence(HERE / "anchors_v3_1_PROPOSED.json")
    assert not permits_insufficient_evidence(HERE / "anchors.json")
    assert not permits_insufficient_evidence(HERE / "anchors_v3_PROPOSED.json")


def test_a_skip_under_v1_anchors_is_refused(tmp_path):
    p = _write(tmp_path / "r", "P-01", "B", {"decision": SKIP})
    with pytest.raises(AgreementError, match="declares no insufficient_evidence"):
        load_readings([p], BANDS)  # allow_insufficient defaults to False


@pytest.mark.parametrize("row, msg", [
    ({"dimension": "decision", "score": None, "confidence": None}, "without insufficient_evidence"),
    ({"dimension": "decision", "confidence": 0.6}, "no 'score' key"),
    ({"dimension": "decision", "score": 0.5, "insufficient_evidence": True}, "but score is 0.5"),
])
def test_malformed_rows_raise_agreement_error_not_a_traceback(tmp_path, row, msg):
    d = tmp_path / "r"
    d.mkdir()
    p = d / "x.json"
    p.write_text(json.dumps({"packet_id": "P-07", "rater": "B", "scores": [row]}), encoding="utf-8")
    with pytest.raises(AgreementError, match=msg):
        load_readings([p], BANDS, allow_insufficient=True)


# --- the verdict -------------------------------------------------------------------

def test_one_blind_skip_is_skipped_not_agreement_or_review(tmp_path):
    (cell,) = _cells(tmp_path, b=SKIP, c=0.9)
    assert cell.verdict == "SKIPPED"
    assert cell.blind_spread is None
    assert cell.skipped_by == ["B"]
    assert review_list([cell]) == []


def test_two_blind_skips_are_still_not_agreement(tmp_path):
    (cell,) = _cells(tmp_path, b=SKIP, c=SKIP)
    assert cell.verdict == "SKIPPED"
    assert cell.skipped_by == ["B", "C"]


def test_a_skip_is_not_read_as_0_5(tmp_path):
    # 0.1 vs a skip must not become a two-band REVIEW (as it would if the skip were 0.5),
    # and 0.5 vs a skip must not become AGREE.
    (low,) = _cells(tmp_path / "a", b=0.1, c=SKIP)
    (mid,) = _cells(tmp_path / "b", b=0.5, c=SKIP)
    assert low.verdict == mid.verdict == "SKIPPED"


def test_expert_skip_leaves_the_blind_flag_alone_and_silences_divergence(tmp_path):
    (cell,) = _cells(tmp_path, b=0.9, c=0.9, a=SKIP)
    assert cell.verdict == "AGREE"
    assert cell.expert_divergence is None
    assert cell.skipped_by == ["A"]


def test_scored_cells_behave_exactly_as_before_under_v31(tmp_path):
    assert _cells(tmp_path / "a", b=0.7, c=0.3)[0].verdict == "REVIEW"
    assert _cells(tmp_path / "b", b=0.7, c=0.5)[0].verdict == "WATCH"
    assert _cells(tmp_path / "c", b=0.7, c=0.7)[0].verdict == "AGREE"
    (div,) = _cells(tmp_path / "d", b=0.9, c=0.9, a=0.1)
    assert div.expert_divergence == 4


def test_missing_rater_stays_incomplete_even_if_the_other_skipped(tmp_path):
    anchors = _anchors(tmp_path, with_skip=True)
    p = _write(tmp_path / "r", "P-07", "B", {"decision": SKIP})
    (cell,) = build_cells(load_readings([p], load_band_values(anchors), allow_insufficient=True))
    assert cell.verdict == "INCOMPLETE"


# --- three-way ---------------------------------------------------------------------

def test_three_way_counts_skipped_cells_and_excludes_them_from_distances(tmp_path):
    anchors = _anchors(tmp_path, with_skip=True)
    d = tmp_path / "r"
    paths = [
        _write(d, "P-07", "A", {"decision": 0.1, "pace": 0.5}),
        _write(d, "P-07", "B", {"decision": SKIP, "pace": 0.5}),
        _write(d, "P-07", "C", {"decision": 0.9, "pace": 0.9}),
    ]
    summary = twd.run(paths, anchors)
    assert summary["cells_skipped"] == 1
    assert summary["cells_incomplete"] == 0
    assert summary["n_cells"] == 1  # only pace
    assert set(summary) == twd.SUMMARY_KEYS
    assert summary["three_way_spread_distribution"] == {2: 1}


def test_old_three_way_interface_refuses_skips_instead_of_losing_them(tmp_path):
    anchors = _anchors(tmp_path, with_skip=True)
    d = tmp_path / "r"
    paths = [_write(d, "P-07", r, {"decision": SKIP if r == "B" else 0.5}) for r in "ABC"]
    readings = load_readings(paths, load_band_values(anchors), allow_insufficient=True)
    with pytest.raises(AgreementError, match="split_three_way_cells"):
        twd.build_three_way_cells(readings)


# --- the seam: what the page actually emits ----------------------------------------

def test_the_rater_pages_real_payload_loads_as_one_skip(tmp_path):
    """fixtures/v31_page_payload.json is written by test_rater_page.cjs section 13 from a
    jsdom-driven sitting on a page built from anchors_v3_1_PROPOSED.json. If the page and
    this module ever disagree on the shape of a skip, this is where it shows."""
    payload = json.loads((HERE / "fixtures" / "v31_page_payload.json").read_text(encoding="utf-8"))
    anchors = HERE / "anchors_v3_1_PROPOSED.json"
    readings = load_readings([HERE / "fixtures" / "v31_page_payload.json"],
                             load_band_values(anchors),
                             allow_insufficient=permits_insufficient_evidence(anchors))
    assert len(readings) == 6
    assert [r.dimension for r in readings if r.skipped] == ["decision"]
    assert payload["rubric_version"].startswith("v3.1")
    # The same file is refused under the frozen v1 rubric.
    with pytest.raises(AgreementError):
        load_readings([HERE / "fixtures" / "v31_page_payload.json"], BANDS)


# --- the operator report -----------------------------------------------------------

def test_report_prints_a_separate_skipped_line(tmp_path):
    anchors = _anchors(tmp_path, with_skip=True)
    d = tmp_path / "r"
    _write(d, "P-07", "A", {"decision": SKIP, "pace": 0.5})
    _write(d, "P-07", "B", {"decision": SKIP, "pace": 0.5})
    _write(d, "P-07", "C", {"decision": 0.9, "pace": 0.1})
    out = subprocess.run(
        [sys.executable, str(HERE / "run_agreement_report.py"), str(d), "--anchors", str(anchors)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "REVIEW 1 | WATCH 0 | AGREE 0 | INCOMPLETE 0" in out
    assert "SKIPPED 1" in out
    assert "both blind raters skipped 0, one skipped 1" in out
    assert "skips by rater (incl. A): {'A': 1, 'B': 1}" in out
