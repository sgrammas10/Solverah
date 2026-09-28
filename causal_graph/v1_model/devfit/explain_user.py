"""The only place the match model's numbers are visible. DEV ONLY.

    SOLVERAH_IGNORE_DOTENV=1 APP_ENV=testing \\
    DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah_modeldev \\
    JWT_SECRET_KEY=... SOLVERAH_FORM_TOKEN_SECRET=... \\
    python -m causal_graph.v1_model.devfit.explain_user \\
        --email synth-00007@synthetic.solverah.invalid --source run

WHY THE GUARD IS NOT OPTIONAL HERE
-----------------------------------
This prints, per dimension: the environment score, the sealed person-side score,
the signed gap, the bucket, the direction, the mag and dir weights, the weighted
cost and the rank -- then P(doing well) with its band. Decision D-15 keeps every
one of those magnitudes off every API payload: the Situation Report ships the
bucket WORD and an order, and nothing else. A user is never shown their own
number, and no employer is ever shown anyone's.

So this script is a debugging instrument for a database of invented people, and
the guard is what keeps it one. It refuses anything but a local
`solverah_modeldev*` database, before it opens a connection.

--source priors | run
---------------------
`priors` ranks with the expert's elicited weights; `run` ranks with the latest
fitted `model_run`'s. Running both on one user is how you see whether a fit
actually changed the model's mind -- which, with a planted truth that nearly
swaps autonomy and pace, should show up as those two dimensions trading places.

The ranking weights are converted here rather than imported from the API's
situation-report service: that module is the web layer's, it carries its own
caching and error contract, and a dev script reaching into it would couple this
harness to a file it has no business depending on. The conversion is three
lines, and `work_pulse.situation` owns the actual ordering either way.
"""

from __future__ import annotations

import argparse
import sys

from . import MODEL_DIR, REPO_ROOT  # noqa: F401  -- sys.path side effects
from .guard import add_database_argument, require_database_url

import numpy as np

SOURCES = ("priors", "run")


def dimension_weights(nested):
    """match_core's nested weights -> work_pulse.situation's DimensionWeight map.

    Means only. The sd describes how confident the expert was (or how much the
    data moved her); it orders nothing, and `dimension_cost` takes a point
    weight.
    """
    return {
        dim: {"mag": float(feats["mag"]["mean"]), "dir": float(feats["dir"]["mean"])}
        for dim, feats in nested["dimensions"].items()
    }


def _load_weights(db, source, run_id=None):
    """(label, cfg, nested weights) for the requested source. No fallback either
    way: a missing run is an error, not a silent slide back to the priors (D-07).

    `run_id` names a specific run instead of the current one. Worth having: two
    fits at different `--prior-sd-scale` values both live in the database, and
    "the latest" can only ever show the second. Without this the first fit
    becomes uninspectable the moment the second lands.
    """
    import match_scoring
    from model import ModelRun

    cfg, pri = match_scoring.load()
    if source == "priors":
        return "priors.yaml (elicited)", cfg, match_scoring.weights_from_priors(cfg, pri)

    run = None
    if run_id is not None:
        run = ModelRun.query.get(run_id)
        if run is None:
            raise SystemExit("no model_run with id %d in this database" % run_id)
    run, weights = match_scoring.load_run_weights(db, run=run, cfg=cfg)

    scale = ""
    if run.notes:
        try:
            import json
            scale = "  prior_sd_scale=%s" % json.loads(run.notes)["prior_sd_scale"]
        except (ValueError, KeyError, TypeError):
            scale = ""
    label = "model_run %d (%s, n_rows=%s)%s" % (
        run.id, run.model_version, run.n_rows, scale
    )
    return label, cfg, weights


def _row_for_user(User, email):
    user = User.query.filter(User.email == email).first()
    if user is None:
        raise SystemExit("no user with email %r in this database" % email)
    return user


