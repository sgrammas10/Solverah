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


@pytest.fixture(autouse=True)
def _narration_runs_in_this_app(monkeypatch):
    """W-16: `start_narration` pushes the app the queue adapter bound.

    In production there is one app and `init_celery` binds it. In the suite,
    every test that calls `create_app()` rebinds the queue to ITS app -- so,
    depending on test order, the narration here would run in some other test's
    non-TESTING app, on the threaded path, and these assertions would race it.
    Bind the app this file's client uses, for the length of each test.
    """
    from app import app
    from solverah.infra.queue import celery_app

    monkeypatch.setitem(celery_app.conf, "solverah_flask_app", app)


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

    # W-16: the page is what the SCORER returned, not what the narrator
    # answered for. Before W-16 a card the narrator left out vanished from the
    # page; now it keeps its place and takes the fallback sentence.
    assert [s["onet_code"] for s in body["suggestions"]] == ["11-2021.00", "11-3021.00"]
    s = body["suggestions"][0]
    assert s["title"] == "Marketing Managers"
    assert isinstance(s["why_text"], str) and len(s["why_text"]) > 0
    assert isinstance(s["profile_dimensions"], list) and len(s["profile_dimensions"]) >= 1
    assert s["match_score"] == pytest.approx(0.82)
    assert s["overlapping_skills"] == ["Communication"]
    unwritten = body["suggestions"][1]
    assert unwritten["why_text"] == (
        "A different direction. Open it to see how it lines up with your skills."
    )
    assert unwritten["profile_dimensions"] == []
    assert body["narration_pending"] is False

    mock_score.assert_called_once()
    # W-17: both cards are in the page's first three, so each is its own call.
    assert mock_narrative.call_count == 2


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


# ---------------------------------------------------------------------------
# W-12 -- the job narrates twenty and serves ten
# ---------------------------------------------------------------------------
#
# The first browser test: after a tap, the cards that came in to replace the
# removed ones read "Uses your SQL." with no pills, next to cards with a real
# why-sentence.  F-8 routed the fix onward -- the LLM narrative on a re-ranked
# card "has to be earned off the request path" -- and this is where it is
# earned.  The serving half is in `tests/test_path_feedback_api.py`.


def _deep_scored(n: int = 20) -> list:
    return [
        ScoredPath(
            onet_code="15-00%02d.00" % i,
            title="Role %d" % i,
            score=0.9 - i / 100,
            overlapping_skills=["Python"],
        )
        for i in range(n)
    ]


def _mock_deep_scoring(monkeypatch, *, fail_codes=frozenset()):
    """A scorer that honours `reserve`, and a narrator that records its batches.

    `generate_narratives` is the thing patched, not `narrate_page_first`
    -- so the real batching runs and the calls recorded here are the real
    completions the job would have made.
    """
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    everything = _deep_scored(20)

    def score(*_args, reserve=0, **_kwargs):
        return everything[: 10 + reserve]

    batches: list[list[str]] = []

    def narrate(candidates, _ctx):
        codes = [c.onet_code for c in candidates]
        batches.append(codes)
        if fail_codes & set(codes):
            raise RuntimeError("the provider is down")
        return [
            PathSuggestion(
                onet_code=c.onet_code,
                title=c.title,
                why_text="Narrated %s." % c.onet_code,
                profile_dimensions=["Builds on your Python", "Fits you"],
            )
            for c in candidates
        ]

    mock_score = MagicMock(side_effect=score)
    monkeypatch.setattr(path_scoring_mod, "score_paths", mock_score)
    monkeypatch.setattr(
        path_narrative_mod, "generate_narratives", MagicMock(side_effect=narrate)
    )
    return mock_score, batches


def _deep_profile(client, monkeypatch, email):
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_profile(
        email,
        {
            "career_status": "employed",
            "skills": ["Python"],
            "skill_levels": {"Python": "advanced"},
            "experience": [{"position": "Software Engineer", "company": "Acme"}],
        },
    )
    return csrf


def test_the_job_asks_the_scorer_for_a_reserve(client, monkeypatch):
    from solverah.services.intelligence_service import RESERVE_DEPTH

    csrf = _deep_profile(client, monkeypatch, "w12reserve@example.com")
    mock_score, _ = _mock_deep_scoring(monkeypatch)

    _warm_cache(client, csrf)

    assert mock_score.call_args.kwargs["reserve"] == RESERVE_DEPTH


