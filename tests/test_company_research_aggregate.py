"""The aggregation rule (six-trait build, C5; agg-v2 after the C5b review fixes),
pinned case by case, no database.

Rule under test: solverah/services/company_research/aggregate.py, constants in
constants.py under AGGREGATION_VERSION. The table of cases is the plan's (C5, REVISED
to Julie's anchors ruling 5) plus research-ground-truth's measured holes (2026-10-13):
5x0.9 + 1x0.1 is known/high with lower confidence; 3 vs 3 is mixed; a split explained
by scope TYPE (never by label); a split explained by time; 2 items is unknown; all
abstaining is unknown; nothing inside 24 months is unknown; company-authored-only
evidence is never known; the 0.5 items stay in a known estimate.
"""
from __future__ import annotations

import datetime

import pytest

from solverah.services.company_research import constants
from solverah.services.company_research.aggregate import (
    ScoredEntry,
    aggregate_dimension,
    is_independent,
    size_discount,
)

TODAY = datetime.date(2026, 10, 13)
RECENT = datetime.date(2026, 6, 1)
OLD = datetime.date(2023, 1, 15)  # > 24 months before TODAY


def _entries(scores, *, dates=None, scopes=None, sources=None, speakers=None):
    rows = []
    for i, score in enumerate(scores):
        date = dates[i] if dates else RECENT
        scope, label = (scopes[i] if scopes else ("company", None))
        rows.append(ScoredEntry(
            score_id=i + 1, score=score, published_at=date, scope=scope, scope_label=label,
            source_type=sources[i] if sources else "employee_review",
            speaker=speakers[i] if speakers else None,
        ))
    return rows


def test_version_is_stamped_and_the_constants_are_the_documented_ones():
    assert constants.AGGREGATION_VERSION == "agg-v2-2026-10-13"
    assert constants.MIN_SCORED_ITEMS == 3
    assert constants.RECENCY_DAYS == 730
    assert constants.MIXED_MIN_SIDE_COUNT == 2
    assert constants.MIXED_MIN_SIDE_FRACTION == 0.25
    assert constants.PARAPHRASE_MAX_SHARED_WORDS == 7
    assert constants.PARAPHRASE_MAX_TRIGRAM_REUSE == 0.35
    assert constants.VERIFY_MIN_COVERAGE == 0.9
    assert constants.TIME_SPLIT_KNOWN_MIN_INDEPENDENT_RECENT == 3
    assert constants.INDEPENDENT_SOURCE_TYPES == ("employee_review", "news")


def test_five_high_one_low_is_known_high_with_lower_confidence():
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.9, 0.9, 0.9, 0.1]), today=TODAY, headcount=50)
    assert agg.status == "known"
    assert agg.estimate == 0.9  # the predominant side's mean, the minority is not averaged in
    assert agg.low_end is None and agg.high_end is None
    unanimous = aggregate_dimension(_entries([0.9] * 6), today=TODAY, headcount=50)
    assert unanimous.status == "known" and unanimous.estimate == 0.9
    assert agg.confidence < unanimous.confidence  # spread lowered it
    assert agg.scored == 6 and agg.abstained == 0 and len(agg.score_ids) == 6
    assert agg.unknown_reason is None


def test_three_against_three_is_mixed_with_both_ends_and_no_estimate():
    agg = aggregate_dimension(_entries([0.1, 0.3, 0.1, 0.9, 0.7, 0.9]), today=TODAY)
    assert agg.status == "mixed"
    assert agg.estimate is None
    assert agg.low_end == pytest.approx((0.1 + 0.3 + 0.1) / 3)
    assert agg.high_end == pytest.approx((0.9 + 0.7 + 0.9) / 3)
    assert agg.split_explained_by is None  # same scope, same window: nothing explains it
    assert agg.confidence is not None


