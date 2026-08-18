"""
present_items.py -- the consumer of the `presentation:` contract in assessment_items_v2.yaml.

Design rule 3 has, until now, been a SPECIFICATION rather than a PROTECTION: it is declared in
the item YAML and enforced *against* the YAML by check_assessment_items.py, but nothing in the
repo read it. This module is what reads it. Nothing else should build a person-side form.

WHY THIS IS LAUNCH-BLOCKING, not a UI nicety
--------------------------------------------
A graduated-difficulty ladder displayed in difficulty order is transparent. The four rungs read
visibly as "a little / somewhat / quite / extremely", so a respondent who wants to look decisive
does not have to guess which answers do it -- they endorse further down the list. The resulting
profile is perfectly Guttman-consistent, so the planned confidence measure (internal consistency)
returns HIGH on a fabrication.

The funnel answer of 2026-08-18 makes this worse, not better. A signed-up user self-profiling for
matching does not soften the way a candidate mid-application would -- they ASPIRE, answering as
the person who gets matched to the job they want. That is exactly the behaviour rule 3 exists to
defeat. Shipping the ladder in difficulty order is strictly worse than shipping v1, which had no
visible gradient to climb.

THREE DESIGN DECISIONS, each of which is a correctness requirement
------------------------------------------------------------------
1. ORDERING IS SERVER-AUTHORITATIVE. The client never shuffles. If both a Python scorer and a
   TypeScript frontend computed the order independently they would have to agree bit-for-bit
   forever, across two languages' PRNGs -- a divergence here is silent and corrupts a resumed
   session's ordering rather than erroring. So the server emits an already-ordered payload and
   the client renders it verbatim. There is deliberately no TS shuffle helper to keep in sync.

2. ITEMS ARE ADDRESSED BY OPAQUE PER-RESPONDENT TOKENS, not by item id. This closes a gap in the
   rule 3 contract itself: `never_display` lists `id`, precisely because ids are sequential
   within a dimension (au1v2..au4v2) and surfacing them re-leaks the order the shuffle just hid.
   But a form must round-trip an answer to the item it answers. If the client posts back
   {"au3v2": "A"} then the id was in the DOM and the shuffle bought nothing. Tokens are an
   HMAC of (respondent_id, item_id) under a server secret: stable across a resumed session,
   unordered, and not invertible by the client.

3. OPTION ORDER IS NOT RANDOMIZED, and this module refuses to do it. Design rule 2's 2/2 key
   balance already neutralizes positional bias deterministically rather than in expectation;
   every probe file keys its frozen choices by letter; and a stored "chose A" becomes ambiguous
   unless the shuffle is persisted alongside it. If `randomize_option_order` is ever flipped to
   true, responses must be stored as the chosen POLE rather than the letter and every probe file
   reworked -- so this module raises rather than silently honouring the flag.

Scoring is unaffected by any of this: mean_pole is order-invariant. That invariance is asserted
in test_present_items.py rather than assumed.

Usage:
    from present_items import build_form, resolve_responses

    form, token_map = build_form("respondent-abc", secret=SECRET)
    ...                                    # render form; persist token_map with the session
    choices = resolve_responses(token_map, {"9f3c...": "A", ...})   # -> {"au3v2": "A", ...}
"""

from __future__ import annotations

import hashlib
import hmac
from functools import lru_cache
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_ITEMS_PATH = Path(__file__).resolve().parent / "assessment_items_v2.yaml"

# Fields that must never reach the respondent's screen, per the YAML's presentation block. The
# list is READ FROM THE YAML rather than hardcoded here -- the contract lives in one place, and a
# field added there is redacted here without a code change. These are the minimum the contract is
# required to contain; check_assessment_items.py fails the file if any is missing.
#   `dimension` joined this list with design rule 7. Before interleaving, the grouping already
#   revealed it; now that the grouping is gone, leaving the field on each item would hand back
#   exactly what the interleave removes.
REQUIRED_REDACTIONS = frozenset({"id", "dimension", "difficulty_target", "pole"})

ITEMS_PER_DIMENSION = 4  # load-bearing: mean_pole over 4 reproduces build_model.PERSON_LATTICE

_TOKEN_BYTES = 16  # 128 bits; collision-free across any realistic item count


class PresentationContractError(RuntimeError):
    """The item file's presentation block is missing, weakened, or self-inconsistent."""


@lru_cache(maxsize=8)
def _parse(path_str: str, mtime_ns: int, size: int) -> dict:
    """Parsed-YAML cache keyed on (path, mtime, size). build_form is called once per respondent
    per page load, and reparsing a 30KB YAML each time is pure waste -- the uniformity test alone
    calls it 2000 times. Keying on mtime rather than path alone means an edited item file is
    picked up without a restart, which matters because a stale cached copy of a RETIRED file
    would keep being served."""
    return yaml.safe_load(Path(path_str).read_text(encoding="utf-8"))


