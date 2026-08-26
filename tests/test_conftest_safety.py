"""Tests for the guards in conftest.py.

Regression cover for 2026-08-26, when a production DATABASE_URL was exported in
a shell for a migration. Running pytest in that same shell would have called
db.drop_all() against production: conftest uses os.environ.setdefault, so an
already-set URL wins, and nothing checked where it pointed.
"""

import os

import pytest

from conftest import LOCAL_HOSTS, _refuse_non_local_database


# --------------------------------------------------------------------- allowed
@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///test.db",
        "sqlite:///:memory:",
        "sqlite:////absolute/path/test.db",
        "sqlite+pysqlite:///test.db",
        "postgresql://solverah:solverah@localhost:5432/solverah",
        "postgresql://u:p@127.0.0.1:5432/solverah",
        "postgresql://u:p@[::1]:5432/solverah",
        "postgresql+psycopg2://u:p@localhost/solverah",
        "postgresql://u:p@db:5432/solverah",        # docker-compose service alias
        "postgresql://u:p@postgres:5432/solverah",
    ],
)
def test_local_databases_are_allowed(url):
    _refuse_non_local_database(url)  # must not raise


def test_every_declared_local_host_is_accepted():
    """LOCAL_HOSTS and the check must not drift apart."""
    for host in LOCAL_HOSTS:
        if not host:
            continue
        # An IPv6 literal has to be bracketed in a URL, or the trailing :5432
        # makes the whole authority unparseable.
        authority = "[%s]" % host if ":" in host else host
        _refuse_non_local_database("postgresql://u:p@%s:5432/solverah" % authority)


# --------------------------------------------------------------------- refused
def test_the_production_url_shape_is_refused():
    """The exact case this guard exists for."""
    with pytest.raises(RuntimeError) as exc:
        _refuse_non_local_database(
            "postgresql://solverah_postgres_user:hunter2"
            "@dpg-abc123-a.virginia-postgres.render.com/solverah_postgres"
        )

    assert "REFUSING TO RUN TESTS" in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@db.example.com:5432/app",
        "postgresql://u:p@10.0.0.5:5432/app",           # private, but not this machine
        "postgresql://u:p@some-host.rds.amazonaws.com/app",
        "mysql://u:p@mysql.internal/app",
    ],
)
def test_remote_databases_are_refused(url):
    with pytest.raises(RuntimeError):
        _refuse_non_local_database(url)


def test_the_refusal_does_not_echo_the_password():
    """The message is printed to a terminal and pasted into bug reports."""
    with pytest.raises(RuntimeError) as exc:
        _refuse_non_local_database("postgresql://someuser:sup3rs3cret@prod.example.com/app")

    message = str(exc.value)
    assert "sup3rs3cret" not in message
    assert "prod.example.com" in message   # the host is what the reader needs


def test_the_refusal_says_how_to_recover():
    with pytest.raises(RuntimeError) as exc:
        _refuse_non_local_database("postgresql://u:p@prod.example.com/app")

    message = str(exc.value)
    assert "Remove-Item Env:DATABASE_URL" in message
    assert "unset DATABASE_URL" in message


def test_an_unparseable_url_is_refused_rather_than_assumed_safe():
    with pytest.raises(RuntimeError):
        _refuse_non_local_database("this is not a url")


# ------------------------------------------------------- the suite's own state
def test_this_run_is_pointed_at_a_local_database():
    """Belt and braces: assert the guard actually held for this session."""
    _refuse_non_local_database(os.environ["DATABASE_URL"])


def test_the_teardown_removes_the_database_flask_actually_writes(client):
    """The resolved SQLite path must be the one under instance/, not ./test.db.

    `sqlite:///test.db` is relative, and Flask-SQLAlchemy resolves relative
    SQLite paths against app.instance_path. The old teardown removed "test.db"
    from the working directory -- a file that never existed -- so the real
    database was never deleted and leaked state into every later run.
    """
    from app import app
    from model import db

    # db.engine resolves against the current app, so this needs a context of its
    # own -- the client fixture yields a test client, not an active app context.
    with app.app_context():
        url = db.engine.url
        if not url.drivername.startswith("sqlite") or url.database == ":memory:":
            pytest.skip("only meaningful for a file-backed SQLite run")

        assert os.path.isabs(url.database), "the resolved path must be absolute"
        assert os.path.dirname(url.database) == app.instance_path, (
            "Flask writes the database under instance/; teardown must delete that "
            "path, not a bare 'test.db' in the working directory"
        )
