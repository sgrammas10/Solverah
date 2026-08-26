"""Pure culture-matching: scoring a company set and shaping the best/worst split.

The scoring itself is :mod:`packages.ml.culture`.  What lives here is the
ranking and presentation logic that sat inside the ``/company-lens/matches``
handler: which dimensions to call out, how to phrase the summary, and how to
split a ranked list into "best" and "worst" when there are too few companies for
both slices to be disjoint.

That last rule is subtle and easy to lose in a rewrite, so it is stated plainly:
when the total is at most ``2 * limit``, best and worst **partition** the whole
list at the midpoint rather than each taking a slice off the end -- otherwise the
same company would appear in both lists, which reads as a bug to a user looking
at four companies.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

__all__ = [
    "DIMENSION_LABELS",
    "build_fit_summary",
    "split_best_and_worst",
    "top_and_bottom_dimensions",
]

#: Dimension keys mapped to the words used in a user-facing sentence.
DIMENSION_LABELS: Dict[str, str] = {
    "empathy": "empathy",
    "creative_drive": "creative drive",
    "adaptability": "adaptability",
    "futuristic": "future orientation",
    "harmony": "harmony",
    "data_orientation": "data orientation",
    "pace": "work pace",
    "work_environment": "work environment",
}


def build_fit_summary(matching: Sequence[str], mismatching: Sequence[str]) -> str:
    """One sentence describing where a company fits and where it does not."""
    match_str = " and ".join(DIMENSION_LABELS.get(d, d) for d in matching)
    mismatch_str = " and ".join(DIMENSION_LABELS.get(d, d) for d in mismatching)
    if mismatching:
        return "Strong alignment on %s; potential friction around %s." % (
            match_str,
            mismatch_str,
        )
    return "Strong alignment on %s." % match_str


def top_and_bottom_dimensions(
    dimension_scores: Dict[str, float]
) -> Tuple[List[str], List[str]]:
    """The two best- and two worst-scoring dimensions.

    With fewer than two scored dimensions the mismatching list is empty rather
    than overlapping the matching one.

    Note the two lists can still overlap at exactly two or three dimensions --
    ``sorted[:2]`` and ``sorted[-2:]`` share members. Preserved from the original
    because the company rows in production carry all six numeric dimensions plus
    pace, so the case does not arise on real data, and changing it would change
    the summary sentence for any row that is missing dimensions.
    """
    ordered = sorted(dimension_scores.items(), key=lambda kv: kv[1], reverse=True)
    matching = [name for name, _ in ordered[:2]]
    mismatching = [name for name, _ in ordered[-2:]] if len(ordered) >= 2 else []
    return matching, mismatching


def split_best_and_worst(scored: List[Any], limit: int) -> Tuple[List[Any], List[Any]]:
    """Split a descending-ranked list into best and worst slices.

    Args:
        scored: Companies ordered best fit first.
        limit: How many to return in each list.

    Returns:
        ``(best, worst)``. ``worst`` is ordered worst-first.

    When there are at most ``2 * limit`` companies the two lists partition the
    whole set at the midpoint, so no company appears in both. Above that
    threshold each takes its own slice off its own end.
    """
    total = len(scored)
    if total <= 2 * limit:
        mid = (total + 1) // 2
        return scored[:mid], scored[mid:]
    return scored[:limit], scored[-limit:][::-1]
