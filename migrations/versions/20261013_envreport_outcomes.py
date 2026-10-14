"""add five optional exploratory outcome columns to environment_reports

PRODUCT_DECISIONS.md §2, "The six-trait match model" (Sebastian, 2026-10-13): the
primary outcome stays the pre-registered `experienced_outcome` ("doing well" = 4 or
5). Five further outcomes are measured as EXPLORATORY, each a single optional 1..5
item asked after `experienced` on the Environment Report (form `env-v3-2026-10-13`):

- `outcome_satisfaction`
- `outcome_performance`
- `outcome_engagement`
- `outcome_sustainability`
- `outcome_retention_intention`

Each is a nullable SMALLINT with a CHECK of 1..5 (or NULL). NULL means "skipped" on an
env-v3 row and "never asked" on an older one; `version` tells the two apart, the same
rule `industry` follows. Values are stored RAW; the 0..1 mapping ((rating - 1) / 4) is
done at analysis time, never in storage. Every existing row gets NULL, which is the
correct "never asked".

The column list is frozen here as a literal rather than imported from `model.py`,
because a migration describes the schema as it was on the day it ran.

REVERSIBILITY
-------------
`downgrade` drops the five CHECKs and the five columns, and the answers with them.
Nothing reads them yet except the export; the training assembler adds them in a later
chunk (C6).

Revision ID: 20261013_envreport_outcomes
Revises: 20261013_company_evidence
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "20261013_envreport_outcomes"
down_revision = "20261013_company_evidence"
branch_labels = None
depends_on = None

OUTCOME_COLUMNS = (
    "outcome_satisfaction",
    "outcome_performance",
    "outcome_engagement",
    "outcome_sustainability",
    "outcome_retention_intention",
)


def upgrade():
    for column in OUTCOME_COLUMNS:
        op.add_column("environment_reports", sa.Column(column, sa.SmallInteger(), nullable=True))
        op.create_check_constraint(
            "ck_envreport_%s_range" % column,
            "environment_reports",
            "%s IS NULL OR (%s >= 1 AND %s <= 5)" % (column, column, column),
        )


def downgrade():
    for column in reversed(OUTCOME_COLUMNS):
        op.drop_constraint("ck_envreport_%s_range" % column, "environment_reports", type_="check")
        op.drop_column("environment_reports", column)
