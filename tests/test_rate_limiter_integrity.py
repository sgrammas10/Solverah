"""Boot-strict, runtime-tolerant: the rate limiter's two halves of one design.

**The findings (2026-09 audit, 9.1 HIGH conditional and 9.2 MED conditional).**
Two different ways to end up serving production traffic on per-worker counters,
both of them quiet:

  * `memory://` in production emitted a `logger.warning` and carried on (9.1).
  * A Redis URI with the `redis` driver missing emitted a `logger.error` and
    silently served on `memory://` anyway (9.2).

What that costs is not "slightly looser limits". `memory://` counts per process,
so with N gunicorn workers every limit is N times looser than it reads and every
deploy hands an attacker a fresh budget. The 5/minute on login becomes 5N. The
per-IP OTP-verification throttle -- which is the *only* bound on guessing a
6-digit code that `/auth/password/reset` exchanges for a session -- resets on
each release. And the global spend ceilings on the two anonymous LLM endpoints
stop being ceilings entirely, because a bucket each worker keeps a private copy
of does not bound anything global. `security.py`'s own module docstring called
the result "decorative rather than protective" and was right.

S1 makes both fatal. The instrument matters as much as the verdict: a warning is
one line in a boot log, predicting a failure that is otherwise invisible;
refusing to start is loud, immediate, and fixed by setting one variable.

**And the other half, which is not optional.** Fatal-at-boot only works if it
does not also mean fatal-at-3am. Redis becoming unreachable while the service
runs is weather, not misconfiguration, and a rate limiter is a *control on* the
service rather than a dependency of it -- 500ing every request because the thing
that counts requests is down turns a degraded control into a total outage, which
is a strictly worse security outcome. So the running limiter degrades instead:
in-memory fallback with a WARNING, and `swallow_errors` beneath that. The state
it degrades into is exactly the state boot refuses to start in, which is the
point -- entering it by accident is impossible, entering it because Redis died
is survivable and self-healing.

⚠ These tests encode a DEPLOY DEPENDENCY. Production has no Redis today, so the
next deploy fails at boot until `REDIS_URL` is set. That ordering is the fix,
not a side effect; see the round report.
"""

import logging

import pytest

from security import (
    MEMORY_STORAGE,
    RUNTIME_TOLERANCE_CONFIG,
    init_rate_limiter,
    resolve_storage_uri,
)
from solverah.config import ConfigError

REDIS_URI = "redis://cache:6379/0"


@pytest.fixture()
def production(monkeypatch):
    """`init_rate_limiter` reads APP_ENV directly, so this is the whole switch."""
    monkeypatch.setenv("APP_ENV", "production")


@pytest.fixture()
def development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")


def _bare_app(name="ratelimit-integrity"):
    """A Flask app with nothing on it but config.

    Deliberately not `create_app()`: these tests are about `init_rate_limiter`
    in isolation, and booting the real factory would drag in a database, a
    Celery config and a settings validation that raises for its own reasons.
    """
    from flask import Flask

    app = Flask(name)
    app.config["TESTING"] = False
    return app


# ── Boot is strict ──────────────────────────────────────────────────────────

def test_memory_storage_in_production_refuses_to_boot(production):
    """9.1. Fails against a build that only logs a warning."""
    with pytest.raises(ConfigError) as exc:
        init_rate_limiter(_bare_app(), storage_uri=MEMORY_STORAGE)

    assert any("memory://" in p for p in exc.value.problems)


def test_memory_storage_outside_production_is_fine(development):
    """One process, no deploys -- memory:// is what dev is *for*."""
    limiter = init_rate_limiter(_bare_app(), storage_uri=MEMORY_STORAGE)

    assert limiter is not None


def test_a_redis_uri_with_no_driver_refuses_to_boot_in_production(production, monkeypatch):
    """9.2, and the harder half to argue.

    The old behaviour degraded on the reasoning that a missing optional
    dependency should not take down a running service. But the operator has
    *explicitly asked for* a shared store here; answering a packaging
    regression with per-worker counters serves without the controls the config
    claims, and never says so again after that one log line. A packaging
    regression is also caught by the deploy that introduces it, which is the
    cheapest possible moment to catch it.
    """
    monkeypatch.setattr("security._redis_driver_available", lambda: False)

    with pytest.raises(ConfigError) as exc:
        init_rate_limiter(_bare_app(), storage_uri=REDIS_URI)

    assert any("redis" in p for p in exc.value.problems)


