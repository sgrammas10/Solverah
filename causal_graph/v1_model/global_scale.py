"""global_scale.py -- the OPTIONAL one-parameter reparameterization of the gap costs.

Pure numpy. No PyMC, so the main suite can test every helper here and serving
could import it without growing a dependency (serving does not import it today:
a saved run's weights are already the EFFECTIVE weights, see below).

WHY IT EXISTS (approved 2026-09-29)
-----------------------------------
priors.yaml carries one expert's per-dimension weights at a tight sd (0.309).
Learning twelve dimension weights independently needs ~1000 outcome rows; early
on there will be ~50-100. The linear predictor also SUMS the six weighted costs,
so a small 0.2 gap on all six already predicts ~3.3/10 P(doing well) -- probably
too harsh, and nothing at 100 rows can move twelve confident weights far enough
to say so.

So, switched on, every DIMENSION weight is reparameterized as

    weight_k = s * prior_mean_k + delta_k

    s        ~ LogNormal(0, sigma_log)           ONE global scale on her whole cost
    delta_k  ~ Normal(0, delta_sd)               tightly-shrunk per-weight deviations

`s` answers the two questions 50-100 rows CAN answer: does the gap predict the
rating at all (s -> 0), and is her overall harshness right (s < 1 softer, s > 1
harsher). Her RELATIVE ordering of the dimensions is kept unless the data pushes
a delta hard enough -- which is what the tight delta_sd is for.

THE CHOICES, with the reason for each
-------------------------------------
* s prior LogNormal(0, 0.5): positive by construction, median exactly 1 (her
  harshness as elicited), 94% prior interval ~[0.39, 2.56]. Being log-scaled it
  reaches toward 0 multiplicatively -- a posterior at 0.2 is two prior sds out,
  which ~100 informative rows can reach. Wider (e.g. 1.0) would let 50 rows
  wander; narrower would make "her harshness is wrong" unanswerable.
* delta_sd 0.10, about a third of her per-weight sd 0.309: small enough that at
  low N the common factor s does the work (a delta costs ~10x as much prior
  density per unit of movement as s does per weight), large enough that a
  single mis-ordered dimension can still show up as a systematic delta at a few
  hundred rows. It is a knob (`--delta-sd`), not a truth.
* Confounders NOT scaled: `comp` and `stage_size` were elicited as separate
  questions about pay and company size, not as gap costs, and `industry` is
  masked on every row. s is "how much do culture gaps matter"; folding pay in
  would let a comp effect masquerade as gap harshness. The intercept and the
  cutpoint spacings are untouched for the same reason.

WHAT A SAVED RUN HOLDS
----------------------
The EFFECTIVE weight, s * mean + delta, under the same twenty flat names as
always (`unflatten_weights` is strict and the set is pinned). build_model
exposes it as a pm.Deterministic under the ordinary `<dim>_<feat>` name, so
run_fit.posterior_weights reads it unchanged. s's own posterior and the
delta_sd live in the run's `notes`, next to the cutpoint spacings.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Optional

import numpy as np

#: LogNormal(mu=0, sigma=DEFAULT_SIGMA_LOG) on s: median 1.
DEFAULT_SIGMA_LOG = 0.5

#: Normal(0, DEFAULT_DELTA_SD) on each per-weight deviation.
DEFAULT_DELTA_SD = 0.10

#: The PyMC name of the scale RV, and the suffix of the deviation RVs.
SCALE_NAME = "global_scale"
DELTA_SUFFIX = "_delta"


def global_scale_settings(sigma_log: float = DEFAULT_SIGMA_LOG,
                          delta_sd: float = DEFAULT_DELTA_SD) -> dict:
    """The validated switch value build_model takes. Both must be positive and finite."""
    sigma_log, delta_sd = float(sigma_log), float(delta_sd)
    for name, value in (("sigma_log", sigma_log), ("delta_sd", delta_sd)):
        if not np.isfinite(value) or value <= 0:
            raise ValueError("global scale %s must be a positive number, got %r" % (name, value))
    return {"sigma_log": sigma_log, "delta_sd": delta_sd}


def scale_dimension_weights(weights: Mapping[str, Any], cfg: Mapping[str, Any],
                            s: float) -> dict:
    """POINT weights with every active DIMENSION weight multiplied by `s`.

    Intercept and confounders are returned unchanged (see the module docstring).
    A deep copy: the caller's dict -- often the expert's loaded priors -- is
    never mutated.
    """
    from match_core import active

    out = copy.deepcopy(dict(weights))
    feats = cfg["settings"]["gap_features"]
    for d in active(cfg["dimensions"]):
        k = d["key"]
        for feat in feats:
            out["dimensions"][k][feat] = float(s) * float(weights["dimensions"][k][feat])
    return out


def hdi(draws: Any, prob: float = 0.94) -> tuple:
    """Shortest interval holding `prob` of the draws (the arviz definition).

    Implemented here so the summary that goes into a run's notes is testable
    without arviz. Needs at least two draws.
    """
    values = np.sort(np.asarray(draws, dtype=float).reshape(-1))
    n = values.size
    if n < 2:
        raise ValueError("hdi needs at least 2 draws, got %d" % n)
    if not 0 < prob < 1:
        raise ValueError("prob must be in (0, 1), got %r" % prob)
    width = int(np.floor(prob * n))
    width = min(max(width, 1), n - 1)
    spans = values[width:] - values[: n - width]
    lo = int(np.argmin(spans))
    return float(values[lo]), float(values[lo + width])


def summarize_scale(draws: Any, prob: float = 0.94) -> dict:
    """{mean, sd, hdi_low, hdi_high, hdi_prob} for s's posterior draws."""
    values = np.asarray(draws, dtype=float).reshape(-1)
    low, high = hdi(values, prob)
    return {
        "mean": float(values.mean()),
        "sd": float(values.std(ddof=1)),
        "hdi_low": low,
        "hdi_high": high,
        "hdi_prob": float(prob),
    }


def uniform_gap_p_fit(cfg: Mapping[str, Any], weights: Mapping[str, Any], gap: float,
                      scale: Optional[float] = None) -> float:
    """P(doing well) when EVERY active dimension has the same signed gap `gap`
    and no confounder is informative (all at their standardized zero).

    The "0.2 gap on all six" illustration of additivity harshness, computed from
    the linear predictor's definition rather than through a person/env pair, so
    the lattice snap cannot move the gap. `weights` are point weights; `scale`,
    if given, multiplies the dimension weights first.
    """
    from match_core import active

    if scale is not None:
        weights = scale_dimension_weights(weights, cfg, scale)
    feats = cfg["settings"]["gap_features"]
    z = float(weights["intercept"])
    for d in active(cfg["dimensions"]):
        w = weights["dimensions"][d["key"]]
        if "mag" in feats:
            z += float(w["mag"]) * abs(gap)
        if "dir" in feats:
            z += float(w["dir"]) * gap
    return float(1.0 / (1.0 + np.exp(-z)))
