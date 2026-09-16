"""``POST``/``DELETE /api/v1/me/path-feedback`` -- the inline card feedback loop (F-6).

Four things this file exists to prove, each of them a decision rather than an
implementation detail.

**Zero taps is the identity.** Design doc §3.2's product constraint is that an
elicitation which is abandoned must still produce a sensible default -- so the
scorer with no judgements has to return exactly what it returned before F-6
existed, and clearing has to put a user back there. Both halves are asserted
here; ``tests/test_path_scoring.py`` asserts the same thing one layer down.

**The two signals are different kinds of signal.** ``too_similar`` is a radius
and ``interesting`` is a direction, and the easy failure is to build the first
and call it done. The route tests here check the *wiring* -- that a verdict
reaches the scorer at all and that a dismissed card does not come back; the maths
is `tests/test_path_scoring.py`'s.

**It writes into the cache rather than invalidating it.** A judgement is not a
profile change, so the Tier-2 fits survive it and `GET /me/path-suggestions`
serves the re-ranked list rather than a 404. Getting this backwards would look
like nothing in development and would throw away every stored deep fit on every
tap in production.

**A tap costs zero LLM completions.** Measured, the re-rank is 3 ms and the
narrator is 1.4-4 seconds, so the narrator is not on this path: an existing
`why_text` is carried across and a newly surfaced card describes itself from the
skills the scorer already matched. A test is the only thing that stops a later
refactor from quietly putting a four-second LLM call back on a control the user
is expected to press repeatedly.

`score_paths` and `generate_narratives` are doubled in most cases here and run
for real in the two marked end-to-end, against the synthetic corpus
`tests/test_path_scoring.py` builds.
"""
from unittest.mock import MagicMock

import pytest

import backend.services.occupation_retrieval as retrieval
import backend.services.path_narrative as pn
import backend.services.path_scoring as ps
from backend.services.occupation_retrieval import CorpusUnavailable
from backend.services.path_narrative import PathSuggestion
from backend.services.path_scoring import InsufficientProfile, ScoredPath

EMAIL = "pathfeedback@example.com"
CODE = "15-1252.00"
OTHER = "15-1251.00"
RESIDUAL = "15-1299.99"

PROFILE = {
    "career_status": "employed",
    "skills": ["Python", "SQL"],
    "skill_levels": {"Python": "advanced", "SQL": "intermediate"},
    "experience": [{"position": "Software Engineer", "endDate": "Present"}],
    "path_preferences": {
        "move_intent": "adjacent",
        "seniority_intent": "open",
        "priority": "interesting_work",
    },
}


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
            "name": "Feedback User",
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
        profile_repository.update_document(user.id, lambda existing: {**existing, **extra})
        db.session.commit()


def _user_id(email: str = EMAIL) -> int:
    from app import app
    from model import User

    with app.app_context():
        return User.query.filter_by(email=email).first().id


def _rows(email: str = EMAIL):
    from app import app
    from solverah.repositories import path_feedback_repository

    with app.app_context():
        return path_feedback_repository.list_for_user(_user_id(email))


def _post(client, csrf, code=CODE, verdict="too_similar"):
    return client.post(
        "/api/v1/me/path-feedback",
        json={"onet_code": code, "verdict": verdict},
        headers={"X-CSRF-TOKEN": csrf},
    )


def _delete(client, csrf):
    return client.delete(
        "/api/v1/me/path-feedback", headers={"X-CSRF-TOKEN": csrf}
    )


