"""Phase 2, item 5: RANGE-partition the three high-volume tables.

`audit_log` by `created_at`, `match_recommendation` by `shown_at`, `rec_action`
by `acted_at`.  Storage change only: no column that anything reads changes type,
name or meaning, and no endpoint's response moves.

**The fourth table is deliberately not partitioned.**  Part 4 names four
high-volume tables.  The per-item response table on the person side is the
lowest-volume of them and is left exactly as it is, because it carries a
uniqueness guarantee over (submission, item).  Postgres requires the partition
key to be a member of every unique constraint on a partitioned table, so
partitioning it on its answer timestamp would force that column into the key and
turn "one answer per item per submission" into "one answer per item per
submission per instant" -- which is not a constraint at all.  A duplicate row
there changes `mean_pole`'s denominator and silently moves a score.  The
guarantee is worth more than the partition.

That table is not named anywhere in this file.  `tests/test_employer_visibility.py`
holds the person-side names to an allowlist (D-01), and this migration does not
touch the table -- explaining why would be the only reason to name it, and that
is not reason enough to widen an allowlist.

**Why a rebuild and not an ALTER.**  There is no `ALTER TABLE ... PARTITION BY`.
A partitioned table can only be born partitioned, so each of the three is created
alongside the original, its rows copied, the original dropped and the new one
renamed into place -- with every index, constraint and foreign key restated here
rather than inherited.

**Why the primary keys widen.**  Every unique constraint on a partitioned table
must contain the partition key, so `audit_log`'s key becomes `(id, created_at)`,
`match_recommendation`'s `(id, shown_at)` and `rec_action`'s `(id, acted_at)`.
`id` stays unique in practice -- it keeps the same sequence, detached and
reattached here so numbering continues rather than restarting.

**Why three other tables grow a `shown_at`.**  Widening `match_recommendation`'s
key invalidates every foreign key that named `id` alone:
`rec_action.recommendation_id`, `outcome_appeal.recommendation_id` and
`outcome_experienced.recommendation_id`.  Each of the three now carries the
parent's `shown_at` beside its id and references `(id, shown_at)`.

Dropping those foreign keys instead would have been one line each.  All three
feed the causal model, where a dangling recommendation reference produces no
error anyone sees -- just training rows that are quietly wrong.  Composite keys
keep the database saying no.

`outcome_appeal`'s uniqueness stays on `recommendation_id` alone.  One appeal per
recommendation is still the rule; widening it to `(recommendation_id, shown_at)`
would accept two appeals for one recommendation as long as their timestamps
differed, and only one of them could be about a real event.

**Partitions, and the absence of gaps.**  Each table gets a monthly partition for
every month its data spans, two months beyond the newest row, *and* a DEFAULT
partition.  A partitioned parent with no partition matching a row rejects the
insert outright ("no partition of relation ... found for row"), and `audit_log`
is written on the hottest endpoint in the application -- so the DEFAULT is not
tidiness, it is the difference between a late-arriving or clock-skewed row being
stored and a request failing.

The DEFAULT has one operational cost, recorded here because it stays invisible
until it bites: attaching a *new* monthly partition whose range overlaps rows
already sitting in DEFAULT requires scanning DEFAULT and fails if it finds any.
Months are therefore created ahead of the data rather than behind it, and the
job that adds next month's partition should run before rows need it.

Revision ID: 20260827_partition
Revises: 20260827_assessment_unify
Create Date: 2026-08-27

"""

import sqlalchemy as sa
from alembic import op

# Short on purpose. `alembic_version.version_num` is VARCHAR(32) and this project
# already carries revision ids of up to 42 characters, so `alembic upgrade head`
# fails on a fresh database today. That is not fixed here -- widening the column
# is its own migration with its own rollback story -- but nothing in this file
# makes it worse.
revision = "20260827_partition"
down_revision = "20260827_assessment_unify"
branch_labels = None
depends_on = None


#: The three tables that reference `match_recommendation`, and whether the
#: reference may be absent. `outcome_experienced` records placements that no
#: recommendation led to, so both of its foreign key columns are nullable
#: together -- a composite foreign key with any NULL member is not checked, which
#: is exactly the behaviour that case needs.
REFERENCERS = (
    ("rec_action", "fk_raction_recommendation", False),
    ("outcome_appeal", "fk_oappeal_recommendation", False),
    ("outcome_experienced", "fk_oexp_recommendation", True),
)


