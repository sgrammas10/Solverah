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

from flask import current_app, request
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


def init_rate_limiter(
    app,
    storage_uri: Optional[str] = None,
    limiter: Optional[Limiter] = None,
) -> Limiter:
    """Resolve the backend and attach a Flask-Limiter instance to *app*.

    Default limits are conservative to protect against credential-stuffing and
    scraping; auth endpoints add tighter per-endpoint limits on top of these.

    Args:
        app: The Flask application instance.
        storage_uri: Explicit backend URI.  Resolved from the environment when
            omitted.
        limiter: An existing, unbound ``Limiter`` to attach.  ``create_app()``
            passes the shared singleton from ``solverah.extensions`` so that
            blueprint modules can decorate with ``@limiter.limit(...)`` at
            import time, before any app exists.  When omitted a fresh limiter is
            constructed, which is the pre-Phase-1 behaviour.

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

    if limiter is None:
        return Limiter(
            get_remote_address,
            app=app,
            default_limits=DEFAULT_LIMITS,
            storage_uri=uri,
            request_filter=_skip_preflight,
        )

    # Flask-Limiter reads this during init_app; setting it on the config rather
    # than the constructor is what lets the limiter be built before the app.
    app.config["RATELIMIT_STORAGE_URI"] = uri

    # The filter is registered on the limiter, not the app, so re-registering it
    # on a second create_app() call would stack duplicates that all answer the
    # same question.
    if not getattr(limiter, "_solverah_filters_installed", False):
        limiter.request_filter(_skip_preflight)
        limiter.request_filter(_skip_when_testing)
        limiter._solverah_filters_installed = True

    limiter.init_app(app)
    return limiter


def _skip_preflight() -> bool:
    """Exempt CORS pre-flight requests from rate counting.

    They carry no payload, the browser issues them unprompted before the real
    request, and counting them would halve every configured limit for any
    cross-site caller.
    """
    return request.method == "OPTIONS"


def _skip_when_testing() -> bool:
    """Exempt requests made by the test client from rate counting.

    Read this together with the Phase 1 note below, because it looks more
    alarming than it is.

    Until Phase 1, every ``@limiter.limit(...)`` in ``app.py`` was written
    ABOVE its ``@app.route(...)``::

        @limiter.limit("5 per minute")
        @app.route("/api/login", methods=["POST"])
        def login(): ...

    Decorators apply bottom-up, and ``Flask.route`` registers the function it is
    handed and returns it unchanged.  So Flask registered the *undecorated*
    ``login``, ``limiter.limit`` wrapped a function nothing would ever call, and
    the limit never ran.  Every per-endpoint limit in the application -- the
    5/minute on login and register, the 3/minute on password reset, the 1/day on
    guest quiz insights -- was inert.  Only the blanket ``default_limits``
    applied.

    Moving the handlers into blueprints put the decorators in the conventional
    order, so those limits now do what they always said they did.  That is a
    fix, not a regression, but it means a test suite that fires 40 logins in a
    second suddenly gets 429s -- the suite was written against an application
    where the limits did nothing.

    Exempting the test client keeps the suite measuring what it was written to
    measure.  It is gated on ``app.config["TESTING"]``, which is set by the test
    fixture and by nothing else; a production app with TESTING on has larger
    problems than its rate limits.  tests/test_rate_limits.py turns the flag off
    and asserts the limits actually fire, so the control is covered rather than
    merely skipped.
    """
    return bool(current_app.config.get("TESTING"))
