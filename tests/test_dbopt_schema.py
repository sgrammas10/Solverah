"""DB ledger, Package H: indexes, one intake email expression, the account repository.

Every index test reads a plan with ``enable_seqscan = off``.  The test tables
hold a handful of rows, and at that size the planner picks a sequential scan
whatever indexes exist; the question here is whether an index *can* serve the
statement the code sends, not whether the planner prefers it on an empty table.
Where the code builds the statement, the test captures the exact SQL it sent and
explains that, so a later rewrite of the query that stops matching the index
fails here instead of in production.

Findings pinned, each run against the code before its fix to watch it fail:

* ``job_recommendation`` had only its primary key, so the dashboard's count,
  the export's list and the deletion's DELETE each scanned the table.
* ``intake_submissions`` had only its primary key, and its three email lookups
  used two spellings: the account export/delete and retention compared
  ``lower(email)``, the dashboard compared the column as stored.  One expression
  now serves all three, and it is the one the new index is built on.
* Retention's age filter on ``intake_submissions.created_at`` had no index.
* ``user_sessions.parent_id`` / ``successor_id`` are self-referencing foreign
  keys with ``ON DELETE SET NULL``, so every session row the retention purge
  deletes makes Postgres look for rows pointing at it -- on columns with no
  index, one scan per deleted row.
* ``outbox.purge_published`` and ``resume_jobs.purge_terminal`` filtered on
  columns no index covered (``scoring_jobs`` already had its terminal index).
* Six indexes duplicated the leading column of a unique constraint on the same
  table, and ``ix_users_confirmation_token`` served no query at all: the code
  only ever compares the token after looking the user up by email.
* ``users.profile_data`` -- dead since Phase 2a -- was loaded with every user.
* ``account_repository.delete_personal_rows`` deleted intakes one row at a time.
"""

import contextlib
import datetime
import importlib.util
import re
import types
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations" / "versions" / "20260928_ledger_indexes.py"
)

USER_ID = 7101
OTHER_USER_ID = 7102

#: Indexes the migration removes; none may come back through ``db.create_all()``.
DROPPED = {
    "ix_resume_parse_correction_user_id",
    "ix_company_slug",
    "ix_company_dimension_score_company_id",
    "ix_company_confounder_value_company_id",
    "ix_weight_posterior_model_run_id",
    "ix_environment_dimension_score_environment_report_id",
    "ix_users_confirmation_token",
}

#: For each dropped leading-key index, the column it covered: something must
#: still lead with it, or the foreign-key checks on the parent lose their index.
STILL_COVERED = {
    ("resume_parse_correction", "user_id"),
    ("company", "slug"),
    ("company_dimension_score", "company_id"),
    ("company_confounder_value", "company_id"),
    ("weight_posterior", "model_run_id"),
    ("environment_dimension_score", "environment_report_id"),
}


def _app():
    from app import app

    return app


@contextlib.contextmanager
def _capture_sql():
    """Every ``(statement, parameters)`` pair sent inside the block."""
    from model import db

    sent = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        sent.append((statement, parameters))

    event.listen(db.engine, "before_cursor_execute", _record)
    try:
        yield sent
    finally:
        event.remove(db.engine, "before_cursor_execute", _record)


@contextlib.contextmanager
def _count_round_trips():
    """Statements sent, except a psycopg2 executemany counts once per row."""
    from model import db

    trips = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        many = executemany and isinstance(parameters, (list, tuple))
        trips.extend([statement] * (len(parameters) if many else 1))

    event.listen(db.engine, "before_cursor_execute", _record)
    try:
        yield trips
    finally:
        event.remove(db.engine, "before_cursor_execute", _record)


