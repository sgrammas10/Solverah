"""Regression tests for Scripts/verify_scrub.py's quote-fidelity check (check 3).

Found 2026-09-29 on P-13: check 3 paired a quote only when a dash followed it directly, so
two bullet shapes were dropped from the comparison without a word -- a truncated review,
`"..." [...]  -- [employee review]`, and a press quote with its attribution after it,
`"...," Name said.  -- [trade press]`. 5 of P-13's 55 bullets went unchecked while the
verdict read PASSED. The press shape is exactly where a scrub edits names inside quotes.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "Scripts" / "verify_scrub.py"


@pytest.fixture(scope="module")
def verify_scrub():
    spec = importlib.util.spec_from_file_location("verify_scrub", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FILLER = [
    '"We value clear, direct feedback between teams." — [company careers site] — corporate voice',
] * 10


def _packet(header: str, bullets: list[str]) -> str:
    body = "\n\n".join("   • " + b for b in bullets)
    return (
        header
        + "\n########## SECTION 1 — EVIDENCE PACKET ##########\n\n"
        + "--- A. CAREERS / VALUES PAGE (5–20 excerpts) ---\n\n"
        + body
        + "\n\n########## END OF PACKET ##########\n"
    )


def _write(tmp_path: Path, raw_bullets: list[str], scr_bullets: list[str]) -> Path:
    gt = tmp_path / "ground_truth"
    (gt / "packets" / "P-99_testco").mkdir(parents=True)
    (gt / "anonymization").mkdir(parents=True)
    (gt / "packets" / "P-99_testco" / "P-99_packet.txt").write_text(
        _packet("BUILD RECORD\n  prompt version : v4.11\n", raw_bullets), encoding="utf-8")
    (gt / "anonymization" / "P-99_packet_ANON.txt").write_text(
        _packet("PACKET P-99\n  scrubbed from : P-99_packet.txt (build v4.11, model x, "
                "built 2026-09-29)\n", scr_bullets), encoding="utf-8")
    return tmp_path


def _run(verify_scrub, ip_dir: Path, capsys) -> tuple[int, str]:
    rc = verify_scrub.main(["P-99", "--company", "Testco", "--ip-dir", str(ip_dir)])
    return rc, capsys.readouterr().out


def test_undeclared_edit_in_truncated_review_fails(verify_scrub, tmp_path, capsys):
    raw = FILLER + ['"The managers here really listen to drivers and" [...]  — [employee review] — driver']
    scr = FILLER + ['"The managers here rarely listen to drivers and" [...]  — [employee review] — driver']
    rc, out = _run(verify_scrub, _write(tmp_path, raw, scr), capsys)
    assert rc == 1, out
    assert "NO bracketed declaration" in out


def test_undeclared_edit_before_said_attribution_fails(verify_scrub, tmp_path, capsys):
    raw = FILLER + ['"Our strength is adapting fast," the chief executive said.  — [trade press]']
    scr = FILLER + ['"Our strength is adapting slowly," the chief executive said.  — [trade press]']
    rc, out = _run(verify_scrub, _write(tmp_path, raw, scr), capsys)
    assert rc == 1, out
    assert "NO bracketed declaration" in out


def test_undeclared_edit_after_an_inner_quote_fails(verify_scrub, tmp_path, capsys):
    # A quote that itself contains a quote. Matching to the FIRST closing mark would compare
    # only `They call it ` and miss an edit after the inner quote entirely.
    raw = FILLER + ['"They call it "the family" here and mean it."  — [employee review] — driver']
    scr = FILLER + ['"They call it "the family" here and never mean it."  — [employee review] — driver']
    rc, out = _run(verify_scrub, _write(tmp_path, raw, scr), capsys)
    assert rc == 1, out
    assert "NO bracketed declaration" in out


def test_clean_packet_compares_every_quoted_bullet_and_lists_unquoted(verify_scrub, tmp_path, capsys):
    shapes = [
        '"Short shifts, fair pay." [...]  — [employee review] — driver',
        '"We adapt quickly," the chief executive said.  — [trade press]',
    ]
    unquoted = "Headcount rose over the year.  — [annual report]"
    bullets = FILLER + shapes + [unquoted]
    rc, out = _run(verify_scrub, _write(tmp_path, bullets, bullets), capsys)
    assert rc == 0, out
    assert "quotes compared        : 12" in out
    assert "not compared           : 1" in out
    assert "Headcount rose" in out
