"""Julie's fixed order (PREREG_ROUND2 addendum A2) and the round-2 page builder's scrub gate."""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_round2_pages as b  # noqa: E402


def test_julie_order_is_the_preregistered_draw():
    """The literal is what A2 records; it must be exactly what the seed gives, so nobody can
    reorder her packets by editing a list."""
    rest = [p for p in b.ROUND2_PACKETS if p not in ("P-10", "P-11")]
    random.Random(b.JULIE_SEED).shuffle(rest)
    assert b.JULIE_ORDER == ["P-11", "P-10"] + rest


def test_julie_order_starts_with_her_a1_draws_and_covers_every_packet_once():
    assert b.JULIE_ORDER[:2] == ["P-11", "P-10"]
    assert sorted(b.JULIE_ORDER) == b.ROUND2_PACKETS


def test_her_file_names_sort_in_the_order_she_works_in():
    names = [b.julie_page_name(p) for p in b.JULIE_ORDER]
    assert names == sorted(names)
    assert names[0] == "01_P-11_raterA.html" and names[-1] == "13_P-12_raterA.html"


def test_only_packets_that_exist_and_pass_the_scrub_get_pages(tmp_path):
    for pid in ("P-07", "P-08"):
        (tmp_path / f"{pid}_packet_ANON.txt").write_text("x", encoding="utf-8")
    ok, skipped = b.buildable(["P-07", "P-08", "P-09"], anon_dir=tmp_path,
                              verify=lambda pid: pid != "P-08")
    assert ok == ["P-07"]
    assert skipped == {"P-08": "verify_scrub did not PASS", "P-09": "not in anonymization/ yet"}