def _detach_sequence(conn, table):
    """Release *table*'s id sequence so dropping the table does not take it along.

    A sequence owned by a column is dropped with it. Detaching first is what lets
    the rebuilt table carry on numbering from where the old one stopped, instead
    of restarting at 1 and colliding with every row copied across.

    The name is read rather than assumed. The `<table>_id_seq` convention holds
    for all of these today, but a guessed-wrong sequence is only noticed when the
    first insert after the migration collides with an existing id.
    """
    sequence = conn.execute(
        sa.text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table}
    ).scalar()
    if not sequence:
        raise RuntimeError(
            "%s.id has no sequence, so rebuilding the table would drop its "
            "default and the next insert would fail on a null id." % table
        )
    conn.execute(sa.text("ALTER SEQUENCE %s OWNED BY NONE" % sequence))
    return sequence


def _rename_aside(conn, table):
    """Move *table* and its primary key out of the way, keeping both names free.

    The rebuilt table is created under the *final* name rather than a temporary
    one, so its partitions and constraints are born correctly named. Building it
    as `<table>_rebuilt` and renaming afterwards renames only the parent -- every
    partition underneath keeps the name it was created with, and a table left
    holding `audit_log_rebuilt_2026_08` is one the month-detach job will not find.

    Constraint names are per-table, but a primary key is backed by an *index*, and
    index names are unique across the whole schema. So the rebuilt table cannot be
    created carrying `audit_log_pkey` while the original still holds it -- the
    CREATE fails with `relation "audit_log_pkey" already exists`.

    So the original steps aside instead. Both the table and its primary key wear a
    `_superseded` suffix for the few statements between here and the DROP that
    removes them.
    """
    name = conn.execute(
        sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = CAST(:t AS regclass) AND contype = 'p'"
        ),
        {"t": table},
    ).scalar()
    if name:
        conn.execute(
            sa.text(
                'ALTER TABLE "%s" RENAME CONSTRAINT "%s" TO "%s_superseded"'
                % (table, name, name)
            )
        )
    conn.execute(sa.text('ALTER TABLE "%s" RENAME TO "%s_superseded"' % (table, table)))


def _create_partitions(conn, table, key, source):
    """Give *table* a monthly partition per month of *source*'s data, plus DEFAULT.

    Monthly partitions are created *before* the rows are copied and before the
    DEFAULT exists. Both orderings matter: rows copied into a table whose only
    partition is DEFAULT would all land there, and every monthly partition added
    afterwards would have to scan DEFAULT and would fail on the first overlapping
    row it found.
    """
    lo, hi = conn.execute(
        sa.text(
            "SELECT date_trunc('month', MIN(%s)), date_trunc('month', MAX(%s)) "
            "FROM %s" % (key, key, source)
        )
    ).one()

    # An empty table still needs somewhere for today's writes to go.
    if lo is None:
        lo, hi = conn.execute(
            sa.text("SELECT date_trunc('month', now()), date_trunc('month', now())")
        ).one()

    months = conn.execute(
        sa.text(
            "SELECT to_char(m, 'YYYY_MM'), m::date, (m + interval '1 month')::date "
            "FROM generate_series(:lo, :hi + interval '2 months', interval '1 month') AS m"
        ),
        {"lo": lo, "hi": hi},
    ).all()

    for label, start, stop in months:
        conn.execute(
            sa.text(
                'CREATE TABLE IF NOT EXISTS "%s_%s" PARTITION OF "%s" '
                "FOR VALUES FROM ('%s') TO ('%s')" % (table, label, table, start, stop)
            )
        )

    conn.execute(
        sa.text(
            'CREATE TABLE IF NOT EXISTS "%s_default" PARTITION OF "%s" DEFAULT'
            % (table, table)
        )
    )


def _drop_superseded(conn, table):
    """Remove the original, now that the rebuilt table holds its name and rows."""
    conn.execute(sa.text('DROP TABLE "%s_superseded"' % table))


