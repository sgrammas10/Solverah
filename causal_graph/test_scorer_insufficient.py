"""
test_scorer_insufficient.py -- the LLM's "insufficient evidence" abstention (Julie's ruling 4).

Two halves:
  1. Under the frozen v1 anchors, nothing a scoring call sends has changed. The response
     schema, the rubric text and the full request kwargs are compared against
     fixtures/scorer_v1_golden.json, captured from the code BEFORE this change on
     2026-09-29 with a fake client. Never regenerate that fixture from post-change code.
  2. Under anchors v3.1 the model may return score and confidence null, and every consumer
     in this directory that reads a score survives it.

No test here calls the API; the client is always faked.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scorer_pipeline as sp
from extremity_flag import ManualBandProbe, flag_dimension

HERE = Path(__file__).resolve().parent
GOLDEN = json.loads((HERE / "fixtures" / "scorer_v1_golden.json").read_text(encoding="utf-8"))
V31_PATH = sp.REPO_IP / "ground_truth" / "rater_app" / "anchors_v3_1_PROPOSED.json"
V3_PATH = sp.REPO_IP / "ground_truth" / "rater_app" / "anchors_v3_PROPOSED.json"

requires_repo_ip = pytest.mark.skipif(
    not sp.ANCHORS_PATH.exists(), reason=f"Solverah_IP not found at {sp.REPO_IP}")


class _FakeClient:
    """Records the kwargs of the one create() call and returns `body` as the message."""

    def __init__(self, body: dict):
        self.kwargs: dict = {}
        self.calls = 0
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls += 1
                outer.kwargs = kwargs
                msg = SimpleNamespace(content=json.dumps(body))
                return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        self.chat = SimpleNamespace(completions=_Completions())


def _body(**overrides):
    body = {d: {"score": 0.5, "confidence": 0.6, "evidence_quotes": ["x" * 12]}
            for d in sp.DIMENSIONS}
    body.update(overrides)
    return body


def _jsonable(x):
    return json.loads(json.dumps(x, sort_keys=True, ensure_ascii=False))


# --- 1. v1 is byte-identical --------------------------------------------------------

@requires_repo_ip
def test_v1_rubric_text_is_unchanged():
    anchors = sp.load_anchors()
    assert anchors["rubric_version"] == GOLDEN["anchors_rubric_version"] == "v1-frozen-2026-08-15"
    assert sp.build_rubric_text(anchors) == GOLDEN["rubric_text"]


def test_v1_response_schema_is_unchanged():
    assert _jsonable(sp.RESPONSE_SCHEMA) == GOLDEN["response_schema"]
    assert sp.response_schema() is sp.RESPONSE_SCHEMA
    assert sp.response_schema(False) is sp.RESPONSE_SCHEMA


@requires_repo_ip
def test_v1_request_is_unchanged_down_to_the_kwargs():
    anchors = sp.load_anchors()
    client = _FakeClient(_body())
    sp.score_packet(client, "PACKET-TEXT-PLACEHOLDER", sp.build_rubric_text(anchors),
                    packet_id="P-01", rubric_version=anchors["rubric_version"],
                    packet_version="v4.6")
    assert _jsonable(client.kwargs) == GOLDEN["request_kwargs"]


@requires_repo_ip
def test_v3_without_the_block_also_gets_the_old_schema():
    anchors = sp.load_anchors(V3_PATH)
    assert not sp.permits_insufficient_evidence(anchors)
    assert sp.INSUFFICIENT_MARKER not in sp.build_rubric_text(anchors)


# --- 2. v3.1 abstention -------------------------------------------------------------

@requires_repo_ip
def test_v31_rubric_offers_the_skip_and_drops_the_round1_claim():
    anchors = sp.load_anchors(V31_PATH)
    assert sp.permits_insufficient_evidence(anchors)
    text = sp.build_rubric_text(anchors)
    assert sp.INSUFFICIENT_MARKER in text
    assert anchors["insufficient_evidence"]["text"] in text
    assert "frozen for round 1" not in text


def test_nullable_schema_shape_keeps_every_key_required():
    dim = sp.RESPONSE_SCHEMA_INSUFFICIENT["properties"]["decision"]
    assert dim["required"] == ["score", "confidence", "evidence_quotes"]
    assert dim["additionalProperties"] is False
    assert {"type": "null"} in dim["properties"]["score"]["anyOf"]
    assert {"type": "null"} in dim["properties"]["confidence"]["anyOf"]
    assert dim["properties"]["evidence_quotes"]["minItems"] == 0
    assert sp.response_schema(True) is sp.RESPONSE_SCHEMA_INSUFFICIENT


def test_nullable_schema_validates_as_intended():
    jsonschema = pytest.importorskip("jsonschema")
    ok = _body(decision={"score": None, "confidence": None, "evidence_quotes": []})
    jsonschema.validate(ok, sp.RESPONSE_SCHEMA_INSUFFICIENT)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(ok, sp.RESPONSE_SCHEMA)  # v1 schema still refuses it
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_body(decision={"score": 0.75, "confidence": 0.6, "evidence_quotes": []}),
                            sp.RESPONSE_SCHEMA_INSUFFICIENT)


@requires_repo_ip
def test_score_packet_returns_an_abstention_and_sends_the_nullable_schema():
    anchors = sp.load_anchors(V31_PATH)
    # The model attaches a confidence to its abstention; it must not survive.
    client = _FakeClient(_body(decision={"score": None, "confidence": 0.6, "evidence_quotes": []}))
    result = sp.score_packet(client, "PACKET", sp.build_rubric_text(anchors), packet_id="P-07",
                             rubric_version=anchors["rubric_version"], packet_version="v4.8",
                             allow_insufficient_evidence=True)
    sent = client.kwargs["response_format"]["json_schema"]["schema"]
    assert sent is sp.RESPONSE_SCHEMA_INSUFFICIENT
    assert "score null and confidence null" in client.kwargs["messages"][0]["content"]
    dec = next(d for d in result.dimensions if d.dimension == "decision")
    assert dec.score is None and dec.confidence is None and dec.insufficient_evidence
    assert all(d.score == 0.5 for d in result.dimensions if d.dimension != "decision")
    row = next(r for r in result.to_dict()["dimensions"] if r["dimension"] == "decision")
    assert row == {"dimension": "decision", "score": None, "confidence": None,
                   "evidence_quotes": [], "insufficient_evidence": True}
    json.dumps(result.to_dict())


@requires_repo_ip
@pytest.mark.parametrize("allow", [True, False])
def test_a_rubric_and_flag_mismatch_is_refused_before_any_call(allow):
    anchors = sp.load_anchors(sp.ANCHORS_PATH if allow else V31_PATH)
    client = _FakeClient(_body())
    with pytest.raises(ValueError, match="disagree"):
        sp.score_packet(client, "PACKET", sp.build_rubric_text(anchors), packet_id="P-07",
                        rubric_version="x", packet_version="x", allow_insufficient_evidence=allow)
    assert client.calls == 0


def test_a_null_score_without_permission_is_an_explicit_error():
    client = _FakeClient(_body(pace={"score": None, "confidence": None, "evidence_quotes": []}))
    with pytest.raises(ValueError, match="offers no skip"):
        sp.score_packet(client, "PACKET", "RUBRIC", packet_id="P-01", rubric_version="v1",
                        packet_version="v4.6")


def test_a_score_with_null_confidence_is_an_explicit_error():
    client = _FakeClient(_body(pace={"score": 0.3, "confidence": None, "evidence_quotes": ["y" * 12]}))
    with pytest.raises(ValueError, match="null confidence"):
        sp.score_packet(client, "PACKET", f"{sp.INSUFFICIENT_MARKER} ...", packet_id="P-07",
                        rubric_version="v3.1", packet_version="v4.8",
                        allow_insufficient_evidence=True)


def test_scored_rows_serialize_exactly_as_before():
    d = sp.DimensionScore("autonomy", 0.7, 0.6, ["quote"])
    result = sp.ScorerResult("P-01", sp.MODEL, "v1", "v4.6", True, "medium", "t", [d])
    assert result.to_dict()["dimensions"][0] == {
        "dimension": "autonomy", "score": 0.7, "confidence": 0.6, "evidence_quotes": ["quote"]}


def test_verifier_and_noncompany_support_tolerate_an_abstention():
    result = sp.ScorerResult("P-07", sp.MODEL, "v3.1", "v4.8", True, "medium", "t",
                             [sp.DimensionScore(d, None, None, []) for d in sp.DIMENSIONS])
    assert sp.verify_result(result, "no excerpts here") == []
    assert not any(sp.noncompany_support(result, "no excerpts here").values())


class _ProbeMustNotRun(ManualBandProbe):
    """A live probe is an API call; reaching this one fails the test."""

    def probe(self, quotes, dimension):
        raise AssertionError("probe called for an abstention")


def test_extremity_flag_skips_an_abstention_without_spending_a_probe():
    f = flag_dimension(packet_id="P-07", dimension="autonomy", score=None,
                       quotes=["a verified quote that would otherwise be probed"],
                       verified_map={"a verified quote that would otherwise be probed": True},
                       probe=_ProbeMustNotRun({}))
    assert f.flag is None and f.score is None and f.probes == []
    assert "Insufficient evidence" in f.rationale
