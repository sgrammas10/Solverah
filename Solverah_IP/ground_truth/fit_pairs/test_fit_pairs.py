"""test_fit_pairs.py -- the fit-pairs design, pages, hook and analysis.

Run (outside pytest.ini's testpaths, like the rest of Solverah_IP):
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest Solverah_IP/ground_truth/fit_pairs -q

No network, no API key, no app import: the gate constants are pinned against the app's
SOURCE TEXT, so a drift in the product fails here without this lane importing app code.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

import build_fit_pages as bfp  # noqa: E402
import design  # noqa: E402
import fit_pairs_analysis as fa  # noqa: E402

SPEC = design.build_spec()
PAIRS = {p["pair_id"]: p for p in SPEC["pairs"]}
TEST_ROSTER = HERE / "fixtures" / "roster_test.json"
ALIGN = REPO / "Solverah_IP" / "match_model_alignment"


# ---------------------------------------------------------------------------
# The design restates the product's gate rules faithfully
# ---------------------------------------------------------------------------

def _src(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel,name,value", [
    ("solverah/domain/trait_preferences.py", "ALIGNED_FLOOR", "0.15"),
    ("solverah/domain/trait_preferences.py", "STEP_SIZE", "0.25"),
    ("solverah/domain/trait_preferences.py", "MAX_STEPS", "2"),
    ("solverah/domain/trait_preferences.py", "MAX_MUST_HAVES", "2"),
    ("solverah/services/company_match_service.py", "MIN_KNOWN_FOR_READ", "3"),
])
def test_gate_constants_match_the_app_source(rel, name, value):
    m = re.search(r"^%s\s*=\s*([0-9.]+)\s*$" % name, _src(rel), re.M)
    assert m, "%s not found in %s" % (name, rel)
    assert m.group(1) == value
    assert str(getattr(design, name)) == value


def test_trait_order_matches_the_app():
    m = re.search(r"TRAIT_KEYS: tuple\[str, \.\.\.\] = \((.*?)\)", _src("solverah/domain/trait_preferences.py"), re.S)
    assert tuple(re.findall(r'"(\w+)"', m.group(1))) == design.TRAIT_KEYS


def test_flat_zone_rule_matches_the_app_source():
    assert "max(ALIGNED_FLOOR, prefs[key].under_steps * STEP_SIZE)" in _src("solverah/domain/trait_preferences.py")


def test_persons_are_valid_product_users():
    for p in SPEC["persons"]:
        assert set(p["scores"]) == set(design.TRAIT_KEYS)
        assert all(v in design.PERSON_LEVELS for v in p["scores"].values())
        for t in p["tolerance"].values():
            assert t["under_steps"] in (0, 1, 2) and t["over_steps"] in (0, 1, 2)
        assert len(p["must_haves"]) <= design.MAX_MUST_HAVES
        assert set(p["must_haves"]) <= set(design.TRAIT_KEYS)


def test_company_values_sit_exactly_on_bands():
    """What the rater reads maps one to one onto what the model scores."""
    for c in SPEC["companies"]:
        assert c["headcount"] is None and c["confounders"] == {}
        for k, rec in c["traits"].items():
            for key in ("estimate", "low_end", "high_end"):
                if key in rec:
                    assert rec[key] in design.COMPANY_BANDS, (c["company_id"], k, key)
            if rec["status"] == "mixed":
                assert rec["low_end"] < rec["high_end"]


# ---------------------------------------------------------------------------
# Every pair is the case it claims to be
# ---------------------------------------------------------------------------

def test_every_case_is_what_it_says():
    for pid, p in PAIRS.items():
        d, case = p["design_check"], p["case"]
        if case == "aligned":
            assert d["known"] == 6 and not d["outside_tolerance"] and not d["gap_inside_tolerance"], pid
        if case.startswith("must_have_break"):
            assert d["must_have_break"] and len(d["outside_tolerance"]) == 1, pid
        if case.startswith("mixed_must_have"):
            assert d["risk_flag"] and not d["must_have_break"], pid
        if case in ("inside_tolerance", "tolerated_direction", "mixed_inside_tolerance"):
            assert not d["outside_tolerance"] and d["rankable"], pid
        if case in ("inside_tolerance", "tolerated_direction"):
            assert d["gap_inside_tolerance"], pid
        if case == "untolerated_direction":
            assert d["outside_tolerance"] == ["autonomy", "pace"], pid
        if case.startswith("unknown"):
            assert d["unknown"] >= 1 and d["rankable"] and not d["outside_tolerance"], pid
        if case == "thin_evidence":
            assert not d["rankable"], pid
        if case.startswith("single_"):
            assert len(d["outside_tolerance"]) == 1 and not d["must_have_break"], pid
        if case.startswith("compound") or case == "two_gap_control":
            assert len(d["outside_tolerance"]) == 2 and not d["must_have_break"] and not d["risk_flag"], pid
    assert [pid for pid, p in PAIRS.items() if not p["design_check"]["rankable"]] == list(design.UNRANKED_EXPECTED)


def test_tolerated_and_untolerated_direction_are_the_same_gaps_mirrored():
    """K6 must compare like with like: same traits, same distance, only the side differs."""
    comp = {c["company_id"]: c for c in SPEC["companies"]}
    a, b = comp["B7-C2"]["traits"], comp["B7-C3"]["traits"]
    p7 = next(p for p in SPEC["persons"] if p["person_id"] == "P7")
    for k in ("autonomy", "pace"):
        s = design.snap(p7["scores"][k])
        assert abs(abs(s - a[k]["estimate"]) - abs(s - b[k]["estimate"])) < 1e-9
        assert (s - a[k]["estimate"]) * (s - b[k]["estimate"]) < 0


def test_compound_and_controls_have_equal_gap_sizes():
    for c in design.CONTRASTS:
        if c["contrast_id"] not in ("K8", "K9", "K10", "K11"):
            continue
        for a, b in zip(c["a"], c["b"]):
            assert PAIRS[a]["block"] == PAIRS[b]["block"]
            pa, pb = PAIRS[a], PAIRS[b]
            person = next(p for p in SPEC["persons"] if p["person_id"] == pa["person_id"])
            comp = {x["company_id"]: x for x in SPEC["companies"]}

            def sizes(pid):
                t = comp[pid]["traits"]
                return sorted(round(abs(design.snap(person["scores"][k]) - t[k]["estimate"]), 9)
                              for k in PAIRS[pid]["design_check"]["outside_tolerance"])
            assert sizes(a) == sizes(b), (a, b)


def test_contrasts_are_well_formed():
    for c in design.CONTRASTS:
        assert len(c["a"]) == len(c["b"]) >= 1
        for a, b in zip(c["a"], c["b"]):
            assert PAIRS[a]["block"] == PAIRS[b]["block"], (c["contrast_id"], a, b)
            da, db = PAIRS[a]["design_check"], PAIRS[b]["design_check"]
            assert da["rankable"] and db["rankable"]
            if c["rule"] == "tie":
                assert not da["outside_tolerance"] and not db["outside_tolerance"]
                assert not da["must_have_break"] and not db["must_have_break"]
            if c["rule"] == "b_last":
                assert db["must_have_break"] and not da["must_have_break"]


def test_every_contrast_has_at_least_one_instance_and_main_ones_replicate():
    by = {c["contrast_id"]: len(c["a"]) for c in design.CONTRASTS}
    assert all(n >= 2 for k, n in by.items() if k in ("K1", "K2", "K3", "K4", "K5", "K8", "K9", "K10", "K11"))


def test_sensitivity_blocks_isolate_pace_size_innovation_size_and_direction():
    """07_SENSITIVITY_RESULTS.md: pace.mag, innovation.mag and innovation.dir move rankings.
    Each K9-K11 pair differs in ONE trait gap of the same size; K11 holds the trait fixed
    and flips only the direction, with `a` always the job-more-inventing side."""
    comp = {c["company_id"]: c for c in SPEC["companies"]}
    persons = {p["person_id"]: p for p in SPEC["persons"]}
    k = {c["contrast_id"]: c for c in design.CONTRASTS}
    for a, b in zip(k["K9"]["a"], k["K9"]["b"]):
        assert PAIRS[a]["design_check"]["outside_tolerance"] == ["autonomy"]
        assert PAIRS[b]["design_check"]["outside_tolerance"] == ["pace"]
    for a, b in zip(k["K10"]["a"], k["K10"]["b"]):
        assert PAIRS[b]["design_check"]["outside_tolerance"] == ["innovation"]
    dirs = set()
    for a, b in zip(k["K11"]["a"], k["K11"]["b"]):
        person = persons[PAIRS[a]["person_id"]]
        s = design.snap(person["scores"]["innovation"])
        ea, eb = comp[a]["traits"]["innovation"]["estimate"], comp[b]["traits"]["innovation"]["estimate"]
        assert ea > s > eb and abs((ea - s) - (s - eb)) < 1e-9
        dirs.add((PAIRS[a]["case"], PAIRS[b]["case"]))
    assert dirs == {("single_innovation_more", "single_innovation_less")}
    # pace error isolated in both directions across the two blocks
    paces = {PAIRS[b]["case"] for b in k["K9"]["b"]}
    assert paces == {"single_pace_faster", "single_pace_steadier"}
    # both sensitivity blocks are inside the 4-block minimum
    order = [b["block_id"] for b in SPEC["blocks"]]
    assert order.index("B9") < fa.MIN_BLOCKS_PER_RATER and order.index("B10") < fa.MIN_BLOCKS_PER_RATER


# ---------------------------------------------------------------------------
# Repeats: the same question, by construction
# ---------------------------------------------------------------------------

def test_repeats_reference_existing_pairs_two_blocks_later():
    order = [b["block_id"] for b in SPEC["blocks"]]
    for r in SPEC["repeats"]:
        orig = PAIRS[r["of_pair"]]
        assert order.index(r["shown_after_block"]) - order.index(orig["block"]) == 2
        assert orig["case"] != "aligned"


def test_repeat_cards_are_byte_identical_for_every_rater():
    for rater in ("Z", "E", "PREVIEW"):
        items = bfp.presentation(SPEC, rater)
        firsts = {x["pair_id"]: x for x in items if not x["is_repeat"]}
        reps = [x for x in items if x["is_repeat"]]
        assert len(reps) == 4
        for r in reps:
            assert r["card"] == firsts[r["pair_id"]]["card"]
            assert r["name"] == firsts[r["pair_id"]]["name"]


def test_presentation_is_fixed_block_order_with_seeded_shuffle():
    a, b = bfp.presentation(SPEC, "E"), bfp.presentation(SPEC, "F")
    assert len(a) == len(SPEC["pairs"]) + len(SPEC["repeats"]) == 54 and [x["part"] for x in a] == sorted(x["part"] for x in a)
    assert sorted(x["item_id"] for x in a) == sorted(x["item_id"] for x in b)
    assert [x["item_id"] for x in a] == [x["item_id"] for x in bfp.presentation(SPEC, "E")]
    assert [x["item_id"] for x in a] != [x["item_id"] for x in b]


# ---------------------------------------------------------------------------
# Page text: paraphrase only, plain, ASCII
# ---------------------------------------------------------------------------

def test_evidence_is_ascii_paraphrase_with_no_quotation_marks():
    for trait, bands in design.EVIDENCE.items():
        assert set(bands) == set(design.COMPANY_BANDS)
        for lines in bands.values():
            assert len(lines) == 3
            for src, text in lines:
                assert src in ("Employee review", "News report")      # independent: ask 3
                assert text.isascii() and '"' not in text


def test_card_never_shows_a_number_or_the_model_verdict():
    for x in bfp.presentation(SPEC, "E"):
        text = re.sub(r"<[^>]+>", " ", x["card"])
        assert not re.search(r"\d\.\d|%", text), text[:200]
        assert "of the 6 traits" in text
        for word in ("must_have_break", "risk", "investigate", "rank", "score"):
            assert word not in text.lower()


# ---------------------------------------------------------------------------
# The hook file and the builder
# ---------------------------------------------------------------------------

def test_pair_specs_on_disk_is_current():
    on_disk = HERE / "pair_specs.json"
    assert on_disk.read_bytes() == design.spec_bytes(SPEC), "run: python design.py"


def test_hook_schema_fields_matching_model_needs():
    assert SPEC["schema"] == "fit_pairs_spec_v1"
    for p in SPEC["pairs"]:
        assert set(p) >= {"pair_id", "block", "person_id", "company_id", "case", "design_check"}
    for c in SPEC["companies"]:
        for rec in c["traits"].values():
            assert rec["status"] in ("known", "mixed", "unknown")
            assert ("estimate" in rec) == (rec["status"] == "known")
            assert ("low_end" in rec and "high_end" in rec) == (rec["status"] == "mixed")


@pytest.mark.parametrize("rater,msg", [("A", "set the weights"), ("Q", "not in"),
                                        ("E", "not eligible")])
def test_builder_refuses_weight_setters_strangers_and_empty_slots(rater, msg):
    with pytest.raises(bfp.RosterError, match=msg):
        bfp.check_rater(rater, TEST_ROSTER)


@pytest.mark.parametrize("roster_path", [TEST_ROSTER, HERE / "roster.json"])
def test_builder_accepts_sebastian_and_refuses_the_rest_of_the_round1_roster(roster_path):
    """Amendment 1 (2026-10-14): the weights are Julie's alone, so D may rate."""
    bfp.check_rater("D", roster_path)
    for rater in ("A",) + (("B", "C", "E", "F") if roster_path.name == "roster.json" else ()):
        with pytest.raises(bfp.RosterError):
            bfp.check_rater(rater, roster_path)


