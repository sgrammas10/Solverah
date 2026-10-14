"""user_company_link -- "I took this job" (six-trait build, C6)

PRODUCT_DECISIONS.md §2, "The six-trait match model" (Sebastian, 2026-10-13), "What
changes the weights" item 4: after launch, 90-day check-ins through Pulse are linked to
the CompanyLens read by an "I took this job" action. This table is that action: one row
per (user, company, started_on), `ended_on` NULL while the job is current. C8 attaches
`pulse_checkins.company_link_id` to it in the next revision.

User-keyed: `started_on` is a date the user stated about their own working life. The
`user_id` FK carries no `ondelete`, like every other user-keyed table here; export and
deletion wiring is auth-accounts' and tests/test_export_delete_coverage.py names the
table until it lands. No score, gap or probability is stored on the row.

REVERSIBILITY
-------------
`downgrade` drops the table and the links in it. Nothing else reads it until C8's
`pulse_checkins.company_link_id`, which must be downgraded first (its own revision
depends on this one). The links themselves are lost; they are one click to restate.

Revision ID: 20261013_user_company_link
Revises: 20261013_envreport_outcomes
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "20261013_user_company_link"
down_revision = "20261013_envreport_outcomes"
branch_labels = None
depends_on = None

TABLE = "user_company_link"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "ended_on IS NULL OR ended_on >= started_on", name="ck_ucl_ended_after_started"
        ),
    )
    op.create_index("ix_ucl_user_started", TABLE, ["user_id", "started_on"], unique=False)
    op.create_index(
        "ix_ucl_one_open_per_user", TABLE, ["user_id"],
        unique=True, postgresql_where=sa.text("ended_on IS NULL"),
    )


def downgrade():
    op.drop_index("ix_ucl_one_open_per_user", table_name=TABLE)
    op.drop_index("ix_ucl_user_started", table_name=TABLE)
    op.drop_table(TABLE)