def upgrade():
    conn = op.get_bind()

    # -- audit_log -----------------------------------------------------------------
    # Independent of the other two: nothing references it, and it references only
    # `users`. Postgres has allowed outgoing foreign keys from partitioned tables
    # since 12, so that reference survives the rebuild unchanged.
    sequence = _detach_sequence(conn, "audit_log")
    _rename_aside(conn, "audit_log")
    conn.execute(
        sa.text(
            """
            CREATE TABLE audit_log (
                id integer NOT NULL DEFAULT nextval('%s'),
                actor_user_id integer,
                action varchar(50) NOT NULL,
                resource varchar(100) NOT NULL,
                ip_address varchar(64),
                user_agent varchar(300),
                "metadata" json,
                created_at timestamp without time zone DEFAULT now() NOT NULL,
                CONSTRAINT audit_log_pkey PRIMARY KEY (id, created_at),
                CONSTRAINT audit_log_actor_user_id_fkey
                    FOREIGN KEY (actor_user_id) REFERENCES users (id)
            ) PARTITION BY RANGE (created_at)
            """
            % sequence
        )
    )
    _create_partitions(conn, "audit_log", "created_at", "audit_log_superseded")
    conn.execute(
        sa.text(
            'INSERT INTO audit_log (id, actor_user_id, action, resource, '
            'ip_address, user_agent, "metadata", created_at) '
            'SELECT id, actor_user_id, action, resource, ip_address, user_agent, '
            '"metadata", created_at FROM audit_log_superseded'
        )
    )
    _drop_superseded(conn, "audit_log")
    conn.execute(sa.text("ALTER SEQUENCE %s OWNED BY audit_log.id" % sequence))

    # -- the referencing foreign keys come off first --------------------------------
    # `match_recommendation.id` stops being unique on its own the moment the table
    # is partitioned, so every foreign key naming it alone has to go before the
    # rebuild and come back afterwards as a composite.
    for table, _name, _nullable in REFERENCERS:
        constraint = conn.execute(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = CAST(:t AS regclass) AND contype = 'f' "
                "AND confrelid = 'match_recommendation'::regclass"
            ),
            {"t": table},
        ).scalar()
        if constraint:
            conn.execute(
                sa.text('ALTER TABLE "%s" DROP CONSTRAINT "%s"' % (table, constraint))
            )

    # -- match_recommendation -------------------------------------------------------
    # The four CHECK constraints are restated by name. A rebuild that quietly lost
    # one would leave p_fit free to hold 1.7 and nothing would notice until a
    # probability left the model looking like a certainty.
    sequence = _detach_sequence(conn, "match_recommendation")
    _rename_aside(conn, "match_recommendation")
    conn.execute(
        sa.text(
            """
            CREATE TABLE match_recommendation (
                id integer NOT NULL DEFAULT nextval('%s'),
                user_id integer NOT NULL,
                company_id integer NOT NULL,
                model_run_id integer,
                p_fit double precision,
                p_fit_low double precision,
                p_fit_high double precision,
                "rank" integer,
                is_exploration boolean DEFAULT false NOT NULL,
                channel varchar(16) DEFAULT 'onsite' NOT NULL,
                shown_at timestamp without time zone DEFAULT now() NOT NULL,
                CONSTRAINT match_recommendation_pkey PRIMARY KEY (id, shown_at),
                CONSTRAINT match_recommendation_user_id_fkey
                    FOREIGN KEY (user_id) REFERENCES users (id),
                CONSTRAINT match_recommendation_company_id_fkey
                    FOREIGN KEY (company_id) REFERENCES company (id),
                CONSTRAINT match_recommendation_model_run_id_fkey
                    FOREIGN KEY (model_run_id) REFERENCES model_run (id),
                CONSTRAINT ck_mrec_pfit_range
                    CHECK (p_fit IS NULL OR (p_fit >= 0 AND p_fit <= 1)),
                CONSTRAINT ck_mrec_pfit_low_range
                    CHECK (p_fit_low IS NULL OR (p_fit_low >= 0 AND p_fit_low <= 1)),
                CONSTRAINT ck_mrec_pfit_high_range
                    CHECK (p_fit_high IS NULL OR (p_fit_high >= 0 AND p_fit_high <= 1)),
                CONSTRAINT ck_mrec_channel_vocab
                    CHECK (channel IN ('onsite', 'email'))
            ) PARTITION BY RANGE (shown_at)
            """
            % sequence
        )
    )
    _create_partitions(
        conn, "match_recommendation", "shown_at", "match_recommendation_superseded"
    )
    conn.execute(
        sa.text(
            'INSERT INTO match_recommendation (id, user_id, company_id, '
            'model_run_id, p_fit, p_fit_low, p_fit_high, "rank", is_exploration, '
            "channel, shown_at) "
            'SELECT id, user_id, company_id, model_run_id, p_fit, p_fit_low, '
            'p_fit_high, "rank", is_exploration, channel, shown_at '
            "FROM match_recommendation_superseded"
        )
    )
    _drop_superseded(conn, "match_recommendation")
    conn.execute(
        sa.text("ALTER SEQUENCE %s OWNED BY match_recommendation.id" % sequence)
    )
    op.create_index(
        "ix_match_recommendation_user_id", "match_recommendation", ["user_id"]
    )
    op.create_index(
        "ix_match_recommendation_company_id", "match_recommendation", ["company_id"]
    )

    # -- rec_action -----------------------------------------------------------------
    # Partitioned by `acted_at`, its own event time, while `shown_at` is a copy of
    # the parent's and exists only to complete the foreign key. The two timestamps
    # mean different things and the copy is taken by join, not by assumption.
    sequence = _detach_sequence(conn, "rec_action")
    _rename_aside(conn, "rec_action")
    conn.execute(
        sa.text(
            """
            CREATE TABLE rec_action (
                id integer NOT NULL DEFAULT nextval('%s'),
                recommendation_id integer NOT NULL,
                shown_at timestamp without time zone NOT NULL,
                action varchar(16) NOT NULL,
                acted_at timestamp without time zone DEFAULT now() NOT NULL,
                CONSTRAINT rec_action_pkey PRIMARY KEY (id, acted_at),
                CONSTRAINT ck_raction_action_vocab CHECK (action IN (
                    'viewed', 'saved', 'passed', 'applied', 'interviewed',
                    'offered', 'hired', 'accepted', 'declined'))
            ) PARTITION BY RANGE (acted_at)
            """
            % sequence
        )
    )
    _create_partitions(conn, "rec_action", "acted_at", "rec_action_superseded")
    conn.execute(
        sa.text(
            "INSERT INTO rec_action (id, recommendation_id, shown_at, action, "
            "acted_at) "
            "SELECT r.id, r.recommendation_id, m.shown_at, r.action, r.acted_at "
            "FROM rec_action_superseded r "
            "JOIN match_recommendation m ON m.id = r.recommendation_id"
        )
    )
    _drop_superseded(conn, "rec_action")
    conn.execute(sa.text("ALTER SEQUENCE %s OWNED BY rec_action.id" % sequence))
    op.create_index(
        "ix_rec_action_recommendation_id", "rec_action", ["recommendation_id"]
    )

    # -- the two outcome tables keep their rows and grow a column --------------------
    # Neither is partitioned, so neither needs a rebuild: an ALTER is enough, and
    # an ALTER preserves the rows without a copy.
    for table, _name, nullable in REFERENCERS[1:]:
        op.add_column(table, sa.Column("shown_at", sa.DateTime(), nullable=True))
        conn.execute(
            sa.text(
                "UPDATE %s AS t SET shown_at = m.shown_at "
                "FROM match_recommendation m WHERE m.id = t.recommendation_id" % table
            )
        )
        if not nullable:
            op.alter_column(table, "shown_at", nullable=False)

    # -- and the composite foreign keys go back on ----------------------------------
    for table, name, _nullable in REFERENCERS:
        op.create_foreign_key(
            name,
            table,
            "match_recommendation",
            ["recommendation_id", "shown_at"],
            ["id", "shown_at"],
        )


