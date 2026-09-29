"""The confirm sheet covers every v3.1 change Julie is asked about, and is not stale."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_confirm_sheet as bcs  # noqa: E402


def test_on_disk_sheet_matches_a_fresh_build():
    on_disk = (HERE / "confirm_sheet.html").read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert on_disk == bcs.build()


def test_every_askable_change_is_on_the_sheet_exactly_once():
    covered = [e["change_id"] for it in bcs.items() for e in it["edits"]]
    askable = [c["id"] for c in bcs.mav.V3_1_CHANGES if c["ask"] is not None]
    assert sorted(covered) == sorted(askable)
    assert len(covered) == len(set(covered))
    assert "R4-rule" not in covered


def test_seven_items_five_rulings_then_two_derived():
    its = bcs.items()
    assert [it["id"] for it in its] == [
        "ruling-1", "ruling-2", "ruling-3", "ruling-4", "ruling-5", "D1", "D2"]
    assert all(it["her_words"] for it in its if not it["derived"])
    assert all(it["her_words"] is None for it in its if it["derived"])


def test_ruling3_asks_the_construct_question_not_a_bare_right():
    r3 = next(it for it in bcs.items() if it["id"] == "ruling-3")
    assert "judgement to data" in r3["ask"]
