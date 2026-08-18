"""
Pytest gate for present_items.py -- the consumer of design rules 3 and 7.

check_assessment_items.py verifies the item file DECLARES the presentation contract. These
tests verify the code HONOURS it. Both are needed: a passing structural gate over a contract
nothing reads is exactly the state the repo was in before present_items.py existed.

Two tests here are non-obvious and worth keeping even if they look redundant:

  test_shuffle_is_approximately_uniform -- a shuffle that is deterministic and stable but
  BIASED (leaving rung 1 in position 0 more often than chance) would pass every other test
  while partially re-exposing the ladder. That failure is invisible in any single respondent's
  form and only shows up across a population, which is also when it is too late to fix.

  test_no_two_adjacent_items_share_a_dimension -- rule 7's actual guarantee. Per-block
  correctness does not imply it: a block ending on `pace` followed by a block starting on
  `pace` puts two same-dimension items next to each other across the seam, which is precisely
  the adjacency the interleave exists to prevent.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest
import yaml

from present_items import (
    ITEMS_PER_DIMENSION,
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


@pytest.fixture(scope="module")
def dim_of(doc):
    return {i["id"]: i["dimension"] for i in doc["items"]}


def flat(form):
    """Every item in display order, across block boundaries."""
    return [it for b in form["blocks"] for it in b["items"]]


# ---------------------------------------------------------------------------
# contract
# ---------------------------------------------------------------------------

def test_contract_is_valid(doc):
    p = presentation_contract(doc)
    assert p["randomize_item_order_within_dimension"] is True
    assert p["interleave_dimensions"] is True
    assert p["block_count"] == ITEMS_PER_DIMENSION
    assert p["order_seed"] == "respondent_id"
    assert p["randomize_option_order"] is False


@pytest.mark.parametrize("mutation, fragment", [
    ({"randomize_item_order_within_dimension": False}, "difficulty order"),
    ({"randomize_option_order": True}, "chosen POLE"),
    ({"order_seed": None}, "reshuffle"),
    ({"never_display": ["dimension", "difficulty_target", "pole"]}, "sequential"),  # id gone
    ({"never_display": ["id", "difficulty_target", "pole"]}, "never_display"),      # dimension gone
    ({"interleave_dimensions": False}, "self-presentation"),
    ({"block_count": 6}, "block count and the rung count"),
    ({"block_count": None}, "block count and the rung count"),
])
def test_weakened_contract_is_refused(doc, mutation, fragment):
    """Every weakening must raise. Degrading to a safe default is NOT acceptable: a form that
    silently renders grouped or unshuffled produces data that looks fine and is not."""
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
    assert "dimensions" not in form, "payload must not be dimension-grouped (design rule 7)"
    assert len(form["blocks"]) == ITEMS_PER_DIMENSION
    for b in form["blocks"]:
        assert len(b["items"]) == len(DIMS)
        for it in b["items"]:
            assert set(it) == {"token", "prompt", "options"}
            assert [o["key"] for o in it["options"]] == ["A", "B"]
    assert len(flat(form)) == 24
    assert len(token_map) == 24
    assert len(set(token_map.values())) == 24


def test_no_never_display_field_reaches_the_client(doc):
    """The deep scan in build_form should make this impossible; assert it independently anyway,
    including that no raw item id or dimension name appears anywhere in the payload."""
    form, _ = build_form("respondent-1", ITEMS, SECRET)
    blob = json.dumps(form)
    for field in doc["presentation"]["never_display"]:
        assert f'"{field}"' not in blob, f"{field} leaked into the payload"
    for item in doc["items"]:
        assert item["id"] not in blob, f"item id {item['id']} leaked into the payload"
    # Deliberately NOT asserting that dimension NAMES are absent from the blob. They are
    # ordinary English words and legitimately occur in item text -- de4v2's prompt contains
    # "the decisions that frustrated you". The requirement is that the `dimension` FIELD is
    # absent, which the never_display loop above already covers. An over-strict version of this
    # test failed on correct output, which is its own kind of defect.


def test_option_order_is_preserved(doc):
    """randomize_option_order is false by design. Verify the module honours that rather than
    quietly shuffling options too -- probe files key their frozen choices by letter."""
    form, token_map = build_form("respondent-1", ITEMS, SECRET)
    src = {i["id"]: i for i in doc["items"]}
    for it in flat(form):
        original = src[token_map[it["token"]]]["options"]
        assert [o["key"] for o in it["options"]] == [o["key"] for o in original]
        assert [o["text"] for o in it["options"]] == [o["text"] for o in original]


# ---------------------------------------------------------------------------
# design rule 7 -- interleaving
# ---------------------------------------------------------------------------

def test_each_block_holds_exactly_one_item_per_dimension(dim_of):
    for i in range(30):
        form, token_map = build_form(f"r{i}", ITEMS, SECRET)
        for b in form["blocks"]:
            dims = [dim_of[token_map[it["token"]]] for it in b["items"]]
            assert sorted(dims) == sorted(DIMS), f"block {b['block']} dims: {dims}"


def test_no_two_adjacent_items_share_a_dimension(dim_of):
    """Rule 7's actual guarantee, checked across block seams -- per-block correctness does not
    imply it."""
    for i in range(60):
        form, token_map = build_form(f"r{i}", ITEMS, SECRET)
        seq = [dim_of[token_map[it["token"]]] for it in flat(form)]
        adjacent = [(a, b) for a, b in zip(seq, seq[1:]) if a == b]
        assert not adjacent, f"r{i}: same-dimension items adjacent: {adjacent}"


def test_rung_order_within_a_dimension_is_still_hidden(dim_of, doc):
    """Rule 7 must not silently undo rule 3. A dimension's four rungs should not appear in
    ascending difficulty across the blocks in any systematic way."""
    rung = {i["id"]: i["difficulty_target"] for i in doc["items"]}
    ascending = 0
    n = 300
    for i in range(n):
        form, token_map = build_form(f"r{i}", ITEMS, SECRET)
        by_dim = collections.defaultdict(list)
        for b in form["blocks"]:
            for it in b["items"]:
                iid = token_map[it["token"]]
                by_dim[dim_of[iid]].append(rung[iid])
        for order in by_dim.values():
            if order == sorted(order):
                ascending += 1
    # 6 dimensions x n respondents, each 1/24 chance of landing in ascending order by chance
    expected = 6 * n / 24
    assert ascending < expected * 2, (
        f"{ascending} ascending orders vs ~{expected:.0f} expected by chance -- rule 3's "
        f"within-dimension shuffle may have been weakened by the interleave"
    )


def test_dimension_sequence_varies_between_blocks(dim_of):
    """If every block presented dimensions in the same order, the grouping would be trivially
    recoverable by counting positions."""
    identical = 0
    for i in range(50):
        form, token_map = build_form(f"r{i}", ITEMS, SECRET)
        seqs = [tuple(dim_of[token_map[it["token"]]] for it in b["items"])
                for b in form["blocks"]]
        if len(set(seqs)) == 1:
            identical += 1
    assert identical <= 1, f"{identical}/50 respondents saw the same dimension order in all blocks"


# ---------------------------------------------------------------------------
# determinism and stability -- the resumed-session guarantee
# ---------------------------------------------------------------------------

def test_same_respondent_same_order():
    assert build_form("respondent-1", ITEMS, SECRET) == build_form("respondent-1", ITEMS, SECRET)


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


def test_order_differs_across_respondents(dim_of):
    """If the order were identical for everyone, the shuffle would be decorative -- one
    respondent posting their form would expose the structure for all of them."""
    orders = {tuple(token_map[it["token"]] for it in flat(form))
              for form, token_map in (build_form(f"r{i}", ITEMS, SECRET) for i in range(50))}
    assert len(orders) > 40, f"only {len(orders)} distinct orders across 50 respondents"


def test_dimensions_shuffle_independently(dim_of, doc):
    """A single shared permutation across all six dimensions would let a respondent who works
    out one dimension's rung order read off the other five."""
    rung = {i["id"]: i["difficulty_target"] for i in doc["items"]}
    perms = collections.defaultdict(set)
    for i in range(50):
        form, token_map = build_form(f"r{i}", ITEMS, SECRET)
        seen = collections.defaultdict(list)
        for b in form["blocks"]:
            for it in b["items"]:
                iid = token_map[it["token"]]
                seen[dim_of[iid]].append(rung[iid])
        for d, order in seen.items():
            perms[d].add(tuple(order))
    assert len({frozenset(v) for v in perms.values()}) > 1, \
        "all dimensions produced the same permutation set"


