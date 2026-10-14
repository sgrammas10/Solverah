"""experiments.status gains 'completed' -- an ended experiment must stop being 'active'

Found in the 2026-10-02 lane audit: `experiments.status` only knew `active` and
`abandoned`, the phase `ended` being derived from `ends_at` on read. Nothing ever
moved a naturally ended row off `active`, so `uq_experiments_one_active_per_user`
(partial on `status = 'active'`) and the service's 409 check kept refusing every
later start for that user, forever, and no UI could clear it.

A partial index cannot carry a time predicate (`now()` is not immutable), so the
fix is a third stored status, `completed`, which the service writes lazily once
`ends_at` has passed (`experiment_store.close_ended_experiments`). This migration:

- widens `ck_experiment_status_vocab` to `('active', 'completed', 'abandoned')`;
- backfills every row that is past its `ends_at` but still `active` to
  `completed` -- production holds such rows, and each one is a user who cannot
  start an experiment today. The backfill uses the database clock; the service's
  lazy close uses the request clock, and the boundary (`ends_at <= now`) is the
  same one `work_pulse.experiments.derive_phase` draws.

The partial unique index is unchanged: a `completed` row simply no longer
matches its predicate. `ck_experiment_abandoned_at_matches_status` is unchanged
too -- `completed` rows have no `abandoned_at`, as `active` rows never did.

REVERSIBILITY
-------------
`downgrade` relabels `completed` rows back to `active` (the pre-fix schema's own
representation of an ended experiment: `active`, with `ends_at` in the past) and
narrows the CHECK again. That relabel is only possible when every user holds at
most ONE row that is `active` or `completed`: two such rows -- a completed one
beside a running one, or two completed ones, which is the shape of every user
who has ever run two experiments under the fixed code -- would become two
`active` rows and trip `uq_experiments_one_active_per_user` mid-statement. The
old schema cannot hold either shape, so `downgrade` refuses up front with the
reason rather than failing on the index or picking a row to lose, the same
stance `20261002_envreport_subject` takes.

Revision ID: 20261002_experiment_completed
Revises: 20261002_envreport_subject
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20261002_experiment_completed"
down_revision = "20261002_envreport_subject"
branch_labels = None
depends_on = None

OLD_STATUSES = ("active", "abandoned")
NEW_STATUSES = ("active", "completed", "abandoned")


def upgrade():
    op.drop_constraint("ck_experiment_status_vocab", "experiments", type_="check")
    op.create_check_constraint(
        "ck_experiment_status_vocab", "experiments", "status IN %s" % (NEW_STATUSES,)
    )
    op.execute(
        "UPDATE experiments SET status = 'completed' "
        "WHERE status = 'active' AND ends_at <= now()"
    )


def downgrade():
    bind = op.get_bind()
    colliding = bind.execute(
        sa.text(
            "SELECT count(*) FROM ("
            "  SELECT user_id FROM experiments"
            "  WHERE status IN ('active', 'completed')"
            "  GROUP BY user_id HAVING count(*) > 1"
            ") s"
        )
    ).scalar()
    if colliding:
        raise RuntimeError(
            "%d user(s) hold more than one active-or-completed experiment; the "
            "pre-'completed' schema cannot represent that (relabelling them all "
            "'active' would trip uq_experiments_one_active_per_user). Abandon or "
            "delete all but one per user first." % colliding
        )
    op.execute("UPDATE experiments SET status = 'active' WHERE status = 'completed'")
    op.drop_constraint("ck_experiment_status_vocab", "experiments", type_="check")
    op.create_check_constraint(
        "ck_experiment_status_vocab", "experiments", "status IN %s" % (OLD_STATUSES,)
    )
