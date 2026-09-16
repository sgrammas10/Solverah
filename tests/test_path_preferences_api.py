"""Tests for POST /api/intelligence/path-preferences."""
import pytest


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_path_suggestions_api.py)
# ---------------------------------------------------------------------------

def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="prefs@example.com", password="Strongpass1!"):
    import app as app_module
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Prefs User", "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


VALID_PREFS = {
    "move_intent": "adjacent",
    "seniority_intent": "move_up",
    "priority": "learning_growth",
}


@pytest.fixture(autouse=True)
def clear_path_cache():
    from solverah.services import path_cache
    path_cache.clear()
    yield
    path_cache.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_unauthenticated_returns_401(client):
    resp = client.put("/api/v1/me/path-preferences", json=VALID_PREFS)
    assert resp.status_code == 401


def test_happy_path_returns_200(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    resp = client.put(
        "/api/v1/me/path-preferences",
        json=VALID_PREFS,
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    # The saved document comes back, not `{"message": "Preferences saved"}`.
    # The endpoint this replaced was write-only, so a client that wanted to show
    # the user their own answers had to keep a copy or dig them out of the
    # profile blob -- which is the coupling to profile_data's shape that putting
    # schemas at the API boundary exists to stop.
    assert resp.get_json() == VALID_PREFS


def test_preferences_persisted_in_the_profile_document(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    client.put(
        "/api/v1/me/path-preferences",
        json=VALID_PREFS,
        headers={"X-CSRF-TOKEN": csrf},
    )

    from app import app
    from model import User
    from solverah.repositories import profile_repository
    from solverah.services import path_cache
    with app.app_context():
        user = User.query.filter_by(email="prefs@example.com").first()
        prefs = profile_repository.load_document(user.id).get("path_preferences")
    assert prefs == VALID_PREFS


def test_invalid_move_intent_returns_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    resp = client.put(
        "/api/v1/me/path-preferences",
        json={**VALID_PREFS, "move_intent": "sideways"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400
    assert "move_intent" in resp.get_json()["error"]


def test_invalid_seniority_intent_returns_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    resp = client.put(
        "/api/v1/me/path-preferences",
        json={**VALID_PREFS, "seniority_intent": "unknown"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400
    assert "seniority_intent" in resp.get_json()["error"]


def test_invalid_priority_returns_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    resp = client.put(
        "/api/v1/me/path-preferences",
        json={**VALID_PREFS, "priority": "vibes"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 400
    assert "priority" in resp.get_json()["error"]


def test_missing_field_returns_422(client, monkeypatch):
    """422 since Phase 1b: an absent field is a schema violation.

    A *present but unrecognised* value is still 400 -- that is a business rule
    about which values the path scorer branches on, and the three tests above
    cover it. The two failures were one status before and are now told apart.
    """
    csrf = _register_and_login(client, monkeypatch)
    resp = client.put(
        "/api/v1/me/path-preferences",
        json={"seniority_intent": "move_up", "priority": "pay_title"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 422
    assert "move_intent" in {error["field"] for error in resp.get_json()["errors"]}


def test_save_preferences_invalidates_path_cache(client, monkeypatch):
    import app as app_module

    csrf = _register_and_login(client, monkeypatch)

    # Seed a fake cache entry for this user
    from app import app
    from model import User
    from solverah.services import path_cache
    with app.app_context():
        user = User.query.filter_by(email="prefs@example.com").first()
        path_cache.store(user.id, {"suggestions": [], "career_status": "employed", "generated_at": "2026-01-01T00:00:00Z"})
        user_id = user.id

    assert user_id in path_cache.snapshot()

    client.put(
        "/api/v1/me/path-preferences",
        json=VALID_PREFS,
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert user_id not in path_cache.snapshot()


# ---------------------------------------------------------------------------
# The invalidation enumeration (extended for BUILD_PLAN F-5)
# ---------------------------------------------------------------------------
#
# `path_cache`'s docstring names this file as the place its call sites are
# enumerated "rather than left to review", because missing one does not fail
# loudly -- it serves a stale suggestion. F-5 added a second thing to invalidate
# on the same writes (the stored Tier-2 deep fits in `path_fits`), and a second
# enumeration maintained by hand would drift from the first the moment somebody
# added a seventh write site and remembered only one of them.
#
# So the enumeration below is not a list of sites. It is the *rule*: wherever
# `path_cache.invalidate` is called, `path_fit_repository.invalidate` is called
# too. Adding a write site that invalidates one and not the other fails here
# whether or not anyone thought to update this file.


def _service_sources():
    """Every module under `solverah/` that invalidates path state, as text."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "solverah"
    return {
        path.relative_to(root.parent).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*.py")
        if "path_cache.invalidate(" in path.read_text(encoding="utf-8")
    }


#: The six sites as they stand. Not the assertion -- `_service_sources()` is --
#: but a floor, so a scan that silently stopped matching cannot pass by finding
#: nothing. Raise it when a seventh write site is added.
_KNOWN_INVALIDATION_SITES = 6


def test_every_path_cache_invalidation_also_drops_the_stored_deep_fits():
    sources = _service_sources()
    assert sources, "the scan found no invalidation sites at all"

    problems = []
    total = 0
    for name, text in sources.items():
        cache_calls = text.count("path_cache.invalidate(")
        fit_calls = text.count("path_fit_repository.invalidate(")
        total += cache_calls
        if cache_calls != fit_calls:
            problems.append(
                "%s: %d path_cache.invalidate call(s) but %d "
                "path_fit_repository.invalidate call(s)" % (name, cache_calls, fit_calls)
            )

    assert not problems, (
        "A write that changes a path-scoring input must drop BOTH the Tier-1 "
        "suggestion cache and the Tier-2 stored fits (BUILD_PLAN F-5). "
        + "; ".join(problems)
    )
    assert total >= _KNOWN_INVALIDATION_SITES, (
        "the scan saw %d invalidation sites, fewer than the %d known to exist -- "
        "it has stopped matching, not found a deletion"
        % (total, _KNOWN_INVALIDATION_SITES)
    )


def test_the_three_services_that_invalidate_are_the_ones_expected():
    """A new module invalidating path state is a review moment, not a silent fact.

    The rule above is enforced per file, so a *new* file gets it for free -- but
    only if somebody noticed the file exists. This is where they notice.
    """
    assert set(_service_sources()) == {
        "solverah/services/assessment_service.py",
        "solverah/services/intelligence_service.py",
        "solverah/services/profile_service.py",
    }


def test_save_preferences_drops_the_stored_deep_fits(client, monkeypatch):
    """The rule proved as behaviour on one site, not only as a source scan.

    A scan cannot see a call that is made but never reached -- inside a branch
    that is always false, or after an early return. One end-to-end case per
    mechanism is what stops the scan from being the only evidence.
    """
    csrf = _register_and_login(client, monkeypatch, email="fits@example.com")

    from app import app
    from model import PathFit, User, db
    from solverah.repositories import path_fit_repository

    with app.app_context():
        user = User.query.filter_by(email="fits@example.com").first()
        user_id = user.id
        path_fit_repository.store(
            user_id, "15-1252.00", {"fit_score": 0.5}, "f" * 64
        )
        db.session.commit()
        assert PathFit.query.filter_by(user_id=user_id).count() == 1

    client.put(
        "/api/v1/me/path-preferences",
        json=VALID_PREFS,
        headers={"X-CSRF-TOKEN": csrf},
    )

    with app.app_context():
        assert PathFit.query.filter_by(user_id=user_id).count() == 0
