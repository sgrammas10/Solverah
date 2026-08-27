"""Company lookup and culture matching.

:func:`_score_all` is **P0-2**, the second-largest scale blocker in the system,
and it is preserved unchanged here rather than fixed:

    Every request pulls *every* company row into Python with its
    ``profile_json`` attached, constructs a ``CultureValues`` per row, scores it,
    sorts the whole set, and slices.  There is no cache, no index, and no limit
    on the query.  At ten companies it is invisible; at a hundred thousand
    companies times meaningful RPS it saturates the database and every worker
    simultaneously.

It also **commits a write on a GET**: a user who completed Work Pulse before
``culture_preferences`` was stored gets a backfill written and committed
mid-read.  That is the same class of problem as P0-3 on the profile read.

Both are Phase 2/3 work -- a pgvector index over precomputed culture vectors, a
Redis-cached match set refreshed by a worker, and the backfill moved to a
migration.  Fixing either here would change response timing and content in a
batch whose contract is that neither changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from model import User, db
from packages.ml.culture import CultureValues, culture_fit_score
from solverah import pagination
from solverah.domain import matching as domain
from solverah.repositories import company_repository, profile_repository

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
    """Return one company's full stored profile.

    The integer id is exposed directly in the URL, so the endpoint enumerates:
    an authenticated caller can walk ``/companies/1``, ``/companies/2``, and
    read the whole network. Part 4.2 and Part 5.2 replace it with a UUID
    ``public_id``. Unchanged here because the frontend links by integer id.
    """
    company = company_repository.get_by_id(company_id)
    if company is None:
        return _error(404, "Company not found")

    return MatchingResult(
        status=200,
        body={
            "id": company.id,
            "name": company.name,
            "slug": company.slug,
            "profile": company.profile_json,
        },
    )


def resolve_culture_preferences(user: User) -> Optional[dict]:
    """The user's culture preferences, backfilling from Work Pulse if absent.

    Returns None when neither is available, which the caller turns into a 400.

    The backfill commits inside a GET -- see the module docstring. It exists for
    users who completed Work Pulse before ``culture_preferences`` was written at
    submit time; those accounts have the answers but not the derived vector.
    """
    profile = profile_repository.load_document(user.id)
    user_prefs = profile.get("culture_preferences")
    if user_prefs:
        return user_prefs

    # Backfill for users who completed WP before culture_preferences was stored.
    from model import UserIntake
    from work_pulse.derive_preferences import derive_culture_preferences

    intake = UserIntake.query.filter_by(user_id=user.id).first()
    if not intake or not intake.wpl_answers:
        return None

    user_prefs = derive_culture_preferences(intake.wpl_answers)
    profile_repository.update_document(
        user.id, lambda existing: {**existing, "culture_preferences": user_prefs}
    )
    db.session.commit()
    return user_prefs


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
