"""Tests for the D-17 confidence measure (S-31): e = Guttman error count.

What is load-bearing here:

1. e ITSELF -- hand-verified values for known patterns, including the pair that justifies
   the whole measure: {1,1,0,0} and {0,1,0,1} both mean_pole to 0.5, but the first is the
   canonical honest 0.5 (e=0) and the second is indistinguishable from coin-flipping (e=2).

2. RUNG ORDER COMES FROM difficulty_target, NOT item id. In the real item file the two
   orders coincide (au1v2 is also the easiest rung), so a sort-by-id bug would be invisible
   against real items -- the S-40 lesson. The synthetic item set below has id order
   DISAGREE with difficulty order, so that mutation fails here and nowhere else.

3. THE PIPELINE: submit_form grades five dimensions and leaves feedback None (D-17(a));
   persist_submission stores exactly what the submission carries and a retake REFRESHES
   confidence; get_dimension_confidences is the sanctioned read. Persistence tests go
   through persist_submission / get_dimension_confidences only, keeping this file off the
   test_employer_visibility.py allowlist by construction.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import assessment_form as af  # noqa: E402  (puts causal_graph/v1_model on sys.path)
from present_items import build_form  # noqa: E402
from score_person_side import (  # noqa: E402
    confidence_from_error,
    error_counts_all_dimensions,
    guttman_error_count,
    load_items,
    score_all_dimensions,
)

ITEMS = _ROOT / "causal_graph" / "v1_model" / "assessment_items_v2.yaml"
DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


# ---------------------------------------------------------------------------
# 1. e itself
# ---------------------------------------------------------------------------

def test_error_count_hand_verified_values():
    # The five valid prefixes are all e=0.
    for prefix in ((0, 0, 0, 0), (1, 0, 0, 0), (1, 1, 0, 0), (1, 1, 1, 0), (1, 1, 1, 1)):
        assert guttman_error_count(prefix) == 0
    # One flip away.
    assert guttman_error_count((0, 1, 0, 0)) == 1  # -> 0000 or 1100
    assert guttman_error_count((1, 0, 1, 1)) == 1  # -> 1111
    assert guttman_error_count((0, 0, 0, 1)) == 1  # -> 0000
    assert guttman_error_count((1, 1, 0, 1)) == 1  # the pre-registered rule-6 cell (S-18)
    # The maximally scrambled patterns (and one that only looks scrambled).
    assert guttman_error_count((0, 1, 0, 1)) == 2
    assert guttman_error_count((0, 0, 1, 1)) == 2
    assert guttman_error_count((1, 0, 0, 1)) == 1  # one flip from 1000


def test_error_count_refuses_wrong_shape():
    with pytest.raises(ValueError):
        guttman_error_count((1, 1, 0))  # three items is not the instrument
    with pytest.raises(ValueError):
        guttman_error_count((1, 1, 0, 2))  # not binary


def test_confidence_mapping_is_bijective_and_bounded():
    assert confidence_from_error(0) == 1.0
    assert confidence_from_error(1) == 0.5
    assert confidence_from_error(2) == 0.0
    with pytest.raises(ValueError):
        confidence_from_error(3)
    with pytest.raises(ValueError):
        confidence_from_error(-1)


def test_the_d17_justification_pair():
    """{1,1,0,0} and {0,1,0,1} both mean_pole to 0.5; e tells them apart. This is the
    sentence D-17 rests on, executed against the real item file."""
    items_index = load_items(ITEMS)
    by_id = items_index["by_id"]

    def choices_for(dim, bits_in_rung_order):
        items = sorted(
            (i for i in by_id.values() if i["dimension"] == dim),
            key=lambda i: i["difficulty_target"],
        )
        out = {}
        for item, bit in zip(items, bits_in_rung_order):
            pole = "high" if bit else "low"
            out[item["id"]] = next(o["key"] for o in item["options"] if o["pole"] == pole)
        return out

    honest_mid = choices_for("autonomy", (1, 1, 0, 0))
    scrambled = choices_for("autonomy", (0, 1, 0, 1))

    assert score_all_dimensions(honest_mid, items_index)["autonomy"] == 0.5
    assert score_all_dimensions(scrambled, items_index)["autonomy"] == 0.5
    assert error_counts_all_dimensions(honest_mid, items_index)["autonomy"] == 0
    assert error_counts_all_dimensions(scrambled, items_index)["autonomy"] == 2


# ---------------------------------------------------------------------------
# 2. Rung order is difficulty_target, not id order
# ---------------------------------------------------------------------------

def _synthetic_index(difficulties, dim="syn"):
    """Four items whose ID order (s1..s4) deliberately disagrees with difficulty order."""
    items = []
    for n, difficulty in enumerate(difficulties, start=1):
        item = {
            "id": f"s{n}",
            "dimension": dim,
            "options": [
                {"key": "A", "pole": "high"},
                {"key": "B", "pole": "low"},
            ],
        }
        if difficulty is not None:
            item["difficulty_target"] = difficulty
        items.append(item)
    return {
        "pole_values": {"low": 0.0, "high": 1.0},
        "by_id": {i["id"]: i for i in items},
        "form_version": "synthetic",
        "status": "active",
    }


def test_rung_order_is_difficulty_not_id():
    # id order s1,s2,s3,s4 has difficulties 0.9,0.3,0.7,0.5 -- rung order is s2,s4,s3,s1.
    idx = _synthetic_index([0.9, 0.3, 0.7, 0.5])
    # High on the two EASIEST rungs (s2: 0.3, s4: 0.5), low on the harder two.
    choices = {"s1": "B", "s2": "A", "s3": "B", "s4": "A"}
    # In rung order that is (1,1,0,0): a valid prefix, e=0.
    # In id order it reads (0,1,0,1): e=2. A sort-by-id bug fails here.
    assert error_counts_all_dimensions(choices, idx)["syn"] == 0


def test_ambiguous_rung_order_refuses():
    dup = _synthetic_index([0.3, 0.5, 0.5, 0.9])  # duplicated difficulty: order undefined
    choices = {"s1": "A", "s2": "A", "s3": "B", "s4": "B"}
    with pytest.raises(ValueError):
        error_counts_all_dimensions(choices, dup)

    missing = _synthetic_index([0.3, None, 0.7, 0.9])  # absent difficulty: order undefined
    with pytest.raises(ValueError):
        error_counts_all_dimensions(choices, missing)


def test_arity_contract_matches_scorer():
    idx = _synthetic_index([0.3, 0.5, 0.7, 0.9])
    with pytest.raises(ValueError):
        error_counts_all_dimensions({"s1": "A", "s2": "A", "s3": "A"}, idx)  # 3 of 4


# ---------------------------------------------------------------------------
# 3. The pipeline: submit -> persist -> read
# ---------------------------------------------------------------------------

def _answer_all(respondent_id, key="A"):
    payload, _ = build_form(respondent_id, ITEMS)
    return {
        item["token"]: key
        for block in payload["blocks"]
        for item in block["items"]
    }


def test_submit_form_grades_five_and_leaves_feedback_null():
    result = af.submit_form("respondent-c1", _answer_all("respondent-c1"))
    assert set(result.confidences) == set(DIMS)
    assert result.confidences["feedback"] is None  # D-17(a), pending S-18
    for dim in DIMS:
        if dim == "feedback":
            continue
        assert result.confidences[dim] in (0.0, 0.5, 1.0), dim


def test_persisted_confidence_roundtrips_and_retake_refreshes(client):
    from app import app
    from assessment_form import scoring_key_version, ScoredSubmission
    from assessment_store import get_dimension_confidences, persist_submission
    from model import db

    def submission(conf_value):
        choices = {f"{d[:2]}{r}v2": "A" for d in DIMS for r in range(1, 5)}
        return ScoredSubmission(
            form_version="v2-2026-08-18",
            scoring_key_version=scoring_key_version(),
            scores={d: 0.5 for d in DIMS},
            choices=choices,
            confidences={d: (None if d == "feedback" else conf_value) for d in DIMS},
        )

    with app.app_context():
        assert get_dimension_confidences(7) is None  # no profile yet

        persist_submission(db, 7, submission(1.0))
        db.session.commit()
        stored = get_dimension_confidences(7)
        assert stored["feedback"] is None
        assert all(stored[d] == 1.0 for d in DIMS if d != "feedback")

        # A retake under the same key must refresh confidence -- a new sitting's score
        # carrying the old sitting's e would attribute one pattern to another submission.
        persist_submission(db, 7, submission(0.5))
        db.session.commit()
        stored = get_dimension_confidences(7)
        assert all(stored[d] == 0.5 for d in DIMS if d != "feedback")
        assert stored["feedback"] is None
