"""Every per-worker cache is bounded. Regression tests for two production outages.

**2026-09-08.** Production booted 2026-09-03 19:19 UTC and was SIGKILLed
2026-09-08 14:13, dead by 15:16. Three gunicorn workers, never recycled, each
holding two dicts that nothing ever deleted from:

  * ``path_cache._cache`` -- keyed by user_id, no eviction of any kind; and
  * ``agent_service._resume_cache`` -- a ten-minute TTL consulted **only on
    read**, so an entry whose user never returned was never evaluated again and
    therefore never expired, while holding up to 6 KB of resume text.

**2026-09-15.** The web dyno sat pinned at ~90-100% of 512 MB for eight hours
with repeated OOM restarts. Two more caches, in the O*NET scoring path, with the
same two defects between them:

  * ``path_scoring._EMBED_CACHE`` -- capped at 10,000 *entries* and not bytes,
    holding 1536-dim embeddings as ``list[float]`` at 48.50 KB each. A full
    cache was 473.6 MB, i.e. the cap permitted a cache nearly the size of the
    whole instance; and
  * ``onet_client._OCC_CACHE`` -- no size cap at all, and a 24h TTL consulted
    only on read. The 2026-09-08 lesson, written down in ``agent_service`` and
    never applied here.

``gunicorn.conf.py`` now recycles workers, which bounds any per-worker leak
regardless of cause -- that is guarded by ``tests/test_gunicorn_config.py``.
These tests guard the causes themselves. Both are needed: recycling turns an
unbounded leak into a sawtooth, and only these make the sawtooth flat. Recycling
is also inert at low traffic, since it fires per 2,000 requests per worker --
which is why 2026-09-15 was a flat plateau rather than the intended sawtooth.

Every test here fails against the code as it stood before its outage.

These assert the **bound**, never the pathology: a test that actually allocated
474 MB to prove the leak would be an OOM on the CI runner. They cap or shrink a
budget and check that eviction happens, and they measure with a deterministic
deep ``sys.getsizeof`` rather than RSS, which is not stable enough in CI.

**F-8 box 3 re-derived ``_EMBED_CACHE``'s budget, and the narrative above is
now history rather than the reason.** F-4 did not cap that demand, it removed
it: the cache no longer holds every role item of every candidate, and a cold
scoring run measures 3-14 entries / 19.6-91.7 KB where it used to be 300-700
entries / 15-35 MB. The 32 MB therefore needed a new justification or a cut,
and it has a new justification -- eviction here is FIFO, so the budget is a
*residency window* for the ~76-name Tier-2 core that every occupation and every
user shares. ``test_the_budget_is_a_residency_window_for_the_shared_core``
below is that argument as an assertion, and the arithmetic is in
``path_scoring``'s own comment. The cache also did NOT retire with the funnel,
as F-8's brief originally had it: F-5's deep fit and F-6's re-rank both use it,
and ``test_embed_cache_reads_tolerate_the_stored_vector_type`` pins that the two
tiers hold one object.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

import backend.services.onet_client as onet_client
import backend.services.path_scoring as path_scoring
from solverah.services import agent_service, path_cache


@pytest.fixture(autouse=True)
def _clean_caches():
    """No cache may leak state between tests -- they are all module globals."""
    def _clear() -> None:
        path_cache.clear()
        agent_service._resume_cache.clear()
        path_scoring._EMBED_CACHE.clear()
        onet_client._OCC_CACHE.clear()

    _clear()
    yield
    _clear()


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


# ── path_scoring embedding cache ────────────────────────────────────────────

#: Real embedding width, so per-entry footprint assertions mean something.
_EMBED_DIMS = 1536


def _deep_bytes(key: str, vec: object) -> int:
    """Resident cost of one cache entry, measured here rather than imported.

    Deliberately a local copy of ``path_scoring._embed_entry_bytes``: importing
    the production helper would make these fail with ``AttributeError`` against
    a tree that predates the fix, instead of failing with the real number they
    exist to pin down.

    ``sys.getsizeof`` covers an ndarray's data buffer, but a list holds only
    pointers -- its floats are separate 24-byte objects the cache keeps alive --
    so they are summed.
    """
    total = sys.getsizeof(key) + sys.getsizeof(vec)
    if isinstance(vec, list):
        total += sum(sys.getsizeof(f) for f in vec)
    return total


@pytest.fixture()
def embed(monkeypatch):
    """Drive ``_batch_embed`` with the OpenAI embeddings endpoint stubbed.

    OpenAI is an external service, so it is mocked; the cache, the byte
    accounting and the eviction loop are all the real code path.

    Every vector component is computed rather than ``[x] * dims``: a repeated
    list holds *dims* references to one float object, which would make the
    ``list[float]`` storage look ~4x cheaper than it is under ``_deep_bytes``
    and turn the size assertions into measurement artefacts. The real SDK parses
    distinct floats out of the response body, which is what this reproduces.
    """
    class _Item:
        def __init__(self, index: int, dims: int) -> None:
            self.index = index
            self.embedding = [(index + 1) * 0.001 + j * 1e-7 for j in range(dims)]

    class _Resp:
        def __init__(self, data: list) -> None:
            self.data = data

    class _Embeddings:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, model: str, input: list[str]) -> "_Resp":
            self.calls += 1
            return _Resp([_Item(i, _embed.dims) for i in range(len(input))])

    class _Client:
        def __init__(self) -> None:
            self.embeddings = _Embeddings()

    client = _Client()

    def _embed(texts: list[str], dims: int = _EMBED_DIMS) -> None:
        _embed.dims = dims
        path_scoring._batch_embed(texts, client)

    _embed.dims = _EMBED_DIMS
    _embed.client = client
    return _embed


def test_embed_cache_stores_compact_entries(embed) -> None:
    """A cached 1536-dim vector must not cost 48 KB of boxed Python floats.

    THE leak. As ``list[float]`` one entry is ~48.5 KB -- the list is only 12 KB
    of pointers, but the cache holds the only reference to 1536 float objects at
    24 bytes each. float32 storage is ~6.2 KB. The ceiling below sits between
    the two, so it fails on the real number rather than on a missing name.
    """
    embed(["active listening"])

    entry = path_scoring._EMBED_CACHE["active listening"]
    assert _deep_bytes("active listening", entry) < 8 * 1024


def test_embed_cache_is_bounded_by_bytes_not_entries(embed, monkeypatch) -> None:
    """The bound is a byte budget, so vector width cannot silently defeat it.

    An entry cap cannot: 10,000 entries was a perfectly small-sounding number
    that permitted 473.6 MB. The budget is shrunk to 256 KB here so ~60
    full-width vectors overshoot it -- filling the real 32 MB would be slow, and
    reproducing the 474 MB failure would be an OOM on the runner.
    """
    budget = 256 * 1024
    monkeypatch.setattr(path_scoring, "_EMBED_CACHE_MAX_BYTES", budget, raising=False)

    texts = ["role item %d" % i for i in range(60)]
    embed(texts)

    resident = sum(_deep_bytes(k, v) for k, v in path_scoring._EMBED_CACHE.items())
    assert resident <= budget
    assert len(path_scoring._EMBED_CACHE) > 0, "it emptied itself instead of evicting"
    assert texts[-1] in path_scoring._EMBED_CACHE, "the newest entry was evicted"
    assert texts[0] not in path_scoring._EMBED_CACHE, "the oldest entry survived"


def test_embed_cache_default_budget_fits_the_dyno() -> None:
    """The shipped budget must leave the 512 MB Starter room to serve requests.

    A booted worker with empty caches measures ~148 MB, so 364 MB is the whole
    headroom for every cache plus request handling. 64 MB is a deliberately
    loose ceiling -- it fails on a budget set by wishful thinking, not on a
    considered retune.
    """
    assert path_scoring._EMBED_CACHE_MAX_BYTES <= 64 * 1024 * 1024


#: The Tier-2 core: O*NET's ~35 generic skills plus its ~41 work activities.
#:
#: The same names for EVERY occupation -- that is F-4's central finding about
#: why the old scorer could not discriminate, and it is also why this cache
#: earns its place now. Measured 2026-09-16 over five real deep-fit clicks: the
#: first costs 97 entries, the fifth costs 16, and a second user clicking the
#: same five costs 7 and then nothing at all.
_TIER_TWO_CORE_ENTRIES = 76

#: Mean resident cost of one entry, measured the way `_evict_to_budget` counts.
_MEASURED_ENTRY_BYTES = 6_553

#: Marginal entries a new distinct user adds to a warm cache. Measured across
#: the 19 non-degenerate F-2 profiles: 158 entries for 19 users.
_MARGINAL_ENTRIES_PER_USER = 8.3


def test_the_budget_is_a_residency_window_for_the_shared_core() -> None:
    """F-8 box 3. The budget re-derived against the demand that exists now.

    The demand this number was originally set against is gone: before F-4 a
    single cold run added 300-700 entries / 15-35 MB, and 32 MB was about one
    run's worth. Measured after F-4, a cold run adds **3-14 entries / 19.6-91.7
    KB**. A budget 370x the thing it was sized against is not conservative, it
    is unexamined -- so it needed a reason or a cut.

    The reason is the eviction policy. `_evict_to_budget` is FIFO, not LRU
    (nothing calls `move_to_end` on a hit, deliberately), so the budget is not
    "how much may be cached" but **how long the shared Tier-2 core survives a
    stream of one-off user documents arriving behind it**. Evicting that core is
    the one thing that makes this cache stop paying for itself: it is re-bought
    from OpenAI on the next deep fit anybody asks for.

    So the assertion is the property, not the constant: the window must be
    large enough that the core is a rounding error inside it and survives a
    realistic run of distinct users. That fails on a careless shrink and passes
    for a considered retune in either direction -- which is what a budget with
    an env override wants.
    """
    window = path_scoring._EMBED_CACHE_MAX_BYTES // _MEASURED_ENTRY_BYTES

    assert window >= _TIER_TWO_CORE_ENTRIES * 20, (
        "the budget holds only %d entries: the %d-entry Tier-2 core is %.0f%% of "
        "the whole cache, so a handful of users evicts the most-shared entries "
        "in it" % (window, _TIER_TWO_CORE_ENTRIES, 100 * _TIER_TWO_CORE_ENTRIES / window)
    )

    users_before_the_core_is_pushed_out = window / _MARGINAL_ENTRIES_PER_USER
    assert users_before_the_core_is_pushed_out >= 200, (
        "at %.1f marginal entries per distinct user the core survives only %.0f "
        "users" % (_MARGINAL_ENTRIES_PER_USER, users_before_the_core_is_pushed_out)
    )


def test_one_cold_scoring_run_is_a_rounding_error_against_the_budget() -> None:
    """The OOM demand was removed, not capped, and this is what that means.

    Before F-4 one cold run could fill the entire budget by itself, so there was
    no eviction headroom at all -- the cap was one run wide. The worst run
    measured across the 20 F-2 profiles is now 14 entries / 91,739 bytes.
    """
    worst_measured_run_bytes = 91_739

    assert worst_measured_run_bytes * 100 < path_scoring._EMBED_CACHE_MAX_BYTES, (
        "the worst cold run is %.1f%% of the budget; it used to be ~100%% and "
        "that is the shape that OOMed"
        % (100 * worst_measured_run_bytes / path_scoring._EMBED_CACHE_MAX_BYTES)
    )


def test_the_budget_is_env_overridable_without_a_deploy() -> None:
    """`workers` going back above 1 divides this budget by the new W.

    The dashboard is where that would be noticed and the dashboard is where it
    has to be fixable, because a redeploy to change a constant is exactly what
    an incident does not have time for.

    In a SUBPROCESS, not via `importlib.reload`. The constant is read at import,
    so proving it in-process means reloading the module -- which replaces
    `_EMBED_CACHE` with a new dict while `path_deep_fit` still holds the old
    one, and the two tiers stop sharing an object for every test that runs
    afterwards. Measured: it turns nine unrelated tests red. A fresh interpreter
    is the honest way to assert something about import-time behaviour.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    probe = (
        "from backend.services.path_scoring import _EMBED_CACHE_MAX_BYTES as b;"
        "print(b)"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env={
            **os.environ,
            "PYTHONPATH": str(repo_root),
            "SOLVERAH_EMBED_CACHE_MAX_BYTES": str(7 * 1024 * 1024),
        },
    )

    assert out.returncode == 0, out.stderr
    assert int(out.stdout.strip()) == 7 * 1024 * 1024