def test_the_job_narrates_the_visible_three_alone_then_the_rest_in_fives(
    client, monkeypatch
):
    """W-17: seven completions -- the page's first three one card each, then
    the other seventeen in batches of five (W-16 had 4 x 5; W-12 had 2 x 10).

    One card is a ~1.4 s completion against 3.1-3.7 s for five, so the three
    sentences a user can see no longer wait for the batch they shared.
    """
    csrf = _deep_profile(client, monkeypatch, "w12batches@example.com")
    _, batches = _mock_deep_scoring(monkeypatch)

    _warm_cache(client, csrf)

    code = "15-00%02d.00"
    assert sorted(batches, key=lambda codes: codes[0]) == [
        [code % 0],
        [code % 1],
        [code % 2],
        [code % i for i in range(3, 8)],
        [code % i for i in range(8, 13)],
        [code % i for i in range(13, 18)],
        [code % i for i in range(18, 20)],
    ]


def test_only_the_page_reaches_the_wire(client, monkeypatch):
    """The cached payload IS the response body and the job's stored result, so
    the reserve cannot live in it -- ten cards out, ten cards cached elsewhere.
    """
    csrf = _deep_profile(client, monkeypatch, "w12wire@example.com")
    _mock_deep_scoring(monkeypatch)

    _warm_cache(client, csrf)
    body = client.get("/api/v1/me/path-suggestions").get_json()

    assert set(body) == {
        "suggestions",
        "career_status",
        "generated_at",
        "feedback",
        "narration_pending",
    }
    assert body["narration_pending"] is False
    assert [s["onet_code"] for s in body["suggestions"]] == [
        "15-00%02d.00" % i for i in range(10)
    ]
    assert all("Narrated" in s["why_text"] for s in body["suggestions"])


def test_every_narrative_the_job_wrote_is_in_the_reserve(client, monkeypatch):
    """All TWENTY, the page included -- W-14 widened this from the other ten.

    W-12 stored the reserve as the complement of the page, because a page card's
    prose is on the payload and `_describe` carries it forward from there. That
    holds until the card is removed: "Not for me" on card 9 drops it from the
    payload, "Start over" puts it back on the page, and a reserve defined to
    exclude the page has nothing for it either -- so it came back reading "Uses
    your SQL." with no pills. `test_a_removed_card_comes_back_with_the_job_prose`
    in `test_path_feedback_api.py` is that walk; this is the store it reads.
    """
    from app import app
    from model import User
    from solverah.services import path_cache

    csrf = _deep_profile(client, monkeypatch, "w12stash@example.com")
    _mock_deep_scoring(monkeypatch)

    _warm_cache(client, csrf)

    with app.app_context():
        user = User.query.filter_by(email="w12stash@example.com").one()
        reserve = path_cache.get_reserve(user.id)

    assert sorted(reserve) == ["15-00%02d.00" % i for i in range(20)]
    for code in ("15-0003.00", "15-0011.00"):  # one from the page, one below it
        assert reserve[code]["why_text"] == "Narrated %s." % code
        assert reserve[code]["profile_dimensions"] == [
            "Builds on your Python",
            "Fits you",
        ]


def test_a_failing_reserve_batch_does_not_fail_the_job(client, monkeypatch):
    """The ten still land; the second ten fall back.

    Failing the whole job -- and with it the shortlist, which is the product --
    because prose for a card the user cannot see came back malformed would trade
    the thing that matters for the thing that does not.
    """
    from app import app
    from model import User
    from solverah.services import path_cache

    csrf = _deep_profile(client, monkeypatch, "w12halfdown@example.com")
    _mock_deep_scoring(
        monkeypatch, fail_codes={"15-00%02d.00" % i for i in range(13, 20)}
    )

    _warm_cache(client, csrf)
    resp = client.get("/api/v1/me/path-suggestions")

    assert resp.status_code == 200
    body = resp.get_json()
    assert [s["onet_code"] for s in body["suggestions"]] == [
        "15-00%02d.00" % i for i in range(10)
    ]
    assert all("Narrated" in s["why_text"] for s in body["suggestions"])
    with app.app_context():
        user = User.query.filter_by(email="w12halfdown@example.com").one()
        reserve = path_cache.get_reserve(user.id)
    # W-14: the reserve is every narrative the job wrote. W-17: the batches are now
    # 3 x 1 then 5-5-5-2, so the two failing ones are cards 13-19 and 0-12 land.
    assert sorted(reserve) == ["15-00%02d.00" % i for i in range(13)]