def test_builder_refuses_an_unnamed_slot_even_if_switched_on(tmp_path):
    doc = json.loads((HERE / "roster.json").read_text(encoding="utf-8"))
    for r in doc["raters"]:
        if r["rater_id"] == "E":
            r["eligible"] = True
    p = tmp_path / "roster.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(bfp.RosterError, match="no name"):
        bfp.check_rater("E", p)


def test_real_roster_after_amendment_1():
    roster = fa.load_roster(HERE / "roster.json")
    assert roster["A"]["sets_weights"] and not fa.is_eligible(roster["A"])
    assert fa.is_eligible(roster["D"]) and not roster["D"]["sets_weights"] and fa.knows_design(roster["D"])
    assert [k for k, r in roster.items() if fa.is_eligible(r)] == ["D"]
    for slot in ("E", "F"):          # reserved, never a placeholder name
        assert roster[slot]["name"] is None and not roster[slot]["eligible"]
    assert not any(r.get("sets_weights") for k, r in roster.items() if k != "A")


def test_builder_writes_a_page_for_an_eligible_rater(tmp_path):
    rc = bfp.main(["--rater", "Z", "--roster", str(TEST_ROSTER), "--out", str(tmp_path),
                   "--spec-out", str(tmp_path / "pair_specs.json")])
    assert rc == 0
    html = (tmp_path / "fit_pairs_raterZ.html").read_text(encoding="utf-8")
    assert design.spec_sha256(SPEC) in html and "__DATA__" not in html


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def test_stratified_tau_b_known_values():
    assert fa.stratified_tau_b([[(1, 1), (2, 2), (3, 3)]]) == 1.0
    assert fa.stratified_tau_b([[(1, 3), (2, 2), (3, 1)]]) == -1.0
    # pairs across strata are never compared
    assert fa.stratified_tau_b([[(1, 1), (2, 2)], [(5, 0), (6, 1)]]) == 1.0
    # tau-b with a tie in x: C=2, D=0, untied x=2, untied y=3
    assert abs(fa.stratified_tau_b([[(1, 1), (1, 2), (2, 3)]]) - 2 / (2 * 3) ** 0.5) < 1e-12
    assert fa.stratified_tau_b([[(None, 1), (2, 2)]]) is None


