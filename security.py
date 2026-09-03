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

Boot-strict, runtime-tolerant
-----------------------------
These are two different questions and S1 answers them opposite ways on purpose.

**At boot, a wrong configuration is fatal.**  ``memory://`` in production, or a
Redis URI with no ``redis`` driver installed, raises :class:`~solverah.config.ConfigError`
rather than logging and carrying on.  Both used to degrade quietly to per-worker
counters, and the 2026-09 audit rated the first the highest-impact finding in
the report.  The operator can fix either in one line, but only if they are told;
a warning in a boot log is not telling.

**At runtime, an unreachable store is not fatal.**  Redis falling over must not
take the site down with it, so the limiter is configured to degrade instead:
``RATELIMIT_IN_MEMORY_FALLBACK_ENABLED`` makes it re-evaluate the same limits
against per-worker memory (a WARNING per transition, and it re-checks and
recovers on its own), and ``RATELIMIT_SWALLOW_ERRORS`` catches anything the
fallback itself cannot serve so the request proceeds unlimited rather than
500ing.  The degraded state is exactly what boot refuses to *start* in -- which
is the point: entering it by accident should be impossible, entering it because
Redis died is survivable and temporary.
"""

import logging
import os
from typing import Optional

from flask import current_app, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from solverah.config import ConfigError

logger = logging.getLogger("solverah.security")

DEFAULT_LIMITS = ["200 per day", "50 per hour"]
MEMORY_STORAGE = "memory://"

#: Fixed key for a limit that is global rather than per-caller. See
#: ``GUEST_INSIGHTS_GLOBAL_LIMIT`` below for the one place this is used and why.
GLOBAL_RATE_LIMIT_KEY = "global"


def global_rate_limit_key() -> str:
    """Key function for a limit shared by every caller.

    Flask-Limiter keys on the remote address by default, which is what makes a
    limit per-caller. Returning a constant makes one bucket for the whole
    deployment -- which is the point when the thing being bounded is spend
    rather than abuse by any individual.
    """
    return GLOBAL_RATE_LIMIT_KEY


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


def _redact(uri: str) -> str:
    """A storage URI safe to put in a log line or an exception message.

    A Redis URI carries its password in the netloc, and both places this string
    can end up -- the boot log and a ``ConfigError`` a supervisor may echo --
    are places a credential must not be.  Everything between ``//`` and the
    last ``@`` goes; the host and database, which are what an operator needs in
    order to act on the message, stay.
    """
    scheme, sep, rest = uri.partition("://")
    if not sep or "@" not in rest:
        return uri
    return "%s://%s%s" % (scheme, "***@", rest.rsplit("@", 1)[1])


# ---------------------------------------------------------------------------
# Runtime tolerance: an unreachable Redis must not become a site outage
# ---------------------------------------------------------------------------
#
# Boot is strict (see the module docstring); the running process is not, and the
# asymmetry is deliberate. A misconfiguration is a mistake somebody can fix in
# one line before any traffic sees it. Redis becoming unreachable at 03:00 is
# not a mistake, it is weather -- and a rate limiter is a *control on* the
# service, not a dependency of it. Answering 500 to every request because the
# thing that counts requests is down converts a degraded control into a total
# outage, which is a strictly worse security outcome than the degraded control.
#
# Two settings, in the order Flask-Limiter tries them:
#
#   * ``IN_MEMORY_FALLBACK_ENABLED`` -- on the first storage error the limiter
#     logs "Rate limit storage unreachable - falling back to in-memory storage"
#     at WARNING and re-evaluates *the same configured limits* against
#     per-worker memory. So the degraded mode still enforces something: N times
#     looser and resettable, which is precisely the posture boot refuses to
#     start in, but far from unlimited. It also polls the real backend and logs
#     "Rate limit storage recovered" at INFO when Redis returns, so recovery
#     needs no deploy.
#
#   * ``SWALLOW_ERRORS`` -- the backstop under that: if even the fallback path
#     raises, the exception is logged and the request is allowed through rather
#     than 500ing. ``RateLimitExceeded`` is re-raised explicitly by the library
#     before this is consulted, so a genuine 429 is still a 429.
#
# Neither has any effect while the store is healthy.
RUNTIME_TOLERANCE = {
    "in_memory_fallback_enabled": True,
    "swallow_errors": True,
}

#: The same two settings by their ``app.config`` names, for the path where the
#: limiter was constructed before the app and cannot take constructor kwargs.
RUNTIME_TOLERANCE_CONFIG = {
    "RATELIMIT_IN_MEMORY_FALLBACK_ENABLED": True,
    "RATELIMIT_SWALLOW_ERRORS": True,
}


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
        detail = (
            "Rate-limit storage is configured for Redis (%s) but the 'redis' "
            "package is not installed. Add redis to requirements.txt." % _redact(uri)
        )
        if is_production:
            # Until S1 this degraded to memory:// with one logger.error, on the
            # reasoning that a missing optional dependency should not take down
            # a running service. That reasoning does not survive contact with
            # what the degradation costs: the operator has *explicitly asked
            # for* a shared store, a packaging regression silently answers with
            # per-worker counters, and nothing after boot ever says so again.
            # Serving with every limit N times looser than configured is not
            # "still serving", it is serving without the controls the config
            # claims. A packaging regression is also caught by the deploy that
            # introduces it, which is the cheapest possible moment to catch it.
            raise ConfigError([detail])
        logger.error(
            "ratelimit_backend_unavailable",
            extra={
                "event": "ratelimit_backend_unavailable",
                "detail": detail + " Falling back to memory:// (per-worker limits).",
            },
        )
        uri = MEMORY_STORAGE

    if uri == MEMORY_STORAGE and is_production:
        # Fatal since S1. ``Settings.from_env`` reports the same problem and
        # normally raises first, so in a full ``create_app()`` boot this branch
        # never fires -- it is here because ``init_rate_limiter`` is callable on
        # its own and takes an explicit ``storage_uri``, and a guard that only
        # holds along one call path is a guard with a hole in it.
        raise ConfigError([
            "Rate-limit storage is memory:// in production: limits would be "
            "per-worker and would reset on every deploy. Set REDIS_URL or "
            "RATELIMIT_STORAGE_URI to a shared store."
        ])

    if limiter is None:
        # The pre-Phase-1 shape: build a limiter of our own rather than
        # attaching the shared singleton. `create_app()` never takes this branch
        # -- it always passes `limiter=` -- which is how a defect survived here
        # unnoticed until S1 put a test on it: `request_filter=` was passed as a
        # constructor keyword, and Flask-Limiter has no such parameter (it is a
        # decorator method), so every call down this path raised TypeError. The
        # filter is registered after construction, which is what the other
        # branch already did.
        fresh = Limiter(
            get_remote_address,
            app=app,
            default_limits=DEFAULT_LIMITS,
            storage_uri=uri,
            **RUNTIME_TOLERANCE,
        )
        fresh.request_filter(_skip_preflight)
        return fresh

    # Flask-Limiter reads these during init_app; setting them on the config
    # rather than the constructor is what lets the limiter be built before the
    # app.
    app.config["RATELIMIT_STORAGE_URI"] = uri
    for key, value in RUNTIME_TOLERANCE_CONFIG.items():
        app.config[key] = value

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


# ---------------------------------------------------------------------------
# Guest quiz-preview insights (Phase 1b -- the outstanding 1a follow-up)
# ---------------------------------------------------------------------------
#
# The endpoint had ``@limiter.limit("1 per day")``, keyed on the remote IP, and
# a docstring saying it existed to cap OpenAI spend.  Both halves of that are
# worth taking seriously and they pull in different directions.
#
# **Why the old limit had to go.**  ``1 per day per IP`` is not one preview per
# person.  Behind corporate NAT it is one preview per *office*; behind mobile
# CGNAT it is one per *carrier segment*, which can be tens of thousands of
# subscribers.  The second person to try gets a 429 having done nothing, on the
# unauthenticated top of the pre-launch funnel, with no account and no way to
# tell a limit from a fault.  It does not read as rate limiting.  It reads as a
# broken quiz, and the visitor leaves.
#
# **Why it cannot simply be loosened.**  Every call is a paid OpenAI request
# with no account behind it, so a per-IP limit alone bounds nothing that matters:
# spend scales with the number of distinct IPs, which is the one quantity an
# abuser controls freely.  Loosening per-IP without a second control converts a
# usability bug into an unbounded bill.
#
# **The shape that solves both.**  Two limits doing two different jobs:
#
#   * a *per-IP* limit sized for a human, generous enough that a shared address
#     is not a single-user address; and
#   * a *global* ceiling sized to a spend budget, which is the control that
#     actually caps the bill.
#
# The trade is explicit and worth stating plainly: a global ceiling means a
# determined abuser can exhaust the day's budget and leave real visitors seeing
# 429s.  That is a worse failure than throttling them individually -- and it is
# still the right trade here, because the alternative failure is an unbounded
# invoice, and because the per-IP limit means exhausting the global budget takes
# many distinct addresses rather than one.
#
# **A caveat that is not optional.**  A global ceiling is only a ceiling if the
# counter is shared.  On ``memory://`` it is per-worker, so N workers means N
# times the budget and a deploy resets it -- that is P0-5, and it makes this
# control decorative in exactly the deployment where it matters.  Set
# ``REDIS_URL`` before relying on the number below.
#
# The numbers are policy, not architecture. They are named here so tuning them
# is a one-line change with the reasoning attached, rather than a magic number
# in a decorator.

#: Per-IP allowance. Sized for a human filling in a short quiz, with enough
#: headroom that a shared NAT gateway is not a one-visitor address.
GUEST_INSIGHTS_PER_IP_LIMIT = "5 per hour;20 per day"

#: Global daily ceiling across every caller -- the control that bounds spend.
#: At current model pricing a short insight is well under a cent, so this is a
#: low-single-digit dollars per day worst case. Requires shared storage; see
#: the caveat above.
GUEST_INSIGHTS_GLOBAL_LIMIT = "500 per day"


# ---------------------------------------------------------------------------
# The anonymous assessment teaser (`wpll`) -- S1
# ---------------------------------------------------------------------------
#
# `POST /assessments/wpll/scoring-jobs` is the application's second
# unauthenticated door onto a paid provider. Every accepted call commits a
# `scoring_jobs` row and, in the worker, makes an OpenAI request with no account
# behind it. Until S1 it carried no limit of its own at all: it rode
# DEFAULT_LIMITS, per IP, and the 2026-09 audit probed the consequence -- 40
# back-to-back enqueues from one address all returned 202, because 200-per-day
# is not a rate and 50-per-hour is not a burst control.
#
# The endpoint that already had this right is `POST
# /intake/quiz-preview/insights`, six lines further up this file: a per-IP limit
# sized for a human plus a global-key bucket sized to a spend budget, with the
# reasoning under GUEST_INSIGHTS_PER_IP_LIMIT. That reasoning transfers whole --
# spend scales with the number of distinct IPs, so a per-IP limit alone bounds
# the wrong quantity -- and the shape below is deliberately the same shape, not
# a second invention.
#
# Two things are *not* copied, both on purpose:
#
#   * The global bucket gets its own scope rather than joining
#     `intake:quiz-preview-insights:global`. They are separate instruments with
#     separate prompts and separate budgets, and one shared bucket would mean
#     abuse of either one silently closes the other -- two funnel entrances
#     failing together for a reason neither log would explain.
#
#   * The per-IP limit keeps a per-minute term, which guest-insights does not
#     need. wpll's enqueue returns 202 immediately, so a client can pipeline it
#     in a way a synchronous endpoint's own latency already throttles.
#
# The per-IP limit REPLACES wpll's bare DEFAULT_LIMITS rather than stacking on
# top of it: two per-IP buckets on one door is the "conflicting buckets" shape,
# where the effective limit is whichever is tighter and neither string tells you
# which. The day term below is the one that used to come from the defaults, kept
# explicitly because `shared_limit` defaults to `override_defaults=True`.

#: Per-IP allowance for the anonymous teaser. The burst term matches every other
#: instrument's submit; the hour and day terms are the human envelope -- nobody
#: fills in a five-question teaser twenty times, and a shared NAT gateway still
#: gets room for a classroom.
WPLL_ANON_PER_IP_LIMIT = "5 per minute;20 per hour;50 per day"

#: Global daily ceiling across every caller -- the control that actually bounds
#: spend, since the per-IP one bounds only what a single address can do. Sized
#: like GUEST_INSIGHTS_GLOBAL_LIMIT and for the same money: a gpt-4o-mini teaser
#: is well under a cent, so this is low-single-digit dollars per day worst case.
#:
#: The trade is the same one stated above for guest insights and worth restating:
#: a global ceiling means a determined abuser can exhaust the day's budget and
#: leave real visitors seeing 429s. That is still the better failure than an
#: unbounded invoice, and reaching it takes many distinct addresses rather than
#: one, because of the per-IP limit above.
#:
#: Like every ceiling here it is only a ceiling if the counter is shared -- which
#: is now enforced at boot rather than hoped for; see the module docstring.
WPLL_ANON_GLOBAL_LIMIT = "500 per day"


# ---------------------------------------------------------------------------
# The refresh endpoint (`POST /auth/refresh`) -- S3
# ---------------------------------------------------------------------------
#
# Unauthenticated by cookie: it is reached precisely when the access token has
# expired, so nothing above it has decided who the caller is. It therefore needs
# a limit of its own, and sizing it wrong breaks the product in one of two
# directions.
#
# **What this limit is NOT for.** It is not brute-force protection. The token is
# 256 bits of CSPRNG output (`domain.auth.REFRESH_TOKEN_BYTES`), so guessing one
# is not a strategy at any rate a limiter could permit, and a stolen token needs
# exactly one call. What the limit bounds is *work*: every accepted refresh
# writes two rows and reads an index, and an unbounded loop against this door is
# a database write amplifier pointed at the auth path.
#
# **Why it is generous, and why that is not a weakening.** With a fifteen-minute
# access token a legitimate browser refreshes four times an hour, and this limit
# is keyed on the IP -- so behind a corporate NAT gateway the bucket is shared by
# the whole office and behind mobile CGNAT by a carrier segment. `1 per day per
# IP` on the guest quiz endpoint is the same mistake already made and already
# removed in this file (see GUEST_INSIGHTS_PER_IP_LIMIT): a number sized for one
# person becomes a number sized for a building, and the second person to arrive
# is signed out for reasons no log explains. Thirty per minute is roughly thirty
# distinct browsers hitting a refresh in the same minute, which is a plausible
# 9 a.m. and is nowhere near a loop.
#
# **No day term, deliberately**, which is the one place this shape differs from
# WPLL_ANON_PER_IP_LIMIT above. That endpoint spends money per call and a daily
# ceiling is the budget; this one spends two INSERTs, and four refreshes per
# browser per hour times an office is a legitimately large daily number. A day
# term sized to survive that would bound nothing a minute term had not already
# bounded, and a day term sized to look tight would sign an office out every
# afternoon.
#
# `shared_limit` with an explicit scope, like every other limit in this
# application, and `override_defaults=True` (its default) is intended here
# rather than incidental: DEFAULT_LIMITS' `200 per day` is exactly the per-IP
# day term the paragraph above rules out.
REFRESH_PER_IP_LIMIT = "30 per minute;300 per hour"
