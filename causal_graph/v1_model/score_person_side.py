"""
score_person_side.py

Mechanically recomputes each vignette's person-side dimension score from
assessment_items.yaml + the item_choices frozen in vignette_probes/pairs/vignette_probe_pairs_v1.yaml, and
checks it against the target_person value recorded in that file.

No API needed -- this is pure arithmetic over local files, so it can (and should) be run
and checked BEFORE any company-side LLM call happens, as an audit that the hand-scoring
wasn't just asserted but is actually reproducible from the real scoring method
(scoring.method: mean_pole in assessment_items.yaml).

Usage:
    python score_person_side.py \
        --pairs vignette_probes/pairs/vignette_probe_pairs_v1.yaml \
        --items assessment_items.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def load_items(items_path: Path) -> dict:
    data = yaml.safe_load(items_path.read_text(encoding="utf-8"))
    pole_values = data["scoring"]["pole_values"]
    by_id = {item["id"]: item for item in data["items"]}
    return {"pole_values": pole_values, "by_id": by_id}


def score_choices(choices: dict, items_index: dict) -> tuple[float, list[str]]:
    """Given {item_id: chosen_key}, return (mean_pole_score, [pole per item in order])."""
    by_id = items_index["by_id"]
    pole_values = items_index["pole_values"]
    poles = []
    for item_id, chosen_key in choices.items():
        item = by_id.get(item_id)
        if item is None:
            raise ValueError(f"Unknown item id {item_id!r} -- not in assessment_items.yaml")
        opt = next((o for o in item["options"] if o["key"] == chosen_key), None)
        if opt is None:
            raise ValueError(f"Item {item_id} has no option {chosen_key!r}")
        poles.append(opt["pole"])
    values = [pole_values[p] for p in poles]
    return sum(values) / len(values), poles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="vignette_probes/pairs/vignette_probe_pairs_v1.yaml")
    ap.add_argument("--items", default="assessment_items.yaml")
    args = ap.parse_args()

    pairs_doc = yaml.safe_load(Path(args.pairs).read_text(encoding="utf-8"))
    items_index = load_items(Path(args.items))

    mismatches = []
    total = 0
    print(f"{'dimension':<15}{'level':<8}{'target':<10}{'computed':<12}{'choices'}")
    print("-" * 90)
    for dim_name, dim_body in pairs_doc["dimensions"].items():
        expected_items = set(dim_body["items"])
        for pair in dim_body["pairs"]:
            total += 1
            choices = pair["person_item_choices"]
            if set(choices.keys()) != expected_items:
                mismatches.append(
                    f"{dim_name}/{pair['level']}: item set {set(choices.keys())} != "
                    f"expected {expected_items}"
                )
                continue
            computed, poles = score_choices(choices, items_index)
            target = pair["target_person"]
            status = "OK" if abs(computed - target) < 1e-9 else "MISMATCH"
            if status == "MISMATCH":
                mismatches.append(
                    f"{dim_name}/{pair['level']}: computed {computed} != target {target} "
                    f"(poles: {poles})"
                )
            print(f"{dim_name:<15}{pair['level']:<8}{target:<10}{computed:<12}{choices}")

    print()
    if mismatches:
        print(f"{len(mismatches)} of {total} pairs FAILED to reproduce their frozen target_person value:")
        for m in mismatches:
            print(f"  - {m}")
        print()
        print("Fix vignette_probes/pairs/vignette_probe_pairs_v1.yaml (either the choices or the target) before "
              "running the company side -- a person-side number that doesn't match its own "
              "stated derivation shouldn't be compared against anything.")
        return 1

    print(f"All {total} pairs' person-side scores are reproducible from assessment_items.yaml "
          f"and match their frozen target_person value. Safe to proceed to the company side.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