def test_the_refusal_does_not_print_the_redis_password(production, monkeypatch):
    """A ConfigError message reaches boot logs and supervisors. No credentials."""
    monkeypatch.setattr("security._redis_driver_available", lambda: False)

    with pytest.raises(ConfigError) as exc:
        init_rate_limiter(
            _bare_app(), storage_uri="rediss://default:hunter2@cache.example.com:6379/0"
        )

    message = str(exc.value)
    assert "hunter2" not in message
    assert "cache.example.com" in message  # the operator still has to act on it


def test_a_redis_uri_with_no_driver_still_degrades_outside_production(
    development, monkeypatch, caplog
):
    """Dev keeps the old behaviour: a laptop without `redis` must still run."""
    monkeypatch.setattr("security._redis_driver_available", lambda: False)

    with caplog.at_level(logging.ERROR, logger="solverah.security"):
        limiter = init_rate_limiter(_bare_app(), storage_uri=REDIS_URI)

    assert limiter is not None
    assert any("ratelimit_backend_unavailable" in r.message for r in caplog.records)


def test_a_healthy_redis_config_boots(production, monkeypatch):
    monkeypatch.setattr("security._redis_driver_available", lambda: True)

    assert init_rate_limiter(_bare_app(), storage_uri=REDIS_URI) is not None


def test_the_two_fatal_paths_agree_with_what_resolve_would_have_chosen(production):
    """The guard has to sit on the value that is actually used.

    A refusal keyed on something other than `resolve_storage_uri`'s answer would
    be a guard on a different setting than the one the limiter serves.
    """
    assert resolve_storage_uri({}) == MEMORY_STORAGE

    with pytest.raises(ConfigError):
        init_rate_limiter(_bare_app())


# ── Runtime is tolerant ─────────────────────────────────────────────────────

def test_the_tolerance_flags_are_actually_set_on_the_app(development):
    """Both knobs, on the config the extension reads during init_app.

    Asserted separately from the behaviour below because the behavioural test
    exercises one of the two paths; this one proves the backstop is armed.

    The two names are written out rather than looped over
    `RUNTIME_TOLERANCE_CONFIG`, which would be a test of nothing: emptying that
    dict would empty the loop and the test would pass against a limiter with no
    tolerance configured at all.
    """
    from solverah.extensions import limiter

    app = _bare_app("tolerance-flags")
    init_rate_limiter(app, storage_uri=MEMORY_STORAGE, limiter=limiter)

    assert app.config["RATELIMIT_IN_MEMORY_FALLBACK_ENABLED"] is True
    assert app.config["RATELIMIT_SWALLOW_ERRORS"] is True
    assert RUNTIME_TOLERANCE_CONFIG == {
        "RATELIMIT_IN_MEMORY_FALLBACK_ENABLED": True,
        "RATELIMIT_SWALLOW_ERRORS": True,
    }


def test_an_unreachable_store_degrades_instead_of_500ing(client, caplog):
    """The whole point of the runtime half. Fails against a bare limiter.

    The live app's storage is broken mid-flight by making every counter
    operation raise, which is what an unreachable Redis looks like from inside
    Flask-Limiter. Without the tolerance flags the exception propagates out of
    `_check_request_limit` and the request is a 500.
    """
    from app import app
    from solverah.extensions import limiter

    def unreachable(*_a, **_k):
        raise ConnectionError("redis is not answering")

    limiter.reset()
    app.config["TESTING"] = False  # turn off the test-client exemption
    strategy = limiter._limiter
    original = (strategy.test, strategy.hit)
    strategy.test, strategy.hit = unreachable, unreachable
    try:
        with caplog.at_level(logging.WARNING, logger="flask-limiter"):
            res = client.post(
                "/api/v1/auth/password/forgot", json={"email": "someone@example.com"}
            )
    finally:
        strategy.test, strategy.hit = original
        app.config["TESTING"] = True
        limiter._storage_dead = False
        limiter.reset()

    assert res.status_code == 200, res.get_data(as_text=True)
    assert any(
        r.levelno >= logging.WARNING and "storage" in r.getMessage().lower()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


def test_a_real_refusal_is_still_a_refusal(enforcing):
    """Tolerance must not have swallowed the 429 as well.

    `RateLimitExceeded` is re-raised by the library before `swallow_errors` is
    consulted -- asserted rather than trusted, because a limiter that fails open
    on *breach* would be worse than no limiter at all.
    """
    statuses = [
        enforcing.post(
            "/api/v1/auth/password/forgot", json={"email": "nobody@example.com"}
        ).status_code
        for _ in range(4)
    ]

    assert statuses[3] == 429


@pytest.fixture()
def enforcing(client):
    """A client with the TESTING exemption off. Mirrors tests/test_rate_limits.py."""
    from app import app
    from solverah.extensions import limiter

    limiter.reset()
    app.config["TESTING"] = False
    try:
        yield client
    finally:
        app.config["TESTING"] = True
        limiter.reset()