def _model_rows(perturb=None):
    """TEST FIXTURE, not a model ranking: z = minus the number of traits outside
    tolerance, so the gate cross-check passes and ties fall where the rules put them."""
    rows = []
    for p in SPEC["pairs"]:
        d = p["design_check"]
        rows.append({"pair_id": p["pair_id"], "state": "ranked" if d["rankable"] else "not_enough_evidence",
                     "z": -float(len(d["outside_tolerance"])) if d["rankable"] else None,
                     "must_have_break": d["must_have_break"], "risk_flag": d["risk_flag"]})
    if perturb:
        perturb(rows)
    return rows


def _write_model(tmp_path, sha, rows):
    p = tmp_path / "pair_model_scores.json"
    p.write_text(json.dumps({"schema": fa.MODEL_SCHEMA, "spec_sha256": sha, "model": {}, "pairs": rows}))
    return p


def _write_return(d: Path, rater, sha, ratings):
    d.mkdir(exist_ok=True)
    rows = [{"item_id": pid, "pair_id": pid, "is_repeat": False, "position": i, "rating": v,
             "abstain": v is None, "note": ""} for i, (pid, v) in enumerate(ratings.items(), 1)]
    (d / ("%s.json" % rater)).write_text(json.dumps({"instrument": fa.INSTRUMENT, "spec_sha256": sha,
                                                     "rater": rater, "ratings": rows}))


