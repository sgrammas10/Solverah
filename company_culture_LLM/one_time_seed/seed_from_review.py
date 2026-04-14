"""seed_from_review.py

Seeds all company profiles from the reviewed backfill spreadsheet into the database.

Run from the project root after confirming the REVIEW xlsx looks correct:

    python -m company_culture_LLM.seed_from_review

Requires DATABASE_URL in the environment (or a .env file).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from model import db
from company_culture_LLM.parse_xlsx import parse_all
from company_culture_LLM.store import upsert_company, _slugify

REVIEW_XLSX = Path(__file__).resolve().parent.parent / "docs" / "Original profiles with culture narratives REVIEW.xlsx"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def run_seed(verbose: bool = True) -> None:
    if not REVIEW_XLSX.exists():
        sys.exit(f"Error: review file not found: {REVIEW_XLSX}")

    app = create_app()

    profiles = parse_all(REVIEW_XLSX)
    if verbose:
        print(f"Parsed {len(profiles)} companies from review spreadsheet")

    with app.app_context():
        seeded, updated = 0, 0
        for profile in profiles:
            name = profile.overview.name
            from model import Company
            existing = Company.query.filter_by(slug=_slugify(name)).first()
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


if __name__ == "__main__":
    run_seed()