def _load(items_path: Path) -> dict:
    st = items_path.stat()
    doc = _parse(str(items_path), st.st_mtime_ns, st.st_size)
    status = doc.get("status")
    if status == "superseded":
        raise PresentationContractError(
            f"REFUSED: {items_path} is marked status: superseded and must not be presented to a "
            f"respondent. Historical reproduction is score_person_side.py --allow-superseded; "
            f"there is deliberately no equivalent escape hatch for serving a live form."
        )
    if status != "active":
        raise PresentationContractError(
            f"REFUSED: {items_path} has status: {status!r}. Only an 'active' item file may be "
            f"served to a respondent -- a proposal must be ratified first."
        )
    return doc


def presentation_contract(doc: dict) -> dict:
    """Read and validate the presentation block. Raises rather than degrading to a safe default:
    a form that silently renders unshuffled is the exact failure this module exists to prevent,
    and it is invisible in the resulting data."""
    p = doc.get("presentation")
    if not isinstance(p, dict):
        raise PresentationContractError(
            "no `presentation:` block -- refusing to guess. Rule 3 is a correctness requirement."
        )
    if p.get("randomize_item_order_within_dimension") is not True:
        raise PresentationContractError(
            "randomize_item_order_within_dimension is not true. Serving the ladder in difficulty "
            "order lets a self-presenting respondent walk down it and produce a perfectly "
            "Guttman-consistent fake that the confidence measure scores HIGH."
        )
    if not p.get("order_seed"):
        raise PresentationContractError(
            "no order_seed declared -- a resumed session would reshuffle, and a respondent who "
            "saw two different orders can infer the grouping."
        )
    if p.get("order_seed") != "respondent_id":
        raise PresentationContractError(
            f"order_seed is {p['order_seed']!r}; this module only implements 'respondent_id'. "
            f"Anything session-scoped reshuffles on resume."
        )
    if p.get("randomize_option_order") is True:
        raise PresentationContractError(
            "randomize_option_order is true. This module refuses: responses would have to be "
            "stored as the chosen POLE rather than the letter, and every vignette probe file's "
            "person_item_choices would be invalid. See design rule 3 in the item YAML."
        )
    # Design rule 7. Interleaving is a correctness requirement for the same reason rule 3 is:
    # shown in dimension groups, a respondent can see which four items measure one thing and
    # has an obvious pull toward answering them coherently -- which inflates the
    # internal-consistency confidence measure on a LESS accurate profile.
    if p.get("interleave_dimensions") is not True:
        raise PresentationContractError(
            "interleave_dimensions is not true. Serving items in dimension groups lets a "
            "respondent see which four measure the same thing, and answering that group "
            "'consistently' as self-presentation inflates the confidence measure. Rule 3's "
            "within-dimension shuffle does not close this -- it leaves the block intact."
        )
    blocks = p.get("block_count")
    if not isinstance(blocks, int) or blocks != ITEMS_PER_DIMENSION:
        raise PresentationContractError(
            f"block_count is {blocks!r}; it must equal {ITEMS_PER_DIMENSION}, the number of "
            f"items per dimension. Each block holds exactly one item from every dimension, so "
            f"the block count and the rung count are the same number by construction."
        )

    never = set(p.get("never_display") or [])
    missing = REQUIRED_REDACTIONS - never
    if missing:
        raise PresentationContractError(
            f"never_display is missing {sorted(missing)}. 'id' in particular is load-bearing: "
            f"ids are sequential within a dimension, so surfacing them re-leaks the rung order "
            f"the shuffle just hid."
        )
    return p


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------
# Seeded from (respondent_id, dimension) so the six dimensions shuffle independently -- a single
# stream would correlate their orders, and a respondent comparing dimensions could infer the
# shared permutation. SHA-256 rather than Python's hash(): the builtin is salted per process, so
# a resumed session in a different worker would reshuffle. That failure would be intermittent,
# environment-dependent and invisible in the data, which is the worst kind.

def _seed(respondent_id: str, dimension: str) -> int:
    h = hashlib.sha256(f"{respondent_id}\x00{dimension}".encode("utf-8")).digest()
    return int.from_bytes(h, "big")


def _shuffled(items: list, respondent_id: str, dimension: str) -> list:
    """Fisher-Yates driven by successive slices of the seed. Written out rather than delegated to
    random.Random so the permutation is a documented function of the seed and cannot change under
    a CPython version bump -- a silent reordering across a deploy would break resumed sessions."""
    out = list(items)
    state = _seed(respondent_id, dimension)
    for i in range(len(out) - 1, 0, -1):
        state = int.from_bytes(
            hashlib.sha256(state.to_bytes(32, "big")).digest(), "big"
        )
        j = state % (i + 1)
        out[i], out[j] = out[j], out[i]
    return out


# ---------------------------------------------------------------------------
# Opaque item tokens
# ---------------------------------------------------------------------------

def _token(respondent_id: str, item_id: str, secret: bytes) -> str:
    return hmac.new(
        secret, f"{respondent_id}\x00{item_id}".encode("utf-8"), hashlib.sha256
    ).hexdigest()[: _TOKEN_BYTES * 2]


