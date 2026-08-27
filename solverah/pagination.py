"""Opaque cursor pagination -- Part 5.1's ``?cursor=&limit=`` convention.

Decision A5 in docs/ARCHITECTURE.md rules out offset pagination, and the reason
matters for how this is built.  ``OFFSET 100000`` makes the database walk a
hundred thousand rows to discard them, and -- the part that is a correctness
problem rather than a performance one -- a row inserted or deleted between two
requests shifts every subsequent page, so a client paging through a list under
concurrent writes silently skips and repeats entries.

So the cursor here is a **keyset**, not a disguised offset.  It carries the sort
key of the last row returned, and the next page is "everything ordered after
this key".  Insertions and deletions elsewhere in the list cannot shift it.

The encoding is base64url of a compact JSON object.  It is opaque *by contract*
-- clients must treat it as a token and pass it back unmodified -- but it is
deliberately not encrypted or signed, and that is worth being explicit about:

* Signing it would mean a key to rotate and a failure mode where every
  in-flight cursor breaks on rotation, to protect a value that is not a secret.
  Every cursor this module mints holds a sort key the caller was just handed in
  the response body.
* A tampered cursor therefore cannot read anything the caller could not read
  anyway.  It selects a *position* in a result set the caller is already
  authorised for; it never carries the identity that authorised it.  Every
  caller-scoped list re-derives its scope from the JWT on each request.

:func:`decode_cursor` treats anything malformed as a client error, not as page
one.  Silently starting over on a garbled cursor is how a paging loop turns into
an infinite one.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .errors import ValidationError

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "MIN_LIMIT",
    "decode_cursor",
    "encode_cursor",
    "page",
    "resolve_limit",
]

DEFAULT_LIMIT = 20
MIN_LIMIT = 1
MAX_LIMIT = 100


def encode_cursor(key: Dict[str, Any]) -> str:
    """Encode a sort key as an opaque cursor token.

    Separators are tightened and keys sorted so the same position always encodes
    to the same string -- a client caching on the cursor value gets a stable one,
    and a test can assert on it.
    """
    raw = json.dumps(key, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Decode a cursor token, or return None when there is none.

    Args:
        token: The ``cursor`` query parameter, if the client sent one.

    Returns:
        The sort key dict, or None for a first page.

    Raises:
        ValidationError: If *token* is not a cursor this module minted. A
            malformed cursor is a bug in the caller; answering it with page one
            turns a paging loop into an infinite one, and answering it with an
            empty page hides the bug entirely.
    """
    if token is None or token == "":
        return None

    padding = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(token + padding)
        key = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValidationError(
            detail="cursor is not a valid pagination token",
            errors=[{"field": "cursor", "code": "invalid_cursor"}],
        ) from exc

    if not isinstance(key, dict):
        raise ValidationError(
            detail="cursor is not a valid pagination token",
            errors=[{"field": "cursor", "code": "invalid_cursor"}],
        )
    return key


def resolve_limit(
    raw: Any,
    *,
    default: int = DEFAULT_LIMIT,
    maximum: int = MAX_LIMIT,
) -> int:
    """Parse and bound the ``limit`` query parameter.

    An absent limit takes *default*.  A non-integer is a 422 rather than a
    silent fallback: ``limit=abc`` is a client bug, and serving 20 rows for it
    means the bug ships. An out-of-range integer is clamped rather than
    rejected, because ``limit=1000`` is a legible request for "as many as you
    will give me" and clamping answers it honestly.

    Raises:
        ValidationError: If *raw* is present and is not an integer.
    """
    if raw is None or raw == "":
        return default
    try:
        limit = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            detail="limit must be an integer",
            errors=[{"field": "limit", "code": "int_parsing"}],
        ) from exc
    return max(MIN_LIMIT, min(maximum, limit))


def page(
    rows: Sequence[Any],
    *,
    limit: int,
    key_of: Callable[[Any], Dict[str, Any]],
    after: Optional[Dict[str, Any]] = None,
    follows: Optional[Callable[[Any, Dict[str, Any]], bool]] = None,
) -> Tuple[List[Any], Optional[str]]:
    """Slice an ordered, in-memory sequence into one keyset page.

    In-memory is the honest description of what the two paginated lists can do
    today: culture matching scores every company in process (P0-2), and the
    company list is small enough that the query is not the bottleneck.  The
    *interface* is what matters -- callers hand back opaque cursors and never
    see an offset -- so Phase 2 can push the same keyset into SQL without the
    client noticing.

    Args:
        rows: Rows already in their final sort order.
        limit: Maximum rows to return.
        key_of: Row -> the sort key to mint a cursor from. Must be unique per
            row, or paging stalls on a duplicate.
        after: Decoded cursor; rows up to and including it are skipped.
        follows: ``(row, key) -> bool``, true when *row* sorts strictly after
            *key*. Used only when the cursor's row is no longer in the list.
            Direction lives here rather than being inferred, because half these
            lists sort descending and a comparison guessed from the key alone
            would silently page the wrong way.

    Returns:
        ``(rows_for_this_page, next_cursor)``. ``next_cursor`` is None on the
        last page, which is the client's signal to stop.
    """
    start = 0 if after is None else _position_after(rows, after, key_of, follows)

    window = list(rows[start : start + limit])
    if not window or start + limit >= len(rows):
        return window, None
    return window, encode_cursor(key_of(window[-1]))


def _position_after(
    rows: Sequence[Any],
    after: Dict[str, Any],
    key_of: Callable[[Any], Dict[str, Any]],
    follows: Optional[Callable[[Any, Dict[str, Any]], bool]],
) -> int:
    """Index of the first row strictly after the cursor key.

    Exact-match first: in a stable list the cursor names a row that is still
    there, and that is both the common case and the cheap one.

    The fallback is what makes this a keyset rather than an offset. If the row
    the cursor named has been deleted -- or its score changed, which happens on
    the culture list because scores are recomputed per request -- *follows*
    finds the position it would now occupy, so the next page continues from the
    right place instead of restarting or skipping a block.
    """
    for index, row in enumerate(rows):
        if key_of(row) == after:
            return index + 1

    if follows is None:
        # No comparator supplied and no exact match: the cursor points past
        # everything this list still holds. An empty final page is the correct
        # answer -- it terminates the client's loop.
        return len(rows)

    for index, row in enumerate(rows):
        if follows(row, after):
            return index
    return len(rows)
