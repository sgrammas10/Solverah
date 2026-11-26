"""profile_onboarding -- the first-run "What brings you here?" answers on profiles

The first two steps of the new first-run flow (agreed by Sebastian and Julie,
2026-11-24) store two answers on the existing one-row-per-user profile table:

* ``career_moment`` -- which of six career moments brought the user here. A
  closed vocabulary, so it carries a CHECK on the six ids
  (``solverah.domain.profile.CAREER_MOMENTS``). NULL means "not answered yet",
  and the dashboard opens the first-run dialog while it is NULL.
* ``own_words`` -- an optional sentence or two, kept verbatim (trimmed) and
  never scored. The 1000-character cap is enforced in the domain layer, not
  here, so the cap can move without a migration.

Both are nullable with no default: every existing row reads as "not answered",
which is the intended state for current users.

Account deletion needs no new wiring: the tombstone rewrites the whole profile
document through ``profile_repository.update_document``, and both columns are
document scalars, so they are nulled with everything else.

BACKFILL
--------
None. There is nothing to derive a moment from.

REVERSIBILITY
-------------
``downgrade`` drops the constraint and both columns, and with them every answer
given since the upgrade. Downgrade the code with it: the profile repository
reads both columns.

Revision ID: 20261124_profile_onboarding
Revises: 20261123_user_company_lookup
Create Date: 2026-11-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20261124_profile_onboarding"
down_revision = "20261123_user_company_lookup"
branch_labels = None
depends_on = None

TABLE = "profiles"
CHECK = "ck_profiles_career_moment"
MOMENTS = (
    "off_at_work",
    "stay_or_go",
    "job_hunting",
    "between_jobs",
    "first_job",
    "curious",
)


def upgrade():
    op.add_column(TABLE, sa.Column("career_moment", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("own_words", sa.Text(), nullable=True))
    op.create_check_constraint(
        CHECK,
        TABLE,
        "career_moment IS NULL OR career_moment IN (%s)"
        % ", ".join("'%s'" % moment for moment in MOMENTS),
    )


def downgrade():
    op.drop_constraint(CHECK, TABLE, type_="check")
    op.drop_column(TABLE, "own_words")
    op.drop_column(TABLE, "career_moment")
