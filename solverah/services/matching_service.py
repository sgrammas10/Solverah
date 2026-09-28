"""Company lookup and culture matching.

:func:`_score_all` is **P0-2**, the second-largest scale blocker in the system,
and it is narrowed here rather than fixed:

    Every request pulls every scoreable company into Python, constructs a
    ``CultureValues`` per row, scores it, sorts the whole set, and slices.
    There is no cache, no index, and no limit on the query.  At ten companies
    it is invisible; at a hundred thousand companies times meaningful RPS it
    saturates the database and every worker simultaneously.

What the scan reads is the key and the eight culture columns, with
``pace IS NOT NULL`` in the query.  It used to read every column of every row,
``profile_json`` -- the whole research document -- included, for a page that
shows one field of it; the page's names and industries are now read for the
page alone, in one more query.

It **used to commit a write on a GET** as well: a user who completed Work Pulse
before ``culture_preferences`` was stored got a backfill written and committed
mid-read -- the same class of problem as P0-3 on the profile read.  **Fixed in
Phase 3.**  :func:`resolve_culture_preferences` still derives the vector when it
is missing, and still returns it, so the response is identical; what it no longer
does is persist it.  Persisting is :func:`backfill_culture_preferences`, run from
the ``maintenance`` queue over the accounts that predate the vector being written
at submit time.

Deriving on every read rather than caching the derivation is affordable and was
measured: ``derive_culture_preferences`` is arithmetic over twelve stored answers,
and it runs only for accounts the backfill has not reached.

P0-2 is untouched, and Phase 3 deliberately does **not** put a Redis cache in
front of it.  ``docs/ARCHITECTURE.md`` lists "Redis cache for match sets" as this
phase's first caching item, and that item is dropped rather than deferred:
``culture_fit_score`` is an interim scorer being deleted, not migrated -- 34ms
across 2,071 companies -- and the causal Bayesian model replacing it has a
different key and a different invalidation trigger.  A cache built here would be
deleted with the thing it caches.  See ``solverah/infra/cache.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import sqlalchemy as sa

from model import AssessmentSubmission, User, db
from packages.ml.culture import CultureValues, culture_fit_score
from solverah import pagination
from solverah.domain import matching as domain
from solverah.infra import cache
from solverah.repositories import (
    assessment_repository,
    company_repository,
    profile_repository,
)

__all__ = [
    "DEFAULT_LENS",
    "DEFAULT_LIMIT",
    "DEFAULT_ORDER",
    "LENSES",
    "ORDERS",
    "list_companies",
    "matches",
    "MAX_LIMIT",
    "MatchingResult",
    "backfill_culture_preferences",
    "company_detail",
    "resolve_culture_preferences",
]

DEFAULT_LIMIT = 5
MIN_LIMIT = 1
MAX_LIMIT = 50

#: The ``profiles.extra`` key the culture vector lives under.
_PREFERENCES_KEY = "culture_preferences"


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


def _derive_culture_preferences(answers: Any) -> Optional[dict]:
    """Compute the culture vector from stored Work Pulse *answers*, or None.

    The answers come from the Work Pulse submission since Phase 2d; they came
    from ``user_intake.wpl_answers`` before, which was the last query outside the
    assessment tables that treated an instrument's answers as profile state.

    Pure: it computes and returns, and reading the answers and persisting the
    result are the callers' decisions.  That separation is what lets the read
    path have the value without writing it.
    """
    from work_pulse.derive_preferences import derive_culture_preferences

    if not answers:
        return None
    return derive_culture_preferences(answers)


def _work_pulse_answers(user_ids: Sequence[int]) -> Dict[int, Any]:
    """``{user_id: answers}`` of each user's Work Pulse sitting, in one query.

    Only the answers: not the result, and not the narrative. A user who has not
    sat Work Pulse is absent. No ordering is needed to pick the *current* row --
    ``uq_assessment_submissions_current`` holds one row per user for every kind
    but ``core``, which is the rule ``assessment_repository.current_submission``
    rests on for these kinds too.

    The backfill's batch read. It belongs beside
    ``assessment_repository.current_submissions``; move it there when that
    module next changes.
    """
    ids = list(user_ids)
    if not ids:
        return {}
    rows = db.session.execute(
        sa.select(AssessmentSubmission.user_id, AssessmentSubmission.answers).where(
            AssessmentSubmission.kind == "work_pulse",
            AssessmentSubmission.user_id.in_(ids),
        )
    )
    return {user_id: answers for user_id, answers in rows}


def resolve_culture_preferences(user: User) -> Optional[dict]:
    """The user's culture preferences, deriving from Work Pulse if absent.

    Returns None when neither is available, which the caller turns into a 400.

    One read of the one key, where this used to assemble the whole profile
    document -- six statements -- to look at it; and, when it is absent, one read
    of the Work Pulse row without its narrative.

    **Writes nothing.**  This derived and then committed inside a GET until
    Phase 3 -- see the module docstring.  The derivation is unchanged and so is
    the value returned; only the INSERT is gone, and
    :func:`backfill_culture_preferences` is where it went.
    """
    user_prefs = profile_repository.read_extra_key(user.id, _PREFERENCES_KEY)
    if user_prefs:
        return user_prefs

    submission = assessment_repository.current_result(user.id, "work_pulse")
    return _derive_culture_preferences(submission.answers if submission is not None else None)


class _AlreadyStored(Exception):
    """The key gained a value after the sweep chose this user: leave it alone."""


def _fill_if_empty(value: dict) -> Callable[[Any], dict]:
    """An ``update_extra_key`` mutate that stores *value* only where nothing is stored.

    Pure, as ``update_extra_key`` requires: it closes over the value to write,
    never over a stored one, and re-running it against a fresh read re-decides.
    Raising is how it declines -- ``update_extra_key`` has written nothing when
    the mutate runs, so nothing needs undoing.
    """

    def mutate(stored: Any) -> dict:
        if stored:
            raise _AlreadyStored()
        return value

    return mutate


def backfill_culture_preferences(limit: int = 500) -> Dict[str, int]:
    """Persist derived culture preferences for accounts still missing them.

    The write ``resolve_culture_preferences`` used to do on a read, done where it
    belongs: on the ``maintenance`` queue, in bulk, never on a request.  Nothing
    depends on it having run -- the read derives what it needs either way -- so a
    failure here costs a few milliseconds per read and not a wrong answer.

    Idempotent and bounded.  Selects only users whose profile lacks the key, so
    running it twice over a finished backfill is a query and no writes.

    The rule for writing is the one it has always had -- a user is written only
    if the key is still empty and their answers yield a vector -- but the "still
    empty" check now runs inside ``update_extra_key``'s compare-and-swap.  It used
    to run before the derivation, and the write after it was unconditional, so
    a Work Pulse submit landing in between (the submit writes the key itself)
    was overwritten with a vector derived from the answers the sweep had read.

    One read of every candidate's answers, three statements per user written,
    and **one commit for the sweep**, where there was a commit per user.  A
    failure part-way -- ``ConcurrentProfileUpdate``, say -- leaves the sweep
    uncommitted and the caller's teardown rolls it back; the next run redoes it.
    The rows written stay locked until that commit, so a user saving their
    profile meanwhile waits for the sweep, which is a few statements a user.

    Returns:
        ``{"considered": n, "written": n, "underivable": n}``.
    """
    counts = {"considered": 0, "written": 0, "underivable": 0}

    user_ids = profile_repository.user_ids_missing(_PREFERENCES_KEY, limit=limit)
    answers = _work_pulse_answers(user_ids)
    for user_id in user_ids:
        counts["considered"] += 1
        derived = _derive_culture_preferences(answers.get(user_id))
        if not derived:
            # No Work Pulse submission to derive from. Not an error: most accounts
            # in this state simply have not taken the instrument yet.
            counts["underivable"] += 1
            continue

        try:
            profile_repository.update_extra_key(
                user_id, _PREFERENCES_KEY, _fill_if_empty(derived)
            )
        except _AlreadyStored:
            continue
        counts["written"] += 1

    if counts["written"]:
        db.session.commit()
    return counts


def _clamp_limit(raw: Any) -> Any:
    """Parse and clamp the ``limit`` query parameter.

    Returns the int, or None when it is not parseable -- the caller answers 400
    for garbage rather than silently defaulting, because a client sending
    ``limit=abc`` has a bug worth surfacing.
    """
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return None
    return max(MIN_LIMIT, min(MAX_LIMIT, limit))


def _format_entry(company, fit) -> Dict[str, Any]:
    """One match row, as the company-lens UI renders it.

    *company* is a ``company_repository.summaries`` row: ``industry`` comes out
    of the research document by JSON path, not with it.
    """
    matching, mismatching = domain.top_and_bottom_dimensions(fit.dimension_scores)
    return {
        "id": company.id,
        "name": company.name,
        "slug": company.slug,
        "industry": company.industry,
        "fit_score": fit.total_score,
        "top_matching_dimensions": matching,
        "top_mismatching_dimensions": mismatching,
        "fit_summary": domain.build_fit_summary(matching, mismatching),
    }


# ---------------------------------------------------------------------------
# Phase 1b -- cursor-paginated lists
# ---------------------------------------------------------------------------
#
# Both lists below page with a keyset cursor rather than an offset (A5).  The
# company list's keyset is in the query: a page reads its rows and no others.
# The matches list still pages in process, because its sort key is a score that
# exists only once Python has computed it for every company (P0-2).  What the
# cursor fixed first is the *interface*: a client that has been handed opaque
# cursors and never an offset does not have to change when Phase 2 pushes the
# matches keyset into a pgvector-backed query, and a client that has been
# handed ``?page=3&per_page=20`` does.

#: The only scoring lens that exists. Declared rather than assumed so adding a
#: second one is a change to this tuple and a branch, not a new endpoint.
LENSES = ("culture",)
DEFAULT_LENS = "culture"

ORDERS = ("best", "worst")
DEFAULT_ORDER = "best"


def _company_key(row) -> Dict[str, Any]:
    """The company list's cursor key. Unique, because ``name`` is."""
    return {"id": row.id, "name": row.name}


