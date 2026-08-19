"""
seed_discipline.py -- the seeds rule (S-04), enforced at the point a number is produced.

THE RULE, adopted 2026-08-19b as D-21, proposed 2026-08-18 and violated three times before
that: a quantitative comparison may be quoted only if it rests on >= MIN_DRAWS independent
draws WITH a paired design and a reported dispersion. Anything less is reported as a pilot,
labelled, WITH NO NUMBER QUOTED.

WHY THE ENFORCEMENT LIVES HERE AND NOT IN A DOCUMENT CHECKER
------------------------------------------------------------
The three violations (-17d finding 3, -17e section 3's 2.5x figure, and the earlier one this
script's own siblings document in lattice_gap_analysis.py section C) were not bad arithmetic.
Every one of them was a legitimate exploratory run whose number was then copied into prose as
a finding. The compute was never wrong; the CLAIM was unwarranted.

A checker that scans documents cannot catch that: handoffs live in Solverah_IP, outside this
git repo (D-11), so CI cannot see them, and "is this number a quantitative comparison" is not
reliably detectable in prose -- a check whose failure is invisible is not a check (S-40).

So the label is attached where the number is born, and travels with it. This is the same
pattern as scoring_key_version (D-14: a stored score carries what makes it interpretable) and
the confidence column (D-17: NULL rather than a default that would read as real).

WHAT MAKES THE METADATA HARD TO FALSIFY
---------------------------------------
`n_draws` and `dispersion` are DERIVED from the per-draw array, never passed in -- a caller
cannot claim five draws while holding one number. And `paired_contrast()` takes the two arms'
per-draw arrays and differences them ELEMENTWISE, refusing unequal lengths: pairing is not an
assertion the caller makes, it is a property of the construction. The honest escape hatch for
genuinely unpaired arms is `unpaired_contrast()`, which is never quotable -- because the rule
says paired, and offering no honest way to report unpaired work is how people reach for the
paired constructor and lie.

DRAWS, NOT JUST SEEDS (decided with Sebastian 2026-08-19b)
-----------------------------------------------------------
The rule was written as ">= 3 seeds", which is simulation-only. S-17 and S-18 analyze real
respondent data, where there is no seed and one sample exists -- under a seeds-only reading
they could never comply, and STATE's claim that they "require the multi-seed paired
discipline" would stay loose in the way S-35 warns about. Generalized: >= MIN_DRAWS
independent draws, where `draw_kind` is "seed" for simulations and "bootstrap" for resampled
real-data statistics.

WHAT THIS RULE DOES NOT GOVERN
------------------------------
Deterministic production computation. `match_core.score_pairs(seed=...)` takes a seed for
reproducibility of a served prediction; it is not a reported comparison and needs no draws.
The rule governs numbers that enter a document as evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "DRAW_KINDS",
    "Finding",
    "MIN_DRAWS",
    "NotQuotable",
]

# The rule as written on 2026-08-18: ">= 3 seeds and a paired design". The 2x2 recovery sweep
# that produced the retraction used 5. Three is the floor, not the target.
MIN_DRAWS = 3

DRAW_KINDS = ("seed", "bootstrap")


class NotQuotable(ValueError):
    """Raised by Finding.quote() on a result the seeds rule does not permit quoting."""


def _mean(values) -> float:
    return sum(values) / len(values)


def _sd(values) -> float | None:
    """Sample SD (ddof=1). None for a single draw -- dispersion is undefined, which is
    itself disqualifying: a point estimate with no spread is the failure mode."""
    if len(values) < 2:
        return None
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _clean(values, what: str) -> list[float]:
    out = [float(v) for v in values]
    if not out:
        raise ValueError(f"{what} is empty -- there is no result to report")
    if any(math.isnan(v) or math.isinf(v) for v in out):
        raise ValueError(f"{what} contains a non-finite value: {out!r}")
    return out


@dataclass(frozen=True)
class Finding:
    """One reportable quantity, carrying what the seeds rule needs to judge it.

    Construct through `estimate()`, `paired_contrast()` or `unpaired_contrast()` -- never by
    calling Finding(...) directly with hand-written metadata, which is exactly the claim the
    constructors exist to make unfalsifiable.
    """

    label: str
    value: float
    dispersion: float | None
    n_draws: int
    draw_kind: str
    # True/False for a two-arm comparison; None for a single-arm estimate, where pairing is
    # not applicable rather than absent.
    paired: bool | None
    unit: str = ""

    def __post_init__(self):
        if self.draw_kind not in DRAW_KINDS:
            raise ValueError(
                f"draw_kind must be one of {DRAW_KINDS}, got {self.draw_kind!r}. A draw is a "
                f"seed (simulation) or a bootstrap resample (real-data statistic)."
            )

    # -- constructors ------------------------------------------------------------------

    @classmethod
    def estimate(cls, label: str, values, *, draw_kind: str = "seed", unit: str = "") -> "Finding":
        """A single-arm quantity measured once per draw. Pairing is not applicable."""
        vals = _clean(values, f"{label!r} values")
        return cls(
            label=label,
            value=_mean(vals),
            dispersion=_sd(vals),
            n_draws=len(vals),
            draw_kind=draw_kind,
            paired=None,
            unit=unit,
        )

    @classmethod
    def paired_contrast(
        cls, label: str, arm_a, arm_b, *, draw_kind: str = "seed", unit: str = ""
    ) -> "Finding":
        """arm_a - arm_b, differenced PER DRAW.

        The two arrays must be the same length and aligned draw-for-draw: element i of each
        must come from the same seed/resample. Pairing is therefore structural -- there is no
        way to pass unpaired data and have it counted as paired, which is the whole point.
        Unequal lengths raise rather than truncating (D-07).
        """
        a = _clean(arm_a, f"{label!r} arm A")
        b = _clean(arm_b, f"{label!r} arm B")
        if len(a) != len(b):
            raise ValueError(
                f"{label!r}: paired_contrast needs one value per arm per draw, got "
                f"{len(a)} and {len(b)}. Unequal lengths mean the arms are not paired -- use "
                f"unpaired_contrast() and report it as the pilot it is."
            )
        diffs = [x - y for x, y in zip(a, b)]
        return cls(
            label=label,
            value=_mean(diffs),
            dispersion=_sd(diffs),
            n_draws=len(diffs),
            draw_kind=draw_kind,
            paired=True,
            unit=unit,
        )

    @classmethod
    def unpaired_contrast(
        cls, label: str, arm_a, arm_b, *, draw_kind: str = "seed", unit: str = ""
    ) -> "Finding":
        """Difference of arm means where draws are NOT aligned. Never quotable under D-21.

        Exists so unpaired work has an honest home. Sampling noise in independently drawn
        arms masquerades as an arm effect -- the failure lattice_gap_analysis.py section C
        documents and recovery_multiseed.py was rebuilt to avoid.
        """
        a = _clean(arm_a, f"{label!r} arm A")
        b = _clean(arm_b, f"{label!r} arm B")
        n = min(len(a), len(b))
        sd_a, sd_b = _sd(a), _sd(b)
        dispersion = (
            math.sqrt(sd_a**2 / len(a) + sd_b**2 / len(b)) * math.sqrt(min(len(a), len(b)))
            if sd_a is not None and sd_b is not None
            else None
        )
        return cls(
            label=label,
            value=_mean(a) - _mean(b),
            dispersion=dispersion,
            n_draws=n,
            draw_kind=draw_kind,
            paired=False,
            unit=unit,
        )

    # -- the judgement -----------------------------------------------------------------

    @property
    def disqualifiers(self) -> tuple[str, ...]:
        """Every reason this may not be quoted. Empty means quotable."""
        reasons = []
        if self.n_draws < MIN_DRAWS:
            reasons.append(
                f"{self.n_draws} {self.draw_kind}{'' if self.n_draws == 1 else 's'} "
                f"(rule requires >= {MIN_DRAWS})"
            )
        if self.paired is False:
            reasons.append("unpaired arms")
        if self.dispersion is None:
            reasons.append("no dispersion (a point estimate with no spread is the failure)")
        return tuple(reasons)

    @property
    def quotable(self) -> bool:
        return not self.disqualifiers

    def quote(self) -> str:
        """The number, formatted -- or NotQuotable. Use where a hard failure is wanted;
        every weakening raises rather than degrading to a safe default (D-07)."""
        if not self.quotable:
            raise NotQuotable(
                f"{self.label!r} may not be quoted under the seeds rule (D-21): "
                f"{'; '.join(self.disqualifiers)}. Report it as a pilot, or run it properly."
            )
        return f"{self.value:.3f}{self.unit}"

    def render(self) -> str:
        """One line, safe to paste anywhere.

        Not quotable -> the number is NOT rendered at all. The rule says "labelled as a pilot
        with no number quoted" and this is that clause with teeth: the console output a
        session copies from simply does not contain the figure. `.value` still holds it for
        further computation, so reaching past this is possible -- and deliberate, and visible
        in a diff.
        """
        if not self.quotable:
            return (
                f"{self.label}: PILOT -- no number quoted "
                f"[{'; '.join(self.disqualifiers)}] (seeds rule, D-21)"
            )
        pairing = "paired " if self.paired else ""
        return (
            f"{self.label}: {self.value:.3f}{self.unit} "
            f"(mean of {self.n_draws} {pairing}{self.draw_kind}s, SD {self.dispersion:.3f})"
        )

    def __str__(self) -> str:
        return self.render()
