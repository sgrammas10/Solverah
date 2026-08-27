"""Shared pytest fixtures, and the guards that make running them safe.

Two defects lived here and both bit on 2026-08-26.

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
"""

import os

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
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


def _enforce_sqlite_foreign_keys() -> None:
    """Make SQLite reject orphan foreign keys, the way Postgres always has.

    SQLite ships with foreign-key enforcement OFF and it is a per-connection pragma,
    so an FK declared in the schema is documentation and nothing more until someone
    turns it on.  Nobody had.  Eight tests across four files inserted child rows
    naming a ``user_id`` no ``user`` row ever had; all eight passed for as long as the
    suite ran on SQLite and all eight failed the hour CI moved to Postgres
    (2026-08-27).  The rows were orphans on both databases.  Only one of the two said so.

    The SQLite job is kept for speed, and a fast job that is *laxer* than the gate is
    worse than no fast job: it reports green on precisely the defects the gate exists
    to catch, so the first real signal arrives minutes later from the slower run.  This
    listener closes that gap -- both jobs now enforce the same integrity rules.
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
    """Advance ``user.id``'s sequence past any hand-assigned ids.

    Supplying a primary key explicitly does not consume a value from the sequence
    backing it, so the next ``User()`` inserted without an id is handed 1 and collides
    with the seeded row.  SQLite has no sequence and needs nothing.
    """
    if db.engine.url.drivername.startswith("sqlite"):
        return

    from sqlalchemy import text

    # `user` is a reserved word in Postgres, hence the quoting (P1-8 renames the table
    # to `users` in Phase 2; until then every reference has to carry the quotes).
    # The table and column reach pg_get_serial_sequence as bind parameters because it
    # takes them as *text*, so inlining them would mean a quoted literal inside a
    # quoted literal for no benefit.
    db.session.execute(
        text(
            "SELECT setval(pg_get_serial_sequence(:tbl, :col), "
            'COALESCE((SELECT MAX(id) FROM "user"), 0) + 1, false)'
        ),
        {"tbl": '"user"', "col": "id"},
    )
    db.session.commit()


@pytest.fixture()
def seed_user(client):
    """Create ``user`` rows with the explicit ids a test's child rows point at.

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
                        password="not-a-real-hash",
                    )
                )
            db.session.commit()
            _resync_identity_sequence(db)

    return _seed
