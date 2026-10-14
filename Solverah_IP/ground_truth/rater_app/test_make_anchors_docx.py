"""
test_make_anchors_docx.py -- the rubric document marks what changed, computed at render time.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

docx = pytest.importorskip("docx")
import make_anchors_docx as mad  # noqa: E402
import make_anchors_v3 as mav  # noqa: E402


def _text(path: Path) -> str:
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts += [c.text for c in row.cells]
    return "\n".join(parts)


@pytest.fixture(scope="module")
def v31_doc(tmp_path_factory):
    out = tmp_path_factory.mktemp("docx") / "v31.docx"
    marked = mad.build(mav.V3_1_PATH, out)
    return out, marked, _text(out)


def test_every_v31_change_is_tagged_exactly_once(v31_doc):
    _, marked, text = v31_doc
    assert sorted(marked) == sorted(tuple(c["path"]) for c in mav.V3_1_CHANGES)
    for ch in mav.V3_1_CHANGES:
        assert text.count(f"v3.1 change {ch['id']} (") == 1, ch["id"]


def test_derived_changes_say_they_are_inferences(v31_doc):
    _, _, text = v31_doc
    for ch in mav.V3_1_CHANGES:
        if ch["derived"]:
            assert f"v3.1 change {ch['id']} (derived from ruling 4: MY INFERENCE" in text


def test_prior_wording_is_shown_beneath_a_changed_field(v31_doc):
    _, _, text = v31_doc
    # Feedback 0.1 in v1, and the confidence 0.1 text in v1.
    assert "Was (v1): Feedback is occasional and softened. Harmony valued, conflict avoided" in text
    assert "Was (v1): Almost nothing in the packet bears on this dimension. You are close to guessing." in text
    assert "candid developmental or corrective input is rare in the evidence" in text
    assert "Insufficient evidence -- no score" in text


def test_the_frozen_v1_renders_with_no_change_markers(tmp_path):
    out = tmp_path / "v1.docx"
    marked = mad.build(mav.V1_PATH, out)
    text = _text(out)
    assert marked == []
    assert "[CHANGED since v1]" not in text and "[NEW since v1]" not in text
    assert "Was (v1)" not in text
