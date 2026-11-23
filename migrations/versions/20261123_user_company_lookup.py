"""user_company_lookup -- which companies each user looked up in CompanyLens (G66)

G66 (2026-11-23, Sebastian's ruling): the CompanyLens list ("Your companies") must show
only the companies the signed-in user looked up through the research form, not every
company anyone researched. Nothing recorded the requesting user before this: a research
run is per company and shared, and a request that lands on a cached or in-flight run
writes no row at all. This table is that record -- one row per (user, company),
written by `POST /companies/research` once the request is accepted, cache hit or not.

No free text, no score: a user id, a company id and a timestamp. The `user_id` FK is
`ON DELETE CASCADE` so a hard-deleted user row never blocks on it; account deletion
(a tombstone, not a row delete) reaches it through auth-accounts' wiring, and
tests/test_export_delete_coverage.py names the table until that lands.

BACKFILL
--------
None, and none is possible: the requester of a past run was never stored anywhere
(not on `company_research_run`, not in any other table). Companies researched before
this revision therefore leave every user's list until that user asks for them again
-- which is a cache hit, free and instant, and records the lookup. `solverah_julie`
had zero research runs when this was written (2026-11-23), so nothing is lost there.

REVERSIBILITY
-------------
`downgrade` drops the table. `/me/matches` then has nothing to scope by; downgrade the
code with it.

Revision ID: 20261123_user_company_lookup
Revises: 20261013_pulse_company_link
Create Date: 2026-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "20261123_user_company_lookup"
down_revision = "20261013_pulse_company_link"
branch_labels = None
depends_on = None

TABLE = "user_company_lookup"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "company_id", name="uq_user_company_lookup"),
    )


def downgrade():
    op.drop_table(TABLE)