def test_mixed_needs_two_on_the_smaller_side_and_a_quarter_of_the_items():
    # 7 vs 2: two on the small side but 2/9 < 25% -> known
    agg = aggregate_dimension(_entries([0.9] * 7 + [0.1, 0.1]), today=TODAY)
    assert agg.status == "known" and agg.estimate == 0.9
    # 4 vs 2: 2/6 = 33% and two items -> mixed
    agg = aggregate_dimension(_entries([0.9] * 4 + [0.1, 0.1]), today=TODAY)
    assert agg.status == "mixed"
    # 3 vs 1: one item is never a side
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.9, 0.1]), today=TODAY)
    assert agg.status == "known" and agg.estimate == 0.9
    # 6 vs 2: exactly 25% -> mixed (provisional, Julie ask 1)
    agg = aggregate_dimension(_entries([0.9] * 6 + [0.1, 0.1]), today=TODAY)
    assert agg.status == "mixed"


def test_a_split_explained_by_scope_type_is_recorded():
    """Company-wide material one way, role-level reviews the other: the scope TYPE
    partitions the items and each part is single-sided."""
    scopes = [("company", None)] * 3 + [("role", "Cashier"), ("role", "Stocker"), ("role", "Driver")]
    agg = aggregate_dimension(
        _entries([0.9, 0.7, 0.9, 0.1, 0.3, 0.1], scopes=scopes), today=TODAY
    )
    assert agg.status == "mixed"
    assert agg.split_explained_by == "scope"


def test_review_f6_five_different_titles_are_one_scope_and_explain_nothing():
    """Measured hole: five reviews each with its own job title used to be five
    singleton 'scope' groups and the split read as explained by scope. Labels are
    free text; only the scope type partitions."""
    scopes = [("role", "Cashier"), ("role", "Stocker"), ("role", "Driver"),
              ("role", "Engineer"), ("role", "Analyst")]
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.7, 0.1, 0.3], scopes=scopes), today=TODAY)
    assert agg.status == "mixed"
    assert agg.split_explained_by is None


def test_a_scope_group_smaller_than_the_side_minimum_explains_nothing():
    scopes = [("company", None)] * 5 + [("location", "Austin")]
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.9, 0.1, 0.1, 0.1], scopes=scopes), today=TODAY)
    assert agg.status == "mixed" and agg.split_explained_by is None


def test_a_split_explained_by_time_is_recorded_as_mixed_when_the_recent_side_is_thin():
    dates = [RECENT] * 2 + [OLD] * 3
    agg = aggregate_dimension(_entries([0.9, 0.7, 0.1, 0.3, 0.1], dates=dates), today=TODAY)
    assert agg.status == "mixed"
    assert agg.split_explained_by == "time"
    assert agg.estimate is None


def test_julie_ask_4_a_time_split_with_three_recent_independent_items_is_known_recently():
    """Provisional: the recent side alone has >= 3 independent items -> known in the
    recent direction, with 'time' kept as the "changed recently" note."""
    dates = [RECENT] * 3 + [OLD] * 3
    agg = aggregate_dimension(_entries([0.9, 0.7, 0.9, 0.1, 0.3, 0.1], dates=dates), today=TODAY)
    assert agg.status == "known"
    assert agg.estimate == pytest.approx((0.9 + 0.7 + 0.9) / 3)
    assert agg.split_explained_by == "time"
    assert agg.low_end is None and agg.high_end is None
    # ...but not when the recent items are company-authored.
    sources = ["careers_page"] * 3 + ["employee_review"] * 3
    agg = aggregate_dimension(
        _entries([0.9, 0.7, 0.9, 0.1, 0.3, 0.1], dates=dates, sources=sources), today=TODAY
    )
    assert agg.status == "unknown" and agg.unknown_reason == "no_recent_independent_item"


def test_scope_is_tried_before_time_and_an_impure_partition_explains_nothing():
    # Both partitions line up: scope wins, being checked first.
    scopes = [("company", None)] * 3 + [("location", "Berlin")] * 3
    dates = [RECENT] * 3 + [OLD] * 3
    agg = aggregate_dimension(
        _entries([0.9, 0.7, 0.9, 0.1, 0.3, 0.1], scopes=scopes, dates=dates), today=TODAY
    )
    assert agg.split_explained_by == "scope"
    # A scope group that itself straddles the split explains nothing.
    scopes = [("company", None)] * 4 + [("location", "Berlin")] * 2
    agg = aggregate_dimension(
        _entries([0.9, 0.7, 0.1, 0.9, 0.1, 0.3], scopes=scopes), today=TODAY
    )
    assert agg.status == "mixed" and agg.split_explained_by is None


