"""Cursor pagination -- the keyset itself, and the two lists built on it.

The unit tests below matter more than they look. A cursor is the one part of an
API a client cannot work around when it is wrong: a paging loop that restarts on
a bad token spins forever, and one that silently skips a block loses data with
no error anywhere. So the properties asserted here are the ones a
paginated list has to have and an offset-based one does not:

* every row appears exactly once across the pages;
* the last page says so, by returning a null cursor;
* a row deleted mid-walk does not shift the rows after it;
* a token the server did not mint is refused rather than interpreted.
"""

import pytest

from solverah.errors import ValidationError
from solverah.pagination import decode_cursor, encode_cursor, page, resolve_limit


def _key(row):
    return {"id": row["id"], "name": row["name"]}


def _follows(row, key):
    return (row["name"], row["id"]) > (key.get("name"), key.get("id"))


def _rows(n):
    return [{"id": i, "name": "company-%02d" % i} for i in range(1, n + 1)]


def _walk(rows, limit, **kwargs):
    """Page through *rows* to exhaustion, returning every row seen."""
    seen, cursor, guard = [], None, 0
    while True:
        guard += 1
        assert guard < 100, "pagination did not terminate"
        window, cursor = page(
            rows, limit=limit, after=decode_cursor(cursor), key_of=_key, **kwargs
        )
        seen.extend(window)
        if cursor is None:
            return seen


# ── Encoding ────────────────────────────────────────────────────────────────


def test_a_cursor_round_trips():
    key = {"id": 7, "score": 0.42}

    assert decode_cursor(encode_cursor(key)) == key


def test_the_same_position_always_encodes_the_same_way():
    """A client caching on the cursor value needs a stable one."""
    assert encode_cursor({"id": 1, "score": 2}) == encode_cursor({"score": 2, "id": 1})


def test_no_cursor_means_the_first_page():
    assert decode_cursor(None) is None
    assert decode_cursor("") is None


@pytest.mark.parametrize(
    "token",
    [
        "not-base64!!",  # not base64 at all
        "YWJj",          # base64 of "abc" -- decodes, is not JSON
        "bnVsbA",        # base64 of "null" -- valid JSON, not an object
        "WzEsMl0",       # base64 of "[1,2]" -- valid JSON, not an object
    ],
)
def test_a_token_the_server_did_not_mint_is_refused(token):
    """Not silently treated as page one.

    Restarting on a garbled cursor turns a client's paging loop into an infinite
    one, and answering with an empty page hides the bug instead.
    """
    with pytest.raises(ValidationError):
        decode_cursor(token)


# ── Limits ──────────────────────────────────────────────────────────────────


def test_an_absent_limit_takes_the_default():
    assert resolve_limit(None, default=20) == 20


def test_an_oversized_limit_is_clamped_not_rejected():
    """`limit=1000` is a legible request for "as many as you will give me"."""
    assert resolve_limit(1000, maximum=100) == 100


def test_a_non_integer_limit_is_a_client_error():
    """Serving 20 rows for `limit=abc` means the client's bug ships."""
    with pytest.raises(ValidationError):
        resolve_limit("abc")


# ── The keyset ──────────────────────────────────────────────────────────────


def test_paging_covers_every_row_exactly_once():
    rows = _rows(10)

    seen = _walk(rows, limit=3)

    assert seen == rows


def test_the_last_page_reports_itself():
    rows = _rows(6)

    _window, cursor = page(rows, limit=3, after=decode_cursor(None), key_of=_key)
    window2, cursor2 = page(rows, limit=3, after=decode_cursor(cursor), key_of=_key)

    assert len(window2) == 3
    assert cursor2 is None


def test_an_exactly_full_final_page_still_terminates():
    """The off-by-one that makes a client fetch one empty page and stop late."""
    rows = _rows(4)

    seen = _walk(rows, limit=2)

    assert len(seen) == 4


def test_a_deletion_mid_walk_does_not_shift_the_rows_after_it():
    """The property offset pagination does not have, and the reason for A5.

    With OFFSET, deleting a row before the cursor pulls every later row back by
    one and the next page silently skips an entry. A keyset names a position by
    its sort key, so removing something ahead of it changes nothing behind it.
    """
    rows = _rows(10)

    first, cursor = page(rows, limit=3, after=None, key_of=_key)
    survivors = [r for r in rows if r["id"] != 1]  # delete a row already returned
    second, _ = page(survivors, limit=3, after=decode_cursor(cursor), key_of=_key, follows=_follows)

    assert [r["id"] for r in first] == [1, 2, 3]
    assert [r["id"] for r in second] == [4, 5, 6]


def test_paging_resumes_correctly_when_the_cursor_row_is_gone():
    """`follows` is what makes this work; without it the walk would end early."""
    rows = _rows(10)

    _first, cursor = page(rows, limit=3, after=None, key_of=_key)
    survivors = [r for r in rows if r["id"] != 3]  # the cursor row itself
    second, _ = page(survivors, limit=3, after=decode_cursor(cursor), key_of=_key, follows=_follows)

    assert [r["id"] for r in second] == [4, 5, 6]


def test_an_empty_list_pages_to_nothing_and_stops():
    window, cursor = page([], limit=5, after=None, key_of=_key)

    assert window == []
    assert cursor is None
