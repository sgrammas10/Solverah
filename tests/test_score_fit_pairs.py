"""score_fit_pairs: determinism, spec hash, design_check never read, schema shape."""

from __future__ import annotations

import hashlib
import json

import pytest

from causal_graph.v1_model import score_fit_pairs as S

STAMP = "2026-10-14T00:00:00+00:00"


@pytest.fixture(scope="module")
def spec_bytes() -> bytes:
    return S.DEFAULT_SPECS.read_bytes()


def test_deterministic(spec_bytes):
    a = S.score_specs(spec_bytes, scored_at=STAMP)
    b = S.score_specs(spec_bytes, scored_at=STAMP)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_spec_sha_recorded(spec_bytes):
    out = S.score_specs(spec_bytes, scored_at=STAMP)
    assert out["spec_sha256"] == hashlib.sha256(spec_bytes).hexdigest()


def test_design_check_is_never_read(spec_bytes):
    doc = json.loads(spec_bytes)
    for p in doc["pairs"]:
        p.pop("design_check")
    stripped = json.dumps(doc).encode("utf-8")
    a = S.score_specs(spec_bytes, scored_at=STAMP)
    b = S.score_specs(stripped, scored_at=STAMP)
    assert a["pairs"] == b["pairs"]


def test_output_matches_prereg_schema(spec_bytes):
    spec = json.loads(spec_bytes)
    out = S.score_specs(spec_bytes, scored_at=STAMP)
    assert out["schema"] == "fit_pairs_model_scores_v1"
    assert out["model"]["weights_source"] == "priors"
    assert out["model"]["model_run_id"] is None
    for k in ("priors_sha256", "git_sha", "scored_at"):
        assert k in out["model"]
    assert [r["pair_id"] for r in out["pairs"]] == [p["pair_id"] for p in spec["pairs"]]
    for r in out["pairs"]:
        assert set(r) == {"pair_id", "state", "z", "must_have_break", "risk_flag",
                          "next_step", "rank_in_block"}
        assert r["state"] in ("ranked", "not_enough_evidence")
        assert r["next_step"] in ("decide", "investigate", "explore")
        assert isinstance(r["must_have_break"], bool) and isinstance(r["risk_flag"], bool)
        if r["state"] == "ranked":
            assert isinstance(r["z"], float) and isinstance(r["rank_in_block"], int)
        else:
            assert r["z"] is None and r["rank_in_block"] is None