def test_a_failing_page_batch_falls_back_instead_of_failing_the_job(
    client, monkeypatch
):
    """W-16 reverses W-12's asymmetry, deliberately.

    Before W-16 the narrator ran before any card was shown, so a page it could
    not write was a page with nothing on it, and the job failed. Now the cards
    are scored and on screen first; failing the job at the narration step would
    take a list the user is already reading away from them. The page's cards
    take the fallback sentence, and nothing is stored as narration -- neither
    in `path_narratives` nor as a "narrated" cache entry the next job would
    trust.
    """
    from app import app
    from model import User
    from solverah.repositories import path_narrative_repository
    from solverah.services import path_cache

    csrf = _deep_profile(client, monkeypatch, "w12pagedown@example.com")
    _mock_deep_scoring(
        monkeypatch, fail_codes={"15-00%02d.00" % i for i in range(10)}
    )

    _warm_cache(client, csrf)
    resp = client.get("/api/v1/me/path-suggestions")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["narration_pending"] is False
    assert [s["why_text"] for s in body["suggestions"]] == ["Uses your Python."] * 10
    assert all(s["profile_dimensions"] == [] for s in body["suggestions"])
    with app.app_context():
        user = User.query.filter_by(email="w12pagedown@example.com").one()
        stored = {row.onet_code for row in path_narrative_repository.list_for_user(user.id)}
        assert not path_cache.is_narrated(user.id)
    # W-17: cards 10-12 share the 8-12 batch with the page's last two, so they
    # go down with it; the two batches wholly below the page are what land.
    assert stored == {"15-00%02d.00" % i for i in range(13, 20)}, (
        "the reserve batches that worked are stored; the page's fallbacks are not"
    )


# ---------------------------------------------------------------------------
# W-13: no grade reaches the wire (ruling flag 12)
# ---------------------------------------------------------------------------


def test_a_graded_narrative_is_scrubbed_before_it_reaches_the_wire(
    client, monkeypatch
):
    """The third browser test's card, end to end.

    The narrator is NOT doubled here -- the OpenAI client under it is. Every
    other test in this file replaces `generate_narratives` wholesale, which is
    right for what those are about and wrong for this one: the scrub lives
    inside that function, so a double for it would step over the thing being
    proved. What is faked is the provider, returning the sentence the tester
    actually saw.
    """
    import json

    csrf = _register_and_login(client, monkeypatch, email="w13grade@example.com")
    _set_profile("w13grade@example.com", {
        "career_status": "employed",
        "skills": ["Communication", "Python"],
        "experience": [{"position": "Software Engineer", "company": "Acme"}],
    })
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    monkeypatch.setattr(
        path_scoring_mod, "score_paths", MagicMock(return_value=SCORED_PATHS[:1])
    )

    graded = {
        "suggestions": [
            {
                "onet_code": "11-2021.00",
                "title": "Marketing Managers",
                "why_text": (
                    "You would own campaigns end to end, making it a strong fit "
                    "for your background."
                ),
                "profile_dimensions": [
                    "Builds on Communication skills",
                    "95% overlap with your skills",
                ],
            }
        ]
    }
    choice = MagicMock()
    choice.message.content = json.dumps(graded)
    response = MagicMock()
    response.choices = [choice]
    provider = MagicMock()
    provider.chat.completions.create.return_value = response
    monkeypatch.setattr(path_narrative_mod, "_get_openai_client", lambda: provider)

    _warm_cache(client, csrf)
    body = client.get("/api/v1/me/path-suggestions").get_json()

    [card] = body["suggestions"]
    assert card["why_text"] == "You would own campaigns end to end."
    assert card["profile_dimensions"] == ["Builds on Communication skills"]
    assert "%" not in json.dumps(body["suggestions"])


# ---------------------------------------------------------------------------
# W-16 -- cards first, sentences after, and the sentences stored
# ---------------------------------------------------------------------------
#
# Sebastian: "the loading phase is 5-10 s with one user, imagine 10 users at the
# same time." Celery runs eager in production, so the scoring job ran inside
# the POST -- scoring AND ~10 s of narrator -- on one of eight gunicorn threads.
# The job now stores the scored list first and narrates on the service's own
# pool; the narrator's sentences are stored by a fingerprint of its inputs so a
# re-sort pays for none of them twice.


def _post_job(client, csrf) -> str:
    resp = client.post("/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": csrf})
    assert resp.status_code == 202, resp.get_json()
    return resp.get_json()["job_id"]


def _poll(client, job_id) -> dict:
    resp = client.get("/api/v1/me/path-suggestion-jobs/%s" % job_id)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _user_id(email: str) -> int:
    from app import app
    from model import User

    with app.app_context():
        return User.query.filter_by(email=email).one().id


def _stored_codes(email: str) -> list:
    from app import app
    from solverah.repositories import path_narrative_repository

    with app.app_context():
        return sorted(
            row.onet_code
            for row in path_narrative_repository.list_for_user(_user_id(email))
        )