def _agreeing_ratings(model):
    out = {}
    for pid, row in model.items():
        if row["state"] != "ranked":
            out[pid] = None
        elif row["must_have_break"]:
            out[pid] = 1
        else:
            out[pid] = max(1, 5 + int(row["z"]))
    return out


def test_excluded_rater_return_is_refused(tmp_path):
    sha = design.spec_sha256(SPEC)
    _write_return(tmp_path / "ret", "A", sha, {"B1-C1": 5})
    roster = fa.load_roster(TEST_ROSTER)
    with pytest.raises(fa.ExcludedRaterError):
        fa.load_returns(tmp_path / "ret", SPEC, sha, roster)


def test_return_from_another_spec_is_refused(tmp_path):
    _write_return(tmp_path / "ret", "Z", "0" * 64, {"B1-C1": 5})
    with pytest.raises(fa.AnalysisError, match="different pair_specs"):
        fa.load_returns(tmp_path / "ret", SPEC, design.spec_sha256(SPEC), fa.load_roster(TEST_ROSTER))


def test_cross_check_stops_on_a_flag_mismatch(tmp_path):
    sha = design.spec_sha256(SPEC)

    def drop_flag(rows):
        next(r for r in rows if r["pair_id"] == "B1-C2")["must_have_break"] = False
    model = fa.load_model_scores(_write_model(tmp_path, sha, _model_rows(drop_flag)), SPEC, sha)
    rep = fa.analyse(SPEC, sha, model, [])
    assert rep.stage == "0-cross-check" and rep.verdict.startswith("STOP")


