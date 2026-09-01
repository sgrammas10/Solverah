"""Redis read cache, invalidated by key on write.

Phase 3, item 4.  Two reads are cached: a company's research profile
(``GET /companies/{id}``) and the job-seeker dashboard (``GET /me/dashboard``).

**Match sets are deliberately not cached.**  Phase 3 as written in
docs/ARCHITECTURE.md lists them first, and that item is dropped rather than
deferred: the interim ``culture_fit_score`` scorer is being deleted, not
migrated -- it measures 34ms across 2,071 companies -- and a cache built around
its output is deleted along with it.  The causal Bayesian model that replaces it
has a different key, a different invalidation trigger, and a different shape.

**No Redis is a supported configuration, not a degraded one.**  CI runs no Redis
service container, and a developer with ``REDIS_URL`` unset must get the same
answers as one without.  Every function here therefore answers "miss" rather
than raising when there is no client, and a *runtime* Redis failure is treated
identically: a cache that is down makes reads slower, never wrong, and never a
500.  This is the same call ``security.py`` makes about the rate limiter.

**Invalidation happens after the commit, not before it.**  A writer that deletes
the key before committing opens a window in which a concurrent reader repopulates
the cache from the pre-write state and leaves it there -- stale until the TTL,
caused by the very write that was supposed to clear it.  Writers therefore call
:func:`invalidate_on_commit`, which parks the keys on the session and drops them
from an ``after_commit`` hook.  A rolled-back transaction drops nothing, which is
correct: nothing changed.

The TTL is a backstop for an invalidation someone forgot to write, not the
mechanism.  If correctness ever depends on it, the missing ``invalidate_on_commit``
call is the bug.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable, List, Optional

from sqlalchemy import event as sa_event

from model import db

__all__ = [
    "SESSION_INVALIDATION_KEY",
    "clear_client",
    "company_detail_key",
    "dashboard_key",
    "delete",
    "get_json",
    "init_cache",
    "invalidate_on_commit",
    "is_enabled",
    "set_json",
]

logger = logging.getLogger("solverah.cache")

#: Bumped when a cached payload's *shape* changes, which retires every key of the
#: previous shape without a flush and without a deploy-ordering problem: old
#: workers read old keys, new workers read new ones, and the old ones expire.
KEY_VERSION = "v1"

#: Where pending invalidations live between the write and its commit.
SESSION_INVALIDATION_KEY = "solverah_cache_invalidate"

_url: Optional[str] = None
_default_ttl: int = 300
_client: Any = None
_client_resolved = False
_listener_installed = False


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

def company_detail_key(company_id: int) -> str:
    """Cache key for one company's research profile."""
    return "solverah:%s:company:%s" % (KEY_VERSION, company_id)


def dashboard_key(user_id: int) -> str:
    """Cache key for one user's dashboard summary."""
    return "solverah:%s:dashboard:%s" % (KEY_VERSION, user_id)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

def init_cache(app, settings=None) -> None:
    """Resolve the backend for this application and install the commit hook."""
    global _url, _default_ttl
    _url = settings.redis_url if settings else None
    _default_ttl = settings.cache_default_ttl_seconds if settings else 300
    clear_client()
    _install_commit_listener()

    app.extensions["solverah_cache_enabled"] = bool(_url)
    if not _url:
        # INFO, not WARNING: running without Redis is the documented local and CI
        # configuration.  The production case is covered by config.py's warning
        # about memory:// rate limiting, which is the same missing variable.
        logger.info("cache_disabled", extra={"event": "cache_disabled"})


def clear_client() -> None:
    """Drop the memoised client so the next call re-resolves it.

    Used by :func:`init_cache` and by tests that move ``REDIS_URL`` between
    cases; without it the first test to resolve a client pins that decision for
    the rest of the session.
    """
    global _client, _client_resolved
    _client = None
    _client_resolved = False


def is_enabled() -> bool:
    """Whether a cache backend is configured *and* reachable."""
    return _get_client() is not None


def _get_client():
    """The Redis client, or None. Resolved once; failures are not retried per call."""
    global _client, _client_resolved
    if _client_resolved:
        return _client

    _client_resolved = True
    if not _url:
        _client = None
        return None

    try:
        import redis

        client = redis.Redis.from_url(
            _url,
            decode_responses=True,
            # A cache is never worth waiting on: a Redis that has gone away must
            # cost a read a few milliseconds, not the request's whole budget.
            socket_timeout=0.25,
            socket_connect_timeout=0.25,
        )
        client.ping()
        _client = client
    except Exception as exc:  # noqa: BLE001 -- absent backend is a supported state
        logger.warning(
            "cache_unavailable", extra={"event": "cache_unavailable", "error": str(exc)}
        )
        _client = None
    return _client


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def get_json(key: str) -> Optional[Any]:
    """Return the decoded value at *key*, or None for a miss.

    A stored value that will not decode is a miss and is deleted: it can only
    have come from a previous shape of the payload, and serving it would put a
    body on the wire that the current schema never produced.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
    except Exception as exc:  # noqa: BLE001 -- a cache failure is a miss
        logger.warning("cache_get_failed", extra={"event": "cache_get_failed",
                                                  "key": key, "error": str(exc)})
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        delete(key)
        return None


def set_json(key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
    """Store *value* at *key*. Returns whether it was stored.

    A value that will not serialise is dropped rather than raised: caching is an
    optimisation, and a response must not fail because it could not be cached.
    """
    client = _get_client()
    if client is None:
        return False
    try:
        payload = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        logger.warning("cache_encode_failed", extra={"event": "cache_encode_failed",
                                                     "key": key, "error": str(exc)})
        return False
    try:
        client.setex(key, ttl_seconds or _default_ttl, payload)
        return True
    except Exception as exc:  # noqa: BLE001 -- see module docstring
        logger.warning("cache_set_failed", extra={"event": "cache_set_failed",
                                                  "key": key, "error": str(exc)})
        return False


def delete(*keys: str) -> None:
    """Drop *keys*. Silent when there is no backend or the backend is down."""
    if not keys:
        return
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(*keys)
    except Exception as exc:  # noqa: BLE001 -- see module docstring
        logger.warning("cache_delete_failed", extra={"event": "cache_delete_failed",
                                                     "keys": list(keys), "error": str(exc)})


def invalidate_on_commit(*keys: str) -> None:
    """Drop *keys* when the current transaction commits, and not before.

    Safe to call with no Redis and safe to call outside a transaction that ever
    commits -- the keys are simply never dropped, because nothing changed.
    """
    if not keys:
        return
    pending: List[str] = db.session.info.setdefault(SESSION_INVALIDATION_KEY, [])
    pending.extend(keys)


def _install_commit_listener() -> None:
    """Attach the ``after_commit`` hook that flushes pending invalidations.

    Idempotent: ``create_app()`` can be called many times in one process (every
    test that builds an app does), and registering the listener once per app
    would delete each key N times.
    """
    global _listener_installed
    if _listener_installed:
        return

    @sa_event.listens_for(db.session, "after_commit")
    def _drop_pending(session) -> None:  # noqa: ANN001 -- SQLAlchemy's signature
        keys: Iterable[str] = session.info.pop(SESSION_INVALIDATION_KEY, ())
        if keys:
            delete(*keys)

    _listener_installed = True
