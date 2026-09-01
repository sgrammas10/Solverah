"""Company lookup and culture matching.

:func:`_score_all` is **P0-2**, the second-largest scale blocker in the system,
and it is preserved unchanged here rather than fixed:

    Every request pulls *every* company row into Python with its
    ``profile_json`` attached, constructs a ``CultureValues`` per row, scores it,
    sorts the whole set, and slices.  There is no cache, no index, and no limit
    on the query.  At ten companies it is invisible; at a hundred thousand
    companies times meaningful RPS it saturates the database and every worker
    simultaneously.

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
from typing import Any, Dict, List, Optional

from model import User, db
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


def _derive_culture_preferences(user_id: int, profile: Dict[str, Any]) -> Optional[dict]:
    """Compute the culture vector from stored Work Pulse answers, or None.

    Reads the Work Pulse submission since Phase 2d; it read
    ``user_intake.wpl_answers`` before, which was the last query outside the
    assessment tables that treated an instrument's answers as profile state.

    Pure with respect to the database: it reads and returns, and persisting the
    result is the caller's decision.  That separation is what lets the read path
    have the value without writing it.
    """
    from work_pulse.derive_preferences import derive_culture_preferences

    submission = assessment_repository.current_submission(user_id, "work_pulse")
    if submission is None or not submission.answers:
        return None
    return derive_culture_preferences(submission.answers)


def resolve_culture_preferences(user: User) -> Optional[dict]:
    """The user's culture preferences, deriving from Work Pulse if absent.

    Returns None when neither is available, which the caller turns into a 400.

    **Writes nothing.**  This derived and then committed inside a GET until
    Phase 3 -- see the module docstring.  The derivation is unchanged and so is
    the value returned; only the INSERT is gone, and
    :func:`backfill_culture_preferences` is where it went.
    """
    profile = profile_repository.load_document(user.id)
    user_prefs = profile.get("culture_preferences")
    if user_prefs:
        return user_prefs

    return _derive_culture_preferences(user.id, profile)


def backfill_culture_preferences(limit: int = 500) -> Dict[str, int]:
    """Persist derived culture preferences for accounts still missing them.

    The write ``resolve_culture_preferences`` used to do on a read, done where it
    belongs: on the ``maintenance`` queue, in bulk, never on a request.  Nothing
    depends on it having run -- the read derives what it needs either way -- so a
    failure here costs a few milliseconds per read and not a wrong answer.

    Idempotent and bounded.  Selects only users whose profile lacks the key, so
    running it twice over a finished backfill is a query and no writes.

    Returns:
        ``{"considered": n, "written": n, "underivable": n}``.
    """
    counts = {"considered": 0, "written": 0, "underivable": 0}

    for user_id in profile_repository.user_ids_missing("culture_preferences", limit=limit):
        counts["considered"] += 1
        profile = profile_repository.load_document(user_id)
        if profile.get("culture_preferences"):
            continue

        derived = _derive_culture_preferences(user_id, profile)
        if not derived:
            # No Work Pulse submission to derive from. Not an error: most accounts
            # in this state simply have not taken the instrument yet.
            counts["underivable"] += 1
            continue

        profile_repository.update_document(
            user_id,
            lambda existing, value=derived: {**existing, "culture_preferences": value},
        )
        db.session.commit()
        counts["written"] += 1

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
    """One match row, as the company-lens UI renders it."""
    matching, mismatching = domain.top_and_bottom_dimensions(fit.dimension_scores)
    overview = (company.profile_json or {}).get("overview") or {}
    return {
        "id": company.id,
        "name": company.name,
        "slug": company.slug,
        "industry": overview.get("industry"),
        "fit_score": fit.total_score,
        "top_matching_dimensions": matching,
        "top_mismatching_dimensions": mismatching,
        "fit_summary": domain.build_fit_summary(matching, mismatching),
    }


# ---------------------------------------------------------------------------
# Phase 1b -- cursor-paginated lists
# ---------------------------------------------------------------------------
#
# Both lists below page with a keyset cursor rather than an offset (A5).  Both
# still do the work in process, which is P0-2 and is not fixed here -- what
# changes is the *interface*.  A client that has been handed opaque cursors and
# never an offset does not have to change when Phase 2 pushes the same keyset
# into a pgvector-backed query, and a client that has been handed
# ``?page=3&per_page=20`` does.  Paginating the contract before the storage can
# support it efficiently is the cheap half of the fix and the half that has to
# come first.

#: The only scoring lens that exists. Declared rather than assumed so adding a
#: second one is a change to this tuple and a branch, not a new endpoint.
LENSES = ("culture",)
DEFAULT_LENS = "culture"

ORDERS = ("best", "worst")
DEFAULT_ORDER = "best"


def _company_industry(company) -> Optional[str]:
    return ((company.profile_json or {}).get("overview") or {}).get("industry")


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

    The industry filter runs in Python because ``industry`` lives inside
    ``profile_json`` and not in a column -- a scan, and honest about being one.
    Phase 4.5 promotes it and the filter moves into the query.
    """
    after = pagination.decode_cursor(cursor)
    page_size = pagination.resolve_limit(limit)

    rows = company_repository.search_companies(q=q)
    if industry:
        wanted = industry.strip().lower()
        rows = [c for c in rows if (_company_industry(c) or "").lower() == wanted]

    window, next_cursor = pagination.page(
        rows,
        limit=page_size,
        after=after,
        key_of=lambda c: {"id": c.id, "name": c.name},
        # Ordered by (name, id) ascending, so a row follows the cursor when its
        # sort tuple is greater. Spelled out rather than inferred because the
        # matches list below sorts the other way and a guessed comparison would
        # page it backwards.
        follows=lambda c, key: (c.name, c.id) > (key.get("name"), key.get("id")),
    )

    return MatchingResult(
        status=200,
        body={
            "data": [
                {
                    "id": c.id,
                    "name": c.name,
                    "slug": c.slug,
                    "industry": _company_industry(c),
                }
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

    Still an O(all-companies) in-process scan with a commit on the read path
    (P0-2). See the module docstring; the cursor makes the contract survive the
    fix, it is not the fix.
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

    return MatchingResult(
        status=200,
        body={
            "data": [_format_entry(company, fit) for company, fit in window],
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
    """
    scored = []
    for company in company_repository.all_companies():
        if company.pace is None:
            continue
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
