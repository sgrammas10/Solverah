"""Tests for match_scoring.py + match_core.py -- the PyMC-free serving path.

Three contracts under test:

1. THE WEIGHT ROUND-TRIP. priors.yaml -> nested weights -> flat (name, mean, sd) rows ->
   database -> nested weights must be lossless, because the flat naming convention is the
   interface a future fitted posterior will be exported through. Strictness is part of the
   contract: missing rows and unrecognized rows both refuse (D-07).

2. THE SCORES THEMSELVES. Analytic anchor points (perfect match at neutral priors = 0.5
   exactly), the pole-snap correction (a 1.0-pole person against the best achievable 0.9
   env scores IDENTICALLY to a perfectly matched mid person), monotonicity in |gap|, and
   determinism under a fixed seed.

3. ONE LINEAR PREDICTOR. build_model.py must import the core from match_core, not keep
   its own copy -- asserted structurally (AST) because the PyMC path cannot run in this
   suite, and a drifted duplicate would fail silently everywhere else.

DB tests seed person scores via persist_submission and read via get_dimension_scores, so
this file stays off the test_employer_visibility.py allowlist by construction.
"""

import ast
from pathlib import Path

import numpy as np
import pytest

import match_scoring  # noqa: F401  -- installs causal_graph/v1_model on sys.path, making
                      # `from match_core import ...` valid regardless of test order

REPO_ROOT = Path(__file__).resolve().parents[1]

DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]

# stage_size=3.0 and comp=3.0 standardize to exactly 0 under the config's fixed scales,
# and every confounder weight's prior mean is 0 -- so with these values the confounder
# terms vanish at point weights and the analytic anchors below are exact.
NEUTRAL_CONF = {"stage_size": [3.0], "comp": [3.0], "industry": ["tech"]}


def _cfg_pri():
    from match_scoring import load

    return load()


# ---------------------------------------------------------------------------
# 1. Weight round-trip + persistence
# ---------------------------------------------------------------------------

def test_flatten_unflatten_roundtrip():
    from match_core import flatten_weights, unflatten_weights, weights_from_priors

    cfg, pri = _cfg_pri()
    nested = weights_from_priors(cfg, pri)
    rows = flatten_weights(cfg, nested)

    # 1 intercept + 6 dims x 2 feats + stage_size + comp + 5 industry levels = 20
    assert len(rows) == 20
    assert len({name for name, _, _ in rows}) == 20  # names are unique

    back = unflatten_weights(cfg, {name: (m, s) for name, m, s in rows})
    assert back["intercept"] == nested["intercept"]
    for d in DIMS:
        assert back["dimensions"][d] == nested["dimensions"][d]
    for k in ("stage_size", "comp"):
        assert back["confounders"][k] == nested["confounders"][k]
    np.testing.assert_array_equal(
        back["confounders"]["industry"]["mean"], nested["confounders"]["industry"]["mean"]
    )


def test_unflatten_refuses_missing_and_unexpected_weights():
    from match_core import flatten_weights, unflatten_weights, weights_from_priors

    cfg, pri = _cfg_pri()
    rows = {n: (m, s) for n, m, s in flatten_weights(cfg, weights_from_priors(cfg, pri))}

    missing = dict(rows)
    del missing["pace_mag"]
    with pytest.raises(ValueError):
        unflatten_weights(cfg, missing)

    extra = dict(rows)
    extra["w_prestige"] = (0.0, 1.0)  # a weight for an inactive confounder
    with pytest.raises(ValueError):
        unflatten_weights(cfg, extra)


def test_seed_is_idempotent_and_loads_back_exactly(client):
    from app import app
    from match_core import flatten_weights, weights_from_priors
    from match_scoring import load_run_weights, seed_priors_model_run
    from model import db, WeightPosterior

    with app.app_context():
        run1 = seed_priors_model_run(db)
        db.session.commit()
        run2 = seed_priors_model_run(db)  # same priors -> same run, no duplicate
        db.session.commit()
        assert run1.id == run2.id
        assert WeightPosterior.query.count() == 20

        cfg, pri = _cfg_pri()
        run, weights = load_run_weights(db)
        assert run.id == run1.id
        assert run.n_rows == 0  # prior-only run says it trained on nothing
        expected = {n: (m, s) for n, m, s in flatten_weights(cfg, weights_from_priors(cfg, pri))}
        got = {n: (m, s) for n, m, s in flatten_weights(cfg, weights)}
        assert got == expected


