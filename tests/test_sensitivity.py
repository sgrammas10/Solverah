"""The penalty-weight sensitivity test (causal_graph/v1_model/sensitivity.py), C9 of
the CompanyLens six-trait build (PRODUCT_DECISIONS.md section 2, step (2) of "What
changes the weights, cheapest first").

Four contracts:

1. DETERMINISM. The same seed produces the same people, the same synthetic companies
   and the same numbers, so a results doc can be regenerated and compared.
2. A ZERO NUDGE IS A NO-OP. With nudge=0 every person's top-5 overlap is 5 of 5 (or
   k of k) and every tau is exactly 1, under every profile.
3. THE METRIC SEES WHAT IT SHOULD. A weight that obviously dominates the ranking
   registers as mattering; a weight on a trait where no company differs cannot move
   anything and registers as not mattering.
4. IT RANKS THE WAY PRODUCTION RANKS. The ranking goes through
   company_match_service's own eval / worst-case-z / order functions with the weights
   swapped, and a must-have break still sorts last whatever the weights.

No database, no app context: the service's ranking functions are pure given the
evals, and the person side is built here rather than read through assessment_store.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from causal_graph.v1_model import sensitivity as S
from match_core import load, weights_from_priors

DIMS = list(S.DIMS)


@pytest.fixture(scope="module")
def cfg_weights():
    cfg, pri = load()
    return cfg, weights_from_priors(cfg, pri)


def _flat_weights(cfg, mags, dirs=None, intercept=1.0):
    """A nested weights dict with {mean, sd} leaves from explicit per-dimension means."""
    _, pri = load()
    base = weights_from_priors(cfg, pri)
    for k in DIMS:
        base["dimensions"][k]["mag"]["mean"] = float(mags.get(k, 0.0))
        base["dimensions"][k]["dir"]["mean"] = float((dirs or {}).get(k, 0.0))
    base["intercept"]["mean"] = intercept
    return base


def _known_companies(rows):
    """rows: list of {dim: estimate}; every trait known, confounders missing."""
    return [
        S.Company(id=i + 1, name="C-%02d" % (i + 1),
                  traits={k: ("known", float(row[k])) for k in DIMS},
                  conf={"stage_size": None, "comp": None, "industry": None})
        for i, row in enumerate(rows)
    ]


# ---------------------------------------------------------------------------
# 1. Determinism
# ---------------------------------------------------------------------------

def test_same_seed_same_people_same_companies_same_numbers(cfg_weights):
    cfg, weights = cfg_weights
    people_a, people_b = S.synthetic_people(12, seed=5), S.synthetic_people(12, seed=5)
    assert people_a == people_b
    comp_a, comp_b = S.synthetic_companies(10, seed=5), S.synthetic_companies(10, seed=5)
    assert comp_a == comp_b

    run_a = S.run(comp_a, people_a, cfg, weights)
    run_b = S.run(comp_b, people_b, cfg, weights)
    assert json.dumps(run_a, sort_keys=True) == json.dumps(run_b, sort_keys=True)

    # ... and a different seed is a different population, so the fixed seed is doing
    # the work rather than the generator being constant.
    assert S.synthetic_people(12, seed=6) != people_a


# ---------------------------------------------------------------------------
# 2. A zero nudge is a no-op
# ---------------------------------------------------------------------------

def test_a_zero_nudge_gives_full_overlap_and_tau_one_everywhere(cfg_weights):
    cfg, weights = cfg_weights
    companies = S.synthetic_companies(12, seed=2)
    people = S.synthetic_people(15, seed=2)

    result = S.run(companies, people, cfg, weights, nudge=0.0)

    for name, entry in result["weights"].items():
        assert entry["matters"] is False, name
        for dlabel, nudge in entry["nudges"].items():
            assert nudge["value"] == entry["baseline_mean"], (name, dlabel)
            for profile, stats in nudge["profiles"].items():
                assert stats["n"] == len(people)
                assert stats["tau_min"] == 1.0, (name, dlabel, profile)
                assert stats["tau_mean"] == 1.0
                assert stats["overlap_min"] == S.TOP_K
                assert stats["overlap_mean"] == float(S.TOP_K)
                assert stats["share_flagged"] == 0.0


# ---------------------------------------------------------------------------
# 3. The metric sees what it should
# ---------------------------------------------------------------------------

def test_an_obviously_dominant_weight_registers_as_mattering(cfg_weights):
    """Two live dimensions: pace at -3, autonomy at -1, nothing else. Halving or
    half-again-ing the pace weight changes how a pace gap trades off against an
    autonomy gap, so for many people the order of twelve companies that spread on both
    traits must change."""
    cfg, _ = cfg_weights
    weights = _flat_weights(cfg, {"pace": -3.0, "autonomy": -1.0})
    rng = np.random.default_rng(0)
    rows = [{k: 0.5 for k in DIMS} for _ in range(12)]
    for row in rows:
        row["pace"] = float(rng.choice(S.BAND_VALUES))
        row["autonomy"] = float(rng.choice(S.BAND_VALUES))
    companies = _known_companies(rows)
    people = S.synthetic_people(40, seed=3)

    result = S.run(companies, people, cfg, weights)

    assert result["weights"]["pace.mag"]["matters"] is True
    assert result["weights"]["pace.mag"]["max_share_flagged"] >= S.MATTERS_SHARE


def test_a_weight_on_a_trait_where_no_company_differs_cannot_matter(cfg_weights):
    """Every company sits at 0.5 on collaboration: its term is a per-person constant,
    so any nudge of collaboration.mag or .dir leaves every ordering identical."""
    cfg, weights = cfg_weights
    rng = np.random.default_rng(1)
    rows = []
    for _ in range(10):
        row = {k: float(rng.choice(S.BAND_VALUES)) for k in DIMS}
        row["collaboration"] = 0.5
        rows.append(row)
    companies = _known_companies(rows)
    people = S.synthetic_people(25, seed=4)

    result = S.run(companies, people, cfg, weights)

    for name in ("collaboration.mag", "collaboration.dir"):
        entry = result["weights"][name]
        assert entry["matters"] is False, name
        for nudge in entry["nudges"].values():
            assert nudge["pooled"]["tau_min"] == 1.0
            assert nudge["pooled"]["share_flagged"] == 0.0


def test_a_zero_weight_is_nudged_absolutely_and_labelled(cfg_weights):
    """autonomy.dir and innovation.dir are exactly 0 in the live table (Julie's two
    answers were equal). A relative nudge of 0 would silently test nothing."""
    cfg, weights = cfg_weights
    for dim in ("autonomy", "innovation"):
        assert weights["dimensions"][dim]["dir"]["mean"] == 0.0
        w, value, mode = S.nudged_weights(weights, dim, "dir", +0.5)
        assert mode == "absolute"
        assert value == pytest.approx(0.5 * abs(weights["dimensions"][dim]["mag"]["mean"]))
        assert w["dimensions"][dim]["dir"]["mean"] == value
        assert weights["dimensions"][dim]["dir"]["mean"] == 0.0     # the original is untouched
    w, value, mode = S.nudged_weights(weights, "pace", "mag", -0.5)
    assert mode == "relative"
    assert value == pytest.approx(weights["dimensions"]["pace"]["mag"]["mean"] * 0.5)


def test_kendall_tau_and_top_k_overlap():
    assert S.kendall_tau([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert S.kendall_tau([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert S.kendall_tau([1, 2, 3, 4], [2, 1, 3, 4]) == pytest.approx(4.0 / 6.0)
    assert S.kendall_tau([7], [7]) == 1.0
    with pytest.raises(ValueError):
        S.kendall_tau([1, 2], [1, 3])
    assert S.top_k_overlap([1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, 1], 5) == 4
    assert S.top_k_overlap([1, 2, 3], [3, 2, 1], 5) == 3


# ---------------------------------------------------------------------------
# 4. It ranks the way production ranks
# ---------------------------------------------------------------------------

def test_rank_goes_through_the_service_and_a_must_have_break_sorts_last(cfg_weights, monkeypatch):
    cfg, weights = cfg_weights
    from solverah.services import company_match_service as cms

    calls = []
    original = cms._worst_case_z

    def spy(evals, person, cfg_weights=None):
        calls.append(cfg_weights)
        return original(evals, person, cfg_weights=cfg_weights)

    monkeypatch.setattr(cms, "_worst_case_z", spy)

    # Company 1 is the best fit overall (five traits at the person's pole, pace one
    # band outside a 1-step zone -> a must-have break); companies 2 and 3 are inside
    # the zone on pace and worse fits on the other five.
    companies = _known_companies([
        {"autonomy": 0.9, "pace": 0.5, "collaboration": 0.9, "feedback": 0.9, "innovation": 0.9, "decision": 0.9},
        {"autonomy": 0.5, "pace": 0.9, "collaboration": 0.5, "feedback": 0.5, "innovation": 0.5, "decision": 0.5},
        {"autonomy": 0.3, "pace": 0.9, "collaboration": 0.3, "feedback": 0.3, "innovation": 0.3, "decision": 0.3},
    ])
    person = {k: 1.0 for k in DIMS}

    without = S.rank(companies, person, cfg, weights, steps=1)
    assert without == [1, 2, 3]
    with_break = S.rank(companies, person, cfg, weights, steps=1, must_haves=["pace"])
    assert with_break == [2, 3, 1]
    assert calls and all(c is not None and c[0] is cfg for c in calls)


def test_the_unanswered_profile_has_the_floor_zone_and_no_must_haves():
    cms = S._service()
    person = {"scores": {k: 0.5 for k in DIMS}, "must_haves": ("pace", "feedback")}
    unanswered = S._person_for(cms, person, None)
    assert unanswered.answered is False
    assert unanswered.must_haves == frozenset()
    assert all(z == (S.ALIGNED_FLOOR, S.ALIGNED_FLOOR) for z in unanswered.zones.values())
    typical = S._person_for(cms, person, 1)
    assert typical.must_haves == frozenset({"pace", "feedback"})
    assert all(z == (0.25, 0.25) for z in typical.zones.values())
    wide = S._person_for(cms, person, 2)
    assert all(z == (0.5, 0.5) for z in wide.zones.values())


def test_a_company_below_three_known_traits_has_no_position_to_move(cfg_weights):
    cfg, weights = cfg_weights
    companies = _known_companies([{k: 0.5 for k in DIMS}, {k: 0.7 for k in DIMS}])
    thin = S.Company(id=3, name="thin",
                     traits={"autonomy": ("known", 0.9), "pace": ("known", 0.9),
                             "collaboration": ("mixed", 0.1, 0.9), "feedback": ("unknown",),
                             "innovation": ("unknown",), "decision": ("unknown",)},
                     conf={"stage_size": None, "comp": None, "industry": None})
    ranking = S.rank(companies + [thin], {k: 0.9 for k in DIMS}, cfg, weights)
    assert ranking == [2, 1]


# ---------------------------------------------------------------------------
# The real set loads
# ---------------------------------------------------------------------------

def test_the_real_set_is_the_six_round_1_packets_every_trait_known():
    companies = S.load_real_companies()
    assert [c.name for c in companies] == list(S.PACKETS)
    for c in companies:
        assert c.known_count() == 6
        for k in DIMS:
            status, estimate = c.traits[k]
            assert status == "known"
            assert 0.1 <= estimate <= 0.9
        assert "round-1 raters" in c.source


def test_the_markdown_table_names_every_weight_and_the_threshold(cfg_weights):
    cfg, weights = cfg_weights
    result = S.run(S.synthetic_companies(8, seed=9), S.synthetic_people(6, seed=9), cfg, weights)
    doc = {"meta": {"top_k": S.TOP_K, "overlap_floor": S.OVERLAP_FLOOR, "tau_floor": S.TAU_FLOOR,
                    "matters_share": S.MATTERS_SHARE,
                    "profiles": {p: {} for p in S.PROFILES}},
           "sets": {"synthetic": result}}
    text = S.to_markdown(doc)
    assert text.isascii()
    for dim in DIMS:
        assert "| %s.mag |" % dim in text and "| %s.dir |" % dim in text
    assert ">= 10% of people" in text
