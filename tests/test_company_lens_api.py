"""Tests for GET /api/v1/me/matches.

Phase 1b replaced `GET /company-lens/matches`, which returned two fixed-size
slices -- `best_fits` and `worst_fits` -- in a single body and could show
nothing past them. The replacement is a cursor-paginated ranking that `?order=`
reads from either end, so both halves are still reachable and either can be
walked as deep as the caller wants.

One guarantee did not survive the change and its replacement is documented
below: the old endpoint partitioned at the midpoint so a company could never
appear in both slices. A paginated ranking cannot do that, and the
de-duplication moved to the screen that renders both ends at once.
"""

import pytest


USER_PREFS = {
    "empathy": 0.8,
    "creative_drive": 0.7,
    "adaptability": 0.6,
    "futuristic": 0.9,
    "harmony": 0.5,
    "data_orientation": 0.4,
    "pace": "fast",
    "work_environment": "collaborative",
}


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="lens@example.com", password="Strongpass1!"):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": "Lens User", "terms_accepted": True})

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


def _set_culture_prefs(email, prefs):
    from app import app
    from model import User, db
    from solverah.repositories import profile_repository
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile_repository.update_document(
            user.id, lambda existing: {**existing, "culture_preferences": prefs}
        )
        db.session.commit()


def _seed_companies(count):
    """Seed `count` companies with distinct culture profiles (pace always 'fast')."""
    from app import app
    from model import Company, db
    with app.app_context():
        for i in range(count):
            # Spread empathy linearly so scores differ meaningfully
            empathy = round((i + 1) / count, 3)
            company = Company(
                name=f"TestCo {i}",
                slug=f"testco-{i}",
                profile_json={"overview": {"name": f"TestCo {i}", "industry": f"Industry {i}"}},
                work_environment="collaborative",
                pace="fast",
                empathy=empathy,
                creative_drive=0.5,
                adaptability=0.5,
                futuristic=0.5,
                harmony=0.5,
                data_orientation=0.5,
            )
            db.session.add(company)
        db.session.commit()


# ── Happy path ────────────────────────────────────────────────────────────────

def test_matches_returns_both_ends_of_the_ranking(client, monkeypatch):
    """Two directions through one list, where there used to be two slices."""
    csrf = _register_and_login(client, monkeypatch)
    _set_culture_prefs("lens@example.com", USER_PREFS)
    _seed_companies(10)

    best = client.get("/api/v1/me/matches?order=best&limit=3")
    worst = client.get("/api/v1/me/matches?order=worst&limit=3")

    assert best.status_code == 200
    assert worst.status_code == 200
    assert best.get_json()["total_companies_scored"] == 10
    assert len(best.get_json()["data"]) == 3
    assert len(worst.get_json()["data"]) == 3
    # There is more past the first page, unlike the endpoint this replaced.
    assert best.get_json()["next_cursor"] is not None


def test_matches_response_shape(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="shape@example.com")
    _set_culture_prefs("shape@example.com", USER_PREFS)
    _seed_companies(6)

    best = client.get("/api/v1/me/matches?order=best&limit=2").get_json()
    worst = client.get("/api/v1/me/matches?order=worst&limit=2").get_json()

    for entry in best["data"] + worst["data"]:
        assert "id" in entry
        assert "name" in entry
        assert "slug" in entry
        assert "industry" in entry
        assert "fit_score" in entry
        assert isinstance(entry["fit_score"], float)
        assert "top_matching_dimensions" in entry
        assert isinstance(entry["top_matching_dimensions"], list)
        assert "top_mismatching_dimensions" in entry
        assert isinstance(entry["top_mismatching_dimensions"], list)
        assert "fit_summary" in entry
        assert isinstance(entry["fit_summary"], str) and len(entry["fit_summary"]) > 0


def test_matches_best_fits_sorted_descending(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="sort@example.com")
    _set_culture_prefs("sort@example.com", USER_PREFS)
    _seed_companies(10)

    resp = client.get("/api/v1/me/matches?order=best&limit=5")
    body = resp.get_json()

    scores = [e["fit_score"] for e in body["data"]]
    assert scores == sorted(scores, reverse=True), "order=best must rank strongest fit first"


# ── limit param ───────────────────────────────────────────────────────────────

def test_limit_bounds_the_page(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="limit3@example.com")
    _set_culture_prefs("limit3@example.com", USER_PREFS)
    _seed_companies(10)

    resp = client.get("/api/v1/me/matches?order=best&limit=3")

    assert resp.status_code == 200
    assert len(resp.get_json()["data"]) == 3


def test_an_absent_limit_takes_the_pagination_default(client, monkeypatch):
    """The default moved from 5 to the shared pagination default.

    5 was "how many fit in each of two lists on one screen" -- a layout decision
    that had leaked into the API. A paginated list's default is a page size, and
    it is now the same one every list in this API uses.
    """
    csrf = _register_and_login(client, monkeypatch, email="deflimit@example.com")
    _set_culture_prefs("deflimit@example.com", USER_PREFS)
    _seed_companies(12)

    resp = client.get("/api/v1/me/matches")

    assert resp.status_code == 200
    # All 12 fit inside one default-sized page, so there is no second one.
    assert len(resp.get_json()["data"]) == 12
    assert resp.get_json()["next_cursor"] is None


# ── Missing culture_preferences ───────────────────────────────────────────────

def test_missing_culture_preferences_returns_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="noprefs@example.com")
    # Do not set culture_preferences

    resp = client.get("/api/v1/me/matches")
    assert resp.status_code == 400
    assert "culture preferences" in resp.get_json()["error"].lower()


# ── Fewer companies than 2*limit ──────────────────────────────────────────────

def test_the_two_orders_are_one_ranking_read_from_both_ends(client, monkeypatch):
    """Where the old "never in both lists" guarantee went.

    The endpoint this replaced partitioned at the midpoint when there were few
    companies, so one could not appear in both slices. A paginated ranking
    cannot do that -- it walks a list, it does not carve one -- so with few
    companies the two orders genuinely overlap, and they are the same ranking
    reversed.

    The de-duplication moved to the screen that renders both ends at once
    (src/pages/CompanyLensPage.tsx), which is where a presentation decision
    belongs. Asserted here is the property the API does guarantee.
    """
    csrf = _register_and_login(client, monkeypatch, email="few@example.com")
    _set_culture_prefs("few@example.com", USER_PREFS)
    _seed_companies(3)

    best = client.get("/api/v1/me/matches?order=best&limit=5").get_json()["data"]
    worst = client.get("/api/v1/me/matches?order=worst&limit=5").get_json()["data"]

    assert [e["id"] for e in worst] == [e["id"] for e in reversed(best)]


def test_total_companies_scored_reflects_all_valid_companies(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="total@example.com")
    _set_culture_prefs("total@example.com", USER_PREFS)
    _seed_companies(4)

    resp = client.get("/api/v1/me/matches?limit=5")
    body = resp.get_json()
    assert body["total_companies_scored"] == 4


# ── Unauthenticated ───────────────────────────────────────────────────────────

def test_unauthenticated_returns_401(client):
    resp = client.get("/api/v1/me/matches")
    assert resp.status_code == 401
