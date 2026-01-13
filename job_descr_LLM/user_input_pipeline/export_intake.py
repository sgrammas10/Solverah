"""Export intake submissions from Postgres into a dataset manifest."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine


@dataclass
class IntakeExporter:
    dsn: str
    query: str = (
        "SELECT id, first_name, last_name, email, state, resume_key, resume_mime, "
        "resume_size_bytes, created_at FROM intake_submissions"
    )

    def export(self, output_csv: Path) -> Path:
        output_csv = Path(output_csv)
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(self.dsn)
        df = pd.read_sql(self.query, con=engine)
        df.to_csv(output_csv, index=False)
        return output_csv


def export_from_env(version: str = "v1") -> Path:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL environment variable is required for export")
    exporter = IntakeExporter(dsn=dsn)
    dataset_root = Path("datasets") / version
    return exporter.export(dataset_root / "intake.csv")


if __name__ == "__main__":
    export_from_env()