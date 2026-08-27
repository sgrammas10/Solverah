"""Shared pytest fixtures, and the guards that make running them safe.

Three defects lived here. Two bit on 2026-08-26.

**The cleanup deleted the wrong file.** Teardown called ``os.remove("test.db")``,
but ``DATABASE_URL=sqlite:///test.db`` is a *relative* path and Flask-SQLAlchemy
resolves relative SQLite paths against ``app.instance_path``.  The database is
written to ``instance/test.db``; the removal targeted ``./test.db``, which never
existed, raised ``FileNotFoundError``, and was swallowed by the bare ``except``.
The test database was therefore never once cleaned up -- it accumulated state
across every run since the fixture was written, and rows surviving a supposedly
fresh setup surfaced as ``ObjectDeletedError`` in unrelated tests.

**Nothing stopped the suite pointing at production.** ``os.environ.setdefault``
keeps whatever ``DATABASE_URL`` is already in the shell, and the fixture calls
``db.drop_all()``.  A developer who exported a production URL in a terminal --
to run a migration, say -- and then ran ``pytest`` in that same terminal would
drop every production table.  Nothing in the code stood between those two
keystrokes.  :func:`_refuse_non_local_database` now does.

**Nothing stopped two runs sharing one database.** ``setdefault``, the
Makefile's ``DATABASE_URL ?=`` and ``Scripts/capture_contract.py`` all resolved
to one URL, and two of the three drop the schema.  A suite failure reported on
2026-08-27 as "920 passed, 36 failed, 132 errors, Phase 2d caused it" was two
pytest processes on one database and nothing else; the same commit on its own
database ran 1062 passed, 0 failed, 0 errors.  It read as a schema defect
because every one of the 132 errors named ``user_role`` -- which is not evidence
about any phase, only the first enum ``create_all`` emits, and so the first
object two racing processes reach together.  The three defaults are now three
databases, and :func:`_claim_database_or_refuse` catches the case the defaults
cannot: two pytest processes inheriting the same one.

**The default is Postgres as of 2026-08-27**, and the SQLite CI job is gone --
see ``.github/workflows/tests.yml`` for the reasoning.  The SQLite branches
below are kept rather than deleted: the guard has to keep accepting SQLite URLs
because ``test_conftest_safety.py`` asserts on them directly, and the teardown
branch is the fix for a real bug that would come straight back if anyone points
``DATABASE_URL`` at a file again.
"""

import os

import pytest

#: The database this suite owns, and owns alone.
#:
#: `solverah_test` rather than the `solverah` that `make dev` uses, because this
#: file calls ``db.drop_all()`` and ``Scripts/capture_contract.py`` calls
#: ``DROP SCHEMA public CASCADE``.  Until 2026-08-27 those two and ``make
#: test-pg`` all defaulted to the same database, so running any two at once meant
#: each tearing down the other's tables mid-run.  Splitting the default is what
#: makes that impossible *between tools*; two pytest processes still inherit the
#: same value, and :func:`_claim_database_or_refuse` is what stops those.
#:
#: Keep this in step with ``Makefile`` (``DATABASE_URL ?=``) and with
#: ``infra/docker/initdb/02-lane-databases.sql``, which creates it.  CI never
#: reaches this line -- it sets ``DATABASE_URL`` explicitly against a service
#: container it is the only process on, and on 5432, because a runner has
#: nothing to collide with.
#:
#: Port 5433 rather than 5432: a native Windows Postgres service shadows 5432 on
#: at least one developer machine, and Windows lets both it and Docker bind the
#: port instead of refusing.  The reasoning lives in ``infra/docker/compose.yml``
#: and the failure it produces is named in the refusal below.
TEST_DATABASE_URL = "postgresql://solverah:solverah@localhost:5433/solverah_test"