def test_unseeded_database_refuses_to_serve(client):
    from app import app
    from match_scoring import MatchModelError, current_run
    from model import db  # noqa: F401  (fixture creates the empty schema)

    with app.app_context():
        with pytest.raises(MatchModelError):
            current_run(db)


def test_corrupt_weight_rows_refuse_to_serve(client):
    from app import app
    from match_scoring import MatchModelError, load_run_weights, seed_priors_model_run
    from model import db, WeightPosterior

    with app.app_context():
        run = seed_priors_model_run(db)
        db.session.flush()

        # A weight the config does not define: fitted under a different set -> refuse.
        db.session.add(
            WeightPosterior(model_run_id=run.id, weight_name="w_prestige", mean=0.0, sd=1.0)
        )
        db.session.flush()
        with pytest.raises(MatchModelError):
            load_run_weights(db)
        db.session.rollback()

        # A required weight missing -> refuse rather than serve partially weighted.
        seed_priors_model_run(db)
        db.session.flush()
        WeightPosterior.query.filter_by(weight_name="intercept").delete()
        db.session.flush()
        with pytest.raises(MatchModelError):
            load_run_weights(db)
        db.session.rollback()


# ---------------------------------------------------------------------------
# 2. The scores
# ---------------------------------------------------------------------------

def test_perfect_match_at_neutral_priors_is_exactly_half():
    from match_core import point_p_fit, weights_from_priors

    cfg, pri = _cfg_pri()
    w = weights_from_priors(cfg, pri)
    person = {d: [0.5] for d in DIMS}
    env = {d: [0.5] for d in DIMS}
    p = point_p_fit(person, env, NEUTRAL_CONF, cfg, w)
    assert p.shape == (1,)
    assert p[0] == 0.5  # z is exactly 0: gap 0 everywhere, confounder terms exactly 0


def test_pole_candidate_scores_identically_to_perfect_mid_match():
    """The Finding-1 regression, on the serving path: person=1.0 vs env=0.9 (the best any
    env can offer) must price EXACTLY like person=0.5 vs env=0.5 -- same gaps after the
    snap, same seed, same weight draws, bitwise-identical output."""
    from match_core import score_pairs, weights_from_priors

    cfg, pri = _cfg_pri()
    w = weights_from_priors(cfg, pri)
    pole = score_pairs({d: [1.0] for d in DIMS}, {d: [0.9] for d in DIMS},
                       NEUTRAL_CONF, cfg, w, draws=200, seed=7)
    mid = score_pairs({d: [0.5] for d in DIMS}, {d: [0.5] for d in DIMS},
                      NEUTRAL_CONF, cfg, w, draws=200, seed=7)
    for key in ("p_fit", "p_fit_low", "p_fit_high"):
        np.testing.assert_array_equal(pole[key], mid[key])


def test_p_fit_decreases_as_gap_grows():
    from match_core import point_p_fit, weights_from_priors

    cfg, pri = _cfg_pri()
    w = weights_from_priors(cfg, pri)
    conf = {"stage_size": [3.0] * 3, "comp": [3.0] * 3, "industry": ["tech"] * 3}
    person = {d: [0.5, 0.5, 1.0] for d in DIMS}
    env = {d: [0.5, 0.9, 0.1] for d in DIMS}  # |gap| = 0, 0.4, 0.8 after the snap
    p = point_p_fit(person, env, conf, cfg, w)
    assert p[0] > p[1] > p[2]


def test_band_is_ordered_deterministic_and_widens_nothing_silently():
    from match_core import score_pairs, weights_from_priors

    cfg, pri = _cfg_pri()
    w = weights_from_priors(cfg, pri)
    person = {d: [0.5] for d in DIMS}
    env = {d: [0.7] for d in DIMS}

    a = score_pairs(person, env, NEUTRAL_CONF, cfg, w, draws=300, seed=1)
    b = score_pairs(person, env, NEUTRAL_CONF, cfg, w, draws=300, seed=1)
    for key in ("p_fit", "p_fit_low", "p_fit_high"):
        np.testing.assert_array_equal(a[key], b[key])  # same seed, same numbers

    assert a["p_fit_low"][0] < a["p_fit"][0] < a["p_fit_high"][0]
    assert 0.0 <= a["p_fit_low"][0] and a["p_fit_high"][0] <= 1.0