def test_embed_cache_still_prevents_re_embedding(embed) -> None:
    """The cache must still do its job -- a hit must not re-call the API."""
    embed(["active listening"], dims=4)
    assert embed.client.embeddings.calls == 1

    embed(["active listening"], dims=4)
    assert embed.client.embeddings.calls == 1, "a cache hit re-called the embeddings API"


def test_embed_cache_reads_tolerate_the_stored_vector_type() -> None:
    """Every read site must survive an ndarray value.

    Not a leak test, and it passes before the fix as well -- the read sites were
    already ``is None``-clean when the storage type changed. It is a guard for
    that type change: numpy raises "truth value of an array with more than one
    element is ambiguous" on a bare ``if emb:``, so a later refactor that swaps
    an ``is None`` check for a truthiness test fails here rather than in prod.

    The two read sites exercised here moved to ``path_deep_fit`` in F-5, and the
    cache they read did not -- ``path_scoring._EMBED_CACHE`` is one dict shared
    by both tiers, which is what the 32 MB budget above is a budget for. So the
    call sites are imported from their new home and the cache is still poked
    through its old one, deliberately: if those ever stop being the same object
    the budget stops describing anything and this test says so.
    """
    import backend.services.path_deep_fit as path_deep_fit
    from backend.services.path_scoring import UserSkill

    assert path_deep_fit._EMBED_CACHE is path_scoring._EMBED_CACHE

    for name in ("python", "programming"):
        path_scoring._EMBED_CACHE[name] = np.asarray([1.0, 0.0], dtype=np.float32)

    skills = [UserSkill(name="Python", level="advanced")]
    role_items = [("programming", 90.0)]

    score, matched = path_deep_fit._compute_centroid_score(skills, role_items)
    assert score == pytest.approx(1.0)
    assert matched == ["Python"]
    assert path_deep_fit._role_coverage_score(skills, role_items) == pytest.approx(1.0)