def _company_follows(row, key: Dict[str, Any]) -> bool:
    # Ordered by (name, id) ascending, so a row follows the cursor when its sort
    # tuple is greater. Spelled out rather than inferred because the matches
    # list below sorts the other way and a guessed comparison would page it
    # backwards.
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


def matches(
    user: User,
    *,
    cursor: Optional[str],
    limit: Any,
    lens: Optional[str],
    order: Optional[str],
    logger,
) -> MatchingResult:
    """One page of companies ranked by fit against the user's culture preferences.

    Replaces ``GET /company-lens/matches``, which returned two fixed-size slices
    -- ``best_fits`` and ``worst_fits`` -- in one body and could show nothing
    beyond them. ``?order=worst`` is what carries the second slice over: the two
    halves become two directions through one paginated list, so a client can
    walk as far as it wants in either.

    Still an O(all-companies) in-process scan (P0-2), though of the key and the
    eight culture columns only; names, slugs and industries are read afterwards
    for the page being returned. See the module docstring; the cursor makes the
    contract survive the fix, it is not the fix.
    """
    resolved_lens = (lens or DEFAULT_LENS).strip().lower()
    if resolved_lens not in LENSES:
        return _error(400, "Unsupported lens %r" % lens)

    resolved_order = (order or DEFAULT_ORDER).strip().lower()
    if resolved_order not in ORDERS:
        return _error(400, "order must be 'best' or 'worst'")

    user_prefs = resolve_culture_preferences(user)
    if not user_prefs:
        return _error(400, "Work Pulse not completed — culture preferences not found")

    after = pagination.decode_cursor(cursor)
    page_size = pagination.resolve_limit(limit)

    scored = _score_all(user, user_prefs, logger)
    descending = resolved_order == "best"
    scored.sort(key=lambda pair: (-pair[1].total_score, pair[0].id) if descending
                else (pair[1].total_score, pair[0].id))

    def _follows(pair, key) -> bool:
        company, fit = pair
        if descending:
            return (-fit.total_score, company.id) > (-key.get("score", 0), key.get("id", 0))
        return (fit.total_score, company.id) > (key.get("score", 0), key.get("id", 0))

    window, next_cursor = pagination.page(
        scored,
        limit=page_size,
        after=after,
        key_of=lambda pair: {"id": pair[0].id, "score": pair[1].total_score},
        follows=_follows,
    )

    # One IN query for the page's names, slugs and industries. A company deleted
    # between the scan and this read has nothing left to show and is left out;
    # nothing in the application deletes companies.
    summaries = company_repository.summaries(company.id for company, _fit in window)
    return MatchingResult(
        status=200,
        body={
            "data": [
                _format_entry(summaries[company.id], fit)
                for company, fit in window
                if company.id in summaries
            ],
            "next_cursor": next_cursor,
            "total_companies_scored": len(scored),
            "lens": resolved_lens,
            "order": resolved_order,
        },
    )


def _score_all(user: User, user_prefs: dict, logger) -> List[Any]:
    """Every scoreable company, paired with its fit. The P0-2 scan itself.

    Kept separate from :func:`matches` so that the scan and the paging are two
    things rather than one -- Phase 2 replaces this function with a pgvector
    query and a cached match set, and the paging above does not have to change
    when it does.

    Each company is a ``company_repository.culture_rows`` row: the key and the
    eight culture columns, and only for companies with a pace.
    """
    scored = []
    for company in company_repository.culture_rows():
        try:
            culture_values = CultureValues(
                work_environment=company.work_environment,
                pace=company.pace,
                empathy=company.empathy,
                creative_drive=company.creative_drive,
                adaptability=company.adaptability,
                futuristic=company.futuristic,
                harmony=company.harmony,
                data_orientation=company.data_orientation,
            )
            fit = culture_fit_score(culture_values, user_prefs)
        except Exception:  # noqa: BLE001 -- one bad row must not fail the list
            logger.warning("Skipping company %s — invalid culture data", company.id)
            continue
        scored.append((company, fit))
    return scored
