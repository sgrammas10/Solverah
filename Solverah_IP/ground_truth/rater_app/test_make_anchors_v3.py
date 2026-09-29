"""
test_make_anchors_v3.py -- the generator reproduces what Julie reviewed, and v3.1 is exactly
v3 plus the changes in V3_1_CHANGES.

Until 2026-09-29 make_anchors_v3.py did not reproduce anchors_v3_PROPOSED.json: the
2026-09-01 edits lived only in the JSON, and a rerun would have silently wiped them. The
first test is the guard against that happening again.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_anchors_v3 as m  # noqa: E402

V1 = json.loads(m.V1_PATH.read_text(encoding="utf-8"))
V3, V3_EDITS = m.build_v3(V1)
V31, LOG = m.build_v3_1(V3)


def _leaves(x, p=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _leaves(v, f"{p}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves(v, f"{p}[{i}]")
    else:
        yield p, x


def test_build_v3_reproduces_the_reviewed_file_exactly():
    assert m.render_v3(V3) == m.read_lf(m.V3_PATH)


def test_v31_and_changelog_on_disk_are_current():
    assert m.read_lf(m.V3_1_PATH) == m.render(V31)
    assert m.read_lf(m.CHANGELOG_PATH) == m.changelog_markdown(LOG)


def test_v31_differs_from_v3_only_where_a_change_says_so():
    before, after = dict(_leaves(V3)), dict(_leaves(V31))
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    replacements = [c for c in m.V3_1_CHANGES if c["op"] == "replace_in"]
    explained = {".rubric_version", "._note",
                 ".insufficient_evidence.label", ".insufficient_evidence.text",
                 ".agreement_rule.insufficient_evidence"}
    for p in changed:
        if p in explained:
            continue
        owners = [c["id"] for c in replacements if c["new"] in str(after.get(p))]
        assert len(owners) == 1, f"{p} changed but no single V3_1_CHANGES entry accounts for it"
    # one leaf per replacement (no two replacements share a field), plus the fixed set
    assert len(changed) == len(replacements) + len(explained)


@pytest.mark.parametrize("ch", [c for c in m.V3_1_CHANGES if c["op"] == "replace_in"],
                         ids=lambda c: c["id"])
def test_each_replacement_landed_once_and_the_old_text_is_gone(ch):
    container, key = m._locate(V31, ch["path"])
    assert container[key].count(ch["new"]) == 1
    if ch["old"] not in ch["new"]:
        assert ch["old"] not in container[key]


def test_ruling_texts_carry_her_words():
    fb01 = next(b for b in m.dim(V31, "feedback")["bands"] if b["value"] == 0.1)["text"]
    assert "candid developmental or corrective input is rare in the evidence" in fb01
    assert "open disagreement" not in fb01
    dec05 = next(b for b in m.dim(V31, "decision")["bands"] if b["value"] == 0.5)["text"]
    assert "that is what it exists for" not in dec05
    assert "neither predominates" in dec05
    assert "picking the quote you find most persuasive" in dec05  # warning kept
    decision_kd = m.dim(V31, "decision")["keep_distinct"]
    assert "“following procedures,”" not in decision_kd
    assert "“A procedure governing decision-making” is Decision evidence" in decision_kd
    assert "Do NOT count language about approval layers" not in m.dim(V31, "decision")["where_to_look"]


def test_insufficient_evidence_block_and_rule():
    keys = list(V31)
    assert keys.index("insufficient_evidence") == keys.index("confidence_bands") + 1
    assert V31["insufficient_evidence"]["label"] == "Insufficient evidence"
    assert "not 0.5" in V31["insufficient_evidence"]["text"]
    assert "neither agreement nor disagreement" in V31["agreement_rule"]["insufficient_evidence"]
    # The D-12 rule keys are untouched, so rater_agreement still reads the file.
    for k in ("same_band", "one_band_apart", "two_or_more_bands_apart"):
        assert V31["agreement_rule"][k] == V1["agreement_rule"][k]


def test_scales_are_unchanged_so_band_indices_and_schemas_still_line_up():
    assert V31["band_values"] == V1["band_values"]
    assert [b["value"] for b in V31["confidence_bands"]] == [b["value"] for b in V1["confidence_bands"]]
    for d1, d31 in zip(V1["dimensions"], V31["dimensions"]):
        assert d1["key"] == d31["key"]
        assert [b["value"] for b in d1["bands"]] == [b["value"] for b in d31["bands"]]


def test_derived_changes_are_marked_and_asked_about():
    for ch in m.V3_1_CHANGES:
        if ch["derived"]:
            assert ch["her_words"] is None and ch["ask"]
            assert "my inference" in ch["title"]
        else:
            assert ch["her_words"]
    assert {c["id"] for c in m.V3_1_CHANGES if c["derived"]} == {"D1", "D2"}
    assert {c["ruling"] for c in m.V3_1_CHANGES} == {1, 2, 3, 4, 5}


def test_the_frozen_files_are_never_written(tmp_path):
    for p in (m.V1_PATH, m.V3_PATH):
        with pytest.raises(RuntimeError, match="frozen record"):
            m._write(p, "x")


def test_a_drifted_source_fails_loudly():
    drifted = json.loads(json.dumps(V3))
    m.dim(drifted, "feedback")["bands"][0]["text"] = "something else"
    with pytest.raises(AssertionError, match="R1"):
        m.build_v3_1(drifted)
