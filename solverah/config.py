"""Typed, validated application settings.

Today ``app.py`` reads ``os.environ`` at 30-odd call sites, coerces booleans by
hand, and crashes with a bare ``KeyError`` at import time when ``DATABASE_URL``
is absent.  That fails late, fails one variable at a time, and gives an operator
no way to tell a misconfigured deploy from a code bug.

``Settings.from_env()`` replaces that: it reads the environment once, coerces and
validates every value, and raises a single :class:`ConfigError` listing *every*
problem it found.  A bad deploy therefore surfaces the complete fix in one log
line instead of one variable per restart loop.

Usage::

    from solverah.config import Settings

    settings = Settings.from_env()          # raises ConfigError on bad input
    app.config["SQLALCHEMY_DATABASE_URI"] = settings.database_url

Nothing here imports Flask.  Settings are readable from workers, scripts, and
tests without constructing an application.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence

__all__ = ["ConfigError", "Settings", "is_truthy"]


class ConfigError(RuntimeError):
    """Raised when the environment cannot produce a valid :class:`Settings`.

    Carries every validation failure at once so an operator sees the full set of
    problems rather than discovering them one restart at a time.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems: List[str] = list(problems)
        detail = "\n".join("  - " + p for p in self.problems)
        super().__init__(
            "Invalid configuration (%d problem%s):\n%s"
            % (len(self.problems), "" if len(self.problems) == 1 else "s", detail)
        )


_TRUE_VALUES = frozenset({"1", "true", "yes", "y", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "n", "off", ""})

PRODUCTION_NAMES = frozenset({"production", "prod"})
TESTING_NAMES = frozenset({"testing", "test"})


def is_truthy(raw: Optional[str]) -> bool:
    """Whether a raw environment value reads as true.

    The permissive counterpart to :func:`_read_bool`, for flags where an
    unrecognised value should simply mean "off" rather than being recorded as a
    configuration problem.  Use it only for switches that cannot cause harm when
    they fail closed -- ``SOLVERAH_IGNORE_DOTENV`` is the intended case, where
    "off" means the normal developer behaviour.

    Anything that gates security (``JWT_COOKIE_SECURE``) must keep using
    :func:`_read_bool`, which rejects ``TRU`` rather than silently reading it as
    False.
    """
    return (raw or "").strip().lower() in _TRUE_VALUES


def _read_bool(env: Mapping[str, str], key: str, default: bool, problems: List[str]) -> bool:
    """Coerce ``env[key]`` to bool, recording a problem for unrecognised values.

    Unlike a permissive ``value in {"1","true"}`` check, an unrecognised value is
    an error rather than a silent False: ``JWT_COOKIE_SECURE=TRU`` disabling
    secure cookies in production is exactly the failure this prevents.
    """
    raw = env.get(key)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    problems.append(
        "%s must be a boolean (one of 1/true/yes/on, 0/false/no/off), got %r" % (key, raw)
    )
    return default