# ── onet_client occupation cache ────────────────────────────────────────────


@pytest.fixture()
def occ(monkeypatch):
    """Build ``_OCC_CACHE`` keys against a movable clock.

    The leak being guarded against is entirely about what happens as time
    passes, so the helper exposes the clock the same way the resume-cache
    fixture above does.
    """
    clock = {"now": 1000.0}
    monkeypatch.setattr(onet_client.time, "monotonic", lambda: clock["now"])

    def _key(code: str) -> tuple:
        return ("get_job_zone", code, ())

    _key.clock = clock
    return _key


def test_expired_occupation_entries_do_not_survive_forever(occ) -> None:
    """THE leak, second occurrence. An entry nobody reads again must still go.

    Before the fix ``_occ_cache_get`` returned None on expiry but left the entry
    resident, and ``_occ_cache_set`` never swept -- so an occupation that fell
    out of the candidate pool was never read again and never reclaimed. Exactly
    the shape ``agent_service`` names and fixes for itself above.
    """
    onet_client._occ_cache_set(occ("15-1252.00"), 4)
    assert occ("15-1252.00") in onet_client._OCC_CACHE

    occ.clock["now"] += onet_client._OCC_CACHE_TTL + 1

    # A write for an unrelated occupation must still collect the stale one.
    onet_client._occ_cache_set(occ("11-1021.00"), 3)

    assert occ("15-1252.00") not in onet_client._OCC_CACHE, (
        "an expired entry nobody re-read stayed resident -- this is the 2026-09-15 leak"
    )
    assert occ("11-1021.00") in onet_client._OCC_CACHE


