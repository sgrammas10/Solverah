"""``GET /api/v1/me/path-suggestions`` -- a cache read, and only a cache read.

Until Phase 3c a miss here ran the whole O*NET and OpenAI fan-out inside the
request -- the handler ``gunicorn.conf.py``'s 120-second timeout was raised
for. The SPA moved to ``POST /me/path-suggestion-jobs`` plus a poll (43a2024),
and 3c cut this route down to serving the per-user cache a succeeded job warms.

So the tests split the way the route did: the shape and cache-coherence tests
warm the cache through the job pair and read it back here, and the miss tests
assert the fan-out *never runs* on this route -- the scorer's call count, not
the status code, is what proves the blocking call is gone.
"""
import pytest
from unittest.mock import MagicMock

import backend.services.path_scoring as path_scoring_mod
import backend.services.path_narrative as path_narrative_mod
from backend.services.occupation_retrieval import CorpusUnavailable
from backend.services.path_scoring import ScoredPath
from backend.services.path_narrative import PathSuggestion

# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------

SCORED_PATHS = [
    ScoredPath(
        onet_code="11-2021.00",
        title="Marketing Managers",
        score=0.82,
        overlapping_skills=["Communication"],
    ),
    ScoredPath(
        onet_code="11-3021.00",
        title="IT Managers",
        score=0.65,
        overlapping_skills=[],
    ),
]

PATH_SUGGESTIONS = [
    PathSuggestion(
        onet_code="11-2021.00",
        title="Marketing Managers",
        why_text="Your skills align well with marketing leadership.",
        profile_dimensions=["Matches your Creative Drive archetype", "Builds on Communication skills"],
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="paths@example.com", password="Strongpass1!"):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Path User", "role": "job-seeker", "terms_accepted": True},
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


def _set_profile(email: str, extra: dict):
    from app import app
    from model import User, db
    from solverah.repositories import profile_repository
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile_repository.update_document(
            user.id, lambda existing: {**existing, **extra}
        )
        db.session.commit()


def _mock_scoring(monkeypatch):
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    mock_score = MagicMock(return_value=SCORED_PATHS)
    mock_narrative = MagicMock(return_value=PATH_SUGGESTIONS)
    monkeypatch.setattr(path_scoring_mod, "score_paths", mock_score)
    monkeypatch.setattr(path_narrative_mod, "generate_narratives", mock_narrative)
    return mock_score, mock_narrative


def _warm_cache(client, csrf):
    """Run the fan-out the only way it runs now: a job, eager, already done."""
    resp = client.post("/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": csrf})
    assert resp.status_code == 202, resp.get_json()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
    resp = client.get("/api/v1/me/path-suggestions")
    assert resp.status_code == 401


def test_a_cache_miss_is_a_404_that_computes_nothing(client, monkeypatch):
    """The inversion of the test that used to stand here.

    Until 3c a miss with no career_status was a 400 from *inside* the fan-out;
    now the route must answer before any of that machinery is reachable. The
    scorer's call count is the real assertion -- a 404 produced after an inline
    compute failed would pass a status check and still be the regression.
    """
    _register_and_login(client, monkeypatch)
    mock_score, mock_narrative = _mock_scoring(monkeypatch)

    resp = client.get("/api/v1/me/path-suggestions")

    assert resp.status_code == 404
    mock_score.assert_not_called()
    mock_narrative.assert_not_called()


def test_a_cache_miss_points_at_the_job_route(client, monkeypatch):
    """The 404 is a pointer, not a shrug.

    A client that missed the cutover has to be told where the work went:
    the problem document names the enqueue whose succeeded job makes this
    route answer 200.
    """
    _register_and_login(client, monkeypatch)

    resp = client.get("/api/v1/me/path-suggestions")

    assert resp.status_code == 404
    assert resp.mimetype == "application/problem+json"
    body = resp.get_json()
    assert body["start_job_url"] == "/me/path-suggestion-jobs"
    assert body["errors"] == [{"field": "cache", "code": "not_generated"}]


