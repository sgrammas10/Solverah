"""The anonymous ``wpll`` teaser is retired (Sebastian's ruling C, 2026-11-23).

``/start`` was deleted that day, and its teaser result was the only caller of
the anonymous ``wpll`` scoring job -- an unauthenticated door that committed a
row and paid for an LLM call. Nothing signed in used the kind either, so it is
retired the way the original ``work_pulse`` was on 2026-10-02: its scorer is
deleted, every write door answers ``410 kind_retired`` before auth and before
the body is read, and sittings claimed onto an account before then stay where
they are and still count as completed.

This file used to drive the LLM scorer through the job pair. What it pins now is
that every door is shut, for a signed-out caller and a signed-in one alike, and
that a shut door spends nothing: no row, no provider call.
"""

import pytest

PASSWORD = "Strongpass1!"
EMAIL = "wpll-retired@example.test"

VALID_ANSWERS = [
    {"question_id": "wpll-q%d" % i, "option_id": "wpll-q%d-c" % i} for i in range(1, 6)
]

_ENQUEUE = "/api/v1/assessments/wpll/scoring-jobs"
_SUBMIT = "/api/v1/assessments/wpll/submissions"


# `respondent_id_for_user` reads this at call time and has no default by design
# (D-05). Set per file, never in conftest.py: test_assessment_form.py deletes it
# to prove the no-default rule holds.
@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


@pytest.fixture()
def provider(monkeypatch):
    """A stubbed provider whose call count is the assertion."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)
    return mock_client


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def csrf(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns its CSRF token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)
    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Retired Teaser",
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


def _assert_retired(resp):
    assert resp.status_code == 410
    assert resp.mimetype == "application/problem+json"
    body = resp.get_json()
    assert body["errors"] == [{"field": "kind", "code": "kind_retired"}]
    assert "replaced_by" not in body
    from solverah.services import assessment_service

    assert body["detail"] == assessment_service.RETIRED_WPLL_MESSAGE


def _assert_nothing_written(provider):
    from app import app
    from model import AssessmentSubmission, ScoringJob

    assert provider.chat.completions.create.call_count == 0
    with app.app_context():
        assert ScoringJob.query.count() == 0
        assert AssessmentSubmission.query.filter_by(kind="wpll").count() == 0


def test_the_anonymous_enqueue_is_refused_and_spends_nothing(client, provider):
    """The door ruling C closed: no row, no provider call."""
    _assert_retired(client.post(_ENQUEUE, json={"answers": VALID_ANSWERS}))
    _assert_nothing_written(provider)


def test_a_signed_in_enqueue_is_refused_too(client, csrf, provider):
    """Nothing signed in used the teaser, so it is not re-opened behind auth."""
    resp = client.post(
        _ENQUEUE, json={"answers": VALID_ANSWERS}, headers={"X-CSRF-TOKEN": csrf}
    )

    _assert_retired(resp)
    _assert_nothing_written(provider)


def test_the_refusal_comes_before_the_body_is_read(client, provider):
    """A body that would once have been a 422 or a 400 gets the same 410."""
    for body in ({}, {"answers": []}, {"answers": "nope"}):
        _assert_retired(client.post(_ENQUEUE, json=body))
    _assert_nothing_written(provider)


def test_the_anonymous_poll_is_refused(client):
    _assert_retired(client.get("%s/%s" % (_ENQUEUE, "0" * 32)))


def test_the_synchronous_submit_is_refused_without_a_pointer(client, provider):
    """It was a 410 `moved_to_scoring_jobs` with a forwarding address until the
    retirement; the operation is gone now, not moved, so there is no address."""
    _assert_retired(client.post(_SUBMIT, json={"answers": VALID_ANSWERS}))
    _assert_nothing_written(provider)


def test_the_catalogue_still_lists_it_and_every_kind_needs_auth(client, csrf):
    """Retired, not deleted: a sitting claimed before 2026-11-23 still counts.

    `requires_auth` stays on every entry so the shape holds, and it is true for
    all of them now that the one anonymous kind is retired.
    """
    entries = {e["kind"]: e for e in client.get("/api/v1/assessments").get_json()["data"]}

    assert "wpll" in entries
    assert all(entry["requires_auth"] is True for entry in entries.values())
