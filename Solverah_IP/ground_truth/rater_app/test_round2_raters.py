"""
test_round2_raters.py -- rater D (Sebastian, the round-2 reference) and the packet hash.

PREREG_ROUND2_2026-09-29.md addendum A1: D is neither blind nor the rubric's author, so D never
enters the D-12 flag or expert_divergence, and adding D must not change anything that round 1
computes over A, B and C (pinned separately by test_round1_unchanged.py).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_rater_page import packet_sha256  # noqa: E402
from rater_agreement import RATER_ROLES, build_cells, load_readings  # noqa: E402
import three_way_dispersion as twd  # noqa: E402

BANDS = [0.1, 0.3, 0.5, 0.7, 0.9]


def _write(d: Path, packet, rater, scores: dict) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{packet}_rater{rater}.json"
    p.write_text(json.dumps({"packet_id": packet, "rater": rater, "scores": [
        {"dimension": k, "score": v, "confidence": 0.6, "quotes": []} for k, v in scores.items()
    ]}), encoding="utf-8")
    return p


def test_d_is_the_reference_role():
    assert RATER_ROLES["D"] == "reference"
    assert [r for r, role in RATER_ROLES.items() if role == "blind"] == ["B", "C"]


def test_d_never_enters_the_flag_or_expert_divergence(tmp_path):
    paths = [_write(tmp_path, "P-07", r, {"decision": s})
             for r, s in (("B", 0.9), ("C", 0.9), ("A", 0.1), ("D", 0.5))]
    (cell,) = build_cells(load_readings(paths, BANDS))
    assert cell.reference == {"D": 2}
    assert "D" not in cell.blind and "D" not in cell.expert
    assert cell.verdict == "AGREE"            # B and C only
    assert cell.expert_divergence == 4        # still against A, not D


def test_a_round2_cell_with_only_a_and_d_is_incomplete_for_the_flag(tmp_path):
    paths = [_write(tmp_path, "P-10", r, {"pace": s}) for r, s in (("A", 0.3), ("D", 0.7))]
    (cell,) = build_cells(load_readings(paths, BANDS))
    assert cell.verdict == "INCOMPLETE"       # the D-12 flag has no blind readers in round 2
    assert cell.expert_divergence is None


def test_three_way_ignores_d_entirely(tmp_path):
    rows = {"A": 0.1, "B": 0.5, "C": 0.9, "D": 0.5}
    paths = [_write(tmp_path, "P-07", r, {"feedback": s}) for r, s in rows.items()]
    cells, incomplete, skipped = twd.split_three_way_cells(load_readings(paths, BANDS))
    assert (len(cells), incomplete, skipped) == (1, 0, 0)
    assert cells[0].bands == {"A": 0, "B": 2, "C": 4}
    assert cells[0].three_way_spread == 4


REPO = HERE.parents[2]
GT = HERE.parent
NEW_TAGS = [  # the real v4.7-v4.11 attributions that were "unknown" before 2026-09-29
    ("— [news reporting] — local broadcast newsroom, credited to a company press release — 2026-07-24", "company"),
    ("— [company press release, quarterly results] — the Chief Executive Officer — 2026-08-04", "company"),
    ("— [company-published article on how research is done] — corporate voice — 2026-06-09", "company"),
    ("— [employer response] — replying beneath the 2026-09-20 review", "company"),
    ("— [local news reporting] — local news — 2025-11-14", "noncompany"),
    ("— [local television news, independent reporting] — local television news — 2026-05-05", "noncompany"),
]


def _scorer_pipeline():
    sys.path.insert(0, str(REPO / "causal_graph"))
    import scorer_pipeline
    return scorer_pipeline


def test_new_attribution_tags_classify_the_same_in_both_copies():
    from build_rater_page import classify_source as page_classify
    sp = _scorer_pipeline()
    for attribution, expected in NEW_TAGS:
        assert page_classify(attribution) == expected, attribution
        assert sp.classify_source(attribution) == expected, attribution


def test_no_round2_packet_has_an_unclassified_excerpt():
    sp = _scorer_pipeline()
    packets = [GT / "anonymization" / f"P-{n:02d}_packet_ANON.txt" for n in range(1, 13)]
    p13 = GT / "anonymization" / "P-13_packet_ANON.txt"
    packets.append(p13 if p13.exists() else GT / "_scrub_env" / "packets_out" / "P-13_packet_ANON.txt")
    for p in packets:
        if not p.exists():
            continue
        unknown = [e.eid for e in sp.parse_excerpts(sp.load_packet_section1(p)) if e.source_tag == "unknown"]
        assert unknown == [], f"{p.name}: {unknown}"


def test_packet_hash_folds_crlf_and_nothing_else(tmp_path):
    lf, crlf, other = tmp_path / "lf.txt", tmp_path / "crlf.txt", tmp_path / "other.txt"
    lf.write_bytes(b"line one\nline two\n")
    crlf.write_bytes(b"line one\r\nline two\r\n")
    other.write_bytes(b"line one\nline two!\n")
    assert packet_sha256(lf) == packet_sha256(crlf)
    assert packet_sha256(lf) != packet_sha256(other)
    assert len(packet_sha256(lf)) == 64