def test_agreeing_raters_leave_the_defaults_standing(tmp_path):
    sha = design.spec_sha256(SPEC)
    model = fa.load_model_scores(_write_model(tmp_path, sha, _model_rows()), SPEC, sha)
    ratings = _agreeing_ratings(model)
    for r in ("X", "Y", "Z"):
        _write_return(tmp_path / "ret", r, sha, ratings)
    returns = fa.load_returns(tmp_path / "ret", SPEC, sha, fa.load_roster(TEST_ROSTER))
    rep = fa.analyse(SPEC, sha, model, returns)
    assert rep.verdict.startswith("DEFAULTS STAND"), (rep.verdict, rep.lines)
    assert rep.numbers["consensus_tau"] == pytest.approx(1.0)


def test_raters_who_rate_unknowns_down_fail_k3(tmp_path):
    sha = design.spec_sha256(SPEC)
    model = fa.load_model_scores(_write_model(tmp_path, sha, _model_rows()), SPEC, sha)
    ratings = _agreeing_ratings(model)
    for pid in ("B1-C4", "B7-C4", "B5-C5"):
        ratings[pid] = 3
    for r in ("X", "Y", "Z"):
        _write_return(tmp_path / "ret", r, sha, ratings)
    returns = fa.load_returns(tmp_path / "ret", SPEC, sha, fa.load_roster(TEST_ROSTER))
    rep = fa.analyse(SPEC, sha, model, returns)
    assert "K3" in rep.numbers["contrasts_failed"]
    assert rep.verdict.startswith("EXAMINE")


