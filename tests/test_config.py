"""Tests for solverah.config — environment validation and engine options."""

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