def test_the_post_returns_with_cards_before_the_narrator_finishes(client, monkeypatch):
    """The whole of part 1, on the real threaded path.

    The narrator is held on an Event, so if the POST waited for it the POST
    would not return until the Event is set -- and the Event is only set after
    the POST returns and the first poll has been checked. The poll in between
    must already render: succeeded, every card with its title, reasons and
    overlapping skills, every sentence empty, `narration_pending: true`.
    """
    import threading
    import time

    from app import app

    monkeypatch.setitem(app.config, "PATH_NARRATION_INLINE", False)
    csrf = _deep_profile(client, monkeypatch, "w16cardsfirst@example.com")
    _mock_deep_scoring(monkeypatch)
    release = threading.Event()
    entered = threading.Event()
    real_generate = path_narrative_mod.generate_narratives

    def held(candidates, ctx):
        entered.set()
        assert release.wait(10), "the test never released the narrator"
        return real_generate(candidates, ctx)

    monkeypatch.setattr(path_narrative_mod, "generate_narratives", held)

    try:
        job_id = _post_job(client, csrf)
        assert entered.wait(5), "the narration never started"

        first = _poll(client, job_id)
        assert first["status"] == "succeeded"
        result = first["result"]
        assert result["narration_pending"] is True
        assert [s["onet_code"] for s in result["suggestions"]] == [
            "15-00%02d.00" % i for i in range(10)
        ]
        assert all(s["why_text"] == "" for s in result["suggestions"])
        assert all(s["profile_dimensions"] == [] for s in result["suggestions"])
        assert all(s["overlapping_skills"] == ["Python"] for s in result["suggestions"])
    finally:
        release.set()

    deadline = time.monotonic() + 10
    while True:
        settled = _poll(client, job_id)["result"]
        if not settled["narration_pending"] or time.monotonic() > deadline:
            break
        time.sleep(0.1)

    assert settled["narration_pending"] is False
    assert [s["onet_code"] for s in settled["suggestions"]] == [
        "15-00%02d.00" % i for i in range(10)
    ], "the sentences land in place; the order does not move"
    assert [s["why_text"] for s in settled["suggestions"]] == [
        "Narrated 15-00%02d.00." % i for i in range(10)
    ]


def test_the_first_three_sentences_reach_the_poll_before_the_rest(client, monkeypatch):
    """W-17 on the real threaded path: the visible three land on their own.

    Every multi-card call (the tail) is held on an Event. The page's first three
    are one-card calls at head priority, so they must reach the job's result --
    and the cached list -- while the tail is still held: filled in place,
    everything else still empty, `narration_pending` still true, and the cache
    NOT marked narrated (W-14's flag waits for the whole narration). Regression
    for W-17: before it the first three shared a five-card batch, which is held
    here, so this poll never saw a sentence until the release.
    """
    import threading
    import time

    from app import app
    from solverah.services import path_cache

    monkeypatch.setitem(app.config, "PATH_NARRATION_INLINE", False)
    email = "w17headfirst@example.com"
    csrf = _deep_profile(client, monkeypatch, email)
    _mock_deep_scoring(monkeypatch)
    release = threading.Event()
    real_generate = path_narrative_mod.generate_narratives

    def held(candidates, ctx):
        if len(candidates) > 1:
            assert release.wait(10), "the test never released the tail"
        return real_generate(candidates, ctx)

    monkeypatch.setattr(path_narrative_mod, "generate_narratives", held)
    head = ["Narrated 15-00%02d.00." % i for i in range(3)]

    try:
        job_id = _post_job(client, csrf)
        deadline = time.monotonic() + 10
        while True:
            partial = _poll(client, job_id)["result"]
            texts = [s["why_text"] for s in partial["suggestions"]]
            if texts[:3] == head or time.monotonic() > deadline:
                break
            time.sleep(0.05)

        assert texts == head + [""] * 7
        assert partial["narration_pending"] is True
        cached = client.get("/api/v1/me/path-suggestions").get_json()
        assert [s["why_text"] for s in cached["suggestions"]] == head + [""] * 7
        with app.app_context():
            assert not path_cache.is_narrated(_user_id(email))
    finally:
        release.set()

    deadline = time.monotonic() + 10
    while True:
        settled = _poll(client, job_id)["result"]
        if not settled["narration_pending"] or time.monotonic() > deadline:
            break
        time.sleep(0.05)

    assert [s["why_text"] for s in settled["suggestions"]] == [
        "Narrated 15-00%02d.00." % i for i in range(10)
    ]
    with app.app_context():
        assert path_cache.is_narrated(_user_id(email))


def test_every_sentence_the_job_wrote_is_stored(client, monkeypatch):
    csrf = _deep_profile(client, monkeypatch, "w16stored@example.com")
    _mock_deep_scoring(monkeypatch)

    _warm_cache(client, csrf)

    assert _stored_codes("w16stored@example.com") == [
        "15-00%02d.00" % i for i in range(20)
    ]


