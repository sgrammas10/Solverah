"""``POST /api/v1/me/path-fit/{onet_code}`` -- the Tier-2 deep fit, on click (F-5).

Three things this file is written to prove, because each of them is a decision
rather than an implementation detail:

**It is stored, and the storage is keyed to the profile.** A second click on the
same card must cost nothing, and the first click *after* a profile edit must
cost everything again. Both halves are asserted against real Postgres rows --
``path_fits`` is a table, not a dict, so a test that mocked it would be testing
the mock.

**The failure modes are typed.** Six error strings, each one something the SPA
branches on, and every one of them reachable through the route rather than only
from the service function.

**The limit is on this route because this route reaches the provider** (A9), the
same reasoning ``POST /me/path-suggestion-jobs`` carries.

``deep_fit`` itself is unit-tested in ``tests/test_path_deep_fit.py``; it is
mocked here in every test but the two marked as end-to-end, which run the real
function against a synthetic corpus and a mocked O*NET client.
"""
from unittest.mock import MagicMock

import pytest

import backend.services.path_deep_fit as pdf
import backend.services.path_scoring as ps
from backend.services.occupation_retrieval import CorpusUnavailable
from backend.services.onet_client import OnetClient, Skill, Task
from backend.services.path_deep_fit import DeepFit, UnknownOccupation, ZoneFit
from backend.services.path_scoring import InsufficientProfile

CODE = "15-1252.00"
EMAIL = "pathfit@example.com"

PROFILE = {
    "career_status": "employed",
    "skills": ["Python", "SQL"],
    "skill_levels": {"Python": "advanced", "SQL": "intermediate"},
    "experience": [{"position": "Software Engineer", "endDate": "Present"}],
}


def _fit(**overrides) -> DeepFit:
    defaults = dict(
        onet_code=CODE,
        title="Software Developers",
        fit_score=0.71,
        retrieval_cosine=0.83,
        centroid_score=0.6,
        coverage_score=0.8,
        skills_score=0.7,
        work_style_score=0.0,
        zone=ZoneFit(
            user_zone=4,
            user_zone_resolved=True,
            occupation_zone=4,
            delta=0,
            score=0.6,
        ),
        matched_skills=["Python"],
        gap_skills=[],
        tasks=["Write code."],
        tech_stack=["Python"],
        weights={"role": 0.35, "coverage": 0.455, "zone": 0.195, "style": 0.0},
        onet_calls=4,
    )
    defaults.update(overrides)
    return DeepFit(**defaults)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email=EMAIL, password="Strongpass1!"):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Fit User",
            "role": "job-seeker",
            "terms_accepted": True,
        },
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


def _set_profile(extra: dict, email: str = EMAIL):
    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile_repository.update_document(
            user.id, lambda existing: {**existing, **extra}
        )
        db.session.commit()


def _user_id(email: str = EMAIL) -> int:
    from app import app
    from model import User

    with app.app_context():
        return User.query.filter_by(email=email).first().id


def _stored_rows(email: str = EMAIL):
    from app import app
    from solverah.repositories import path_fit_repository

    with app.app_context():
        return path_fit_repository.list_for_user(_user_id(email))


def _post(client, csrf, code=CODE):
    return client.post(
        "/api/v1/me/path-fit/%s" % code, headers={"X-CSRF-TOKEN": csrf}
    )


@pytest.fixture()
def mock_fit(monkeypatch):
    """`deep_fit` replaced by a counting double, returning a canned analysis."""
    mock = MagicMock(return_value=_fit())
    monkeypatch.setattr(pdf, "deep_fit", mock)
    return mock


