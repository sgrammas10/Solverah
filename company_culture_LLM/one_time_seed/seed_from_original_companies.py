"""Seed all company profiles from the spreadsheet into the database.

Run from the project root after applying the migration:

    alembic upgrade head
    python -m company_culture_LLM.seed_from_xlsx

Requires DATABASE_URL in the environment (or a .env file).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from model import db, Company
from company_culture_LLM.parse_xlsx import parse_all
from company_culture_LLM.store import upsert_company


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def run_seed(verbose: bool = True) -> None:
    app = create_app()

    profiles = parse_all()
    if verbose:
        print(f"Parsed {len(profiles)} companies from spreadsheet")

    with app.app_context():
        seeded, updated = 0, 0
        for profile in profiles:
            name = profile.overview.name
            existing = Company.query.filter_by(
                slug=_slugify(name)
            ).first()
            upsert_company(profile)
            if existing:
                updated += 1
                if verbose:
                    print(f"  updated  {name}")
            else:
                seeded += 1
                if verbose:
                    print(f"  inserted {name}")

        print(f"\nDone — {seeded} inserted, {updated} updated.")


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


if __name__ == "__main__":
    run_seed()
