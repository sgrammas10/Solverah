"""
run_agreement_report.py -- operator entry point for the S-15 flag and the three-way
dispersion diagnostic, run against ACTUAL returned rater JSONs.

Neither rater_agreement.py nor three_way_dispersion.py has a __main__: both are
deliberately "file-in, dict-out, no side effects" libraries, exercised so far only by
their test suites against synthetic fixtures. This script is the missing wiring, not a
reimplementation -- every rule (band mapping, the REVIEW/WATCH/AGREE verdict, the
three-way dispersion guard clauses) lives in those two modules and is untouched here.

USAGE
-----
    python run_agreement_report.py <returned_dir> [--anchors PATH]

<returned_dir>  a folder containing the raters' solverah_P-0X_rater{A,B,C}.json files
                 (whatever you name the folder you save emailed attachments into).
--anchors       defaults to anchors.json next to this script -- the FROZEN v1 file.
                 Round 1 was scored under v1; do not point this at anchors_v3_PROPOSED.json,
                 even after it exists, or every score will fail band_index() as off-band
                 the moment v3's band wording changes without changing band_values (it
                 currently doesn't, but this guards the case where it someday does).

WHAT IT PRINTS
---------------
1. REVIEW cells (the actual S-15 flag output -- reword these, per anchors.json's own
   rule, do NOT average) and WATCH cells (one band apart; NOT a flag, collected only so
   round 1 doesn't have to be reopened later if REVIEW comes back near-empty).
2. expert_divergence cells (D-12(c)): blind raters agree with each other but sit >=2
   bands from Julie. Blind agreement can't see this on its own.
3. The three-way dispersion summary (non-triggering by construction -- see that module's
   own guard clauses. This script does not add a ranking or a threshold on top of it).
4. Coverage: how many of the expected 18 (6 packets x 3 raters) files were found, and
   any packet/rater combination that's missing, so a partial return (e.g. Julie + Carolynn
   in, George not yet) is visible as a fact, not silently averaged over.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rater_agreement import (
    RATER_ROLES,
    AgreementError,
    build_cells,
    load_band_values,
    load_readings,
    permits_insufficient_evidence,
)
import three_way_dispersion as twd

EXPECTED_PACKETS = [f"P-0{n}" for n in range(1, 7)]
EXPECTED_RATERS = list(RATER_ROLES)  # ["A", "B", "C"]


def find_returned_files(returned_dir: Path) -> list[Path]:
    paths = sorted(returned_dir.glob("*.json"))
    if not paths:
        raise AgreementError(
            f"no .json files found in {returned_dir} -- point this at the folder you "
            f"saved the emailed solverah_P-0X_rater{{A,B,C}}.json files into."
        )
    return paths


def report_coverage(paths: list[Path]) -> dict[tuple[str, str], Path]:
    """Map (packet_id, rater) -> path, and report what's missing.

    Reads packet_id/rater straight from each file's own contents rather than trusting
    the filename, so a rename doesn't silently misfile a reading.
    """
    found: dict[tuple[str, str], Path] = {}
    bad: list[str] = []
    for p in paths:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            bad.append(f"{p.name}: not valid JSON ({e})")
            continue
        packet_id, rater = doc.get("packet_id"), doc.get("rater")
        if not packet_id or rater not in RATER_ROLES:
            bad.append(f"{p.name}: missing/unrecognized packet_id or rater (got {packet_id!r}, {rater!r})")
            continue
        if (packet_id, rater) in found:
            bad.append(f"{p.name}: duplicate return for {packet_id}/{rater} -- also in {found[(packet_id, rater)].name}")
            continue
        found[(packet_id, rater)] = p

    print("=" * 70)
    print("COVERAGE")
    print("=" * 70)
    missing = [
        f"{pk}/{r}"
        for pk in EXPECTED_PACKETS
        for r in EXPECTED_RATERS
        if (pk, r) not in found
    ]
    print(f"{len(found)}/18 expected (packet, rater) files found.")
    if missing:
        print("Missing: " + ", ".join(missing))
    else:
        print("All 18 present.")
    if bad:
        print("\nFiles skipped (did not parse as a valid rater return):")
        for line in bad:
            print(f"  - {line}")
    print()
    return found


def report_flag(paths: list[Path], band_values: list[float], *,
                allow_insufficient: bool = False) -> None:
    readings = load_readings(paths, band_values, allow_insufficient=allow_insufficient)
    cells = build_cells(readings)

    review = [c for c in cells if c.verdict == "REVIEW"]
    watch = [c for c in cells if c.verdict == "WATCH"]
    incomplete = [c for c in cells if c.verdict == "INCOMPLETE"]
    skipped = [c for c in cells if c.verdict == "SKIPPED"]
    agree = [c for c in cells if c.verdict == "AGREE"]

    print("=" * 70)
    print("S-15 FLAG (computed over B and C only, per D-12(b) -- Julie excluded, authorship)")
    print("=" * 70)
    print(f"cells: {len(cells)} total | REVIEW {len(review)} | WATCH {len(watch)} | "
          f"AGREE {len(agree)} | INCOMPLETE {len(incomplete)}")
    if allow_insufficient:
        report_skips(cells, readings, skipped)
    print()

    if review:
        print("REVIEW -- reword these anchors. Do not average.")
        for c in review:
            print(f"  {c.packet_id:8s} {c.dimension:14s} blind={c.blind}  spread={c.blind_spread}")
    else:
        print("REVIEW list is EMPTY. Per S-15's own sensitivity warning: this is not by "
              "itself evidence the rubric is unambiguous -- two lawyers reading the same "
              "packet correlate heavily, and few-to-zero REVIEW cells was the realistic "
              "expectation going in. Check the WATCH list and the licensed inference below "
              "before treating this as a clean pass.")
    print()

    if watch:
        print("WATCH (one band apart -- NOT a flag, do not act on this alone):")
        for c in watch:
            print(f"  {c.packet_id:8s} {c.dimension:14s} blind={c.blind}  spread={c.blind_spread}")
        print()

    divergent = [c for c in cells if c.expert_divergence is not None]
    if divergent:
        print("expert_divergence (D-12(c)) -- blind raters agree with each other, both sit "
              ">=2 bands from Julie. This is a real signal blind-vs-blind agreement cannot see:")
        for c in divergent:
            print(f"  {c.packet_id:8s} {c.dimension:14s} blind={c.blind}  "
                  f"expert={c.expert}  delta={c.expert_divergence}")
        print()

    if incomplete:
        print(f"INCOMPLETE: {len(incomplete)} cell(s) have fewer than 2 blind readings -- "
              f"a rater hasn't returned all dimensions for that packet yet.")
        print()


def report_skips(cells, readings, skipped) -> None:
    """Insufficient-evidence cells: neither agreement nor disagreement, so their own line.

    Printed only under an anchors file that offers the skip, so a v1 report is unchanged.
    """
    both = [c for c in skipped if all(b is None for b in c.blind.values())]
    print(f"SKIPPED {len(skipped)} (insufficient evidence from a blind rater -- neither "
          f"agreement nor disagreement; not in the counts above): both blind raters skipped "
          f"{len(both)}, one skipped {len(skipped) - len(both)}")
    by_rater: dict[str, int] = {}
    by_dim: dict[str, int] = {}
    for r in readings:
        if r.skipped:
            by_rater[r.rater] = by_rater.get(r.rater, 0) + 1
            by_dim[r.dimension] = by_dim.get(r.dimension, 0) + 1
    print(f"  skips by rater (incl. A): {dict(sorted(by_rater.items()))}")
    print(f"  skips by dimension:       {dict(sorted(by_dim.items()))}")
    for c in skipped:
        print(f"  {c.packet_id:8s} {c.dimension:14s} blind={c.blind}  skipped_by={c.skipped_by}")


def report_dispersion(paths: list[Path], anchors_path: Path) -> None:
    print("=" * 70)
    print("THREE-WAY DISPERSION (non-triggering diagnostic -- informational only)")
    print("=" * 70)
    summary = twd.run(paths, anchors_path)
    print(f"complete three-way cells: {summary['n_cells']}  |  incomplete: {summary['cells_incomplete']}"
          + (f"  |  skipped: {summary['cells_skipped']}" if summary["cells_skipped"] else ""))
    print(f"three_way_spread_distribution: {summary['three_way_spread_distribution']}")
    for pair, dist in summary["pair_distance_distribution"].items():
        print(f"  {pair}: {dist}")
    mass = summary["licensed_inference"]["mass_d_ge_2"]
    print(f"\nlicensed_inference.mass_d_ge_2 (fraction of cells at distance >= 2): {mass}")
    print("Per the module's own guard: this compares A-B/A-C mass against B-C's. It does "
          "NOT license any other threshold or ranking -- read it, do not act on it directly.")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("returned_dir", type=Path, help="folder containing returned rater *.json files")
    ap.add_argument("--anchors", type=Path, default=Path(__file__).parent / "anchors.json",
                     help="path to the anchors file round 1 was scored under (default: "
                          "anchors.json next to this script -- the frozen v1). Do NOT point "
                          "this at anchors_v3_PROPOSED.json for round-1 data.")
    args = ap.parse_args()

    if not args.returned_dir.is_dir():
        print(f"error: {args.returned_dir} is not a directory", file=sys.stderr)
        return 2
    if not args.anchors.is_file():
        print(f"error: anchors file not found at {args.anchors}", file=sys.stderr)
        return 2

    try:
        paths = find_returned_files(args.returned_dir)
        band_values = load_band_values(args.anchors)
        report_coverage(paths)
        report_flag(paths, band_values,
                    allow_insufficient=permits_insufficient_evidence(args.anchors))
        report_dispersion(paths, args.anchors)
    except AgreementError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
