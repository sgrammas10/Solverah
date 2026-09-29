"""
calibration_harness.py -- an isotonic map from the LLM's band to the human reference's band.

WHY: the extractor never used the 0.1 band in 72 round-1 scoring instances, and a prompt fix did
not move it (STATE 2026-09-01, section 5). That is a systematic, monotone-looking distortion,
which is what a post-hoc isotonic map can correct without trusting the model's own scale.

WHAT IT REFUSES: fitting on fewer than MIN_PACKETS packets that carry a human reference. S-48
put reasonable power at N~15-19 once within-packet correlation is honoured; round 1 had 6.
PREREG_ROUND2_2026-09-29.md section 9 fixes this floor in advance, so it is a constant, not
a parameter. Evaluation is leave-one-PACKET-out, never leave-one-cell-out, for the same reason:
cells of one packet are not independent.

WHAT IT DOES NOT DO: save anything. There is no persistence here on purpose. Shipping a fitted
map into scoring is a separate decision, taken on an evaluation this module prints, not a side
effect of running it.

Inputs are integer band indices 0-4 (0.1 -> 0 ... 0.9 -> 4), one (packet_id, llm_band,
reference_band) triple per cell where BOTH scored. Insufficient-evidence cells are excluded
upstream and never imputed.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from sklearn.isotonic import IsotonicRegression

MIN_PACKETS = 15      # pre-registered (PREREG_ROUND2 section 9); not a tuning knob
N_BANDS = 5


class CalibrationRefused(RuntimeError):
    """Not enough independent packets to fit. Never downgraded to a warning."""


@dataclass(frozen=True)
class Cell:
    packet_id: str
    llm_band: int
    reference_band: int


def _check(cells: list[Cell]) -> None:
    packets = {c.packet_id for c in cells}
    if len(packets) < MIN_PACKETS:
        raise CalibrationRefused(
            f"{len(packets)} packet(s) with a reference reading; at least {MIN_PACKETS} are "
            f"required before any mapping is fitted (PREREG_ROUND2 section 9, S-48)."
        )
    for c in cells:
        if not (0 <= c.llm_band < N_BANDS and 0 <= c.reference_band < N_BANDS):
            raise ValueError(f"band out of range in {c}")


def _fit(cells: list[Cell]) -> IsotonicRegression:
    iso = IsotonicRegression(increasing=True, y_min=0, y_max=N_BANDS - 1, out_of_bounds="clip")
    iso.fit([c.llm_band for c in cells], [c.reference_band for c in cells])
    return iso


def _to_band(x: float) -> int:
    """Nearest band, ties toward the floor -- the direction round 1's bias ran away from."""
    return int(np.floor(x + 0.5 - 1e-9))


def fit_mapping(cells: list[Cell]) -> dict[int, int]:
    """LLM band -> calibrated band, for all five bands. Refuses below MIN_PACKETS."""
    _check(cells)
    iso = _fit(cells)
    return {b: _to_band(float(iso.predict([b])[0])) for b in range(N_BANDS)}


def evaluate(cells: list[Cell]) -> dict:
    """Leave-one-packet-out: mean |band distance| to the reference, raw vs calibrated.

    Each fold fits on every OTHER packet and scores the held-out one, so the calibrated number
    is an honest out-of-sample estimate. Refuses below MIN_PACKETS like fit_mapping.
    """
    _check(cells)
    by_packet: dict[str, list[Cell]] = defaultdict(list)
    for c in cells:
        by_packet[c.packet_id].append(c)
    raw, cal = [], []
    for held_out, test in sorted(by_packet.items()):
        iso = _fit([c for c in cells if c.packet_id != held_out])
        for c in test:
            raw.append(abs(c.llm_band - c.reference_band))
            cal.append(abs(_to_band(float(iso.predict([c.llm_band])[0])) - c.reference_band))
    return {"packets": len(by_packet), "cells": len(raw),
            "raw_mean_distance": float(np.mean(raw)), "calibrated_mean_distance": float(np.mean(cal)),
            "llm_floor_uses_raw": sum(1 for c in cells if c.llm_band == 0)}
