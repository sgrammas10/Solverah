"""Tests for solverah.config — environment validation and engine options."""

import os

import pytest

from solverah.config import ConfigError, Settings

BASE_ENV = {
    "APP_ENV": "development",
    "DATABASE_URL": "postgresql://u:p@localhost:5432/solverah",
    "JWT_SECRET_KEY": "x" * 40,
}

PROD_ENV = dict(
    BASE_ENV,
    APP_ENV="production",
    JWT_COOKIE_SECURE="true",
    JWT_COOKIE_SAMESITE="None",
)


def test_valid_env_builds_settings():
    s = Settings.from_env(BASE_ENV)

    assert s.env == "development"
    assert s.is_production is False
    assert s.database_url == BASE_ENV["DATABASE_URL"]
    assert s.jwt_cookie_samesite == "Lax"   # dev default
    assert s.trusted_proxy_count == 0       # no proxy locally


def test_production_defaults_differ_from_development():
    s = Settings.from_env(PROD_ENV)

    assert s.is_production is True
    assert s.jwt_cookie_secure is True
    assert s.jwt_cookie_samesite == "None"
    assert s.trusted_proxy_count == 1       # Render terminates at exactly one proxy
    assert s.log_format == "json"


def test_missing_required_values_are_reported():
    with pytest.raises(ConfigError) as exc:
        Settings.from_env({})

    problems = " ".join(exc.value.problems)
    assert "DATABASE_URL" in problems
    assert "JWT_SECRET_KEY" in problems


def test_all_problems_reported_together():
    """One ConfigError must carry every failure, not just the first.

    The point of the class: an operator fixes a bad deploy in one pass instead
    of discovering the next missing variable on the next restart.
    """
    with pytest.raises(ConfigError) as exc:
        Settings.from_env({"JWT_COOKIE_SECURE": "maybe", "DB_POOL_SIZE": "huge"})

    problems = " ".join(exc.value.problems)
    assert len(exc.value.problems) >= 4
    assert "DATABASE_URL" in problems
    assert "JWT_SECRET_KEY" in problems
    assert "JWT_COOKIE_SECURE" in problems
    assert "DB_POOL_SIZE" in problems


def test_unrecognised_boolean_is_an_error_not_a_silent_false():
    """`JWT_COOKIE_SECURE=TRU` must fail loudly.

    A permissive `value in {"1","true"}` check would read this as False and
    silently disable secure cookies in production.
    """
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(dict(BASE_ENV, JWT_COOKIE_SECURE="TRU"))

    assert any("JWT_COOKIE_SECURE" in p for p in exc.value.problems)


@pytest.mark.parametrize(
    "override,expected_fragment",
    [
        ({"DATABASE_URL": "sqlite:///prod.db"}, "SQLite"),
        ({"JWT_SECRET_KEY": "short"}, "32 characters"),
        ({"JWT_COOKIE_SECURE": "false"}, "JWT_COOKIE_SECURE"),
    ],
)
def test_production_rules_are_enforced(override, expected_fragment):
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(dict(PROD_ENV, **override))

    assert any(expected_fragment in p for p in exc.value.problems)


def test_samesite_none_requires_secure():
    """Browsers drop a SameSite=None cookie that is not Secure.

    The failure is silent client-side -- every authenticated request just fails
    with no server-side error -- so it has to be caught at boot.
    """
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(
            dict(BASE_ENV, JWT_COOKIE_SAMESITE="None", JWT_COOKIE_SECURE="false")
        )

    assert any("SameSite" in p or "SAMESITE" in p for p in exc.value.problems)


def test_invalid_samesite_value_rejected():
    with pytest.raises(ConfigError):
        Settings.from_env(dict(BASE_ENV, JWT_COOKIE_SAMESITE="Loose"))


def test_memory_rate_limit_in_production_warns_but_does_not_fail():
    """Per-worker limits are wrong, but not a reason to refuse to boot."""
    s = Settings.from_env(PROD_ENV)

    assert s.ratelimit_storage_uri == "memory://"
    assert any("RATELIMIT_STORAGE_URI" in w for w in s.warnings)


def test_redis_url_backs_rate_limiting_when_set():
    s = Settings.from_env(dict(PROD_ENV, REDIS_URL="redis://cache:6379/0"))

    assert s.ratelimit_storage_uri == "redis://cache:6379/0"
    assert s.warnings == []


def test_engine_options_for_postgres_include_pooling_and_timeout():
    s = Settings.from_env(dict(BASE_ENV, DB_POOL_SIZE="20", DB_STATEMENT_TIMEOUT_MS="5000"))
    opts = s.engine_options()

    assert opts["pool_pre_ping"] is True
    assert opts["pool_size"] == 20
    assert "statement_timeout=5000" in opts["connect_args"]["options"]


