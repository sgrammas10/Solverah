"""pulse_checkins.company_link_id -- attach the active "I took this job" link (C8)

PRODUCT_DECISIONS.md §2, "The six-trait match model", "What changes the weights" item
4: after launch, 90-day check-ins through Pulse are linked to the CompanyLens read by
an "I took this job" action. `20261013_user_company_link` (C6) built that action's
table; this revision adds the pointer on the check-in side.

Nullable, `ondelete="SET NULL"`: deleting the link -- by the user through
`DELETE /me/company-links/<id>`, or in bulk through
`company_evidence_store.delete_company_links_for_user` during account deletion --
must never block on, or delete, the check-in it was attached to. Pulse check-ins hold
no free text and already ride the account-deletion tombstone de-identified
(`PulseCheckin`'s docstring, D-7b); this column does not change that -- it just goes
to NULL.

No ~90-day check-in schedule is wired to this column. That is a follow-up idea, not
part of this build.

REVERSIBILITY
-------------
`downgrade` drops the column. Nothing downstream of it needs restating; the check-ins
themselves are untouched.

Revision ID: 20261013_pulse_company_link
Revises: 20261013_user_company_link
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "20261013_pulse_company_link"
down_revision = "20261013_user_company_link"
branch_labels = None
depends_on = None

TABLE = "pulse_checkins"
COLUMN = "company_link_id"


def upgrade():
    op.add_column(TABLE, sa.Column(COLUMN, sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_pulse_checkins_company_link_id",
        TABLE,
        "user_company_link",
        [COLUMN],
        ["id"],
        ondelete="SET NULL",
    )
    # An ON DELETE SET NULL target is scanned on every delete of the referenced
    # link; index it (the 20260928 ledger-index rule).
    op.create_index("ix_pulse_checkins_company_link", TABLE, [COLUMN])


def downgrade():
    op.drop_index("ix_pulse_checkins_company_link", table_name=TABLE)
    op.drop_constraint("fk_pulse_checkins_company_link_id", TABLE, type_="foreignkey")
    op.drop_column(TABLE, COLUMN)