def _plan(statement, parameters=None):
    """``EXPLAIN`` a statement with sequential scans priced out."""
    from model import db

    connection = db.session.connection()
    try:
        connection.exec_driver_sql("SET LOCAL enable_seqscan = off")
        rows = connection.exec_driver_sql(
            "EXPLAIN " + statement, parameters or {}
        ).fetchall()
    finally:
        db.session.rollback()
    return "\n".join(row[0] for row in rows)


def _only(sent, *needles):
    """The one captured statement containing every needle."""
    hits = [(s, p) for s, p in sent if all(n in s for n in needles)]
    assert len(hits) == 1, [s for s, _ in sent]
    return hits[0]


def _add_intake(submission_id, email, age_days=0):
    from model import IntakeSubmission, db

    # The column is a naive timestamp; store UTC wall-clock time in it.
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    created = now - datetime.timedelta(days=age_days)
    db.session.add(IntakeSubmission(
        id=submission_id, first_name="I", last_name="S", email=email, state="TX",
        resume_key="intake/%s/r.pdf" % submission_id, resume_mime="application/pdf",
        resume_size_bytes=10, created_at=created,
    ))
    db.session.commit()


def _index_rows(table):
    """``{index_name: (is_unique, predicate_or_None, definition)}`` for *table*."""
    from model import db

    rows = db.session.execute(sa.text(
        "SELECT i.relname, x.indisunique, pg_get_expr(x.indpred, x.indrelid), "
        "       pg_get_indexdef(x.indexrelid) "
        "FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid "
        "WHERE x.indrelid = CAST(:t AS regclass)"
    ), {"t": table}).all()
    return {name: (unique, pred, definition) for name, unique, pred, definition in rows}


@pytest.fixture()
def people(seed_user):
    seed_user(USER_ID, OTHER_USER_ID)
    return USER_ID, OTHER_USER_ID


# ---------------------------------------------------------------------------
# New indexes, each proven against the statement its reader actually sends
# ---------------------------------------------------------------------------


def test_job_recommendation_reads_are_served_by_a_user_index(people):
    """Ledger ``model.py``:41 and its three readers (count, export list, delete)."""
    from model import JobRecommendation, db
    from solverah.repositories import account_repository, profile_repository

    with _app().app_context():
        db.session.add(JobRecommendation(user_id=USER_ID, job_id=1, score=0.5))
        db.session.commit()

        with _capture_sql() as sent:
            assert len(account_repository.find_job_recommendations(USER_ID)) == 1
            assert profile_repository.count_job_recommendations(USER_ID) == 1
        (listed, count) = sent

        for statement, parameters in (listed, count):
            plan = _plan(statement, parameters)
            assert "ix_job_recommendation_user_id" in plan, plan

        plan = _plan(
            "DELETE FROM job_recommendation WHERE user_id = %(u)s", {"u": USER_ID}
        )
        assert "ix_job_recommendation_user_id" in plan, plan


def _stub_bucket(monkeypatch):
    """A configured bucket that accepts every delete, so rule 1 deletes its rows.

    Without a bucket rule 1 keeps every stale row, which would leave the
    statements below untested for the case that actually deletes.
    """
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr("solverah.infra.storage.get_s3_client",
                        lambda: _WatchingBucket({}))


def test_every_intake_email_lookup_spells_the_same_expression(client, monkeypatch):
    """One expression, so one index serves all three readers.

    Before the fix the dashboard's ``has_intake_submission`` compared the column
    as stored while the account and retention paths compared ``lower(email)``.
    """
    from retention_cleanup import run_cleanup
    from solverah.repositories import account_repository, profile_repository

    _stub_bucket(monkeypatch)
    expression = "lower(intake_submissions.email)"

    with _app().app_context():
        with _capture_sql() as sent:
            account_repository.find_intakes_for_email("a@example.test")
            profile_repository.has_intake_submission("a@example.test")
        (found, probe) = sent
        with _capture_sql() as swept:
            run_cleanup(dry_run_sweep=True)
        stale = _only(swept, "FROM intake_submissions", "created_at")

    for statement, _ in (found, probe, stale):
        assert expression in statement, statement