def test_two_items_is_unknown():
    agg = aggregate_dimension(_entries([0.9, 0.9]), today=TODAY)
    assert agg.status == "unknown" and agg.unknown_reason == "too_few_items"
    assert agg.estimate is None and agg.confidence is None
    assert len(agg.score_ids) == 2  # still linked, so the record's counts derive


def test_all_abstaining_is_unknown_with_every_row_linked():
    agg = aggregate_dimension(_entries([None, None, None, None]), today=TODAY)
    assert agg.status == "unknown"
    assert agg.scored == 0 and agg.abstained == 4 and len(agg.score_ids) == 4


def test_nothing_inside_24_months_is_unknown_and_undated_items_do_not_count_as_recent():
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.9], dates=[OLD, OLD, OLD]), today=TODAY)
    assert agg.status == "unknown" and agg.unknown_reason == "no_recent_independent_item"
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.9], dates=[None, None, OLD]), today=TODAY)
    assert agg.status == "unknown"
    # One recent item is enough to open the window; the old ones still count.
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.9], dates=[OLD, OLD, RECENT]), today=TODAY)
    assert agg.status == "known" and agg.recent == 1


def test_the_boundary_of_the_window_is_inclusive_at_730_days():
    edge = TODAY - datetime.timedelta(days=constants.RECENCY_DAYS)
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.9], dates=[edge, OLD, OLD]), today=TODAY)
    assert agg.status == "known"
    over = TODAY - datetime.timedelta(days=constants.RECENCY_DAYS + 1)
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.9], dates=[over, OLD, OLD]), today=TODAY)
    assert agg.status == "unknown"


def test_abstentions_do_not_count_toward_the_minimum_or_the_sides():
    agg = aggregate_dimension(_entries([0.9, 0.9, None, None, None]), today=TODAY)
    assert agg.status == "unknown" and agg.scored == 2 and agg.abstained == 3


def test_review_f5_the_midpoint_items_stay_in_a_known_estimate():
    """Measured hole: 5x0.5 + 3x0.7 + 1x0.3 used to drop the five 0.5s with the
    minority. The estimate is the larger side TOGETHER WITH the 0.5 items."""
    agg = aggregate_dimension(_entries([0.5] * 5 + [0.7] * 3 + [0.3]), today=TODAY)
    assert agg.status == "known"
    assert agg.estimate == pytest.approx((0.5 * 5 + 0.7 * 3) / 8)
    # 2 high + 3 neutral, no minority side: the mean of everything.
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.5, 0.5, 0.5]), today=TODAY)
    assert agg.status == "known"
    assert agg.estimate == pytest.approx((0.9 + 0.9 + 0.5 * 3) / 5)
    # One low against two high: the high side and the 0.5s; the 0.1 drops out.
    agg = aggregate_dimension(_entries([0.9, 0.9, 0.1, 0.5, 0.5]), today=TODAY)
    assert agg.status == "known" and agg.estimate == pytest.approx((0.9 + 0.9 + 0.5 + 0.5) / 4)
    # No side at all: the mean of everything.
    agg = aggregate_dimension(_entries([0.5, 0.5, 0.5]), today=TODAY)
    assert agg.status == "known" and agg.estimate == 0.5
    # A 1:1 tie with a neutral: known at the mean (the probe's 0.1, 0.9, 0.5 case).
    agg = aggregate_dimension(_entries([0.1, 0.9, 0.5]), today=TODAY)
    assert agg.status == "known" and agg.estimate == pytest.approx(0.5)