def test_engine_options_for_sqlite_omit_unsupported_keys():
    """SQLite has no pool sizing and no statement_timeout; passing them errors at connect."""
    s = Settings.from_env(dict(BASE_ENV, DATABASE_URL="sqlite:///test.db"))
    opts = s.engine_options()

    assert opts == {"pool_pre_ping": True}


def test_out_of_range_numeric_is_rejected():
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(dict(BASE_ENV, DB_POOL_SIZE="0"))

    assert any("DB_POOL_SIZE" in p for p in exc.value.problems)


def test_redacted_never_exposes_secrets():
    s = Settings.from_env(
        dict(BASE_ENV, OPENAI_API_KEY="sk-live-abcdef", DATABASE_URL="postgresql://u:hunter2@db:5432/app")
    )
    blob = repr(s.redacted())

    assert "hunter2" not in blob
    assert "sk-live-abcdef" not in blob
    assert s.redacted()["providers"]["openai"] is True
    assert s.redacted()["database"] == "postgresql://db:5432/app"


def test_settings_are_immutable():
    """Configuration that can change after boot can differ between two workers."""
    s = Settings.from_env(BASE_ENV)

    with pytest.raises(Exception):
        s.database_url = "postgresql://elsewhere/db"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# .env suppression (SOLVERAH_IGNORE_DOTENV)
#
# app.py calls load_dotenv(), so a developer with a populated .env has every
# variable in it available and CI -- which sets five and has no .env -- does
# not. A test reaching code that reads anything else is green locally and red
# on the runner. `make test-ci` sets this flag so the two agree.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", True), ("true", True), ("TRUE", True), ("  yes  ", True),
        ("y", True), ("on", True),
        ("0", False), ("false", False), ("no", False), ("off", False),
        ("", False), ("   ", False), (None, False),
        # Permissive by design: an unrecognised value means "off", which for
        # this flag is the normal developer behaviour. Anything gating security
        # uses the strict reader instead, which rejects "TRU" rather than
        # silently treating it as False.
        ("TRU", False), ("maybe", False),
    ],
)
def test_is_truthy_truth_table(raw, expected):
    from solverah.config import is_truthy

    assert is_truthy(raw) is expected


def test_app_guards_load_dotenv_behind_the_flag():
    """Deleting the guard restores the failure mode it exists to prevent.

    A source check rather than a behavioural one: app.py is imported once per
    session and load_dotenv() has already run by the time any test executes, so
    there is nothing left to observe at runtime.
    """
    import io as _io
    import re

    source = _io.open("app.py", encoding="utf-8").read()

    assert "SOLVERAH_IGNORE_DOTENV" in source, "the .env guard is gone"
    # The call must be conditional, not bare.
    bare = re.search(r"^load_dotenv\(\)", source, re.MULTILINE)
    assert bare is None, "load_dotenv() is called unconditionally"
    assert re.search(
        r"if not is_truthy\(os\.environ\.get\(IGNORE_DOTENV_VAR\)\):\s*\n\s+load_dotenv\(\)",
        source,
    ), "load_dotenv() is no longer guarded by IGNORE_DOTENV_VAR"


CI_VARIABLES = (
    "APP_ENV",
    "DATABASE_URL",
    "JWT_SECRET_KEY",
    "JWT_COOKIE_SECURE",
    "JWT_COOKIE_SAMESITE",
)

# Each backend CI job and the make target that reproduces it. One, as of Phase 2a:
# the `backend-tests-sqlite` job and its `test-ci` target were retired on 2026-08-27
# because the Part 4.3 profile tables cannot be created on SQLite at all.
#
# The pairing is still worth asserting with a single entry in it. A target that has
# drifted from its job is a target that lies, and `make test-pg` is now the only way
# to find out what CI will say without pushing.
BACKEND_JOBS = (
    ("backend-tests-postgres:", "test-pg:"),
)