@pytest.fixture()
def signed_in(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _set_profile(PROFILE)
    return csrf


@pytest.fixture(autouse=True)
def clear_path_cache():
    from solverah.services import path_cache

    path_cache.clear()
    yield
    path_cache.clear()


@pytest.fixture(autouse=True)
def _onet_key(monkeypatch):
    """`OnetClient()` refuses to construct without a key, and the service builds
    one before it reaches `deep_fit` -- so mocking the analysis is not enough.

    CI-parity note: this is exactly the leak CLAUDE.md warns about. A developer
    with a populated `.env` gets `ONET_API_KEY` for free and every test below
    passes without this fixture; the runner, which sets five variables and has
    no `.env`, gets a 500 in thirteen of them.
    """
    monkeypatch.setenv("ONET_API_KEY", "test-key")


# ---------------------------------------------------------------------------
# Auth and method
# ---------------------------------------------------------------------------


def test_unauthenticated_returns_401(client):
    resp = client.post("/api/v1/me/path-fit/%s" % CODE)
    assert resp.status_code == 401


def test_a_write_without_the_csrf_header_is_refused(client, monkeypatch, mock_fit):
    """POST rather than GET is what puts this behind the CSRF guard at all.

    A GET-with-cache would have carried the same provider spend outside it --
    see the route's comment for why that was the deciding argument.
    """
    _register_and_login(client, monkeypatch)
    _set_profile(PROFILE)
    resp = client.post("/api/v1/me/path-fit/%s" % CODE)
    assert resp.status_code == 401
    assert mock_fit.call_count == 0


def test_get_is_not_served(client, monkeypatch, mock_fit):
    _register_and_login(client, monkeypatch)
    assert client.get("/api/v1/me/path-fit/%s" % CODE).status_code == 405


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_a_fit_is_computed_stored_and_returned(client, signed_in, mock_fit):
    resp = _post(client, signed_in)
    assert resp.status_code == 200, resp.get_json()

    body = resp.get_json()
    assert body["onet_code"] == CODE
    assert body["title"] == "Software Developers"
    assert body["fit_score"] == 0.71
    assert body["matched_skills"] == ["Python"]
    assert body["zone"]["delta"] == 0
    assert body["cached"] is False
    assert body["computed_at"].endswith("Z")
    assert body["narrative"] is None, "F-5 ships no LLM call; see path_deep_fit"

    rows = _stored_rows()
    assert len(rows) == 1
    assert rows[0].onet_code == CODE
    assert rows[0].payload["fit_score"] == 0.71
    assert len(rows[0].profile_fingerprint) == 64


def test_the_scorer_sees_the_profile_the_shortlist_was_built_from(
    client, signed_in, mock_fit
):
    """`build_user_profile` is shared with `path_suggestions` on purpose: the
    panel and the card it opened from must not disagree about the user."""
    _post(client, signed_in)
    user_profile = mock_fit.call_args.args[0]
    assert user_profile.current_title == "Software Engineer"
    assert sorted(s.name for s in user_profile.skills) == ["Python", "SQL"]
    assert mock_fit.call_args.args[1] == CODE


def test_a_second_click_is_served_from_storage(client, signed_in, mock_fit):
    first = _post(client, signed_in).get_json()
    second = _post(client, signed_in).get_json()

    assert mock_fit.call_count == 1, "the second click paid for the analysis again"
    assert second["cached"] is True
    assert second["computed_at"] == first["computed_at"]
    assert {k: v for k, v in second.items() if k != "cached"} == {
        k: v for k, v in first.items() if k != "cached"
    }


def test_two_occupations_are_two_rows(client, signed_in, mock_fit):
    other = "15-1251.00"
    mock_fit.return_value = _fit()
    _post(client, signed_in)
    mock_fit.return_value = _fit(onet_code=other, title="Computer Programmers")
    _post(client, signed_in, other)

    assert {row.onet_code for row in _stored_rows()} == {CODE, other}
    assert mock_fit.call_count == 2


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def test_a_profile_write_invalidates_the_stored_fit(client, signed_in, mock_fit):
    _post(client, signed_in)
    assert len(_stored_rows()) == 1

    resp = client.put(
        "/api/v1/me/path-preferences",
        json={
            "move_intent": "adjacent",
            "seniority_intent": "move_up",
            "priority": "learning_growth",
        },
        headers={"X-CSRF-TOKEN": signed_in},
    )
    assert resp.status_code == 200
    assert _stored_rows() == [], "the write left a fit computed from the old profile"

    assert _post(client, signed_in).get_json()["cached"] is False
    assert mock_fit.call_count == 2


def test_a_row_that_survived_a_missed_invalidation_is_still_refused(
    client, signed_in, mock_fit
):
    """The belt to the enumeration's braces.

    `path_cache`'s docstring records the weakness of an enumerated call-site
    list: "missing one of those calls does not fail loudly; it serves a stale
    suggestion". Here the row is edited behind the service's back to simulate
    exactly that -- a fit that outlived a profile change -- and the fingerprint
    catches it with no invalidate call involved at all.
    """
    _post(client, signed_in)

    from app import app
    from model import db

    with app.app_context():
        from solverah.repositories import path_fit_repository

        row = path_fit_repository.list_for_user(_user_id())[0]
        row.profile_fingerprint = "0" * 64
        db.session.commit()

    assert _post(client, signed_in).get_json()["cached"] is False
    assert mock_fit.call_count == 2
    assert len(_stored_rows()) == 1, "the refused row was duplicated, not replaced"


def test_a_fit_older_than_max_age_is_recomputed(client, signed_in, mock_fit):
    """The third input nothing else bounds: O*NET's own content, quarterly."""
    import datetime

    _post(client, signed_in)

    from app import app
    from model import db
    from solverah.repositories import path_fit_repository

    with app.app_context():
        row = path_fit_repository.list_for_user(_user_id())[0]
        row.computed_at = datetime.datetime.now(
            datetime.timezone.utc
        ) - path_fit_repository.MAX_AGE - datetime.timedelta(days=1)
        db.session.commit()

    assert _post(client, signed_in).get_json()["cached"] is False
    assert mock_fit.call_count == 2


def test_an_unrelated_profile_edit_does_not_change_the_fingerprint():
    """A user fixing their phone number must not throw away every fit."""
    from backend.services.path_scoring import UserProfile, UserSkill
    from solverah.repositories import path_fit_repository

    base = UserProfile(
        current_title="Software Engineer",
        career_status="employed",
        skills=[UserSkill(name="Python", level="advanced")],
        archetype="Deep Diver",
    )
    reordered = UserProfile(
        current_title="Software Engineer",
        career_status="employed",
        # Same skills, listed the other way round: not a change.
        skills=[UserSkill(name="Python", level="advanced")],
        archetype="Deep Diver",
    )
    moved = UserProfile(
        current_title="Staff Software Engineer",
        career_status="employed",
        skills=[UserSkill(name="Python", level="advanced")],
        archetype="Deep Diver",
    )

    assert path_fit_repository.fingerprint(base) == path_fit_repository.fingerprint(
        reordered
    )
    assert path_fit_repository.fingerprint(base) != path_fit_repository.fingerprint(
        moved
    )


def test_archetype_description_no_longer_moves_the_fingerprint():
    """F-8 follow-up. F-8 box 8 (02dd338) stopped `_build_behavioral_profile`
    reading `archetype_description`, so a regenerated description is no longer a
    reason to throw away a stored fit -- nothing the analysis reads changed.

    `focus_type` is the control: it IS read by `_build_behavioral_profile`, so it
    must still move the fingerprint. Without the control this test could pass by
    accident if `fingerprint` hashed nothing at all.
    """
    from backend.services.path_scoring import UserProfile, UserSkill
    from solverah.repositories import path_fit_repository

    base = UserProfile(
        current_title="Software Engineer",
        career_status="employed",
        skills=[UserSkill(name="Python", level="advanced")],
        archetype="Deep Diver",
        archetype_description="You build momentum through sustained effort.",
        focus_type="Structured Thinker",
    )
    description_changed = UserProfile(
        current_title="Software Engineer",
        career_status="employed",
        skills=[UserSkill(name="Python", level="advanced")],
        archetype="Deep Diver",
        archetype_description="An entirely different sentence, about fire safety.",
        focus_type="Structured Thinker",
    )
    focus_type_changed = UserProfile(
        current_title="Software Engineer",
        career_status="employed",
        skills=[UserSkill(name="Python", level="advanced")],
        archetype="Deep Diver",
        archetype_description="You build momentum through sustained effort.",
        focus_type="Something else entirely",
    )

    assert path_fit_repository.fingerprint(base) == path_fit_repository.fingerprint(
        description_changed
    ), "archetype_description is not read by the analysis and must not move the fingerprint"
    assert path_fit_repository.fingerprint(base) != path_fit_repository.fingerprint(
        focus_type_changed
    ), "focus_type IS read by the analysis and must still move the fingerprint"


# ---------------------------------------------------------------------------
# Typed failures
# ---------------------------------------------------------------------------


def test_no_career_status_and_none_derivable_is_a_400(client, monkeypatch, mock_fit):
    csrf = _register_and_login(client, monkeypatch)
    _set_profile({"skills": ["Python"], "experience": []})

    resp = _post(client, csrf)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "career_status_not_set"
    assert mock_fit.call_count == 0


def test_an_empty_profile_is_profile_incomplete_not_a_500(
    client, signed_in, monkeypatch
):
    """The F-4 branch, reused. `stateForFailure()` already handles this string."""
    monkeypatch.setattr(
        pdf, "deep_fit", MagicMock(side_effect=InsufficientProfile("nothing to fit"))
    )
    resp = _post(client, signed_in)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "profile_incomplete"


@pytest.mark.parametrize(
    "reason, error",
    [
        ("malformed", "invalid_onet_code"),
        ("unknown", "unknown_occupation"),
        ("residual", "unsupported_occupation"),
    ],
)
def test_each_unknown_occupation_reason_is_its_own_404_string(
    client, signed_in, monkeypatch, reason: str, error: str
):
    monkeypatch.setattr(
        pdf,
        "deep_fit",
        MagicMock(side_effect=UnknownOccupation("15-9999.00", reason)),
    )
    resp = _post(client, signed_in)
    assert resp.status_code == 404
    assert resp.get_json()["error"] == error


def test_a_corpus_outage_is_a_503_not_a_404(client, signed_in, monkeypatch):
    """A missing artifact is an outage the client should retry, not a bad code."""
    monkeypatch.setattr(
        pdf, "deep_fit", MagicMock(side_effect=CorpusUnavailable("no artifact"))
    )
    resp = _post(client, signed_in)
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "corpus_unavailable"


def test_an_unexpected_failure_is_a_500_and_stores_nothing(
    client, signed_in, monkeypatch
):
    monkeypatch.setattr(pdf, "deep_fit", MagicMock(side_effect=RuntimeError("boom")))
    resp = _post(client, signed_in)
    assert resp.status_code == 500
    assert _stored_rows() == []


# ---------------------------------------------------------------------------
# The limit
# ---------------------------------------------------------------------------


def test_ten_per_minute_matching_the_path_suggestion_job(
    client, monkeypatch, mock_fit
):
    """A9: the budget bounds provider spend, so it lives on the door to the spend.

    A stored fit is served without spending anything, so ten *distinct*
    occupations is what the limit actually bounds -- which is the whole
    shortlist and then some.
    """
    from app import app
    from solverah.extensions import limiter

    csrf = _register_and_login(client, monkeypatch)
    _set_profile(PROFILE)

    limiter.reset()
    app.config["TESTING"] = False
    try:
        statuses = [
            client.post(
                "/api/v1/me/path-fit/15-12%02d.00" % i,
                headers={"X-CSRF-TOKEN": csrf},
            ).status_code
            for i in range(11)
        ]
    finally:
        app.config["TESTING"] = True
        limiter.reset()

    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429


# ---------------------------------------------------------------------------
# End to end: the real deep_fit, a synthetic corpus, a mocked O*NET
# ---------------------------------------------------------------------------


def _synthetic_corpus():
    from tests.test_path_scoring import WORLD_ROWS, WORLD_ZONES, build_corpus

    return build_corpus(WORLD_ROWS, WORLD_ZONES)


@pytest.fixture()
def real_stack(monkeypatch):
    """The real `deep_fit`, over a corpus of five hand-written vectors.

    No OpenAI client: `llm.get_openai_client` raises without a key and the
    service degrades rather than failing, which is the promise, so this is also
    the CI-parity path -- CI sets no `OPENAI_API_KEY`.
    """
    corpus = _synthetic_corpus()
    monkeypatch.setattr(pdf, "get_corpus", lambda: corpus)
    monkeypatch.setattr(ps, "get_corpus", lambda: corpus)

    onet = MagicMock(spec=OnetClient)
    onet.get_skills_profile.return_value = [
        Skill(element_id="2.A.1.a", name="Programming", importance=90.0, level=0.0)
    ]
    onet.get_hot_technologies.return_value = ["Python"]
    onet.get_work_activities.return_value = []
    onet.get_tasks.return_value = [
        Task(task_id="1", title="Write code.", importance=90.0, category="Core")
    ]
    onet.search_occupations.return_value = []
    monkeypatch.setattr(
        "backend.services.onet_client.OnetClient", MagicMock(return_value=onet)
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return onet


def test_end_to_end_through_the_real_analysis(client, signed_in, real_stack):
    resp = _post(client, signed_in, "15-1251.00")
    assert resp.status_code == 200, resp.get_json()

    body = resp.get_json()
    assert body["title"] == "Computer Programmers"
    assert body["tasks"] == ["Write code."]
    assert body["tech_stack"] == ["Python"]
    assert body["onet_calls"] == 4
    assert body["zone"]["occupation_zone"] == 4
    assert 0.0 <= body["fit_score"] <= 1.0
    assert sum(body["weights"].values()) == pytest.approx(1.0, abs=1e-3)

    # The declared schema is descriptive, not enforced at runtime, so the only
    # thing keeping `docs/openapi.json` honest about this route is a real
    # response pushed through the real model -- the job
    # `tests/test_schema_conformance.py` does for the endpoints that predate it.
    # Kept here rather than added there because this route needs a corpus and a
    # mocked O*NET client, which that file has no fixture for.
    from solverah.schemas.intelligence import PathFitResponse

    PathFitResponse.model_validate(body)


def test_end_to_end_refuses_a_code_the_corpus_does_not_have(
    client, signed_in, real_stack
):
    resp = _post(client, signed_in, "99-9999.00")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "unknown_occupation"
    assert real_stack.get_skills_profile.call_count == 0, "a miss paid for a fetch"