def test_the_email_index_is_built_on_the_expression_the_lookups_use(client):
    """The model's index and the lookup expression cannot drift apart."""
    from model import IntakeSubmission, db

    index = {i.name: i for i in IntakeSubmission.__table__.indexes}[
        "ix_intake_submissions_email_lower"
    ]
    (indexed,) = index.expressions
    dialect = postgresql.dialect()
    assert str(indexed.compile(dialect=dialect)) == str(
        IntakeSubmission.email_key.compile(dialect=dialect)
    )

    with _app().app_context():
        assert "ix_intake_submissions_email_lower" in _index_rows("intake_submissions")
        db.session.rollback()


def test_intake_email_lookups_are_served_by_the_expression_index(client):
    """Ledger ``account_repository``:55 and ``profile_repository``:672."""
    from solverah.repositories import account_repository, profile_repository

    with _app().app_context():
        with _capture_sql() as sent:
            account_repository.find_intakes_for_email("Someone@Example.test")
            profile_repository.has_intake_submission("Someone@Example.test")

        for statement, parameters in sent:
            plan = _plan(statement, parameters)
            assert "ix_intake_submissions_email_lower" in plan, plan


def test_intake_lookups_ignore_case_the_same_way(client):
    """The dashboard's probe now answers what the export and delete already did."""
    from solverah.repositories import account_repository, profile_repository

    with _app().app_context():
        _add_intake("dbopt-h-mixed", "Mixed@Example.test")
        _add_intake("dbopt-h-lower", "lower@example.test")

        for asked in ("mixed@example.test", "MIXED@EXAMPLE.TEST", "Mixed@Example.test"):
            assert profile_repository.has_intake_submission(asked) is True, asked
            found = account_repository.find_intakes_for_email(asked)
            assert [i.id for i in found] == ["dbopt-h-mixed"], asked
        assert profile_repository.has_intake_submission("Lower@Example.test") is True
        assert profile_repository.has_intake_submission("nobody@example.test") is False
        assert account_repository.find_intakes_for_email("") == []


def test_retention_age_filter_is_served_by_the_created_at_index(client, monkeypatch):
    """Ledger ``retention_cleanup``:87: the stale-intake read, as sent."""
    from retention_cleanup import run_cleanup

    _stub_bucket(monkeypatch)

    with _app().app_context():
        _add_intake("dbopt-h-old", "old@example.test", age_days=120)
        with _capture_sql() as swept:
            summary = run_cleanup(dry_run_sweep=True)
        assert summary["abandoned_intakes_deleted"] == 1

        statement, parameters = _only(swept, "FROM intake_submissions", "created_at")
        plan = _plan(statement, parameters)
    assert "ix_intake_submissions_created_at" in plan, plan


@pytest.mark.parametrize("column", ["parent_id", "successor_id"])
def test_session_chain_links_are_indexed_plainly(client, column):
    """Ledger ``refresh_tokens.purge_terminal``: the ``ON DELETE SET NULL`` lookups.

    The referential action for a deleted session is, per foreign key,
    ``UPDATE ONLY user_sessions SET <col> = NULL WHERE <col> = <deleted id>``.
    That is the statement explained here.

    The index must stay non-unique and non-partial.  ``refresh_tokens.rotate``
    inserts the successor before it claims the parent, and that order is free of
    deadlocks only while no unique index covers these columns.
    """
    name = {"parent_id": "ix_user_sessions_parent",
            "successor_id": "ix_user_sessions_successor"}[column]

    with _app().app_context():
        plan = _plan(
            "UPDATE ONLY user_sessions SET %s = NULL WHERE %s = 1" % (column, column)
        )
        assert name in plan, plan
        unique, predicate, definition = _index_rows("user_sessions")[name]
        from model import db

        db.session.rollback()

    assert unique is False, definition
    assert predicate is None, definition
    assert definition.endswith("USING btree (%s)" % column), definition


