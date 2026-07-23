"""
build_model.py -- reads the config + priors and builds the Solverah outcome model.

This is the ARCHITECTURE skeleton: it runs today, with placeholder priors and
no expert input, so you can test the plumbing (does it build, handle missing
inputs, extend cleanly). It is deliberately framework-light -- pure numpy -- so
"it runs" doesn't depend on PyMC being installed. Where the real Bayesian
version plugs in is marked ==> PYMC.

Adding a dimension or confounder requires NO change here -- only the two YAMLs.

    pip install pyyaml numpy --break-system-packages
    python build_model.py
"""

import math
import os
import yaml

MODEL_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Load structure + numbers separately (the whole point of the split)
# ---------------------------------------------------------------------------
def load(cfg_path=None, pri_path=None):
    cfg_path = cfg_path or os.path.join(MODEL_DIR, "solverah_model_config.yaml")
    pri_path = pri_path or os.path.join(MODEL_DIR, "priors.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    with open(pri_path) as f:
        pri = yaml.safe_load(f)
    return cfg, pri


def active(items):
    return [x for x in items if x.get("active")]


# ---------------------------------------------------------------------------
# Deterministic Fit layer: signed gap
# ---------------------------------------------------------------------------
def fit_gap(person_score, env_score):
    return person_score - env_score            # signed, range -1..1


# ---------------------------------------------------------------------------
# Outcome: logistic linear predictor built from config + priors
#   person, env : dict {dim_key: score in 0..1}
#   conf        : dict {confounder_key: raw value}
# ---------------------------------------------------------------------------
def outcome_logit(person, env, conf, cfg, pri):
    feats = cfg["settings"]["gap_features"]     # e.g. ["mag", "dir"]
    z = pri["intercept"]

    for d in active(cfg["dimensions"]):
        k = d["key"]
        g = fit_gap(person[k], env[k])
        w = pri["dimensions"][k]
        if "mag" in feats:
            z += w["mag"] * abs(g)              # any mismatch hurts (symmetric)
        if "dir" in feats:
            z += w["dir"] * g                   # directional asymmetry

    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue                            # unmeasurable -> not a term
        z += pri["confounders"][c["key"]] * conf.get(c["key"], 0.0)

    return z                                    # ==> PYMC: this is your logit;
                                                #     wrap with pm.Bernoulli(...)


def p_fit(person, env, conf, cfg, pri):
    return 1.0 / (1.0 + math.exp(-outcome_logit(person, env, conf, cfg, pri)))


# ---------------------------------------------------------------------------
# Derived views the config gives you for free
# ---------------------------------------------------------------------------
def dag_edges(cfg):
    """Confounder -> env-node edges, for DAGitty / drawing / adjustment sets."""
    edges = []
    for c in active(cfg["confounders"]):
        for dim in c["biases"]:
            edges.append((c["key"], f"env_{dim}"))
    return edges


def sanity_check(cfg, pri):
    dims = active(cfg["dimensions"])
    confs = [c for c in active(cfg["confounders"]) if c.get("measurable")]
    print(f"Active dimensions ({len(dims)}): {[d['key'] for d in dims]}")
    print(f"Active measurable confounders ({len(confs)}): {[c['key'] for c in confs]}")
    print(f"Outcome parents = {len(dims)} fits + {len(confs)} confounders "
          f"= {len(dims) + len(confs)}")

    # synthetic person/company: perfect match vs bad match
    perfect_p = {d["key"]: 0.5 for d in dims}
    perfect_e = {d["key"]: 0.5 for d in dims}
    bad_p = {d["key"]: 0.9 for d in dims}
    bad_e = {d["key"]: 0.1 for d in dims}
    conf = {c["key"]: 0.0 for c in confs}

    print(f"\nP(fit) perfect match (gap=0 everywhere): "
          f"{p_fit(perfect_p, perfect_e, conf, cfg, pri):.3f}")
    print(f"P(fit) large mismatch (gap=0.8 everywhere): "
          f"{p_fit(bad_p, bad_e, conf, cfg, pri):.3f}")
    print(f"\nConfounder->env edges: {dag_edges(cfg)}")


if __name__ == "__main__":
    cfg, pri = load()
    sanity_check(cfg, pri)
