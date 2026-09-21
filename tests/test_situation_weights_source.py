"""SOLVERAH_MODEL_WEIGHTS_SOURCE (PRODUCT_DECISIONS, 2026-09-21).

`situation_report_service._dimension_weights` reads its per-dimension weights
from one of two places, chosen by this setting: `priors.yaml` (default, and
production's only source today) or the latest `model_run` / `weight_posterior`
rows. This file proves the switch actually switches, that "run" mode has no
fallback to priors (D-07), that a typo does not silently read as "priors",
that a new `model_run` reaches the next call with no cache to clear by hand,
and that the setting's effect reaches a real HTTP response in ranked order.

Reuses `test_situation_report_api.py`'s real-form helpers (`tests` has no
`__init__.py`, but `test_path_deep_fit.py` already cross-imports this way) so
sittings and environment reports go through the actual API rather than a
hand-built result dict.
"""

from __future__ import annotations

import pytest
import yaml

from tests.test_situation_report_api import (
    _complete_core,
    _get_report,
    _register_and_login,
    _set_career_status,
    _submit_env_by_dimension,
    _walk,
)

VAR = "SOLVERAH_MODEL_WEIGHTS_SOURCE"

PRIORS_PATH = "causal_graph/v1_model/priors.yaml"


@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


@pytest.fixture(autouse=True)
def _clear_weight_caches():
    """Neither cache may leak between tests: the priors path's `lru_cache` and
    the run path's per-run-id cache are both module-level state."""
    from solverah.services import situation_report_service as svc

    def _reset():
        svc._priors_dimension_weights.cache_clear()
        svc._run_weights_cache["run_id"] = None
        svc._run_weights_cache["weights"] = None

    _reset()
    yield
    _reset()


def _seed_run(db, cfg, overrides, model_version, priors_version, n_rows=1):
    """A fully-formed `model_run` + `weight_posterior` rows, built from the
    live priors with `overrides` ({(dim, feat): value}) applied on top --
    everything else stays at its real elicited value, including `dir`, so
    tests only need to name the numbers they actually care about.

    Not `match_scoring.seed_priors_model_run`: that function is idempotent on
    (model_version, priors_version) against the *live* priors, so a second
    call with the same priors file returns the FIRST run again rather than
    creating a second one -- exactly wrong for a test that needs two distinct
    runs with different weights.
    """
    import match_scoring
    from match_core import active, flatten_weights, weights_from_priors
    from model import ModelRun, WeightPosterior

    _, pri = match_scoring.load()
    weights = weights_from_priors(cfg, pri)
    for (dim, feat), value in overrides.items():
        weights["dimensions"][dim][feat]["mean"] = value

    run = ModelRun(
        model_version=model_version,
        dimension_set_version=",".join(d["key"] for d in active(cfg["dimensions"])),
        priors_version=priors_version,
        n_rows=n_rows,
    )
    db.session.add(run)
    db.session.flush()
    for name, mean, sd in flatten_weights(cfg, weights):
        db.session.add(WeightPosterior(model_run_id=run.id, weight_name=name, mean=mean, sd=sd))
    return run


# ── unset / "priors": today's behavior, unchanged ────────────────────────────


@pytest.mark.parametrize("value", [None, "priors"])
def test_unset_and_priors_match_the_live_priors_yaml(monkeypatch, value):
    from solverah.services.situation_report_service import _dimension_weights
    from work_pulse.situation import DIMENSIONS

    if value is None:
        monkeypatch.delenv(VAR, raising=False)
    else:
        monkeypatch.setenv(VAR, value)

    with open(PRIORS_PATH, encoding="ascii") as handle:
        priors = yaml.safe_load(handle)["dimensions"]

    weights = _dimension_weights()

    assert set(weights) == set(DIMENSIONS)
    for dim in DIMENSIONS:
        assert weights[dim]["mag"] == pytest.approx(priors[dim]["mag"]["mean"]), dim
        assert weights[dim]["dir"] == pytest.approx(priors[dim]["dir"]["mean"]), dim


# ── "run": no fallback ────────────────────────────────────────────────────


def test_run_with_no_model_run_raises_and_never_falls_back_to_priors(client, monkeypatch):
    from app import app
    from match_scoring import MatchModelError
    from solverah.services import situation_report_service as svc

    monkeypatch.setenv(VAR, "run")

    def _priors_must_not_be_called():
        raise AssertionError("priors path was used despite SOLVERAH_MODEL_WEIGHTS_SOURCE=run")

    monkeypatch.setattr(svc, "_priors_dimension_weights", _priors_must_not_be_called)

    with app.app_context():
        with pytest.raises(MatchModelError):
            svc._dimension_weights()


