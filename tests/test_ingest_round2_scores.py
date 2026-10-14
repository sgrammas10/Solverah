"""Round-2 LLM draws into the ground-truth lane DB: the guard, and abstentions kept out of rows.

Scripts/ingest_round2_scores.py. The company score table's score column is NOT NULL and the product
schema is deliberately unchanged (decided 2026-09-29), so an "insufficient evidence" dimension
must never reach a row -- it is recorded in the scorer_run notes, and in full in the draw JSON.
"""

import datetime

import pytest

from Scripts.ingest_round2_scores import UnsafeDatabaseError, assert_lane_database, to_ingest_args

LANE = "postgresql://solverah:solverah@localhost:5433/solverah_gt2"


def _draw(skip_decision=True):
    dims = []
    for d in ("autonomy", "pace", "collaboration", "feedback", "innovation", "decision"):
        if d == "decision" and skip_decision:
            dims.append({"dimension": d, "score": None, "confidence": None, "evidence_quotes": [],
                         "insufficient_evidence": True})
        else:
            dims.append({"dimension": d, "score": 0.7, "confidence": 0.6, "evidence_quotes": ["q"]})
    return {
        "packet_id": "P-09", "draw": 2, "run_at": "2026-10-02T10:00:00+00:00",
        "model": "gpt-5.5-2026-04-23", "reasoning_effort": "medium", "temperature_honored": True,
        "rubric_version": "v3.1-PROPOSED-2026-09-29", "anchors_hash": "3e270b206116",
        "packet_sha256": "0" * 64, "packet_version": "v4.7",
        "result": {"dimensions": dims},
        "citations": [{"dimension": "autonomy", "quote": "a quote that matched", "matched": True,
                       "matched_eid": "B3", "source_tag": "noncompany"},
                      {"dimension": "pace", "quote": "a quote that did not", "matched": False,
                       "matched_eid": None, "source_tag": None}],
    }


@pytest.mark.parametrize("url", [
    None, "",
    "postgresql://u:p@dpg-prod.render.com/solverah",                       # remote host
    "postgresql://solverah:solverah@localhost:5433/solverah",               # not a lane DB
    "postgresql://solverah:solverah@localhost:5433/solverah_gt2?host=prod.example.com",
    "postgresql://localhost:pw@prod.example.com/solverah_gt2",              # creds that look local
])
def test_guard_refuses_anything_but_a_local_lane_database(url):
    with pytest.raises(UnsafeDatabaseError):
        assert_lane_database(url)


def test_guard_accepts_the_lane_database():
    assert assert_lane_database(LANE) == LANE
    assert assert_lane_database(LANE + "?sslmode=disable")


def test_abstentions_never_become_rows_and_are_named_in_the_notes():
    args = to_ingest_args(_draw())
    assert [d["dimension_key"] for d in args["dimensions"]] == [
        "autonomy", "pace", "collaboration", "feedback", "innovation"]
    assert all(d["score"] is not None for d in args["dimensions"])
    assert args["skipped"] == ["decision"]
    assert "insufficient evidence on: decision" in args["run"]["notes"]
    assert args["as_of"] == datetime.date(2026, 10, 2)
    auto = next(d for d in args["dimensions"] if d["dimension_key"] == "autonomy")
    assert auto["citations"] == [{"quote_text": "a quote that matched", "matched": True,
                                  "matched_excerpt_id": "B3", "source_tag": "noncompany"}]


def test_a_draw_with_no_skips_says_nothing_about_them():
    assert "insufficient" not in to_ingest_args(_draw(skip_decision=False))["run"]["notes"]


def test_converted_draw_stores_through_the_real_write_path(client):
    """The seam: to_ingest_args' output is accepted by ingest_extractor_result as-is."""
    from app import app
    from model import Company, db
    import company_score_store

    with app.app_context():
        company = Company(name="Round Two Co", slug="round-two-co", profile_json={})
        db.session.add(company)
        db.session.commit()
        args = to_ingest_args(_draw())
        summary = company_score_store.ingest_extractor_result(
            company_id=company.id, as_of=args["as_of"], run=args["run"],
            dimensions=args["dimensions"], source="scraped", is_ground_truth=True)
        assert summary["scores_created"] == 5
        stored = company_score_store.get_company_scores(company.id, "v3.1-PROPOSED-2026-09-29")
        assert {s["dimension_key"] for s in stored} == {
            "autonomy", "pace", "collaboration", "feedback", "innovation"}
