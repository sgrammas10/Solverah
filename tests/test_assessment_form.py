"""
test_assessment_form.py -- tests for the web layer's doorway to the person-side instrument.

Every test here is written so that it FAILS if the thing it covers is removed. Per the
operating policy's red rule 7, "I implemented it" is not completion; design rule 3 sat
specified-but-unconsumed for a full session precisely because nothing failed in its absence.

The most important test in this file is test_score_choices_over_whole_form_is_silently_wrong.
It does not test our code -- it pins the bug our code exists to prevent, so that if someone
later "simplifies" submit_form to call score_choices the failure is loud rather than a
plausible float in a database.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# assessment_form puts causal_graph/v1_model on sys.path as an import side effect, so it must
# be imported before present_items / score_person_side. Kept explicit rather than relying on
# alphabetical luck.
import assessment_form as af  # noqa: E402

from present_items import PresentationContractError, build_form  # noqa: E402
from score_person_side import load_items, score_all_dimensions, score_choices  # noqa: E402

SECRET = b"test-secret-not-a-real-one"
ITEMS = _ROOT / "causal_graph" / "v1_model" / "assessment_items_v2.yaml"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", SECRET.decode())


@pytest.fixture
def items_index():
    return load_items(ITEMS)


@pytest.fixture
def raw_items():
    return yaml.safe_load(ITEMS.read_text(encoding="utf-8"))["items"]


def _answer_all(respondent_id, key="A", items_path=ITEMS):
    """Build a form and answer every item with `key`. Returns {token: key}."""
    payload, _ = build_form(respondent_id, items_path)
    return {
        item["token"]: key
        for block in payload["blocks"]
        for item in block["items"]
    }


# ---------------------------------------------------------------------------
# score_all_dimensions -- the arity contract (D-02)
# ---------------------------------------------------------------------------

def test_returns_one_score_per_dimension(items_index, raw_items):
    choices = {item["id"]: "A" for item in raw_items}
    scores = score_all_dimensions(choices, items_index)
    assert set(scores) == {item["dimension"] for item in raw_items}
    assert len(scores) == 6


def test_each_dimension_score_is_that_dimension_s_own_mean(items_index, raw_items):
    """A grouping bug that mixed dimensions would still return six plausible floats.
    This checks the values, not just the shape."""
    choices = {item["id"]: "A" for item in raw_items}
    scores = score_all_dimensions(choices, items_index)

    pole_values = items_index["pole_values"]
    for dim in scores:
        members = [i for i in raw_items if i["dimension"] == dim]
        expected = sum(
            pole_values[next(o for o in i["options"] if o["key"] == "A")["pole"]]
            for i in members
        ) / len(members)
        assert scores[dim] == pytest.approx(expected)


def test_short_dimension_is_refused_not_averaged(items_index, raw_items):
    """D-02: mean_pole over three items is off PERSON_LATTICE. It must not be returned."""
    choices = {item["id"]: "A" for item in raw_items}
    victim = raw_items[0]
    del choices[victim["id"]]

    with pytest.raises(ValueError, match="exactly 4 responses per dimension"):
        score_all_dimensions(choices, items_index)


def test_unknown_item_id_is_refused(items_index, raw_items):
    choices = {item["id"]: "A" for item in raw_items}
    choices["not_an_item"] = "A"
    with pytest.raises(ValueError, match="Unknown item id"):
        score_all_dimensions(choices, items_index)


def test_score_choices_over_whole_form_is_silently_wrong(items_index, raw_items):
    """PINS THE BUG. score_choices over all 24 responses returns a single float in [0,1]
    with no error -- a number that is not any dimension's score. If this test ever fails
    because score_choices grew a guard, delete it; until then it is the reason
    submit_form must never call score_choices."""
    choices = {item["id"]: "A" for item in raw_items}
    lumped, _ = score_choices(choices, items_index)
    assert isinstance(lumped, float)
    assert 0.0 <= lumped <= 1.0

    per_dimension = score_all_dimensions(choices, items_index)
    assert len(per_dimension) == 6
    # The lump is the mean of the six only by coincidence of equal group sizes; the point
    # is that it is one number where six are required, and nothing raised to say so.
    assert not isinstance(lumped, dict)


# ---------------------------------------------------------------------------
# submit_form -- the integration contract
# ---------------------------------------------------------------------------

def test_submit_round_trips_without_a_stored_token_map():
    """DECISION 1: the map is regenerated from (respondent_id, secret), never stored.
    Nothing is carried between these two calls but the respondent id."""
    submitted = _answer_all("respondent-1")
    result = af.submit_form("respondent-1", submitted, ITEMS)
    assert len(result.scores) == 6
    assert all(0.0 <= v <= 1.0 for v in result.scores.values())
    assert len(result.choices) == 24


def test_a_different_respondent_cannot_submit_your_tokens():
    """Tokens are salted per respondent. Replaying one respondent's tokens under another
    id must fail loudly, not resolve to some other item."""
    submitted = _answer_all("respondent-1")
    with pytest.raises(af.AssessmentError, match="unknown item token"):
        af.submit_form("respondent-2", submitted, ITEMS)


def test_scores_are_invariant_to_the_respondent_s_shuffle():
    """Two respondents see different orders (rule 3 + rule 7) but the same answers to the
    same items must produce the same scores. If this fails, the shuffle is leaking into
    scoring, which would make every profile incomparable to every other."""
    a = af.submit_form("respondent-A", _answer_all("respondent-A"), ITEMS)
    b = af.submit_form("respondent-B", _answer_all("respondent-B"), ITEMS)
    assert a.scores == b.scores


def test_two_respondents_actually_get_different_orders():
    """Guards the test above from passing vacuously if the shuffle stopped shuffling."""
    pa, _ = build_form("respondent-A", ITEMS)
    pb, _ = build_form("respondent-B", ITEMS)
    order_a = [i["prompt"] for b in pa["blocks"] for i in b["items"]]
    order_b = [i["prompt"] for b in pb["blocks"] for i in b["items"]]
    assert order_a != order_b
    assert sorted(order_a) == sorted(order_b)


def test_partial_submission_is_refused():
    submitted = _answer_all("respondent-1")
    submitted.pop(next(iter(submitted)))
    with pytest.raises(af.AssessmentError, match="expected 24 responses, got 23"):
        af.submit_form("respondent-1", submitted, ITEMS)


def test_padded_submission_is_refused():
    submitted = _answer_all("respondent-1")
    submitted["deadbeef" * 4] = "A"
    with pytest.raises(af.AssessmentError, match="expected 24 responses, got 25"):
        af.submit_form("respondent-1", submitted, ITEMS)


def test_unknown_option_key_is_refused():
    submitted = _answer_all("respondent-1", key="Z")
    with pytest.raises(af.AssessmentError, match="no option 'Z'"):
        af.submit_form("respondent-1", submitted, ITEMS)


def test_empty_respondent_id_is_refused():
    with pytest.raises(af.AssessmentError, match="non-empty string"):
        af.get_form("")


# ---------------------------------------------------------------------------
# The payload contract -- what may reach the client
# ---------------------------------------------------------------------------

def test_form_payload_carries_blocks_not_dimensions():
    """Design rule 7. A dimension-grouped payload leaks the grouping through its own shape
    regardless of which fields are redacted."""
    payload = af.get_form("respondent-1", ITEMS)
    assert "blocks" in payload
    assert "dimensions" not in payload
    assert len(payload["blocks"]) == 4
    assert all(len(b["items"]) == 6 for b in payload["blocks"])


def test_no_redacted_field_reaches_the_client():
    payload = af.get_form("respondent-1", ITEMS)
    never = set(
        yaml.safe_load(ITEMS.read_text(encoding="utf-8"))["presentation"]["never_display"]
    )
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            seen.update(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    assert not (seen & never), f"leaked: {sorted(seen & never)}"


def test_no_two_adjacent_items_share_a_dimension(raw_items):
    """Rule 7, checked end to end across block seams rather than within a block."""
    dim_by_prompt = {i["prompt"]: i["dimension"] for i in raw_items}
    for rid in ("r-1", "r-2", "r-3", "r-4", "r-5"):
        payload = af.get_form(rid, ITEMS)
        flat = [dim_by_prompt[i["prompt"]] for b in payload["blocks"] for i in b["items"]]
        assert len(flat) == 24
        adjacent = [(a, b) for a, b in zip(flat, flat[1:]) if a == b]
        assert not adjacent, f"{rid}: same-dimension items adjacent: {adjacent}"


# ---------------------------------------------------------------------------
# D-05 -- no default for the token secret
# ---------------------------------------------------------------------------

def test_missing_secret_raises_rather_than_defaulting(monkeypatch):
    """A hardcoded fallback would make tokens forgeable and let a client map a token back
    to an item id, undoing never_display. The absence of a default is the feature."""
    monkeypatch.delenv("SOLVERAH_FORM_TOKEN_SECRET", raising=False)
    with pytest.raises(PresentationContractError, match="no form token secret"):
        af.get_form("respondent-1", ITEMS)


# ---------------------------------------------------------------------------
# scoring_key_version -- S-08
# ---------------------------------------------------------------------------

def test_key_version_names_both_the_item_file_and_the_method():
    """A score is comparable only to scores from the same items scored the same way.
    Either half alone lets one change pass unnoticed."""
    doc = yaml.safe_load(ITEMS.read_text(encoding="utf-8"))
    kv = af.scoring_key_version(ITEMS)
    assert doc["form_version"] in kv
    assert doc["scoring"]["method"] in kv


def test_submission_carries_the_key_version_it_was_scored_under():
    result = af.submit_form("respondent-1", _answer_all("respondent-1"), ITEMS)
    assert result.scoring_key_version == af.scoring_key_version(ITEMS)
    assert result.form_version == yaml.safe_load(
        ITEMS.read_text(encoding="utf-8")
    )["form_version"]


def test_key_version_refuses_an_item_file_missing_its_method(tmp_path):
    """Rather than emitting a half-key that would compare equal to a real one."""
    doc = yaml.safe_load(ITEMS.read_text(encoding="utf-8"))
    del doc["scoring"]["method"]
    stunted = tmp_path / "no_method.yaml"
    stunted.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(af.AssessmentError, match="no form_version and/or scoring.method"):
        af.scoring_key_version(stunted)


def test_raw_choices_are_item_ids_not_tokens():
    """Raw responses are stored so scores can be re-derived after a scoring-key change.
    Stored as tokens they would become unreadable the moment the secret rotated."""
    result = af.submit_form("respondent-1", _answer_all("respondent-1"), ITEMS)
    ids = {i["id"] for i in yaml.safe_load(ITEMS.read_text(encoding="utf-8"))["items"]}
    assert set(result.choices) == ids
