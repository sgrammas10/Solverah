"""The safety catch. Written before anything that touches a database.

Every script in this package calls `assert_local_dev_database(url)` on the URL it
is ABOUT to connect with -- not on os.environ, not on a default, on the actual
string that will be handed to create_engine. A guard that checks a different value
than the one used is not a guard.

WHAT IT IS GUARDING AGAINST
---------------------------
Two concrete hazards, both of which have bitten this repo before:

1. **The repo's own .env carries a Render-internal PRODUCTION DATABASE_URL**, and
   `app.py` calls `load_dotenv()`. A script that merely read `os.environ` after an
   import of the app would connect to production without anyone typing a
   production hostname. Hence `require_database_url()`: these scripts refuse to
   run without an EXPLICIT --database-url or DATABASE_URL, and the caller is
   expected to pass SOLVERAH_IGNORE_DOTENV=1 as well.

2. **`seed_synthetic.py` writes rows and `--reset` deletes them.** The blast
   radius of running that against anything real is the whole point of this file.

THE THREE CONDITIONS, all of which must hold:

  * host is `localhost` or `127.0.0.1` -- a socket that cannot leave this machine.
    An EMPTY host is refused (libpq would read PGHOST), and so is any query
    parameter outside SAFE_QUERY_KEYS (the driver lets `?host=` / `?dbname=` /
    `?hostaddr=` / `?service=` override what the URL visibly says)
  * database name starts with `solverah_modeldev` -- a name nothing else uses, so
    a right-host-wrong-database mistake still refuses
  * `APP_ENV` is not `production`

Deliberately NOT a warning, a prompt, or a `--force` flag: the refusal is the
feature. There is no override, because an override is what gets typed at 2am.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlsplit

#: The only hostnames that cannot reach another machine.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# NOT the empty host. `postgresql:///db` makes libpq take its host from the PGHOST
# environment variable (or a service file), so an empty host is "wherever the
# environment points", which is exactly what this guard exists to not trust.

#: The ONLY query parameters a guarded URL may carry. An allowlist, because the
#: dangerous ones are open-ended: SQLAlchemy merges the query string into the
#: driver's connect arguments AFTER the URL's own host and database, so
#: `?host=prod.example.com`, `?hostaddr=10.0.0.9`, `?dbname=solverah_postgres` and
#: `?service=prod` each redirect a URL whose visible host and path look perfectly
#: local (verified 2026-09-21 against PGDialect_psycopg2.create_connect_args). None
#: of these can change WHERE the connection goes.
SAFE_QUERY_KEYS = frozenset(
    {"sslmode", "application_name", "connect_timeout", "client_encoding"}
)

#: Every database this harness may touch starts with this. `solverah_modeldev`
#: itself is the pipeline database; the prefix leaves room for
#: `solverah_modeldev_b` and friends without widening the rule.
DEV_DB_PREFIX = "solverah_modeldev"

#: The pilot-form research database (`causal_graph/v1_model/pilot_form/`). Its
#: own prefix rather than a widening of DEV_DB_PREFIX: pilot rows are REAL
#: respondents and synthetic cohorts must never land beside them, so each
#: harness accepts only its own family of names. Same three conditions, same
#: refusal, no override.
PILOT_DB_PREFIX = "solverah_pilot"


class UnsafeDatabaseError(RuntimeError):
    """The URL is not a local model-dev database. Never downgraded to a warning."""


def _database_name(url: str) -> str:
    """The path component without its leading slash. Bare, so a URL with query
    parameters (?sslmode=require -- itself a sign of a remote database) does not
    smuggle them into the name comparison."""
    return urlsplit(url).path.lstrip("/")


def _host(url: str) -> str:
    """Hostname only, lower-cased, no port and no credentials. `urlsplit().hostname`
    already strips user:pass@ -- which matters, because a URL like
    `postgresql://localhost:pw@prod.example.com/db` would otherwise read as local
    to a naive substring check."""
    return (urlsplit(url).hostname or "").lower()


def assert_local_dev_database(url: str, *, app_env: str | None = None) -> str:
    """Raise UnsafeDatabaseError unless `url` is a local model-dev database.

    Returns the url unchanged on success, so it can be used inline:

        engine = create_engine(assert_local_dev_database(url))

    `app_env` defaults to os.environ["APP_ENV"]; it is a parameter so the check
    itself is testable without mutating the process environment.
    """
    return assert_local_database(url, prefix=DEV_DB_PREFIX, app_env=app_env)


def assert_local_database(url: str, *, prefix: str, app_env: str | None = None) -> str:
    """The guard itself, for any database-name family (`DEV_DB_PREFIX`,
    `PILOT_DB_PREFIX`). Every condition in the module docstring applies; only
    the required name prefix differs."""
    if not prefix:
        raise UnsafeDatabaseError("no database-name prefix given -- refusing to guess")
    if not isinstance(url, str) or not url.strip():
        raise UnsafeDatabaseError(
            "no database URL given -- this harness never falls back to a default "
            "or to whatever .env happens to hold (the repo's .env carries a "
            "PRODUCTION URL). Pass --database-url or set DATABASE_URL explicitly."
        )

    env = os.environ.get("APP_ENV", "") if app_env is None else app_env
    if env.strip().lower() == "production":
        raise UnsafeDatabaseError(
            "APP_ENV=production -- refusing to run a dev harness in a production "
            "environment regardless of which database the URL names"
        )

    redirecting = sorted(
        key for key, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)
        if key.lower() not in SAFE_QUERY_KEYS
    )
    if redirecting:
        raise UnsafeDatabaseError(
            "database URL carries query parameter(s) %s -- the driver merges the "
            "query string over the URL's own host and database, so these can send "
            "the connection somewhere the visible host and path do not name. Only "
            "%s are allowed here." % (redirecting, sorted(SAFE_QUERY_KEYS))
        )

    host = _host(url)
    if host not in LOCAL_HOSTS:
        raise UnsafeDatabaseError(
            "database host %r is not local -- this harness seeds, deletes and "
            "prints raw model numbers, and may only ever run against %s"
            % (host, " or ".join(sorted(h for h in LOCAL_HOSTS if h)))
        )

    name = _database_name(url)
    if not name.startswith(prefix):
        raise UnsafeDatabaseError(
            "database %r does not start with %r -- a local host is not enough. "
            "The pipeline database is `%s`; the app's own database, the test "
            "databases and every other lane's database are all off limits here."
            % (name, prefix, prefix)
        )

    return url


def require_database_url(explicit: str | None = None, *, prefix: str = DEV_DB_PREFIX) -> str:
    """The URL these scripts will actually use, guarded.

    `explicit` is the --database-url argument. Falling back to the DATABASE_URL
    environment variable is allowed (it is how the migration step is run too), but
    there is no third fallback: no default, no config file, no .env read. If
    neither is set, this raises rather than connecting to something unnamed.
    """
    url = explicit or os.environ.get("DATABASE_URL") or ""
    return assert_local_database(url, prefix=prefix)


def add_database_argument(parser) -> None:
    """The one flag every script in this package shares, worded the same way."""
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "postgresql://... for a local solverah_modeldev* database. Falls back "
            "to $DATABASE_URL. Refused unless host is local, the database name "
            "starts with %r, and APP_ENV is not production." % DEV_DB_PREFIX
        ),
    )