def test_review_f4_f8_one_dated_item_and_seven_careers_items():
    """Measured hole: 1 dated + 7 access-dated careers items came out known with full
    count confidence. Now: careers items are company-authored, so they count toward
    neither recency nor independent support."""
    dates = [RECENT] + [None] * 7
    # The dated item is itself a careers page: nothing independent -> unknown.
    agg = aggregate_dimension(
        _entries([0.9] * 8, dates=dates, sources=["careers_page"] * 8), today=TODAY
    )
    assert agg.status == "unknown" and agg.unknown_reason == "no_recent_independent_item"
    # The dated item is an employee review: known, carried by that one independent item.
    agg = aggregate_dimension(
        _entries([0.9] * 8, dates=dates, sources=["employee_review"] + ["careers_page"] * 7),
        today=TODAY,
    )
    assert agg.status == "known" and agg.recent == 1 and agg.estimate == 0.9
    # An independent item that is recent but on the losing side does not carry the
    # winning side: the supporting items must include one.
    agg = aggregate_dimension(
        _entries([0.1] + [0.9] * 7, dates=[RECENT] * 8,
                 sources=["employee_review"] + ["careers_page"] * 7),
        today=TODAY,
    )
    assert agg.status == "unknown" and agg.unknown_reason == "company_authored_only"


def test_an_employer_reply_is_not_independent_whatever_its_source_type_says():
    assert is_independent("employee_review", "employee review, Cashier")
    assert is_independent("news", None)
    assert not is_independent("employee_review", "Employer response")
    assert not is_independent("employee_review", "response from the company")
    assert not is_independent("news", "CEO, quoted in the piece")
    assert not is_independent("careers_page", "employee review, Cashier")
    assert not is_independent("user_pasted_posting", None)
    # Three reviews where one is the employer's reply: the reply does not count.
    agg = aggregate_dimension(
        _entries([0.9, 0.9, 0.9], sources=["employee_review"] * 3,
                 speakers=["Employer response", "employer reply", "Response from management"]),
        today=TODAY,
    )
    assert agg.status == "unknown" and agg.unknown_reason == "no_recent_independent_item"


def test_a_posting_record_is_aggregated_without_the_independence_rule():
    """A pasted posting is the company's own words by construction; its private record
    is read through them (flagged for Julie with ask 3)."""
    entries = _entries([0.1, 0.1, 0.3], sources=["user_pasted_posting"] * 3)
    assert aggregate_dimension(entries, today=TODAY).status == "unknown"
    agg = aggregate_dimension(entries, today=TODAY, independent_required=False)
    assert agg.status == "known" and agg.estimate == pytest.approx((0.1 + 0.1 + 0.3) / 3)


def test_confidence_rises_with_count_and_falls_with_company_size():
    three = aggregate_dimension(_entries([0.9] * 3), today=TODAY, headcount=50)
    eight = aggregate_dimension(_entries([0.9] * 8), today=TODAY, headcount=50)
    assert three.confidence < eight.confidence
    assert eight.confidence == pytest.approx(1.0 * constants.SIZE_DISCOUNT_BY_BAND[2])
    small = aggregate_dimension(_entries([0.9] * 8), today=TODAY, headcount=5)
    huge = aggregate_dimension(_entries([0.9] * 8), today=TODAY, headcount=50_000)
    assert small.confidence > eight.confidence > huge.confidence
    assert size_discount(None) == constants.SIZE_DISCOUNT_UNKNOWN
    assert [size_discount(h) for h in (5, 50, 500, 5000, 50000)] == [
        constants.SIZE_DISCOUNT_BY_BAND[b] for b in (1, 2, 3, 4, 5)
    ]


def test_every_value_is_inside_the_unit_interval():
    for scores in ([0.1] * 3, [0.9] * 9, [0.1, 0.3, 0.5, 0.7, 0.9], [0.1, 0.1, 0.9, 0.9]):
        agg = aggregate_dimension(_entries(scores), today=TODAY, headcount=None)
        for value in (agg.estimate, agg.low_end, agg.high_end, agg.confidence):
            assert value is None or 0.0 <= value <= 1.0