def test_a_resort_reuses_every_stored_sentence(client, monkeypatch):
    """The point of part 3: a re-score after a wants save pays for no sentence.

    `path_cache.invalidate` is what a wants save does to the list
    (`path_wants_service`), and it is what a deploy does to all of them. The
    second job finds all twenty sentences in `path_narratives`, calls the
    narrator zero times, and its scored result is already complete -- there is
    no narration phase to run.
    """
    from app import app
    from model import User
    from solverah.services import path_cache, scoring_jobs

    csrf = _deep_profile(client, monkeypatch, "w16resort@example.com")
    _, batches = _mock_deep_scoring(monkeypatch)
    _warm_cache(client, csrf)
    first = client.get("/api/v1/me/path-suggestions").get_json()
    assert len(batches) == 7

    with app.app_context():
        user = User.query.filter_by(email="w16resort@example.com").one()
        path_cache.invalidate(user.id)
        status, result, _, narration = scoring_jobs._score_path_suggestions(
            {"user_id": user.id}
        )

    assert status == scoring_jobs.SUCCEEDED
    assert narration is None, "nothing left to narrate"
    assert len(batches) == 7, "the narrator was not called again"
    assert result["narration_pending"] is False
    assert [s["why_text"] for s in result["suggestions"]] == [
        s["why_text"] for s in first["suggestions"]
    ], "the text does not change on a save"
    assert all(s["profile_dimensions"] for s in result["suggestions"])


def test_a_wants_answer_is_not_a_narrator_input(client, monkeypatch):
    """Changing wants leaves every fingerprint unchanged -- end to end.

    A `path_wants` row is written the way the panel writes one, the cache is
    dropped the way `path_wants_service` drops it, and the next job narrates
    nothing: the row reached the scorer's inputs, not the narrator's.
    """
    from app import app
    from backend.services.path_narrative import narrative_fingerprint
    from model import PathWant, User, db
    from solverah.repositories import profile_repository
    from solverah.services import intelligence_service, path_cache

    email = "w16wants@example.com"
    csrf = _deep_profile(client, monkeypatch, email)
    _, batches = _mock_deep_scoring(monkeypatch)
    _warm_cache(client, csrf)
    assert len(batches) == 7

    def fingerprints(user):
        profile = profile_repository.load_document(user.id)
        ctx = intelligence_service.build_user_context(profile, user.intake, "employed")
        return [narrative_fingerprint(path, ctx) for path in _deep_scored(20)]

    with app.app_context():
        user = User.query.filter_by(email=email).one()
        before = fingerprints(user)
        db.session.add(
            PathWant(
                user_id=user.id,
                anchor_onet_code="15-1252.00",
                kind="condition",
                item_key="people",
                item_text="",
                verdict="more",
            )
        )
        db.session.commit()
        after = fingerprints(user)
        path_cache.invalidate(user.id)

    assert before == after
    _warm_cache(client, csrf)
    assert len(batches) == 7, "a wants save costs no narrator call"


def test_a_changed_skill_is_narrated_again(client, monkeypatch):
    """The other half of the pin: a narrator input moved, so every key moved."""
    from app import app
    from model import User
    from solverah.services import path_cache

    email = "w16skill@example.com"
    csrf = _deep_profile(client, monkeypatch, email)
    _, batches = _mock_deep_scoring(monkeypatch)
    _warm_cache(client, csrf)
    assert len(batches) == 7

    _set_profile(email, {"skills": ["Python", "Kubernetes"]})
    with app.app_context():
        path_cache.invalidate(User.query.filter_by(email=email).one().id)
    _warm_cache(client, csrf)

    assert len(batches) == 14, "a new top skill re-keys every card"


def test_the_scrub_runs_before_anything_is_stored_and_a_fallback_never_is(
    client, monkeypatch
):
    """W-13's scrub, then storage -- and a card the scrub emptied is shown with
    the fallback sentence but never written to the table.
    """
    import json

    from app import app
    from solverah.repositories import path_narrative_repository

    email = "w16scrub@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_profile(email, {
        "career_status": "employed",
        "skills": ["Communication", "Python"],
        "experience": [{"position": "Software Engineer", "company": "Acme"}],
    })
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    monkeypatch.setattr(path_scoring_mod, "score_paths", MagicMock(return_value=SCORED_PATHS))
    answer = {
        "suggestions": [
            {
                "onet_code": "11-2021.00",
                "title": "Marketing Managers",
                "why_text": "You would own campaigns end to end, making it a strong fit.",
                "profile_dimensions": ["Builds on Communication skills", "95% overlap"],
            },
            {
                "onet_code": "11-3021.00",
                "title": "IT Managers",
                "why_text": "A great fit.",
                "profile_dimensions": ["Fits you", "Top choice for you"],
            },
        ]
    }
    def create(*, messages, **_kwargs):
        # W-17: each of these two cards is its own completion now, so the
        # provider answers for the codes it was asked about and no others.
        asked = messages[1]["content"]
        choice = MagicMock()
        choice.message.content = json.dumps(
            {"suggestions": [s for s in answer["suggestions"] if s["onet_code"] in asked]}
        )
        response = MagicMock()
        response.choices = [choice]
        return response

    provider = MagicMock()
    provider.chat.completions.create.side_effect = create
    monkeypatch.setattr(path_narrative_mod, "_get_openai_client", lambda: provider)

    _warm_cache(client, csrf)
    body = client.get("/api/v1/me/path-suggestions").get_json()

    assert [s["why_text"] for s in body["suggestions"]] == [
        "You would own campaigns end to end.",
        "A different direction. Open it to see how it lines up with your skills.",
    ]
    with app.app_context():
        rows = path_narrative_repository.list_for_user(_user_id(email))
        stored = {row.onet_code: (row.why_text, row.profile_dimensions) for row in rows}
    assert stored == {
        "11-2021.00": (
            "You would own campaigns end to end.",
            ["Builds on Communication skills"],
        )
    }, "scrubbed before storage, and the fallback card not stored at all"


