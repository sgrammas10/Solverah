"""
match_scoring.py -- the web layer's only doorway to the match model.

The analogue of assessment_form.py for the company side of the instrument: app.py may
import this module and nothing deeper. It serves P(fit) with an uncertainty band from
weights stored in the model_run / weight_posterior tables -- pure numpy, no PyMC.
Training (PyMC, NUTS, real outcome data) stays research-side in
causal_graph/v1_model/build_model.py; the two share ONE linear predictor via match_core.

HOW SERVING WORKS (decided with Sebastian 2026-08-19, S-45 item 6)
------------------------------------------------------------------
A model_run row is a versioned set of weights; weight_posterior holds one (mean, sd) row
per weight under the naming convention documented in match_core. Serving loads the
latest run's weights and computes p_fit / p_fit_low / p_fit_high per (person, company)
pair by Monte Carlo over Normal(mean, sd) weight draws -- milliseconds, deterministic
for a given seed. Run 1 is seeded from priors.yaml ("v1-priors-only"): at launch the
band is a prior-predictive band, honest about the fact that no outcome data exists yet.
When a real fit happens later it writes a NEW model_run + weight rows under the same
names, and this module serves it without changing.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
- It never reads the person-side tables. A user's six dimension scores enter through
  assessment_store.get_dimension_scores() -- the sanctioned doorway (D-01) -- called by
  the app layer, which passes plain dicts in. This module stays off the
  test_employer_visibility.py allowlist by construction.
- It does not assemble company-side inputs from the database. Company dimension scores
  and confounder values barely exist yet (S-10, S-37); when they do, the assembly + the
  match endpoint are their own piece of work (S-45 item 7) with D-01 constraints on what
  the output reveals.
- No OrderedLogistic. Experienced outcomes (working_scale) train through an
  OrderedLogistic likelihood when placement data exists -- locked as D-20, deferred by
  decision; never dichotomize working_scale into the Bernoulli path.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_MODEL_DIR = Path(__file__).resolve().parent / "causal_graph" / "v1_model"
if str(_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(_MODEL_DIR))

from match_core import (  # noqa: E402
    active,
    flatten_weights,
    load,
    point_p_fit,
    score_pairs,
    unflatten_weights,
    weights_from_priors,
)

__all__ = [
    "MatchModelError",
    "PRIORS_MODEL_VERSION",
    "current_run",
    "load",
    "load_run_weights",
    "point_p_fit",
    "score_pairs",
    "score_with_current_run",
    "seed_priors_model_run",
    "weights_from_priors",
]

PRIORS_MODEL_VERSION = "v1-priors-only"


class MatchModelError(RuntimeError):
    """The model cannot be served. Never degrade to a default prediction (D-07)."""


def _priors_version(pri_path: Path | None = None) -> str:
    """Content hash of priors.yaml -- the priors file carries no version field, and a
    hash cannot go stale the way a hand-bumped string can."""
    path = pri_path or (_MODEL_DIR / "priors.yaml")
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def _dimension_set_version(cfg) -> str:
    """Self-describing: the active dimension keys, joined. A run fitted under a
    different active set fails unflatten_weights() loudly, and this column says why."""
    return ",".join(d["key"] for d in active(cfg["dimensions"]))


def seed_priors_model_run(db, cfg=None, pri=None, notes=None):
    """Insert model_run #1 from priors.yaml, one weight_posterior row per weight.

    Idempotent on (model_version, priors_version): re-seeding the same priors returns
    the existing run instead of duplicating it; changed priors seed a NEW run (the hash
    differs), which is the desired audit trail. Does NOT commit -- caller owns the
    transaction, same convention as assessment_store.persist_submission.
    """
    from model import ModelRun, WeightPosterior

    if cfg is None or pri is None:
        cfg, pri = load()
    priors_version = _priors_version()

    existing = ModelRun.query.filter_by(
        model_version=PRIORS_MODEL_VERSION, priors_version=priors_version
    ).first()
    if existing is not None:
        return existing

    run = ModelRun(
        model_version=PRIORS_MODEL_VERSION,
        dimension_set_version=_dimension_set_version(cfg),
        priors_version=priors_version,
        n_rows=0,  # prior-only: trained on nothing, and says so
        notes=notes or (
            "Seeded from priors.yaml -- expert priors, no outcome data. Served bands "
            "are prior-predictive. Superseded by the first real fit_posterior run."
        ),
    )
    db.session.add(run)
    db.session.flush()

    for name, mean, sd in flatten_weights(cfg, weights_from_priors(cfg, pri)):
        db.session.add(
            WeightPosterior(model_run_id=run.id, weight_name=name, mean=mean, sd=sd)
        )
    return run


def current_run(db):
    """The run serving predictions: the most recent model_run. Raises if none exists --
    an unseeded database must fail loudly, not serve an implicit default (D-07)."""
    from model import ModelRun

    run = ModelRun.query.order_by(ModelRun.id.desc()).first()
    if run is None:
        raise MatchModelError(
            "no model_run exists -- seed the priors run (seed_priors_model_run) before "
            "serving predictions; refusing to invent weights (D-07)"
        )
    return run


def load_run_weights(db, run=None, cfg=None):
    """(run, nested weights) for `run` (default: current). Strict: missing or
    unexpected weight rows raise via unflatten_weights (D-07)."""
    from model import WeightPosterior

    if cfg is None:
        cfg, _ = load()
    if run is None:
        run = current_run(db)

    rows = {
        w.weight_name: (w.mean, w.sd)
        for w in WeightPosterior.query.filter_by(model_run_id=run.id).all()
    }
    if not rows:
        raise MatchModelError(
            f"model_run {run.id} ({run.model_version}) has no weight_posterior rows"
        )
    try:
        weights = unflatten_weights(cfg, rows)
    except ValueError as exc:
        raise MatchModelError(
            f"model_run {run.id} ({run.model_version}, dimension_set="
            f"{run.dimension_set_version}) does not match the active config: {exc}"
        ) from exc
    return run, weights


def score_with_current_run(db, person, env, conf_raw, draws=2000, seed=0):
    """P(fit) + band for N pairs under the current run's weights.

    person/env: {dimension_key: array-like length N}; conf_raw: raw confounder values.
    Person scores come from assessment_store.get_dimension_scores() -- this module
    never reads them itself (D-01).

    Returns (run, {"p_fit": ..., "p_fit_low": ..., "p_fit_high": ...}) -- the arrays
    line up with match_recommendation's columns; writing those rows is the match
    surface's job (S-45 item 7), not this module's.
    """
    cfg, _ = load()
    run, weights = load_run_weights(db, cfg=cfg)
    return run, score_pairs(person, env, conf_raw, cfg, weights, draws=draws, seed=seed)