def test_mostly_abstained_instances_are_not_judged(tmp_path):
    """Prereg section 8: raters who could not judge an unknown-heavy company do not make
    K3 fail -- an abstention is an answer, not a vote against the model."""
    sha = design.spec_sha256(SPEC)
    model = fa.load_model_scores(_write_model(tmp_path, sha, _model_rows()), SPEC, sha)
    ratings = _agreeing_ratings(model)
    ratings["B1-C4"], ratings["B7-C4"], ratings["B5-C5"] = 3, None, 3
    for r in ("X", "Y", "Z"):
        _write_return(tmp_path / "ret", r, sha, ratings)
    rep = fa.analyse(SPEC, sha, model, fa.load_returns(tmp_path / "ret", SPEC, sha, fa.load_roster(TEST_ROSTER)))
    assert "K3" not in rep.numbers["contrasts_failed"]


def _k11_result(tmp_path, side_b9, side_b10):
    """Model ties K11 (innovation.dir = 0, here: z depends only on the count outside)."""
    sha = design.spec_sha256(SPEC)
    model = fa.load_model_scores(_write_model(tmp_path, sha, _model_rows()), SPEC, sha)
    ratings = _agreeing_ratings(model)
    ratings["B9-C3"], ratings["B9-C4"] = (4, 2) if side_b9 == "invent" else (2, 4)
    ratings["B10-C4"], ratings["B10-C3"] = (4, 2) if side_b10 == "invent" else (2, 4)
    for r in ("X", "Y", "Z"):
        _write_return(tmp_path / "ret", r, sha, ratings)
    rep = fa.analyse(SPEC, sha, model, fa.load_returns(tmp_path / "ret", SPEC, sha, fa.load_roster(TEST_ROSTER)))
    return rep.numbers["contrasts_failed"]


def test_k11_fails_when_raters_consistently_prefer_one_innovation_direction(tmp_path):
    assert "K11" in _k11_result(tmp_path, "invent", "invent")


def test_k11_holds_when_raters_break_the_tie_inconsistently(tmp_path):
    assert "K11" not in _k11_result(tmp_path, "invent", "refine")


def test_too_few_raters_is_descriptive_only(tmp_path):
    sha = design.spec_sha256(SPEC)
    model = fa.load_model_scores(_write_model(tmp_path, sha, _model_rows()), SPEC, sha)
    _write_return(tmp_path / "ret", "Z", sha, _agreeing_ratings(model))
    rep = fa.analyse(SPEC, sha, model, fa.load_returns(tmp_path / "ret", SPEC, sha, fa.load_roster(TEST_ROSTER)))
    assert rep.verdict.startswith("DESCRIPTIVE ONLY")


def test_descriptive_only_still_reports_the_numbers(tmp_path):
    """Prereg section 6: "report numbers, decide nothing". Two raters are enough for the
    inter-rater statistic, the consensus and the contrasts; no verdict reads them."""
    sha = design.spec_sha256(SPEC)
    model = fa.load_model_scores(_write_model(tmp_path, sha, _model_rows()), SPEC, sha)
    for r in ("Y", "Z"):
        _write_return(tmp_path / "ret", r, sha, _agreeing_ratings(model))
    rep = fa.analyse(SPEC, sha, model, fa.load_returns(tmp_path / "ret", SPEC, sha, fa.load_roster(TEST_ROSTER)))
    assert rep.code == "DESCRIPTIVE_ONLY"
    d = rep.numbers["descriptive"]
    assert d["inter_rater_tau_mean"] == pytest.approx(1.0) and d["consensus_tau"] == pytest.approx(1.0)
    assert d["contrasts_against_model"] == [] and "inter_rater_tau_mean" not in rep.numbers


# ---------------------------------------------------------------------------
# Amendment 1 (2026-10-14): D rates; every verdict is reported twice
# ---------------------------------------------------------------------------

def _reversed(ratings):
    return {pid: (None if v is None else 6 - v) for pid, v in ratings.items()}


def _twin(tmp_path, by_rater):
    sha = design.spec_sha256(SPEC)
    model = fa.load_model_scores(_write_model(tmp_path, sha, _model_rows()), SPEC, sha)
    for rater, make in by_rater.items():
        _write_return(tmp_path / "ret", rater, sha, make(_agreeing_ratings(model)))
    roster = fa.load_roster(TEST_ROSTER)
    returns = fa.load_returns(tmp_path / "ret", SPEC, sha, roster)
    return fa.analyse_twin(SPEC, sha, model, returns, roster)