def test_a_narrator_outage_leaves_fallbacks_and_a_succeeded_job(client, monkeypatch):
    """The narrator raising is not the job failing: the scored list stands and
    each card takes the fallback sentence, at once rather than at the deadline."""
    csrf = _register_and_login(client, monkeypatch, email="w16outage@example.com")
    _set_profile("w16outage@example.com", {"career_status": "between_jobs"})
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    monkeypatch.setattr(path_scoring_mod, "score_paths", MagicMock(return_value=SCORED_PATHS))
    monkeypatch.setattr(
        path_narrative_mod,
        "generate_narratives",
        MagicMock(side_effect=RuntimeError("OPENAI_API_KEY is not set")),
    )

    job_id = _post_job(client, csrf)
    body = _poll(client, job_id)

    assert body["status"] == "succeeded"
    assert body["result"]["narration_pending"] is False
    assert [s["why_text"] for s in body["result"]["suggestions"]] == [
        "Uses your Communication.",
        "A different direction. Open it to see how it lines up with your skills.",
    ]


def test_a_narration_whose_worker_died_resolves_after_the_deadline(client, monkeypatch):
    """Worker death, simulated as the narration never running at all.

    The job is `succeeded` (the reaper only fails queued/running rows, so it
    never touches it) with a result that says `narration_pending`. Within the
    deadline the poll says exactly that; past it, every read -- the job poll and
    `GET /me/path-suggestions` -- serves the fallback sentences and
    `narration_pending: false`, so the page stops shimmering. A reload after
    that scores again and narrates properly.
    """
    import datetime

    from solverah.services import intelligence_service, scoring_jobs

    csrf = _register_and_login(client, monkeypatch, email="w16dead@example.com")
    _set_profile("w16dead@example.com", {"career_status": "between_jobs"})
    mock_score, _ = _mock_scoring(monkeypatch)
    real_start = intelligence_service.start_narration
    monkeypatch.setattr(intelligence_service, "start_narration", lambda *_a, **_k: None)

    job_id = _post_job(client, csrf)
    pending = _poll(client, job_id)
    assert pending["status"] == "succeeded"
    assert pending["result"]["narration_pending"] is True
    assert [s["why_text"] for s in pending["result"]["suggestions"]] == ["", ""]
    from app import app

    with app.app_context():
        reaped = scoring_jobs.reap_stalled(older_than_minutes=0)
    assert reaped == 0, "the reaper must not fail a job whose cards were delivered"

    monkeypatch.setattr(intelligence_service, "NARRATION_DEADLINE", datetime.timedelta(0))
    stale = _poll(client, job_id)
    assert stale["result"]["narration_pending"] is False
    assert [s["why_text"] for s in stale["result"]["suggestions"]] == [
        "Uses your Communication.",
        "A different direction. Open it to see how it lines up with your skills.",
    ]
    cached = client.get("/api/v1/me/path-suggestions").get_json()
    assert cached["narration_pending"] is False
    assert cached["suggestions"] == stale["result"]["suggestions"]

    # The reload: the pending list is not served as a hit, and this time the
    # narration runs.
    monkeypatch.setattr(intelligence_service, "start_narration", real_start)
    monkeypatch.setattr(intelligence_service, "NARRATION_DEADLINE", datetime.timedelta(seconds=60))
    fresh = _poll(client, _post_job(client, csrf))
    assert fresh["result"]["narration_pending"] is False
    assert fresh["result"]["suggestions"][0]["why_text"] == (
        "Your skills align well with marketing leadership."
    )
    assert mock_score.call_count == 2


