"""In-process cache of generated path suggestions.

Lifted from ``app.py``, where the dict and its lock were module globals and six
handlers reached into them directly.

This is deliberately still a plain dict behind a lock, unchanged in behaviour.
It is also unambiguously wrong for production and is Phase 3's to fix:

  * It is **per worker**.  With N gunicorn workers a user gets a hit only when
    they land on the process that generated their suggestions -- so the cache
    hit rate is 1/N, and the expensive path is taken far more often than the
    numbers suggest.
  * It is **unbounded**.  Nothing evicts, so it grows with the number of distinct
    users a worker has ever served.
  * It is **lost on deploy**, which is when the miss storm is least welcome.

Collecting it here means the Phase 3 swap to Redis is a change to one module
rather than to six call sites, and the lock discipline is in one place instead
of being re-derived at each of them.
"""

from __future__ import annotations

from threading import Lock
from typing import Dict, Optional

__all__ = ["get", "invalidate", "store", "clear", "snapshot"]

_cache: Dict[int, dict] = {}  # user_id -> response payload
_lock = Lock()


def get(user_id: int) -> Optional[dict]:
    """Return the cached payload for *user_id*, or None."""
    with _lock:
        return _cache.get(user_id)


def store(user_id: int, payload: dict) -> None:
    """Cache *payload* for *user_id*."""
    with _lock:
        _cache[user_id] = payload


def invalidate(user_id: int) -> None:
    """Drop any cached payload for *user_id*.

    Called from every write that changes an input to path scoring -- skills,
    experience, proficiencies, career status, preferences, assessment results.
    Missing one of those calls does not fail loudly; it serves a stale
    suggestion, which is why they are enumerated in
    ``tests/test_path_preferences_api.py`` rather than left to review.
    """
    with _lock:
        _cache.pop(user_id, None)


def clear() -> None:
    """Empty the cache. Used by tests to isolate one case from the next."""
    with _lock:
        _cache.clear()


def snapshot() -> Dict[int, dict]:
    """A copy of the current contents, for assertions and diagnostics."""
    with _lock:
        return dict(_cache)
