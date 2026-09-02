"""The CI database must be able to do what the production database can do.

Moving CI onto Postgres (2026-08-27) removed the divergence in P1-9 -- the suite no
longer proves things about SQLite and hopes they hold on Postgres.  It does not, by
itself, keep that true.  A service-container image is one line in a workflow file, and
the reason a particular line was chosen lives in a YAML comment nobody reads while
bumping a tag.

So the reasons are asserted here instead.

Measured against Render on 2026-08-27, from `SELECT version()`:

    PostgreSQL 18.3 (Debian 18.3-1.pgdg12+1) on x86_64-pc-linux-gnu

and `citext` 1.8, `pg_trgm` 1.6, and `vector` 0.8.1 are all installable by the
application role.  Everything below follows from that measurement.

The failure this prevents is specific and quiet.  `docs/ARCHITECTURE.md` Part 4 gives
every table `public_id UUID NOT NULL DEFAULT uuidv7()`, and `uuidv7()` is a Postgres 18
built-in with no Postgres 16 equivalent.  On a pg16 runner every Phase 2 migration would
fail against a schema production accepts without complaint -- and the tempting fix, of
generating ids in the application instead, would be a permanent change to every table in
Part 4 made to satisfy a CI container rather than a real constraint.

These tests skip on SQLite rather than fail: the SQLite job is deliberately non-gating
early signal, and it is not expected to satisfy any of this.
"""

import pytest


MINIMUM_SERVER_VERSION_NUM = 180000  # 18.0 -- the release that introduced uuidv7()

# Declared by infra/docker/initdb/01-extensions.sql, created as a step in the CI
# Postgres job, and required by Part 4: citext for case-insensitive email uniqueness,
# pg_trgm for skill-label search, vector for the culture ANN index that replaces the
# load-every-company-and-score-in-Python scan (P0-2).
REQUIRED_EXTENSIONS = ("citext", "pg_trgm", "vector")


@pytest.fixture()
def pg(client):
    """A connection to the test database, or a skip if it is not Postgres."""
    from app import app
    from model import db

    with app.app_context():
        if not db.engine.url.drivername.startswith("postgresql"):
            pytest.skip("Postgres-only: asserts capabilities SQLite does not have")
        yield db


def test_server_is_new_enough_for_uuidv7(pg):
    """Part 4 defaults every public_id to uuidv7(), which is Postgres 18 or nothing."""
    from sqlalchemy import text

    version_num = pg.session.execute(text("SHOW server_version_num")).scalar()

    assert int(version_num) >= MINIMUM_SERVER_VERSION_NUM, (
        "This database is server_version_num=%s; Part 4 needs >= %d.\n"
        "Render runs 18.3. A runner older than the production server turns every "
        "uuidv7() default into a CI-only failure, and 'generate ids in Python instead' "
        "is not the fix -- bump the service-container image in "
        ".github/workflows/tests.yml." % (version_num, MINIMUM_SERVER_VERSION_NUM)
    )


def test_uuidv7_is_callable_and_time_ordered(pg):
    """Not just present: actually returning v7 UUIDs, which are ordered by creation.

    Time-ordering is the whole reason Part 4 specifies v7 over v4 -- a random UUID
    primary key scatters inserts across the index and destroys locality on exactly the
    append-only tables that take the most writes.
    """
    from sqlalchemy import text

    first, second = pg.session.execute(text("SELECT uuidv7(), uuidv7()")).one()

    # Version nibble: the 13th hex digit of a v7 UUID is '7'.
    assert str(first)[14] == "7", "uuidv7() did not return a version-7 UUID: %s" % first
    assert str(first) < str(second), (
        "uuidv7() values are not ascending (%s !< %s); without that ordering v7 buys "
        "nothing over v4." % (first, second)
    )


@pytest.mark.parametrize("extension", REQUIRED_EXTENSIONS)
def test_required_extension_is_installed(pg, extension):
    """Installed, not merely available -- a migration cannot wait for someone to notice."""
    from sqlalchemy import text

    installed = pg.session.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = :name"),
        {"name": extension},
    ).scalar()

    assert installed is not None, (
        "Extension %r is not installed in the test database.\n"
        "Locally: `docker compose -f infra/docker/compose.yml up` runs "
        "infra/docker/initdb/01-extensions.sql. In CI the 'Enable required extensions' "
        "step does it, because a service container starts before checkout and cannot "
        "mount that file." % extension
    )


def test_foreign_keys_are_enforced(client):
    """The defect class that moving to Postgres actually caught.

    Eight tests inserted child rows naming a parent id that no parent row had. SQLite
    accepted every one, because its foreign-key enforcement is off by default and is a
    per-connection pragma -- so a foreign key declared in the schema was documentation
    and nothing else.

    This one deliberately does NOT skip on SQLite. It is the assertion that conftest's
    `PRAGMA foreign_keys=ON` is actually reaching the connection, which is the only
    thing making the fast job trustworthy rather than merely quick. It runs against a
    throwaway pair of tables so it asks about the database's behaviour and not about
    any particular application table.
    """
    from app import app
    from model import db
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        db.session.execute(text("CREATE TABLE fk_probe_parent (id INTEGER PRIMARY KEY)"))
        db.session.execute(
            text(
                "CREATE TABLE fk_probe_child ("
                "  id        INTEGER PRIMARY KEY,"
                "  parent_id INTEGER NOT NULL REFERENCES fk_probe_parent(id))"
            )
        )
        db.session.commit()
        try:
            with pytest.raises(IntegrityError):
                db.session.execute(
                    text("INSERT INTO fk_probe_child (id, parent_id) VALUES (1, 999)")
                )
                db.session.commit()
        finally:
            # These tables are not in the SQLAlchemy metadata, so the fixture's
            # drop_all() will not remove them.
            db.session.rollback()
            db.session.execute(text("DROP TABLE fk_probe_child"))
            db.session.execute(text("DROP TABLE fk_probe_parent"))
            db.session.commit()
