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
from typing import Callable, Dict, NamedTuple, Optional, Tuple

__all__ = [
    "get",
    "invalidate",
    "is_narrated",
    "store",
    "clear",
    "snapshot",
    "get_reserve",
    "store_reserve",
    "reserve_snapshot",
    "narration_token",
    "store_rescore",
    "finish_narration",
]

#: W-16. ``fill(payload, narratives) -> (filled_payload, any_narrator_prose)``.
#:
#: Supplied by ``intelligence_service`` because the fallback sentence is its copy,
#: not this module's. Called UNDER this module's lock, so it must be a pure
#: function of its arguments: no I/O, no call back into this module.
Fill = Callable[[dict, Dict[str, dict]], Tuple[dict, bool]]


class _Entry(NamedTuple):
    """One user's cached payload and what is known about it.

    ``narrated`` is W-14's flag. ``token`` and ``pending`` are W-16's: the id of
    the scoring job that produced the list, and whether that job's narration
    phase is still running. A tap inherits the token of the list it re-ranked
    (the profile did not change, so neither did the narrator's inputs), which is
    how a narration that lands after a tap still finds the list to fill.
    """

    payload: dict
    narrated: bool
    token: Optional[str] = None
    pending: bool = False

#: Most-recently-used payloads retained per worker.
#:
#: A payload is one user's scored path suggestions. 500 of them is a few MB per
#: worker -- small next to the ~150 MB baseline a worker already carries for
#: pandas, numpy and scikit-learn -- while being far more than the number of
#: users any single worker serves inside a deploy window at current traffic. It
#: is a memory ceiling, not a tuned hit-rate target: raise it only with a
#: measurement, since three workers pay it independently.
MAX_ENTRIES = 500

#: ``user_id -> _Entry(payload, narrated, token, pending)``.
#:
#: (``token`` and ``pending`` are W-16's; see :class:`_Entry`.)
#:
#: **The second half is W-14.**  Two different things get stored under one key.
#: The scoring job narrates and stores a page of written cards; ``_rescore`` -- a
#: tap, or "Start over" -- also stores, and on a cold worker it has nothing to
#: write from, so what it stores is ten fallback sentences with no pills.  Before
#: W-14 the next job read that back as a hit and served it, and so did every
#: reload after it, until some unrelated profile write invalidated the entry.  In
#: production that was every user's first tap after a deploy or a worker recycle.
#:
#: A key on the *payload* would have recorded it in one place, but the payload
#: **is the wire** (see `_reserve` below), so the flag rides beside the payload
#: in the entry instead: :func:`store` sets it and :func:`is_narrated` answers
#: it.  Inside the entry rather than in a second dict keyed by user, so that it
#: is evicted, invalidated and cleared by construction: this module is the one
#: that filled a worker until production was SIGKILLed, and a parallel
#: per-user structure maintained by hand is exactly how that comes back.
#: :func:`get` and :func:`snapshot` unwrap, so every existing caller still sees
#: the payload alone.
_cache: "OrderedDict[int, _Entry]" = OrderedDict()

#: W-12, widened by W-14.  ``user_id -> {onet_code: {"why_text",
#: "profile_dimensions"}}`` for **every** card the scoring job narrated -- the
#: ten on the page and the ten below it.
#:
#: **Why it lives in this module and not next to it.** The scoring job narrates
#: twenty cards and shows ten; all twenty are written down so that a tap which
#: promotes one of them finds prose instead of "Uses your SQL." (F-8, routed
#: onward, now wanted).  They cannot go in the payload:
#: ``cached_path_suggestions`` returns the cached dict as the response body and
#: the job stores it as its result, so **this cache is the wire** and a new key
#: in it is a new field on ``GET /me/path-suggestions``.
#:
#: **Why all twenty and not only the ten below the page** (W-14).  W-12 stored
#: the reserve as the complement of the page, on the reasoning that a page card's
#: prose is already on the payload and can be carried forward.  It is -- until the
#: card is *removed*.  Tap "Not for me" on card 9 and the payload that replaces
#: the cached one no longer carries it; press "Start over" and card 9 is back on
#: the page with its prose nowhere: not on the payload, and not in a reserve that
#: was defined to exclude it.  It returned reading "Uses your SQL." with no pills
#: next to nine narrated neighbours.  Holding every narrative the job wrote costs
#: ten more small dicts per user and makes "a card that ever had prose gets it
#: back" true by construction rather than by which half of the list it was in.
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
        entry = _cache.get(user_id)
        if entry is None:
            return None
        _cache.move_to_end(user_id)
        return entry.payload


def _put(user_id: int, entry: _Entry) -> None:
    """Insert under the lock the caller already holds, evicting LRU if full."""
    _cache[user_id] = entry
    _cache.move_to_end(user_id)
    while len(_cache) > MAX_ENTRIES:
        _cache.popitem(last=False)


