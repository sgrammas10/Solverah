"""Tests for the guards in conftest.py.

Regression cover for two days.

**2026-08-26**, when a production DATABASE_URL was exported in a shell for a
migration. Running pytest in that same shell would have called db.drop_all()
against production: conftest uses os.environ.setdefault, so an already-set URL
wins, and nothing checked where it pointed.

**2026-08-27**, when a suite failure reported as "920 passed, 36 failed, 132
errors, Phase 2d caused it" turned out to be two pytest processes sharing one
database. Nothing stopped them: conftest's setdefault, the Makefile's
``DATABASE_URL ?=`` and ``Scripts/capture_contract.py`` all resolved to the same
URL, and one of the three drops the schema. The bottom half of this file covers
both halves of that fix -- the per-tool databases, and the claim that catches
two runs which inherit the same one anyway.
"""

import os
import pathlib
import re

import pytest

from conftest import (
    LOCAL_HOSTS,
    REQUIRED_EXTENSIONS,
    TEST_DATABASE_URL,
    _claim_database_or_refuse,
    _refuse_non_local_database,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


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


# ------------------------------------------------- one database per tool (D-1a)
#
# Changing only conftest's default would leave `make test-pg` -- the documented
# gate command -- on the shared dev database, which buys nothing. These read the
# other two files rather than trusting that someone kept them in step.

def _makefile_default() -> str:
    text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^DATABASE_URL \?= (.+)$", text, re.MULTILINE)
    assert match, "Makefile no longer declares a default DATABASE_URL"
    return match.group(1).strip()


def _capture_contract_default() -> str:
    from Scripts.capture_contract import CONTRACT_DATABASE_URL

    return CONTRACT_DATABASE_URL


def test_the_three_defaults_are_three_different_databases():
    """The whole fix, stated once.

    conftest, the Makefile and capture_contract each drop what they find --
    drop_all() twice and DROP SCHEMA public CASCADE once. Any two of them sharing
    a database destroy each other mid-run.
    """
    from sqlalchemy.engine import make_url

    names = {
        "tests/conftest.py": make_url(TEST_DATABASE_URL).database,
        "Makefile": make_url(_makefile_default()).database,
        "Scripts/capture_contract.py": make_url(_capture_contract_default()).database,
    }
    assert len(set(names.values())) == len(names) - 1, (
        "conftest and the Makefile must name the same database (the Makefile "
        "reproduces the suite), and capture_contract must not share it: %r" % names
    )
    assert names["tests/conftest.py"] == names["Makefile"]
    assert names["Scripts/capture_contract.py"] != names["tests/conftest.py"]


def test_no_default_is_the_database_make_dev_uses():
    """`solverah` belongs to the dev stack, and these tools drop what they find."""
    from sqlalchemy.engine import make_url

    for source, url in (
        ("tests/conftest.py", TEST_DATABASE_URL),
        ("Makefile", _makefile_default()),
        ("Scripts/capture_contract.py", _capture_contract_default()),
    ):
        assert make_url(url).database != "solverah", (
            "%s defaults to the database `make dev` runs on; it calls "
            "drop_all()/DROP SCHEMA on it" % source
        )


def test_every_default_database_is_created_by_the_stack():
    """A default nothing creates is a default that fails on a fresh machine."""
    from sqlalchemy.engine import make_url

    initdb = (
        REPO_ROOT / "infra" / "docker" / "initdb" / "02-lane-databases.sql"
    ).read_text(encoding="utf-8")

    for url in (TEST_DATABASE_URL, _makefile_default(), _capture_contract_default()):
        name = make_url(url).database
        assert "CREATE DATABASE %s" % name in initdb, (
            "%s is defaulted to but never created; `make test-pg` would fail on "
            "a fresh stack" % name
        )


# ------------------------------------------- one process per database (D-1b)

def _skip_unless_postgres():
    from sqlalchemy.engine import make_url

    if make_url(os.environ["DATABASE_URL"]).get_backend_name() != "postgresql":
        pytest.skip("the claim is a Postgres advisory lock")


def test_sqlite_is_not_claimed():
    """A file per URL cannot be shared the way one server database can."""
    assert _claim_database_or_refuse("sqlite:///test.db") is None
    assert _claim_database_or_refuse("sqlite:///:memory:") is None


def test_a_second_claim_on_this_database_is_refused():
    """This session already holds the claim, so this call must not get it.

    Two things at once, and the second is the subtle one.

    It proves the guard refuses a database that is already spoken for -- the
    2026-08-27 failure, where two pytest processes ran on one database and the
    only symptom was 132 errors naming `user_role`.

    It also proves the claim is still *held*. pg_advisory_lock is scoped to a
    connection, and SQLAlchemy pools connections: taken on a pooled one it would
    have been released the moment it was checked back in, minutes ago, and this
    call would succeed. That is the version of this guard that passes its own
    tests and stops nothing.
    """
    _skip_unless_postgres()

    connection = None
    try:
        with pytest.raises(RuntimeError) as exc:
            connection = _claim_database_or_refuse(os.environ["DATABASE_URL"])
    finally:
        if connection is not None:  # the pooled-connection bug; do not leak it
            connection.close()

    assert "ANOTHER PROCESS IS ALREADY USING THIS TEST" in str(exc.value)


def test_the_refusal_says_how_to_get_a_database_of_your_own():
    """The message is the deliverable.

    The failure this replaces named `user_role` 132 times and pointed at the
    wrong phase for hours. A refusal that stops the run without saying what to
    do next just relocates the confusion.
    """
    _skip_unless_postgres()

    connection = None
    try:
        with pytest.raises(RuntimeError) as exc:
            connection = _claim_database_or_refuse(os.environ["DATABASE_URL"])
    finally:
        if connection is not None:
            connection.close()

    message = str(exc.value)
    assert "CREATE DATABASE" in message
    for extension in REQUIRED_EXTENSIONS:
        assert "CREATE EXTENSION IF NOT EXISTS %s" % extension in message
    # A schema is not enough: enum types live in pg_type and outlive
    # DROP SCHEMA ... CASCADE. Anyone who tries that instead is back where they
    # started, colliding on `user_role`.
    assert "schema" in message and "pg_type" in message
    assert "user_role" in message


def test_the_claim_refusal_does_not_echo_the_password():
    """Same rule as the non-local guard: this gets pasted into bug reports."""
    _skip_unless_postgres()

    connection = None
    try:
        with pytest.raises(RuntimeError) as exc:
            connection = _claim_database_or_refuse(os.environ["DATABASE_URL"])
    finally:
        if connection is not None:
            connection.close()

    message = str(exc.value)
    # Asserted on the mask rather than on the password's absence: the compose
    # credentials are `solverah`/`solverah`, so a literal search for the password
    # matches the username and the database name and passes either way.
    reported = [line for line in message.splitlines() if "://" in line and "@" in line]
    assert reported, message
    assert ":***@" in reported[0], reported[0]


def test_an_unreachable_database_explains_itself_rather_than_stack_tracing():
    """The other way this bites: a default nobody has created yet.

    Pointing pytest at a database that does not exist used to surface as
    whatever psycopg2 said at the first fixture, repeated once per test.
    """
    _skip_unless_postgres()

    from sqlalchemy.engine import make_url

    absent = make_url(os.environ["DATABASE_URL"]).set(
        database="solverah_no_such_database"
    )

    with pytest.raises(RuntimeError) as exc:
        _claim_database_or_refuse(absent.render_as_string(hide_password=False))

    message = str(exc.value)
    assert "cannot reach the test database" in message
    assert "docker compose -f infra/docker/compose.yml up -d db" in message
    assert "CREATE DATABASE" in message


def test_an_authentication_failure_names_the_shadowing_service():
    """The failure mode that made `up -d db` look like it worked when it had not.

    Windows lets a native Postgres service and Docker both bind one port instead
    of refusing the second, and the native one answers. Every other signal says
    the database is healthy -- `docker compose ps db` says so, `docker compose
    exec db psql` connects -- and only the published port is a lie. What reaches
    the developer is `password authentication failed`, which reads as a typo in
    credentials that live in compose.yml and that nobody types.
    """
    _skip_unless_postgres()

    from sqlalchemy.engine import make_url

    wrong = make_url(os.environ["DATABASE_URL"]).set(password="not-the-password")

    with pytest.raises(RuntimeError) as exc:
        _claim_database_or_refuse(wrong.render_as_string(hide_password=False))

    message = str(exc.value)
    assert "cannot reach the test database" in message
    assert "Get-Service postgresql*" in message
    assert "netstat -ano" in message
    # And it must still say the ordinary thing, since the ordinary cause is real.
    assert "docker compose -f infra/docker/compose.yml up -d db" in message


def test_a_missing_database_does_not_blame_a_shadowing_service():
    """The shadow paragraph is conditional, or it is noise on every other failure."""
    _skip_unless_postgres()

    from sqlalchemy.engine import make_url

    absent = make_url(os.environ["DATABASE_URL"]).set(
        database="solverah_no_such_database"
    )

    with pytest.raises(RuntimeError) as exc:
        _claim_database_or_refuse(absent.render_as_string(hide_password=False))

    assert "Get-Service postgresql*" not in str(exc.value)
