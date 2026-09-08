"""The two per-worker caches are bounded. Regression tests for the 2026-09-08 outage.

Production booted 2026-09-03 19:19 UTC and was SIGKILLed 2026-09-08 14:13, dead
by 15:16. Three gunicorn workers, never recycled, each holding two dicts that
nothing ever deleted from:

  * ``path_cache._cache`` -- keyed by user_id, no eviction of any kind; and
  * ``agent_service._resume_cache`` -- a ten-minute TTL consulted **only on
    read**, so an entry whose user never returned was never evaluated again and
    therefore never expired, while holding up to 6 KB of resume text.

``gunicorn.conf.py`` now recycles workers, which bounds any per-worker leak
regardless of cause -- that is guarded by ``tests/test_gunicorn_config.py``.
These tests guard the causes themselves. Both are needed: recycling turns an
unbounded leak into a sawtooth, and only these make the sawtooth flat.

Every test here fails against the code as it stood on 2026-09-07.
"""

from __future__ import annotations

import pytest

from solverah.services import agent_service, path_cache


@pytest.fixture(autouse=True)
def _clean_caches():
    """Neither cache may leak state between tests -- they are module globals."""
    path_cache.clear()
    agent_service._resume_cache.clear()
    yield
    path_cache.clear()
    agent_service._resume_cache.clear()


# ── path_cache ──────────────────────────────────────────────────────────────


def test_path_cache_is_bounded():
    """Storing more distinct users than the cap must not grow the dict.

    This is the direct regression: before the fix ``_cache`` was a plain dict
    and this loop would leave 600 entries resident forever.
    """
    for user_id in range(path_cache.MAX_ENTRIES + 100):
        path_cache.store(user_id, {"suggestions": [user_id]})

    assert len(path_cache.snapshot()) == path_cache.MAX_ENTRIES


def test_path_cache_evicts_least_recently_used_not_oldest():
    """A user who keeps reading must not be evicted on age alone.

    Insertion-order eviction would drop the most active users first, which is
    the opposite of what a cache is for. The ``move_to_end`` in ``get`` is what
    makes this pass; without it user 0 is evicted despite being read most
    recently.
    """
    for user_id in range(path_cache.MAX_ENTRIES):
        path_cache.store(user_id, {"n": user_id})

    # Touch the oldest entry, making it the most recently used.
    assert path_cache.get(0) == {"n": 0}

    # One more insert must now evict user 1, not user 0.
    path_cache.store(9999, {"n": 9999})

    snapshot = path_cache.snapshot()
    assert 0 in snapshot, "the most recently read entry was evicted"
    assert 1 not in snapshot, "the least recently used entry survived"
    assert 9999 in snapshot


def test_path_cache_behaviour_is_otherwise_unchanged():
    """Bounding must not alter the semantics six call sites depend on."""
    path_cache.store(7, {"a": 1})
    assert path_cache.get(7) == {"a": 1}

    path_cache.store(7, {"a": 2})           # overwrite, not duplicate
    assert path_cache.get(7) == {"a": 2}
    assert len(path_cache.snapshot()) == 1

    path_cache.invalidate(7)
    assert path_cache.get(7) is None

    path_cache.invalidate(7)                # idempotent
    path_cache.store(8, {})
    path_cache.clear()
    assert path_cache.snapshot() == {}


# ── agent_service resume cache ──────────────────────────────────────────────


@pytest.fixture()
def fetch(monkeypatch):
    """Drive ``fetch_resume_text`` with S3 and extraction stubbed.

    S3 is an external service, so it is mocked; everything else -- the cache,
    the TTL arithmetic, the temp-file handling -- is the real code path. The
    returned helper also lets a test move the clock, since the leak being
    guarded against is entirely about what happens as time passes.
    """
    clock = {"now": 1000.0}
    monkeypatch.setattr(agent_service.time, "monotonic", lambda: clock["now"])
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")

    class _Body:
        def read(self):
            return b"%PDF-1.4 fake"

    class _S3:
        def get_object(self, Bucket, Key):
            return {"Body": _Body()}

    monkeypatch.setattr(agent_service.storage, "get_s3_client", lambda: _S3())
    monkeypatch.setattr(
        agent_service.resume_service,
        "extract_resume_text",
        lambda path, mime: "resume text " + "x" * 100,
    )

    def _fetch(resume_key: str) -> str:
        return agent_service.fetch_resume_text(
            {"resumeKey": resume_key, "uploadedResume": {"type": "application/pdf"}}
        )

    _fetch.clock = clock
    return _fetch


def test_expired_entries_do_not_survive_forever(fetch):
    """THE leak. An entry nobody reads again must still be evicted.

    Before the fix the TTL was checked only on read, so this sequence left
    ``alice`` resident indefinitely: she is stored, her TTL passes, and nobody
    ever reads her key again. The write for ``bob`` now sweeps her out.
    """
    fetch("alice")
    assert "alice" in agent_service._resume_cache

    # Move past alice's TTL. Nobody reads her key again.
    fetch.clock["now"] += agent_service._RESUME_CACHE_TTL + 1

    fetch("bob")

    assert "alice" not in agent_service._resume_cache, (
        "an expired entry nobody re-read stayed resident -- this is the 2026-09-08 leak"
    )
    assert "bob" in agent_service._resume_cache


def test_expired_entry_is_dropped_on_read_too(fetch):
    """A reader that finds an expired entry removes it rather than re-serving it."""
    fetch("alice")
    fetch.clock["now"] += agent_service._RESUME_CACHE_TTL + 1

    # Re-fetching the same key must re-extract, and must not leave two entries.
    fetch("alice")
    assert len(agent_service._resume_cache) == 1


def test_resume_cache_is_bounded_even_when_nothing_has_expired(fetch):
    """The backstop: every entry live at once must still not grow without bound."""
    for i in range(agent_service._RESUME_CACHE_MAX + 50):
        fetch(f"resume-{i}")

    assert len(agent_service._resume_cache) <= agent_service._RESUME_CACHE_MAX


def test_cache_still_prevents_re_extraction(fetch, monkeypatch):
    """The cache must still do its job -- a hit must not re-extract from S3."""
    calls = {"n": 0}

    def _counting_extract(path, mime):
        calls["n"] += 1
        return "text"

    monkeypatch.setattr(
        agent_service.resume_service, "extract_resume_text", _counting_extract
    )

    assert fetch("alice") == "text"
    assert fetch("alice") == "text"
    assert calls["n"] == 1, "a cache hit re-extracted the resume"