def test_outbox_purge_is_served_by_a_published_index(client):
    """Ledger ``outbox.purge_published``: the index is shaped to its predicate."""
    from solverah.services import outbox

    with _app().app_context():
        with _capture_sql() as sent:
            outbox.purge_published()
        statement, parameters = _only(sent, "DELETE FROM outbox")
        plan = _plan(statement, parameters)
        assert "ix_outbox_published" in plan, plan

        unique, predicate, _ = _index_rows("outbox")["ix_outbox_published"]
        from model import db

        db.session.rollback()
    assert unique is False
    assert predicate == "(published_at IS NOT NULL)"


def test_resume_job_purge_is_served_by_a_terminal_index(client):
    """Ledger ``resume_jobs.purge_terminal``: mirrors ``ix_scoring_jobs_terminal``."""
    from solverah.services import resume_jobs

    with _app().app_context():
        with _capture_sql() as sent:
            resume_jobs.purge_terminal()
        statement, parameters = _only(sent, "DELETE FROM resume_parse_jobs")
        plan = _plan(statement, parameters)
        assert "ix_resume_parse_jobs_terminal" in plan, plan

        mine = _index_rows("resume_parse_jobs")["ix_resume_parse_jobs_terminal"]
        theirs = _index_rows("scoring_jobs")["ix_scoring_jobs_terminal"]
        from model import db

        db.session.rollback()

    def _shape(definition):
        return re.sub(r"^.* USING ", "USING ", definition)

    assert (mine[0], mine[1], _shape(mine[2])) == (
        theirs[0], theirs[1], _shape(theirs[2])
    )


# ---------------------------------------------------------------------------
# Redundant indexes
# ---------------------------------------------------------------------------


def test_redundant_indexes_are_gone_and_their_columns_stay_covered(client):
    """Each dropped index duplicated the leading column of a unique key.

    ``company.slug`` is the one that matters most: it must stay UNIQUE after
    losing ``ix_company_slug``, which ``create_all`` used to build as the only
    unique index on the column.
    """
    from model import db

    with _app().app_context():
        present = {}
        for table in {t for t, _ in STILL_COVERED} | {"users"}:
            present[table] = _index_rows(table)
        db.session.rollback()

    names = {name for rows in present.values() for name in rows}
    assert not DROPPED & names, sorted(DROPPED & names)

    for table, column in STILL_COVERED:
        leading = [
            name for name, (_, predicate, definition) in present[table].items()
            if predicate is None
            and re.search(r"USING btree \(%s(,|\))" % column, definition)
        ]
        assert leading, (table, column, present[table])

    slug_unique = [
        name for name, (unique, _, definition) in present["company"].items()
        if unique and definition.endswith("USING btree (slug)")
    ]
    assert slug_unique, present["company"]


# ---------------------------------------------------------------------------
# Model and migration agree
# ---------------------------------------------------------------------------


class _Recorder:
    """Stands in for ``alembic.op``: records every operation in order, runs nothing."""

    def __init__(self, slug_constraint_present=True):
        self.created = {}
        self.dropped = {}
        self.calls = []  # ("execute" | "probe" | "create_index" | "drop_index", detail)
        self._slug_constraint_present = slug_constraint_present

    def execute(self, statement):
        self.calls.append(("execute", str(statement)))

    def create_index(self, name, table, columns, unique=False, **kw):
        self.calls.append(("create_index", name))
        self.created[name] = (table, list(columns), bool(unique), kw.get("postgresql_where"))

    def drop_index(self, name, table_name=None, **kw):
        self.calls.append(("drop_index", name))
        self.dropped[name] = table_name

    def get_bind(self):
        return _RecordingBind(self)

    def __getattr__(self, attr):
        raise AssertionError("the index migration called op.%s" % attr)


