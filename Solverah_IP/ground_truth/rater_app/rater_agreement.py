"""
rater_agreement.py -- the anchor-ambiguity flag over returned rater JSONs.

Replaces the Agreement tab of the retired MASTER workbook. It does NOT reimplement that tab's
rule. See THE RULE below: the workbook's numeric `ABS(A-B) > 0.15` was never the live rule, and
it sits *below* one band width, so it would have flagged as ambiguity exactly what the live rule
calls expected instrument resolution.

THE RULE -- read from anchors.json, not hardcoded
-------------------------------------------------
`anchors.json` carries it under `agreement_rule`, frozen at v1-frozen-2026-08-15, and
RATER_INSTRUCTIONS.md quotes that version to the raters. It is a BAND DISTANCE rule:

    same band               -> agreement
    one band apart          -> expected instrument resolution, NOT ambiguity
    two or more bands apart -> anchor ambiguity: reword the band anchor, do NOT average

Bands are [0.1, 0.3, 0.5, 0.7, 0.9]. Three humans are mid-round having been told this. Changing
it now would rescore work already in strangers' hands -- the same reason anchors.json is frozen.

WHY BAND INDICES AND NOT A NUMERIC THRESHOLD
--------------------------------------------
The achievable |differences| between two band values are exactly {0.0, 0.2, 0.4, 0.6, 0.8}, so
ANY threshold strictly inside (0.2, 0.4) produces an identical partition. A numeric threshold is
therefore not a dial -- it is a categorical rule wearing a number's clothing, and writing it as a
float invites someone to "tune" it later as though the intermediate values meant something.

Worse, the obvious threshold is actively broken. In IEEE 754:

    0.7 - 0.3 == 0.39999999999999997        so  (0.7 - 0.3) > 0.4  is False

A genuine two-band gap silently fails a `> 0.4` test. The bug produces a REVIEW list that is
quietly missing rows, which is indistinguishable from a clean result.

So scores are mapped to integer band indices and compared as integers. There is no threshold to
tune and no float comparison anywhere in the flag.

WHO COUNTS
----------
The flag detects ambiguous anchor WORDING. Its whole logic is that a naive reader trips over
wording its author cannot. Julie owns the rubric and rewrites anchors.json after round 1, so her
readings cannot evidence that the text is clear -- she knows what it was meant to say. The flag
is computed over the blind raters only; her scores are carried in full, labelled, as the expert
reference, and drive a separate diagnostic (see `expert_divergence`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Rater roles. Stated by Sebastian 2026-08-19.
# ---------------------------------------------------------------------------
# Deliberately explicit rather than inferred from the filename. The emitted JSON carries
# `rater: "A"` and nothing else -- no name, no role -- so this mapping is the only thing that
# knows Julie is not a blind reader. Getting it wrong produces a flag that looks like it worked.
RATER_ROLES: dict[str, str] = {
    "A": "expert",  # Julie -- partner, domain expert, author of anchors.json
    "B": "blind",   # Carolynn -- lawyer
    "C": "blind",   # George -- lawyer
}

AMBIGUITY_BAND_DISTANCE = 2  # from anchors.json agreement_rule: two_or_more_bands_apart


class AgreementError(RuntimeError):
    """The returned files or the anchors file cannot support the comparison."""


# ---------------------------------------------------------------------------
# Bands
# ---------------------------------------------------------------------------

def load_band_values(anchors_path: Path | str) -> list[float]:
    doc = json.loads(Path(anchors_path).read_text(encoding="utf-8"))
    bands = doc.get("band_values")
    if not bands:
        raise AgreementError(f"{anchors_path} declares no band_values")
    rule = doc.get("agreement_rule") or {}
    # Fail loudly if the frozen rule ever changes shape rather than silently applying the old
    # reading of it. This module encodes ONE rule; a different anchors file needs a new look.
    if "two_or_more_bands_apart" not in rule:
        raise AgreementError(
            f"{anchors_path} agreement_rule has no 'two_or_more_bands_apart' key. This module "
            f"implements the band-distance rule and refuses to guess at a replacement."
        )
    return sorted(float(b) for b in bands)


def band_index(score: float, band_values: list[float], *, tol: float = 1e-9) -> int:
    """Map a rater's score to its integer band index.

    Refuses a score that is not ON a band. The rater page only ever emits band values, so an
    off-band score means the file was hand-edited, produced by a different anchors version, or
    is an average -- and averaging is the one thing the rule explicitly forbids. Snapping it to
    the nearest band would launder exactly the corruption worth catching.
    """
    for i, b in enumerate(band_values):
        if abs(score - b) <= tol:
            return i
    raise AgreementError(
        f"score {score!r} is not one of the band values {band_values}. Not snapping to the "
        f"nearest band: an off-band value means an edited file, a different anchors version, or "
        f"an average -- and 'do not average' is the rule."
    )


# ---------------------------------------------------------------------------
# Loading returned rater files
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Reading:
    packet_id: str
    rater: str
    role: str
    dimension: str
    score: float
    band: int
    confidence: float | None
    recognition: str | None


def load_readings(paths, band_values: list[float]) -> list[Reading]:
    """Read returned solverah_<PACKET>_rater<R>.json files into flat Reading rows."""
    out: list[Reading] = []
    for p in paths:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        rater = doc.get("rater")
        if rater not in RATER_ROLES:
            raise AgreementError(
                f"{p}: rater {rater!r} has no entry in RATER_ROLES. Add it deliberately -- a "
                f"rater silently defaulting to 'blind' would put the rubric's author into the "
                f"ambiguity flag."
            )
        for row in doc.get("scores") or []:
            out.append(
                Reading(
                    packet_id=doc["packet_id"],
                    rater=rater,
                    role=RATER_ROLES[rater],
                    dimension=row["dimension"],
                    score=float(row["score"]),
                    band=band_index(float(row["score"]), band_values),
                    confidence=row.get("confidence"),
                    recognition=doc.get("recognition"),
                )
            )
    return out


# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------

@dataclass
class Cell:
    """One (packet, dimension) cell of the comparison."""

    packet_id: str
    dimension: str
    blind: dict[str, int] = field(default_factory=dict)   # rater letter -> band index
    expert: dict[str, int] = field(default_factory=dict)

    @property
    def blind_spread(self) -> int | None:
        if len(self.blind) < 2:
            return None
        return max(self.blind.values()) - min(self.blind.values())

    @property
    def verdict(self) -> str:
        """REVIEW / WATCH / AGREE / INCOMPLETE, per the frozen rule.

        WATCH is not in anchors.json and is NOT a flag. One band apart is explicitly 'expected
        instrument resolution', so it must not trigger a rewrite. It is surfaced only because
        the flag rests on two readings and will fire rarely; if round 1 yields too few REVIEW
        cells to guide Julie's rewrite, the near-misses are the place to look next -- and
        collecting them now costs nothing, whereas re-deriving them later means reopening
        returned files.
        """
        spread = self.blind_spread
        if spread is None:
            return "INCOMPLETE"
        if spread >= AMBIGUITY_BAND_DISTANCE:
            return "REVIEW"
        if spread == 1:
            return "WATCH"
        return "AGREE"

    @property
    def expert_divergence(self) -> int | None:
        """How far every blind rater sits from the expert, when they agree with each other.

        A separate and arguably stronger signal than blind-vs-blind disagreement: if both blind
        readers land two or more bands from Julie *in the same direction*, they read the anchor
        consistently and read it differently from its author. That is the anchor saying something
        other than what it was written to say -- which blind-vs-blind agreement cannot detect,
        because the two of them agreeing looks like success.

        Returns the signed band distance when it applies, else None.
        """
        if not self.expert or self.blind_spread != 0:
            return None
        expert_band = next(iter(self.expert.values()))
        blind_band = next(iter(self.blind.values()))
        delta = blind_band - expert_band
        return delta if abs(delta) >= AMBIGUITY_BAND_DISTANCE else None


def build_cells(readings: list[Reading]) -> list[Cell]:
    cells: dict[tuple[str, str], Cell] = {}
    for r in readings:
        cell = cells.setdefault(
            (r.packet_id, r.dimension), Cell(r.packet_id, r.dimension)
        )
        target = cell.blind if r.role == "blind" else cell.expert
        target[r.rater] = r.band
    return [cells[k] for k in sorted(cells)]


def review_list(cells: list[Cell]) -> list[Cell]:
    """The cells whose band anchor must be reworded. Do not average them."""
    return [c for c in cells if c.verdict == "REVIEW"]
