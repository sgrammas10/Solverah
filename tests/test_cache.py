"""The Redis read cache: inert without Redis, and never wrong with it.

Two properties, and the first one is the one CI depends on.

**Without Redis, nothing changes.**  The runner sets five environment variables
and has no Redis service container, so every function in
``solverah.infra.cache`` has to answer "miss" rather than raise.  Most of this
suite proves that implicitly by passing; the tests here prove it on purpose,
because "the cache silently stopped working" and "the cache is correctly absent"
look identical from the outside and only one of them is fine in production.

**With Redis, a cached response is byte-identical to an uncached one.**  This is
the failure that no ordinary endpoint test would catch: the second read serves
a payload that went through ``json.dumps``/``json.loads``, and any value that
does not survive that round trip -- a tuple that became a list, a datetime that
became a string, a key that moved -- is a contract change nobody asked for.
``Scripts/verify_contract.py`` is the other half of this, run with ``REDIS_URL``
set so the second of each pair of reads in its scenario comes from the cache.

The client here is a fake rather than a real Redis, deliberately.  A test that
needs a container is a test that gets skipped on the runner, and what is being
checked -- the round trip, the key, and *when* the delete happens -- is not
Redis behaviour.  ``tests/test_rate_limit_storage.py`` makes the same call about
the limiter's backend.
"""

import pytest


class FakeRedis:
    """Enough Redis for this module: get, setex, delete, ping.

    Records every operation so a test can assert on *ordering* -- specifically
    that an invalidation lands after the commit and not before it, which is the
    difference between a cache that self-heals and one that a concurrent reader
    can repopulate with pre-write state.
    """

    def __init__(self):
        self.store = {}
        self.ops = []

    def ping(self):
        return True

    def get(self, key):
        self.ops.append(("get", key))
        return self.store.get(key)

    def setex(self, key, _ttl, value):
        self.ops.append(("setex", key))
        self.store[key] = value

    def delete(self, *keys):
        self.ops.append(("delete", tuple(keys)))
        for key in keys:
            self.store.pop(key, None)


@pytest.fixture()
def fake_cache(monkeypatch):
    """Install a FakeRedis as the cache backend for one test."""
    from solverah.infra import cache

    fake = FakeRedis()
    cache.clear_client()
    monkeypatch.setattr(cache, "_url", "redis://fake")
    monkeypatch.setattr(cache, "_client", fake)
    monkeypatch.setattr(cache, "_client_resolved", True)
    yield fake
    cache.clear_client()


# ── Absent backend ──────────────────────────────────────────────────────────


def test_without_redis_every_operation_is_a_no_op(client):
    """What CI runs. A miss, a silent store, a silent delete -- never an error."""
    from solverah.infra import cache

    assert cache.is_enabled() is False
    assert cache.get_json("solverah:v1:nothing") is None
    assert cache.set_json("solverah:v1:nothing", {"a": 1}) is False
    cache.delete("solverah:v1:nothing")  # must not raise


def test_an_unreachable_backend_degrades_to_no_cache(monkeypatch):
    """A Redis that is configured but down makes reads slower, never wrong.

    The alternative -- letting the connection error out of ``get_json`` -- would
    turn a cache outage into a 500 on every cached endpoint, which is strictly
    worse than not having a cache.
    """
    from solverah.infra import cache

    class _Dead:
        def ping(self):
            raise OSError("connection refused")

    monkeypatch.setattr(cache, "_url", "redis://unreachable")
    cache.clear_client()
    monkeypatch.setattr(
        "redis.Redis.from_url", lambda *_a, **_k: _Dead(), raising=False
    )

    try:
        assert cache.is_enabled() is False
        assert cache.get_json("solverah:v1:x") is None
    finally:
        cache.clear_client()


# ── Round trip ──────────────────────────────────────────────────────────────


def test_a_cached_value_survives_the_round_trip_unchanged(client, fake_cache):
    from solverah.infra import cache

    payload = {
        "id": 7,
        "name": "Acme",
        "profile": {"overview": {"industry": "Testing"}, "score": 0.75},
        "flag": True,
        "missing": None,
        "list": [1, 2, 3],
    }

    cache.set_json("solverah:v1:round-trip", payload)

    assert cache.get_json("solverah:v1:round-trip") == payload


def test_an_undecodable_value_is_a_miss_and_is_dropped(client, fake_cache):
    """A stored value that will not decode can only be a previous payload shape.

    Serving it would put a body on the wire the current schema never produced,
    so it is treated as a miss and deleted rather than returned or raised on.
    """
    from solverah.infra import cache

    fake_cache.store["solverah:v1:corrupt"] = "{not json"

    assert cache.get_json("solverah:v1:corrupt") is None
    assert "solverah:v1:corrupt" not in fake_cache.store


