"""Assemble the local training rows, fit the ordinal head, save the posterior.

SYSTEM PYTHON ONLY -- this is the one module in the package that imports PyMC:

    SOLVERAH_IGNORE_DOTENV=1 APP_ENV=testing \\
    DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah_modeldev \\
    JWT_SECRET_KEY=... \\
    python -m causal_graph.v1_model.devfit.run_fit --chains 2 --tune 500 --draws 500

THE SHAPE OF THE RUN

    assemble_environment_training_data(conn, cfg)   person / env / conf /
                                                    conf_missing / outcome
    build_model.fit_posterior(head="experienced")   OrderedLogistic over the same
                                                    linear predictor, rating-3/4
                                                    cutpoint pinned at 0
    match_scoring.record_fitted_run(...)            one model_run + 20 weight rows

`industry` is masked on every row (the instrument never asks it), so its five
level weights come back exactly at their prior. That is correct and is recorded
in the run's notes rather than hidden by dropping the rows -- see
match_scoring.record_fitted_run.

WHY --prior-sd-scale EXISTS
---------------------------
The expert ticked "confident" on every dimension, so priors.yaml carries sd
0.309 on all twelve dimension weights. At a few hundred rows a prior that tight
barely moves: the posterior mostly returns her numbers, which is what a
confident prior MEANS, not a bug. `--prior-sd-scale` multiplies those sds IN
MEMORY for one run, so a dev can see what the data alone is saying. It never
edits priors.yaml, and the value used is written into the run's notes and the
report -- a posterior fitted under widened priors must never be mistaken for one
fitted under hers.

Only the DIMENSION weights are scaled. The intercept, the confounders and the
cutpoint spacings are left alone: the intercept is the best-identified parameter
in the model and the cutpoint priors were never elicited in the first place, so
widening them would change what the run means for no diagnostic gain.

THE DIAGNOSTIC GATE
-------------------
r_hat >= 1.05 or any divergence and the run is NOT saved. A report is still
written, and the exit code is non-zero. Saving a badly-mixed posterior is worse
than saving nothing: `current_run()` serves the newest run, so an unusable fit
would immediately become what the app reads.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

from . import MODEL_DIR, REPO_ROOT  # noqa: F401  -- sys.path side effects
from .guard import add_database_argument, require_database_url
from .seed_synthetic import DEFAULT_TRUTH_PATH

import numpy as np

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def scaled_priors(pri, scale):
    """A deep copy of `pri` with every DIMENSION weight's sd multiplied by `scale`.

    Deep-copied rather than mutated: `match_core.load()` returns a fresh dict each
    call today, but a future cache would turn an in-place edit into a process-wide
    change to the expert's numbers.
    """
    if scale == 1.0:
        return copy.deepcopy(pri)
    out = copy.deepcopy(pri)
    for dim, feats in out["dimensions"].items():
        for feat in feats:
            out["dimensions"][dim][feat]["sd"] = float(
                out["dimensions"][dim][feat]["sd"] * scale
            )
    return out


def posterior_weights(idata, cfg):
    """arviz posterior -> the nested {mean, sd} shape weights_from_priors returns.

    Plain Python floats and numpy arrays, so `match_scoring.record_fitted_run`
    never sees an xarray object and `match_scoring` never imports pymc.
    """
    from match_core import active

    post = idata.posterior

    def leaf(name):
        values = np.asarray(post[name].values).reshape(-1)
        return {"mean": float(values.mean()), "sd": float(values.std(ddof=1))}

    feats = cfg["settings"]["gap_features"]
    out = {"intercept": leaf("intercept"), "dimensions": {}, "confounders": {}}
    for d in active(cfg["dimensions"]):
        out["dimensions"][d["key"]] = {f: leaf("%s_%s" % (d["key"], f)) for f in feats}
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue
        key = c["key"]
        if c.get("kind") == "categorical":
            levels = len(c["levels"])
            values = np.asarray(post["w_%s" % key].values).reshape(-1, levels)
            out["confounders"][key] = {
                "mean": values.mean(axis=0),
                "sd": values.std(axis=0, ddof=1),
            }
        else:
            out["confounders"][key] = leaf("w_%s" % key)
    return out


def cutpoint_spacings(idata):
    """(mean, sd) per free spacing. NOT weight rows -- see record_fitted_run."""
    values = np.asarray(idata.posterior["cut_spacing"].values)
    values = values.reshape(-1, values.shape[-1])
    return [
        {"mean": float(values[:, i].mean()), "sd": float(values[:, i].std(ddof=1))}
        for i in range(values.shape[1])
    ]


def diagnostics(idata):
    """Worst r_hat, where it was, and the divergence count.

    r_hat is UNAVAILABLE with a single chain -- it is a between-chain statistic,
    and arviz returns NaN for every variable. Reported as NaN rather than
    collapsed to 0.0, because a 0.0 would sail through `is_healthy`'s `< 1.05`
    and turn the gate into something that cannot fail. A one-chain run is
    therefore never saved, which is correct: nothing has checked that it mixed.
    """
    import arviz as az

    rhat = az.rhat(idata)
    worst_name, worst = "", float("-inf")
    for name in rhat.data_vars:
        values = np.asarray(rhat[name].values, dtype=float)
        if not np.isfinite(values).any():
            continue
        value = float(np.nanmax(values))
        if value > worst:
            worst_name, worst = str(name), value

    if worst == float("-inf"):
        worst, worst_name = float("nan"), "unavailable (r_hat needs >= 2 chains)"

    divergences = int(np.asarray(idata.sample_stats["diverging"].values).sum())
    return {"max_rhat": worst, "max_rhat_on": worst_name, "divergences": divergences}


#: A posterior must clear both to be saved. `current_run()` serves the NEWEST
#: run, so an unusable fit would immediately become what the app reads -- saving
#: nothing is strictly better than saving that.
RHAT_CEILING = 1.05


def _rhat_text(diag):
    """`nan` formatted as %.4f reads as a number. It is not one."""
    value = diag["max_rhat"]
    return "%.4f" % value if np.isfinite(value) else "UNAVAILABLE"


def is_healthy(diag):
    """Whether this run may be saved.

    A non-finite r_hat fails. That is the one-chain case, and "we could not
    check" has to be treated as "not verified", never as "fine": the whole point
    of the gate is that an unchecked posterior does not reach the app.
    """
    # bool(), not the numpy bool `np.isfinite` hands back: this is a predicate
    # other code branches on and tests compare with `is False`.
    return bool(
        np.isfinite(diag["max_rhat"])
        and diag["max_rhat"] < RHAT_CEILING
        and diag["divergences"] == 0
    )


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------
def _truth_lookup(truth):
    """{flat weight name: true value} from a last_truth.json record."""
    if not truth:
        return {}
    flat = {"intercept": float(truth["intercept"])}
    for dim, feats in truth.get("dimensions", {}).items():
        for feat, value in feats.items():
            flat["%s_%s" % (dim, feat)] = float(value)
    for key, value in truth.get("confounders", {}).items():
        if isinstance(value, (int, float)):
            flat["w_%s" % key] = float(value)
    return flat


def _covered(prior_mean, post_mean, true_value):
    """Share of the prior -> truth distance the posterior actually travelled.

    Returns None where the prior already sat on the truth: the denominator is
    zero and "100% of nothing" would read as a success the fit never had to earn.
    """
    distance = true_value - prior_mean
    if abs(distance) < 1e-9:
        return None
    return 100.0 * (post_mean - prior_mean) / distance


def write_report(path, *, run_id, cfg, prior_weights, post_weights, spacings,
                 diag, rows_kept, dropped, wall, args, truth, saved):
    from match_core import flatten_weights

    prior_flat = {n: (m, s) for n, m, s in flatten_weights(cfg, prior_weights)}
    post_flat = {n: (m, s) for n, m, s in flatten_weights(cfg, post_weights)}
    truth_flat = _truth_lookup(truth)

    lines = []
    lines.append("# devfit fit report -- model_run %s" % (run_id if saved else "NOT SAVED"))
    lines.append("")
    lines.append("- database: `%s`" % args.database_url_display)
    lines.append("- rows fitted: **%d**   (dropped %d)" % (rows_kept, len(dropped)))
    lines.append("- chains %d, tune %d, draws %d, seed %d"
                 % (args.chains, args.tune, args.draws, args.seed))
    lines.append("- `--prior-sd-scale` **%.2f**%s"
                 % (args.prior_sd_scale,
                    "" if args.prior_sd_scale == 1.0
                    else "  (DIMENSION weight sds widened in memory; priors.yaml untouched)"))
    lines.append("- wall time: %.1f s" % wall)
    lines.append("- max r_hat: **%s** (%s); divergences: **%d**"
                 % (_rhat_text(diag), diag["max_rhat_on"], diag["divergences"]))
    if not saved:
        lines.append("")
        lines.append("> **NOT SAVED.** The diagnostic gate refused this run "
                     "(r_hat missing or >= 1.05, or a divergence). `current_run()` serves the "
                     "newest run, so an unusable posterior would immediately become "
                     "what the app reads.")
    lines.append("")

    if dropped:
        lines.append("## Dropped rows")
        lines.append("")
        reasons = {}
        for row in dropped:
            for reason in row["reason"]:
                reasons[reason] = reasons.get(reason, 0) + 1
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            lines.append("- `%s` x %d" % (reason, count))
        lines.append("")

    lines.append("## Weights: prior -> posterior")
    lines.append("")
    if truth_flat:
        lines.append("| weight | prior mean | prior sd | post mean | post sd | truth | covered |")
        lines.append("|---|---|---|---|---|---|---|")
    else:
        lines.append("| weight | prior mean | prior sd | post mean | post sd |")
        lines.append("|---|---|---|---|---|")

    for name in post_flat:
        p_mean, p_sd = prior_flat[name]
        q_mean, q_sd = post_flat[name]
        if truth_flat:
            true_value = truth_flat.get(name)
            if true_value is None:
                cells = "| -- | -- |"
            else:
                share = _covered(p_mean, q_mean, true_value)
                cells = "| %+.3f | %s |" % (
                    true_value,
                    "n/a (prior on truth)" if share is None else "%.0f%%" % share,
                )
            lines.append("| `%s` | %+.3f | %.3f | %+.3f | %.3f %s"
                         % (name, p_mean, p_sd, q_mean, q_sd, cells))
        else:
            lines.append("| `%s` | %+.3f | %.3f | %+.3f | %.3f |"
                         % (name, p_mean, p_sd, q_mean, q_sd))
    lines.append("")

    lines.append("## Cutpoint spacings")
    lines.append("")
    lines.append("Not weight rows: the flat weight set is a database interface pinned at")
    lines.append("20, and the rating-3/4 cutpoint is fixed at 0, so serving P(doing well)")
    lines.append("needs the 20 weights and nothing else. Recorded here and in the run's")
    lines.append("`notes` as a diagnostic.")
    lines.append("")
    lines.append("| spacing | post mean | post sd |")
    lines.append("|---|---|---|")
    for i, spacing in enumerate(spacings):
        lines.append("| `cut_spacing[%d]` | %.3f | %.3f |"
                     % (i, spacing["mean"], spacing["sd"]))
    lines.append("")

    lines.append("## Flags")
    lines.append("")
    lines.append("- `industry` is masked on every row from this source -- the instrument")
    lines.append("  never asks it -- so its five level weights are the prior, unmoved.")
    lines.append("  They are exported as-is; the row set is a contract.")
    if truth:
        lines.append("- planted truth: %s"
                     % ", ".join("`%s` = %+.2f" % (k, v)
                                 for k, v in sorted(truth.get("planted", {}).items())))
        lines.append("- cohort: n=%d, seed=%d, aligned_rate=%.2f, comp_unsure_rate=%.2f"
                     % (truth["n"], truth["seed"], truth["aligned_rate"],
                        truth["comp_unsure_rate"]))
    else:
        lines.append("- no `last_truth.json` found, so no truth column: this report")
        lines.append("  describes movement from the prior and nothing about accuracy.")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


# ---------------------------------------------------------------------------
def _quiet_third_party_logging():
    """Importing `app` installs the API's logging config, whose default level is
    DEBUG. Numba (which arviz pulls in) then logs its whole SSA rewrite pass --
    thousands of lines per sample -- and buries the diagnostics this script exists
    to print. Raised to WARNING here rather than by setting LOG_LEVEL, so the
    quieting is visible in the file that needs it.
    """
    import logging

    logging.getLogger().setLevel(logging.WARNING)
    for name in ("numba", "pytensor", "arviz", "solverah", "matplotlib"):
        logging.getLogger(name).setLevel(logging.WARNING)


def run(args):
    url = require_database_url(args.database_url)
    args.database_url_display = url.rsplit("/", 1)[-1]
    os.environ["DATABASE_URL"] = url

    import assemble_training_data as atd
    import build_model as bm
    import match_core
    import match_scoring
    from app import app
    from model import db

    _quiet_third_party_logging()

    cfg, pri = match_core.load()
    fit_pri = scaled_priors(pri, args.prior_sd_scale)

    with app.app_context():
        with db.engine.connect() as conn:
            result = atd.assemble_environment_training_data(conn, cfg)

        rows_kept = len(result.rows)
        print("assembled %d row(s); dropped %d" % (rows_kept, len(result.dropped)))
        if result.dropped:
            reasons = {}
            for row in result.dropped:
                for reason in row["reason"]:
                    reasons[reason] = reasons.get(reason, 0) + 1
            for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
                print("  dropped: %s x %d" % (reason, count))
        if rows_kept < args.min_rows:
            raise SystemExit(
                "only %d row(s) -- refusing to fit below --min-rows=%d. Seed first."
                % (rows_kept, args.min_rows)
            )
        print("unsupplied confounders: %s" % (result.unsupplied_confounders,))
        print("outcome counts 1..5: %s"
              % np.bincount(result.outcome, minlength=6)[1:].tolist())

        started = time.time()
        idata = bm.fit_posterior(
            result.person, result.env, result.conf, result.outcome, cfg, fit_pri,
            head="experienced", conf_missing=result.conf_missing,
            draws=args.draws, tune=args.tune, chains=args.chains, cores=args.cores,
            random_seed=args.seed, progressbar=False,
            compute_convergence_checks=False,
        )
        wall = time.time() - started

        diag = diagnostics(idata)
        print("")
        print("wall %.1f s | max r_hat %s (%s) | divergences %d"
              % (wall, _rhat_text(diag), diag["max_rhat_on"], diag["divergences"]))

        prior_weights = match_core.weights_from_priors(cfg, fit_pri)
        post_weights = posterior_weights(idata, cfg)
        spacings = cutpoint_spacings(idata)

        truth = None
        truth_path = Path(args.truth)
        if truth_path.exists():
            truth = json.loads(truth_path.read_text(encoding="ascii"))
            print("truth loaded from %s" % truth_path)
        else:
            print("no truth file at %s -- report will omit the truth column" % truth_path)

        healthy = is_healthy(diag)
        run_id = None
        if healthy:
            notes = json.dumps({
                "source": "devfit",
                "head": "experienced",
                "prior_sd_scale": args.prior_sd_scale,
                "chains": args.chains, "tune": args.tune, "draws": args.draws,
                "seed": args.seed,
                "max_rhat": round(float(diag["max_rhat"]), 5),
                "divergences": diag["divergences"],
                "cut_spacing": [
                    {"mean": round(s["mean"], 6), "sd": round(s["sd"], 6)}
                    for s in spacings
                ],
                "industry": ("fully masked by this source -- the environment "
                             "instrument never asks it, so the five level weights "
                             "are the prior, unmoved by data"),
                "comp_missing_rows": int(np.asarray(result.conf_missing["comp"]).sum()),
            }, sort_keys=True)
            fitted = match_scoring.record_fitted_run(
                db, cfg, post_weights, n_rows=rows_kept, notes=notes
            )
            db.session.commit()
            run_id = fitted.id
            print("saved model_run %d (%s)" % (run_id, fitted.model_version))
        else:
            print("REFUSED to save: r_hat %s (ceiling %.2f), divergences %d"
                  % (_rhat_text(diag), RHAT_CEILING, diag["divergences"]))
            if not np.isfinite(diag["max_rhat"]):
                print("  r_hat is a between-chain statistic -- rerun with --chains 2+")

    report_path = write_report(
        REPORTS_DIR / ("fit_%s.md" % (run_id if run_id else "unsaved_%d" % int(time.time()))),
        run_id=run_id, cfg=cfg, prior_weights=prior_weights, post_weights=post_weights,
        spacings=spacings, diag=diag, rows_kept=rows_kept, dropped=result.dropped,
        wall=wall, args=args, truth=truth, saved=healthy,
    )
    print("report written to %s" % report_path)
    return 0 if healthy else 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble local rows, fit the ordinal head, save the posterior."
    )
    add_database_argument(parser)
    parser.add_argument("--chains", type=int, default=2)
    parser.add_argument("--tune", type=int, default=500)
    parser.add_argument("--draws", type=int, default=500)
    parser.add_argument("--cores", type=int, default=1,
                        help="1 keeps chains sequential; multiprocessing spawn under "
                             "Windows re-imports the app per chain")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--prior-sd-scale", type=float, default=1.0,
                        help="multiply every DIMENSION weight's prior sd by this, in "
                             "memory only. priors.yaml is never edited.")
    parser.add_argument("--min-rows", type=int, default=50,
                        help="refuse to fit below this many assembled rows")
    parser.add_argument("--truth", default=str(DEFAULT_TRUTH_PATH),
                        help="last_truth.json from the seeder (default %s)"
                             % DEFAULT_TRUTH_PATH)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