def test_sebastian_return_is_accepted_and_julie_is_still_refused(tmp_path):
    sha = design.spec_sha256(SPEC)
    roster = fa.load_roster(TEST_ROSTER)
    _write_return(tmp_path / "ret", "D", sha, {"B1-C1": 5})
    assert [r.rater for r in fa.load_returns(tmp_path / "ret", SPEC, sha, roster)] == ["D"]
    _write_return(tmp_path / "ret", "A", sha, {"B1-C1": 5})
    with pytest.raises(fa.ExcludedRaterError, match="set the weights"):
        fa.load_returns(tmp_path / "ret", SPEC, sha, roster)
    # the real roster refuses A too
    with pytest.raises(fa.ExcludedRaterError):
        fa.load_return(tmp_path / "ret" / "A.json", SPEC, sha, fa.load_roster(HERE / "roster.json"))


def test_twin_runs_excluding_d_and_agrees_when_d_agrees(tmp_path):
    same = lambda r: r  # noqa: E731
    twin = _twin(tmp_path, {"D": same, "X": same, "Y": same, "Z": same})
    assert twin.excluded_ids == ["D"]
    assert twin.all_raters.numbers["raters_counted"] == 4 and twin.excluding.numbers["raters_counted"] == 3
    assert twin.all_raters.code == twin.excluding.code == "DEFAULTS_STAND"
    assert twin.disagreements == [] and twin.governing is twin.excluding


def test_twin_disagreement_is_reported_and_excluding_d_governs(tmp_path):
    """D reads every block backwards: with him the agreement gate fails; without him the
    defaults stand. The excluding-D verdict governs and the disagreement is named, gate first."""
    same = lambda r: r  # noqa: E731
    twin = _twin(tmp_path, {"D": _reversed, "X": same, "Y": same, "Z": same})
    assert twin.all_raters.code == "NO_CONCLUSION_DISAGREE"
    assert twin.governing.code == "DEFAULTS_STAND"
    assert twin.disagreements[0].startswith("agreement gate: all raters fail, excluding D pass")
    assert any(d.startswith("overall verdict") for d in twin.disagreements)


def test_twin_names_a_contrast_that_only_d_fails(tmp_path):
    def d_dislikes_unknowns(r):
        r = dict(r)
        for pid in ("B1-C4", "B7-C4", "B5-C5"):
            r[pid] = 3
        return r
    same = lambda r: r  # noqa: E731
    # D and two of four others mark unknowns down: K3 fails with D (3 of 5 against the model),
    # holds without him (2 of 4 is not a majority)
    twin = _twin(tmp_path, {"D": d_dislikes_unknowns, "W": d_dislikes_unknowns,
                            "X": d_dislikes_unknowns, "Y": same, "Z": same})
    states = {d.split(":")[0] for d in twin.disagreements}
    assert "K3" in states, twin.disagreements
    assert "K3" in twin.all_raters.numbers["contrasts_failed"]
    assert "K3" not in twin.governing.numbers["contrasts_failed"]


def test_d_plus_two_recruits_governs_as_descriptive_only(tmp_path):
    """The consequence the amendment states: D + 2 recruits reach a verdict with D, but the
    excluding-D run has 2 counted raters, so the governing verdict is DESCRIPTIVE ONLY."""
    same = lambda r: r  # noqa: E731
    twin = _twin(tmp_path, {"D": same, "Y": same, "Z": same})
    assert twin.all_raters.code == "DEFAULTS_STAND"
    assert twin.governing.code == "DESCRIPTIVE_ONLY"
    assert twin.governing.numbers["descriptive"]["inter_rater_tau_mean"] == pytest.approx(1.0)
    assert "overall verdict: all raters DEFAULTS_STAND, excluding D DESCRIPTIVE_ONLY" in twin.disagreements


def test_twin_without_a_d_return_is_identical(tmp_path):
    same = lambda r: r  # noqa: E731
    twin = _twin(tmp_path, {"X": same, "Y": same, "Z": same})
    assert twin.excluded_ids == [] and twin.disagreements == []
    assert twin.all_raters.verdict == twin.excluding.verdict


