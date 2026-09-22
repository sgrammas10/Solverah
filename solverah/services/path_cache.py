"""In-process cache of generated path suggestions.

Lifted from ``app.py``, where the dict and its lock were module globals and six
handlers reached into them directly.

An LRU dict behind a lock. Two of the three original problems remain, and are
still Phase 3's to fix:

  * It is **per worker**.  With N gunicorn workers a user gets a hit only when
    they land on the process that generated their suggestions -- so the cache
    hit rate is 1/N, and the expensive path is taken far more often than the
    numbers suggest.
  * It is **lost on deploy**, which is when the miss storm is least welcome.

The third -- that it was **unbounded** -- was fixed on 2026-09-08, because it
stopped being theoretical. This dict and ``agent_service._resume_cache`` grew
for 4.8 days across three gunicorn workers that never recycled, and production
died of it (SIGKILL 14:13, total failure 15:16). ``gunicorn.conf.py`` now
recycles workers, which bounds *any* per-worker leak; the cap below removes this
particular one at the source, so the two are belt and braces rather than
duplicates.

**Why a size cap and not a TTL.** Entries here are invalidated by the writes that
change their inputs -- :func:`invalidate` is called from every one of them, and
that enumeration is tested in ``tests/test_path_preferences_api.py``. A TTL would
add a second, weaker correctness mechanism next to a working one. What was
missing was purely a memory bound, so a memory bound is what was added: the
cache now holds the ``MAX_ENTRIES`` most recently used users and forgets the
rest, which costs a recomputation and never a wrong answer.

Collecting it here means the Phase 3 swap to Redis is a change to one module
rather than to six call sites, and the lock discipline is in one place instead
of being re-derived at each of them. That swap is now unblocked -- production
gained Redis on 2026-09-08 -- and ``solverah/infra/cache.py`` is the adapter it
should use, including :func:`~solverah.infra.cache.invalidate_on_commit` rather
than a direct delete, for the reason its docstring gives.
"""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import Dict, Optional

__all__ = [
    "get",
    "invalidate",
    "store",
    "clear",
    "snapshot",
    "get_reserve",
    "store_reserve",
    "reserve_snapshot",
]

#: Most-recently-used payloads retained per worker.
#:
#: A payload is one user's scored path suggestions. 500 of them is a few MB per
#: worker -- small next to the ~150 MB baseline a worker already carries for
#: pandas, numpy and scikit-learn -- while being far more than the number of
#: users any single worker serves inside a deploy window at current traffic. It
#: is a memory ceiling, not a tuned hit-rate target: raise it only with a
#: measurement, since three workers pay it independently.
MAX_ENTRIES = 500

_cache: "OrderedDict[int, dict]" = OrderedDict()  # user_id -> response payload

#: W-12.  ``user_id -> {onet_code: {"why_text", "profile_dimensions"}}`` for the
#: cards BELOW the ten the payload above holds.
#:
#: **Why it lives in this module and not next to it.** The scoring job narrates
#: twenty cards and shows ten; the other ten are written so that a tap promoting
#: one of them finds prose instead of "Uses your SQL." (F-8, routed onward, now
#: wanted).  They cannot go in the payload: ``cached_path_suggestions`` returns
#: the cached dict as the response body and the job stores it as its result, so
#: **this cache is the wire** and a new key in it is a new field on
#: ``GET /me/path-suggestions``.
#:
#: What they must share with the payload is a LIFETIME.  A narrative is written
#: against one profile, and a profile edit that drops the shortlist has to drop
#: the reserve with it or a tap would promote a card wearing prose about a person
#: who no longer exists -- the one failure a separate store invites and the
#: reason this is a second dict here rather than a second module.  Every writer
#: that changes a scoring input already calls :func:`invalidate` (the enumeration
#: `tests/test_path_preferences_api.py` guards), so putting the reserve behind
#: the same function and the same lock covers all of them at once and cannot be
#: half-done by a caller that forgets the second call.
_reserve: "OrderedDict[int, Dict[str, dict]]" = OrderedDict()
_lock = Lock()


def get(user_id: int) -> Optional[dict]:
    """Return the cached payload for *user_id*, or None.

    A hit marks the entry most-recently-used, which is what makes the eviction
    in :func:`store` LRU rather than insertion-ordered. Without it, an active
    user's entry would be evicted on age alone while idle ones survived.
    """
    with _lock:
        payload = _cache.get(user_id)
        if payload is not None:
            _cache.move_to_end(user_id)
        return payload


def store(user_id: int, payload: dict) -> None:
    """Cache *payload* for *user_id*, evicting the least recently used if full."""
    with _lock:
        _cache[user_id] = payload
        _cache.move_to_end(user_id)
        while len(_cache) > MAX_ENTRIES:
            _cache.popitem(last=False)


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
        # W-12. The reserve goes with it, always. See `_reserve`.
        _reserve.pop(user_id, None)


def clear() -> None:
    """Empty the cache. Used by tests to isolate one case from the next."""
    with _lock:
        _cache.clear()
        _reserve.clear()


def snapshot() -> Dict[int, dict]:
    """A copy of the current contents, for assertions and diagnostics."""
    with _lock:
        return dict(_cache)


# ---------------------------------------------------------------------------
# The reserve narratives (W-12)
# ---------------------------------------------------------------------------


def store_reserve(user_id: int, narratives: Dict[str, dict]) -> None:
    """Cache the below-the-page narratives for *user_id*.

    Same LRU bound and the same ``MAX_ENTRIES`` as the payloads: one entry is
    ten ``{"why_text", "profile_dimensions"}`` dicts, smaller than the payload
    it accompanies, and a worker that holds one should hold the other.
    """
    with _lock:
        _reserve[user_id] = narratives
        _reserve.move_to_end(user_id)
        while len(_reserve) > MAX_ENTRIES:
            _reserve.popitem(last=False)


def get_reserve(user_id: int) -> Dict[str, dict]:
    """The reserve narratives for *user_id*, or an empty mapping.

    Empty rather than None: every caller is asking "is there prose for this
    card", and a miss is "no" rather than an error -- the reserve is an
    optimisation over the fallback sentence, never a precondition for one.
    """
    with _lock:
        narratives = _reserve.get(user_id)
        if narratives is None:
            return {}
        _reserve.move_to_end(user_id)
        return dict(narratives)


def reserve_snapshot() -> Dict[int, Dict[str, dict]]:
    """A copy of the reserve, for assertions and diagnostics."""
    with _lock:
        return {user_id: dict(item) for user_id, item in _reserve.items()}