@pytest.mark.parametrize("job_anchor, target_anchor", BACKEND_JOBS)
def test_make_targets_reproduce_the_ci_backend_jobs(job_anchor, target_anchor):
    """Every backend CI job must have a make target that is an honest copy of it.

    If a job's env block gains a variable and its target does not, the target quietly
    stops matching and the gap it exists to close reopens.
    """
    import io as _io

    makefile = _io.open("Makefile", encoding="utf-8").read()
    assert job_anchor.rstrip(":") in _io.open(
        ".github/workflows/tests.yml", encoding="utf-8"
    ).read(), (
        "CI job %r is gone. If a backend job was renamed or removed, update "
        "BACKEND_JOBS -- do not delete the pairing." % job_anchor
    )
    recipe = makefile.split(target_anchor, 1)[1].split(".PHONY", 1)[0]

    # Anchor on the job first: "Run Tests" also names the frontend step, which runs npm
    # and carries no env block.
    workflow = _io.open(".github/workflows/tests.yml", encoding="utf-8").read()
    backend_job = workflow.split(job_anchor, 1)[1]
    ci_env = backend_job.split("- name: Run Tests", 1)[1].split("run:", 1)[0]

    assert "SOLVERAH_IGNORE_DOTENV=1" in recipe, (
        "%s does not suppress .env, so it runs with secrets the runner does not have"
        % target_anchor
    )

    for name in CI_VARIABLES:
        assert name in ci_env, "CI no longer sets %s; update this test" % name
        assert name in recipe, "make %s does not set %s, but CI does" % (
            target_anchor,
            name,
        )


def test_the_postgres_job_is_the_gate_and_is_the_only_backend_job():
    """Postgres decides, and nothing runs beside it that could disagree.

    This used to assert that the SQLite job carried `continue-on-error: true`, so a
    database the product does not run on could not block a build -- or, worse, get
    "fixed" by making the code accommodate it. Phase 2a retired that job, so the
    assertion inverts: there must not be a second backend job at all.

    A non-gating backend job is not forbidden forever. What is forbidden is one that
    reappears without the reasoning in .github/workflows/tests.yml being revisited,
    which is what this failing would mean.
    """
    import io as _io

    workflow = _io.open(".github/workflows/tests.yml", encoding="utf-8").read()

    jobs = _yaml_jobs(workflow)
    backend_jobs = [name for name in jobs if name.startswith("backend-tests")]
    assert backend_jobs == ["backend-tests-postgres"], (
        "Backend CI jobs are %s. A second one needs the trade-off in "
        ".github/workflows/tests.yml revisited, not this test updated." % backend_jobs
    )

    postgres_job = jobs["backend-tests-postgres"]
    assert "continue-on-error" not in postgres_job, (
        "The Postgres job is the gate; it must be able to fail the build."
    )
    assert "pgvector/pgvector:pg" in _io.open(
        ".github/workflows/tests.yml", encoding="utf-8"
    ).read(), "the Postgres service container is gone"


# ---------------------------------------------------------------------------
# Fatal validation (2026-09-02).
#
# Phase 0 logged ConfigError at CRITICAL and booted anyway, with a note that it
# would become fatal once create_app() owned configuration. Phase 1 landed the
# factory, so create_app() now raises. The line being drawn: fatal means
# *invalid* config, never *testing* config -- the five CI variables must keep
# booting every entrypoint (web, worker, flask db, capture_contract).
# ---------------------------------------------------------------------------


def test_create_app_refuses_to_boot_when_a_required_var_is_missing(monkeypatch):
    """A genuinely missing DATABASE_URL must kill boot, naming the variable.

    The pre-promotion behaviour -- log CRITICAL, keep booting -- deferred the
    failure to the first query, where it surfaces as a pool error that says
    nothing about configuration.
    """
    from solverah.factory import create_app

    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ConfigError) as exc:
        create_app()

    assert "DATABASE_URL" in str(exc.value)


def test_create_app_boots_under_exactly_the_ci_environment():
    """The five variables CI sets are sufficient to boot -- nothing else.

    The worker, `flask db`, and Scripts/capture_contract.py all boot the app
    under this environment; if this test fails, so do they, before any of
    their own code runs.
    """
    from unittest import mock

    from solverah.factory import create_app

    # Process-level variables the interpreter and libraries need to function;
    # everything app-shaped is cleared so a developer's .env cannot leak in.
    keep = {
        k: v
        for k, v in os.environ.items()
        if k in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "COMSPEC"}
    }
    ci_env = dict(
        keep,
        APP_ENV="testing",
        DATABASE_URL=os.environ["DATABASE_URL"],
        JWT_SECRET_KEY="test-jwt-secret-not-a-real-one-32-bytes-min",
        JWT_COOKIE_SECURE="false",
        JWT_COOKIE_SAMESITE="Lax",
    )

    with mock.patch.dict(os.environ, ci_env, clear=True):
        app = create_app()

    assert app.extensions["solverah_settings"] is not None
    assert app.extensions["solverah_settings"].is_testing is True


def _yaml_jobs(workflow: str) -> dict:
    """The workflow's jobs, parsed rather than string-split.

    The retired job left a forty-line comment block behind that still contains the
    words "backend-tests-sqlite", and a `.split()` on that string would find it.
    Parsing is what tells a job apart from a note about a job.
    """
    import yaml

    return yaml.safe_load(workflow)["jobs"]
