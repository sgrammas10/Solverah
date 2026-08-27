"""``create_app()`` -- the application factory.

Everything in here used to run at ``app.py`` module scope: the ``Flask()``
construction, ProxyFix, CORS, Talisman, config, ``db.init_app``, the limiter,
the error handlers, and the health probes.  That is P0-4 in
docs/ARCHITECTURE.md, and it cost four things:

  * ``os.environ["DATABASE_URL"]`` raised ``KeyError`` at *import*, so a missing
    variable surfaced as an import traceback rather than a startup error.
  * A test could not build a second app with different configuration.
  * Importing anything from ``app.py`` -- a helper, a constant -- ran the entire
    boot sequence as a side effect.
  * Nothing could be split out of ``app.py``, because a module holding routes
    needed ``app``, and ``app`` only existed inside the module holding routes.

The wiring order below is not arbitrary and is preserved from the original:

  1. ProxyFix wraps ``wsgi_app`` first, so every layer above it -- rate limiting,
     audit logging, the access log -- sees the real client IP rather than the
     edge proxy's.
  2. CORS and Talisman next: they install ``after_request`` hooks, and Talisman's
     ``force_https`` must be able to see requests the health blueprint exempts.
  3. Config before extensions, because ``db.init_app`` reads the engine options
     and the JWT manager reads the cookie policy.
  4. Blueprints last, so ``limiter.exempt()`` and the Talisman per-view options
     can address view functions that exist.

Configuration validation stays non-fatal.  Phase 0 left a note saying it would
become fatal "in Phase 1 when create_app() owns configuration"; that is
deliberately not being done in the same change that moves 38 routes.  Turning a
strict check fatal is a deploy-breaking behaviour change and deserves to land on
its own, where a failure is unambiguously attributable to it.  The problems are
still logged at CRITICAL.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any, Mapping, Optional, Tuple

from flask import Flask
from flask_cors import CORS
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix

from security import init_rate_limiter
from solverah.api.health import create_health_blueprint, database_check
from solverah.api.v1 import register_v1_blueprints
from solverah.config import ConfigError, Settings
from solverah.errors import register_error_handlers
from solverah.extensions import bcrypt, db, jwt, limiter, migrate
from solverah.observability.logging import init_logging, install_request_logging
from solverah.validation import install_request_validation

__all__ = [
    "LEGACY_PREFIX",
    "V1_PREFIX",
    "create_app",
]

#: Canonical prefix.  Every rule in the API is registered here, and it is the
#: only prefix the application serves.
V1_PREFIX = "/api/v1"

#: The unversioned prefix the API served through the Phase 1 cutover.
#:
#: ``register_legacy_aliases`` bound every ``/api/v1/x`` rule to ``/api/x`` as
#: well -- a second URL rule on the *same endpoint*, never a redirect, so that
#: one Flask-Limiter bucket covered both and a preflighted cross-origin POST did
#: not have to survive a 308.  Phase 1b moved the frontend onto the versioned
#: paths and removed the aliases; nothing serves this prefix now.
#:
#: The constant remains because CORS still matches on it -- ``r"/api/*"`` covers
#: ``/api/v1/...`` -- and because ``tests/test_v1_aliasing.py`` asserts the
#: unversioned paths are gone rather than trusting that they are.
LEGACY_PREFIX = "/api"


# ---------------------------------------------------------------------------
# Environment helpers.  Unchanged from app.py, which re-exports them so the
# tests that import them by name keep working.
# ---------------------------------------------------------------------------

def _is_production() -> bool:
    """Return True if any of the standard environment indicators say 'production'.

    Checks FLASK_ENV, APP_ENV, and ENV in that order.  Used to gate HTTPS-only
    cookies, HSTS headers, and Talisman's ``force_https`` flag.
    """
    env_name = (
        os.environ.get("FLASK_ENV")
        or os.environ.get("APP_ENV")
        or os.environ.get("ENV")
        or ""
    )
    return env_name.lower() in {"production", "prod"}


def _parse_bool_env(value, default: bool) -> bool:
    """Coerce an environment-variable string to bool.

    Args:
        value:   Raw string from ``os.environ.get(...)`` (may be None).
        default: Fallback value when *value* is None.

    Returns:
        True for '1', 'true', 'yes', 'y', 'on' (case-insensitive); False
        for everything else; *default* if *value* is None.
    """
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


# Trust the reverse proxy's X-Forwarded-* headers so request.remote_addr holds
# the real client IP instead of the proxy's. Without this, everything behind
# Render's edge shares a single address: rate limiting collapses into one
# global bucket (so the per-IP auth limits stop being per-IP) and the audit log
# records the proxy on every event.
#
# TRUSTED_PROXY_COUNT must equal the number of proxies actually in front of
# the app -- ProxyFix trusts that many entries from the right of
# X-Forwarded-For. Setting it higher than reality lets a client spoof its own
# IP by sending the header itself, which is worse than not trusting it at
# all; 0 disables the middleware (correct for local runs with no proxy).
# Render terminates at exactly one proxy, hence the production default of 1.
# Add one per extra layer if you put e.g. Cloudflare in front.
def _resolve_trusted_proxy_count(raw, production: bool) -> int:
    """Decide how many forwarding hops to trust.

    Args:
        raw:        Raw TRUSTED_PROXY_COUNT value (may be None or blank).
        production: Whether the app is running in production.

    Returns:
        Hop count to trust; 0 means do not read X-Forwarded-* at all.

    Raises:
        RuntimeError: If *raw* is set but is not a non-negative integer. This
            fails the boot rather than guessing, because guessing high is a
            spoofing hole and guessing low breaks rate limiting.
    """
    if raw is None or not raw.strip():
        return 1 if production else 0
    try:
        count = int(raw)
    except ValueError:
        raise RuntimeError(
            "TRUSTED_PROXY_COUNT must be a non-negative integer, got %r" % raw
        )
    if count < 0:
        raise RuntimeError(
            "TRUSTED_PROXY_COUNT must be a non-negative integer, got %r" % raw
        )
    return count


def _apply_proxy_fix(flask_app, count: int) -> bool:
    """Wrap *flask_app* so request.remote_addr reflects the real client.

    Args:
        flask_app: The Flask application to wrap.
        count:     Number of trusted proxy hops; <= 0 applies nothing.

    Returns:
        True if the middleware was applied.
    """
    if count <= 0:
        return False
    # x_host/x_port/x_prefix stay 0 on purpose: trusting a forwarded Host would
    # let an attacker poison absolute URLs we generate (password-reset links
    # being the obvious target).
    flask_app.wsgi_app = ProxyFix(
        flask_app.wsgi_app,
        x_for=count,
        x_proto=count,
        x_host=0,
        x_port=0,
        x_prefix=0,
    )
    return True


def _engine_options(settings: Optional[Settings]) -> dict:
    """Return SQLAlchemy engine options, degrading safely if config is invalid.

    ``pool_pre_ping`` is the one option worth keeping even when the rest of the
    configuration failed validation: without it a Postgres failover leaves the
    pool full of dead connections and every request errors until they age out.
    """
    if settings is not None:
        return settings.engine_options()
    return {"pool_pre_ping": True}


def _load_settings() -> Tuple[Optional[Settings], list]:
    """Validate the environment, returning ``(settings, problems)``.

    ``Settings.from_env()`` reads and validates the whole environment at once
    and raises ``ConfigError`` listing every problem, rather than the older
    pattern of scattered ``os.environ`` reads that fail one variable per
    restart.  Non-fatal -- see the module docstring for why.
    """
    try:
        return Settings.from_env(), []
    except ConfigError as config_error:
        return None, config_error.problems


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

def _configure(app: Flask, settings: Optional[Settings], is_production: bool) -> None:
    """Apply database, request-size, and JWT configuration to *app*."""
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Connection-pool and statement-timeout policy. Left at SQLAlchemy's
    # defaults the app has no liveness check on checkout -- after a Postgres
    # failover the pool hands out dead connections and every request errors
    # until they age out -- and no server-side statement timeout, so one
    # pathological query holds a worker until gunicorn kills it at 120s. See
    # solverah/config.py for the derivation and the per-knob env variables.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = _engine_options(settings)

    # Cap request bodies. Resumes go browser -> R2 directly and never transit
    # Flask, and no endpoint accepts multipart, so nothing legitimate comes
    # close to this; it exists so an unbounded JSON body cannot exhaust worker
    # memory.
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2MB

    # Configuring secret keys for JWTs
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")
    if not app.config["JWT_SECRET_KEY"]:
        raise RuntimeError("JWT_SECRET_KEY is not set")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)  # token expires in 1 hour

    # Tell JWTs to live in cookies instead of headers
    app.config["JWT_TOKEN_LOCATION"] = ["cookies"]

    # In dev (http://localhost) this must be False; in prod over HTTPS, True.
    app.config["JWT_COOKIE_SECURE"] = _parse_bool_env(
        os.environ.get("JWT_COOKIE_SECURE"),
        default=is_production,
    )

    # If frontend and backend are on the same origin, "Lax" is fine; if
    # cross-site + HTTPS, use "None".
    app.config["JWT_COOKIE_SAMESITE"] = os.environ.get(
        "JWT_COOKIE_SAMESITE",
        "None" if is_production else "Lax",
    )

    # CSRF protection on state-changing methods
    app.config["JWT_COOKIE_CSRF_PROTECT"] = True
    app.config["JWT_CSRF_METHODS"] = ["POST", "PUT", "PATCH", "DELETE"]
    app.config["JWT_CSRF_HEADER_NAME"] = "X-CSRF-TOKEN"


def _install_http_middleware(app: Flask, is_production: bool) -> None:
    """Install ProxyFix, CORS, and Talisman, in that order."""
    _apply_proxy_fix(
        app,
        _resolve_trusted_proxy_count(
            os.environ.get("TRUSTED_PROXY_COUNT"), is_production
        ),
    )

    # Flask-CORS 5.x: pass resources as a path pattern and all options at the
    # top level. Nesting options inside the resources dict (4.x style) silently
    # produces no headers in 5.x.
    #
    # The r"/api/*" pattern is matched with re.match, so it covers the
    # /api/v1/... rules this factory adds as well as the legacy /api/... ones.
    # That matters more than it looks: every authenticated write carries an
    # X-CSRF-TOKEN header, which makes it a non-simple request, which means the
    # browser preflights it. A v1 path falling outside this pattern would fail
    # its OPTIONS and the POST would never be sent at all.
    CORS(
        app,
        resources=r"/api/*",
        origins=[
            r"http://localhost:\d+",
            r"http://127\.0\.0\.1:\d+",
            "https://solverah.vercel.app",
            "https://solverah.com",
            "https://www.solverah.com",
            "https://api.solverah.com",
        ],
        supports_credentials=True,
        allow_headers=["Content-Type", "X-CSRF-TOKEN"],
    )

    # Security headers with Talisman for CSP.
    # Explicit per-directive policy rather than default-src alone: script-src
    # and object-src lock down code execution; frame-ancestors blocks
    # clickjacking on API-served pages. The FRONTEND's CSP is separate -- set in
    # vercel.json.
    Talisman(
        app,
        content_security_policy={
            "default-src": ["'self'"],
            "script-src": ["'self'"],
            "style-src": ["'self'", "https://fonts.googleapis.com"],
            "font-src": ["https://fonts.gstatic.com"],
            "img-src": ["'self'", "data:"],
            "object-src": ["'none'"],
            "frame-ancestors": ["'none'"],
            "base-uri": ["'self'"],
        },
        force_https=is_production,
        strict_transport_security=is_production,
        strict_transport_security_max_age=31536000 if is_production else None,
        strict_transport_security_include_subdomains=is_production,
        strict_transport_security_preload=is_production,
    )


def _init_extensions(app: Flask) -> None:
    """Bind the extension singletons from ``solverah.extensions`` to *app*."""
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    jwt.init_app(app)
    init_rate_limiter(app, limiter=limiter)


def _register_platform_blueprints(app: Flask) -> None:
    """Health probes plus their Talisman and rate-limit exemptions."""
    # Liveness and readiness. /healthz checks nothing external on purpose: if it
    # checked the database, one database blip would fail liveness on every
    # replica at once and the orchestrator would restart the whole fleet.
    app.register_blueprint(
        create_health_blueprint(
            checks={"database": database_check(db)},
            release=os.environ.get("RELEASE", "dev"),
        )
    )

    # Probes reach the pod over plain HTTP inside the cluster; without this they
    # get a 301 from Talisman's force_https and the orchestrator reads that as
    # unhealthy.
    for health_endpoint in ("health.healthz", "health.readyz"):
        app.view_functions[health_endpoint].talisman_view_options = {"force_https": False}

    # Probes fire every few seconds and would otherwise consume the shared
    # default budget of 200/day, causing real traffic to be throttled.
    limiter.exempt(app.view_functions["health.healthz"])
    limiter.exempt(app.view_functions["health.readyz"])


def create_app(config: Optional[Mapping[str, Any]] = None) -> Flask:
    """Build, configure, and return the Flask application.

    Args:
        config: Optional config overrides, applied after the environment-derived
            configuration and before extensions are initialised.  Intended for
            tests that need a differently-configured app; production passes
            nothing.

    Returns:
        A fully wired ``Flask`` app.  Every route it serves is declared in
        ``solverah/api/v1/``; the strangler seam that let handlers attach at
        ``app.py`` module scope closed when Phase 1b removed the last of them.
    """
    is_production = _is_production()
    settings, config_problems = _load_settings()

    init_logging(
        level=os.environ.get("LOG_LEVEL", "INFO" if is_production else "DEBUG"),
        fmt=os.environ.get("LOG_FORMAT", "json" if is_production else "console"),
        service="api",
        release=os.environ.get("RELEASE", "dev"),
    )

    if config_problems:
        logging.getLogger("solverah.config").critical(
            "configuration_invalid",
            extra={"event": "configuration_invalid", "problems": config_problems},
        )
    elif settings is not None:
        for warning in settings.warnings:
            logging.getLogger("solverah.config").warning(
                "configuration_warning",
                extra={"event": "configuration_warning", "detail": warning},
            )

    # Named "app" rather than __name__ so the Flask app, its logger, and its
    # static/template roots keep the identity they had when this was
    # ``Flask(__name__)`` inside app.py.  app.logger is used by handlers and by
    # tests that read caplog.
    app = Flask("app")

    _install_http_middleware(app, is_production)
    _configure(app, settings, is_production)
    if config:
        app.config.update(config)
    _init_extensions(app)

    # Assigns every request an X-Request-Id (adopting a safe inbound one so an
    # edge-initiated trace stays joined up), echoes it on the response, and
    # emits one structured access line per request.
    install_request_logging(app)

    # Every failure answers with RFC 9457 problem+json. Previously an unhandled
    # exception returned Werkzeug's HTML 500 page to a client calling
    # res.json(), which surfaced in the UI as "Unexpected response from server"
    # instead of the actual error. Handlers that already return {"error": ...}
    # are untouched.
    register_error_handlers(app)

    # Routes declared with @document(..., enforce=True) get their request body
    # and query string validated before the handler runs. Installed here, after
    # the limiter's own before_request, so a flood of malformed bodies is
    # refused by the limiter rather than parsed one at a time. See
    # solverah/validation.py for why this is a hook and not a decorator.
    install_request_validation(app)

    _register_platform_blueprints(app)
    register_v1_blueprints(app, url_prefix=V1_PREFIX)

    app.extensions["solverah_settings"] = settings
    app.extensions["solverah_is_production"] = is_production
    return app