def test_happy_path_returns_correct_shape(client, monkeypatch):
    """The payload is unchanged by 3c -- only who computes it moved.

    The job's succeeded result and this route serve the same cached document,
    so every shape assertion the synchronous route carried still holds here.
    """
    csrf = _register_and_login(client, monkeypatch)
    _set_profile("paths@example.com", {
        "career_status": "employed",
        "skills": ["Communication", "Python"],
        "skill_levels": {"Communication": "advanced", "Python": "intermediate"},
        "experience": [{"position": "Software Engineer", "company": "Acme"}],
        "manager_match_result": {"archetype": "The Autonomist", "dimension_scores": {}},
    })
    mock_score, mock_narrative = _mock_scoring(monkeypatch)
    _warm_cache(client, csrf)

    resp = client.get("/api/v1/me/path-suggestions")
    assert resp.status_code == 200
    body = resp.get_json()

    assert "suggestions" in body
    assert "career_status" in body
    assert "generated_at" in body
    assert body["career_status"] == "employed"
    assert body["generated_at"].endswith("Z")

    assert len(body["suggestions"]) == 1
    s = body["suggestions"][0]
    assert s["onet_code"] == "11-2021.00"
    assert s["title"] == "Marketing Managers"
    assert isinstance(s["why_text"], str) and len(s["why_text"]) > 0
    assert isinstance(s["profile_dimensions"], list) and len(s["profile_dimensions"]) >= 1
    assert s["match_score"] == pytest.approx(0.82)

    mock_score.assert_called_once()
    mock_narrative.assert_called_once()


def test_repeat_reads_serve_one_computation(client, monkeypatch):
    """Cache coherence across the pair: one job, many reads, one fan-out."""
    csrf = _register_and_login(client, monkeypatch, email="paths_cache@example.com")
    _set_profile("paths_cache@example.com", {"career_status": "between_jobs"})
    mock_score, _ = _mock_scoring(monkeypatch)
    _warm_cache(client, csrf)

    resp1 = client.get("/api/v1/me/path-suggestions")
    assert resp1.status_code == 200

    resp2 = client.get("/api/v1/me/path-suggestions")
    assert resp2.status_code == 200

    assert mock_score.call_count == 1
    assert resp1.get_json() == resp2.get_json()


# ---------------------------------------------------------------------------
# F-6 -- the cold generation honours stored judgements too
# ---------------------------------------------------------------------------
#
# `POST /me/path-feedback` re-ranks and writes into `path_cache`. That cache is
# per worker and lost on deploy, so without the two behaviours below a reload
# after one would silently rebuild the DEFAULT list while the rows recording
# what the user asked for sat untouched in the database -- and the client would
# have no way to know, because the payload would not say.


def test_the_cold_generation_passes_stored_judgements_to_the_scorer(client, monkeypatch):
    """A judgement is user state, not a property of one re-rank.

    `client` is taken for its schema, not for a request: this asserts on the
    service function because the argument the scorer receives is the claim, and a
    double's output would be whatever the double was told to return.
    """
    from unittest.mock import MagicMock

    import backend.services.path_narrative as pn
    import backend.services.path_scoring as ps
    from app import app
    from backend.services.path_scoring import ScoredPath
    from model import User, db
    from solverah.repositories import path_feedback_repository, profile_repository
    from solverah.services import intelligence_service, path_cache

    with app.app_context():
        user = User(email="coldfb@example.com", password_hash="x", name="Cold")
        db.session.add(user)
        db.session.commit()
        profile_repository.update_document(
            user.id,
            lambda existing: {
                **existing,
                "career_status": "employed",
                "skills": ["Python"],
                "skill_levels": {"Python": "advanced"},
            },
        )
        path_feedback_repository.record(user.id, "15-1252.00", "too_similar")
        db.session.commit()
        path_cache.invalidate(user.id)

        scorer = MagicMock(
            return_value=[
                ScoredPath(onet_code="15-1251.00", title="Computer Programmers", score=0.8)
            ]
        )
        monkeypatch.setattr(ps, "score_paths", scorer)
        monkeypatch.setattr(
            pn,
            "generate_narratives",
            MagicMock(
                side_effect=lambda cands, _ctx: [
                    pn.PathSuggestion(
                        onet_code=c.onet_code,
                        title=c.title,
                        why_text="why",
                        profile_dimensions=["a", "b"],
                    )
                    for c in cands
                ]
            ),
        )
        monkeypatch.setenv("ONET_API_KEY", "test-key")

        result = intelligence_service.path_suggestions(user, app.logger)

    assert result.status == 200, result.body
    assert scorer.call_args.kwargs["feedback"] == {"15-1252.00": "too_similar"}
    assert result.body["feedback"] == {"15-1252.00": "too_similar"}
    # And the same map reaches the cache the GET serves, so a reload sees it.
    assert path_cache.get(user.id)["feedback"] == {"15-1252.00": "too_similar"}


