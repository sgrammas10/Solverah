"""The mm-q11 correction: the marker on new sittings, and the backfill of old ones.

`mm-q11` keyed `relationship` opposite to `mm-q9`/`mm-q10` until 2026-09-10
(MANAGER_PROFILE_ITEMS_BIAS_REVIEW.md, Finding 7). Correcting the item changes
what a `relationship` score *means*, and every sitting stored before the flip
holds a number computed under the old key.

Two mechanisms close that, and this file tests both:

* `result["scoring_key"]` stamps every sitting scored from now on, so a stored
  row says which key produced it. Its absence means the contaminated one.
* `Scripts/backfill_manager_match_scoring_key` re-derives the old rows from the
  answers they stored and stamps them.

The property that makes the second one legitimate is the one
:func:`test_a_backfilled_row_matches_a_fresh_submission_of_the_same_answers`
asserts: a backfilled row and a sitting submitted fresh today from the same
answers agree exactly on the deterministic half. If they ever disagree, the
backfill has invented a score rather than re-derived one.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from manager_match.score import SCORING_KEY

#: The contaminated anchors, frozen here rather than read from the item table.
#: Seeding a "v1 row" means reproducing what the scorer *used to* produce, and a
#: helper that read today's table would seed a corrected row and quietly prove
#: nothing. See `_seed_v1_submission`.
V1_MM_Q11_ANCHORS = {"a": 0.25, "b": 0.80}

#: A sitting whose `relationship` score differs under the two keys -- which is
#: the whole point of it. mm-q9 'b' and mm-q10 'a' take the close pole; mm-q11
#: 'a' takes "available and accessible", scored 0.25 under v1 and 0.80 under v2.
MM_ANSWERS = [
    {"question_id": "mm-q1", "choice": "b"},
    {"question_id": "mm-q2", "choice": "b"},
    {"question_id": "mm-q3", "choice": "a"},
    {"question_id": "mm-q4", "choice": "a"},
    {"question_id": "mm-q5", "choice": "a"},
    {"question_id": "mm-q6", "choice": "a"},
    {"question_id": "mm-q7", "choice": "b"},
    {"question_id": "mm-q8", "choice": "b"},
    {"question_id": "mm-q9", "choice": "b"},
    {"question_id": "mm-q10", "choice": "a"},
    {"question_id": "mm-q11", "choice": "a"},
    {"question_id": "mm-q12", "choice": "a"},
    {"question_id": "mm-q13", "choice": "a"},
    {"question_id": "mm-q14", "choice": "a"},
    {"question_id": "mm-q15", "choice": "a"},
]

VALID_LLM_RESPONSE = {
    "narrative": "You do your best work with a manager who knows you as a person.",
    "what_to_look_for": ["Ask how the manager builds rapport with the team"],
    "red_flags": ["A manager who only appears at review time"],
    "archetype_description": "Close working relationships are load-bearing for you.",
}

#: Keys the backfill replaces. Everything else in a stored result is LLM prose it
#: must leave alone.
DETERMINISTIC_KEYS = ("archetype", "dimension_scores", "scoring_key")


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email, password="Strongpass1!"):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "MM User",
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


def _mock_openai(monkeypatch, response_json=None):
    mock_client = MagicMock()
    payload = response_json if response_json is not None else VALID_LLM_RESPONSE
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(payload)
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)
    return mock_client


def _submit(client, csrf, answers):
    """Queue a scoring and poll it once -- terminal under the suite's eager execution."""
    queued = client.post(
        "/api/v1/assessments/manager_match/scoring-jobs",
        json={"answers": answers},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert queued.status_code == 202
    poll = client.get(
        "/api/v1/assessments/manager_match/scoring-jobs/%s" % queued.get_json()["job_id"]
    )
    assert poll.get_json()["status"] == "succeeded", poll.get_json()
    return poll.get_json()["result"]


def _user_id(email):
    from model import User

    return User.query.filter_by(email=email).first().id


def _v1_scoring(answers):
    """What `score_manager_match` returned for *answers* before the correction.

    The old anchors are put back on the scorer's own lookup for the duration of
    the call, so this reproduces the historical result through the real archetype
    rules rather than through a second copy of them that could drift. Restored in
    a `finally`, and deliberately not via `monkeypatch` -- `monkeypatch.undo()`
    unwinds every patch a test has made, including the provider stub these tests
    need to survive the call.

    The marker is stripped because no v1 row ever carried one; that absence is
    exactly what identifies them.
    """
    from manager_match import score

    original = score._SCORE_LOOKUP["mm-q11"]
    score._SCORE_LOOKUP["mm-q11"] = V1_MM_Q11_ANCHORS
    try:
        scoring = score.score_manager_match(answers)
    finally:
        score._SCORE_LOOKUP["mm-q11"] = original
    scoring.pop("scoring_key", None)
    return scoring


def _seed_v1_submission(user_id, *, answers, scoring, llm=None):
    """Write the row a ManagerMatch sitting left behind before the correction.

    Through `open_current`, the write doorway, so this cannot seed a row the
    application could not have produced -- and so the form registration the
    composite foreign key needs happens on the way in.
    """
    from model import db
    from solverah.domain import auth as auth_domain
    from solverah.repositories import assessment_repository
    from solverah.services import assessment_service

    submission = assessment_repository.open_current(
        user_id, "manager_match", assessment_service.CLIENT_FORM_VERSION
    )
    result = {**scoring, **(llm if llm is not None else VALID_LLM_RESPONSE)}
    assert "scoring_key" not in result, "a v1 row is defined by not having one"
    submission.answers = answers
    submission.result = result
    submission.narrative = result["narrative"]
    submission.status = "scored"
    submission.completed_at = submission.scored_at = auth_domain.utcnow()
    db.session.commit()
    return submission.public_id


def _stored_result(user_id):
    from solverah.repositories import assessment_repository

    return assessment_repository.current_submission(user_id, "manager_match").result


# ---------------------------------------------------------------------------
# The marker on sittings scored from now on
# ---------------------------------------------------------------------------

def test_a_new_submission_is_stamped_with_the_scoring_key(client, monkeypatch):
    """Absence of the marker is what identifies a contaminated row, so presence
    on every new one is what makes that inference safe."""
    csrf = _register_and_login(client, monkeypatch, "mm_marker@example.com")
    _mock_openai(monkeypatch)

    body = _submit(client, csrf, MM_ANSWERS)
    assert body["scoring_key"] == SCORING_KEY

    from app import app

    with app.app_context():
        assert _stored_result(_user_id("mm_marker@example.com"))["scoring_key"] == SCORING_KEY


def test_the_marker_reaches_the_result_endpoint_and_the_profile_document(client, monkeypatch):
    """Both surfaces serve the stored blob, so both must carry the era stamp."""
    csrf = _register_and_login(client, monkeypatch, "mm_surfaces@example.com")
    _mock_openai(monkeypatch)
    _submit(client, csrf, MM_ANSWERS)

    res = client.get("/api/v1/me/assessments/manager_match/result")
    assert res.status_code == 200
    assert res.get_json()["scoring_key"] == SCORING_KEY

    from app import app
    from solverah.repositories import profile_repository

    with app.app_context():
        document = profile_repository.load_document(_user_id("mm_surfaces@example.com"))
        assert document["manager_match_result"]["scoring_key"] == SCORING_KEY


def test_the_model_reply_cannot_shadow_the_deterministic_scoring(client, monkeypatch):
    """A marker a model reply could overwrite would not be a marker.

    The result is a merge of deterministic scoring and LLM prose. The scoring
    half wins: a reply that happens to contain `archetype`, `dimension_scores`
    or `scoring_key` must not be able to relabel which key produced the numbers.
    """
    csrf = _register_and_login(client, monkeypatch, "mm_shadow@example.com")
    _mock_openai(
        monkeypatch,
        response_json={
            **VALID_LLM_RESPONSE,
            "archetype": "The Impostor",
            "dimension_scores": {"relationship": 9.99},
            "scoring_key": "mm-v0",
        },
    )

    body = _submit(client, csrf, MM_ANSWERS)

    assert body["scoring_key"] == SCORING_KEY
    assert body["archetype"] != "The Impostor"
    assert body["dimension_scores"]["relationship"] != 9.99


# ---------------------------------------------------------------------------
# The backfill
# ---------------------------------------------------------------------------

def test_a_backfilled_row_matches_a_fresh_submission_of_the_same_answers(client, monkeypatch):
    """The property that makes re-deriving legitimate rather than a guess.

    One user's sitting is seeded as it was stored under the contaminated key;
    another user submits the identical answers today. After the backfill the two
    stored results must agree exactly on the deterministic half.
    """
    from app import app
    from Scripts import backfill_manager_match_scoring_key as backfill_script

    csrf = _register_and_login(client, monkeypatch, "mm_old@example.com")
    _mock_openai(monkeypatch)

    with app.app_context():
        old_scoring = _v1_scoring(MM_ANSWERS)
        _seed_v1_submission(_user_id("mm_old@example.com"), answers=MM_ANSWERS, scoring=old_scoring)

    # A second account submits the same answers now, under the corrected key.
    _mock_openai(monkeypatch)
    fresh_csrf = _register_and_login(client, monkeypatch, "mm_new@example.com")
    fresh = _submit(client, fresh_csrf, MM_ANSWERS)

    # The seeded row must genuinely be contaminated, or this test proves nothing.
    assert (
        old_scoring["dimension_scores"]["relationship"]
        != fresh["dimension_scores"]["relationship"]
    ), "the v1 and v2 keys score this sitting identically -- pick answers where they differ"

    with app.app_context():
        counts = backfill_script.backfill()
        assert counts["rescored"] == 1, counts
        assert counts["unusable_answers"] == 0, counts

        rescored = _stored_result(_user_id("mm_old@example.com"))

    for key in DETERMINISTIC_KEYS:
        assert rescored[key] == fresh[key], key


def test_the_backfill_preserves_the_llm_half_verbatim(client, monkeypatch):
    """It re-derives scores. It does not touch prose, and does not regenerate it."""
    from app import app
    from Scripts import backfill_manager_match_scoring_key as backfill_script

    _register_and_login(client, monkeypatch, "mm_prose@example.com")

    with app.app_context():
        user_id = _user_id("mm_prose@example.com")
        _seed_v1_submission(
            user_id, answers=MM_ANSWERS, scoring=_v1_scoring(MM_ANSWERS)
        )
        backfill_script.backfill()
        rescored = _stored_result(user_id)

    for key, value in VALID_LLM_RESPONSE.items():
        assert rescored[key] == value, key


def test_the_backfill_is_idempotent(client, monkeypatch):
    """A second run over a finished backfill rescores nothing and changes nothing."""
    from app import app
    from Scripts import backfill_manager_match_scoring_key as backfill_script

    _register_and_login(client, monkeypatch, "mm_twice@example.com")

    with app.app_context():
        user_id = _user_id("mm_twice@example.com")
        _seed_v1_submission(
            user_id, answers=MM_ANSWERS, scoring=_v1_scoring(MM_ANSWERS)
        )

        first = backfill_script.backfill()
        after_first = _stored_result(user_id)

        second = backfill_script.backfill()
        after_second = _stored_result(user_id)

    assert first["rescored"] == 1 and first["already_v2"] == 0, first
    assert second["rescored"] == 0 and second["already_v2"] == 1, second
    assert after_second == after_first


def test_a_dry_run_writes_nothing(client, monkeypatch):
    from app import app
    from Scripts import backfill_manager_match_scoring_key as backfill_script

    _register_and_login(client, monkeypatch, "mm_dry@example.com")

    with app.app_context():
        user_id = _user_id("mm_dry@example.com")
        _seed_v1_submission(
            user_id, answers=MM_ANSWERS, scoring=_v1_scoring(MM_ANSWERS)
        )
        before = dict(_stored_result(user_id))

        counts = backfill_script.backfill(dry_run=True)
        after = _stored_result(user_id)

    assert counts["rescored"] == 1
    assert after == before
    assert "scoring_key" not in after


@pytest.mark.parametrize(
    "answers",
    [
        pytest.param(None, id="missing"),
        pytest.param([], id="empty"),
        pytest.param({"question_id": "mm-q1", "choice": "a"}, id="not-a-list"),
        pytest.param(["mm-q1: a"], id="entries-are-not-mappings"),
        pytest.param(
            [{"question_id": "mm-q%d" % i, "choice": "a"} for i in range(1, 15)],
            id="fourteen-answers",
        ),
        pytest.param(
            [{"question_id": "mm-q%d" % i, "choice": "z"} for i in range(1, 16)],
            id="invalid-choice",
        ),
        pytest.param(
            [{"question_id": "unknown-q%d" % i, "choice": "a"} for i in range(1, 16)],
            id="unknown-question-ids",
        ),
    ],
)
def test_a_row_whose_answers_cannot_be_rescored_is_skipped_not_corrupted(
    client, monkeypatch, answers
):
    """Counted and named, never rewritten and never stamped.

    Leaving it unmarked is the honest outcome: the row *is* scored under the old
    key and nothing here can correct it. Stamping it v2 would make it
    indistinguishable from a row that was actually re-derived.
    """
    from app import app
    from Scripts import backfill_manager_match_scoring_key as backfill_script

    _register_and_login(client, monkeypatch, "mm_bad@example.com")

    with app.app_context():
        user_id = _user_id("mm_bad@example.com")
        public_id = _seed_v1_submission(
            user_id, answers=answers, scoring=_v1_scoring(MM_ANSWERS)
        )
        before = dict(_stored_result(user_id))

        counts = backfill_script.backfill()
        after = _stored_result(user_id)

    assert counts["rescored"] == 0, counts
    assert counts["unusable_answers"] == 1, counts
    assert counts["unusable_public_ids"] == [str(public_id)]
    assert after == before
    assert "scoring_key" not in after


def test_the_backfill_reports_rows_whose_archetype_moved(client, monkeypatch):
    """The stored narrative was written for the old archetype; the operator is told.

    Regenerating that prose would mean an LLM call per user, which this script
    deliberately does not make -- so the count is how the consequence stays
    visible instead of silent.
    """
    from app import app
    from Scripts import backfill_manager_match_scoring_key as backfill_script

    _register_and_login(client, monkeypatch, "mm_arch@example.com")

    with app.app_context():
        user_id = _user_id("mm_arch@example.com")
        old_scoring = _v1_scoring(MM_ANSWERS)
        _seed_v1_submission(user_id, answers=MM_ANSWERS, scoring=old_scoring)

        counts = backfill_script.backfill()
        rescored = _stored_result(user_id)

    moved = rescored["archetype"] != old_scoring["archetype"]
    assert counts["archetype_changed"] == (1 if moved else 0), counts


def test_the_backfill_reads_no_other_kind(client, monkeypatch):
    """`core` is not in scope and neither is any other instrument.

    `core` answers and dimension scores are behind `assessment_store` (D-01) and
    a `core` submission row carries null `result` and null `answers` under a
    check constraint -- but the reason this script cannot reach them is the
    query, which names `manager_match` and nothing else. `focus_type` is the
    control: a non-`core` kind that *does* store a result, and must come out
    untouched and unstamped.
    """
    from app import app
    from model import AssessmentForm, AssessmentSubmission, db
    from Scripts import backfill_manager_match_scoring_key as backfill_script
    from solverah.domain import auth as auth_domain
    from solverah.repositories import assessment_repository
    from solverah.services import assessment_service

    _register_and_login(client, monkeypatch, "mm_kinds@example.com")

    with app.app_context():
        user_id = _user_id("mm_kinds@example.com")

        focus = assessment_repository.open_current(
            user_id, "focus_type", assessment_service.CLIENT_FORM_VERSION
        )
        focus.result = {"archetype": "Deep Diver", "dimension_scores": {"depth": 0.9}}
        focus.status = "scored"
        focus.completed_at = focus.scored_at = auth_domain.utcnow()

        AssessmentForm.register("core", assessment_service.CLIENT_FORM_VERSION)
        db.session.add(
            AssessmentSubmission(
                user_id=user_id,
                kind="core",
                form_version=assessment_service.CLIENT_FORM_VERSION,
                status="scored",
                completed_at=auth_domain.utcnow(),
                scored_at=auth_domain.utcnow(),
            )
        )
        db.session.commit()

        counts = backfill_script.backfill()

        assert counts["considered"] == 0, counts
        assert assessment_repository.current_submission(user_id, "focus_type").result == {
            "archetype": "Deep Diver",
            "dimension_scores": {"depth": 0.9},
        }
        core = assessment_repository.current_submission(user_id, "core")
        assert core.result is None and core.answers is None


def test_a_backfilled_row_propagates_with_no_second_write(client, monkeypatch):
    """The rescore reaches every reader through the row it already read from.

    `profile_repository.load_document` merges `manager_match_result` out of
    `assessment_submissions` on every read -- unconditionally, so a stale copy
    left anywhere else cannot shadow it -- and `GET /me/assessments/manager_match/
    result` serves the same blob verbatim. So correcting the row is the whole
    propagation: there is no second place holding a copy for the backfill to
    chase.
    """
    from app import app
    from Scripts import backfill_manager_match_scoring_key as backfill_script
    from solverah.repositories import profile_repository

    csrf = _register_and_login(client, monkeypatch, "mm_prop@example.com")
    _mock_openai(monkeypatch)

    with app.app_context():
        user_id = _user_id("mm_prop@example.com")
        _seed_v1_submission(user_id, answers=MM_ANSWERS, scoring=_v1_scoring(MM_ANSWERS))

    # Both surfaces serve the contaminated numbers before the backfill runs.
    before = client.get("/api/v1/me/assessments/manager_match/result").get_json()
    assert "scoring_key" not in before

    with app.app_context():
        backfill_script.backfill()
        corrected = _stored_result(_user_id("mm_prop@example.com"))
        document = profile_repository.load_document(_user_id("mm_prop@example.com"))

    served = client.get("/api/v1/me/assessments/manager_match/result").get_json()

    assert served["scoring_key"] == SCORING_KEY
    assert served["dimension_scores"] == corrected["dimension_scores"]
    assert served["dimension_scores"] != before["dimension_scores"]
    assert document["manager_match_result"] == corrected
