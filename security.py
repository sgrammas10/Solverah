"""Flask-Limiter rate-limiting configuration.

Applies global default limits (200/day, 50/hour) keyed on the remote IP address.
Individual endpoints can override these limits with the ``@limiter.limit(...)``
decorator provided by the returned ``Limiter`` instance.

CORS pre-flight OPTIONS requests are excluded from rate limiting because they
carry no payload and are initiated by the browser before the real request.

Storage backend
---------------
``memory://`` counts **per process**.  With N gunicorn workers each worker keeps
its own counters and every deploy resets them, so the effective limit is N times
looser than the configured one and a redeploy clears an attacker's budget.  That
makes the auth limits below decorative rather than protective in production.

The backend is resolved from ``RATELIMIT_STORAGE_URI`` if set, else ``REDIS_URL``
(the same Redis the rest of the platform uses), else ``memory://``.  Reading
``REDIS_URL`` as a fallback means setting one variable configures both the cache
and the limiter, instead of the two silently disagreeing.
"""

import logging
import os
from typing import Optional

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger("solverah.security")

DEFAULT_LIMITS = ["200 per day", "50 per hour"]
MEMORY_STORAGE = "memory://"


def resolve_storage_uri(env=None) -> str:
    """Return the rate-limit storage URI implied by the environment.

    Precedence: ``RATELIMIT_STORAGE_URI`` (explicit) > ``REDIS_URL`` (shared
    platform Redis) > ``memory://`` (per-worker, development only).

    Args:
        env: Mapping to read from; defaults to ``os.environ``.  Injectable so
            tests do not mutate the process environment.
    """
    env = os.environ if env is None else env
    explicit = (env.get("RATELIMIT_STORAGE_URI") or "").strip()
    if explicit:
        return explicit
    redis_url = (env.get("REDIS_URL") or "").strip()
    if redis_url:
        return redis_url
    return MEMORY_STORAGE


def _redis_driver_available() -> bool:
    """Return True if the ``redis`` package can be imported."""
    try:
        import redis  # noqa: F401
    except ImportError:
        return False
    return True


def init_rate_limiter(app, storage_uri: Optional[str] = None) -> Limiter:
    """Create and attach a Flask-Limiter instance to *app*.

    Default limits are conservative to protect against credential-stuffing and
    scraping; auth endpoints add tighter per-endpoint limits on top of these.

    Args:
        app: The Flask application instance.
        storage_uri: Explicit backend URI.  Resolved from the environment when
            omitted.

    Returns:
        The configured ``Limiter`` (attach ``@limiter.limit(...)`` to individual
        routes needing stricter or looser bounds).
    """
    uri = storage_uri or resolve_storage_uri()
    is_production = (os.environ.get("APP_ENV") or "").strip().lower() in {"production", "prod"}

    if uri.startswith("redis") and not _redis_driver_available():
        # Failing the boot here would take down a running service over a missing
        # optional dependency. Degrading to memory:// keeps it serving, and the
        # error below says exactly what to install.
        logger.error(
            "ratelimit_backend_unavailable",
            extra={
                "event": "ratelimit_backend_unavailable",
                "detail": (
                    "Rate-limit storage is configured for Redis but the 'redis' "
                    "package is not installed; falling back to memory:// "
                    "(per-worker limits). Add redis to requirements.txt."
                ),
            },
        )
        uri = MEMORY_STORAGE

    if uri == MEMORY_STORAGE and is_production:
        logger.warning(
            "ratelimit_storage_is_in_memory",
            extra={
                "event": "ratelimit_storage_is_in_memory",
                "detail": (
                    "Rate limiting uses in-memory storage in production: limits "
                    "are per-worker and reset on deploy. Set REDIS_URL or "
                    "RATELIMIT_STORAGE_URI."
                ),
            },
        )

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=DEFAULT_LIMITS,
        storage_uri=uri,
    )

    @limiter.request_filter
    def _skip_preflight():
        """Exempt CORS pre-flight requests from rate counting."""
        return request.method == "OPTIONS"

    return limiter