# ---------------------------------------------------------------------------
# F-8 box 4 -- what a thin profile gets on the wire
# ---------------------------------------------------------------------------
#
# The scorer-level cases are in `tests/test_path_scoring.py::TestScorePaths`.
# These three are here because the CODE the user's browser sees is a separate
# claim from what `score_paths` returns, and the difference between them is the
# ACC-4 defect: the SPA's `stateForFailure()` has always had a
# `profile_incomplete` branch -- "Add a job title and a few skills to get
# started" -- and it was dead for months because the backend sent 500 instead.


def _start_job(client, csrf):
    """POST the job and return the finished row. Celery is eager in tests."""
    resp = client.post(
        "/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": csrf}
    )
    return resp


def test_an_invented_job_title_is_scored_not_refused(client, monkeypatch):
    """Box 4, case 1. Invented titles are normal, especially at startups.

    The user is not at fault for being a "Growth Ninja", and the route must not
    treat an O*NET keyword-search miss as a reason to refuse them. It reaches
    the scorer, which resolves the title from the composed document.
    """
    csrf = _register_and_login(client, monkeypatch, email="ninja@example.com")
    _set_profile("ninja@example.com", {
        "career_status": "employed",
        "skills": ["A/B testing", "Email marketing automation", "SQL"],
        "skill_levels": {"SQL": "beginner"},
        "experience": [{"position": "Growth Ninja", "company": "Acme"}],
    })
    mock_score, _ = _mock_scoring(monkeypatch)
    _start_job(client, csrf)

    resp = client.get("/api/v1/me/path-suggestions")

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["suggestions"]
    profile_arg = mock_score.call_args.args[0]
    assert profile_arg.current_title == "Growth Ninja"
    assert len(profile_arg.skills) == 3


def test_no_title_with_skills_is_scored_not_refused(client, monkeypatch):
    """Box 4, case 2. Every `first_job` user, and most new signups.

    `build_user_profile` deliberately produces no title for `first_job` even
    when an experience row exists, so this is the shape of a real cohort rather
    than an edge case.
    """
    csrf = _register_and_login(client, monkeypatch, email="firstjob@example.com")
    _set_profile("firstjob@example.com", {
        "career_status": "first_job",
        "skills": ["Customer service", "Microsoft Excel"],
        "skill_levels": {"Customer service": "intermediate"},
    })
    mock_score, _ = _mock_scoring(monkeypatch)
    _start_job(client, csrf)

    resp = client.get("/api/v1/me/path-suggestions")

    assert resp.status_code == 200, resp.get_json()
    profile_arg = mock_score.call_args.args[0]
    assert profile_arg.current_title is None
    assert [s.name for s in profile_arg.skills] == [
        "Customer service",
        "Microsoft Excel",
    ]


