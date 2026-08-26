"""Company lookup and culture matching.

:func:`culture_matches` is **P0-2**, the second-largest scale blocker in the
system, and it is preserved unchanged here rather than fixed:

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
from solverah.domain import matching as domain
from solverah.repositories import company_repository

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "MatchingResult",
    "company_detail",
    "culture_matches",
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
    profile = user.profile_data or {}
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
    profile = dict(profile)
    profile["culture_preferences"] = user_prefs
    user.profile_data = profile
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


def culture_matches(user: User, raw_limit: Any, logger) -> MatchingResult:
    """Score every company against the user's culture preferences.

    See the module docstring: this is an O(all companies) in-process scan.
    """
    user_prefs = resolve_culture_preferences(user)
    if not user_prefs:
        return _error(400, "Work Pulse not completed — culture preferences not found")

    limit = _clamp_limit(raw_limit)
    if limit is None:
        return _error(400, "limit must be an integer")

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

    scored.sort(key=lambda pair: pair[1].total_score, reverse=True)
    best_rows, worst_rows = domain.split_best_and_worst(scored, limit)

    return MatchingResult(
        status=200,
        body={
            "best_fits": [_format_entry(c, f) for c, f in best_rows],
            "worst_fits": [_format_entry(c, f) for c, f in worst_rows],
            "total_companies_scored": len(scored),
            "limit": limit,
        },
    )


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
