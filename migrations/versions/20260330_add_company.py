"""Add company table

Stores company profiles with the 8 culture dimensions as queryable columns
alongside a full profile JSON blob.

Revision ID: 20260330_add_company
Revises: 20260312_add_resume_parse_corrections
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20260330_add_company"
down_revision = "20260312_add_resume_parse_corrections"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        # Categorical culture dimensions
        sa.Column("work_environment", sa.String(length=200), nullable=True),
        sa.Column("pace", sa.String(length=100), nullable=True),
        # Numeric culture dimensions (0.0–1.0)
        sa.Column("empathy", sa.Float(), nullable=True),
        sa.Column("creative_drive", sa.Float(), nullable=True),
        sa.Column("adaptability", sa.Float(), nullable=True),
        sa.Column("futuristic", sa.Float(), nullable=True),
        sa.Column("harmony", sa.Float(), nullable=True),
        sa.Column("data_orientation", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_company_slug", "company", ["slug"])


def downgrade():
    op.drop_index("ix_company_slug", table_name="company")
    op.drop_table("company")
