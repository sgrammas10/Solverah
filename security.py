"""Flask-Limiter rate-limiting configuration.

Applies global default limits (200/day, 50/hour) keyed on the remote IP address.
Individual endpoints can override these limits with the ``@limiter.limit(...)``
decorator provided by the returned ``Limiter`` instance.

CORS pre-flight OPTIONS requests are excluded from rate limiting because they
carry no payload and are initiated by the browser before the real request.
"""

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def init_rate_limiter(app) -> Limiter:
    """Create and attach a Flask-Limiter instance to *app*.

    Default limits are conservative to protect against credential-stuffing and
    scraping; auth endpoints add tighter per-endpoint limits on top of these.

    Args:
        app: The Flask application instance.

    Returns:
        The configured ``Limiter`` object (attach ``@limiter.limit(...)`` to
        individual routes that need stricter or looser bounds).
    """
    import os

    # memory:// counts per-process: with multiple gunicorn workers each worker
    # keeps its own counters and every deploy resets them, so effective limits
    # are N-workers times looser than configured. Set RATELIMIT_STORAGE_URI
    # (e.g. a Render Redis URL) in production for real shared limits.
    storage_uri = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    if storage_uri == "memory://" and os.environ.get("APP_ENV") == "production":
        app.logger.warning(
            "Rate limiting uses in-memory storage in production: limits are "
            "per-worker and reset on deploy. Set RATELIMIT_STORAGE_URI."
        )
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
        storage_uri=storage_uri,
    )

    @limiter.request_filter
    def _skip_preflight():
        """Exempt CORS pre-flight requests from rate counting."""
        return request.method == "OPTIONS"

    return limiter
