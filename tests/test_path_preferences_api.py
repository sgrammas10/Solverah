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


#: The seven sites as they stand. Not the assertion -- `_service_sources()` is
#: -- but a floor, so a scan that silently stopped matching cannot pass by
#: finding nothing. Raise it when an eighth write site is added.
#:
#: Six until F-8 box 6, which found the seventh: `set_career_status` invalidated
#: neither cache. The rule above could not catch it, because the rule is "a site
#: that drops one must drop the other" and that site dropped neither -- the scan
#: only looks at files that already call `path_cache.invalidate`, so a write
#: which forgot both was invisible to it by construction. This floor is what
#: catches the next one: a site that goes missing takes the count down with it.
#:
#: Seven until W-4, which added the eighth: `path_wants_service.save_path_wants`.
#: A stated want changes the ranking every later request computes, so the cached
#: shortlist is wrong the moment one lands -- unlike F-6's card judgements, which
#: invalidate neither because the re-rank writes its own result straight into the
#: cache. The stored deep fits go with it on the rule rather than on a claim that
#: a fit's numbers moved: wants are not in `path_fit_repository.fingerprint`, and
#: dropping them costs a recomputation and never a wrong answer.
_KNOWN_INVALIDATION_SITES = 8


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


def test_the_services_that_invalidate_are_the_ones_expected():
    """A new module invalidating path state is a review moment, not a silent fact.

    The rule above is enforced per file, so a *new* file gets it for free -- but
    only if somebody noticed the file exists. This is where they notice, and W-4
    is the first time it has fired: `path_wants_service` is the fourth module,
    and it is here because a stated want changes the ranking rather than because
    it changes the profile.
    """
    assert set(_service_sources()) == {
        "solverah/services/assessment_service.py",
        "solverah/services/intelligence_service.py",
        "solverah/services/path_wants_service.py",
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


# ---------------------------------------------------------------------------
# F-8 box 6 -- the seventh write site
# ---------------------------------------------------------------------------
#
# `career_status` is a path-scoring INPUT and not a label. It selects the
# weight row (`path_scoring._WEIGHT_SPLITS`), it decides whether a title is
# read off the experience list at all (`build_user_profile` skips it for
# `first_job`), and it feeds the Job Zone floor. `set_career_status` dropped
# neither cache, so a user who corrected "employed" to "between_jobs" kept
# being served the answers to the question they had just changed.
#
# The RULE test above could not have caught this. It scans files that already
# call `path_cache.invalidate` and checks that each such call has a matching
# `path_fit_repository.invalidate` -- so a write site that forgot BOTH is
# invisible to it by construction. The floor is what closes that, and these two
# are the behaviour behind it.


def test_setting_career_status_invalidates_the_suggestion_cache(client, monkeypatch):
    """The regression. Fails without the fix, on the shape a user would hit."""
    csrf = _register_and_login(client, monkeypatch, email="status@example.com")

    from app import app
    from model import User
    from solverah.services import path_cache

    with app.app_context():
        user_id = User.query.filter_by(email="status@example.com").first().id
        path_cache.store(
            user_id,
            {
                "suggestions": [],
                "career_status": "employed",
                "generated_at": "2026-01-01T00:00:00Z",
            },
        )

    assert user_id in path_cache.snapshot()

    resp = client.patch(
        "/api/v1/me/career-status",
        json={"status": "between_jobs"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 200, resp.get_json()
    assert user_id not in path_cache.snapshot(), (
        "the suggestions still answer the career_status the user just changed"
    )


def test_setting_career_status_drops_the_stored_deep_fits(client, monkeypatch):
    """Tier 2 as well, even though Tier 2 would have self-corrected.

    `path_fits` carries a profile fingerprint and would have noticed on the next
    read, so only Tier 1 actually served stale results. Both are dropped anyway:
    "one of the two happens to be self-healing" is not a rule anybody can hold
    in their head, and the enumeration above is built on the two moving
    together.
    """
    csrf = _register_and_login(client, monkeypatch, email="statusfits@example.com")

    from app import app
    from model import PathFit, User, db
    from solverah.repositories import path_fit_repository

    with app.app_context():
        user_id = User.query.filter_by(email="statusfits@example.com").first().id
        path_fit_repository.store(user_id, "15-1252.00", {"fit_score": 0.5}, "f" * 64)
        db.session.commit()
        assert PathFit.query.filter_by(user_id=user_id).count() == 1

    client.patch(
        "/api/v1/me/career-status",
        json={"status": "first_job"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    with app.app_context():
        assert PathFit.query.filter_by(user_id=user_id).count() == 0


def test_a_rejected_career_status_invalidates_nothing(client, monkeypatch):
    """An invalid status changes no input, so it must not cost a cache.

    The invalidation sits after the validation guard, and this is what keeps it
    there: throwing away a warm cache on a request that wrote nothing is a free
    latency regression nobody would trace back to here.
    """
    csrf = _register_and_login(client, monkeypatch, email="badstatus@example.com")

    from app import app
    from model import User
    from solverah.services import path_cache

    with app.app_context():
        user_id = User.query.filter_by(email="badstatus@example.com").first().id
        path_cache.store(user_id, {"suggestions": [], "career_status": "employed"})

    resp = client.patch(
        "/api/v1/me/career-status",
        json={"status": "retired-to-a-vineyard"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 400
    assert user_id in path_cache.snapshot()
