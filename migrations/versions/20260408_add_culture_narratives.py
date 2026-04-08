"""Add culture_narrative_company and culture_narrative_employees columns to company table.

Splits the old single culture_narrative field into two separate columns:
one for what the company officially says, one for what employees report.

Revision ID: 20260408_add_culture_narratives
Revises: 20260406_add_pace_float
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "20260408_add_culture_narratives"
down_revision = "20260406_add_pace_float"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("company", sa.Column("culture_narrative_company", sa.Text(), nullable=True))
    op.add_column("company", sa.Column("culture_narrative_employees", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("company", "culture_narrative_employees")
    op.drop_column("company", "culture_narrative_company")