def test_expired_occupation_entry_is_dropped_on_read_too(occ) -> None:
    """A reader that finds an expired entry removes it rather than hiding it.

    Returning None while leaving it resident is what turns a TTL into decoration.
    """
    onet_client._occ_cache_set(occ("15-1252.00"), 4)
    occ.clock["now"] += onet_client._OCC_CACHE_TTL + 1

    assert onet_client._occ_cache_get(occ("15-1252.00")) is None
    assert occ("15-1252.00") not in onet_client._OCC_CACHE


def test_occupation_cache_is_bounded_even_when_nothing_has_expired(occ) -> None:
    """The backstop: every entry live at once must still not grow without bound.

    4,000 writes is ~2x the cap and, at the measured ~6 KB per real entry, would
    be ~24 MB uncapped. Ints are stored rather than real payloads so the test
    costs nothing to run.
    """
    inserted = 4_000
    for i in range(inserted):
        onet_client._occ_cache_set(occ("15-%04d.00" % i), 4)

    # Behavioural assertion first, so a tree predating the fix fails on the
    # number rather than on an AttributeError for the new constant.
    assert len(onet_client._OCC_CACHE) < inserted
    assert len(onet_client._OCC_CACHE) <= onet_client._OCC_CACHE_MAX_ENTRIES
    assert occ("15-%04d.00" % (inserted - 1)) in onet_client._OCC_CACHE
    assert occ("15-0000.00") not in onet_client._OCC_CACHE