def test_the_deadline_rule_leaves_a_fresh_pending_list_alone():
    import datetime

    from solverah.services import intelligence_service

    now = datetime.datetime(2026, 9, 28, 12, 0, 0, tzinfo=datetime.timezone.utc)
    payload = {
        "suggestions": [
            {"onet_code": "11-2021.00", "why_text": "", "profile_dimensions": [],
             "overlapping_skills": ["SQL"]},
            {"onet_code": "11-3021.00", "why_text": "Written.", "profile_dimensions": ["a", "b"],
             "overlapping_skills": []},
        ],
        "generated_at": "2026-09-28T11:59:30Z",
        "narration_pending": True,
    }

    assert intelligence_service.resolve_stale_narration(payload, now) is payload

    later = now + datetime.timedelta(seconds=31)
    resolved = intelligence_service.resolve_stale_narration(payload, later)
    assert resolved["narration_pending"] is False
    assert [s["why_text"] for s in resolved["suggestions"]] == ["Uses your SQL.", "Written."]
    assert resolved["suggestions"][1]["profile_dimensions"] == ["a", "b"]
    assert payload["narration_pending"] is True, "a read never mutates the stored list"


# ---------------------------------------------------------------------------
# W-18 -- an O*NET summary on every card, from the first poll
# ---------------------------------------------------------------------------


def _summary(code: str) -> str:
    return "What a %s does, in one sentence." % code


@pytest.fixture()
def summaries_corpus(tmp_path, monkeypatch):
    """The committed fixture corpus, with a real `*.summaries.json` beside it.

    `score_paths` is doubled in these tests, so nothing else loads a corpus;
    `get_corpus` is pointed at this one so the service's lookup runs the real
    loader over a real file.
    """
    from pathlib import Path

    from backend.services import occupation_retrieval, occupation_summaries

    source = Path(__file__).parent / "fixtures" / "corpus"
    for name in (
        "onet_corpus_testfix.npy",
        "onet_corpus_testfix.json",
        "onet_corpus_testfix.zones.json",
    ):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    loaded = occupation_retrieval.load_corpus(tmp_path / "onet_corpus_testfix.npy")
    occupation_summaries.write_summaries_sidecar(
        loaded.matrix_path,
        occupation_summaries.SummariesTable(
            summaries={"15-00%02d.00" % i: _summary("15-00%02d.00" % i) for i in range(20)}
        ),
    )
    occupation_summaries.reset_summaries_cache()
    monkeypatch.setattr(occupation_retrieval, "get_corpus", lambda: loaded)
    yield loaded
    occupation_summaries.reset_summaries_cache()


def test_every_card_carries_its_summary_on_the_first_poll_before_any_sentence(
    client, monkeypatch, summaries_corpus
):
    """W-18's whole promise, on the real threaded path.

    The narrator is held, so the first poll is the moment a card appears with
    no sentence at all -- and it must already carry O*NET's summary. When the
    sentences land, the summary is the same string: it is added to, never
    swapped out. Fails before W-18: the card had no `summary` key.
    """
    import threading
    import time

    from app import app

    monkeypatch.setitem(app.config, "PATH_NARRATION_INLINE", False)
    csrf = _deep_profile(client, monkeypatch, "w18summary@example.com")
    _mock_deep_scoring(monkeypatch)
    release = threading.Event()
    entered = threading.Event()
    real_generate = path_narrative_mod.generate_narratives

    def held(candidates, ctx):
        entered.set()
        assert release.wait(10), "the test never released the narrator"
        return real_generate(candidates, ctx)

    monkeypatch.setattr(path_narrative_mod, "generate_narratives", held)
    codes = ["15-00%02d.00" % i for i in range(10)]

    try:
        job_id = _post_job(client, csrf)
        assert entered.wait(5), "the narration never started"
        first = _poll(client, job_id)["result"]
        assert first["narration_pending"] is True
        assert all(s["why_text"] == "" for s in first["suggestions"])
        assert [s["summary"] for s in first["suggestions"]] == [_summary(c) for c in codes]
        cached = client.get("/api/v1/me/path-suggestions").get_json()
        assert [s["summary"] for s in cached["suggestions"]] == [_summary(c) for c in codes]
    finally:
        release.set()

    deadline = time.monotonic() + 10
    while True:
        settled = _poll(client, job_id)["result"]
        if not settled["narration_pending"] or time.monotonic() > deadline:
            break
        time.sleep(0.05)

    assert settled["narration_pending"] is False
    assert [s["summary"] for s in settled["suggestions"]] == [_summary(c) for c in codes]
    assert [s["why_text"] for s in settled["suggestions"]] == [
        "Narrated %s." % c for c in codes
    ]


