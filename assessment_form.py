"""
assessment_form.py -- the web layer's only doorway to the person-side instrument.

`present_items.py` is the correctness layer for how items reach a respondent and
`score_person_side.py` is the correctness layer for how choices become dimension scores.
Neither knows about Flask, and neither should. This module is the seam: it owns the two
integration decisions that live in neither file, and it is the only thing app.py imports.

Nothing else in the web layer may import present_items or score_person_side directly.
Both expose lower-level functions that are correct for their original callers and wrong
for a live form -- see DECISION 2.


DECISION 1: the token map is NOT persisted. It is regenerated.
--------------------------------------------------------------
`build_form` returns (payload, token_map) and its docstring notes the map "must be
persisted with the respondent's session" -- but also that it "is reproducible from
(respondent_id, secret), so a resumed session regenerates identical tokens even if the
map was not stored." We take the second reading, and store nothing.

Rebuilding is not merely equivalent, it is safer. A stored map is a second copy of the
respondent->item mapping that can drift from the item file, outlive a session table's TTL,
or be restored from a backup taken before an item edit. Regenerating means the map is a
pure function of (respondent_id, secret, item file) at submit time.

The one behavioural difference is the good one: if the active item file changes between
a respondent loading the form and submitting it, the regenerated tokens differ and
`resolve_responses` raises on the first unknown token. That is correct. A form built from
one instrument and scored against another is exactly the silent corruption D-07 forbids,
and refusing loudly beats scoring a mixture. The cost is a rare hard failure for a
respondent who left a tab open across a deploy; the alternative is an unnoticed bad row
in the ground-truth set.

This also means there is no session table, no TTL, and no cleanup job for form state.


DECISION 2: submit calls score_all_dimensions, never score_choices.
-------------------------------------------------------------------
`score_choices` means over everything it is handed. Given all 24 responses it returns one
number, successfully, and that number is not any dimension's score. See the long comment
on `score_all_dimensions`. Routing every submit through this module is what stops a
future edit from reaching for the more obvious-looking function.


DECISION 3: `respondent_id` must be stable and opaque, and it is the caller's job.
---------------------------------------------------------------------------------
It seeds the shuffle and salts the token HMAC, so it must be identical across a resumed
session or the respondent sees a reordered form (from which the grouping is inferable).
It must NOT be anything the respondent can choose or a sequential public counter. This
module validates shape only; the route supplies the value.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MODEL_DIR = Path(__file__).resolve().parent / "causal_graph" / "v1_model"
if str(_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(_MODEL_DIR))

from present_items import (  # noqa: E402
    DEFAULT_ITEMS_PATH,
    PresentationContractError,
    build_form,
    resolve_responses,
)
from score_person_side import load_items, score_all_dimensions  # noqa: E402

__all__ = [
    "AssessmentError",
    "PresentationContractError",
    "ScoredSubmission",
    "get_form",
    "scoring_key_version",
    "submit_form",
    "EXPECTED_RESPONSE_COUNT",
]

# 6 dimensions x 4 items. Asserted against the built form rather than trusted, because a
# client posting a short set is the one thing the token scheme does not already catch.
EXPECTED_RESPONSE_COUNT = 24


class AssessmentError(ValueError):
    """A submission that cannot be scored. Safe to surface as a 400."""


@dataclass(frozen=True)
class ScoredSubmission:
    """Everything the persistence layer needs, and nothing it has to re-derive.

    `choices` is included deliberately. Raw responses must be stored so scores can be
    re-derived when the scoring key changes, and the only place the token->item_id mapping
    exists is inside submit_form. A caller that had to redo that mapping would need the
    secret and a second build_form call, and would be one refactor away from storing tokens
    instead of item ids -- which would make the raw rows unreadable the moment the secret
    rotated.
    """

    form_version: str
    scoring_key_version: str
    scores: dict[str, float]
    choices: dict[str, str]


def scoring_key_version(items_path: Path | str = DEFAULT_ITEMS_PATH) -> str:
    """The identifier a stored score must carry to stay interpretable.

    S-08: the column and its plumbing have existed since v2 went active with nothing writing
    a meaningful value, which means the v1/v2 separation lives only in memory.

    It is the item file's `form_version` AND the scoring method, joined -- not either alone.
    A score is comparable to another score only if both were produced from the same items by
    the same arithmetic. `mean_pole` changing to anything else would silently reinterpret
    every stored row while `form_version` stayed put.
    """
    doc = _load_doc(items_path)
    version = doc.get("form_version")
    method = (doc.get("scoring") or {}).get("method")
    if not version or not method:
        raise AssessmentError(
            "the active item file declares no form_version and/or scoring.method; a score "
            "stored without a key version cannot be told apart from one scored under a "
            "different instrument"
        )
    return f"{version}+{method}"


def _load_doc(items_path: Path | str) -> dict:
    import yaml

    return yaml.safe_load(Path(items_path).read_text(encoding="utf-8"))


def _validate_respondent_id(respondent_id: Any) -> str:
    if not isinstance(respondent_id, str) or not respondent_id.strip():
        raise AssessmentError("respondent_id must be a non-empty string")
    return respondent_id


def get_form(respondent_id: str, items_path: Path | str = DEFAULT_ITEMS_PATH) -> dict:
    """Return the client-safe payload for this respondent.

    The payload carries `blocks`, not `dimensions` (design rule 7), and every field in the
    item file's `never_display` list is absent rather than blanked. The client renders it
    verbatim: it does not sort, group, or shuffle anything (D-04).

    The token map is deliberately discarded here -- see DECISION 1.
    """
    payload, _token_map = build_form(_validate_respondent_id(respondent_id), items_path)
    return payload


def submit_form(
    respondent_id: str,
    submitted: dict[str, str],
    items_path: Path | str = DEFAULT_ITEMS_PATH,
) -> ScoredSubmission:
    """Score a completed form. Returns a ScoredSubmission: six dimension scores, the raw
    {item_id: chosen_key} behind them, and the key version they were produced under.

    `submitted` is {opaque_token: chosen_option_key} exactly as posted by the client.

    Raises AssessmentError on anything that would make the result incomparable to a
    company-side score: wrong response count, an unknown token, an option key the item does
    not define, or a dimension that did not receive exactly four responses. None of these
    degrade to a partial score -- a partial mean_pole is a number off PERSON_LATTICE, and it
    is indistinguishable from a real one once stored.
    """
    respondent_id = _validate_respondent_id(respondent_id)

    if not isinstance(submitted, dict):
        raise AssessmentError("responses must be an object of {token: option_key}")
    if len(submitted) != EXPECTED_RESPONSE_COUNT:
        raise AssessmentError(
            f"expected {EXPECTED_RESPONSE_COUNT} responses, got {len(submitted)}. A partial "
            f"form is not scoreable: mean_pole over a short set is off PERSON_LATTICE and "
            f"cannot be compared with a company-side score."
        )

    # Regenerated, not loaded. DECISION 1.
    _payload, token_map = build_form(respondent_id, items_path)

    try:
        choices = resolve_responses(token_map, submitted)
    except ValueError as exc:
        raise AssessmentError(str(exc)) from exc

    items_index = load_items(Path(items_path))
    try:
        scores = score_all_dimensions(choices, items_index)
    except ValueError as exc:
        raise AssessmentError(str(exc)) from exc

    return ScoredSubmission(
        form_version=items_index["form_version"],
        scoring_key_version=scoring_key_version(items_path),
        scores=scores,
        choices=choices,
    )