def test_no_title_and_no_skills_is_profile_incomplete_not_a_five_hundred(
    client, monkeypatch
):
    """Box 4, case 3. The ONE path allowed to produce no results.

    `InsufficientProfile` -> `400 profile_incomplete` -> a job row of
    `{status: failed, error: profile_incomplete}`, which `stateForFailure()`
    branches on. A 500 here tells the user to retry something no amount of
    retrying can fix, and that is exactly what it did before F-4.

    The real scorer runs -- not a double -- because the claim is about which
    exception it raises, and a mock would be asserting on its own return value.
    """
    csrf = _register_and_login(client, monkeypatch, email="empty@example.com")
    _set_profile("empty@example.com", {"career_status": "employed", "skills": []})
    monkeypatch.setenv("ONET_API_KEY", "test-key")

    resp = _start_job(client, csrf)

    assert resp.status_code == 202, resp.get_json()
    job = resp.get_json()
    poll = client.get("/api/v1/me/path-suggestion-jobs/%s" % job["job_id"])
    assert poll.status_code == 200, poll.get_json()
    body = poll.get_json()
    assert body["status"] == "failed"
    assert body["error"] == "profile_incomplete", (
        "a thin profile was reported as an outage rather than as something the "
        "user can fix: %r" % body
    )


# ---------------------------------------------------------------------------
# F-8 follow-up -- the cold generation had no CorpusUnavailable branch
# ---------------------------------------------------------------------------
#
# `path_fit`, `record_path_feedback` and `_rescore` each catch `CorpusUnavailable`
# and answer `503 corpus_unavailable`, which `stateForFailure()` already branches
# on. `path_suggestions` -- the cold generation this job runs -- had no branch
# for it: the exception fell through to the generic `except Exception:` and the
# job carried `500 "Unable to score career paths"`, indistinguishable from any
# other failure. This is the missing branch, mirroring the `InsufficientProfile`
# -> `profile_incomplete` one directly above.


def test_a_missing_corpus_is_corpus_unavailable_not_a_five_hundred(client, monkeypatch):
    """The untyped-500 defect this follow-up closes, exercised through the job.

    `score_paths` is not mocked wholesale -- only its corpus loader is, so the
    real function is what raises the typed exception under test.
    """
    csrf = _register_and_login(client, monkeypatch, email="corpus@example.com")
    _set_profile("corpus@example.com", {
        "career_status": "employed",
        "skills": ["Python"],
        "experience": [{"position": "Software Engineer", "endDate": "Present"}],
    })
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    monkeypatch.setattr(
        path_scoring_mod,
        "get_corpus",
        MagicMock(side_effect=CorpusUnavailable("no corpus configured")),
    )

    resp = _start_job(client, csrf)

    assert resp.status_code == 202, resp.get_json()
    job = resp.get_json()
    poll = client.get("/api/v1/me/path-suggestion-jobs/%s" % job["job_id"])
    assert poll.status_code == 200, poll.get_json()
    body = poll.get_json()
    assert body["status"] == "failed"
    assert body["error"] == "corpus_unavailable", (
        "a missing corpus was reported as an untyped failure rather than the "
        "retryable outage the SPA already branches on: %r" % body
    )
    assert body["error"] != "Unable to score career paths"


def test_path_suggestions_answers_a_typed_503_for_a_missing_corpus(client, monkeypatch):
    """The service-level contract the job route above rides on.

    `path_fit`, `record_path_feedback` and `_rescore` all answer
    `IntelligenceResult(status=503, body={"error": "corpus_unavailable"})` for
    this exception; `path_suggestions` now does too. Called directly, the way
    the F-6 cold-generation test above it in this file does, because the status
    code the job route surfaces is folded into a job's `error` string well before
    a client could observe it as `503`. `client` is taken for its schema, not for
    a request -- the same reason that test takes it.
    """
    from app import app
    from model import User, db
    from solverah.repositories import profile_repository
    from solverah.services import intelligence_service

    monkeypatch.setenv("ONET_API_KEY", "test-key")
    monkeypatch.setattr(
        path_scoring_mod,
        "get_corpus",
        MagicMock(side_effect=CorpusUnavailable("no corpus configured")),
    )

    with app.app_context():
        user = User(email="corpus-direct@example.com", password_hash="x", name="Corpus")
        db.session.add(user)
        db.session.commit()
        profile_repository.update_document(
            user.id,
            lambda existing: {
                **existing,
                "career_status": "employed",
                "skills": ["Python"],
                "experience": [{"position": "Software Engineer", "endDate": "Present"}],
            },
        )
        db.session.commit()

        result = intelligence_service.path_suggestions(user, app.logger)

    assert result.status == 503
    assert result.body == {"error": "corpus_unavailable"}