def _scored(*codes) -> list:
    """Scored paths carrying the overlapping skills the real scorer computes.

    Not decoration: `_describe` builds a new card's "why" out of them, so a
    double that left them empty would exercise only the no-overlap fallback.
    """
    return [
        ScoredPath(
            onet_code=code,
            title="Role %s" % code,
            score=0.9 - i / 100,
            overlapping_skills=["Python", "SQL"],
        )
        for i, code in enumerate(codes)
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def corpus(monkeypatch):
    """The synthetic five-row corpus, so code validation is real code."""
    from tests.test_path_scoring import WORLD_ROWS, WORLD_ZONES, build_corpus

    built = build_corpus(WORLD_ROWS, WORLD_ZONES)
    monkeypatch.setattr(retrieval, "get_corpus", lambda: built)
    monkeypatch.setattr(ps, "get_corpus", lambda: built)
    return built


@pytest.fixture()
def mock_scorer(monkeypatch):
    """`score_paths` replaced by a counting double that records its feedback."""
    mock = MagicMock(return_value=_scored(CODE, OTHER))
    monkeypatch.setattr(ps, "score_paths", mock)
    return mock


@pytest.fixture()
def mock_narrator(monkeypatch):
    def _generate(candidates, _ctx):
        return [
            PathSuggestion(
                onet_code=c.onet_code,
                title=c.title,
                why_text="Because %s." % c.onet_code,
                profile_dimensions=["a", "b"],
            )
            for c in candidates
        ]

    mock = MagicMock(side_effect=_generate)
    monkeypatch.setattr(pn, "generate_narratives", mock)
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
    """`OnetClient()` refuses to construct without a key and the rescore builds
    one before it reaches the (mocked) scorer.

    CI parity: a developer with a populated `.env` gets this for free and every
    test below passes without the fixture; the runner sets five variables and has
    no `.env`, and would see a 500 in most of them. CLAUDE.md's warning, applied.
    """
    monkeypatch.setenv("ONET_API_KEY", "test-key")


# ---------------------------------------------------------------------------
# Auth, method, shape
# ---------------------------------------------------------------------------


def test_unauthenticated_post_returns_401(client):
    resp = client.post(
        "/api/v1/me/path-feedback", json={"onet_code": CODE, "verdict": "interesting"}
    )
    assert resp.status_code == 401


def test_unauthenticated_delete_returns_401(client):
    assert client.delete("/api/v1/me/path-feedback").status_code == 401


def test_a_write_without_the_csrf_header_is_refused(client, monkeypatch, mock_scorer):
    _register_and_login(client, monkeypatch)
    _set_profile(PROFILE)
    resp = client.post(
        "/api/v1/me/path-feedback", json={"onet_code": CODE, "verdict": "interesting"}
    )
    assert resp.status_code == 401
    assert mock_scorer.call_count == 0


def test_get_is_not_served(client, monkeypatch):
    _register_and_login(client, monkeypatch)
    assert client.get("/api/v1/me/path-feedback").status_code == 405


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_a_judgement_is_stored_and_the_list_comes_back(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    resp = _post(client, signed_in, verdict="interesting")
    assert resp.status_code == 200, resp.get_json()

    body = resp.get_json()
    assert [s["onet_code"] for s in body["suggestions"]] == [CODE, OTHER]
    # No narrative had been written for this card, so its "why" is built from the
    # skills the scorer already matched -- see `intelligence_service._describe`.
    assert body["suggestions"][0]["why_text"] == "Uses your Python and SQL."
    assert body["career_status"] == "employed"
    assert body["generated_at"].endswith("Z")
    assert body["feedback"] == {CODE: "interesting"}

    rows = _rows()
    assert len(rows) == 1
    assert (rows[0].onet_code, rows[0].verdict) == (CODE, "interesting")


def test_the_verdict_reaches_the_scorer(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    """The whole point of the route: a tap changes the scorer's input.

    Asserted on the call rather than on the output, because a double's output is
    whatever the double was told to return -- only the argument is evidence.
    """
    _post(client, signed_in, verdict="too_similar")
    _post(client, signed_in, code=OTHER, verdict="interesting")

    assert mock_scorer.call_args.kwargs["feedback"] == {
        CODE: "too_similar",
        OTHER: "interesting",
    }


def test_re_tapping_a_card_replaces_the_verdict_rather_than_adding_one(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    _post(client, signed_in, verdict="interesting")
    resp = _post(client, signed_in, verdict="too_similar")

    assert resp.get_json()["feedback"] == {CODE: "too_similar"}
    rows = _rows()
    assert len(rows) == 1, "a correction is not a second opinion"
    assert rows[0].verdict == "too_similar"
    assert rows[0].created_at is not None


@pytest.mark.parametrize("verdict", ["too_similar", "interesting", "not_for_me"])
def test_every_verdict_in_the_vocabulary_is_accepted(
    client, signed_in, corpus, mock_scorer, mock_narrator, verdict
):
    assert _post(client, signed_in, verdict=verdict).status_code == 200


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


def test_delete_clears_every_judgement_and_returns_the_default_list(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    _post(client, signed_in, verdict="too_similar")
    _post(client, signed_in, code=OTHER, verdict="interesting")
    assert len(_rows()) == 2

    resp = _delete(client, signed_in)
    assert resp.status_code == 200
    assert resp.get_json()["feedback"] == {}
    assert _rows() == []
    assert mock_scorer.call_args.kwargs["feedback"] == {}


def test_delete_with_nothing_to_clear_is_a_200_not_a_404(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    """The client is asking for a state, not deleting a row it named."""
    resp = _delete(client, signed_in)
    assert resp.status_code == 200
    assert resp.get_json()["feedback"] == {}
    assert resp.get_json()["suggestions"]


def test_one_user_clearing_does_not_touch_another(
    client, monkeypatch, corpus, mock_scorer, mock_narrator
):
    mine = _register_and_login(client, monkeypatch)
    _set_profile(PROFILE)
    _post(client, mine, verdict="interesting")

    theirs = _register_and_login(client, monkeypatch, email="other-fb@example.com")
    _set_profile(PROFILE, email="other-fb@example.com")
    _post(client, theirs, verdict="too_similar")
    _delete(client, theirs)

    assert _rows("other-fb@example.com") == []
    assert len(_rows(EMAIL)) == 1


# ---------------------------------------------------------------------------
# Caching: it writes INTO path_cache and invalidates nothing
# ---------------------------------------------------------------------------


def test_the_rescore_is_written_into_the_cache_the_get_serves(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    posted = _post(client, signed_in, verdict="interesting").get_json()

    served = client.get("/api/v1/me/path-suggestions")
    assert served.status_code == 200, "the GET must not 404 after a tap"
    assert served.get_json()["suggestions"] == posted["suggestions"]


def test_a_tap_does_not_throw_away_the_stored_deep_fits(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    """A judgement is not a profile change (BUILD_PLAN F-6).

    `path_fit_repository.invalidate` is called from every write that changes a
    scoring input derived from the profile. This route changes an input the
    scorer takes directly, and dropping the Tier-2 fits would mean paying four
    O*NET calls again for every card the user had already opened, on every tap.
    """
    from app import app
    from model import db
    from solverah.repositories import path_fit_repository

    user_id = _user_id()
    with app.app_context():
        path_fit_repository.store(user_id, CODE, {"fit_score": 0.5}, "fp")
        db.session.commit()

    _post(client, signed_in, code=OTHER, verdict="interesting")

    with app.app_context():
        assert len(path_fit_repository.list_for_user(user_id)) == 1


def test_the_narrator_is_never_called_on_a_tap(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    """**A tap costs zero LLM completions**, and that is a latency decision.

    Measured against the real API: `gpt-4o-mini` takes 1.4-1.7 s for a single
    narrative and 3.1-3.7 s for five, while the re-rank itself is 3 ms. Putting
    that on a control the user presses repeatedly would make an "inline"
    feedback loop settle seconds after the tap. `_describe` carries existing
    narratives forward and builds a concrete line from the matched skills for
    anything new.

    Without this test a later refactor could put the narrator back and nothing
    else in the suite would notice -- it would simply be slow.
    """
    _post(client, signed_in, verdict="interesting")
    mock_scorer.return_value = _scored(OTHER, CODE)
    _post(client, signed_in, code=OTHER, verdict="interesting")

    assert mock_narrator.call_count == 0


def test_an_existing_narrative_is_carried_across_the_re_rank(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    """Prose the user has been reading must not change under them.

    A `why_text` is a function of (occupation, profile) and a tap moves neither,
    so a card that was on the list keeps exactly the words it had -- including
    the LLM-written ones the cold generation produced.
    """
    from app import app
    from solverah.services import path_cache

    with app.app_context():
        path_cache.store(
            _user_id(),
            {
                "suggestions": [
                    {
                        "onet_code": CODE,
                        "title": "Software Developers",
                        "why_text": "Written by the narrator, once.",
                        "profile_dimensions": ["a", "b"],
                        "match_score": 0.9,
                    }
                ],
                "career_status": "employed",
                "generated_at": "2026-09-16T00:00:00Z",
            },
        )

    body = _post(client, signed_in, code=OTHER, verdict="interesting").get_json()
    carried = next(s for s in body["suggestions"] if s["onet_code"] == CODE)
    assert carried["why_text"] == "Written by the narrator, once."
    assert carried["profile_dimensions"] == ["a", "b"]


def test_a_new_card_describes_itself_from_the_skills_it_uses(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    """The same data the narrator would have been handed, rendered directly.

    `overlapping_skills` is computed per card by `score_paths` at no extra cost,
    and is what `path_narrative` writes from. Naming them is more concrete than
    most prose an LLM produces from the same input, and it costs microseconds.
    """
    mock_scorer.return_value = [
        ScoredPath(
            onet_code=CODE,
            title="Software Developers",
            score=0.9,
            overlapping_skills=["Python", "SQL", "Git", "Docker"],
        )
    ]
    body = _post(client, signed_in, verdict="interesting").get_json()
    # At most three named, so a card never turns into a skills dump.
    assert body["suggestions"][0]["why_text"] == "Uses your Python, SQL and Git."
    assert body["suggestions"][0]["profile_dimensions"] == [], (
        "an invented tag is worse than a missing one"
    )


def test_a_new_card_that_uses_none_of_the_skills_still_says_something(
    client, signed_in, corpus, mock_scorer, mock_narrator
):
    mock_scorer.return_value = [
        ScoredPath(onet_code=CODE, title="Software Developers", score=0.9)
    ]
    body = _post(client, signed_in, verdict="interesting").get_json()
    assert body["suggestions"][0]["why_text"].strip() != ""


# ---------------------------------------------------------------------------
# Errors -- every branch the SPA has a state for
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["maybe", "", "TOO_SIMILAR", "too similar"])
def test_an_unknown_verdict_is_400_invalid_verdict(
    client, signed_in, corpus, mock_scorer, verdict
):
    """A well-formed body carrying a value outside the vocabulary.

    Distinct from the 422 below, and the pair is the point: the schema decides
    whether the request *is* a judgement, and this route decides whether it is
    one of the three the scorer knows how to use. Answering both the same way
    would make a client bug and a vocabulary drift look alike.
    """
    resp = client.post(
        "/api/v1/me/path-feedback",
        json={"onet_code": CODE, "verdict": verdict},
        headers={"X-CSRF-TOKEN": signed_in},
    )
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "invalid_verdict"}
    assert _rows() == []


@pytest.mark.parametrize(
    "body",
    [
        {"onet_code": CODE},
        {"verdict": "interesting"},
        {"onet_code": CODE, "verdict": None},
        {"onet_code": None, "verdict": "interesting"},
        {"onet_code": 15, "verdict": "interesting"},
        {},
    ],
)
def test_a_body_that_is_not_a_judgement_is_422_from_the_schema(
    client, signed_in, corpus, mock_scorer, body
):
    """The request schema is the first gate and answers before the handler runs.

    Both fields are required strings on `PathFeedbackRequest`, so a missing one,
    a null one or a number is a Part 5.1 problem document rather than one of this
    route's own error strings -- the same enforcement every documented request
    body on this blueprint gets, and not something F-6 restates by hand.
    """
    resp = client.post(
        "/api/v1/me/path-feedback", json=body, headers={"X-CSRF-TOKEN": signed_in}
    )
    assert resp.status_code == 422
    assert _rows() == []


@pytest.mark.parametrize("code", ["not-a-code", "15-1252", "", "151252.00", "15-1252.0"])
def test_a_malformed_code_is_404_invalid_onet_code(
    client, signed_in, corpus, mock_scorer, code
):
    resp = client.post(
        "/api/v1/me/path-feedback",
        json={"onet_code": code, "verdict": "interesting"},
        headers={"X-CSRF-TOKEN": signed_in},
    )
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "invalid_onet_code"}


def test_a_code_outside_the_corpus_is_404_unknown_occupation(
    client, signed_in, corpus, mock_scorer
):
    resp = _post(client, signed_in, code="29-1141.00", verdict="interesting")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "unknown_occupation"}
    assert _rows() == []


def test_a_residual_bucket_is_404_unsupported_occupation(
    client, signed_in, corpus, mock_scorer
):
    """Retrieval never returns an "..., All Other" row, so a tap on one can only
    come from a hand-built request."""
    resp = _post(client, signed_in, code=RESIDUAL, verdict="interesting")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "unsupported_occupation"}


def test_a_malformed_code_is_refused_before_the_corpus_is_loaded(
    client, signed_in, monkeypatch, mock_scorer
):
    """F-5's ordering, and F-5's reason.

    A malformed code is a permanent client bug. Checking the corpus first would
    answer it `503 corpus_unavailable` for the whole duration of an S3 outage,
    and send the caller retrying something that will never work.
    """

    def _explode():
        raise CorpusUnavailable("no artifact")

    monkeypatch.setattr(retrieval, "get_corpus", _explode)
    resp = client.post(
        "/api/v1/me/path-feedback",
        json={"onet_code": "nonsense", "verdict": "interesting"},
        headers={"X-CSRF-TOKEN": signed_in},
    )
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "invalid_onet_code"}


def test_an_unreachable_corpus_is_503_corpus_unavailable(
    client, signed_in, monkeypatch, mock_scorer
):
    def _explode():
        raise CorpusUnavailable("no artifact")

    monkeypatch.setattr(retrieval, "get_corpus", _explode)
    resp = _post(client, signed_in, verdict="interesting")
    assert resp.status_code == 503
    assert resp.get_json() == {"error": "corpus_unavailable"}
    assert _rows() == [], "nothing is stored when the request cannot be served"


def test_no_career_status_is_400_career_status_not_set(
    client, monkeypatch, corpus, mock_scorer
):
    csrf = _register_and_login(client, monkeypatch)
    _set_profile({"skills": ["Python"]})
    resp = _post(client, csrf, verdict="interesting")
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "career_status_not_set"}


def test_an_unscoreable_profile_is_400_profile_incomplete(
    client, signed_in, corpus, monkeypatch
):
    monkeypatch.setattr(
        ps, "score_paths", MagicMock(side_effect=InsufficientProfile("nothing"))
    )
    resp = _post(client, signed_in, verdict="interesting")
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "profile_incomplete"}


def test_the_judgement_survives_a_failure_in_the_rescore(
    client, signed_in, corpus, monkeypatch
):
    """The commit is before the re-rank, not after, and that is deliberate.

    The tap is what the user asked for and it is small and durable; the shortlist
    is a cache. A narrator timeout must not silently discard the thing they said.
    """
    monkeypatch.setattr(
        ps, "score_paths", MagicMock(side_effect=RuntimeError("boom"))
    )
    resp = _post(client, signed_in, verdict="interesting")
    assert resp.status_code == 500
    assert len(_rows()) == 1


def test_an_empty_rescore_is_500_not_an_empty_list(
    client, signed_in, corpus, monkeypatch
):
    monkeypatch.setattr(ps, "score_paths", MagicMock(return_value=[]))
    resp = _post(client, signed_in, verdict="too_similar")
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


def test_twenty_per_minute_shared_across_both_methods(
    client, monkeypatch, corpus, mock_scorer, mock_narrator
):
    """A9, with the interaction taken into account.

    Twenty rather than the ten every other spending route on this blueprint
    carries: a shortlist is ten cards and a user working through them taps ten
    times in well under a minute, so a limit of ten would 429 the feature it is
    protecting. The bucket is SHARED with the DELETE because
    clear-then-tap-then-clear is one user doing one thing.
    """
    from app import app
    from solverah.extensions import limiter

    csrf = _register_and_login(client, monkeypatch)
    _set_profile(PROFILE)

    limiter.reset()
    app.config["TESTING"] = False
    try:
        statuses = [
            _post(client, csrf, code=CODE, verdict="interesting").status_code
            for _ in range(19)
        ]
        statuses.append(_delete(client, csrf).status_code)
        statuses.append(_delete(client, csrf).status_code)
    finally:
        app.config["TESTING"] = True
        limiter.reset()

    assert statuses[:20] == [200] * 20
    assert statuses[20] == 429


# ---------------------------------------------------------------------------
# End to end: the real scorer over the synthetic corpus
# ---------------------------------------------------------------------------


@pytest.fixture()
def real_stack(monkeypatch, corpus):
    """The real `score_paths`, over five hand-written vectors and a fake embedder.

    The embedding double is not optional here. Without an OpenAI client the
    anchor falls back to `OnetClient.search_occupations` -- which in this suite
    means a **live HTTP request to O*NET**, answered 403 by the placeholder key
    the autouse fixture sets, after which there is no query vector and the route
    500s. That failure is a test-environment artefact rather than a defect, and
    it is worth naming because it looks exactly like one.
    """
    from solverah.infra import llm
    from tests.test_path_scoring import TECH, FakeEmbeddings

    class _AllTech(dict):
        """Every text this profile produces embeds onto the tech cluster.

        A dict that answers every key, rather than a table of the exact document
        strings: those are `path_scoring`'s private composition rules, and a test
        that spelled them out would break on a wording change that is not a
        behaviour change.
        """

        def get(self, _key, _default=None):
            return TECH

    class _Fake:
        def __init__(self) -> None:
            self.calls = 0
            self.texts: list = []
            self.embeddings = FakeEmbeddings(_AllTech(), self)

    fake = _Fake()
    monkeypatch.setattr(llm, "get_openai_client", lambda: fake)
    monkeypatch.setattr(
        pn,
        "generate_narratives",
        MagicMock(
            side_effect=lambda candidates, _ctx: [
                PathSuggestion(
                    onet_code=c.onet_code,
                    title=c.title,
                    why_text="why",
                    profile_dimensions=["a", "b"],
                )
                for c in candidates
            ]
        ),
    )
    return corpus


def test_end_to_end_a_dismissed_card_does_not_come_back(client, signed_in, real_stack):
    """`too_similar` and `not_for_me` remove a card; `interesting` does not.

    Tapping "interesting" and watching the card vanish would be the single most
    confusing thing this feature could do, so it is pinned here rather than left
    to the scorer's docstring.
    """
    first = _delete(client, signed_in).get_json()["suggestions"]
    shown = [s["onet_code"] for s in first]
    assert shown, "zero taps must still yield a list"

    after = _post(client, signed_in, code=shown[0], verdict="too_similar").get_json()
    assert shown[0] not in [s["onet_code"] for s in after["suggestions"]]

    liked = _post(
        client, signed_in, code=shown[-1], verdict="interesting"
    ).get_json()
    assert shown[-1] in [s["onet_code"] for s in liked["suggestions"]]


def test_end_to_end_clearing_restores_the_zero_tap_list(client, signed_in, real_stack):
    """Design doc §3.2: zero answers must still yield the full default set.

    Proved as round-trip equality rather than as a non-empty list, because "the
    reset put it back" is the claim and only equality checks it.
    """
    default = _delete(client, signed_in).get_json()["suggestions"]
    codes = [s["onet_code"] for s in default]

    _post(client, signed_in, code=codes[0], verdict="too_similar")
    _post(client, signed_in, code=codes[1], verdict="not_for_me")
    changed = _post(
        client, signed_in, code=codes[-1], verdict="interesting"
    ).get_json()["suggestions"]
    assert [s["onet_code"] for s in changed] != codes

    restored = _delete(client, signed_in).get_json()["suggestions"]
    assert [s["onet_code"] for s in restored] == codes
