"""Phase 2d: unify the five assessment products onto Part 4.4's tables.

Creates ``assessment_forms`` and ``assessment_submissions`` and carries the three
current storage homes into them:

* ``user_intake.wpl_*``   -> one ``work_pulse`` submission per user
* ``user_intake.wpll_*``  -> one ``wpll`` submission per user
* ``profiles.extra``'s ``focus_type_result`` / ``manager_match_result``
  -> one ``focus_type`` / ``manager_match`` submission per user
* ``assessment_response`` / ``person_dimension_score`` -> one ``core`` submission
  per distinct sitting, joined by ``public_id``

Four decisions are baked into this file.

**``user_intake``'s columns are not dropped.**  Nothing reads ``wpl_answers``,
``wpl_narrative``, ``wpl_result``, ``wpl_completed_at``, ``wpll_answers``,
``wpll_insight_text`` or ``wpll_completed_at`` after this migration, and they stay
for one release anyway -- the same one-release stay ``users.profile_data`` is
serving since 2a.  A rollback within that window is a redeploy of the previous
image, not a database restore.  ``selected_statement_ids`` stays permanently: it
is intake data, not an assessment, and no instrument produces it.

**``profiles.extra``'s two keys *are* removed.**  Unlike the ``user_intake``
columns, those are not inert -- ``load_document`` assembles ``extra`` into the
profile document, so a copy left behind would still be on the wire and a reader
could not tell which one it was seeing.  The application merges the submission
row over the top unconditionally, so a key missed here is shadowed rather than
authoritative; removing it is what makes the row the only source rather than
merely the winning one.

**The core join key is the existing id, not a new one.**  Each distinct
``assessment_response.submission_id`` becomes one ``assessment_submissions`` row
whose ``public_id`` *is* that value parsed as a UUID -- the ids were
``uuid4().hex`` and parse cleanly.  Nothing on the person-side tables is altered:
no column added, no type changed, no row rewritten.  D-01's doorway is exactly as
wide after this migration as before it, which was a condition of the phase.

**It imports the application's item file reader**, the same trade 2a made for
``profile_document.decompose``.  One call, ``assessment_form.scoring_key_version``
and the item file's own ``form_version``, so that ``core``'s seeded
``assessment_forms.definition`` states the instrument identity rather than a
copy of it that can drift.  If this migration is ever run against data that
matters, confirm that module still means what it meant on 2026-08-27.

Revision ID: 20260827_assessment_unify
Revises: 20260827_users_table
Create Date: 2026-08-27
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260827_assessment_unify"
down_revision = "20260827_users_table"
branch_labels = None
depends_on = None


#: The four instruments whose questions ship in the client bundle. Their
#: ``form_version`` is a placeholder for exactly that reason -- there is no
#: server-side definition to version -- and it exists because the composite
#: foreign key into ``assessment_forms`` would otherwise be unenforceable for
#: four products out of five. Kept in step with
#: ``assessment_service.CLIENT_FORM_VERSION``.
CLIENT_FORM_VERSION = "v1"

CLIENT_RENDERED = ("work_pulse", "wpll", "focus_type", "manager_match")

#: ``profiles.extra`` key -> the kind that owns it from now on.
PROFILE_RESULT_KEYS = {
    "focus_type_result": "focus_type",
    "manager_match_result": "manager_match",
}


def _create_tables() -> None:
    op.create_table(
        "assessment_forms",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column(
            "definition",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "version", name="uq_assessment_forms_kind_version"),
        sa.CheckConstraint(
            "kind IN ('core','work_pulse','wpll','focus_type','manager_match')",
            name="ck_assessment_forms_kind",
        ),
    )

    op.create_table(
        "assessment_submissions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("form_version", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'in_progress'")
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("narrative", sa.Text()),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("scored_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["kind", "form_version"],
            ["assessment_forms.kind", "assessment_forms.version"],
            name="fk_assessment_submissions_form",
        ),
        sa.CheckConstraint(
            "kind IN ('core','work_pulse','wpll','focus_type','manager_match')",
            name="ck_assessment_submissions_kind",
        ),
        sa.CheckConstraint(
            "status IN ('in_progress','complete','scored')",
            name="ck_assessment_submissions_status",
        ),
        sa.CheckConstraint(
            "kind <> 'core' OR (result IS NULL AND answers IS NULL)",
            name="ck_assessment_submissions_core_carries_nothing",
        ),
    )

    # Partial, so the four single-row instruments get a real one-current-sitting
    # constraint while `core` stays append-only. The asymmetry is the schema's
    # to state, not a convention for every reader to remember.
    op.create_index(
        "uq_assessment_submissions_current",
        "assessment_submissions",
        ["user_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind <> 'core'"),
    )
    op.create_index(
        "ix_submissions_user",
        "assessment_submissions",
        ["user_id", "kind", sa.text("completed_at DESC")],
    )


def _core_definition() -> dict:
    """The item file's identity, for ``core``'s seeded form row.

    Read from the file rather than written out here, so the row states what the
    instrument is rather than what someone believed it was on the day this
    migration was written.
    """
    from assessment_form import DEFAULT_ITEMS_PATH, scoring_key_version, _load_doc

    doc = _load_doc(DEFAULT_ITEMS_PATH)
    return {
        "source": "server",
        "served_by": "assessment_form.get_form",
        "form_version": doc.get("form_version"),
        "scoring_key_version": scoring_key_version(),
        "item_count": len(doc.get("items") or []),
    }


def _seed_forms() -> None:
    """One published row per instrument, plus every core version already on disk.

    ``definition`` is empty for the four client-rendered instruments on purpose.
    Their questions ship in the client bundle; writing a copy here would create a
    second source of truth for something no server code reads, and the honest
    record until Phase 4 moves them server-side is that they are not here.
    """
    connection = op.get_bind()

    for kind in CLIENT_RENDERED:
        connection.execute(
            sa.text(
                "INSERT INTO assessment_forms (kind, version, definition, published_at) "
                "VALUES (:kind, :version, '{\"source\": \"client\"}'::jsonb, now()) "
                "ON CONFLICT (kind, version) DO NOTHING"
            ),
            {"kind": kind, "version": CLIENT_FORM_VERSION},
        )

    core = _core_definition()
    connection.execute(
        sa.text(
            "INSERT INTO assessment_forms (kind, version, definition, published_at) "
            "VALUES ('core', :version, CAST(:definition AS jsonb), now()) "
            "ON CONFLICT (kind, version) DO NOTHING"
        ),
        {"version": core["form_version"], "definition": json.dumps(core)},
    )

    # Every core version that already has rows on disk, including superseded
    # ones. Registered with a null `published_at` and an empty definition: the
    # version demonstrably existed, and nobody is publishing a definition for an
    # item file that is no longer the active one.
    connection.execute(
        sa.text(
            "INSERT INTO assessment_forms (kind, version, definition) "
            "SELECT DISTINCT 'core', form_version, '{}'::jsonb "
            "FROM assessment_response "
            "ON CONFLICT (kind, version) DO NOTHING"
        )
    )


def _carry_work_pulse() -> None:
    """``user_intake.wpl_*`` -> one ``work_pulse`` submission per user.

    ``status`` reproduces the two-commit sequence's outcome rather than assuming
    it succeeded: a row with answers and no result is exactly the ``complete``
    state the resubmit path answers 422 for, and flattening it to ``scored``
    would tell those users their narrative is ready.
    """
    op.execute(
        """
        INSERT INTO assessment_submissions
            (user_id, kind, form_version, status, result, narrative, answers,
             started_at, completed_at, scored_at)
        SELECT ui.user_id,
               'work_pulse',
               '%(version)s',
               CASE WHEN ui.wpl_result IS NULL THEN 'complete' ELSE 'scored' END,
               CAST(ui.wpl_result AS jsonb),
               ui.wpl_narrative,
               CAST(ui.wpl_answers AS jsonb),
               COALESCE(ui.wpl_completed_at, ui.created_at),
               ui.wpl_completed_at,
               CASE WHEN ui.wpl_result IS NULL THEN NULL ELSE ui.wpl_completed_at END
        FROM   user_intake ui
        WHERE  ui.wpl_completed_at IS NOT NULL OR ui.wpl_answers IS NOT NULL
        """ % {"version": CLIENT_FORM_VERSION}
    )


def _carry_wpll() -> None:
    """``user_intake.wpll_*`` -> one ``wpll`` submission per user.

    Only rows that actually carry a sitting. ``wpll_answers`` is
    ``NOT NULL DEFAULT '[]'``, so every intake row has the column populated and a
    naive copy would manufacture a completed WPLL for everyone who has ever
    picked a statement.
    """
    op.execute(
        """
        INSERT INTO assessment_submissions
            (user_id, kind, form_version, status, narrative, answers,
             started_at, completed_at)
        SELECT ui.user_id,
               'wpll',
               '%(version)s',
               'complete',
               ui.wpll_insight_text,
               CAST(ui.wpll_answers AS jsonb),
               COALESCE(ui.wpll_completed_at, ui.created_at),
               ui.wpll_completed_at
        FROM   user_intake ui
        WHERE  ui.wpll_completed_at IS NOT NULL
           OR  jsonb_array_length(CAST(ui.wpll_answers AS jsonb)) > 0
        """ % {"version": CLIENT_FORM_VERSION}
    )


def _carry_profile_results() -> None:
    """The two profile-document keys -> ``focus_type`` / ``manager_match`` rows.

    ``completed_at`` falls back to ``profiles.updated_at``. The document never
    recorded when either was taken -- that is one of the things having a table
    buys -- and the profile's own timestamp is the closest honest upper bound.
    """
    for key, kind in PROFILE_RESULT_KEYS.items():
        op.execute(
            sa.text(
                """
                INSERT INTO assessment_submissions
                    (user_id, kind, form_version, status, result,
                     started_at, completed_at, scored_at)
                SELECT p.user_id, :kind, :version, 'scored', p.extra -> :key,
                       p.updated_at, p.updated_at, p.updated_at
                FROM   profiles p
                WHERE  p.extra ? :key
                """
            ).bindparams(key=key, kind=kind, version=CLIENT_FORM_VERSION)
        )

    # Removed, not left behind. `extra` assembles straight into the profile
    # document, so a copy still here would still be on the wire.
    op.execute(
        sa.text("UPDATE profiles SET extra = extra - :a - :b WHERE extra ?| ARRAY[:a, :b]")
        .bindparams(a="focus_type_result", b="manager_match_result")
    )


def _carry_core() -> None:
    """Every distinct person-side sitting -> one ``core`` submission.

    ``public_id`` is set to the existing ``submission_id`` parsed as a UUID
    rather than defaulted, which is what makes the two tables joinable without
    adding a column to either of them. The values were ``uuid4().hex`` and parse
    cleanly; a value that did not would raise here rather than produce a row that
    joins to nothing.

    Sourced from both person-side tables. A score row whose responses are missing
    should be impossible -- they are written in one transaction -- but a sitting
    that exists in only one of them is still a sitting, and a UNION is cheaper
    than being wrong about that.
    """
    op.execute(
        """
        INSERT INTO assessment_submissions
            (public_id, user_id, kind, form_version, status,
             started_at, completed_at, scored_at)
        SELECT sitting.submission_id::uuid,
               sitting.user_id,
               'core',
               sitting.form_version,
               'scored',
               sitting.at,
               sitting.at,
               sitting.at
        FROM (
            SELECT r.submission_id,
                   r.user_id,
                   r.form_version,
                   MIN(r.answered_at) AS at
            FROM   assessment_response r
            GROUP  BY r.submission_id, r.user_id, r.form_version
        ) AS sitting
        """
    )


def upgrade() -> None:
    _create_tables()
    _seed_forms()
    _carry_work_pulse()
    _carry_wpll()
    _carry_profile_results()
    _carry_core()


def downgrade() -> None:
    """Put the four client-rendered instruments back where they were.

    Reversible on purpose, and not because the data is precious -- it is
    disposable at this point in the product's life. It is reversible because a
    downgrade that silently drops whatever was submitted *after* the upgrade is
    a downgrade nobody can run without first working out what they are about to
    lose, which makes it useless in the incident it exists for.

    ``core`` needs nothing put back: this migration never altered
    ``assessment_response`` or ``person_dimension_score``, and their
    ``submission_id`` values are as valid after the tables are dropped as they
    were before they existed.
    """
    op.execute(
        """
        UPDATE user_intake ui
        SET    wpl_answers    = s.answers,
               wpl_narrative  = s.narrative,
               wpl_result     = s.result,
               wpl_completed_at = s.completed_at
        FROM   assessment_submissions s
        WHERE  s.user_id = ui.user_id AND s.kind = 'work_pulse'
        """
    )
    op.execute(
        """
        UPDATE user_intake ui
        SET    wpll_answers      = COALESCE(s.answers, '[]'::jsonb),
               wpll_insight_text = s.narrative,
               wpll_completed_at = s.completed_at
        FROM   assessment_submissions s
        WHERE  s.user_id = ui.user_id AND s.kind = 'wpll'
        """
    )
    for key, kind in PROFILE_RESULT_KEYS.items():
        op.execute(
            sa.text(
                """
                UPDATE profiles p
                SET    extra = p.extra || jsonb_build_object(:key, s.result)
                FROM   assessment_submissions s
                WHERE  s.user_id = p.user_id AND s.kind = :kind
                       AND s.result IS NOT NULL
                """
            ).bindparams(key=key, kind=kind)
        )

    op.drop_index("ix_submissions_user", table_name="assessment_submissions")
    op.drop_index(
        "uq_assessment_submissions_current", table_name="assessment_submissions"
    )
    op.drop_table("assessment_submissions")
    op.drop_table("assessment_forms")
