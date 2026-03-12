"""Add resume_parse_correction table

Tracks corrections users make to parser-extracted resume fields so the parser
can be improved over time. One row per (user, resume_key, field).

Revision ID: 20260312_add_resume_parse_corrections
Revises: 20260203_add_email_confirmation_to_user
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260312_add_resume_parse_corrections"
down_revision = "20260203_add_email_confirmation_to_user"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "resume_parse_correction",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("resume_key", sa.String(length=500), nullable=False),
        sa.Column("field", sa.String(length=50), nullable=False),
        sa.Column("parsed_value", sa.JSON(), nullable=True),
        sa.Column("corrected_value", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "resume_key", "field",
            name="uq_correction_user_resume_field",
        ),
    )
    op.create_index(
        "ix_resume_parse_correction_user_id",
        "resume_parse_correction",
        ["user_id"],
    )


def downgrade():
    op.drop_index("ix_resume_parse_correction_user_id", table_name="resume_parse_correction")
    op.drop_table("resume_parse_correction")
