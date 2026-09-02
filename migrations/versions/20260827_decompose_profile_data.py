"""Phase 2a: decompose profile_data into the Part 4.3 profile tables.

Creates ``profiles``, ``profile_experiences``, ``profile_educations``, ``skills``,
``profile_skills`` and ``resumes``, and carries every existing ``profile_data``
blob across.

Three decisions are baked into this file and worth reading before running it.

**``user.profile_data`` is not dropped.**  Nothing reads or writes it after this
migration, and it stays for one release anyway: a rollback then means redeploying
the previous image, not restoring a dump.  ``docs/RUNBOOK_DATABASE_ROLLBACK.md``
exists and has been rehearsed, but exercising it costs downtime and this costs a
column.  The drop is the next release's migration.

**The carry-over is one pass, not a backfill job.**  There is no dual-write
window and no reconciliation loop.  Production data at this point is tester
accounts, and companies reseed from ``docs/company_profiles_in_db.xlsx``, so the
expensive machinery an expand/contract migration would otherwise need buys
nothing.  What it does instead is the honest minimum: every blob is decomposed
with the same pure code the application uses, and any blob that will not
decompose is carried into ``profiles.extra`` verbatim.  ``extra`` assembles back
to exactly what it holds, so "did not decompose" costs indexability, never data.

**It imports the application's decomposer.**  Migrations are normally frozen
against the code that wrote them, and this one is not: it calls
``solverah.domain.profile_document.decompose``.  That is a deliberate trade for a
one-shot cutover over disposable data -- duplicating eighty lines of promotion
rules would guarantee the copy and the original disagree eventually, and the
disagreement would be silent.  If this migration is ever run against data that
matters, read that module first and confirm it still means what it meant on
2026-08-27.

Revision ID: 20260827_profile_tables
Revises: 20260819_company_model
Create Date: 2026-08-27
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260827_profile_tables"
down_revision = "20260819_company_model"
branch_labels = None
depends_on = None


#: Part 4.1 rule 5: ``updated_at`` is the database's job. The profile write path
#: builds its UPDATE column by column from an optimistic-lock comparison, and a
#: column that write forgets is a column that stops being maintained.
_SET_UPDATED_AT = """
CREATE OR REPLACE FUNCTION solverah_set_updated_at() RETURNS trigger AS $BODY$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$BODY$ LANGUAGE plpgsql;
"""

_TRIGGERED_TABLES = (
    "profiles",
    "profile_experiences",
    "profile_educations",
    "profile_skills",
)


def _create_tables() -> None:
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("headline", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("location_state", sa.Text()),
        sa.Column("location_city", sa.Text()),
        sa.Column("phone", sa.Text()),
        sa.Column("linkedin_url", sa.Text()),
        sa.Column("portfolio_url", sa.Text()),
        sa.Column("career_status", sa.Text()),
        sa.Column("completeness", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    for table, extra_columns, indexes in (
        (
            "profile_experiences",
            [
                sa.Column("company_name", sa.Text(), nullable=False),
                sa.Column("title", sa.Text(), nullable=False),
                sa.Column("start_date", sa.Date()),
                sa.Column("end_date", sa.Date()),
                sa.Column(
                    "is_current", sa.Boolean(), nullable=False, server_default=sa.false()
                ),
                sa.Column("description", sa.Text()),
            ],
            ("ix_experiences_user", "uq_experiences_public_id"),
        ),
        (
            "profile_educations",
            [
                sa.Column("institution", sa.Text(), nullable=False),
                sa.Column("degree", sa.Text()),
                sa.Column("field", sa.Text()),
                sa.Column("start_date", sa.Date()),
                sa.Column("end_date", sa.Date()),
            ],
            ("ix_educations_user", "uq_educations_public_id"),
        ),
    ):
        op.create_table(
            table,
            sa.Column(
                "id", sa.BigInteger(), sa.Identity(always=True), nullable=False
            ),
            sa.Column(
                "public_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                server_default=sa.text("uuidv7()"),
            ),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            *extra_columns,
            sa.Column("source", sa.Text(), nullable=False, server_default="user"),
            sa.Column(
                "ordinal", sa.SmallInteger(), nullable=False, server_default="0"
            ),
            sa.Column(
                "extra",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(indexes[0], table, ["user_id", "ordinal"])
        op.create_index(indexes[1], table, ["public_id"], unique=True)

    op.create_table(
        "skills",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("onet_element_id", sa.Text()),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    # Trigram search over skill labels, so "Node.JS" finds the row whose label
    # says "Node.js". pg_trgm is declared in infra/docker/initdb/01-extensions.sql
    # and created as a step in CI; asserted here so a database missing it fails
    # on the migration rather than on the first query.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_skills_trgm",
        "skills",
        ["label"],
        postgresql_using="gin",
        postgresql_ops={"label": "gin_trgm_ops"},
    )

    op.create_table(
        "profile_skills",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("proficiency", sa.SmallInteger()),
        sa.Column("ordinal", sa.SmallInteger()),
        sa.Column("years", sa.Numeric(4, 1)),
        sa.Column("source", sa.Text(), nullable=False, server_default="user"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"]),
        sa.PrimaryKeyConstraint("user_id", "skill_id"),
        sa.CheckConstraint(
            "proficiency IS NULL OR (proficiency >= 1 AND proficiency <= 5)",
            name="ck_profile_skills_proficiency_range",
        ),
    )
    op.create_index("ix_profile_skills_skill", "profile_skills", ["skill_id"])

    op.create_table(
        "resumes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text()),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="stored"),
        sa.Column("parser_version", sa.Text()),
        sa.Column("parsed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resumes_user", "resumes", ["user_id", sa.text("created_at DESC")]
    )
    op.create_index("uq_resumes_public_id", "resumes", ["public_id"], unique=True)

    op.execute(_SET_UPDATED_AT)
    for table in _TRIGGERED_TABLES:
        op.execute(
            "CREATE TRIGGER trg_%s_updated_at BEFORE UPDATE ON %s "
            "FOR EACH ROW EXECUTE FUNCTION solverah_set_updated_at()" % (table, table)
        )


def _carry_over() -> None:
    """Move every ``user.profile_data`` blob into the new tables.

    One row at a time and one transaction for the lot, which is fine at this
    scale and would not be at another. A blob that raises is carried into
    ``profiles.extra`` verbatim rather than skipped: ``extra`` round-trips to
    exactly what it holds, so the user keeps their profile and loses only the
    indexability the decomposition would have given them.
    """
    from solverah.domain import profile_document

    bind = op.get_bind()
    rows = bind.execute(
        sa.text('SELECT id, profile_data FROM "user" ORDER BY id')
    ).fetchall()

    skill_ids = {}
    carried = decomposed = verbatim = 0

    for user_id, blob in rows:
        if isinstance(blob, str):
            # The column is `sqlalchemy.JSON`, which some drivers hand back as
            # text depending on how the row was written.
            try:
                blob = json.loads(blob)
            except ValueError:
                blob = None
        document = blob if isinstance(blob, dict) else {}

        try:
            state = profile_document.decompose(document)
            decomposed += 1
        except Exception:  # noqa: BLE001 -- a bad blob must not stop the migration
            state = profile_document.ProfileState(extra=dict(document))
            verbatim += 1

        bind.execute(
            sa.text(
                "INSERT INTO profiles (user_id, headline, summary, location_state, "
                "location_city, phone, linkedin_url, portfolio_url, career_status, "
                "completeness, extra, version) VALUES (:user_id, :headline, :summary, "
                ":location_state, :location_city, :phone, :linkedin_url, "
                ":portfolio_url, :career_status, :completeness, CAST(:extra AS jsonb), 0)"
            ),
            {
                "user_id": user_id,
                "completeness": state.completeness,
                "extra": json.dumps(state.extra),
                **{key: state.scalars.get(key) for key in (
                    "headline", "summary", "location_state", "location_city",
                    "phone", "linkedin_url", "portfolio_url", "career_status",
                )},
            },
        )

        for row in state.experiences:
            bind.execute(
                sa.text(
                    "INSERT INTO profile_experiences (user_id, company_name, title, "
                    "start_date, end_date, is_current, description, source, ordinal, "
                    "extra) VALUES (:user_id, :company_name, :title, :start_date, "
                    ":end_date, :is_current, :description, :source, :ordinal, "
                    "CAST(:extra AS jsonb))"
                ),
                {
                    "user_id": user_id,
                    "company_name": row.company_name,
                    "title": row.title,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "is_current": row.is_current,
                    "description": row.description,
                    "source": row.source,
                    "ordinal": row.ordinal,
                    "extra": json.dumps(row.extra),
                },
            )

        for row in state.educations:
            bind.execute(
                sa.text(
                    "INSERT INTO profile_educations (user_id, institution, degree, "
                    'field, start_date, end_date, source, ordinal, extra) '
                    "VALUES (:user_id, :institution, :degree, :field, :start_date, "
                    ":end_date, :source, :ordinal, CAST(:extra AS jsonb))"
                ),
                {
                    "user_id": user_id,
                    "institution": row.institution,
                    "degree": row.degree,
                    "field": row.field_of_study,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "source": row.source,
                    "ordinal": row.ordinal,
                    "extra": json.dumps(row.extra),
                },
            )

        for row in state.skills:
            if row.slug not in skill_ids:
                skill_ids[row.slug] = bind.execute(
                    sa.text(
                        "INSERT INTO skills (slug, label) VALUES (:slug, :label) "
                        "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug "
                        "RETURNING id"
                    ),
                    {"slug": row.slug, "label": row.label},
                ).scalar()
            bind.execute(
                sa.text(
                    "UPDATE skills SET aliases = aliases || ARRAY[:label]::text[] "
                    "WHERE id = :id AND label <> :label "
                    "AND NOT (:label = ANY(aliases))"
                ),
                {"id": skill_ids[row.slug], "label": row.label},
            )
            bind.execute(
                sa.text(
                    "INSERT INTO profile_skills (user_id, skill_id, label, "
                    "proficiency, ordinal, source) VALUES (:user_id, :skill_id, "
                    ":label, :proficiency, :ordinal, :source)"
                ),
                {
                    "user_id": user_id,
                    "skill_id": skill_ids[row.slug],
                    "label": row.label,
                    "proficiency": row.proficiency,
                    "ordinal": row.ordinal,
                    "source": row.source,
                },
            )

        if state.resume is not None:
            bind.execute(
                sa.text(
                    "INSERT INTO resumes (user_id, object_key, mime, size_bytes, "
                    "status) VALUES (:user_id, :object_key, :mime, :size_bytes, "
                    ":status)"
                ),
                {
                    "user_id": user_id,
                    "object_key": state.resume.object_key,
                    "mime": state.resume.mime,
                    "size_bytes": state.resume.size_bytes,
                    "status": state.resume.status,
                },
            )

        carried += 1

    print(
        "profile carry-over: %d users (%d decomposed, %d carried verbatim)"
        % (carried, decomposed, verbatim)
    )


def upgrade():
    _create_tables()
    _carry_over()


def downgrade():
    """Drop the profile tables. ``user.profile_data`` is still there.

    That is the whole point of not dropping the column in this migration: the
    downgrade is a drop rather than a reconstruction, because the data it would
    otherwise have to reconstruct never went away. Writes made *after* the
    upgrade are lost on downgrade, which is the same exposure as rolling back
    the deployment, and the reason the runbook's fast path is a pre-migration
    ``pg_dump``.
    """
    for table in _TRIGGERED_TABLES:
        op.execute("DROP TRIGGER IF EXISTS trg_%s_updated_at ON %s" % (table, table))
    op.execute("DROP FUNCTION IF EXISTS solverah_set_updated_at()")

    op.drop_table("resumes")
    op.drop_table("profile_skills")
    op.drop_table("skills")
    op.drop_table("profile_educations")
    op.drop_table("profile_experiences")
    op.drop_table("profiles")
