"""
three_way_dispersion.py -- non-triggering three-way dispersion diagnostic over rater JSONs.

REBUILT 2026-08-20 (S-55). The original delivered file was lost before it was placed on disk;
this is a reconstruction from its recorded specification (STATE.md section 2, D-12, and the
decision-queue entry "All three raters are blind; D-12(b) STANDS; non-triggering three-way
diagnostic added", 2026-08-20). Its tests and planted-mutation checks were re-run at rebuild
time; the original run's verification numbers do not transfer.

WHAT THIS IS AND IS NOT
-----------------------
The S-15 anchor-ambiguity flag (`rater_agreement.py`) computes over the two blind raters, B and
C, per D-12(b) -- Julie authored `anchors.json`, so her readings cannot evidence that its
wording is clear to a naive reader, whatever she was told about company identity. That decision
STANDS. This module does not touch it, feed it, or extend it.

What the two-reader flag cannot see is SCATTER involving the expert: how far apart all three
readings land on the same cell. This module records that, for every (packet, dimension) cell
where all three raters returned a score:

    d(A-B), d(A-C), d(B-C)   -- pairwise integer band distances
    three-way spread          -- max band - min band across the three readings

THE GUARD -- pre-registered before any rater JSON was opened. Binding.
----------------------------------------------------------------------
1. NOTHING in this module triggers a rewrite. It emits no REVIEW verdicts, no flags, no
   worst-cells ranking. The S-15 flag is the only rewrite trigger, and it is elsewhere.
2. NO THRESHOLD on three-way spread may be introduced after seeing the data. A threshold
   adopted post hoc would be a new decision governing round 2 at the earliest -- never
   retroactively round 1.
3. The primary output is a DISTRIBUTION over cells, not a ranked list. A ranked "worst cells"
   list is a flag wearing a different hat: whatever sits at the top gets rewritten. Per-cell
   records are therefore emitted in canonical (packet_id, dimension) order only.
4. ONE licensed inference, fixed in advance: compare the A-B and A-C distance distributions'
   mass at d >= 2 against B-C's. If the Julie-involving pairs carry clearly more mass at
   d >= 2 than the blind pair does, two-reader resolution was the binding constraint on the
   S-15 flag, and a near-empty REVIEW list is weak evidence that the rubric is unambiguous.
   The module reports the three masses; it does not turn them into a verdict.

WHY INTEGER BANDS
-----------------
Same reason as D-12(a), and it is a regression test here: `0.7 - 0.3 == 0.39999999999999997`
in IEEE 754, so a genuine two-band gap FAILS a naive `> 0.4` float test and drops silently out
of any list built on it. Scores are mapped to integer band indices via
`rater_agreement.band_index` (which refuses off-band scores rather than snapping -- an off-band
score means an edited file or an average, and "do not average" is the rule) and compared as
integers. No float comparison exists anywhere in this module.

INSUFFICIENT EVIDENCE (2026-09-29, anchors v3.1)
------------------------------------------------
A reading of "insufficient evidence" has no band, so it has no distance to anything. A cell
where any of the three raters skipped is excluded from every pair distance and from the
three-way spread, and is counted in `cells_skipped` -- counted, not dropped, for the same
reason incomplete cells are. `cells_skipped` is the one key added to SUMMARY_KEYS; it is a
count, not a flag.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from rater_agreement import (  # noqa: F401  (band_index re-exported for tests)
    AgreementError,
    RATER_ROLES,
    Reading,
    band_index,
    load_band_values,
    load_readings,
    permits_insufficient_evidence,
)

# The three pairs, fixed. "A-B" and "A-C" are the Julie-involving pairs; "B-C" is the blind
# pair the S-15 flag computes over. Dropping any of these is a defect, not a simplification --
# the whole point of the diagnostic is the pairs the flag cannot see.
PAIRS: tuple[tuple[str, str], ...] = (("A", "B"), ("A", "C"), ("B", "C"))
# The three raters this diagnostic is about -- round 1's A, B, C. Deliberately NOT
# set(RATER_ROLES): round 2 added a reference rater (D), and "complete" must keep meaning
# "all three round-1 readers present", or every round-1 cell turns incomplete.
THREE_WAY_RATERS = frozenset(r for pair in PAIRS for r in pair)

# Frozen output schema. Tests assert these exact key sets so that a later edit cannot quietly
# grow a `needs_review` (or any other flag-shaped) key -- the guard as an executable test.
SUMMARY_KEYS = frozenset(
    {
        "n_cells",
        "cells_incomplete",
        "cells_skipped",
        "pair_distance_distribution",
        "three_way_spread_distribution",
        "licensed_inference",
    }
)
RECORD_KEYS = frozenset({"packet_id", "dimension", "pair_distances", "three_way_spread"})


@dataclass(frozen=True)
class ThreeWayCell:
    """One (packet, dimension) cell with all three raters present."""

    packet_id: str
    dimension: str
    bands: dict[str, int]  # rater letter -> integer band index

    @property
    def pair_distances(self) -> dict[str, int]:
        return {
            f"{a}-{b}": abs(self.bands[a] - self.bands[b]) for a, b in PAIRS
        }

    @property
    def three_way_spread(self) -> int:
        return max(self.bands.values()) - min(self.bands.values())


def split_three_way_cells(
    readings: list[Reading],
) -> tuple[list[ThreeWayCell], int, int]:
    """Group readings into three-rater cells.

    Returns (complete_cells, n_incomplete, n_skipped). A cell missing any of the three raters
    carries no three-way information and is counted, not silently dropped -- an absence is a
    fact about coverage, not nothing. A cell with all three raters present where any of them
    recorded insufficient evidence is counted in n_skipped, not n_incomplete: the rater did
    return that dimension, and said there was nothing to score.
    """
    grouped: dict[tuple[str, str], dict[str, int | None]] = {}
    for r in readings:
        if r.rater in THREE_WAY_RATERS:
            grouped.setdefault((r.packet_id, r.dimension), {})[r.rater] = r.band

    complete: list[ThreeWayCell] = []
    incomplete = skipped = 0
    for key in sorted(grouped):  # canonical order -- guard clause 3
        bands = grouped[key]
        if not set(bands) >= THREE_WAY_RATERS:
            incomplete += 1
        elif any(b is None for b in bands.values()):
            skipped += 1
        else:
            complete.append(ThreeWayCell(key[0], key[1], dict(bands)))
    return complete, incomplete, skipped


def build_three_way_cells(
    readings: list[Reading],
) -> tuple[list[ThreeWayCell], int]:
    """(complete_cells, n_incomplete) for readings that carry no skips.

    The pre-v3.1 interface, kept so its callers cannot silently lose skipped cells: it refuses
    any skip and points at split_three_way_cells, which counts them.
    """
    complete, incomplete, skipped = split_three_way_cells(readings)
    if skipped:
        raise AgreementError(
            f"{skipped} cell(s) carry insufficient-evidence readings; use "
            f"split_three_way_cells, which counts them, instead of build_three_way_cells."
        )
    return complete, incomplete


def per_cell_records(cells: list[ThreeWayCell]) -> list[dict]:
    """Per-cell records in canonical (packet_id, dimension) order.

    Deliberately NOT sorted by spread or any badness measure -- see guard clause 3. The input
    order from `build_three_way_cells` is already canonical; this re-sorts defensively so a
    caller passing cells in any order still gets the canonical sequence.
    """
    ordered = sorted(cells, key=lambda c: (c.packet_id, c.dimension))
    return [
        {
            "packet_id": c.packet_id,
            "dimension": c.dimension,
            "pair_distances": c.pair_distances,
            "three_way_spread": c.three_way_spread,
        }
        for c in ordered
    ]


def dispersion_summary(cells: list[ThreeWayCell], *, n_incomplete: int = 0,
                       n_skipped: int = 0) -> dict:
    """The primary output: distributions over cells, plus the one licensed inference.

    `pair_distance_distribution` maps each pair to {distance: count}.
    `three_way_spread_distribution` maps spread to count.
    `licensed_inference.mass_d_ge_2` maps each pair to the FRACTION of cells at distance >= 2
    (0.0 when there are no cells). Nothing here is a verdict; guard clauses 1-2 and 4.
    """
    pair_dist: dict[str, dict[int, int]] = {f"{a}-{b}": {} for a, b in PAIRS}
    spread_dist: Counter[int] = Counter()
    for c in cells:
        for pair, d in c.pair_distances.items():
            pair_dist[pair][d] = pair_dist[pair].get(d, 0) + 1
        spread_dist[c.three_way_spread] += 1

    n = len(cells)
    mass = {
        pair: (sum(cnt for d, cnt in dist.items() if d >= 2) / n if n else 0.0)
        for pair, dist in pair_dist.items()
    }
    return {
        "n_cells": n,
        "cells_incomplete": n_incomplete,
        "cells_skipped": n_skipped,
        "pair_distance_distribution": pair_dist,
        "three_way_spread_distribution": dict(sorted(spread_dist.items())),
        "licensed_inference": {"mass_d_ge_2": mass},
    }


def run(paths, anchors_path) -> dict:
    """Load returned rater JSONs and produce the summary. File-in, dict-out; no side effects."""
    band_values = load_band_values(anchors_path)
    readings = load_readings(paths, band_values,
                             allow_insufficient=permits_insufficient_evidence(anchors_path))
    cells, incomplete, skipped = split_three_way_cells(readings)
    return dispersion_summary(cells, n_incomplete=incomplete, n_skipped=skipped)
