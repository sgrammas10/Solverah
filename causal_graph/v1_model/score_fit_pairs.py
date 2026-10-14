"""score_fit_pairs.py -- the model's side of the blind-rater fit-pair study (C10 hook).

Reads `Solverah_IP/ground_truth/fit_pairs/pair_specs.json` (schema fit_pairs_spec_v1)
and writes `pair_model_scores.json` (schema fit_pairs_model_scores_v1) beside it. The
contract is section 3 of PREREG_FIT_PAIRS_2026-10-13.md.

HOW IT SCORES. Through `company_match_service`'s own `_company_eval`, `_worst_case_z`,
`_order` and `_next_step`, with the weights `priors.yaml` serves (the priors-only path;
SOLVERAH_MODEL_WEIGHTS_SOURCE is ignored on purpose). There is no second ranking
implementation here. One block at a time: one person against that block's companies.
The person's zones and must-haves come from `trait_preferences` (flat_zones /
must_have_keys) on answered TraitPreference values; company traits become company-scope
TraitRecordViews; headcount is None and confounders are masked, as the spec says.

`design_check` and `evidence` are never read: this module only touches `persons`,
`companies`, `blocks`, and `pairs[].pair_id/person_id/company_id`. The `cross_check`
helper (reporting only, used by the CLI) is the one place design_check is compared,
after scoring. z is written to this research file only and never goes on a wire.

    python -m causal_graph.v1_model.score_fit_pairs --specs <path> --out <path>

Every print is ASCII.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import match_scoring  # noqa: E402,F401  -- installs causal_graph/v1_model on sys.path
from solverah.domain import trait_preferences as tp  # noqa: E402

SPEC_SCHEMA = "fit_pairs_spec_v1"
OUT_SCHEMA = "fit_pairs_model_scores_v1"
DEFAULT_SPECS = REPO_ROOT / "Solverah_IP" / "ground_truth" / "fit_pairs" / "pair_specs.json"
DEFAULT_OUT = DEFAULT_SPECS.with_name("pair_model_scores.json")
_STAMP = datetime.datetime(2026, 10, 14, tzinfo=datetime.timezone.utc)

__all__ = ["score_specs", "cross_check", "main"]


def _person(cms, spec_person: dict):
    prefs = {
        k: tp.TraitPreference(
            dimension_key=k,
            under_steps=int(spec_person["tolerance"][k]["under_steps"]),
            over_steps=int(spec_person["tolerance"][k]["over_steps"]),
            must_have=k in spec_person["must_haves"],
            answered=True,
        )
        for k in tp.TRAIT_KEYS
    }
    return cms._Person(
        scores={k: float(spec_person["scores"][k]) for k in tp.TRAIT_KEYS},
        zones=tp.flat_zones(prefs),
        must_haves=tp.must_have_keys(prefs),
        answered=True,
    )


def _records(store, company: dict, cid: int):
    out = []
    for i, k in enumerate(tp.TRAIT_KEYS):
        t = company["traits"][k]
        status = t["status"]
        out.append(store.TraitRecordView(
            id=cid * 10 + i, company_id=cid, job_posting_id=None,
            dimension_key=k, scope="company", scope_label=None, status=status,
            estimate=t.get("estimate") if status == "known" else None,
            low_end=t.get("low_end") if status == "mixed" else None,
            high_end=t.get("high_end") if status == "mixed" else None,
            confidence=None, evidence_count=3 if status != "unknown" else 0,
            abstain_count=0 if status != "unknown" else 1,
            first_dated=None, last_dated=None,
            split_explained_by=t.get("split_explained_by") if status == "mixed" else None,
            aggregation_version="fit-pairs", computed_at=_STAMP,
        ))
    return out


def _git_sha() -> Optional[str]:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or None
    except Exception:
        return None


def score_specs(spec_bytes: bytes, *, scored_at: Optional[str] = None) -> dict:
    from solverah.services import company_match_service as cms
    from solverah.services.company_research.constants import AGGREGATION_VERSION
    import company_evidence_store as store

    spec = json.loads(spec_bytes.decode("utf-8"))
    if spec.get("schema") != SPEC_SCHEMA:
        raise ValueError("spec schema %r is not %s" % (spec.get("schema"), SPEC_SCHEMA))
    cfg, weights = cms._priors_weights()
    persons = {p["person_id"]: p for p in spec["persons"]}
    companies = {c["company_id"]: c for c in spec["companies"]}
    # Stable integer ids for the service (it breaks ties by id): spec order.
    cid_of = {c["company_id"]: i + 1 for i, c in enumerate(spec["companies"])}
    pair_of = {p["pair_id"]: p for p in spec["pairs"]}

    rows: Dict[str, dict] = {}
    for block in spec["blocks"]:
        person = _person(cms, persons[block["person_id"]])
        evals = []
        eval_pair: Dict[int, str] = {}
        for pid in block["pair_ids"]:
            comp = companies[pair_of[pid]["company_id"]]
            cid = cid_of[comp["company_id"]]
            row = types.SimpleNamespace(id=cid, name=comp["company_id"],
                                        slug=comp["company_id"].lower(),
                                        headcount=comp.get("headcount"))
            evals.append(cms._company_eval(
                row, _records(store, comp, cid), dict(comp.get("confounders") or {}), person))
            eval_pair[cid] = pid
        cms._worst_case_z(evals, person, cfg_weights=(cfg, weights))
        cms._order(evals)
        for ev in evals:
            pid = eval_pair[ev.company_id]
            rows[pid] = {
                "pair_id": pid,
                "state": ev.state,
                "z": float(ev.z) if ev.rankable and ev.z is not None else None,
                "must_have_break": bool(ev.must_have_break),
                "risk_flag": ev.flag_counts()["risks"] > 0,
                "next_step": cms._next_step(ev)["category"],
                "rank_in_block": ev.rank if ev.rankable else None,
            }
    pairs = [rows[p["pair_id"]] for p in spec["pairs"]]
    priors_path = REPO_ROOT / "causal_graph" / "v1_model" / "priors.yaml"
    return {
        "schema": OUT_SCHEMA,
        "spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "model": {
            "weights_source": "priors",
            "priors_sha256": hashlib.sha256(priors_path.read_bytes()).hexdigest(),
            "model_run_id": None,
            "aggregation_version": AGGREGATION_VERSION,
            "git_sha": _git_sha(),
            "scored_at": scored_at or datetime.datetime.now(
                datetime.timezone.utc).isoformat(timespec="seconds"),
        },
        "pairs": pairs,
    }


def cross_check(spec: dict, scores: dict) -> List[str]:
    """Pair-level design_check comparison. Reporting only; scoring never reads it."""
    by = {r["pair_id"]: r for r in scores["pairs"]}
    problems = []
    for p in spec["pairs"]:
        d, m = p["design_check"], by[p["pair_id"]]
        want = "ranked" if d["rankable"] else "not_enough_evidence"
        if m["state"] != want:
            problems.append("%s: state %s, design says %s" % (p["pair_id"], m["state"], want))
        for f in ("must_have_break", "risk_flag"):
            if bool(m[f]) != bool(d[f]):
                problems.append("%s: %s=%s, design says %s" % (p["pair_id"], f, m[f], d[f]))
    return problems


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Score the fit-pair specs with the serving model.")
    ap.add_argument("--specs", type=Path, default=DEFAULT_SPECS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    data = args.specs.read_bytes()
    out = score_specs(data)
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    problems = cross_check(json.loads(data.decode("utf-8")), out)
    print("scored %d pairs -> %s" % (len(out["pairs"]), args.out))
    print("design_check mismatches: %d" % len(problems))
    for line in problems:
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
