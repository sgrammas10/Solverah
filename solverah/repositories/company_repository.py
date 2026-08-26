"""Reads and writes for the ``company`` table.

Formerly ``company_culture_LLM/store.py``, reached through the ``sys.path``
injection ``app.py`` performed at import time.  It sits in ``repositories/``
rather than ``packages/ml/`` because it imports SQLAlchemy: the culture *models*
and *scoring* are pure and moved to :mod:`packages.ml.culture`, but persistence
is application infrastructure.

Usage (inside a Flask app context)::

    from solverah.repositories.company_repository import all_companies, get_company

    profile = get_company("google")

Known scale limit, unchanged by Phase 1: :func:`all_companies` returns every
row with ``profile_json`` attached, and the culture-matching service scores the
whole set in process on every request.  That is P0-2 in docs/ARCHITECTURE.md and
is fixed in Phase 2 with a vector index and a precomputed, cached match set.
The query is at least in one place now, which is what makes that fix a local
change.
"""

from __future__ import annotations

import re

from model import Company, db
from packages.ml.culture import CompanyProfile


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
    """Return all Company ORM rows (lightweight — profile_json included)."""
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