def _secret(explicit: bytes | None) -> bytes:
    if explicit is not None:
        return explicit
    env = os.environ.get("SOLVERAH_FORM_TOKEN_SECRET")
    if not env:
        raise PresentationContractError(
            "no form token secret. Set SOLVERAH_FORM_TOKEN_SECRET, or pass secret= explicitly in "
            "tests. Deliberately no default: a hardcoded fallback would make tokens forgeable "
            "and let a client map a token back to an item id, undoing never_display."
        )
    return env.encode("utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_form(
    respondent_id: str,
    items_path: Path | str = DEFAULT_ITEMS_PATH,
    secret: bytes | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Return (payload, token_map).

    `payload` is safe to serialise straight to the client: item order within each dimension is
    shuffled stably for this respondent, and every field in the contract's never_display list is
    absent -- not blanked, absent, so it cannot be recovered from the DOM.

    `token_map` is {token: item_id} and must be persisted with the respondent's session. It is
    reproducible from (respondent_id, secret), so a resumed session regenerates identical tokens
    even if the map was not stored.
    """
    if not respondent_id:
        raise ValueError("respondent_id is required -- it is the shuffle seed and the token salt")

    items_path = Path(items_path)
    doc = _load(items_path)
    contract = presentation_contract(doc)
    never = set(contract["never_display"])
    key = _secret(secret)

    by_dim: dict[str, list[dict]] = {}
    for item in doc["items"]:
        by_dim.setdefault(item["dimension"], []).append(item)

    for dim, its in by_dim.items():
        if len(its) != ITEMS_PER_DIMENSION:
            raise PresentationContractError(
                f"dimension {dim!r} has {len(its)} items, expected {ITEMS_PER_DIMENSION}. The "
                f"interleave assumes every dimension contributes exactly one item per block."
            )

    # Design rule 7. Rule 3's per-dimension permutation decides WHICH rung lands in which
    # block -- block b takes position b of it -- so the rung order stays hidden exactly as
    # before. The order of dimensions WITHIN a block is then shuffled separately per block, so
    # the dimension sequence does not repeat down the form either.
    perm = {dim: _shuffled(its, respondent_id, dim) for dim, its in by_dim.items()}
    dim_names = sorted(by_dim)  # sorted, not dict order: the seed must be the only variable

    token_map: dict[str, str] = {}
    blocks = []
    prev_last: str | None = None
    for b in range(ITEMS_PER_DIMENSION):
        members = [perm[dim][b] for dim in dim_names]
        ordered = _shuffled(members, respondent_id, f"\x01block{b}")

        # Shuffling each block independently is not sufficient. A block can end on `pace` and
        # the next begin on `pace`, putting two same-dimension items adjacent ACROSS THE SEAM
        # -- precisely the adjacency rule 7 exists to prevent, and invisible to any per-block
        # check. Repair deterministically by swapping the first two positions: every dimension
        # appears exactly once per block, so the only member that can collide with prev_last
        # is the one at index 0, and index 1 therefore cannot collide. One swap always fixes
        # it and never creates a new collision.
        if prev_last is not None and ordered[0]["dimension"] == prev_last:
            ordered[0], ordered[1] = ordered[1], ordered[0]
        prev_last = ordered[-1]["dimension"]

        rendered = []
        for item in ordered:
            tok = _token(respondent_id, item["id"], key)
            token_map[tok] = item["id"]
            rendered.append({
                "token": tok,
                "prompt": item["prompt"],
                # Option order is preserved verbatim -- see design decision 3 in the module
                # docstring. Only `key` and `text` cross the wire; `pole` is redacted.
                "options": [
                    {k: v for k, v in o.items() if k not in never}
                    for o in item["options"]
                ],
            })
        blocks.append({"block": b, "items": rendered})

    payload = {
        "form_version": doc["form_version"],
        "respondent_id": respondent_id,
        # `blocks`, not `dimensions` -- design rule 7. A dimension-grouped payload would leak
        # the grouping through its own shape no matter what the item fields say.
        "blocks": blocks,
    }
    _assert_redacted(payload, never)
    return payload, token_map


def _assert_redacted(payload: Any, never: set[str]) -> None:
    """Belt-and-braces deep scan. The construction above is already careful; this catches a future
    edit that adds a field to the rendered dict without thinking about the contract. Cheap, and
    the failure it prevents is silent."""
    if isinstance(payload, dict):
        leaked = never & set(payload)
        if leaked:
            raise PresentationContractError(
                f"never_display field(s) {sorted(leaked)} reached the client payload"
            )
        for v in payload.values():
            _assert_redacted(v, never)
    elif isinstance(payload, list):
        for v in payload:
            _assert_redacted(v, never)


def resolve_responses(token_map: dict[str, str], submitted: dict[str, str]) -> dict[str, str]:
    """Map {token: chosen_key} back to {item_id: chosen_key} for score_person_side.score_choices.

    Rejects unknown tokens rather than dropping them: a silently ignored response changes the
    denominator of mean_pole and moves the score without any error surfacing."""
    out = {}
    for tok, choice in submitted.items():
        item_id = token_map.get(tok)
        if item_id is None:
            raise ValueError(
                f"unknown item token {tok[:8]}... -- refusing to score a partial response set, "
                f"since a dropped item silently changes mean_pole's denominator"
            )
        out[item_id] = choice
    return out
