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
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
    )

    @limiter.request_filter
    def _skip_preflight():
        """Exempt CORS pre-flight requests from rate counting."""
        return request.method == "OPTIONS"

    return limiter
