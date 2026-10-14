"""The bundled docx carries every section and no literal markdown symbols.

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest Solverah_IP/match_model_alignment -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
docx = pytest.importorskip("docx")
import make_alignment_docx as mad  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("docx") / "bundle.docx"
    mad.build(out)
    return docx.Document(str(out))


def _texts(document):
    """(text, is_diagram) for every paragraph and table cell."""
    for p in document.paragraphs:
        mono = any(r.font.name == "Consolas" for r in p.runs) and "\n" in p.text
        yield p.text, mono
    for t in document.tables:
        for row in t.rows:
            for cell in row.cells:
                yield cell.text, False


def test_every_source_heading_present(built):
    headings = [p.text for p in built.paragraphs if p.style.name.startswith(("Heading", "Title"))]
    for name in mad.SOURCES:
        first = next(line for line in (HERE / name).read_text(encoding="utf-8").splitlines()
                     if line.startswith("# "))
        assert first[2:] in headings, name


def test_no_literal_markdown(built):
    bad = re.compile(r"\*\*|`|^#{1,6} |^\|.*\|$|^\s*[-*] |^-{3,}$|\[\[")
    offenders = [t for t, diagram in _texts(built) if not diagram
                 for line in t.splitlines() if bad.search(line)]
    assert offenders == []


def test_tables_and_diagram_render(built):
    expected = 0
    for name in mad.SOURCES:
        prev, fenced = False, False
        for line in (HERE / name).read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("```"):
                fenced = not fenced
            is_row = not fenced and line.strip().startswith("|")
            expected += is_row and not prev
            prev = is_row
    assert expected > 0 and len(built.tables) == expected
    assert any(diagram for _, diagram in _texts(built))


def test_private_anecdote_not_present():
    # The priors free note's story about a member of Julie's team stays out of these docs.
    for name in mad.SOURCES + ["JULIE_BRIEF_2026-10.md"]:
        text = (HERE / name).read_text(encoding="utf-8").lower()
        assert "on my team" not in text and "someone on my team" not in text, name
