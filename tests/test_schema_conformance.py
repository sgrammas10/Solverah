"""Real handler responses validate against their declared pydantic models.

This is what stops the Phase 1a schemas from being decoration. They are
descriptive, not enforced at runtime -- nothing rejects a request or reshapes a
response -- so the only thing keeping them honest is a test that pushes an
actual response through the actual model. Without it, `docs/openapi.json` is a
document about an API that may or may not exist, and the typed client generated
from it in Phase 4 would be wrong in ways the compiler would happily accept.

Covered here: the endpoints reachable without stubbing an LLM provider. The
LLM-backed ones (quiz insights, Work Pulse, ManagerMatch, the agent) already have
provider-stubbed tests of their own in test_work_pulse_submit.py,
test_manager_match_api.py, test_wpll_result.py, and test_agent_api.py; this file
asserts the schema side for the rest and for the two response envelopes those
share.
"""

import pytest

from solverah.schemas import ProblemDetailResponse
from solverah.schemas.assessments import AssessmentFormResponse
from solverah.schemas.auth import (
    LoginResponse,
    LogoutResponse,
    MessageResponse,
    RegisterResponse,
)
from solverah.schemas.intelligence import RecommendationsPage
from solverah.schemas.matching import CompanyDetailResponse, MatchesResponse
from solverah.schemas.profile import (
    CareerStatusResponse,
    DashboardResponse,
    ProfileDocument,
    SkillsResponse,
)

EMAIL = "conformance@example.com"
PASSWORD = "Strongpass1!"

#: Same literal the other person-side tests use. The secret has no default by
#: design (D-05): `respondent_id_for_user` raises rather than falling back,
#: because a default would make respondent ids -- and therefore the item-token
#: salt and the shuffle seed -- identical across every deployment that forgot to
#: set it.
FORM_TOKEN_SECRET = "test-secret-not-a-real-one"


#: What the six-trait read needs on the person side: six core scores. Placed
#: through the `assessment_store` doorway rather than by sitting the instrument,
#: which is how tests/test_company_lens_api.py does it too -- the read never
#: looks past that function, and a sitting here would be forty-odd answers for
#: one dict.
CORE_SCORES = {
    "autonomy": 0.5, "pace": 0.5, "collaboration": 0.5,
    "feedback": 0.5, "innovation": 0.5, "decision": 0.5,
}


def _place_person(monkeypatch):
    import assessment_store

    monkeypatch.setattr(
        assessment_store, "get_dimension_scores", lambda _user_id: dict(CORE_SCORES)
    )


def _researched_company(name, slug):
    """A company `GET /me/matches` lists: one shared trait record is enough to be
    listed (`not_enough_evidence`, after the ranked ones). Written through the
    store, the way the research pipeline writes, so a rewrite of that path that
    stopped listing such a company fails here. Inside an app context."""
    import company_evidence_store as store
    from model import Company, db

    company = Company(name=name, slug=slug, profile_json={"overview": {}})
    db.session.add(company)
    db.session.commit()
    run = store.start_research_run(
        db, company.id, trigger="on_demand", provider="anthropic",
        model="test-model", prompt_version="r1",
    )
    store.write_trait_records(
        db, company.id,
        [store.TraitRecordInput(dimension_key="autonomy", scope="company", status="unknown")],
        aggregation_version="agg-test",
    )
    store.finish_research_run(db, run.id, status="done", cost_usd=0)
    return company.id


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    """Supply the person-side form secret for every test in this module.

    Autouse rather than per-test: it is read at call time inside
    `assessment_store.respondent_id_for_user`, so any test that reaches an
    assessment route needs it, and forgetting it produces a 500 that looks like
    a handler bug rather than a missing variable.

    This fixture is why the module is safe to run with no `.env` present, which
    is how CI runs it -- `app.py` calls `load_dotenv()`, so a developer with a
    populated `.env` gets this variable for free and cannot tell the difference.
    """
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", FORM_TOKEN_SECRET)


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in client plus its CSRF token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Conformance User",
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


# ── Auth ────────────────────────────────────────────────────────────────────


def test_register_response_matches_schema(client, monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "reg-schema@example.com", "password": PASSWORD,
              "name": "Reg Schema", "terms_accepted": True},
    )

    assert resp.status_code == 201
    RegisterResponse.model_validate(resp.get_json())


def test_login_response_matches_schema(client, auth):
    resp = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

    assert resp.status_code == 200
    LoginResponse.model_validate(resp.get_json())


def test_logout_response_matches_schema(client, auth):
    resp = client.post("/api/v1/auth/logout")

    assert resp.status_code == 200
    LogoutResponse.model_validate(resp.get_json())


def test_a_schema_failure_is_a_problem_document(client):
    """An empty body fails the schema, so it answers in the RFC 9457 shape.

    Phase 1a had this returning the handler's own `{"error": ...}` on a 400,
    because the schemas were descriptive and the handler did the checking.
    Enforcing them moved this particular failure in front of the handler.
    """
    resp = client.post("/api/v1/auth/email/verify", json={})

    assert resp.status_code == 422
    assert resp.mimetype == "application/problem+json"
    assert {error["field"] for error in resp.get_json()["errors"]} == {"email", "code"}


def test_a_handler_raised_error_is_still_the_legacy_shape(client):
    """The two error shapes still coexist, and `src/shared/api/apiError.ts` reads both.

    A body that satisfies the schema reaches the handler, and the handler's own
    refusals are unchanged -- they are business rules, not shape checks. Phase 2
    is where these move onto `solverah.errors.ApiError` and the split closes;
    doing it in the same change that enforced the schemas would have made every
    error body move at once.
    """
    resp = client.post(
        "/api/v1/auth/email/verify", json={"email": "nobody@example.com", "code": "000000"}
    )

    assert resp.status_code == 400
    assert set(resp.get_json()) == {"error"}