def test_no_summaries_sidecar_means_an_empty_summary_and_a_working_list(
    client, monkeypatch, summaries_corpus
):
    """The degrade: the file is optional, so its absence costs the line and
    nothing else -- the job succeeds and every card says `summary: ""`."""
    from backend.services import occupation_summaries

    occupation_summaries.summaries_sidecar_path(summaries_corpus.matrix_path).unlink()
    occupation_summaries.reset_summaries_cache()
    csrf = _deep_profile(client, monkeypatch, "w18nosummary@example.com")
    _mock_deep_scoring(monkeypatch)

    _warm_cache(client, csrf)
    body = client.get("/api/v1/me/path-suggestions").get_json()

    assert len(body["suggestions"]) == 10
    assert all(s["summary"] == "" for s in body["suggestions"])
    assert all("Narrated" in s["why_text"] for s in body["suggestions"])


# ---------------------------------------------------------------------------
# W-18 -- the narration poll at 0.5 s: its own limit, keyed per user
# ---------------------------------------------------------------------------

_NO_SUCH_JOB = "/api/v1/me/path-suggestion-jobs/00000000000000000000000000000000"


@pytest.fixture()
def enforcing(client):
    """The client with the TESTING rate-limit exemption switched off."""
    from app import app
    from solverah.extensions import limiter

    limiter.reset()
    app.config["TESTING"] = False
    try:
        yield client
    finally:
        app.config["TESTING"] = True
        limiter.reset()


def test_the_path_poll_limit_is_its_own_and_keeps_a_day_cap():
    """Raised for this route only, and the day cap restated rather than dropped
    (`@limiter.limit` overrides the global defaults)."""
    from solverah.api.v1 import assessments, intelligence, me

    assert intelligence.PATH_SUGGESTION_POLL_LIMIT == "300 per minute;10000 per day"
    assert assessments.POLL_LIMIT == "60 per minute;2000 per day"
    assert me.POLL_LIMIT == "60 per minute;2000 per day"


def test_a_minute_of_half_second_polls_is_never_refused(enforcing, monkeypatch):
    """One tab polling at 0.5 s for the full 60 s window is 120 requests. At
    W-17's 60 a minute the 61st was a 429, which the page treats as a poll
    error and stops on -- sentences that never arrive on screen."""
    _register_and_login(enforcing, monkeypatch, email="w18poll@example.com")

    statuses = [enforcing.get(_NO_SUCH_JOB).status_code for _ in range(130)]

    assert statuses == [404] * 130


def test_the_path_poll_is_budgeted_per_user_not_per_address(enforcing, monkeypatch):
    """Two people behind one office NAT share an IP. Keyed per IP, one user
    polling hard would exhaust the other's budget; keyed per user, it cannot.
    Both test clients arrive from the same address, which is the point."""
    from app import app

    _register_and_login(enforcing, monkeypatch, email="w18nat1@example.com")
    colleague = app.test_client()
    _register_and_login(colleague, monkeypatch, email="w18nat2@example.com")

    first = [enforcing.get(_NO_SUCH_JOB).status_code for _ in range(301)]
    other = colleague.get(_NO_SUCH_JOB).status_code

    assert first[:300] == [404] * 300
    assert first[300] == 429, "one user's minute budget is 300"
    assert other == 404, "a colleague on the same address kept their own budget"


def test_the_poll_key_is_the_hashed_identity_or_the_address(client, monkeypatch):
    """No email in a limiter key (production's storage is Redis), and a request
    with no usable token falls back to the address so `@jwt_required` can
    answer it with its own 401."""
    from app import app
    from solverah.api.v1.intelligence import _signed_in_user_key

    _register_and_login(client, monkeypatch, email="w18key@example.com")
    cookie = client.get_cookie("access_token_cookie")
    assert cookie is not None

    with app.test_request_context(
        "/api/v1/me/path-suggestion-jobs/x",
        headers={"Cookie": "access_token_cookie=%s" % cookie.value},
        environ_base={"REMOTE_ADDR": "10.0.0.7"},
    ):
        signed_in = _signed_in_user_key()
    with app.test_request_context(
        "/api/v1/me/path-suggestion-jobs/x", environ_base={"REMOTE_ADDR": "10.0.0.7"}
    ):
        anonymous = _signed_in_user_key()
    with app.test_request_context(
        "/api/v1/me/path-suggestion-jobs/x",
        headers={"Cookie": "access_token_cookie=not-a-jwt"},
        environ_base={"REMOTE_ADDR": "10.0.0.7"},
    ):
        forged = _signed_in_user_key()

    assert signed_in.startswith("user:") and "w18key" not in signed_in
    assert anonymous == "10.0.0.7"
    assert forged == "10.0.0.7"
    client.delete_cookie("access_token_cookie")
    assert client.get(_NO_SUCH_JOB).status_code == 401