os.environ.setdefault("APP_ENV", "testing")
# The compose stack's database (infra/docker/compose.yml), not SQLite.
#
# It was `sqlite:///test.db` until 2026-08-27. Phase 2a's tables cannot be
# created on SQLite -- `DEFAULT uuidv7()`, identity columns, JSONB, `TEXT[]` and
# a GIN trigram index between them -- so `db.create_all()` fails there before any
# test runs. A default that cannot work is worse than one that needs a container
# running: the failure it produces talks about DDL rather than about the missing
# database.
#
# `docker compose -f infra/docker/compose.yml up db` is the whole setup. The
# guard below still allows SQLite URLs, because it is a guard about *hosts* and
# nothing is gained by narrowing it.
#
# `solverah_test`, not `solverah` -- see TEST_DATABASE_URL above.
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_COOKIE_SECURE", "false")
os.environ.setdefault("JWT_COOKIE_SAMESITE", "Lax")


# Hosts a throwaway test database may live on. `db` and `postgres` are the
# conventional service names inside docker-compose networks, where the host is
# a container alias rather than a routable address.
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "db", "postgres"})


def _refuse_non_local_database(raw_url: str) -> None:
    """Abort collection unless *raw_url* points at a local, throwaway database.

    The fixture below calls ``db.drop_all()``.  Every guarantee that this is
    safe rests on the database being disposable, and nothing else in the stack
    checks that.  SQLite is always allowed (it is a file).  Server databases are
    allowed only on a loopback or container-local host.

    There is deliberately no override flag.  An escape hatch on a guard whose
    entire purpose is preventing an irreversible mistake is a way to make the
    mistake with one extra step; if a remote test database is ever genuinely
    needed, that is a considered change to this function, not a variable someone
    exports at 2am.

    Raises:
        RuntimeError: If the URL is unparseable or names a non-local host.
    """
    from sqlalchemy.engine import make_url

    try:
        url = make_url(raw_url)
    except Exception as exc:  # noqa: BLE001 - any parse failure is fatal here
        raise RuntimeError(
            "DATABASE_URL could not be parsed, so it cannot be checked for "
            "safety, and the test suite drops every table it connects to. "
            "Refusing to run. (%s)" % exc
        ) from exc

    if url.drivername.startswith("sqlite"):
        return

    host = (url.host or "").lower()
    if host in LOCAL_HOSTS:
        return

    raise RuntimeError(
        "REFUSING TO RUN TESTS AGAINST %r.\n"
        "\n"
        "The test fixtures call db.drop_all(). Against this host that would "
        "destroy real data.\n"
        "DATABASE_URL is set in your environment -- most likely exported in this "
        "shell for a migration or a psql session, and pytest inherited it "
        "(conftest uses setdefault, which keeps what is already there).\n"
        "\n"
        "Unset it, or point it at a local database:\n"
        "    PowerShell:  Remove-Item Env:DATABASE_URL\n"
        "    bash:        unset DATABASE_URL\n" % (url.render_as_string(hide_password=True),)
    )


_refuse_non_local_database(os.environ["DATABASE_URL"])


#: Extensions the schema needs in place before ``db.create_all()`` can run.
#: Listed here rather than derived from the models so the refusal can name them.
REQUIRED_EXTENSIONS = ("citext", "pg_trgm", "vector")

#: Advisory-lock key this session claims for as long as it runs.
#:
#: Postgres scopes advisory locks to a database, so a constant is exactly right:
#: two runs on ``solverah_test`` contend, a run on ``solverah_lane2`` does not.
#: The value is arbitrary and only has to stay stable.
DATABASE_CLAIM_LOCK = 0x5011E7A4

#: How to get a database of your own. Printed by every refusal below, because a
#: guard that stops you without telling you how to proceed is an obstacle.
SETUP_STEPS = """\
    docker compose -f infra/docker/compose.yml exec db \
psql -U solverah -d postgres -c "CREATE DATABASE solverah_lane2 OWNER solverah"

    docker compose -f infra/docker/compose.yml exec db \
psql -U solverah -d solverah_lane2 \
-c "CREATE EXTENSION IF NOT EXISTS citext" \
-c "CREATE EXTENSION IF NOT EXISTS pg_trgm" \
-c "CREATE EXTENSION IF NOT EXISTS vector"

then point this run at it:

    PowerShell:  $env:DATABASE_URL = \
"postgresql://solverah:solverah@localhost:5433/solverah_lane2"
    bash:        export \
DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah_lane2

A *schema* is not enough, and that is the part that looks like it should work.
Enum types live in pg_type, not in a schema: they outlive DROP SCHEMA public
CASCADE. Two lanes sharing one database on separate search_paths still collide
on `user_role`. It has to be a separate database."""


