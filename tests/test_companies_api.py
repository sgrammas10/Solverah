"""``GET /companies`` and ``GET /me/matches`` -- the two paginated lists.

``tests/test_pagination.py`` proves the keyset is correct in isolation. These
prove it survives the trip through HTTP: cursors that a client actually
round-trips, ordering that holds across pages, and the two behaviours the
endpoints these replace could not offer -- a company list at all, and reaching
past the fixed best/worst slices.
"""

import pytest

from solverah.schemas.matching import CompanyListResponse, MatchesResponse

EMAIL = "companies-api@example.com"
PASSWORD = "Strongpass1!"

CULTURE_PREFERENCES = {
    "empathy": 0.5, "creative_drive": 0.5, "adaptability": 0.5,
    "futuristic": 0.5, "harmony": 0.5, "data_orientation": 0.5,
    "pace": "fast", "work_environment": "collaborative",
}


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Co User",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def _seed_companies(count, industries=None, scoreable=True):
    """Insert *count* companies with distinct, ordered names."""
    from app import app
    from model import Company, db

    industries = industries or ["Tech"] * count
    with app.app_context():
        for i in range(count):
            culture = {}
            if scoreable:
                culture = {
                    "pace": "fast", "work_environment": "collaborative",
                    # A distinct empathy per row makes every fit_score distinct,
                    # so the sort is total and the cursor keys are unique.
                    "empathy": i / (count * 2), "creative_drive": 0.5,
                    "adaptability": 0.5, "futuristic": 0.5,
                    "harmony": 0.5, "data_orientation": 0.5,
                }
            db.session.add(Company(
                name="Company %02d" % i,
                slug="company-%02d" % i,
                profile_json={"overview": {"industry": industries[i]}},
                **culture,
            ))
        db.session.commit()


def _give_culture_preferences():
    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        profile = dict(user.profile_data or {})
        profile["culture_preferences"] = CULTURE_PREFERENCES
        user.profile_data = profile
        db.session.commit()


def _walk(client, path):
    """Page a list endpoint to exhaustion, returning every row and the page count."""
    rows, cursor, pages = [], None, 0
    while True:
        pages += 1
        assert pages < 50, "pagination did not terminate"
        url = path if cursor is None else "%s%scursor=%s" % (
            path, "&" if "?" in path else "?", cursor
        )
        body = client.get(url).get_json()
        rows.extend(body["data"])
        cursor = body["next_cursor"]
        if cursor is None:
            return rows, pages


# ── GET /companies ──────────────────────────────────────────────────────────


def test_company_list_matches_its_schema(client, auth):
    _seed_companies(3)

    resp = client.get("/api/v1/companies")

    assert resp.status_code == 200
    CompanyListResponse.model_validate(resp.get_json())


def test_paging_returns_every_company_exactly_once(client, auth):
    _seed_companies(7)

    rows, pages = _walk(client, "/api/v1/companies?limit=3")

    assert [r["name"] for r in rows] == ["Company %02d" % i for i in range(7)]
    assert pages == 3


def test_the_last_page_returns_a_null_cursor(client, auth):
    _seed_companies(2)

    body = client.get("/api/v1/companies?limit=10").get_json()

    assert len(body["data"]) == 2
    assert body["next_cursor"] is None


def test_an_empty_list_is_a_200_with_no_cursor(client, auth):
    body = client.get("/api/v1/companies").get_json()

    assert body["data"] == []
    assert body["next_cursor"] is None


def test_the_name_filter_narrows_the_list(client, auth):
    _seed_companies(5)

    body = client.get("/api/v1/companies?q=any 03").get_json()

    assert [r["name"] for r in body["data"]] == ["Company 03"]


def test_the_industry_filter_narrows_the_list(client, auth):
    _seed_companies(3, industries=["Tech", "Health", "Tech"])

    body = client.get("/api/v1/companies?industry=health").get_json()

    assert [r["name"] for r in body["data"]] == ["Company 01"]


def test_a_filter_survives_paging(client, auth):
    """The filter has to be reapplied on every page, not only the first."""
    _seed_companies(6, industries=["Tech", "Health"] * 3)

    rows, _pages = _walk(client, "/api/v1/companies?industry=Tech&limit=1")

    assert [r["name"] for r in rows] == ["Company 00", "Company 02", "Company 04"]


def test_a_forged_cursor_is_refused(client, auth):
    """A 422, not a silent page one -- see tests/test_pagination.py."""
    _seed_companies(3)

    resp = client.get("/api/v1/companies?cursor=not-a-real-cursor")

    assert resp.status_code == 422
    assert resp.mimetype == "application/problem+json"


def test_a_non_integer_limit_is_refused(client, auth):
    resp = client.get("/api/v1/companies?limit=abc")

    assert resp.status_code == 422


def test_the_company_list_requires_authentication(client):
    assert client.get("/api/v1/companies").status_code == 401


# ── GET /me/matches ─────────────────────────────────────────────────────────


def test_matches_matches_its_schema(client, auth):
    _seed_companies(3)
    _give_culture_preferences()

    resp = client.get("/api/v1/me/matches")

    assert resp.status_code == 200
    body = resp.get_json()
    MatchesResponse.model_validate(body)
    assert body["total_companies_scored"] == 3


def test_matches_are_ranked_best_first_by_default(client, auth):
    _seed_companies(5)
    _give_culture_preferences()

    body = client.get("/api/v1/me/matches").get_json()
    scores = [row["fit_score"] for row in body["data"]]

    assert scores == sorted(scores, reverse=True)


def test_order_worst_reverses_the_ranking(client, auth):
    """Carries over the `worst_fits` half of the endpoint this replaces."""
    _seed_companies(5)
    _give_culture_preferences()

    body = client.get("/api/v1/me/matches?order=worst").get_json()
    scores = [row["fit_score"] for row in body["data"]]

    assert scores == sorted(scores)


def test_paging_matches_returns_every_company_exactly_once(client, auth):
    """What the two fixed-size slices could not do: reach the middle of the list."""
    _seed_companies(7)
    _give_culture_preferences()

    rows, pages = _walk(client, "/api/v1/me/matches?limit=2")

    assert len({row["id"] for row in rows}) == 7
    assert pages == 4


def test_paged_matches_stay_in_rank_order_across_pages(client, auth):
    _seed_companies(6)
    _give_culture_preferences()

    rows, _pages = _walk(client, "/api/v1/me/matches?limit=2")
    scores = [row["fit_score"] for row in rows]

    assert scores == sorted(scores, reverse=True)


def test_matches_needs_culture_preferences(client, auth):
    _seed_companies(2)

    resp = client.get("/api/v1/me/matches")

    assert resp.status_code == 400


def test_an_unsupported_lens_is_refused(client, auth):
    """Declared rather than assumed, so adding a lens is a branch, not an endpoint."""
    _give_culture_preferences()

    resp = client.get("/api/v1/me/matches?lens=salary")

    assert resp.status_code == 400


def test_an_unsupported_order_is_refused(client, auth):
    _give_culture_preferences()

    assert client.get("/api/v1/me/matches?order=sideways").status_code == 400


def test_matches_requires_authentication(client):
    assert client.get("/api/v1/me/matches").status_code == 401
