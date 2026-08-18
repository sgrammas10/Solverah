"""
test_scorer_pipeline.py -- S1-7: pytest suite + end-to-end dry run on P-01.

Per this project's testing convention (CLAUDE.md): prefer real dependencies over mocks,
only mock external services. Every test here runs against the REAL anchors.json and
REAL anonymized packets in Solverah_IP -- nothing here is a synthetic fixture standing
in for real data, because scorer_pipeline.py's whole point is correctness against the
actual instrument raters are using. The only mocked thing anywhere is the OpenAI client
itself (the external service), in the two places that need one.

Not in causal_graph/pytest.ini's testpaths (that file scopes to the Flask app's tests/
directory) -- run explicitly:

    pytest causal_graph/test_scorer_pipeline.py -v          # offline tests only
    pytest causal_graph/test_scorer_pipeline.py -v -m live  # + the real API dry run
                                                              # (needs OPENAI_API_KEY)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import scorer_pipeline as sp

pytestmark = []


def _has_repo_ip() -> bool:
    return sp.ANCHORS_PATH.exists()


requires_repo_ip = pytest.mark.skipif(
    not _has_repo_ip(), reason=f"Solverah_IP not found at {sp.REPO_IP} -- connect it to run these tests"
)


# ---------------------------------------------------------------------------
# S1-1: packet_version_for()
# ---------------------------------------------------------------------------
@requires_repo_ip
@pytest.mark.parametrize("packet_id", sp.VALID_PACKETS)
def test_packet_version_matches_known_build(packet_id):
    # All six packets are confirmed (verified by hand this session) to say "build v4.6"
    # in their header. If this ever fails, it means a packet was rebuilt under a new
    # collector-prompt version and packet_version tracking is doing its job by catching it.
    version = sp.packet_version_for(sp.packet_path_for(packet_id))
    assert version == "v4.6"


def test_packet_version_missing_marker_raises(tmp_path):
    bad_file = tmp_path / "fake_packet.txt"
    bad_file.write_text("no version marker anywhere in here\n########## SECTION 1 stuff", encoding="utf-8")
    with pytest.raises(ValueError, match="build vX.Y"):
        sp.packet_version_for(bad_file)


# ---------------------------------------------------------------------------
# S1-1/port: parse_excerpts() + classify_source() vs known-good counts
# ---------------------------------------------------------------------------
# Ground truth: the EXACT excerpt/source-class counts build_rater_page.py reported when
# actually run against these six packets earlier this session (see the rater-page-
# generation output). This is the strongest test in the suite -- it's not just "does the
# code run," it's "does the port reproduce known-correct numbers from the real,
# independently-run production tool," on real data.
KNOWN_GOOD_COUNTS = {
    "P-01": (45, 24, 18, 3, 0), "P-02": (48, 25, 19, 4, 0),
    "P-03": (37, 22, 15, 0, 0), "P-04": (45, 24, 21, 0, 0),
    "P-05": (23, 12, 0, 10, 1), "P-06": (46, 24, 20, 2, 0),
}


@requires_repo_ip
@pytest.mark.parametrize("packet_id,expected", KNOWN_GOOD_COUNTS.items())
def test_parse_excerpts_matches_build_rater_page(packet_id, expected):
    section1 = sp.load_packet_section1(sp.packet_path_for(packet_id))
    excerpts = sp.parse_excerpts(section1)
    counts = (
        len(excerpts),
        sum(1 for e in excerpts if e.source_tag == "company"),
        sum(1 for e in excerpts if e.source_tag == "noncompany"),
        sum(1 for e in excerpts if e.source_tag == "disputed"),
        sum(1 for e in excerpts if e.source_tag == "researcher"),
    )
    assert counts == expected


@requires_repo_ip
@pytest.mark.parametrize("packet_id", sp.VALID_PACKETS)
def test_parse_excerpts_has_no_unclassified(packet_id):
    # build_rater_page.py fails its own build on any 'unknown' excerpt -- the port
    # must hold to the same bar, since an unclassified quote can't feed the <=0.7
    # measurement either way.
    section1 = sp.load_packet_section1(sp.packet_path_for(packet_id))
    excerpts = sp.parse_excerpts(section1)
    unknown = [e for e in excerpts if e.source_tag == "unknown"]
    assert unknown == [], f"{len(unknown)} unclassified excerpt(s): {[e.eid for e in unknown]}"


class TestClassifySource:
    def test_employee_review(self):
        assert sp.classify_source('— [employee review rev-13]') == "noncompany"

    def test_researcher_observation(self):
        assert sp.classify_source('— [researcher observation]') == "researcher"

    def test_absence_recorded(self):
        assert sp.classify_source('— [absence recorded]') == "researcher"

    def test_trade_press(self):
        assert sp.classify_source('— [trade press]') == "noncompany"

    def test_10k_is_company(self):
        assert sp.classify_source('— [10-K Item 1 Human Capital]') == "company"

    def test_job_posting_is_company(self):
        assert sp.classify_source('— [job posting]') == "company"

    def test_company_run_outlet_executive_byline_is_company(self):
        result = sp.classify_source('— [company newsroom article]', byline="the incoming CEO (executive)")
        assert result == "company"

    def test_company_run_outlet_employee_byline_is_disputed(self):
        # this is the whole reason the 'disputed' class exists -- 08-15b open question 5
        result = sp.classify_source('— [company engineering blog]', byline="a senior engineer")
        assert result == "disputed"

    def test_unrecognized_attribution_is_unknown(self):
        assert sp.classify_source('— [some entirely novel source type nobody has seen]') == "unknown"


# ---------------------------------------------------------------------------
# S1-5: citation verifier
# ---------------------------------------------------------------------------
@requires_repo_ip
class TestCitationVerifier:
    @pytest.fixture
    def p02_excerpts(self):
        section1 = sp.load_packet_section1(sp.packet_path_for("P-02"))
        return section1, sp.parse_excerpts(section1)

    def test_exact_quote_matches(self, p02_excerpts):
        _, excerpts = p02_excerpts
        real = next(e for e in excerpts if len(e.text) > 100 and e.source_tag == "company")
        quote = real.text[10:90].strip()
        matched, eid, src = sp.verify_quote(quote, excerpts)
        assert matched and eid == real.eid and src == real.source_tag

    def test_em_dash_and_whitespace_corruption_still_matches(self, p02_excerpts):
        # the exact 08-15b bug: a retype silently swapped ASCII hyphens for em dashes.
        _, excerpts = p02_excerpts
        real = next(e for e in excerpts if len(e.text) > 100 and e.source_tag == "company")
        clean = real.text[10:90].strip()
        corrupted = clean.replace("-", "—").replace(" ", "   ")
        matched, eid, _ = sp.verify_quote(corrupted, excerpts)
        assert matched and eid == real.eid

    def test_smart_quotes_still_match(self, p02_excerpts):
        _, excerpts = p02_excerpts
        real = next(e for e in excerpts if len(e.text) > 100)
        clean = real.text[10:90].strip()
        corrupted = clean.replace("'", "'").replace('"', '"')
        matched, *_ = sp.verify_quote(corrupted, excerpts)
        assert matched

    def test_fabricated_quote_does_not_match(self, p02_excerpts):
        _, excerpts = p02_excerpts
        matched, eid, src = sp.verify_quote(
            "This exact sentence does not appear anywhere in the packet at all", excerpts)
        assert not matched and eid is None and src is None

    def test_too_short_quote_never_matches_even_if_real_text(self, p02_excerpts):
        section1, excerpts = p02_excerpts
        matched, *_ = sp.verify_quote("xyz", excerpts)
        assert not matched

    def test_short_but_real_phrase_over_the_floor_does_match(self, p02_excerpts):
        # sanity check on the floor itself -- something >=10 chars that IS real text
        # should match; this is what distinguishes "too short" from "not present."
        section1, excerpts = p02_excerpts
        assert "enrich lives" in sp._normalize(section1)
        matched, *_ = sp.verify_quote("enrich lives through technology", excerpts)
        assert matched


@requires_repo_ip
def test_noncompany_support_is_all_false_on_p05():
    # P-05 has ZERO real non-company excerpts (12 company / 0 noncompany / 10 disputed /
    # 1 researcher -- confirmed above). No matter what the model claims, a verified
    # citation can never make this True for P-05 -- that's the point of computing
    # source_tag from the packet rather than trusting the model's self-report.
    section1 = sp.load_packet_section1(sp.packet_path_for("P-05"))
    excerpts = sp.parse_excerpts(section1)
    company_ex = next(e for e in excerpts if e.source_tag == "company")
    disputed_ex = next(e for e in excerpts if e.source_tag == "disputed")
    result = sp.ScorerResult(
        packet_id="P-05", model=sp.MODEL, rubric_version="v1-frozen-2026-08-15",
        packet_version="v4.6", temperature_honored=True, reasoning_effort="medium",
        timestamp="2026-01-01T00:00:00Z",
        dimensions=[
            sp.DimensionScore("autonomy", 0.7, 0.6, [company_ex.text[10:60].strip()]),
            sp.DimensionScore("innovation", 0.3, 0.3, [disputed_ex.text[10:60].strip()]),
            *[sp.DimensionScore(d, 0.5, 0.6, ["nonexistent quote text here"])
              for d in ["pace", "collaboration", "feedback", "decision"]],
        ],
    )
    support = sp.noncompany_support(result, section1)
    assert not any(support.values())


# ---------------------------------------------------------------------------
# S1-1: RESPONSE_SCHEMA shape
# ---------------------------------------------------------------------------
def test_response_schema_is_valid_json_schema():
    import jsonschema
    jsonschema.Draft7Validator.check_schema(sp.RESPONSE_SCHEMA)


def test_response_schema_rejects_missing_evidence_quotes():
    import jsonschema
    bad = {dim: {"score": 0.7, "confidence": 0.6} for dim in sp.DIMENSIONS}  # no evidence_quotes
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, sp.RESPONSE_SCHEMA)


def test_response_schema_rejects_out_of_band_score():
    import jsonschema
    bad = {dim: {"score": 0.75, "confidence": 0.6, "evidence_quotes": ["x" * 20]} for dim in sp.DIMENSIONS}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, sp.RESPONSE_SCHEMA)


def test_response_schema_accepts_valid_payload():
    import jsonschema
    good = {dim: {"score": 0.7, "confidence": 0.6, "evidence_quotes": ["a real quote here, long enough"]}
            for dim in sp.DIMENSIONS}
    jsonschema.validate(good, sp.RESPONSE_SCHEMA)  # no exception = pass


# ---------------------------------------------------------------------------
# S1-2: score_packet() -- mocked OpenAI client (the external service, per this
# project's testing convention: mock external services, not internal logic).
# ---------------------------------------------------------------------------
@requires_repo_ip
def test_score_packet_builds_correct_result_from_mocked_response():
    section1 = sp.load_packet_section1(sp.packet_path_for("P-01"))
    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message.content = json.dumps({
        dim: {"score": 0.7, "confidence": 0.6, "evidence_quotes": ["a sufficiently long fake quote here"]}
        for dim in sp.DIMENSIONS
    })
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    result = sp.score_packet(fake_client, section1, "FAKE RUBRIC", packet_id="P-01",
                              rubric_version="v1-frozen-2026-08-15", packet_version="v4.6")

    assert result.packet_id == "P-01"
    assert result.temperature_honored is True
    assert len(result.dimensions) == 6
    assert {d.dimension for d in result.dimensions} == set(sp.DIMENSIONS)
    assert all(d.score == 0.7 and d.confidence == 0.6 for d in result.dimensions)
    fake_client.chat.completions.create.assert_called_once()


def test_score_packet_serializes_via_to_dict():
    result = sp.ScorerResult(
        packet_id="P-01", model=sp.MODEL, rubric_version="v1", packet_version="v4.6",
        temperature_honored=True, reasoning_effort="medium", timestamp="2026-01-01T00:00:00Z",
        dimensions=[sp.DimensionScore("autonomy", 0.7, 0.6, ["quote"])],
    )
    d = result.to_dict()
    assert d["packet_id"] == "P-01"
    assert d["dimensions"][0] == {"dimension": "autonomy", "score": 0.7, "confidence": 0.6, "evidence_quotes": ["quote"]}
    json.dumps(d)  # must be JSON-serializable, no exception = pass


# ---------------------------------------------------------------------------
# S1-2: call_with_retry() parameter-rejection fallback -- this exact path fired for
# real during the S1-4 gpt-4o run (reasoning_effort was rejected 5/5 times), so it's
# not a hypothetical edge case; testing it against a mocked BadRequestError proves the
# fallback logic that was actually exercised live, rather than trusting the live run
# alone (a live run passing doesn't prove the fallback branch is correct, only that it
# didn't crash).
# ---------------------------------------------------------------------------
def test_call_with_retry_falls_back_when_reasoning_effort_rejected():
    from openai import BadRequestError

    fake_error_response = MagicMock()
    fake_error_response.status_code = 400
    reasoning_error = BadRequestError(
        "Unrecognized request argument supplied: reasoning_effort",
        response=fake_error_response, body=None,
    )

    good_response = MagicMock()
    good_response.choices = [MagicMock()]
    good_response.choices[0].message.content = json.dumps({
        dim: {"score": 0.7, "confidence": 0.6, "evidence_quotes": ["quote long enough to pass"]}
        for dim in sp.DIMENSIONS
    })

    client = MagicMock()
    client.chat.completions.create.side_effect = [reasoning_error, good_response]

    response, temperature_honored = sp.call_with_retry(
        client, [{"role": "user", "content": "x"}], "gpt-4o-2024-08-06", 1.0, "medium")

    assert response is good_response
    assert temperature_honored is True  # only reasoning_effort was rejected, not temperature
    assert client.chat.completions.create.call_count == 2
    second_call_kwargs = client.chat.completions.create.call_args_list[1].kwargs
    assert "reasoning_effort" not in second_call_kwargs
    assert second_call_kwargs.get("temperature") == 1.0


# ---------------------------------------------------------------------------
# S1-6: DDL proposal is at least syntactically parseable
# ---------------------------------------------------------------------------
def test_scorer_run_ddl_parses_without_syntax_errors():
    sqlparse = pytest.importorskip("sqlparse")
    ddl_path = Path(__file__).parent / "v1_model" / "scorer_run_ddl_PROPOSED.sql"
    assert ddl_path.exists()
    sql = ddl_path.read_text(encoding="utf-8")
    statements = [s for s in sqlparse.split(sql) if s.strip()]
    types = [sqlparse.parse(s)[0].get_type() for s in statements]
    assert "CREATE" in types and "ALTER" in types


# ---------------------------------------------------------------------------
# S1-7: end-to-end dry run on P-01, against the REAL API. Skipped unless
# OPENAI_API_KEY is set -- this is the one test in the suite that costs money and
# needs live network access, so it's opt-in via -m live, not run by default.
# ---------------------------------------------------------------------------
@pytest.mark.live
@requires_repo_ip
def test_end_to_end_dry_run_on_p01():
    import os
    from openai import OpenAI
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set -- run with a real key to execute the live dry run")

    client = OpenAI(api_key=api_key)
    anchors = sp.load_anchors()
    rubric = sp.build_rubric_text(anchors)
    packet_path = sp.packet_path_for("P-01")
    section1 = sp.load_packet_section1(packet_path)

    result = sp.score_packet(
        client, section1, rubric, packet_id="P-01",
        rubric_version=anchors["rubric_version"], packet_version=sp.packet_version_for(packet_path),
    )

    assert len(result.dimensions) == 6
    for d in result.dimensions:
        assert d.score in sp.SCORE_BAND_VALUES
        assert d.confidence in sp.CONFIDENCE_BAND_VALUES
        assert 1 <= len(d.evidence_quotes) <= 3

    checks = sp.verify_result(result, section1)
    matched = sum(1 for c in checks if c.matched)
    print(f"\nDry run: {matched}/{len(checks)} evidence_quotes verified against the packet.")
    for c in checks:
        status = "OK " if c.matched else "MISS"
        print(f"  [{status}] {c.dimension}: {c.quote[:70]!r} (eid={c.matched_eid}, src={c.source_tag})")
    # A real end-to-end assertion, not just "it ran": the majority of citations should
    # verify. Anything less is itself the finding S1-5 exists to catch -- record it,
    # don't hide behind a soft pass.
    assert matched / len(checks) >= 0.5, (
        f"only {matched}/{len(checks)} quotes verified -- citation quality problem, "
        f"not a test infrastructure problem"
    )
