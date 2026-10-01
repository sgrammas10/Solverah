"""
test_round2_analysis.py -- the round-2 finish line on SYNTHETIC data only.

Every case here is built so its answer is known before the code runs: a PASS, a NOT MET, an
INCONCLUSIVE whose point estimate sits exactly on the margin, and the coverage guard catching
an LLM that buys agreement by abstaining. No real round-2 reading exists as this is written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import round2_analysis as r2  # noqa: E402

V, H, S = "v3.1-TEST", "abcdef123456", "0" * 64
DIMS = r2.DIMENSIONS
BOOT = 4000


def _score(b):
    return None if b is None else r2.BANDS[b]


def human(d: Path, pid, rater, bands, *, sha=S, anchors=H, submitted="2026-10-01T10:00:00Z", eids=None):
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for dim, b in zip(DIMS, bands):
        row = {"dimension": dim, "score": _score(b), "confidence": None if b is None else 0.6,
               "quotes": [], "excerpts_cited": (eids or {}).get(dim, [])}
        if b is None:
            row["insufficient_evidence"] = True
        rows.append(row)
    (d / f"{pid}_rater{rater}.json").write_text(json.dumps({
        "packet_id": pid, "rater": rater, "rubric_version": V, "anchors_hash": anchors,
        "packet_sha256": sha, "submitted_at": submitted, "scores": rows}), encoding="utf-8")


def llm(d: Path, pid, draws, *, sha=S, rubric=V, run_at="2026-10-02T10:00:00Z"):
    d.mkdir(parents=True, exist_ok=True)
    for n, bands in enumerate(draws, 1):
        (d / f"{pid}_draw{n}.json").write_text(json.dumps({
            "packet_id": pid, "draw": n, "run_at": run_at, "rubric_version": rubric,
            "anchors_hash": H, "packet_sha256": sha,
            "result": {"dimensions": [{"dimension": dim, "score": _score(b),
                                       "confidence": None if b is None else 0.6,
                                       "evidence_quotes": []} for dim, b in zip(DIMS, bands)]},
            "citations": [{"dimension": "decision", "quote": "q" * 12, "matched": True,
                           "matched_eid": f"B{n}", "source_tag": "noncompany"}]}), encoding="utf-8")


def run(tmp_path, **kw):
    hum = r2.load_humans(sorted((tmp_path / "h").glob("*.json")))
    ll = r2.load_llm(sorted((tmp_path / "l").glob("*.json")))
    return r2.analyse(hum, ll, expected_rubric=V, expected_hash=H, n_boot=BOOT, **kw)


def packets(n):
    return [f"P-{i:02d}" for i in range(7, 7 + n)]


# --- the LLM's cell value --------------------------------------------------------------------

@pytest.mark.parametrize("draws, expected", [
    ([1, 2, 3], 2), ([3, 3, 1], 3), ([None, 1, 3], 1), ([None, None, 2], None),
    ([None, None, None], None), ([0, 0, 4], 0),
])
def test_combine_draws(draws, expected):
    assert r2.combine_draws(draws) == expected


def test_combine_draws_requires_three():
    with pytest.raises(ValueError):
        r2.combine_draws([1, 2])


# --- the gates -------------------------------------------------------------------------------

@pytest.mark.parametrize("kind, needle", [
    ("sha", "packet_sha256 differs"),
    ("order", "ran before D submitted"),
    ("draws", "2 LLM draws"),
    ("rubric", "rubric_version"),
    ("anchors", "anchors_hash"),
])
def test_each_gate_makes_a_packet_not_comparable(tmp_path, kind, needle):
    human(tmp_path / "h", "P-07", "D", [2] * 6, anchors="zzz" if kind == "anchors" else H)
    draws = [[2] * 6] * (2 if kind == "draws" else 3)
    llm(tmp_path / "l", "P-07", draws, sha="1" * 64 if kind == "sha" else S,
        rubric="v1" if kind == "rubric" else V,
        run_at="2026-09-30T10:00:00Z" if kind == "order" else "2026-10-02T10:00:00Z")
    rep = run(tmp_path)
    assert rep["comparable_packets"] == []
    assert any(needle in r for r in rep["not_comparable"]["P-07"])
    assert rep["finish_line"]["verdict"] == "NO DATA"


def test_overlap_on_a_different_packet_file_is_not_a_ceiling(tmp_path):
    human(tmp_path / "h", "P-10", "D", [2] * 6)
    human(tmp_path / "h", "P-10", "A", [2] * 6, sha="9" * 64)
    llm(tmp_path / "l", "P-10", [[2] * 6] * 3)
    rep = run(tmp_path)
    assert rep["overlap_packets"] == [] and "P-10" in rep["overlap_not_comparable"]
    assert rep["finish_line"]["verdict"] == "NO CEILING"


# --- the verdicts ----------------------------------------------------------------------------

def _design(tmp_path, llm_bands_for, a_bands_for, d_bands_for=lambda p: [2] * 6, n=6, overlap=2):
    for p in packets(n):
        human(tmp_path / "h", p, "D", d_bands_for(p))
        llm(tmp_path / "l", p, [llm_bands_for(p)] * 3)
    for p in packets(n)[:overlap]:
        human(tmp_path / "h", p, "A", a_bands_for(p))


def test_pass_when_the_llm_matches_the_reference_better_than_the_humans_match(tmp_path):
    _design(tmp_path, llm_bands_for=lambda p: [2] * 6, a_bands_for=lambda p: [3] * 6)
    fl = run(tmp_path)["finish_line"]
    assert (fl["D_llm"], fl["D_ceiling"]) == (0.0, 1.0)
    assert fl["verdict"] == "PASS" and fl["ci_high"] < r2.MARGIN


def test_not_met_when_the_llm_is_far_worse(tmp_path):
    _design(tmp_path, llm_bands_for=lambda p: [0] * 6, d_bands_for=lambda p: [3] * 6,
            a_bands_for=lambda p: [3] * 6)
    fl = run(tmp_path)["finish_line"]
    assert fl["D_llm"] == 3.0 and fl["D_ceiling"] == 0.0
    assert fl["verdict"] == "NOT MET" and fl["ci_low"] > r2.MARGIN


def test_inconclusive_when_the_estimate_sits_on_the_margin(tmp_path):
    # LLM: three packets exact, three packets 1.5 bands off (1,2 alternating) -> 0.75.
    # Ceiling: one overlap packet exact, one 1 band off -> 0.5. Difference = +0.25 exactly.
    off = [3, 4, 3, 4, 3, 4]
    _design(tmp_path,
            llm_bands_for=lambda p: [2] * 6 if p in packets(6)[:3] else off,
            a_bands_for=lambda p: [2] * 6 if p == "P-07" else [3] * 6)
    fl = run(tmp_path)["finish_line"]
    assert fl["diff"] == pytest.approx(0.25)
    assert fl["ci_low"] < r2.MARGIN < fl["ci_high"]
    assert fl["verdict"] == "INCONCLUSIVE"


def test_coverage_guard_catches_an_llm_that_abstains_its_way_to_agreement(tmp_path):
    # Perfect agreement where it scores, but it abstains on feedback everywhere: 1/6 of cells,
    # 16.7 points below the reference's full coverage.
    _design(tmp_path, llm_bands_for=lambda p: [2, 2, 2, None, 2, 2], a_bands_for=lambda p: [3] * 6)
    fl = run(tmp_path)["finish_line"]
    assert fl["D_llm"] == 0.0
    assert not fl["coverage_guard_ok"]
    assert fl["verdict"] == "NOT MET" and "coverage" in fl["reason"]


def test_reference_skips_do_not_count_against_the_llm(tmp_path):
    _design(tmp_path, llm_bands_for=lambda p: [2, 2, 2, None, 2, 2],
            d_bands_for=lambda p: [2, 2, 2, None, 2, 2], a_bands_for=lambda p: [3, 3, 3, None, 3, 3])
    rep = run(tmp_path)
    assert rep["finish_line"]["coverage_guard_ok"]
    assert rep["skips"]["table"]["both_skip"] == 6
    assert rep["finish_line"]["n_cells_llm"] == 30


def test_bootstrap_is_deterministic_under_the_seed(tmp_path):
    off = [3, 4, 3, 4, 3, 4]
    _design(tmp_path, llm_bands_for=lambda p: [2] * 6 if p in packets(6)[:3] else off,
            a_bands_for=lambda p: [2] * 6 if p == "P-07" else [3] * 6)
    a, b = run(tmp_path)["finish_line"], run(tmp_path)["finish_line"]
    assert (a["ci_low"], a["ci_high"]) == (b["ci_low"], b["ci_high"])
    c = run(tmp_path, seed=1)["finish_line"]
    assert (c["ci_low"], c["ci_high"]) != (a["ci_low"], a["ci_high"])


# --- secondary checks ------------------------------------------------------------------------

def test_floor_bias_persists_when_the_llm_never_follows_the_reference_down(tmp_path):
    _design(tmp_path, n=3, overlap=1, llm_bands_for=lambda p: [1] * 6,
            d_bands_for=lambda p: [0, 2, 2, 2, 2, 2], a_bands_for=lambda p: [0] * 6)
    fb = run(tmp_path)["floor_bias"]
    assert fb["reference_floor_cells"] == 3 and fb["llm_floor_uses_all_draws"] == 0
    assert fb["reading"] == "floor bias persists"


def test_floor_bias_reduced_when_the_llm_follows_half_or_more(tmp_path):
    _design(tmp_path, n=3, overlap=1,
            llm_bands_for=lambda p: [0] * 6 if p != "P-09" else [1] * 6,
            d_bands_for=lambda p: [0, 2, 2, 2, 2, 2], a_bands_for=lambda p: [0] * 6)
    assert run(tmp_path)["floor_bias"]["reading"] == "floor bias reduced"


def test_review_cells_carry_both_sides_citations(tmp_path):
    human(tmp_path / "h", "P-07", "D", [2, 2, 2, 2, 2, 4], eids={"decision": ["C3"]})
    llm(tmp_path / "l", "P-07", [[2, 2, 2, 2, 2, 1]] * 3)
    (cell,) = run(tmp_path)["review_cells_for_equivalence_gate_3"]
    assert (cell["dimension"], cell["llm_band"], cell["reference_band"]) == ("decision", 1, 4)
    assert cell["reference_eids"] == ["C3"] and cell["llm_eids_by_draw"] == [["B1"], ["B2"], ["B3"]]


def test_expectation_leak_flags_a_reference_that_tracks_the_selection_prior(tmp_path):
    _design(tmp_path, llm_bands_for=lambda p: [2] * 6, d_bands_for=lambda p: [4] * 6,
            a_bands_for=lambda p: [2] * 6)
    poles = {p: {d: "high" for d in DIMS} for p in packets(6)}
    leak = run(tmp_path, expected_poles=poles)["expectation_leak"]
    assert leak["shares"]["D"]["share"] == 1.0 and leak["shares"]["A"]["share"] == 0.0
    assert leak["reading"] == "reference may carry selection priors"


def _readings(tmp_path, d_pids, a_pids):
    for p in d_pids:
        human(tmp_path / "h", p, "D", [2] * 6)
    for p in a_pids:
        human(tmp_path / "h", p, "A", [2] * 6)
    return r2.load_humans(sorted((tmp_path / "h").glob("*.json")))


def test_julie_stopping_early_in_order_is_a_random_prefix(tmp_path):
    # JULIE_ORDER opens P-11, P-10, P-19, P-09. P-19 was never read by anyone (say it failed
    # the scrub), so it is not a gap she skipped.
    check = r2.overlap_order_check(_readings(tmp_path, ["P-11", "P-10", "P-09", "P-08"],
                                             ["P-11", "P-10", "P-09"]))
    assert check["order"][:4] == ["P-11", "P-10", "P-09", "P-08"]
    assert check["completed"] == ["P-11", "P-10", "P-09"]
    assert check["is_prefix"] and check["reading"] == "random prefix of the pre-registered order"


def test_julie_skipping_ahead_is_reported_as_self_selected(tmp_path):
    check = r2.overlap_order_check(_readings(tmp_path, ["P-11", "P-10", "P-09"], ["P-11", "P-09"]))
    assert not check["is_prefix"]
    assert check["out_of_order"] == ["P-09"]
    assert check["reading"].startswith("partly self-selected")


def test_the_rater_pages_real_payload_loads():
    """Seam: the jsdom-captured v3.1 page payload parses as a HumanReading, skip included."""
    fx = HERE.parent / "ground_truth" / "rater_app" / "fixtures" / "v31_page_payload.json"
    (reading,) = r2.load_humans([fx]).values()
    assert reading.bands["decision"] is None
    assert sum(b is not None for b in reading.bands.values()) == 5
