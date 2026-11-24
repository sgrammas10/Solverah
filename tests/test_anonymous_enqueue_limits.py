"""No assessment enqueue is anonymous any more (ruling C, 2026-11-23).

**What this file used to pin.** `POST /assessments/wpll/scoring-jobs` was the
application's one unauthenticated door onto a paid provider: every accepted call
committed a `scoring_jobs` row and made a `gpt-4o-mini` request with no account
behind it. S1 gave it a per-IP limit with a burst term plus a global-key spend
ceiling (the 2026-09 audit fired 40 enqueues from one address in 49 seconds and
collected 40 `202`s).

**What it pins now.** `/start`, the door's only caller, was deleted on
2026-11-23 and `wpll` was retired with it. The anonymous door is gone, so the
controls that existed only for it are gone too -- and that removal is what is
asserted here: an anonymous enqueue gets the normal 401 (or the retired kind's
410) and writes nothing, and the enqueue carries one per-caller bucket and no
global-key ceiling, so nothing deployment-wide remains for a stranger to drain.

Enforcement itself -- that a limiter decorator fires at all -- is covered by
`tests/test_rate_limits.py` and `tests/test_scoring_jobs.py`.
"""

import pytest

from security import global_rate_limit_key
from solverah.api.v1 import assessments
from solverah.services import assessment_service

#: Flask-Limiter keys decorated limits by "<module>.<qualname>.<name>", which is
#: how a handler is identified independently of its URL rule.
_VIEW = "solverah.api.v1.assessments.%s.%s"
ENQUEUE = _VIEW % (("assessment_kind_scoring_job",) * 2)
SUBMIT = _VIEW % (("assessment_kind_submit",) * 2)

MM_ANSWERS = [{"question_id": "mm-q%d" % i, "choice": "a"} for i in range(1, 16)]


# `respondent_id_for_user` reads this at call time and has no default by design
# (D-05). Set per file, never in conftest.py.
@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


def _buckets_for(view, kind):
    """The distinct rate-limit buckets *view* would consult for *kind*.

    Read off the limit manager rather than off the decorators, because a limit
    that is declared but never attached is exactly the defect this codebase has
    already been bitten by once. Resolved inside a request context because the
    limit string and the scope are callables that read `{kind}` off `view_args`.
    """
    from app import app
    from flask import request
    from solverah.extensions import limiter

    with app.test_request_context("/api/v1/assessments/%s/scoring-jobs" % kind):
        request.view_args = {"kind": kind}
        limits = limiter.limit_manager.decorated_limits(view)
        buckets = {(lim.key_func, lim.scope_for(view, "POST")) for lim in limits}

    assert buckets, "no limits registered for %s -- has the view been renamed?" % view
    return buckets


@pytest.fixture()
def provider(monkeypatch):
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)
    return mock_client


@pytest.mark.parametrize(
    "kind, expected",
    [
        ("manager_match", 401),  # live and job-scored: the normal 401
        ("wpll", 410),           # retired: the door is gone for everyone
        ("work_pulse", 410),
        ("core", 404),           # no job operation exists for it
        ("focus_type", 404),
    ],
)
def test_an_anonymous_enqueue_is_refused_and_writes_nothing(client, provider, kind, expected):
    """Every kind, signed out: refused before a row or a provider call."""
    from app import app
    from model import ScoringJob

    resp = client.post(
        "/api/v1/assessments/%s/scoring-jobs" % kind, json={"answers": MM_ANSWERS}
    )

    assert resp.status_code == expected
    assert provider.chat.completions.create.call_count == 0
    with app.app_context():
        assert ScoringJob.query.count() == 0


def test_no_instrument_is_anonymous_any_more():
    """The registry field that made one kind anonymous is gone with it."""
    for kind in assessment_service.ASSESSMENT_KINDS:
        assert not hasattr(kind, "requires_auth"), kind.key


def test_the_anonymous_limit_entry_is_gone():
    """`wpll`'s per-IP limit was for the anonymous door. A retired kind draws
    the default bucket, like the retired `work_pulse`."""
    assert "wpll" not in assessments.SUBMISSION_LIMITS
    for kind in ("core", "focus_type", "manager_match"):
        assert assessments.SUBMISSION_LIMITS[kind] == assessments.DEFAULT_SUBMISSION_LIMIT


@pytest.mark.parametrize("kind", ["manager_match", "wpll"])
def test_the_enqueue_carries_one_per_caller_bucket_and_no_global_ceiling(kind):
    """The global-key ceiling bounded the anonymous spend. With no anonymous
    spend left, a deployment-wide counter would only be a way for one caller to
    close the door for everyone."""
    buckets = _buckets_for(ENQUEUE, kind)

    assert len(buckets) == 1
    assert not any(key is global_rate_limit_key for key, _ in buckets)


def test_the_submit_carries_no_global_ceiling():
    buckets = _buckets_for(SUBMIT, "wpll")

    assert len(buckets) == 1
    assert not any(key is global_rate_limit_key for key, _ in buckets)


def test_the_anonymous_helpers_are_deleted():
    """Not merely unused: a helper left behind is a door one decorator away."""
    for name in ("_anonymous_submission_scope", "_is_authenticated_kind", "_require_auth_for"):
        assert not hasattr(assessments, name), name