def test_main_prints_both_reports_and_the_governing_verdict(tmp_path, capsys):
    sha = design.spec_sha256(SPEC)
    model_path = _write_model(tmp_path, sha, _model_rows())
    model = fa.load_model_scores(model_path, SPEC, sha)
    for r in ("D", "Y", "Z"):
        _write_return(tmp_path / "ret", r, sha, _agreeing_ratings(model))
    rc = fa.main(["--model", str(model_path), "--roster", str(TEST_ROSTER), "--returns", str(tmp_path / "ret")])
    out = capsys.readouterr().out
    assert rc == 0 and out.isascii()
    assert "== ALL ELIGIBLE RATERS ==" in out and "== EXCLUDING D" in out
    assert "THE TWO DISAGREE" in out and "VERDICT (governing, excluding D): DESCRIPTIVE ONLY" in out


def test_committed_model_scores_still_match_the_committed_spec():
    """pair_specs.json and pair_model_scores.json are unchanged by Amendment 1."""
    sha = fa.sha256_file(HERE / "pair_specs.json")
    assert sha == design.spec_sha256(SPEC)
    rows = fa.load_model_scores(HERE / "pair_model_scores.json", SPEC, sha)
    assert len(rows) == len(SPEC["pairs"])


def test_recruit_note_is_plain_short_and_keeps_raters_blind():
    text = (HERE / "RECRUIT_NOTE.txt").read_text(encoding="utf-8")
    assert text.isascii() and len(text.split()) < 400
    for sym in ("#", "**", "`", "|", "](", "* ", "_", "\n- "):
        assert sym not in text, sym
    low = text.lower()
    for word in ("model", "weight", "hypothes", "prior", "penalt", "tolerance", "must-have", "predict"):
        assert word not in low, word
    for must in ("unpaid", "no right answers", "can't say", "download my answers", ".json",
                 "four parts", "6 to 8 minutes", "about an hour", "save"):
        assert must in low, must


def test_captured_page_payload_loads_through_the_analysis():
    """fixtures/captured_payload_raterZ.json is REAL page output (test_fit_page.cjs). If this
    fails on the sha, the design changed: rebuild the Z page and re-run the jsdom test."""
    path = HERE / "fixtures" / "captured_payload_raterZ.json"
    ret = fa.load_return(path, SPEC, design.spec_sha256(SPEC), fa.load_roster(TEST_ROSTER))
    assert len(ret.ratings) == 54 and len(ret.repeats()) == 4
    assert fa.complete_blocks(SPEC, ret) == 10
    rc = fa.repeat_consistency(ret)
    assert rc["n"] >= 0 and set(rc) == {"n", "exact", "within_1", "max_diff", "flagged"}


# ---------------------------------------------------------------------------
# The Julie ask (08) and its email body
# ---------------------------------------------------------------------------

def test_julie_ask_covers_the_five_provisional_rulings():
    doc = (ALIGN / "08_JULIE_ASKS_AGGREGATION.md").read_text(encoding="utf-8")
    consts = _src("solverah/services/company_research/constants.py")
    for n in range(1, 6):
        assert "awaiting Julie ask %d" % n in consts
        assert re.search(r"^## Question %d\b" % n, doc, re.M), n
    # Question 6 (2026-10-14, from 07): innovation direction, standalone, one-tap
    q6 = doc.split("## Question 6", 1)[1].split("\n---", 1)[0]
    assert "5 in 10" in q6 and "6.5" in q6 and "3.5" in q6
    assert all(("**%s.**" % x) in q6 for x in "ABCD")
    for name in ("MIXED_MIN_SIDE_COUNT", "INDEPENDENT_SOURCE_TYPES",
                 "TIME_SPLIT_KNOWN_MIN_INDEPENDENT_RECENT", "COUNT_CONFIDENCE_PER_ITEM"):
        assert name in doc


def test_email_body_is_plain_text():
    text = (ALIGN / "08_EMAIL_TO_JULIE.txt").read_text(encoding="utf-8")
    assert text.isascii()
    for sym in ("#", "**", "`", "|", "](", "* ", "_"):
        assert sym not in text, sym
    assert text.lstrip().lower().startswith(("hi julie", "julie"))
    assert "thank" in text.lower().split("\n\n")[1]
    assert re.search(r"^6\. Is innovation really direction-neutral\?$", text, re.M)