# ---------------------------------------------------------------------------
# uniformity -- catches a deterministic-but-biased shuffle
# ---------------------------------------------------------------------------

def test_shuffle_is_approximately_uniform(dim_of, doc):
    """Each of autonomy's four rungs should land in each block about 1/4 of the time."""
    rung = {i["id"]: i["difficulty_target"] for i in doc["items"]}
    n = 2000
    counts = collections.Counter()
    for i in range(n):
        form, token_map = build_form(f"resp-{i}", ITEMS, SECRET)
        for b in form["blocks"]:
            for it in b["items"]:
                iid = token_map[it["token"]]
                if dim_of[iid] == "autonomy":
                    counts[(rung[iid], b["block"])] += 1

    expected = n / 4
    tol = 4 * (expected * 0.25 * 0.75) ** 0.5  # ~4 sigma on binomial(n, 1/4)
    assert len(counts) == 16, "some (rung, block) combination never occurred"
    worst = max(abs(c - expected) for c in counts.values())
    assert worst < tol, f"worst deviation {worst:.1f} exceeds {tol:.1f} -- shuffle is biased"


# ---------------------------------------------------------------------------
# scoring is order-invariant -- the property the whole design leans on
# ---------------------------------------------------------------------------

def test_scoring_is_order_invariant(doc):
    """mean_pole is order-invariant by construction, which is WHY shuffling and interleaving are
    safe. Assert it rather than assume it: if a future scoring change made order matter, the
    shuffle would start silently changing scores instead of erroring."""
    idx = load_items(ITEMS)
    by_dim = collections.defaultdict(list)
    for it in doc["items"]:
        by_dim[it["dimension"]].append(it)

    for dim, its in by_dim.items():
        for k in range(5):  # each rung of the Guttman prefix ladder
            canonical = {
                it["id"]: next(o for o in it["options"]
                               if o["pole"] == ("high" if j < k else "low"))["key"]
                for j, it in enumerate(its)
            }
            base, _ = score_choices(canonical, idx)
            assert base == k / 4
            for i in range(20):
                form, token_map = build_form(f"r{i}", ITEMS, SECRET)
                shuffled = {}
                for it in flat(form):
                    iid = token_map[it["token"]]
                    if iid in canonical:
                        shuffled[iid] = canonical[iid]
                assert score_choices(shuffled, idx)[0] == base, f"{dim} rung {k}"