# ── Profile ─────────────────────────────────────────────────────────────────


def test_profile_read_response_matches_schema(client, auth):
    resp = client.get("/api/v1/me/profile")

    assert resp.status_code == 200
    ProfileDocument.model_validate(resp.get_json())


def test_profile_patch_response_matches_schema(client, auth):
    resp = client.patch(
        "/api/v1/me/profile",
        json={"profile": {"summary": "Backend engineer.", "skills": ["Python"]}},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 200
    ProfileDocument.model_validate(resp.get_json())


def test_career_status_response_matches_schema(client, auth):
    resp = client.patch(
        "/api/v1/me/career-status",
        json={"status": "employed"},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 200
    CareerStatusResponse.model_validate(resp.get_json())


def test_skills_response_matches_schema(client, auth):
    resp = client.put(
        "/api/v1/me/skills",
        json={"skills": [{"name": "Python", "proficiency": "advanced"}]},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 200
    SkillsResponse.model_validate(resp.get_json())


def test_dashboard_response_matches_schema(client, auth):
    resp = client.get("/api/v1/me/dashboard")

    assert resp.status_code == 200
    DashboardResponse.model_validate(resp.get_json())


def test_dashboard_completion_is_a_percentage_string(client, auth):
    """The field is "71%", not 71 -- the frontend renders it directly."""
    body = DashboardResponse.model_validate(client.get("/api/v1/me/dashboard").get_json())

    assert body.profileCompletion.endswith("%")
    assert body.profileCompletion[:-1].isdigit()


# ── Companies and matching ──────────────────────────────────────────────────


def test_company_detail_response_matches_schema(client, auth):
    from app import app
    from model import Company, db

    with app.app_context():
        company = Company(name="Schema Co", slug="schema-co", profile_json={"overview": {}})
        db.session.add(company)
        db.session.commit()
        company_id = company.id

    resp = client.get("/api/v1/companies/%d" % company_id)

    assert resp.status_code == 200
    CompanyDetailResponse.model_validate(resp.get_json())


def test_matches_response_matches_schema_in_every_state(client, auth, monkeypatch):
    """The three states one body shape has to hold (six-trait build, A33)."""
    from app import app

    body = MatchesResponse.model_validate(client.get("/api/v1/me/matches").get_json())
    assert body.state == "core_required"

    _place_person(monkeypatch)
    body = MatchesResponse.model_validate(client.get("/api/v1/me/matches").get_json())
    assert body.state == "no_companies"

    with app.app_context():
        _researched_company("Match Co", "match-co")
    body = MatchesResponse.model_validate(client.get("/api/v1/me/matches").get_json())
    assert body.state == "ranked"
    assert body.total_companies == 1


def test_a_page_of_matches_never_repeats_a_company(client, auth, monkeypatch):
    """The pagination property that replaced the old partition guarantee.

    `GET /company-lens/matches` returned two fixed slices and partitioned them at
    the midpoint so a company could not appear in both. `/me/matches` is one
    ranking read in one direction, so the property worth asserting is that a
    page does not repeat a row -- which is what a keyset cursor over a total
    ordering guarantees and an offset over a shifting list does not.
    """
    from app import app

    _place_person(monkeypatch)
    with app.app_context():
        for i in range(3):
            _researched_company("Split Co %d" % i, "split-co-%d" % i)

    body = MatchesResponse.model_validate(
        client.get("/api/v1/me/matches?limit=5").get_json()
    )

    ids = [entry.id for entry in body.data]
    assert len(ids) == len(set(ids))
    assert body.total_companies == 3


def test_recommendations_responses_match_schema(client, auth):
    """The list and the refresh trigger are two paths now, not one path twice.

    They were `GET` and `POST` on `/recommendations`; Part 5.2 splits them into
    `/me/recommendations` and `/me/recommendations/refresh`, because "read the
    list" and "go compute a new one" are different operations that will want
    different limits, different caching, and -- once Phase 3 has a queue -- a
    `202` on only one of them.
    """
    listed = client.get("/api/v1/me/recommendations")
    refreshed = client.post(
        "/api/v1/me/recommendations/refresh", headers={"X-CSRF-TOKEN": auth}, json={}
    )

    assert listed.status_code == 200
    assert refreshed.status_code == 200
    RecommendationsPage.model_validate(listed.get_json())
    RecommendationsPage.model_validate(refreshed.get_json())


def test_assessment_form_response_matches_schema(client, auth):
    resp = client.get("/api/v1/assessments/core/form")

    assert resp.status_code == 200
    AssessmentFormResponse.model_validate(resp.get_json())


# ── Error envelopes ─────────────────────────────────────────────────────────


def test_unhandled_404_is_a_problem_document(client):
    """Phase 0's handlers, still in force and now declared as every operation's
    `default` response in the generated contract."""
    resp = client.get("/api/v1/no-such-route")

    assert resp.status_code == 404
    assert resp.mimetype == "application/problem+json"
    ProblemDetailResponse.model_validate(resp.get_json())


def test_problem_document_carries_the_request_id(client):
    """The id is the only thing a user is given, and it is enough to find the trace."""
    resp = client.get("/api/v1/no-such-route")
    body = ProblemDetailResponse.model_validate(resp.get_json())

    assert body.request_id
    assert resp.headers["X-Request-Id"] == body.request_id