def explain(url, email, source, draws, seed, run_id=None):
    import os

    os.environ["DATABASE_URL"] = url

    import assessment_store
    import environment_report_store
    import match_scoring
    from app import app
    from model import User, db
    from work_pulse import situation

    with app.app_context():
        user = _row_for_user(User, email)

        env = environment_report_store.latest_environment_report(user.id)
        if env is None:
            raise SystemExit("user %s has no environment report" % email)

        # The pinned sitting, through the sanctioned doorway. Re-derived from the
        # sitting's own stored answers rather than read from the current-score
        # table, because that table is upserted in place: after any retake it
        # describes a DIFFERENT sitting than the one this report is pinned to.
        submission_id = assessment_store.first_completed_core_submission_id(user.id)
        if submission_id is None:
            raise SystemExit("user %s has no completed core sitting" % email)
        person_scores = assessment_store.dimension_scores_for_submission(submission_id)

        label, cfg, weights = _load_weights(db, source, run_id)
        env_scores = env["dimension_scores"]

        gaps = situation.signed_gaps(env_scores, person_scores)
        dim_weights = dimension_weights(weights)
        order = situation.rank_dimensions(gaps, dim_weights)
        rank_of = {dim: position for position, dim in enumerate(order)}

        print("")
        print("user        : %s (id %d)" % (email, user.id))
        print("weights     : %s" % label)
        print("env report  : id %s, career_status=%s, stage_size=%s, comp=%s"
              % (env["id"], env["career_status"], env["stage_size"], env["comp"]))
        print("observed    : experienced rating %s" % env["experienced_outcome"])
        print("")
        print("NOTE: every number below is D-15-sealed. None of it appears on any")
        print("      API payload; the product ships the bucket word and this order.")
        print("")
        header = ("  %-14s %6s %6s %7s %-10s %-6s %7s %7s %8s %5s"
                  % ("dimension", "env", "person", "gap", "bucket", "dir",
                     "mag", "dirw", "cost", "rank"))
        print(header)
        print("  " + "-" * (len(header) - 2))
        for dim in situation.DIMENSIONS:
            gap = gaps[dim]
            weight = dim_weights[dim]
            print("  %-14s %6.2f %6.2f %+7.3f %-10s %-6s %7.3f %7.3f %8.3f %5d"
                  % (dim, env_scores[dim], person_scores[dim], gap,
                     situation.classify_gap(dim, gap),
                     situation.gap_direction(dim, gap) or "-",
                     weight["mag"], weight["dir"],
                     situation.dimension_cost(dim, gap, weight),
                     rank_of[dim]))

        print("")
        print("  rank order  : %s" % " > ".join(order))

        # P(doing well) under the same weights. score_pairs is match_core's, so
        # it takes conf_missing -- `industry` is masked on every row this source
        # produces, and passing the mask is what keeps its term out of z.
        conf_raw = {
            "stage_size": [float(env["stage_size"])],
            "comp": [np.nan if env["comp"] is None else float(env["comp"])],
            "industry": [None],
        }
        conf_missing = {
            "stage_size": np.array([False]),
            "comp": np.array([env["comp"] is None]),
            "industry": np.array([True]),
        }
        scores = match_scoring.score_pairs(
            {dim: [person_scores[dim]] for dim in situation.DIMENSIONS},
            {dim: [env_scores[dim]] for dim in situation.DIMENSIONS},
            conf_raw, cfg, weights, draws=draws, seed=seed,
            conf_missing=conf_missing,
        )
        print("")
        print("  P(doing well) = %.3f   [%.3f, %.3f]  (%d weight draws, seed %d)"
              % (scores["p_fit"][0], scores["p_fit_low"][0], scores["p_fit_high"][0],
                 draws, seed))
        print("  'doing well' = the experienced rating being 4 or 5; the pinned")
        print("  cutpoint makes sigmoid(z) exactly that probability.")
        print("")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Print one user's per-dimension gaps, costs, rank and P(doing "
                    "well). Local solverah_modeldev only -- D-15 keeps these "
                    "numbers off every API payload."
    )
    add_database_argument(parser)
    parser.add_argument("--email", required=True)
    parser.add_argument("--source", choices=SOURCES, default="priors",
                        help="which weights to rank and score with")
    parser.add_argument("--run-id", type=int, default=None,
                        help="inspect a specific model_run instead of the latest; "
                             "only meaningful with --source run")
    parser.add_argument("--draws", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    url = require_database_url(args.database_url)
    return explain(url, args.email, args.source, args.draws, args.seed,
                   run_id=args.run_id)


if __name__ == "__main__":
    sys.exit(main())