def _claim_database_or_refuse(raw_url: str):
    """Claim *raw_url*'s database for this session, or say who already holds it.

    Nothing else in the stack notices that two runs are sharing a database, and
    sharing one is not merely slow but wrong: the fixtures below call
    ``create_all`` and ``drop_all``, so each run tears down the tables the other
    is halfway through using.  On 2026-08-27 that cost hours, because of the
    shape it takes -- 132 collection errors naming ``user_role``, which reads as
    a schema defect and is not one.  ``user_role`` is only the first enum
    ``create_all`` emits, and so the first object two racing processes meet on.

    The claim is a session-level ``pg_try_advisory_lock``.  Deliberately the
    *try* variant: waiting would turn a mistake into a hang, and the job here is
    to say what is wrong, not to serialise two runs that should not both exist.

    In CI this is a no-op nobody ever sees.  One process owns a dedicated
    service container, so the lock is always free -- and the check needs no
    environment variable of its own, which matters, because the runner sets five
    and has no ``.env`` (CLAUDE.md).  A guard needing a sixth would pass on a
    developer machine and fail the gate.

    Args:
        raw_url: The URL the suite is about to build its schema in.

    Returns:
        The open connection holding the claim.  The caller **must** keep it
        open; closing it releases the claim.  ``None`` where the question does
        not arise -- SQLite is a file per URL, and has no advisory locks.

    Raises:
        RuntimeError: If another process holds the claim, if the database cannot
            be reached, or if it is missing an extension the schema needs.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool

    url = make_url(raw_url)
    if not url.get_backend_name().startswith("postgresql"):
        return None

    shown = url.render_as_string(hide_password=True)

    # NullPool, and the connection is handed back rather than closed, because
    # pg_try_advisory_lock is scoped to a *connection*.  Taken on a pooled one it
    # is released the instant SQLAlchemy checks that connection back in, and this
    # guard would then pass while guarding nothing.  (pg_advisory_xact_lock fails
    # the same way one level down: the claim has to outlive every transaction the
    # suite runs, not one of them.)
    engine = create_engine(url, poolclass=NullPool)
    try:
        connection = engine.connect()
    except Exception as exc:  # noqa: BLE001 - the drivers raise several of these
        detail = str(exc).strip().splitlines()[0]

        # An auth failure against a stack `docker compose ps` calls healthy is
        # almost never a typo'd password -- the credentials are in compose.yml and
        # nobody types them. It is the shadow case, and it is worth its own
        # paragraph because every other signal says the database is fine: the
        # container is healthy, `docker compose exec db psql` works, and only the
        # published port is a lie. Measured 2026-08-27 on postgresql-x64-18.
        shadow = ""
        if "authentication" in detail or "password" in detail:
            shadow = (
                "That is an authentication failure, which here usually means "
                "something OTHER\n"
                "than the compose container answered. Windows lets a native "
                "Postgres service\n"
                "and Docker both bind one port rather than refusing the second, "
                "and the native\n"
                "one wins every connection -- so `docker compose ps db` reports "
                "healthy and\n"
                "`docker compose exec db psql` works while every URL in this repo "
                "fails. It is\n"
                "why the stack publishes 5433 and not 5432. Two commands settle "
                "it:\n"
                "\n"
                "    Get-Service postgresql*                 # is a native one "
                "running?\n"
                "    netstat -ano | findstr :5433            # two PIDs on one "
                "port?\n"
                "\n"
                "If that is what happened, stop the native service or republish "
                "this stack on\n"
                "a port nothing else holds. Otherwise --\n"
                "\n"
            )

        raise RuntimeError(
            "REFUSING TO RUN: cannot reach the test database.\n"
            "\n"
            "    %s\n"
            "    %s\n"
            "\n"
            "%s"
            "This suite has a database of its own, separate from the `solverah`\n"
            "that `make dev` uses, because it drops every table it connects to.\n"
            "Starting the stack creates it:\n"
            "\n"
            "    docker compose -f infra/docker/compose.yml up -d db\n"
            "\n"
            "On a volume created before 2026-08-27 that is not enough. initdb\n"
            "runs only on a first-ever start, so\n"
            "infra/docker/initdb/02-lane-databases.sql never ran there: either\n"
            "`make clean` and start over, or create one by hand --\n"
            "\n"
            "%s\n" % (shown, detail, shadow, SETUP_STEPS)
        ) from exc

    try:
        claimed = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": DATABASE_CLAIM_LOCK}
        ).scalar()
        # Ends the transaction execute() opened.  The lock is session-scoped and
        # survives it -- which is the whole reason for the non-xact variant.
        connection.rollback()

        if not claimed:
            raise RuntimeError(
                "REFUSING TO RUN: ANOTHER PROCESS IS ALREADY USING THIS TEST\n"
                "DATABASE.\n"
                "\n"
                "    %s\n"
                "\n"
                "Almost always a second `pytest`. `python -m\n"
                "Scripts.capture_contract` and `make test-pg` land here too if\n"
                "their defaults were overridden onto this database.\n"
                "\n"
                "This is not a queueing problem, so waiting is not the fix on\n"
                "its own. The fixtures call db.create_all() and db.drop_all():\n"
                "two runs delete each other's tables mid-test. And what that\n"
                "looks like is NOT a message about sharing -- on 2026-08-27 it\n"
                "was 132 collection errors, every one naming `user_role`, and\n"
                "it was read as a Phase 2c schema defect for hours. `user_role`\n"
                "is just the first enum create_all emits, and so the first\n"
                "object two processes racing each other happen to meet on.\n"
                "\n"
                "Wait for the other run to finish, or take a database of your\n"
                "own:\n"
                "\n"
                "%s\n" % (shown, SETUP_STEPS)
            )

        present = {
            row[0]
            for row in connection.execute(text("SELECT extname FROM pg_extension"))
        }
        connection.rollback()
        missing = [name for name in REQUIRED_EXTENSIONS if name not in present]
        if missing:
            raise RuntimeError(
                "REFUSING TO RUN: the test database is missing %s.\n"
                "\n"
                "    %s\n"
                "\n"
                "db.create_all() would fail on the first table that uses one,\n"
                "in DDL that never mentions the extension by name. Extensions\n"
                "are per-database, so creating the database is only half of it:\n"
                "\n"
                "%s\n" % (", ".join(missing), shown, SETUP_STEPS)
            )
    except Exception:
        connection.close()  # releases the claim, if this call is what took it
        raise

    return connection


@pytest.fixture(scope="session", autouse=True)
def _own_the_test_database():
    """Hold this session's claim on the database, or stop the run explaining why.

    ``pytest.exit`` rather than letting the RuntimeError out: an exception in a
    session-scoped autouse fixture is re-reported as an error against every test
    that requests it, and every test requests this one.  That is a thousand
    copies of a paragraph whose entire job is to be read once.
    """
    try:
        connection = _claim_database_or_refuse(os.environ["DATABASE_URL"])
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=1)

    yield

    if connection is not None:
        connection.close()


def _enforce_sqlite_foreign_keys() -> None:
    """Make SQLite reject orphan foreign keys, the way Postgres always has.

    SQLite ships with foreign-key enforcement OFF and it is a per-connection pragma,
    so an FK declared in the schema is documentation and nothing more until someone
    turns it on.  Nobody had.  Eight tests across four files inserted child rows
    naming a ``user_id`` no ``user`` row ever had; all eight passed for as long as the
    suite ran on SQLite and all eight failed the hour CI moved to Postgres
    (2026-08-27).  The rows were orphans on both databases.  Only one of the two said so.

    The SQLite job this was written for is retired (2026-08-27, Phase 2a -- the new
    profile tables cannot be created on SQLite at all).  The listener stays, because it
    is what makes a SQLite ``DATABASE_URL`` merely *limited* rather than actively
    misleading: anyone who points one at a file for a quick run on the subset of tests
    that still work there gets the same integrity rules as the gate, not laxer ones.
    """
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        # Fires for every engine; only SQLite DBAPI connections understand the pragma.
        if type(dbapi_connection).__module__.split(".")[0] != "sqlite3":
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


_enforce_sqlite_foreign_keys()


@pytest.fixture()
def client():
    """A Flask test client backed by a freshly created, fully torn-down database."""
    from app import app
    from model import db

    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()

    yield app.test_client()

    sqlite_path = None
    with app.app_context():
        db.session.remove()
        db.drop_all()

        # Read the resolved path BEFORE disposing: for `sqlite:///test.db`
        # SQLAlchemy reports the absolute location Flask actually writes to
        # (…/instance/test.db), which is the file that needs removing.
        if db.engine.url.drivername.startswith("sqlite"):
            sqlite_path = db.engine.url.database

        # Windows refuses to unlink a file that any handle still has open, and
        # the pool holds one until disposed. Without this the removal below
        # fails with PermissionError and the database survives to pollute the
        # next run -- the original bug, in a different disguise.
        db.engine.dispose()

    if sqlite_path and sqlite_path != ":memory:":
        try:
            os.remove(sqlite_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            # Loud on purpose. A cleanup that cannot clean leaves state behind,
            # and state left behind is what made unrelated tests fail with
            # ObjectDeletedError while each passed in isolation.
            raise RuntimeError(
                "Could not remove the test database at %s: %s\n"
                "It will leak state into the next run. A live connection is the "
                "usual cause -- check for another pytest process still holding it."
                % (sqlite_path, exc)
            ) from exc


def _resync_identity_sequence(db) -> None:
    """Advance ``users.id``'s sequence past any hand-assigned ids.

    Supplying a primary key explicitly does not consume a value from the sequence
    backing it, so the next ``User()`` inserted without an id is handed 1 and collides
    with the seeded row.  SQLite has no sequence and needs nothing.

    Still true after Phase 2c made the column ``GENERATED BY DEFAULT AS IDENTITY``:
    ``BY DEFAULT`` accepts an explicit value and, exactly like ``SERIAL``, does not
    advance the sequence when it does.  ``GENERATED ALWAYS`` would have rejected the
    insert outright rather than made this unnecessary -- see the note on
    ``User.id`` for why the fixture won that argument.
    """
    if db.engine.url.drivername.startswith("sqlite"):
        return

    from sqlalchemy import text

    # No quoting: the table is `users` as of Phase 2c (P1-8's first bullet), so it is
    # no longer a reserved word. The table and column still reach
    # pg_get_serial_sequence as bind parameters because it takes them as *text*.
    db.session.execute(
        text(
            "SELECT setval(pg_get_serial_sequence(:tbl, :col), "
            "COALESCE((SELECT MAX(id) FROM users), 0) + 1, false)"
        ),
        {"tbl": "users", "col": "id"},
    )
    db.session.commit()


@pytest.fixture()
def seed_user(client):
    """Create ``users`` rows with the explicit ids a test's child rows point at.

    Several tests assert things *about a specific user id* -- that completion is
    per-user rather than global, that a stale scoring key does not satisfy the current
    instrument's gate -- so the id is load-bearing and cannot be replaced with whatever
    the sequence happens to hand out.  This seeds the parent row those ids need.

    Depends on ``client`` so the tables exist first, and so both fixtures share one
    database lifecycle: the teardown that drops the schema also removes these rows.
    """
    from app import app
    from model import User, db

    def _seed(*user_ids: int) -> None:
        with app.app_context():
            for user_id in user_ids:
                db.session.add(
                    User(
                        id=user_id,
                        email="seeded-%d@example.test" % user_id,
                        password_hash="not-a-real-hash",
                    )
                )
            db.session.commit()
            _resync_identity_sequence(db)

    return _seed
