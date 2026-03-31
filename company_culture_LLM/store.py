"""DB helpers for persisting and retrieving CompanyProfile objects.

Usage (inside a Flask app context):

    from company_culture_LLM.store import upsert_company, get_company, all_companies
    from company_culture_LLM.seed_company import google

    upsert_company(google)
    profile = get_company("google")
"""

from __future__ import annotations

import re

from company import CompanyProfile
from model import Company, db


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
        "work_environment": c.work_environment,
        "pace": c.pace,
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
    profile_dict = profile.dict()

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
    return CompanyProfile.parse_obj(row.profile_json)


def all_companies() -> list[Company]:
    """Return all Company ORM rows (lightweight — profile_json included)."""
    return Company.query.order_by(Company.name).all()


def seed_all(profiles: list[CompanyProfile]) -> list[Company]:
    """Upsert a list of CompanyProfile objects. Useful for bulk seeding."""
    return [upsert_company(p) for p in profiles]
