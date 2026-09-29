"""
test_round1_unchanged.py -- round 1's agreement numbers, pinned against the real returns.

fixtures/round1_agreement_golden.json was captured on 2026-09-29 from the code as it stood
BEFORE the insufficient-evidence change (per-cell verdicts, blind_spread, expert_divergence,
and the three-way summary + records), over the 18 files in returned/round1 and the frozen
anchors.json. These tests assert the current code reproduces it exactly: S-15's 17 REVIEW /
12 WATCH / 7 AGREE, and every number the 2026-09-01 findings rest on.

Never regenerate the fixture from post-change code -- that would make it pin whatever the
code now does, which is the one thing it exists to prevent.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rater_agreement as ra  # noqa: E402
import three_way_dispersion as twd  # noqa: E402

ANCHORS = HERE / "anchors.json"
ROUND1 = HERE / "returned" / "round1"
GOLDEN = json.loads((HERE / "fixtures" / "round1_agreement_golden.json").read_text(encoding="utf-8"))


def _paths():
    return sorted(ROUND1.glob("*.json"))


def _jsonable(x):
    """Round-trip through JSON so int dict keys compare as the fixture stores them."""
    return json.loads(json.dumps(x, sort_keys=True))


def test_frozen_anchors_still_hash_to_the_round1_value():
    cfg = json.loads(ANCHORS.read_text(encoding="utf-8"))
    blob = json.dumps({k: v for k, v in cfg.items() if not k.startswith("_")},
                      sort_keys=True, ensure_ascii=False)
    assert hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12] == "55c4501b25c5"
    assert not ra.permits_insufficient_evidence(ANCHORS), "v1 must never offer a skip"


def test_every_round1_cell_reproduces_exactly():
    readings = ra.load_readings(_paths(), ra.load_band_values(ANCHORS))
    cells = ra.build_cells(readings)
    got = [
        {
            "packet_id": c.packet_id,
            "dimension": c.dimension,
            "blind": c.blind,
            "expert": c.expert,
            "blind_spread": c.blind_spread,
            "verdict": c.verdict,
            "expert_divergence": c.expert_divergence,
        }
        for c in cells
    ]
    assert len(_paths()) == GOLDEN["n_files"] == 18
    assert len(readings) == GOLDEN["n_readings"] == 108
    assert _jsonable(got) == GOLDEN["cells"]


def test_round1_headline_counts():
    cells = ra.build_cells(ra.load_readings(_paths(), ra.load_band_values(ANCHORS)))
    counts = Counter(c.verdict for c in cells)
    assert counts == {"REVIEW": 17, "WATCH": 12, "AGREE": 7}
    assert counts["SKIPPED"] == 0 and counts["INCOMPLETE"] == 0
    assert all(not c.skipped_by for c in cells)


def test_round1_three_way_summary_reproduces_with_zero_skips():
    summary = twd.run(_paths(), ANCHORS)
    assert summary["cells_skipped"] == 0
    without_new_key = {k: v for k, v in summary.items() if k != "cells_skipped"}
    assert _jsonable(without_new_key) == GOLDEN["three_way_summary"]
    assert summary["three_way_spread_distribution"] == {0: 3, 1: 11, 2: 10, 3: 10, 4: 2}


def test_round1_three_way_records_reproduce():
    readings = ra.load_readings(_paths(), ra.load_band_values(ANCHORS))
    cells, incomplete, skipped = twd.split_three_way_cells(readings)
    assert (incomplete, skipped) == (0, 0)
    assert _jsonable(twd.per_cell_records(cells)) == GOLDEN["three_way_records"]
