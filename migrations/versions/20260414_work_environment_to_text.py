"""Widen work_environment column from VARCHAR(200) to TEXT.

LLM-generated company profiles produce work_environment values that exceed
the 200-character limit. Changing to TEXT removes the constraint.

Revision ID: 20260414_work_env_to_text
Revises: 20260408_add_culture_narratives
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

# Renamed from "20260414_work_environment_to_text" (33 chars): over the VARCHAR(32) limit of
# alembic_version.version_num. See tests/test_migrations_chain.py.
revision = "20260414_work_env_to_text"
down_revision = "20260408_add_culture_narratives"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "company",
        "work_environment",
        type_=sa.Text(),
        existing_type=sa.String(length=200),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "company",
        "work_environment",
        type_=sa.String(length=200),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
