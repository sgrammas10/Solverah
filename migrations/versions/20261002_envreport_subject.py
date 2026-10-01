"""add environment_reports.subject -- a report can describe the job BEFORE this one

Sebastian, 2026-10-01 (PRODUCT_DECISIONS.md §2, "Environment-instrument rulings"):
a user may file ONE report about a past job -- the one before their current or
most recent job -- once they have filed a report about the current one. Those
rows are exploratory-only in the first outcome-fit pre-registration (Amendment 1).

Shaped as a column on the existing table rather than a second table, because a
past report is the same instrument, scored the same way, with the same six child
score rows:

- `subject` TEXT NOT NULL, server default `'current'`. Every row written before
  this migration described the user's current (or most recent) job, so the
  default backfills them correctly in the same statement.
- CHECK `ck_envreport_subject_vocab`: `current` or `past`, nothing else.
- CHECK `ck_envreport_past_not_first_job`: a past row can never carry
  `career_status = 'first_job'`. A never-employed user has no job before their
  current one either, and the service already refuses them with
  `first_job_no_role`; this is the same rule held at the database.

`career_status` keeps its meaning on a past row: the user's status WHEN THEY
FILED, not a description of the past job. The vocabulary is frozen here as a
literal rather than imported from `model.py`, because a migration describes the
schema as it was on the day it ran.

REVERSIBILITY
-------------
`downgrade` drops both constraints and the column. Past rows would then be
indistinguishable from current ones, and the latest-report read would start
returning a past report, so a downgrade on a database holding past rows must
first delete them: `downgrade` refuses rather than silently relabelling them.

Revision ID: 20261002_envreport_subject
Revises: 20261001_envreport_industry
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20261002_envreport_subject"
down_revision = "20261001_envreport_industry"
branch_labels = None
depends_on = None

SUBJECTS = ("current", "past")


def upgrade():
    op.add_column(
        "environment_reports",
        sa.Column("subject", sa.Text(), nullable=False, server_default="current"),
    )
    op.create_check_constraint(
        "ck_envreport_subject_vocab",
        "environment_reports",
        "subject IN %s" % (SUBJECTS,),
    )
    op.create_check_constraint(
        "ck_envreport_past_not_first_job",
        "environment_reports",
        "subject = 'current' OR career_status <> 'first_job'",
    )


def downgrade():
    bind = op.get_bind()
    past_rows = bind.execute(
        sa.text("SELECT count(*) FROM environment_reports WHERE subject <> 'current'")
    ).scalar()
    if past_rows:
        raise RuntimeError(
            "%d past-job environment report row(s) exist; dropping `subject` would "
            "relabel them as current reports. Delete them first if that is intended."
            % past_rows
        )
    op.drop_constraint("ck_envreport_past_not_first_job", "environment_reports", type_="check")
    op.drop_constraint("ck_envreport_subject_vocab", "environment_reports", type_="check")
    op.drop_column("environment_reports", "subject")
