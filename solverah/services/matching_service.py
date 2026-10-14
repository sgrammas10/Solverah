"""Company lookup: the detail read and the paginated list.

The interim ``culture_fit_score`` ranking that used to live here -- ``matches``,
``_score_all`` (P0-2, the O(all-companies) scan), ``resolve_culture_preferences`` and
the ``backfill_culture_preferences`` sweep -- was DELETED by the six-trait build
(C6, 2026-10-13; PRODUCT_DECISIONS.md §2, "two scorers": the causal model was the
destination and the interim scorer was never to be invested in). ``GET /me/matches``
is now served by :mod:`solverah.services.company_match_service` on the company
evidence records. The eight legacy culture columns on ``company`` stay in place; a
column drop is a later migration.

What remains here is what the company pages read: ``company_detail`` (cached in
Redis, Phase 3) and ``list_companies`` (keyset-paginated, A5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from solverah import pagination
from solverah.infra import cache
from solverah.repositories import company_repository

__all__ = [
    "list_companies",
    "MatchingResult",
    "company_detail",
]


@dataclass
class MatchingResult:
    """A service outcome the API layer turns into a response."""

    status: int
    body: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status < 400


def _error(status: int, message: str) -> MatchingResult:
    return MatchingResult(status=status, body={"error": message})


def company_detail(company_id: int) -> MatchingResult:
    """Return one company's full stored profile. Cached in Redis (Phase 3).

    The integer id is exposed directly in the URL, so the endpoint enumerates:
    an authenticated caller can walk ``/companies/1``, ``/companies/2``, and
    read the whole network. Part 4.2 and Part 5.2 replace it with a UUID
    ``public_id``. Unchanged here because the frontend links by integer id.

    **The best caching candidate in the application**, which is why it is one of
    the two reads Phase 3 caches. The row is large -- ``profile_json`` is the
    entire research document -- it is read far more often than it is written,
    every company page hits it, and the payload is identical for every caller
    because nothing in it depends on who is asking. The key is invalidated by
    ``company_repository.upsert_company``, which is the only writer.

    **404 is not cached**, deliberately. An id that does not exist yet may exist
    after the next import, and a negative cache would hold the absence past the
    row appearing. It also means an enumeration probe cannot leave anything
    behind.
    """
    key = cache.company_detail_key(company_id)
    cached = cache.get_json(key)
    if cached is not None:
        return MatchingResult(status=200, body=cached)

    company = company_repository.get_by_id(company_id)
    if company is None:
        return _error(404, "Company not found")

    body = {
        "id": company.id,
        "name": company.name,
        "slug": company.slug,
        "profile": company.profile_json,
    }
    cache.set_json(key, body)
    return MatchingResult(status=200, body=body)


# ---------------------------------------------------------------------------
# Phase 1b -- cursor-paginated lists
# ---------------------------------------------------------------------------
#
# The company list pages with a keyset cursor rather than an offset (A5): the
# keyset is in the query, so a page reads its rows and no others.


def _company_key(row) -> Dict[str, Any]:
    """The company list's cursor key. Unique, because ``name`` is."""
    return {"id": row.id, "name": row.name}


def _company_follows(row, key: Dict[str, Any]) -> bool:
    # Ordered by (name, id) ascending, so a row follows the cursor when its sort
    # tuple is greater. Spelled out rather than inferred because other lists
    # sort the other way and a guessed comparison would page them backwards.
    return (row.name, row.id) > (key.get("name"), key.get("id"))


def _seek_position(after: Dict[str, Any]) -> Optional[Tuple[str, int]]:
    """``(name, id)`` from a cursor the database can seek to, or None.

    This list mints ``{"id": int, "name": str}``. A key of any other shape --
    hand-edited, or from the matches list -- is not sent to the database, where
    a string id or a NUL in the name is an error rather than a comparison; the
    in-memory rule answers it, as it always has.
    """
    company_id, name = after.get("id"), after.get("name")
    if type(company_id) is not int or type(name) is not str or "\x00" in name:
        return None
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate, which JSON can carry
        return None
    return name, company_id


def _company_page_after(
    after: Dict[str, Any], page_size: int, *, q: Optional[str], industry: Optional[str]
) -> Tuple[List[Any], Optional[str]]:
    """The page after cursor *after*: a keyset read when its row is still listed.

    The rule is ``pagination.page``'s, unchanged: start just after the cursor's
    row, and, if that row has left the list -- deleted, renamed, or no longer
    matching the filters -- at the first row that follows it by ``_company_follows``.

    The common case is one query: seek to the cursor's ``(name, id)`` inclusive,
    in the database's order, and see the cursor's own row come back first. The
    fallback is not the same comparison moved into SQL. ``_company_follows``
    compares names by code point and the list is in the database's collation,
    which disagree (``eBay`` follows every capitalised name by code point, and
    sits among the E's by collation), so the fallback reads the list without its
    documents and applies the rule in memory, exactly as before.
    """
    seek = _seek_position(after)
    if seek is not None:
        rows = company_repository.list_rows(
            q=q, industry=industry, start_at=seek, limit=page_size + 2
        )
        if rows and _company_key(rows[0]) == after:
            return pagination.page(rows, limit=page_size, after=after, key_of=_company_key)

    rows = company_repository.list_rows(q=q, industry=industry)
    return pagination.page(
        rows, limit=page_size, after=after, key_of=_company_key, follows=_company_follows
    )


def list_companies(
    *,
    cursor: Optional[str],
    limit: Any,
    q: Optional[str] = None,
    industry: Optional[str] = None,
) -> MatchingResult:
    """One page of companies, filtered and keyset-paginated.

    New in Phase 1b: there was no list endpoint at all, so any screen wanting
    several companies fetched the full research document for each by id.

    Both filters, the keyset and the LIMIT are in the query, and ``industry`` is
    read out of ``profile_json`` by JSON path, so a page is one query for its own
    rows. It used to read every company, document and all, and filter and page
    in Python. The industry filter is still unindexed -- Phase 4.5 promotes
    ``industry`` to a column.
    """
    after = pagination.decode_cursor(cursor)
    page_size = pagination.resolve_limit(limit)
    wanted = industry.strip().lower() if industry else None

    if after is None:
        # One row past the page is what says there is another page.
        rows = company_repository.list_rows(q=q, industry=wanted, limit=page_size + 1)
        window, next_cursor = pagination.page(rows, limit=page_size, key_of=_company_key)
    else:
        window, next_cursor = _company_page_after(after, page_size, q=q, industry=wanted)

    return MatchingResult(
        status=200,
        body={
            "data": [
                {"id": c.id, "name": c.name, "slug": c.slug, "industry": c.industry}
                for c in window
            ],
            "next_cursor": next_cursor,
        },
    )