def store(
    user_id: int,
    payload: dict,
    narrated: bool = True,
    *,
    token: Optional[str] = None,
    pending: bool = False,
) -> None:
    """Cache *payload* for *user_id*, evicting the least recently used if full.

    *narrated* (W-14) says whether this payload carries prose the narrator wrote.
    See :data:`_cache` for what the flag is for and :func:`is_narrated` for who
    reads it.

    *token* and *pending* (W-16) are the scoring job's: a job stores its SCORED
    list before the narrator runs, with ``pending=True`` and its own token, and
    :func:`finish_narration` is what later fills it and clears ``pending``.
    """
    with _lock:
        _put(user_id, _Entry(payload, narrated, token, pending))


def is_narrated(user_id: int) -> bool:
    """Was *user_id*'s cached payload written with narrator prose on it? (W-14)

    False for a miss as well as for a fallback-only page: both mean "there is
    nothing here worth serving instead of narrating", which is the one question
    ``path_suggestions`` asks before it decides to run the narrator.

    Deliberately not folded into :func:`get`: the GET and the job disagree about
    what to do with a fallback-only payload -- the GET serves it, because it is
    what the user is looking at, and the job ignores it and narrates -- so the
    two facts are asked for separately.
    """
    with _lock:
        entry = _cache.get(user_id)
        return bool(entry and entry.narrated)


def narration_token(user_id: int) -> Optional[str]:
    """The token of the narration still running for *user_id*'s list, or None (W-16).

    None for a miss, for a list whose narration has finished, and for a list no
    job narrates (a tap on a cold worker). The tap path asks this to decide
    whether a card with no sentence yet should shimmer -- a sentence is on its
    way -- or take the fallback now, because nothing is coming.
    """
    with _lock:
        entry = _cache.get(user_id)
        if entry is None or not entry.pending:
            return None
        return entry.token


def store_rescore(user_id: int, payload: dict, narrated: bool, fill: Fill) -> dict:
    """Store a tap's re-ranked list, keeping the narration it re-ranked (W-16).

    Returns the payload actually stored -- which is what the tap must answer
    with, because it can differ from the one passed in:

    * The tap's list INHERITS the current entry's token and ``pending`` state.
      The profile did not change, so the narration still running for the old
      list is writing sentences for this one too, and
      :func:`finish_narration` must still recognise it.
    * If the payload says ``narration_pending`` but the narration FINISHED
      between the tap reading the cache and this store -- the race this is under
      the lock to close -- it is filled here from the reserve that narration
      just wrote, so no list is ever stored waiting for a narration that has
      already come and gone.
    """
    with _lock:
        entry = _cache.get(user_id)
        token = entry.token if entry is not None else None
        pending = bool(payload.get("narration_pending"))
        if pending and not (entry is not None and entry.pending):
            payload, filled = fill(payload, dict(_reserve.get(user_id) or {}))
            narrated = narrated or filled
            pending = False
        _put(user_id, _Entry(payload, narrated, token, pending))
        return payload


def finish_narration(
    user_id: int, token: str, narratives: Dict[str, dict], fill: Fill
) -> Optional[dict]:
    """Land one narration: fill the cached list and replace the reserve (W-16).

    Only if the cached entry still carries *token*. Anything else means the list
    this narration was for is gone -- a profile write invalidated it (and the
    sentences may describe a person who no longer exists), or a newer job
    replaced it (and that job's own narration is the one to land) -- so nothing
    here is touched and None is returned.

    Otherwise the entry's list -- the job's own, or a tap's that inherited the
    token -- is filled card by card through *fill*, ``pending`` is cleared, the
    reserve becomes *narratives* (W-12/W-14's "every narrative this job wrote"),
    and the filled payload is returned.
    """
    with _lock:
        entry = _cache.get(user_id)
        if entry is None or entry.token != token:
            return None
        _reserve[user_id] = dict(narratives)
        _reserve.move_to_end(user_id)
        while len(_reserve) > MAX_ENTRIES:
            _reserve.popitem(last=False)
        payload, filled = fill(entry.payload, dict(narratives))
        _put(user_id, _Entry(payload, entry.narrated or filled, token, False))
        return payload


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
    """A copy of the current payloads, for assertions and diagnostics.

    Payloads only, not the W-14 ``narrated`` flag beside them: this answers
    "what is cached", which is what its callers in ``tests/test_cache_bounds.py``
    are counting. :func:`is_narrated` answers the other question.
    """
    with _lock:
        return {user_id: entry.payload for user_id, entry in _cache.items()}


# ---------------------------------------------------------------------------
# The reserve narratives (W-12)
# ---------------------------------------------------------------------------


def store_reserve(user_id: int, narratives: Dict[str, dict]) -> None:
    """Cache every narrative one job wrote for *user_id*.

    Same LRU bound and the same ``MAX_ENTRIES`` as the payloads: one entry is
    twenty ``{"why_text", "profile_dimensions"}`` dicts (W-14 widened it from
    ten), smaller than the payload it accompanies, and a worker that holds one
    should hold the other.
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
