"""Reads and writes for the ``company`` table.

Formerly ``company_culture_LLM/store.py``, reached through the ``sys.path``
injection ``app.py`` performed at import time.  It sits in ``repositories/``
rather than ``packages/ml/`` because it imports SQLAlchemy: the culture *models*
and *scoring* are pure and moved to :mod:`packages.ml.culture`, but persistence
is application infrastructure.

Usage (inside a Flask app context)::

    from solverah.repositories.company_repository import all_companies, get_company

    profile = get_company("google")

``profile_json`` is the whole research document, tens of kilobytes a row, and
the two paginated lists need one field of it.  So the reads they make are
narrow: :func:`list_rows` and :func:`summaries` take ``industry`` out of the
document by JSON path in the database, :func:`culture_rows` is the eight culture
columns and the key, and :func:`network_sample` is three columns.  Only
``GET /companies/<id>`` and the seeding shim read the document itself.

Known scale limit, still: culture matching scores every company with a pace, in
process, on every request -- P0-2 in docs/ARCHITECTURE.md, which the causal
model replaces.  :func:`culture_rows` is that scan; it no longer drags the
document along with it.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import sqlalchemy as sa

from model import Company, db
from packages.ml.culture import CompanyProfile
from solverah.infra import cache

#: The eight columns ``matching_service`` builds a ``CultureValues`` from.
CULTURE_COLUMNS = (
    Company.work_environment,
    Company.pace,
    Company.empathy,
    Company.creative_drive,
    Company.adaptability,
    Company.futuristic,
    Company.harmony,
    Company.data_orientation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _culture_columns(profile: CompanyProfile) -> dict:
    """Extract the 8 culture dimension values from a CompanyProfile."""
    c = profile.culture
    if c is None:
        return {}
    return {
        "culture_narrative_company": c.culture_narrative_company,
        "culture_narrative_employees": c.culture_narrative_employees,
        "work_environment": c.work_environment,
        "pace": c.pace,
        "pace_float": c.pace_float,
        "empathy": c.empathy,
        "creative_drive": c.creative_drive,
        "adaptability": c.adaptability,
        "futuristic": c.futuristic,
        "harmony": c.harmony,
        "data_orientation": c.data_orientation,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upsert_company(profile: CompanyProfile) -> Company:
    """Insert or update a company row from a CompanyProfile object.

    Uses the company name as the natural key. If a row already exists it is
    updated in-place; otherwise a new row is inserted.

    Must be called inside a Flask application context.
    """
    slug = _slugify(profile.overview.name)
    row = Company.query.filter_by(slug=slug).first()

    culture_cols = _culture_columns(profile)
    profile_dict = profile.model_dump()

    if row is None:
        row = Company(
            name=profile.overview.name,
            slug=slug,
            profile_json=profile_dict,
            **culture_cols,
        )
        db.session.add(row)
    else:
        row.name = profile.overview.name
        row.profile_json = profile_dict
        for key, val in culture_cols.items():
            setattr(row, key, val)

    # The only writer of this table, and therefore the only place that can
    # invalidate the cached detail payload (Phase 3). Flushed first because an
    # INSERT has no id until it is, and dropped only once the commit lands --
    # dropping it before would let a concurrent read repopulate the key from the
    # pre-write row and leave it there. See solverah/infra/cache.py.
    db.session.flush()
    cache.invalidate_on_commit(cache.company_detail_key(row.id))

    db.session.commit()
    return row


def get_company(slug_or_name: str) -> CompanyProfile | None:
    """Return a CompanyProfile by slug or exact name, or None if not found."""
    slug = _slugify(slug_or_name)
    row = Company.query.filter(
        (Company.slug == slug) | (Company.name == slug_or_name)
    ).first()
    if row is None:
        return None
    return CompanyProfile.model_validate(row.profile_json)


def all_companies() -> list[Company]:
    """Return all Company ORM rows, ``profile_json`` included.

    For the seeding scripts, through ``company_culture_LLM/store.py``. Nothing on
    a request path calls it: culture matching reads :func:`culture_rows`.
    """
    return Company.query.order_by(Company.name).all()


def seed_all(profiles: list[CompanyProfile]) -> list[Company]:
    """Upsert a list of CompanyProfile objects. Useful for bulk seeding."""
    return [upsert_company(p) for p in profiles]


def get_by_id(company_id: int):
    """Return the company with this primary key, or None.

    ``db.session.get`` rather than the legacy ``Query.get``, which SQLAlchemy 2.0
    deprecates and which emitted a warning on every company-detail request.
    Identical semantics: primary-key lookup, identity-map aware.
    """
    return db.session.get(Company, company_id)


def search_companies(q: str | None = None) -> list[Company]:
    """Whole Company rows whose name matches *q*, ordered by ``(name, id)``.

    What ``GET /companies`` read before it paged in SQL; :func:`list_rows` is
    what it reads now. Kept for any caller that wants the ORM rows.
    """
    query = Company.query
    if q:
        query = query.filter(Company.name.ilike("%%%s%%" % q))
    return query.order_by(Company.name, Company.id).all()


def _industry():
    """``profile_json -> 'overview' -> 'industry'``, typed JSON.

    The one field of the research document either list shows, read by path so
    the document never leaves the database. The driver decodes it as it decodes
    the whole document, so it is the value ``profile_json["overview"]["industry"]``
    held in Python, and None where the key or ``overview`` is missing.
    """
    return Company.profile_json["overview"]["industry"]


def _list_filters(q: Optional[str], industry: Optional[str]) -> List[Any]:
    clauses = []
    if q:
        # The pattern the list has always used. Unescaped, so a `%` or `_` in q
        # is a wildcard, as it was.
        clauses.append(Company.name.ilike("%%%s%%" % q))
    if industry is not None:
        # `(industry or "").lower() == wanted`, in SQL. The stored value is a
        # string or null -- CompanyOverview.industry is Optional[str] and
        # upsert_company is the only writer.
        clauses.append(
            sa.func.lower(sa.func.coalesce(_industry().as_string(), "")) == industry
        )
    return clauses


def list_rows(
    *,
    q: Optional[str] = None,
    industry: Optional[str] = None,
    start_at: Optional[Tuple[str, int]] = None,
    limit: Optional[int] = None,
) -> List[sa.Row]:
    """``id``, ``name``, ``slug`` and ``industry`` of the company list, in ``(name, id)`` order.

    The ordering is the pagination contract, not a display preference: it is
    unique -- ``name`` is unique in the schema and ``id`` breaks any tie a
    future non-unique name would introduce -- which is what makes a keyset
    cursor over it stable.

    Args:
        q: Keep names containing it, case-insensitively (``ILIKE '%q%'``).
        industry: Keep rows whose industry, lowercased, equals it. The caller
            lowercases it; None means no industry filter, and ``""`` keeps the
            rows with no industry.
        start_at: A ``(name, id)`` to start at, *inclusive* -- the keyset as the
            database orders it. Inclusive so the caller can see whether the row
            its cursor names is still in the list.
        limit: At most this many rows; None for all of them.

    Neither filter is indexed: ``q`` is a substring match and ``industry`` sits
    inside ``profile_json``. Both still run in the database, so a page reads its
    rows and no others unless a filter has to look past them.
    """
    statement = sa.select(
        Company.id, Company.name, Company.slug, _industry().label("industry")
    ).where(*_list_filters(q, industry))
    if start_at is not None:
        statement = statement.where(
            sa.tuple_(Company.name, Company.id) >= sa.tuple_(*start_at)
        )
    statement = statement.order_by(Company.name, Company.id)
    if limit is not None:
        statement = statement.limit(limit)
    return db.session.execute(statement).all()


def culture_rows() -> List[sa.Row]:
    """``id`` and the :data:`CULTURE_COLUMNS` of every company with a ``pace``.

    The scan culture matching scores (P0-2): a company without a pace has never
    been scoreable, so the filter is in the query rather than in the loop. In
    no particular order -- the caller sorts by score.
    """
    return db.session.execute(
        sa.select(Company.id, *CULTURE_COLUMNS).where(Company.pace.isnot(None))
    ).all()


def summaries(company_ids: Iterable[int]) -> Dict[int, sa.Row]:
    """``{id: row}`` of ``id``, ``name``, ``slug`` and ``industry``, one IN query.

    For the page of matches a request returns, after scoring has chosen it. An
    id with no row is absent. Sends nothing for no ids.
    """
    ids = list(company_ids)
    if not ids:
        return {}
    rows = db.session.execute(
        sa.select(
            Company.id, Company.name, Company.slug, _industry().label("industry")
        ).where(Company.id.in_(ids))
    )
    return {row.id: row for row in rows}


def network_sample(limit: int = 10) -> List[sa.Row]:
    """``name``, ``work_environment`` and ``pace`` of the first *limit* companies by id.

    The agent's "companies in network" context. Ordered, so the same ten come
    back every time -- with no ORDER BY they were whichever ten the scan met
    first -- and by id, which the primary key serves.
    """
    return db.session.execute(
        sa.select(Company.name, Company.work_environment, Company.pace)
        .order_by(Company.id)
        .limit(limit)
    ).all()
