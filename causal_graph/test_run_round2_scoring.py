"""
test_run_round2_scoring.py -- the round-2 runner's gates and output, with a FAKE client.

No test here can reach the API: the client is always a stand-in, and causal_graph/conftest.py
poisons the key besides.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_round2_scoring as rr
import scorer_pipeline as sp

requires_repo_ip = pytest.mark.skipif(not rr.ANCHORS_V31.exists(), reason="Solverah_IP not present")
PID = "P-09"   # in anonymization/ and passed verify_scrub on 2026-09-29


class FakeClient:
    def __init__(self, decision_abstains=False):
        self.calls = 0
        outer = self

        class _C:
            def create(self, **kwargs):
                outer.calls += 1
                body = {d: {"score": 0.5, "confidence": 0.6,
                            "evidence_quotes": ["not a real quote from the packet"]}
                        for d in sp.DIMENSIONS}
                if decision_abstains:
                    body["decision"] = {"score": None, "confidence": None, "evidence_quotes": []}
                msg = SimpleNamespace(content=json.dumps(body))
                return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        self.chat = SimpleNamespace(completions=_C())


def _submit(returned: Path, pid=PID, sha=None):
    returned.mkdir(parents=True, exist_ok=True)
    sha = sha or rr.packet_sha256(sp.packet_path_for(pid))
    (returned / f"solverah_{pid}_raterD.json").write_text(json.dumps(
        {"packet_id": pid, "rater": "D", "packet_sha256": sha, "scores": []}), encoding="utf-8")


def _plan(tmp_path, **kw):
    return rr.plan([PID], returned=tmp_path / "returned", verify=kw.pop("verify", lambda p: True), **kw)


@requires_repo_ip
def test_refuses_a_packet_the_reference_has_not_submitted(tmp_path):
    (row,), _ = _plan(tmp_path)
    assert not row["ok"] and "rater D has not submitted" in row["reasons"][0]


@requires_repo_ip
def test_refuses_a_submission_on_a_different_packet_file(tmp_path):
    _submit(tmp_path / "returned", sha="0" * 64)
    (row,), _ = _plan(tmp_path)
    assert not row["ok"] and any("packet_sha256 does not match" in r for r in row["reasons"])


@requires_repo_ip
def test_refuses_when_verify_scrub_fails(tmp_path):
    _submit(tmp_path / "returned")
    (row,), _ = _plan(tmp_path, verify=lambda p: False)
    assert not row["ok"] and "verify_scrub" in row["reasons"][0]


@requires_repo_ip
def test_refuses_round1_packets_and_unharvested_ones(tmp_path):
    rows, _ = rr.plan(["P-01", "P-19"], returned=tmp_path, verify=lambda p: True)
    assert [r["ok"] for r in rows] == [False, False]
    assert "not a round-2 packet" in rows[0]["reasons"][0]
    assert "not in anonymization/" in rows[1]["reasons"][0]


@requires_repo_ip
def test_ready_packet_writes_three_draws_with_everything_the_analysis_needs(tmp_path):
    _submit(tmp_path / "returned")
    rows, anchors = _plan(tmp_path)
    assert rows[0]["ok"] and rows[0]["est_input_tokens_per_call"] > 1000
    client = FakeClient(decision_abstains=True)
    written = rr.run_live(client, rows, anchors, out=tmp_path / "out")
    assert client.calls == 3 and [p.name for p in written] == [f"{PID}_draw{n}.json" for n in (1, 2, 3)]
    doc = json.loads(written[0].read_text(encoding="utf-8"))
    assert doc["rubric_version"] == anchors["rubric_version"] and doc["anchors_hash"] == "3e270b206116"
    assert doc["packet_sha256"] == rr.packet_sha256(sp.packet_path_for(PID))
    dec = next(d for d in doc["result"]["dimensions"] if d["dimension"] == "decision")
    assert dec["score"] is None and dec.get("insufficient_evidence") is True
    assert all(c["matched"] is False for c in doc["citations"])   # fake quotes do not verify
    # The request actually offered the skip.
    # (score_packet refuses a rubric/schema mismatch before calling, so reaching 3 calls proves it.)


@requires_repo_ip
def test_draw_files_are_never_overwritten(tmp_path):
    _submit(tmp_path / "returned")
    rows, anchors = _plan(tmp_path)
    rr.run_live(FakeClient(), rows, anchors, out=tmp_path / "out")
    client = FakeClient()
    with pytest.raises(FileExistsError):
        rr.run_live(client, rows, anchors, out=tmp_path / "out")
    assert client.calls == 0


def test_live_needs_the_env_var_too(monkeypatch, capsys):
    monkeypatch.delenv("SOLVERAH_ALLOW_LIVE_CALLS", raising=False)
    monkeypatch.setattr(rr, "plan", lambda packets: ([{"packet_id": "P-09", "ok": True, "reasons": [],
                                                       "est_input_tokens_per_call": 10}],
                                                     {"rubric_version": "v3.1"}))
    assert rr.main(["P-09", "--live"]) == 2
    assert "SOLVERAH_ALLOW_LIVE_CALLS=1" in capsys.readouterr().out


@requires_repo_ip
def test_hashes_match_the_rater_pages():
    sys.path.insert(0, str(rr.RATER_APP))
    from build_rater_page import packet_sha256 as page_sha
    p = sp.packet_path_for(PID)
    assert rr.packet_sha256(p) == page_sha(p)
    assert rr.anchors_hash(sp.load_anchors(rr.ANCHORS_V31)) == "3e270b206116"
