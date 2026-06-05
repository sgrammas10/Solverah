"""Tests for GET /api/company-lens/matches."""

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
    import app as app_module
    monkeypatch.setattr(app_module, "send_confirmation_email", _noop)
    monkeypatch.setattr(app_module, "log_audit_event", _noop)

    client.post("/api/register", json={"email": email, "password": password, "name": "Lens User"})

    from app import app
    from model import User, db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def _set_culture_prefs(email, prefs):
    from app import app
    from model import User, db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile = dict(user.profile_data or {})
        profile["culture_preferences"] = prefs
        user.profile_data = profile
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

def test_matches_returns_best_and_worst(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _set_culture_prefs("lens@example.com", USER_PREFS)
    _seed_companies(10)

    resp = client.get("/api/company-lens/matches?limit=3")
    assert resp.status_code == 200
    body = resp.get_json()

    assert "best_fits" in body
    assert "worst_fits" in body
    assert body["total_companies_scored"] == 10
    assert body["limit"] == 3
    assert len(body["best_fits"]) == 3
    assert len(body["worst_fits"]) == 3


def test_matches_response_shape(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="shape@example.com")
    _set_culture_prefs("shape@example.com", USER_PREFS)
    _seed_companies(6)

    resp = client.get("/api/company-lens/matches?limit=2")
    assert resp.status_code == 200
    body = resp.get_json()

    for entry in body["best_fits"] + body["worst_fits"]:
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

    resp = client.get("/api/company-lens/matches?limit=5")
    body = resp.get_json()

    scores = [e["fit_score"] for e in body["best_fits"]]
    assert scores == sorted(scores, reverse=True), "best_fits must be sorted by fit_score descending"


# ── limit param ───────────────────────────────────────────────────────────────

def test_limit_3_returns_3_in_each_group(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="limit3@example.com")
    _set_culture_prefs("limit3@example.com", USER_PREFS)
    _seed_companies(10)

    resp = client.get("/api/company-lens/matches?limit=3")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["best_fits"]) == 3
    assert len(body["worst_fits"]) == 3
    assert body["limit"] == 3


def test_default_limit_is_5(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="deflimit@example.com")
    _set_culture_prefs("deflimit@example.com", USER_PREFS)
    _seed_companies(12)

    resp = client.get("/api/company-lens/matches")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["limit"] == 5
    assert len(body["best_fits"]) == 5
    assert len(body["worst_fits"]) == 5


# ── Missing culture_preferences ───────────────────────────────────────────────

def test_missing_culture_preferences_returns_400(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="noprefs@example.com")
    # Do not set culture_preferences

    resp = client.get("/api/company-lens/matches")
    assert resp.status_code == 400
    assert "culture preferences" in resp.get_json()["error"].lower()


# ── Fewer companies than 2*limit ──────────────────────────────────────────────

def test_no_company_in_both_lists_when_few_companies(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="few@example.com")
    _set_culture_prefs("few@example.com", USER_PREFS)
    _seed_companies(3)  # fewer than 2*5=10

    resp = client.get("/api/company-lens/matches?limit=5")
    assert resp.status_code == 200
    body = resp.get_json()

    best_ids = {e["id"] for e in body["best_fits"]}
    worst_ids = {e["id"] for e in body["worst_fits"]}
    assert best_ids.isdisjoint(worst_ids), "No company should appear in both best_fits and worst_fits"


def test_total_companies_scored_reflects_all_valid_companies(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="total@example.com")
    _set_culture_prefs("total@example.com", USER_PREFS)
    _seed_companies(4)

    resp = client.get("/api/company-lens/matches?limit=5")
    body = resp.get_json()
    assert body["total_companies_scored"] == 4


# ── Unauthenticated ───────────────────────────────────────────────────────────

def test_unauthenticated_returns_401(client):
    resp = client.get("/api/company-lens/matches")
    assert resp.status_code == 401
