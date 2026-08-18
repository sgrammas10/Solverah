"""
Pytest gate for present_items.py -- the consumer of design rule 3.

check_assessment_items.py verifies the item file DECLARES the presentation contract. These tests
verify the code HONOURS it. Both are needed: a passing structural gate over a contract nothing
reads is exactly the state the repo was in before this module existed.

The uniformity test is the non-obvious one. A shuffle that is deterministic and stable but biased
-- say, one that leaves rung 1 in position 0 more often than chance -- would pass every other test
here while partially re-exposing the ladder. That failure is invisible in any single respondent's
form and only shows up across a population, which is also when it is too late.
"""

from __future__ import annotations

import collections
from pathlib import Path

import pytest
import yaml

from present_items import (
    PresentationContractError,
    build_form,
    presentation_contract,
    resolve_responses,
)
from score_person_side import load_items, score_choices

HERE = Path(__file__).resolve().parent
ITEMS = HERE / "assessment_items_v2.yaml"
SECRET = b"test-secret-not-for-production"
DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]


@pytest.fixture(scope="module")
def doc():
    return yaml.safe_load(ITEMS.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# contract
# ---------------------------------------------------------------------------

def test_contract_is_valid(doc):
    p = presentation_contract(doc)
    assert p["randomize_item_order_within_dimension"] is True
    assert p["order_seed"] == "respondent_id"
    assert p["randomize_option_order"] is False


@pytest.mark.parametrize("mutation, fragment", [
    ({"randomize_item_order_within_dimension": False}, "difficulty order"),
    ({"randomize_option_order": True}, "chosen POLE"),
    ({"order_seed": None}, "reshuffle"),
    ({"never_display": ["difficulty_target", "pole"]}, "sequential"),  # id removed
])
def test_weakened_contract_is_refused(doc, mutation, fragment):
    """Every weakening of the contract must raise. Degrading to a safe default is NOT acceptable:
    a form that silently renders unshuffled produces data that looks fine and is not."""
    d = dict(doc)
    d["presentation"] = {**doc["presentation"], **mutation}
    with pytest.raises(PresentationContractError) as e:
        presentation_contract(d)
    assert fragment in str(e.value)


def test_missing_contract_is_refused(doc):
    d = {k: v for k, v in doc.items() if k != "presentation"}
    with pytest.raises(PresentationContractError):
        presentation_contract(d)


def test_superseded_item_file_cannot_be_served():
    """score_person_side.py has --allow-superseded for historical reproduction. There is
    deliberately no equivalent for serving a live form."""
    v1 = HERE / "assessment_items.yaml"
    if not v1.exists():
        pytest.skip("assessment_items.yaml not present")
    with pytest.raises(PresentationContractError) as e:
        build_form("r1", items_path=v1, secret=SECRET)
    assert "superseded" in str(e.value)


def test_missing_secret_is_refused(monkeypatch):
    monkeypatch.delenv("SOLVERAH_FORM_TOKEN_SECRET", raising=False)
    with pytest.raises(PresentationContractError) as e:
        build_form("r1", items_path=ITEMS)
    assert "forgeable" in str(e.value)


# ---------------------------------------------------------------------------
# shape and redaction
# ---------------------------------------------------------------------------

def test_form_shape():
    form, token_map = build_form("respondent-1", ITEMS, SECRET)
    assert {d["dimension"] for d in form["dimensions"]} == set(DIMS)
    for d in form["dimensions"]:
        assert len(d["items"]) == 4, f"{d['dimension']} must have exactly 4 items (PERSON_LATTICE)"
        for it in d["items"]:
            assert set(it) == {"token", "prompt", "options"}
            assert [o["key"] for o in it["options"]] == ["A", "B"]
    assert len(token_map) == 24
    assert len(set(token_map.values())) == 24


def test_no_never_display_field_reaches_the_client(doc):
    """The deep scan in build_form should make this impossible; assert it independently anyway,
    including that no raw item id appears anywhere in the serialised payload."""
    import json
    form, _ = build_form("respondent-1", ITEMS, SECRET)
    blob = json.dumps(form)
    for field in doc["presentation"]["never_display"]:
        assert f'"{field}"' not in blob, f"{field} leaked into the payload"
    for item in doc["items"]:
        assert item["id"] not in blob, f"item id {item['id']} leaked into the payload"


def test_option_order_is_preserved():
    """randomize_option_order is false by design. Verify the module honours that rather than
    quietly shuffling options too -- probe files key their frozen choices by letter."""
    form, token_map = build_form("respondent-1", ITEMS, SECRET)
    src = {i["id"]: i for i in yaml.safe_load(ITEMS.read_text(encoding="utf-8"))["items"]}
    by_token = {t: src[i] for t, i in token_map.items()}
    for d in form["dimensions"]:
        for it in d["items"]:
            original = by_token[it["token"]]["options"]
            assert [o["key"] for o in it["options"]] == [o["key"] for o in original]
            assert [o["text"] for o in it["options"]] == [o["text"] for o in original]


# ---------------------------------------------------------------------------
# determinism and stability -- the resumed-session guarantee
# ---------------------------------------------------------------------------

def test_same_respondent_same_order():
    a, _ = build_form("respondent-1", ITEMS, SECRET)
    b, _ = build_form("respondent-1", ITEMS, SECRET)
    assert a == b


def test_tokens_are_stable_across_calls():
    """A resumed session must regenerate identical tokens even if token_map was never persisted."""
    _, m1 = build_form("respondent-1", ITEMS, SECRET)
    _, m2 = build_form("respondent-1", ITEMS, SECRET)
    assert m1 == m2


def test_tokens_differ_per_respondent():
    """Otherwise a token is a global item identifier and two respondents comparing forms recover
    the mapping, undoing never_display."""
    _, m1 = build_form("respondent-1", ITEMS, SECRET)
    _, m2 = build_form("respondent-2", ITEMS, SECRET)
    assert not (set(m1) & set(m2))


def test_order_differs_across_respondents():
    """Not a strict requirement per respondent, but if orders were identical for everyone the
    shuffle would be decorative -- one respondent posting their form would expose the ladder."""
    orders = set()
    for i in range(50):
        form, tokens = build_form(f"r{i}", ITEMS, SECRET)
        auto = next(d for d in form["dimensions"] if d["dimension"] == "autonomy")
        orders.add(tuple(tokens[it["token"]] for it in auto["items"]))
    assert len(orders) > 10, f"only {len(orders)} distinct autonomy orders across 50 respondents"


def test_dimensions_shuffle_independently():
    """A single shared permutation across all six dimensions would let a respondent who works out
    one dimension's order read off the other five."""
    perms = collections.defaultdict(set)
    for i in range(50):
        form, tokens = build_form(f"r{i}", ITEMS, SECRET)
        for d in form["dimensions"]:
            ids = [tokens[it["token"]] for it in d["items"]]
            perms[d["dimension"]].add(tuple(int(x[2]) for x in ids))  # rung number from id
    signatures = [frozenset(v) for v in perms.values()]
    assert len(set(signatures)) > 1, "all dimensions produced the same permutation set"


# ---------------------------------------------------------------------------
# uniformity -- the test that catches a deterministic-but-biased shuffle
# ---------------------------------------------------------------------------

def test_shuffle_is_approximately_uniform():
    """Each rung should land in each of the four display positions about 1/4 of the time. A biased
    shuffle passes every other test here while partially re-exposing the ladder -- and the bias is
    invisible in any single respondent's form."""
    n = 2000
    counts = collections.Counter()
    for i in range(n):
        form, tokens = build_form(f"resp-{i}", ITEMS, SECRET)
        auto = next(d for d in form["dimensions"] if d["dimension"] == "autonomy")
        for pos, it in enumerate(auto["items"]):
            counts[(tokens[it["token"]], pos)] += 1

    expected = n / 4
    tol = 4 * (expected * 0.25 * 0.75) ** 0.5  # ~4 sigma on a binomial(n, 1/4)
    worst = max(abs(c - expected) for c in counts.values())
    assert len(counts) == 16, "some (item, position) combination never occurred"
    assert worst < tol, f"worst deviation {worst:.1f} exceeds {tol:.1f} -- shuffle is biased"


# ---------------------------------------------------------------------------
# scoring is order-invariant -- the property the whole design leans on
# ---------------------------------------------------------------------------

def test_scoring_is_order_invariant():
    """mean_pole is order-invariant by construction, which is WHY shuffling is safe. Assert it
    rather than assume it: if a future scoring change made order matter, the shuffle would start
    silently changing scores instead of erroring."""
    idx = load_items(ITEMS)
    src = yaml.safe_load(ITEMS.read_text(encoding="utf-8"))
    by_dim = collections.defaultdict(list)
    for it in src["items"]:
        by_dim[it["dimension"]].append(it)

    for dim, its in by_dim.items():
        for k in range(5):  # each rung of the Guttman prefix ladder
            canonical = {
                it["id"]: next(o for o in it["options"]
                               if o["pole"] == ("high" if j < k else "low"))["key"]
                for j, it in enumerate(its)
            }
            base, _ = score_choices(canonical, idx)
            for i in range(20):
                form, tokens = build_form(f"r{i}", ITEMS, SECRET)
                d = next(x for x in form["dimensions"] if x["dimension"] == dim)
                shuffled = {tokens[it["token"]]: canonical[tokens[it["token"]]]
                            for it in d["items"]}
                got, _ = score_choices(shuffled, idx)
                assert got == base == k / 4, f"{dim} rung {k}: {got} != {base}"


# ---------------------------------------------------------------------------
# round trip
# ---------------------------------------------------------------------------

def test_resolve_responses_round_trip():
    form, token_map = build_form("respondent-1", ITEMS, SECRET)
    submitted = {}
    for d in form["dimensions"]:
        for pos, it in enumerate(d["items"]):
            submitted[it["token"]] = "A" if pos % 2 == 0 else "B"
    choices = resolve_responses(token_map, submitted)
    assert len(choices) == 24
    assert set(choices) == {i["id"] for i in
                            yaml.safe_load(ITEMS.read_text(encoding="utf-8"))["items"]}
    idx = load_items(ITEMS)
    score, _ = score_choices(choices, idx)
    assert 0.0 <= score <= 1.0


def test_unknown_token_is_rejected_not_dropped():
    """A silently dropped response changes mean_pole's denominator and moves the score with no
    error surfacing -- the same class of failure as a partial submission scoring as extreme."""
    _, token_map = build_form("respondent-1", ITEMS, SECRET)
    with pytest.raises(ValueError) as e:
        resolve_responses(token_map, {"deadbeef" * 4: "A"})
    assert "denominator" in str(e.value)


def test_straight_lining_by_position_still_scores_midpoint():
    """Design rule 2's guarantee must survive the shuffle: always-A and always-B both yield 0.50
    on every dimension, so a positional straight-liner lands on the midpoint rather than an
    extreme. The shuffle changes which item is in which slot, not the 2/2 key balance."""
    idx = load_items(ITEMS)
    for rid in ["r-a", "r-b", "r-c"]:
        form, token_map = build_form(rid, ITEMS, SECRET)
        for letter in ("A", "B"):
            for d in form["dimensions"]:
                choices = {token_map[it["token"]]: letter for it in d["items"]}
                score, _ = score_choices(choices, idx)
                assert score == 0.5, f"{rid} {d['dimension']} always-{letter} -> {score}"