# ---------------------------------------------------------------------------
# round trip
# ---------------------------------------------------------------------------

def test_resolve_responses_round_trip(doc):
    form, token_map = build_form("respondent-1", ITEMS, SECRET)
    submitted = {it["token"]: ("A" if pos % 2 == 0 else "B")
                 for pos, it in enumerate(flat(form))}
    choices = resolve_responses(token_map, submitted)
    assert len(choices) == 24
    assert set(choices) == {i["id"] for i in doc["items"]}
    assert 0.0 <= score_choices(choices, load_items(ITEMS))[0] <= 1.0


def test_unknown_token_is_rejected_not_dropped():
    """A silently dropped response changes mean_pole's denominator and moves the score with no
    error surfacing -- the same class of failure as a partial submission scoring as extreme."""
    _, token_map = build_form("respondent-1", ITEMS, SECRET)
    with pytest.raises(ValueError) as e:
        resolve_responses(token_map, {"deadbeef" * 4: "A"})
    assert "denominator" in str(e.value)


def test_straight_lining_by_position_still_scores_midpoint(dim_of):
    """Design rule 2's guarantee must survive both the shuffle and the interleave: always-A and
    always-B yield 0.50 on every dimension, so a positional straight-liner lands on the midpoint
    rather than an extreme."""
    idx = load_items(ITEMS)
    for rid in ["r-a", "r-b", "r-c"]:
        form, token_map = build_form(rid, ITEMS, SECRET)
        for letter in ("A", "B"):
            per_dim = collections.defaultdict(dict)
            for it in flat(form):
                iid = token_map[it["token"]]
                per_dim[dim_of[iid]][iid] = letter
            for dim, choices in per_dim.items():
                assert score_choices(choices, idx)[0] == 0.5, f"{rid} {dim} always-{letter}"