def test_missing_inputs_refuse():
    from match_core import score_pairs, weights_from_priors

    cfg, pri = _cfg_pri()
    w = weights_from_priors(cfg, pri)
    person = {d: [0.5] for d in DIMS}
    env = {d: [0.5] for d in DIMS}

    short_person = {d: [0.5] for d in DIMS if d != "feedback"}
    with pytest.raises(ValueError):
        score_pairs(short_person, env, NEUTRAL_CONF, cfg, w, draws=10)

    no_comp = {"stage_size": [3.0], "industry": ["tech"]}
    with pytest.raises(ValueError):
        score_pairs(person, env, no_comp, cfg, w, draws=10)

    bad_level = {"stage_size": [3.0], "comp": [3.0], "industry": ["crypto"]}
    with pytest.raises(ValueError):
        score_pairs(person, env, bad_level, cfg, w, draws=10)


def test_score_with_current_run_end_to_end(client):
    from app import app
    from match_scoring import score_with_current_run, seed_priors_model_run
    from model import db

    with app.app_context():
        seed_priors_model_run(db)
        db.session.commit()
        person = {d: [0.5] for d in DIMS}
        env = {d: [0.5] for d in DIMS}
        run, scores = score_with_current_run(db, person, env, NEUTRAL_CONF, draws=200, seed=3)
        assert run.model_version == "v1-priors-only"
        assert scores["p_fit_low"][0] < scores["p_fit"][0] < scores["p_fit_high"][0]
        # Perfect match under symmetric neutral priors: the band straddles 0.5.
        assert scores["p_fit_low"][0] < 0.5 < scores["p_fit_high"][0]


# ---------------------------------------------------------------------------
# The sanctioned person-side read
# ---------------------------------------------------------------------------

def _fake_submission(scoring_key_version: str):
    from assessment_form import ScoredSubmission

    choices = {f"{d[:2]}{r}v2": "A" for d in DIMS for r in range(1, 5)}
    return ScoredSubmission(
        form_version="v2-2026-08-18",
        scoring_key_version=scoring_key_version,
        scores={d: 0.25 * i for i, d in enumerate(DIMS[:5], 0)} | {"decision": 0.5},
        choices=choices,
    )


def test_get_dimension_scores_none_current_and_stale(client):
    from app import app
    from assessment_form import scoring_key_version
    from assessment_store import get_dimension_scores, persist_submission
    from model import db

    with app.app_context():
        assert get_dimension_scores(99) is None  # no profile: None, never a default

        persist_submission(db, 1, _fake_submission(scoring_key_version()))
        persist_submission(db, 2, _fake_submission("v1-superseded+mean_pole"))
        db.session.commit()

        scores = get_dimension_scores(1)
        assert set(scores) == set(DIMS)
        assert scores["decision"] == 0.5

        # A superseded instrument's scores are not a current profile (same logic as
        # has_completed_assessment): the match must not consume them.
        assert get_dimension_scores(2) is None


# ---------------------------------------------------------------------------
# 3. One linear predictor -- structural guard
# ---------------------------------------------------------------------------

def test_build_model_imports_core_rather_than_redefining_it():
    """build_model.py must not grow its own copy of the deterministic core. The PyMC
    path cannot run in this suite, so parity is enforced structurally: no top-level
    def/assignment of a core name, and an explicit import of each from match_core."""
    CORE_FUNCS = {"closest_achievable", "fit_gap", "preprocess_conf", "outcome_logit",
                  "load", "active"}
    CORE_CONSTS = {"PERSON_LATTICE", "BAND_VALUES", "N_RUNS", "COMPANY_LATTICE"}

    src = (REPO_ROOT / "causal_graph" / "v1_model" / "build_model.py").read_text()
    tree = ast.parse(src)

    top_defs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert not (top_defs & CORE_FUNCS), (
        f"build_model.py redefines {sorted(top_defs & CORE_FUNCS)} -- the ONE "
        f"implementation lives in match_core.py; import it instead"
    )

    top_assigns = set()
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    top_assigns.add(t.id)
    assert not (top_assigns & CORE_CONSTS), (
        f"build_model.py re-declares {sorted(top_assigns & CORE_CONSTS)} -- import from "
        f"match_core.py instead"
    )

    imported = set()
    for n in tree.body:
        if isinstance(n, ast.ImportFrom) and n.module == "match_core":
            imported |= {a.name for a in n.names}
    missing = (CORE_FUNCS | CORE_CONSTS) - imported
    assert not missing, f"build_model.py no longer imports {sorted(missing)} from match_core"