def downgrade():
    """Rebuild the three tables unpartitioned and drop the carried `shown_at`.

    Rehearsed as upgrade -> downgrade -> upgrade with rows in every table, because
    Phase 2's rollback story is `flask db downgrade` rather than a snapshot
    restore, and that is only true for as long as each migration keeps it true.
    """
    conn = op.get_bind()

    for table, name, _nullable in REFERENCERS:
        conn.execute(sa.text('ALTER TABLE "%s" DROP CONSTRAINT "%s"' % (table, name)))

    # -- rec_action back to a plain table -------------------------------------------
    op.drop_index("ix_rec_action_recommendation_id", "rec_action")
    sequence = _detach_sequence(conn, "rec_action")
    _rename_aside(conn, "rec_action")
    conn.execute(
        sa.text(
            """
            CREATE TABLE rec_action (
                id integer NOT NULL DEFAULT nextval('%s'),
                recommendation_id integer NOT NULL,
                action varchar(16) NOT NULL,
                acted_at timestamp without time zone DEFAULT now() NOT NULL,
                CONSTRAINT rec_action_pkey PRIMARY KEY (id),
                CONSTRAINT ck_raction_action_vocab CHECK (action IN (
                    'viewed', 'saved', 'passed', 'applied', 'interviewed',
                    'offered', 'hired', 'accepted', 'declined'))
            )
            """
            % sequence
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO rec_action (id, recommendation_id, action, acted_at) "
            "SELECT id, recommendation_id, action, acted_at FROM rec_action_superseded"
        )
    )
    _drop_superseded(conn, "rec_action")
    conn.execute(sa.text("ALTER SEQUENCE %s OWNED BY rec_action.id" % sequence))
    op.create_index(
        "ix_rec_action_recommendation_id", "rec_action", ["recommendation_id"]
    )

    # -- match_recommendation back to a plain table ---------------------------------
    op.drop_index("ix_match_recommendation_company_id", "match_recommendation")
    op.drop_index("ix_match_recommendation_user_id", "match_recommendation")
    sequence = _detach_sequence(conn, "match_recommendation")
    _rename_aside(conn, "match_recommendation")
    conn.execute(
        sa.text(
            """
            CREATE TABLE match_recommendation (
                id integer NOT NULL DEFAULT nextval('%s'),
                user_id integer NOT NULL,
                company_id integer NOT NULL,
                model_run_id integer,
                p_fit double precision,
                p_fit_low double precision,
                p_fit_high double precision,
                "rank" integer,
                is_exploration boolean DEFAULT false NOT NULL,
                channel varchar(16) DEFAULT 'onsite' NOT NULL,
                shown_at timestamp without time zone DEFAULT now() NOT NULL,
                CONSTRAINT match_recommendation_pkey PRIMARY KEY (id),
                CONSTRAINT match_recommendation_user_id_fkey
                    FOREIGN KEY (user_id) REFERENCES users (id),
                CONSTRAINT match_recommendation_company_id_fkey
                    FOREIGN KEY (company_id) REFERENCES company (id),
                CONSTRAINT match_recommendation_model_run_id_fkey
                    FOREIGN KEY (model_run_id) REFERENCES model_run (id),
                CONSTRAINT ck_mrec_pfit_range
                    CHECK (p_fit IS NULL OR (p_fit >= 0 AND p_fit <= 1)),
                CONSTRAINT ck_mrec_pfit_low_range
                    CHECK (p_fit_low IS NULL OR (p_fit_low >= 0 AND p_fit_low <= 1)),
                CONSTRAINT ck_mrec_pfit_high_range
                    CHECK (p_fit_high IS NULL OR (p_fit_high >= 0 AND p_fit_high <= 1)),
                CONSTRAINT ck_mrec_channel_vocab
                    CHECK (channel IN ('onsite', 'email'))
            )
            """
            % sequence
        )
    )
    conn.execute(
        sa.text(
            'INSERT INTO match_recommendation (id, user_id, company_id, '
            'model_run_id, p_fit, p_fit_low, p_fit_high, "rank", is_exploration, '
            "channel, shown_at) "
            'SELECT id, user_id, company_id, model_run_id, p_fit, p_fit_low, '
            'p_fit_high, "rank", is_exploration, channel, shown_at '
            "FROM match_recommendation_superseded"
        )
    )
    _drop_superseded(conn, "match_recommendation")
    conn.execute(
        sa.text("ALTER SEQUENCE %s OWNED BY match_recommendation.id" % sequence)
    )
    op.create_index(
        "ix_match_recommendation_user_id", "match_recommendation", ["user_id"]
    )
    op.create_index(
        "ix_match_recommendation_company_id", "match_recommendation", ["company_id"]
    )

    # -- audit_log back to a plain table --------------------------------------------
    sequence = _detach_sequence(conn, "audit_log")
    _rename_aside(conn, "audit_log")
    conn.execute(
        sa.text(
            """
            CREATE TABLE audit_log (
                id integer NOT NULL DEFAULT nextval('%s'),
                actor_user_id integer,
                action varchar(50) NOT NULL,
                resource varchar(100) NOT NULL,
                ip_address varchar(64),
                user_agent varchar(300),
                "metadata" json,
                created_at timestamp without time zone DEFAULT now() NOT NULL,
                CONSTRAINT audit_log_pkey PRIMARY KEY (id),
                CONSTRAINT audit_log_actor_user_id_fkey
                    FOREIGN KEY (actor_user_id) REFERENCES users (id)
            )
            """
            % sequence
        )
    )
    conn.execute(
        sa.text(
            'INSERT INTO audit_log (id, actor_user_id, action, resource, '
            'ip_address, user_agent, "metadata", created_at) '
            'SELECT id, actor_user_id, action, resource, ip_address, user_agent, '
            '"metadata", created_at FROM audit_log_superseded'
        )
    )
    _drop_superseded(conn, "audit_log")
    conn.execute(sa.text("ALTER SEQUENCE %s OWNED BY audit_log.id" % sequence))

    # -- the carried columns go last ------------------------------------------------
    # After the foreign keys that needed them are already gone.
    for table, _name, _nullable in REFERENCERS[1:]:
        op.drop_column(table, "shown_at")

    for table, _name, _nullable in REFERENCERS:
        op.create_foreign_key(
            None, table, "match_recommendation", ["recommendation_id"], ["id"]
        )