class _RecordingBind:
    """A bind that records each probe and answers it from the recorder's setting."""

    def __init__(self, recorder):
        self._recorder = recorder

    def execute(self, statement, *_args, **_kwargs):
        self._recorder.calls.append(("probe", str(statement)))
        answer = 1 if self._recorder._slug_constraint_present else None
        return types.SimpleNamespace(scalar=lambda: answer)


def _load_migration(recorder):
    spec = importlib.util.spec_from_file_location("_h_ledger_indexes", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = recorder
    return module


def _run_migration(direction):
    recorder = _Recorder()
    module = _load_migration(recorder)
    getattr(module, direction)()
    return module, recorder


def _norm(text):
    text = str(text)
    text = re.sub(r"\b[a-z_]+\.", "", text)  # table-qualified column -> column
    return re.sub(r"\s+", "", text).lower()


def _model_index(table_name, name):
    from model import db

    table = db.metadata.tables[table_name]
    matches = [i for i in table.indexes if i.name == name]
    return matches[0] if matches else None


def test_the_migration_is_the_next_link_in_the_chain():
    module, _ = _run_migration("upgrade")
    assert module.down_revision == "20260928_path_narratives"
    assert len(module.revision) <= 32


LOCK_TIMEOUT = "SET LOCAL lock_timeout = '10s'"


def test_upgrade_sets_a_lock_timeout_then_checks_the_slug_before_any_ddl():
    """Fail fast, and fail before anything has been built.

    DROP INDEX takes ACCESS EXCLUSIVE (on ``users`` among others). Without a
    lock timeout it can queue behind a live request and stall every later read
    of the table behind it for the length of the deploy.
    """
    _, up = _run_migration("upgrade")

    assert up.calls[0] == ("execute", LOCK_TIMEOUT), up.calls[:3]
    assert up.calls[1][0] == "probe" and "company_slug_key" in up.calls[1][1], up.calls[:3]
    ddl = [kind for kind, _ in up.calls[2:]]
    assert set(ddl) == {"create_index", "drop_index"}, up.calls


def test_a_missing_slug_constraint_aborts_before_any_index_is_touched():
    recorder = _Recorder(slug_constraint_present=False)
    module = _load_migration(recorder)

    with pytest.raises(RuntimeError, match="company_slug_key"):
        module.upgrade()
    assert [kind for kind, _ in recorder.calls] == ["execute", "probe"], recorder.calls


def test_downgrade_sets_the_same_lock_timeout_first():
    _, down = _run_migration("downgrade")
    assert down.calls[0] == ("execute", LOCK_TIMEOUT), down.calls[:2]


def test_every_index_the_migration_creates_is_declared_identically_in_the_model():
    _, up = _run_migration("upgrade")
    dialect = postgresql.dialect()

    assert up.created, "the migration creates no index"
    for name, (table, columns, unique, where) in up.created.items():
        declared = _model_index(table, name)
        assert declared is not None, "%s is in the migration but not the model" % name
        assert [_norm(c) for c in columns] == [
            _norm(e.compile(dialect=dialect)) for e in declared.expressions
        ], name
        assert unique == bool(declared.unique), name
        model_where = declared.dialect_options["postgresql"]["where"]
        assert _norm("" if where is None else where) == _norm(
            "" if model_where is None else model_where
        ), name


def test_every_index_the_migration_drops_is_absent_from_the_model():
    from model import db

    _, up = _run_migration("upgrade")

    assert set(up.dropped) == DROPPED
    for name, table in up.dropped.items():
        assert table in db.metadata.tables, name
        assert _model_index(table, name) is None, name


def _created_by_earlier_migrations():
    """Index names any earlier revision's ``upgrade()`` creates.

    A textual read, not an execution: ``op.create_index("name", ...)`` (with or
    without ``op.f``), raw ``CREATE [UNIQUE] INDEX name`` and ``RENAME TO name``
    inside the ``upgrade`` body. It cannot see an index an earlier revision
    created and a later one dropped again; that residue, and any index built
    some other way, is what ``flask db check`` against a migrated database is the
    net for (run by hand for this package: partition children are its only
    known false positive).
    """
    names = set()
    for path in MIGRATION.parent.glob("*.py"):
        if path == MIGRATION:
            continue
        source = path.read_text(encoding="utf-8")
        body = source.split("def upgrade", 1)[-1].split("def downgrade", 1)[0]
        names |= set(re.findall(
            r"""create_index\(\s*(?:op\.f\(\s*)?["']([A-Za-z0-9_]+)["']""", body))
        names |= set(re.findall(
            r"(?i)CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)",
            body))
        names |= set(re.findall(r"(?i)RENAME\s+TO\s+([A-Za-z0-9_]+)", body))
    return names


def test_every_model_index_on_the_touched_tables_is_built_by_the_chain():
    """The inverse of the parity test above: no index may exist in the model only.

    ``tests/conftest.py`` builds the schema with ``db.create_all()``, so a
    model-only index would make every test pass against an index production
    never gets.
    """
    from model import db

    _, up = _run_migration("upgrade")
    chain = (_created_by_earlier_migrations() | set(up.created)) - set(up.dropped)
    touched = {table for table, *_ in up.created.values()} | set(up.dropped.values())

    model_only = sorted(
        "%s.%s" % (table, index.name)
        for table in touched
        for index in db.metadata.tables[table].indexes
        if index.name not in chain
    )
    assert not model_only, model_only


def test_downgrade_is_the_exact_inverse():
    _, up = _run_migration("upgrade")
    _, down = _run_migration("downgrade")

    assert set(down.dropped) == set(up.created)
    assert set(down.created) == set(up.dropped)
    for name, table in up.dropped.items():
        assert down.created[name][0] == table, name
        # Every index the upgrade drops was a plain, whole-table, non-unique one.
        assert down.created[name][2] is False, name
        assert down.created[name][3] is None, name


# ---------------------------------------------------------------------------
# users.profile_data
# ---------------------------------------------------------------------------


def test_profile_data_is_not_loaded_with_the_user(people):
    """Ledger ``model.py``:53: the dead JSON column rode along on every user load."""
    from model import User, db
    from tests.query_count import count_queries

    with _app().app_context():
        user = db.session.get(User, USER_ID)
        user.profile_data = {"phone": "+1-555-0100"}
        db.session.commit()
        db.session.expunge_all()

        with count_queries() as loaded:
            user = db.session.get(User, USER_ID)
            email = user.email
        with count_queries() as touched:
            legacy = user.profile_data

    assert email == "seeded-%d@example.test" % USER_ID
    assert len(loaded) == 1
    assert "profile_data" not in loaded[0], loaded[0]
    # Still readable, one SELECT later: the tombstone test in
    # test_account_lifecycle reads it back after deletion.
    assert legacy == {"phone": "+1-555-0100"}
    assert len(touched) == 1


# ---------------------------------------------------------------------------
# account_repository.delete_personal_rows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how_many", [1, 3])
def test_delete_personal_rows_deletes_every_intake_in_one_statement(people, how_many):
    """Ledger ``account_repository``:80: one DELETE per intake before the fix."""
    from sqlalchemy import inspect

    from model import IntakeSubmission, db
    from solverah.repositories import account_repository

    with _app().app_context():
        for n in range(how_many):
            _add_intake("dbopt-h-mine-%d" % n, "Mine@Example.test")
        _add_intake("dbopt-h-theirs", "theirs@example.test")

        intakes = account_repository.find_intakes_for_email("mine@example.test")
        assert len(intakes) == how_many

        with _count_round_trips() as trips:
            account_repository.delete_personal_rows(USER_ID, intakes)
            db.session.flush()
        deletes = [s for s in trips if s.startswith("DELETE FROM intake_submissions")]
        assert len(deletes) == 1, deletes

        # The loaded instances are gone from the session too, so nothing later
        # in the request can flush them back or read a row that no longer exists.
        assert all(inspect(i).was_deleted or inspect(i).detached for i in intakes)
        db.session.commit()

        left = [i for (i,) in db.session.execute(sa.select(IntakeSubmission.id))]
    assert left == ["dbopt-h-theirs"]


def test_delete_personal_rows_with_no_intakes_sends_no_intake_delete(people):
    from model import db
    from solverah.repositories import account_repository

    with _app().app_context():
        with _count_round_trips() as trips:
            account_repository.delete_personal_rows(USER_ID, [])
            db.session.flush()
        db.session.rollback()
    assert not [s for s in trips if "intake_submissions" in s], trips


# ---------------------------------------------------------------------------
# retention_cleanup: no transaction held open across storage calls
# ---------------------------------------------------------------------------


class _WatchingBucket:
    """A fake R2 client that records, per call, whether a DB transaction is open.

    An idle-in-transaction timeout kills a session whose transaction sits open
    while the process waits on something else; storage calls are exactly that
    wait, and there is no bound on how many there are.
    """

    def __init__(self, objects, refuse=()):
        self.objects = dict(objects)  # key -> last_modified
        self.refuse = set(refuse)
        self.calls = []  # (operation, key_or_prefix, in_transaction)
        self.deleted = []

    def _open(self):
        from model import db

        # db.session is the scoped registry; calling it yields this context's Session.
        return db.session().in_transaction()

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):
        self.calls.append(("list", Prefix, self._open()))
        yield {"Contents": [
            {"Key": k, "LastModified": lm}
            for k, lm in sorted(self.objects.items()) if k.startswith(Prefix)
        ]}

    def delete_object(self, Bucket, Key):
        self.calls.append(("delete", Key, self._open()))
        if Key in self.refuse:
            raise RuntimeError("refused")
        self.deleted.append(Key)
        self.objects.pop(Key, None)


