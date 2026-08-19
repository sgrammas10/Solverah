"""
score_person_side.py

Mechanically recomputes each vignette's person-side dimension score from the active item
file + the item_choices frozen in a vignette_probes/pairs/*.yaml, and checks it against the
target_person value recorded in that file.

No API needed -- this is pure arithmetic over local files, so it can (and should) be run
and checked BEFORE any company-side LLM call happens, as an audit that the hand-scoring
wasn't just asserted but is actually reproducible from the real scoring method
(scoring.method: mean_pole).

An item file marked `status: superseded` is REFUSED unless --allow-superseded is passed;
assessment_items.yaml has carried that status since 2026-08-18. --items now defaults to the
v2 file. Structural validity of the item file itself is a separate gate --
check_assessment_items.py / test_assessment_items.py -- which this script does not repeat.

Usage:
    python score_person_side.py \
        --pairs vignette_probes/pairs/vignette_probe_pairs_v3_autonomy_ladder.yaml \
        --items assessment_items_v2.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def load_items(items_path: Path, allow_superseded: bool = False) -> dict:
    data = yaml.safe_load(items_path.read_text(encoding="utf-8"))
    # A retired item file must not be silently scoreable. assessment_items.yaml carries
    # status: superseded as of 2026-08-18 (positional key imbalance + flat difficulty --
    # see its header). Reproducing a historical probe run is the only legitimate reason to
    # load it, and that has to be an explicit choice.
    if data.get("status") == "superseded" and not allow_superseded:
        raise SystemExit(
            f"REFUSED: {items_path} is marked status: superseded"
            + (f" (superseded_by: {data['superseded_by']})" if data.get("superseded_by") else "")
            + ".\nScore against the current item file instead. Pass --allow-superseded only "
              "to reproduce a historical run, and label any output as such."
        )
    pole_values = data["scoring"]["pole_values"]
    by_id = {item["id"]: item for item in data["items"]}
    return {"pole_values": pole_values, "by_id": by_id,
            "form_version": data.get("form_version"), "status": data.get("status")}


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


ITEMS_PER_DIMENSION = 4  # D-02. mean_pole over exactly 4 reproduces build_model.PERSON_LATTICE.


def score_all_dimensions(
    choices: dict, items_index: dict, *, items_per_dimension: int = ITEMS_PER_DIMENSION
) -> dict:
    """Given the WHOLE form's {item_id: chosen_key}, return {dimension: mean_pole}.

    WHY THIS EXISTS, and why calling score_choices directly on a full form is a bug
    -------------------------------------------------------------------------------
    score_choices() takes a mean over every choice it is handed. That is correct for its
    original caller, which passes one dimension's four items at a time out of a probe file.
    Handed all 24 responses from a live form it returns a single number -- the mean pole
    across six unrelated constructs -- and it returns it *successfully*. No exception, a
    plausible float in [0, 1], and a value that is not any dimension's score.

    That is the D-07 failure mode exactly: a weakening that produces data which looks fine
    and is not. The form's submit path must call this function, never score_choices.

    Arity is enforced rather than assumed. `build_form` guarantees 24 items in six groups of
    four, but the submit path receives whatever the client posted, and a dropped or duplicated
    response changes mean_pole's denominator silently -- the same reason resolve_responses
    refuses unknown tokens instead of ignoring them. Under-length is not scoreable at all,
    because a three-item mean is not on PERSON_LATTICE.
    """
    by_id = items_index["by_id"]

    by_dim: dict[str, dict] = {}
    for item_id, chosen_key in choices.items():
        item = by_id.get(item_id)
        if item is None:
            raise ValueError(f"Unknown item id {item_id!r} -- not in the active item file")
        by_dim.setdefault(item["dimension"], {})[item_id] = chosen_key

    wrong = {
        dim: len(group)
        for dim, group in by_dim.items()
        if len(group) != items_per_dimension
    }
    if wrong:
        raise ValueError(
            f"expected exactly {items_per_dimension} responses per dimension (D-02); got "
            f"{wrong}. mean_pole over any other count does not land on PERSON_LATTICE, so the "
            f"resulting score is not comparable to a company-side score. Refusing to average."
        )

    return {dim: score_choices(group, items_index)[0] for dim, group in sorted(by_dim.items())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="vignette_probes/pairs/vignette_probe_pairs_v1.yaml")
    ap.add_argument("--items", default="assessment_items_v2.yaml")
    ap.add_argument("--allow-superseded", action="store_true",
                    help="load an item file marked status: superseded "
                         "(historical reproduction only -- label the output as such)")
    args = ap.parse_args()

    pairs_doc = yaml.safe_load(Path(args.pairs).read_text(encoding="utf-8"))
    items_index = load_items(Path(args.items), allow_superseded=args.allow_superseded)
    print(f"items: {args.items}  form_version={items_index['form_version']!r}"
          + ("   [SUPERSEDED -- historical reproduction]" if items_index["status"] == "superseded" else ""))

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
        print(f"Fix {args.pairs} (either the choices or the target) before "
              "running the company side -- a person-side number that doesn't match its own "
              "stated derivation shouldn't be compared against anything.")
        return 1

    print(f"All {total} pairs' person-side scores are reproducible from {args.items} "
          f"and match their frozen target_person value. Safe to proceed to the company side.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