def test_a_value_that_will_not_serialise_is_dropped_not_raised(client, fake_cache):
    """Caching is an optimisation; a response must not fail because of it."""
    from solverah.infra import cache

    assert cache.set_json("solverah:v1:bad", {"when": object()}) is False
    assert "solverah:v1:bad" not in fake_cache.store


# ── Invalidation, and when it happens ───────────────────────────────────────


def test_invalidation_waits_for_the_commit(client, fake_cache):
    """The ordering property. Dropping the key early is a stale-cache generator.

    A writer that deletes before committing leaves a window in which a concurrent
    reader repopulates the key from the pre-write row -- stale until the TTL, and
    caused by the very write meant to clear it.
    """
    from model import db
    from solverah.infra import cache

    key = cache.dashboard_key(1)
    fake_cache.store[key] = '{"stale": true}'

    with client.application.app_context():
        cache.invalidate_on_commit(key)
        assert key in fake_cache.store, "dropped before the commit"

        db.session.commit()
        assert key not in fake_cache.store


def test_a_rolled_back_write_invalidates_nothing(client, fake_cache):
    """Nothing changed, so nothing cached is stale."""
    from model import db
    from solverah.infra import cache

    key = cache.dashboard_key(2)
    fake_cache.store[key] = '{"fresh": true}'

    with client.application.app_context():
        cache.invalidate_on_commit(key)
        db.session.rollback()
        assert key in fake_cache.store


# ── The two cached reads ────────────────────────────────────────────────────


def test_company_detail_is_served_from_the_cache_on_the_second_read(client, fake_cache):
    """And the two responses are the same object, key for key.

    The second call is answered without touching ``company_repository`` at all --
    forced here by deleting the row between the two reads, which is the only way
    to prove the handler was skipped rather than merely fast.
    """
    from model import Company, db
    from solverah.services import matching_service

    with client.application.app_context():
        company = Company(
            name="Cache Industries",
            slug="cache-industries",
            profile_json={"overview": {"name": "Cache Industries"}},
        )
        db.session.add(company)
        db.session.commit()
        company_id = company.id

        first = matching_service.company_detail(company_id)
        assert first.status == 200

        db.session.delete(db.session.get(Company, company_id))
        db.session.commit()

        second = matching_service.company_detail(company_id)

    assert second.status == 200
    assert second.body == first.body


def test_writing_a_company_drops_its_cached_detail(client, fake_cache):
    """``upsert_company`` is the only writer, so it is the only invalidator."""
    from model import Company, db
    from solverah.infra import cache
    from solverah.repositories import company_repository
    from solverah.services import matching_service

    with client.application.app_context():
        company = Company(
            name="Invalidate Industries",
            slug="invalidate-industries",
            profile_json={"overview": {"name": "Invalidate Industries"}},
        )
        db.session.add(company)
        db.session.commit()
        company_id = company.id

        matching_service.company_detail(company_id)
        assert cache.company_detail_key(company_id) in fake_cache.store

        company_repository.upsert_company(
            _profile_named("Invalidate Industries", "Renamed sector")
        )

        assert cache.company_detail_key(company_id) not in fake_cache.store
        refreshed = matching_service.company_detail(company_id)

    assert refreshed.body["profile"]["overview"]["industry"] == "Renamed sector"


def test_a_profile_write_drops_the_cached_dashboard(client, fake_cache):
    """Registered inside ``update_document`` -- the one profile write path.

    At each of its dozen callers instead, this would be an invalidation somebody
    eventually forgets, and the symptom is a stale number nobody reports.
    """
    from model import User, db
    from solverah.infra import cache
    from solverah.repositories import profile_repository
    from solverah.services import profile_service

    with client.application.app_context():
        user = User(email="cache-dash@example.test", password_hash="not-a-real-hash")
        db.session.add(user)
        db.session.commit()

        profile_service.dashboard_data(user, user.email)
        assert cache.dashboard_key(user.id) in fake_cache.store

        profile_repository.update_document(
            user.id, lambda existing: {**existing, "summary": "changed"}
        )
        db.session.commit()

        assert cache.dashboard_key(user.id) not in fake_cache.store


def _profile_named(name, industry):
    """A minimal valid ``CompanyProfile`` for the upsert path."""
    from packages.ml.culture import CompanyProfile

    return CompanyProfile.model_validate(
        {"overview": {"name": name, "industry": industry}}
    )