def test_retention_holds_no_transaction_open_across_storage_calls(client, monkeypatch):
    """Rule 1's object deletes and rule 3's listing and deletes run outside a transaction.

    Rule 1's order still holds: a row goes only after its object delete
    succeeded, and a refused delete keeps its row for the next run.
    """
    from model import IntakeSubmission, User, db
    from retention_cleanup import ORPHAN_GRACE_HOURS, run_cleanup

    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=ORPHAN_GRACE_HOURS + 1
    )
    fake = _WatchingBucket(
        {"intake/orphan/r.pdf": old, "intake/dbopt-h-gone/r.pdf": old},
        refuse={"intake/dbopt-h-stuck/r.pdf"},
    )
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: fake)

    with _app().app_context():
        db.session.add(User(email="kept@example.test", password_hash="not-a-real-hash"))
        db.session.commit()
        _add_intake("dbopt-h-gone", "gone@example.test", age_days=120)
        _add_intake("dbopt-h-stuck", "stuck@example.test", age_days=120)
        _add_intake("dbopt-h-kept", "Kept@Example.test", age_days=120)

    summary = run_cleanup()

    operations = {op for op, _, _ in fake.calls}
    assert operations == {"list", "delete"}, fake.calls
    held = [call for call in fake.calls if call[2]]
    assert not held, held

    assert summary["abandoned_intakes_deleted"] == 1
    assert summary["r2_delete_failures"] == 1
    assert summary["orphans_deleted"] == 1
    assert sorted(fake.deleted) == ["intake/dbopt-h-gone/r.pdf", "intake/orphan/r.pdf"]
    with _app().app_context():
        left = sorted(i for (i,) in db.session.execute(sa.select(IntakeSubmission.id)))
        db.session.rollback()
    assert left == ["dbopt-h-kept", "dbopt-h-stuck"]