def test_typo_value_raises_valueerror_naming_the_variable(monkeypatch):
    from solverah.services.situation_report_service import _dimension_weights

    monkeypatch.setenv(VAR, "modle_run")  # typo, deliberately not "priors" or "run"

    with pytest.raises(ValueError, match=VAR):
        _dimension_weights()


# ── "run": reflects the database, not the file ───────────────────────────────


def test_run_mode_reflects_an_edited_weight_row_not_the_yaml(client, monkeypatch):
    from app import app
    from match_scoring import seed_priors_model_run
    from model import WeightPosterior, db
    from solverah.services.situation_report_service import _dimension_weights

    monkeypatch.setenv(VAR, "run")

    with app.app_context():
        seed_priors_model_run(db)
        db.session.commit()

        row = WeightPosterior.query.filter_by(weight_name="autonomy_mag").one()
        yaml_mean = row.mean
        row.mean = -9.0
        db.session.commit()

        weights = _dimension_weights()

        assert weights["autonomy"]["mag"] == pytest.approx(-9.0)
        assert weights["autonomy"]["mag"] != pytest.approx(yaml_mean)


def test_run_mode_second_newer_run_reached_with_no_manual_cache_clear(client, monkeypatch):
    from app import app
    from match_scoring import load
    from model import db
    from solverah.services.situation_report_service import _dimension_weights

    monkeypatch.setenv(VAR, "run")
    cfg, _ = load()

    with app.app_context():
        _seed_run(
            db, cfg, {("pace", "mag"): -1.0}, model_version="test-run-1", priors_version="v1"
        )
        db.session.commit()

        first = _dimension_weights()
        assert first["pace"]["mag"] == pytest.approx(-1.0)

        _seed_run(
            db, cfg, {("pace", "mag"): -7.0}, model_version="test-run-2", priors_version="v2"
        )
        db.session.commit()

        second = _dimension_weights()  # no cache_clear() between the two calls
        assert second["pace"]["mag"] == pytest.approx(-7.0)


# ── end to end: the setting's effect reaches a ranked HTTP response ─────────


def test_run_mode_flips_dimension_order_through_the_api(client, monkeypatch):
    """Two equal-sized straining gaps (autonomy, pace); whichever dimension
    the current run weights heavier by |mag| leads the payload -- and a
    second, newer run with the two magnitudes swapped flips that order,
    proving both the weight source AND the per-run-id cache reach a real
    response, not just the service function in isolation.
    """
    from app import app
    from match_scoring import load
    from model import db

    email = "a5_weights_source_flip@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)  # uniform pattern -> 0.5 on all six person scores
    resp = _submit_env_by_dimension(
        client,
        csrf,
        # env 0.9 vs person 0.5 -> |gap| 0.40 on both -- equal-sized straining
        # gaps, so only the weights (not the gap itself) can order them.
        {"autonomy": "high", "pace": "high"},
    )
    assert resp.status_code == 200, resp.get_json()

    monkeypatch.setenv(VAR, "run")
    cfg, _ = load()
    overrides_autonomy_heavy = {
        ("autonomy", "mag"): -5.0, ("autonomy", "dir"): 0.0,
        ("pace", "mag"): -1.0, ("pace", "dir"): 0.0,
    }
    overrides_pace_heavy = {
        ("autonomy", "mag"): -1.0, ("autonomy", "dir"): 0.0,
        ("pace", "mag"): -5.0, ("pace", "dir"): 0.0,
    }

    with app.app_context():
        _seed_run(
            db, cfg, overrides_autonomy_heavy,
            model_version="test-run-flip-1", priors_version="flip-1",
        )
        db.session.commit()

    body = _get_report(client).get_json()
    assert body["state"] == "complete"
    order = [d["dimension"] for d in body["dimensions"]]
    assert order.index("autonomy") < order.index("pace"), order

    for key, _value in _walk(body):
        # `cost_of_staying` is A-6's own guidance-content field name (a `rarely_moves`
        # register key) -- legitimate content, not a D-15 leak of the weighted cost this
        # module computes internally. The existing D-15 test in test_situation_report_api.py
        # checks "person"/"gap"/"magnitude" for the same reason and omits "cost".
        if key == "cost_of_staying":
            continue
        for forbidden in ("gap", "person", "magnitude", "weight", "cost"):
            assert forbidden not in key.lower(), key

    with app.app_context():
        _seed_run(
            db, cfg, overrides_pace_heavy,
            model_version="test-run-flip-2", priors_version="flip-2",
        )
        db.session.commit()

    body = _get_report(client).get_json()
    assert body["state"] == "complete"
    order = [d["dimension"] for d in body["dimensions"]]
    assert order.index("pace") < order.index("autonomy"), order