def _read_int(
    env: Mapping[str, str],
    key: str,
    default: int,
    problems: List[str],
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """Coerce ``env[key]`` to int and range-check it, recording problems."""
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        problems.append("%s must be an integer, got %r" % (key, raw))
        return default
    if minimum is not None and value < minimum:
        problems.append("%s must be >= %d, got %d" % (key, minimum, value))
        return default
    if maximum is not None and value > maximum:
        problems.append("%s must be <= %d, got %d" % (key, maximum, value))
        return default
    return value


@dataclass(frozen=True)
class Settings:
    """Fully resolved application configuration.

    Frozen so a value cannot drift after boot: configuration read at request time
    is configuration that can differ between two workers in the same deploy.
    """

    # -- Environment ---------------------------------------------------------
    env: str
    is_production: bool
    is_testing: bool
    release: str

    # -- Data ----------------------------------------------------------------
    database_url: str
    db_pool_size: int
    db_max_overflow: int
    db_pool_recycle_seconds: int
    db_pool_timeout_seconds: int
    db_statement_timeout_ms: int

    # -- Auth ----------------------------------------------------------------
    jwt_secret_key: str
    jwt_access_token_minutes: int
    jwt_cookie_secure: bool
    jwt_cookie_samesite: str

    # -- Edge ----------------------------------------------------------------
    trusted_proxy_count: int
    cors_origins: List[str]

    # -- Shared state --------------------------------------------------------
    redis_url: Optional[str]
    ratelimit_storage_uri: str

    # -- Async ---------------------------------------------------------------
    celery_broker_url: Optional[str]
    celery_result_backend: Optional[str]
    celery_task_always_eager: bool
    cache_default_ttl_seconds: int

    # -- Observability -------------------------------------------------------
    log_level: str
    log_format: str  # "json" | "console"

    # -- Optional providers --------------------------------------------------
    # Absent providers degrade the feature that needs them; they never block boot.
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    onet_api_key: Optional[str] = None
    resend_api_key: Optional[str] = None
    s3_endpoint_url: Optional[str] = None
    s3_bucket_name: Optional[str] = None

    # -- Derived -------------------------------------------------------------
    warnings: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------ build
    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        """Build settings from ``env`` (defaults to ``os.environ``).

        Args:
            env: Mapping to read from.  Injectable so tests never mutate the
                real process environment.

        Returns:
            A validated, frozen ``Settings``.

        Raises:
            ConfigError: If any value is missing or malformed.  Every problem is
                reported together.
        """
        env = os.environ if env is None else env
        problems: List[str] = []
        warnings: List[str] = []

        env_name = (
            env.get("APP_ENV") or env.get("FLASK_ENV") or env.get("ENV") or "development"
        ).strip().lower()
        is_production = env_name in PRODUCTION_NAMES
        is_testing = env_name in TESTING_NAMES

        database_url = (env.get("DATABASE_URL") or "").strip()
        if not database_url:
            problems.append("DATABASE_URL is required")
        elif is_production and database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must not be SQLite in production")

        jwt_secret_key = (env.get("JWT_SECRET_KEY") or "").strip()
        if not jwt_secret_key:
            problems.append("JWT_SECRET_KEY is required")
        elif is_production and len(jwt_secret_key) < 32:
            problems.append(
                "JWT_SECRET_KEY must be at least 32 characters in production "
                "(got %d)" % len(jwt_secret_key)
            )

        jwt_cookie_secure = _read_bool(env, "JWT_COOKIE_SECURE", is_production, problems)
        if is_production and not jwt_cookie_secure:
            problems.append("JWT_COOKIE_SECURE cannot be false in production")

        samesite = (env.get("JWT_COOKIE_SAMESITE") or ("None" if is_production else "Lax")).strip()
        if samesite not in {"Strict", "Lax", "None"}:
            problems.append(
                "JWT_COOKIE_SAMESITE must be Strict, Lax, or None, got %r" % samesite
            )
        elif samesite == "None" and not jwt_cookie_secure:
            # Browsers reject SameSite=None without Secure; the cookie is dropped
            # silently and every authenticated request fails with no server-side error.
            problems.append("JWT_COOKIE_SAMESITE=None requires JWT_COOKIE_SECURE=true")

        trusted_proxy_count = _read_int(
            env, "TRUSTED_PROXY_COUNT", 1 if is_production else 0, problems, minimum=0, maximum=10
        )

        redis_url = (env.get("REDIS_URL") or "").strip() or None
        ratelimit_storage_uri = (
            (env.get("RATELIMIT_STORAGE_URI") or "").strip() or redis_url or "memory://"
        )
        if is_production and ratelimit_storage_uri == "memory://":
            # Per-worker counters mean the configured limit is N-workers times
            # looser and resets on every deploy.  Loud, but not fatal.
            warnings.append(
                "RATELIMIT_STORAGE_URI is memory://: rate limits are per-worker and "
                "reset on deploy. Set REDIS_URL or RATELIMIT_STORAGE_URI."
            )

        # Celery rides the same Redis as the rate limiter and the cache, for the
        # same reason ``ratelimit_storage_uri`` falls back to ``REDIS_URL``: one
        # variable configures the platform's shared state instead of three that
        # can disagree.  ``CELERY_BROKER_URL`` overrides it for the case where the
        # queue genuinely belongs on its own instance.
        celery_broker_url = (env.get("CELERY_BROKER_URL") or "").strip() or redis_url
        celery_result_backend = (
            (env.get("CELERY_RESULT_BACKEND") or "").strip() or celery_broker_url
        )

        # Eager means "run the task inline in the caller, right now".  Two cases
        # need it and both are about a broker that is not there:
        #
        #   * Testing.  CI sets five environment variables and runs no Redis
        #     service container, so `.delay()` would raise on connect in every
        #     test that reaches a queued path.  Eager keeps the suite honest about
        #     *ordering* -- what runs, in what order, with what arguments -- while
        #     being explicitly no evidence about durability.  The outbox invariant
        #     is tested against the table directly for that reason.
        #   * A developer running the API with no Redis at all.  Degrading to
        #     inline execution keeps `flask run` working exactly as it did before
        #     this phase, rather than turning every registration into a 500.
        #
        # Production always has a broker, and setting this there would silently
        # put every LLM call and every email back on the request path -- so it is
        # a configuration problem rather than a mode, and it is warned about below.
        celery_eager_default = is_testing or not celery_broker_url
        celery_task_always_eager = _read_bool(
            env, "CELERY_TASK_ALWAYS_EAGER", celery_eager_default, problems
        )
        if is_production and celery_task_always_eager:
            warnings.append(
                "CELERY_TASK_ALWAYS_EAGER is on (or no broker is configured): queued "
                "work runs inline in the web worker, which is the request-path "
                "blocking Phase 3 exists to remove. Set CELERY_BROKER_URL or REDIS_URL."
            )

        # Backstop only. Every cached read is invalidated by key on the write that
        # changes it, so the TTL is what bounds staleness if an invalidation is
        # ever missed -- not the mechanism the cache relies on.
        cache_default_ttl_seconds = _read_int(
            env, "CACHE_DEFAULT_TTL_SECONDS", 300, problems, minimum=1, maximum=86400
        )

        log_format = (env.get("LOG_FORMAT") or ("json" if is_production else "console")).strip().lower()
        if log_format not in {"json", "console"}:
            problems.append("LOG_FORMAT must be 'json' or 'console', got %r" % log_format)

        log_level = (env.get("LOG_LEVEL") or ("INFO" if is_production else "DEBUG")).strip().upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            problems.append("LOG_LEVEL must be a standard logging level, got %r" % log_level)

        cors_origins = [
            o.strip() for o in (env.get("CORS_ORIGINS") or "").split(",") if o.strip()
        ]

        # Numeric tuning knobs are read before the raise so a bad DB_POOL_SIZE is
        # reported in the same ConfigError as a missing DATABASE_URL, rather than
        # on the next restart.
        db_pool_size = _read_int(env, "DB_POOL_SIZE", 10, problems, minimum=1, maximum=200)
        db_max_overflow = _read_int(env, "DB_MAX_OVERFLOW", 5, problems, minimum=0, maximum=200)
        db_pool_recycle = _read_int(env, "DB_POOL_RECYCLE_SECONDS", 1800, problems, minimum=30)
        db_pool_timeout = _read_int(
            env, "DB_POOL_TIMEOUT_SECONDS", 10, problems, minimum=1, maximum=120
        )
        db_statement_timeout = _read_int(
            env, "DB_STATEMENT_TIMEOUT_MS", 15000, problems, minimum=100
        )
        jwt_access_minutes = _read_int(
            env, "JWT_ACCESS_TOKEN_MINUTES", 60, problems, minimum=1, maximum=1440
        )

        if problems:
            raise ConfigError(problems)

        return cls(
            env=env_name,
            is_production=is_production,
            is_testing=is_testing,
            release=(env.get("RELEASE") or "dev").strip(),
            database_url=database_url,
            db_pool_size=db_pool_size,
            db_max_overflow=db_max_overflow,
            db_pool_recycle_seconds=db_pool_recycle,
            db_pool_timeout_seconds=db_pool_timeout,
            db_statement_timeout_ms=db_statement_timeout,
            jwt_secret_key=jwt_secret_key,
            jwt_access_token_minutes=jwt_access_minutes,
            jwt_cookie_secure=jwt_cookie_secure,
            jwt_cookie_samesite=samesite,
            trusted_proxy_count=trusted_proxy_count,
            cors_origins=cors_origins,
            redis_url=redis_url,
            ratelimit_storage_uri=ratelimit_storage_uri,
            celery_broker_url=celery_broker_url,
            celery_result_backend=celery_result_backend,
            celery_task_always_eager=celery_task_always_eager,
            cache_default_ttl_seconds=cache_default_ttl_seconds,
            log_level=log_level,
            log_format=log_format,
            openai_api_key=(env.get("OPENAI_API_KEY") or "").strip() or None,
            groq_api_key=(env.get("GROQ_API_KEY") or "").strip() or None,
            onet_api_key=(env.get("ONET_API_KEY") or "").strip() or None,
            resend_api_key=(env.get("RESEND_API_KEY") or "").strip() or None,
            s3_endpoint_url=(env.get("S3_ENDPOINT_URL") or "").strip() or None,
            s3_bucket_name=(env.get("S3_BUCKET_NAME") or "").strip() or None,
            warnings=warnings,
        )

    # ------------------------------------------------------------- SQLAlchemy
    def engine_options(self) -> dict:
        """Return ``SQLALCHEMY_ENGINE_OPTIONS`` for this environment.

        The current app ships SQLAlchemy defaults, which means no liveness check
        on checkout (a Postgres failover hands the app a pool of dead
        connections) and no statement timeout (one pathological query occupies a
        worker until gunicorn kills it).

        SQLite ignores pool sizing and does not support ``statement_timeout``, so
        those options are omitted for it rather than raising at connect time.
        """
        if self.database_url.startswith("sqlite"):
            return {"pool_pre_ping": True}

        return {
            "pool_pre_ping": True,
            "pool_size": self.db_pool_size,
            "max_overflow": self.db_max_overflow,
            "pool_recycle": self.db_pool_recycle_seconds,
            "pool_timeout": self.db_pool_timeout_seconds,
            "connect_args": {
                # Server-side ceiling on any single statement.  Belt to the
                # pool's braces: a runaway query is cancelled by Postgres rather
                # than holding a connection until the worker is killed.
                "options": "-c statement_timeout=%d" % self.db_statement_timeout_ms,
            },
        }

    def redacted(self) -> dict:
        """Return a log-safe view: presence of secrets, never their values."""
        return {
            "env": self.env,
            "release": self.release,
            "database": _redact_dsn(self.database_url),
            "db_pool_size": self.db_pool_size,
            "jwt_cookie_secure": self.jwt_cookie_secure,
            "jwt_cookie_samesite": self.jwt_cookie_samesite,
            "trusted_proxy_count": self.trusted_proxy_count,
            "ratelimit_storage": "redis" if self.ratelimit_storage_uri != "memory://" else "memory",
            "celery_broker": "redis" if self.celery_broker_url else "none",
            "celery_eager": self.celery_task_always_eager,
            "cache": "redis" if self.redis_url else "disabled",
            "log_level": self.log_level,
            "log_format": self.log_format,
            "providers": {
                "openai": self.openai_api_key is not None,
                "groq": self.groq_api_key is not None,
                "onet": self.onet_api_key is not None,
                "resend": self.resend_api_key is not None,
                "s3": self.s3_bucket_name is not None,
            },
        }


def _redact_dsn(dsn: str) -> str:
    """Strip credentials from a database URL so it is safe to log."""
    if "://" not in dsn:
        return "***"
    scheme, _, rest = dsn.partition("://")
    if "@" in rest:
        rest = rest.rpartition("@")[2]
    return "%s://%s" % (scheme, rest)
