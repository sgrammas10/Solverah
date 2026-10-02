"""Assessment scoring and path suggestions off the request path: 202 + a poll.

Phase 3b built the job pair; 3c made it the only door.  ``POST
/assessments/{kind}/submissions`` and ``GET /me/path-suggestions`` used to call
OpenAI and O*NET *inside the request* -- the two handlers
``gunicorn.conf.py``'s 120-second timeout was actually raised for.

**The synchronous halves are closed and these tests say so.**
``test_the_synchronous_submit_for_a_moved_kind_is_gone`` and
``test_the_path_suggestions_get_computes_nothing_on_a_miss`` are the two that
fail if the old halves quietly come back -- a sync submit that starts answering
200 again, or a GET that computes on a miss, is the blocking provider call this
phase existed to remove.  Until the frontend moved (43a2024) the guards pointed
the other way, keeping the routes alive; the cutover is what flipped them.

**Three things here are guarding decisions rather than code**, and each has a
section below:

* **A9 -- the rate limit bounds provider spend, so it has to gate the enqueue.**
  Moving the OpenAI call to a worker does not move the invoice. A job endpoint
  with its own bucket would hand every instrument a second allowance reachable
  by queueing instead of submitting, which is A9 undone by a new door. The
  enqueue therefore shares one per-instrument budget with the submit, and
  ``test_queueing_and_submitting_share_one_budget`` is what proves it.
* **A12 -- five instruments, five result shapes, deliberately not
  interchangeable.** The poll is validated against the per-kind response model,
  not against a generic envelope, and a handle for one instrument is a 404 at
  another's path.
* **D-01 -- `core` has no job endpoint at all**, and that is asserted rather
  than assumed. It is the instrument carrying the six person dimension scores;
  a job row would put them in ``scoring_jobs.result`` and a poll endpoint would
  serve them back, which is a second place they live and a second way out.

**What eager execution can and cannot show.**  Under ``APP_ENV=testing`` the
scoring runs inline, so a job is already terminal by the time the 202 is
returned -- which makes the happy path easy and makes ``queued`` and
``running``, the two states a client actually polls, unreachable through the
endpoint. Those and the sweeps are driven against ``scoring_jobs`` directly.
Eager mode is also why the provider stub below works at all: it patches the
factory in *this* process, which is the process the task runs in. Under a real
worker it would intercept nothing. That is fine for a suite and it is not
evidence about the worker path -- see docs/ARCHITECTURE.md Phase 3b for the
end-to-end run through the compose worker.
"""

import json
from unittest.mock import MagicMock

import pytest

import backend.services.path_narrative as path_narrative_mod
import backend.services.path_scoring as path_scoring_mod
from backend.services.path_narrative import PathSuggestion
from backend.services.path_scoring import ScoredPath
from solverah.schemas.assessments import (
    SCORING_JOB_RESPONSES,
    SUBMISSION_RESPONSES,
    ScoringJobAccepted,
)
from solverah.schemas.intelligence import (
    PathSuggestionJobAccepted,
    PathSuggestionJobStatus,
)

PASSWORD = "Strongpass1!"
EMAIL = "scoring-jobs@example.test"
OTHER_EMAIL = "scoring-jobs-other@example.test"

WP_ANSWERS = [
    {"question_id": "wp-q%d" % i, "option_id": "wp-q%d-b" % i} for i in range(1, 13)
]
MM_ANSWERS = [{"question_id": "mm-q%d" % i, "choice": "a"} for i in range(1, 16)]
WPLL_ANSWERS = [
    {"question_id": "wpll-q%d" % i, "option_id": "wpll-q%d-c" % i} for i in range(1, 6)
]

FOCUS_TYPE_PAYLOAD = {
    "scene_1": ["big_project", "planning_doc", "urgent_client", "teammate_feedback",
                "emails", "admin_tasks"],
    "scene_2": {
        "now": ["email_client_important", "slack_mentioned"],
        "later": ["slack_teammate_question"],
        "ignore": ["email_newsletter", "calendar_meeting_invite", "task_new_ticket",
                   "task_planning_doc", "slack_team_channel", "email_system_report",
                   "calendar_team_lunch"],
    },
    "scene_3": {"deep_solo": 2.5, "planning": 0.5, "social": 0.5, "breaks": 0.25,
                "exploring": 0.25},
    "scene_4": {
        "now": ["deep_research"],
        "tomorrow": ["reply_teammate", "write_report_draft", "update_task_tracker",
                     "quick_call_unblock", "send_followup_email", "review_others_work",
                     "sketch_tomorrow_plan"],
        "avg_decision_time_ms": 500,
    },
    "scene_5": ["deep_work", "wind_down"],
}

WP_LLM_RESPONSE = {
    "narrative": "You bring deep focus to your work when conditions allow it.",
    "emerging_signals": [{"title": "Deep Focus Seeker", "description": "Needs quiet."}],
    "archetype": "Structured Deep Thinker",
    "archetype_description": "You build momentum through sustained effort.",
}

MM_LLM_RESPONSE = {
    "narrative": "You want a manager who explains the why.",
    "what_to_look_for": ["Clear written context"],
    "red_flags": ["Decisions with no stated reasoning"],
    "archetype_description": "You do your best work under an explainer.",
}

WPLL_LLM_RESPONSE = {"insight_text": "You do your sharpest thinking in quiet blocks."}

SCORED_PATHS = [
    ScoredPath(
        onet_code="11-2021.00",
        title="Marketing Managers",
        score=0.82,
        overlapping_skills=["Communication"],
    ),
]

PATH_SUGGESTIONS = [
    PathSuggestion(
        onet_code="11-2021.00",
        title="Marketing Managers",
        why_text="Your skills align well with marketing leadership.",
        profile_dimensions=["Builds on Communication skills"],
    ),
]


def _noop(*_args, **_kwargs):
    return None


# `respondent_id_for_user` reads this at call time and has no default by design
# (D-05). It is set here rather than in tests/conftest.py because
# test_assessment_form.py deliberately deletes it to prove the no-default rule
# holds, and a suite-wide default would make that test unable to fail.
@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


def _mock_openai(monkeypatch, payload):
    """Stub the provider in *this* process.

    Which is the whole of what it can do: under eager execution the task body
    runs here, so the patch is in scope. A real worker is a different process
    and would call OpenAI for real, which is why no test in this file claims
    anything about the worker path.
    """
    mock_client = MagicMock()
    choice = MagicMock()
    choice.message.content = json.dumps(payload)
    response = MagicMock()
    response.choices = [choice]
    mock_client.chat.completions.create.return_value = response
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)
    return mock_client


def _register(client, email):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Scoring Jobs",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()


def _login(client, email):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns its CSRF token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)
    _register(client, EMAIL)
    return _login(client, EMAIL)


@pytest.fixture()
def other_user(client, monkeypatch):
    """A second account, for the ownership-scoping tests. Not logged in."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)
    _register(client, OTHER_EMAIL)

    from app import app
    from model import User

    with app.app_context():
        return User.query.filter_by(email=OTHER_EMAIL).first().id


@pytest.fixture(autouse=True)
def clear_path_cache():
    from solverah.services import path_cache

    path_cache.clear()
    yield
    path_cache.clear()


def _queue(client, kind, body, csrf=None):
    headers = {"X-CSRF-TOKEN": csrf} if csrf else {}
    return client.post(
        "/api/v1/assessments/%s/scoring-jobs" % kind, json=body, headers=headers
    )


def _poll(client, kind, job_id):
    return client.get("/api/v1/assessments/%s/scoring-jobs/%s" % (kind, job_id))


def _submit(client, kind, body, csrf=None):
    headers = {"X-CSRF-TOKEN": csrf} if csrf else {}
    return client.post(
        "/api/v1/assessments/%s/submissions" % kind, json=body, headers=headers
    )


def _mock_path_scoring(monkeypatch):
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    monkeypatch.setattr(
        path_scoring_mod, "score_paths", MagicMock(return_value=SCORED_PATHS)
    )
    monkeypatch.setattr(
        path_narrative_mod, "generate_narratives", MagicMock(return_value=PATH_SUGGESTIONS)
    )


def _set_profile(email, extra):
    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile_repository.update_document(user.id, lambda existing: {**existing, **extra})
        db.session.commit()


# ── Which instruments moved, and which deliberately did not ─────────────────


def test_the_job_eligible_kinds_are_exactly_the_provider_scored_ones():
    """`JOB_ELIGIBLE_KINDS` is a literal; this is what keeps it honest.

    The three that move are the three whose scoring blocks on OpenAI. If a sixth
    instrument is added as `scored_by="llm"` and nobody decides whether it
    queues, this fails rather than leaving the decision unmade.
    """
    from solverah.services import assessment_service, scoring_jobs

    llm_scored = {
        kind.key
        for kind in assessment_service.ASSESSMENT_KINDS
        if kind.scored_by == "llm"
    }

    assert set(scoring_jobs.JOB_ELIGIBLE_KINDS) == llm_scored


def test_every_job_eligible_kind_has_its_own_response_model():
    """A12 from the schema side.

    An instrument with a job endpoint but no entry in `SCORING_JOB_RESPONSES`
    would be documented by the union as "one of these three" while returning a
    fourth shape.
    """
    from solverah.services import scoring_jobs

    assert set(SCORING_JOB_RESPONSES) == set(scoring_jobs.JOB_ELIGIBLE_KINDS)


@pytest.mark.parametrize("kind", ["core", "focus_type"])
def test_a_deterministic_instrument_has_no_job_endpoint(client, auth, kind):
    """`core` and `focus_type` score in-process; a job for them is all cost.

    404 rather than 400: the truthful statement is that the operation does not
    exist for these instruments, not that the caller asked for it wrongly.
    """
    body = FOCUS_TYPE_PAYLOAD if kind == "focus_type" else {"responses": []}

    assert _queue(client, kind, body, auth).status_code == 404
    assert _poll(client, kind, "00000000000000000000000000000000").status_code == 404


def test_core_is_absent_from_the_job_path_entirely(client, auth):
    """D-01, asserted rather than assumed.

    `core` is the instrument holding the six person dimension scores, and it
    withholds them even from its own respondent (A12). A job row would store a
    result in `scoring_jobs.result` and the poll would hand it back -- a second
    place those scores live and a second endpoint that emits them. The guard is
    that `core` never reaches this table at all.
    """
    from solverah.services import scoring_jobs

    assert "core" not in scoring_jobs.JOB_ELIGIBLE_KINDS
    assert "core" not in SCORING_JOB_RESPONSES
    assert _queue(client, "core", {"responses": []}, auth).status_code == 404


# ── The happy path, per instrument ──────────────────────────────────────────


def test_queueing_work_pulse_answers_202_with_a_handle(client, auth, monkeypatch):
    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    resp = _queue(client, "work_pulse", {"answers": WP_ANSWERS}, auth)

    assert resp.status_code == 202
    body = resp.get_json()
    ScoringJobAccepted.model_validate(body)
    assert body["job_id"]
    assert body["status_url"] == "/assessments/work_pulse/scoring-jobs/%s" % body["job_id"]
    # `status` is deliberately not asserted, for the reason 3a's equivalent test
    # gives: under eager execution the task has already run inline by the time
    # the route serialises, so the field reads `succeeded` here and `queued`
    # against a real worker. The poll is where status is worth asserting.


@pytest.mark.parametrize(
    "kind, payload, llm_response",
    [
        ("work_pulse", {"answers": WP_ANSWERS}, WP_LLM_RESPONSE),
        ("manager_match", {"answers": MM_ANSWERS}, MM_LLM_RESPONSE),
    ],
)
def test_polling_a_finished_job_returns_that_instruments_result_model(
    client, auth, monkeypatch, kind, payload, llm_response
):
    """A12 on the job path: `result` is the instrument's own model.

    Validated through the per-kind model rather than checked for "some JSON",
    which is exactly the assertion a generic `{status, result}` envelope would
    pass and a per-discriminator contract would not.
    """
    _mock_openai(monkeypatch, llm_response)

    job_id = _queue(client, kind, payload, auth).get_json()["job_id"]
    resp = _poll(client, kind, job_id)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "succeeded"
    assert body["error"] is None

    # The envelope validates, and so does the result under this kind's model.
    SCORING_JOB_RESPONSES[kind].model_validate(body)
    SUBMISSION_RESPONSES[kind].model_validate(body["result"])


def test_the_job_result_matches_what_the_service_scorer_returns(
    client, auth, monkeypatch
):
    """One scorer, however many doors.

    The worker calls `assessment_service.submit` -- until 3c the same function
    the synchronous handler called, and still the single dispatch every scoring
    goes through. The same answers through the job must produce byte-for-byte
    what the service produces directly; a second scorer written for the queue
    is the drift this forbids. Asserted at the service seam now that the
    synchronous door is a 410 tombstone.
    """
    import logging

    from app import app
    from model import User
    from solverah.services import assessment_service

    _mock_openai(monkeypatch, MM_LLM_RESPONSE)

    queued = _queue(client, "manager_match", {"answers": MM_ANSWERS}, auth)
    job_result = _poll(client, "manager_match", queued.get_json()["job_id"]).get_json()[
        "result"
    ]

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        direct = assessment_service.submit(
            assessment_service.find_kind("manager_match"),
            user,
            {"answers": MM_ANSWERS},
            logging.getLogger("test"),
        )

    assert direct.status == 200
    assert job_result == direct.body


@pytest.mark.parametrize("kind", ["work_pulse", "wpll", "manager_match"])
def test_the_synchronous_submit_for_a_moved_kind_is_gone(
    client, auth, monkeypatch, kind
):
    """The deletion, asserted -- the inverse of the guard that stood until 3c.

    410 rather than 404, because the kind exists and the operation used to; and
    a refusal rather than acceptance, because a 200 here would resurrect the
    blocking provider call this phase existed to remove. The problem document
    names the replacement so a client that missed the cutover is told the fix.
    """
    payload = {"answers": {"work_pulse": WP_ANSWERS, "wpll": WPLL_ANSWERS,
                           "manager_match": MM_ANSWERS}[kind]}

    resp = _submit(client, kind, payload, auth)

    assert resp.status_code == 410
    assert resp.mimetype == "application/problem+json"
    body = resp.get_json()
    assert body["type"] == "https://solverah.com/errors/gone"
    assert body["replaced_by"] == "/assessments/%s/scoring-jobs" % kind
    assert body["errors"] == [{"field": "kind", "code": "moved_to_scoring_jobs"}]


# ── wpll: the anonymous instrument ──────────────────────────────────────────


def test_wpll_can_be_queued_and_polled_without_a_jwt(client, monkeypatch):
    """The one instrument whose job has no owner.

    `wpll` is the pre-launch teaser and has no account to attach to, so the
    handle is the whole of the authorisation.
    """
    _mock_openai(monkeypatch, WPLL_LLM_RESPONSE)

    queued = _queue(client, "wpll", {"answers": WPLL_ANSWERS})
    assert queued.status_code == 202

    resp = _poll(client, "wpll", queued.get_json()["job_id"])

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "succeeded"
    SCORING_JOB_RESPONSES["wpll"].model_validate(body)
    assert body["result"]["insight_text"]


def test_an_owned_job_is_not_reachable_through_the_anonymous_lookup(
    client, auth, monkeypatch
):
    """`find_anonymous` filters on `user_id IS NULL`, and this is why.

    Without that filter an unauthenticated caller holding any handle could read
    an owned job through the one instrument that needs no JWT.
    """
    from app import app
    from model import ScoringJob, User, db
    from solverah.services import scoring_jobs

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        row = ScoringJob(
            user_id=user.id,
            job_type=scoring_jobs.ASSESSMENT,
            kind="wpll",
            payload={},
            status="succeeded",
            result={"insight_text": "owned"},
        )
        db.session.add(row)
        db.session.commit()
        handle = row.public_id.hex

        assert scoring_jobs.find_anonymous(handle, kind="wpll") is None


# ── Handles: scoping, and A12 read from the other end ───────────────────────


def test_a_job_handle_is_scoped_to_its_owner(client, auth, other_user, monkeypatch):
    """Somebody else's handle must be indistinguishable from one that does not exist."""
    from app import app
    from model import ScoringJob, db
    from solverah.services import scoring_jobs

    with app.app_context():
        row = ScoringJob(
            user_id=other_user,
            job_type=scoring_jobs.ASSESSMENT,
            kind="work_pulse",
            payload={},
            status="succeeded",
            result=dict(WP_LLM_RESPONSE),
        )
        db.session.add(row)
        db.session.commit()
        handle = row.public_id.hex

    assert _poll(client, "work_pulse", handle).status_code == 404


def test_a_handle_for_one_instrument_is_a_404_at_anothers_path(
    client, auth, monkeypatch
):
    """A12's per-discriminator promise, read from the poll side.

    A Work Pulse job served at the ManagerMatch path would answer under
    ManagerMatch's response model carrying a Work Pulse body -- the response
    model would be a label rather than a contract.
    """
    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    job_id = _queue(client, "work_pulse", {"answers": WP_ANSWERS}, auth).get_json()[
        "job_id"
    ]

    assert _poll(client, "work_pulse", job_id).status_code == 200
    assert _poll(client, "manager_match", job_id).status_code == 404


def test_a_malformed_handle_is_a_404_not_a_500(client, auth):
    assert _poll(client, "work_pulse", "not-a-uuid").status_code == 404


def test_polling_requires_a_jwt_for_the_authenticated_instruments(client):
    assert _poll(client, "work_pulse", "00000000000000000000000000000000").status_code == 401


# ── A9: the budget bounds provider spend, so it gates the enqueue ───────────
#
# This is the trap the phase brief names. The limit on a submit exists to bound
# what the instrument costs at the provider, per discriminator. Moving the call
# to a worker changes who waits for it and not what it costs, so a job endpoint
# with its own bucket hands every instrument a second allowance -- reachable by
# queueing instead of submitting -- and A9 is undone without a single line of it
# being edited.


@pytest.fixture()
def enforcing(client):
    """A client with the TESTING rate-limit exemption switched off."""
    from app import app
    from solverah.extensions import limiter

    limiter.reset()
    app.config["TESTING"] = False
    try:
        yield client
    finally:
        app.config["TESTING"] = True
        limiter.reset()


def test_the_enqueue_is_rate_limited(enforcing, auth, monkeypatch):
    """A user cannot queue a hundred Work Pulse scorings."""
    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    statuses = [
        _queue(enforcing, "work_pulse", {"answers": WP_ANSWERS}, auth).status_code
        for _ in range(6)
    ]

    assert statuses[:5] == [202] * 5
    assert statuses[5] == 429


def test_queueing_and_submitting_share_one_budget(enforcing, auth, monkeypatch):
    """A9, stated as a number -- and 3c's deletion did not delete the join.

    Five enqueues exhaust Work Pulse's 5-per-minute allowance; the sixth call
    is a *submit* to the closed door, and the limiter refuses it before the
    tombstone can answer. The `shared_limit` expression carrying this is the
    same one that keeps `core` and `focus_type` on their own per-kind budgets
    (trap: deleting the sync handling must not delete the shared-bucket
    accounting), so this failing means the accounting came off the route.

    Written as `limiter.limit(scope=...)` the key would be "{endpoint}:{scope}",
    which sub-divides one endpoint rather than joining two, and this test is
    what catches that.
    """
    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    for _ in range(5):
        assert _queue(enforcing, "work_pulse", {"answers": WP_ANSWERS}, auth).status_code == 202

    spent = _submit(enforcing, "work_pulse", {"answers": WP_ANSWERS}, auth)

    assert spent.status_code == 429


def test_submitting_then_queueing_spends_the_same_budget(enforcing, auth, monkeypatch):
    """The same join, exercised in the other direction.

    Since 3c the five submits are refused as 410s -- but a refused call still
    draws the shared bucket, so the sixth call, an *enqueue*, is a 429. That is
    the property worth keeping: if the tombstone ever stopped charging the
    bucket while the join stood, hammering the closed door would cost nothing;
    if it kept charging but the join broke, the enqueue would get a fresh
    allowance. One of the two orderings could pass by accident if only one
    route carried the shared scope, so both are asserted.
    """
    _mock_openai(monkeypatch, MM_LLM_RESPONSE)

    for _ in range(5):
        assert _submit(enforcing, "manager_match", {"answers": MM_ANSWERS}, auth).status_code == 410

    spent = _queue(enforcing, "manager_match", {"answers": MM_ANSWERS}, auth)

    assert spent.status_code == 429


def test_each_instrument_keeps_its_own_budget_on_the_job_path(
    enforcing, auth, monkeypatch
):
    """Exhausting Work Pulse must not spend ManagerMatch's allowance.

    The property A9 preserved when five handlers became one, asserted again for
    the operation that could have lost it a second time.
    """
    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    for _ in range(6):
        spent = _queue(enforcing, "work_pulse", {"answers": WP_ANSWERS}, auth)
    assert spent.status_code == 429

    _mock_openai(monkeypatch, MM_LLM_RESPONSE)
    other = _queue(enforcing, "manager_match", {"answers": MM_ANSWERS}, auth)

    assert other.status_code != 429


def test_the_path_suggestion_enqueue_is_rate_limited(enforcing, auth, monkeypatch):
    """The GET is unlimited and survives it; an enqueue would not.

    A synchronous fan-out is self-limiting -- the caller holds the connection
    and a repeat inside the cache window reaches no provider. An enqueue returns
    in milliseconds, so the budget has to live on this side.
    """
    _mock_path_scoring(monkeypatch)
    _set_profile(EMAIL, {"career_status": "employed"})

    statuses = [
        enforcing.post(
            "/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": auth}
        ).status_code
        for _ in range(11)
    ]

    assert statuses[:10] == [202] * 10
    assert statuses[10] == 429


# ── Validation happens before the enqueue, not in the worker ────────────────


@pytest.mark.parametrize(
    "kind, bad_body",
    [
        ("work_pulse", {"answers": [{"question_id": "wp-q1", "option_id": "wp-q1-b"}]}),
        ("manager_match", {"answers": [{"question_id": "mm-q1", "choice": "a"}]}),
        # Fifteen answers, so past the count: the precheck's run of the pure
        # scorer is what refuses this one (2026-10-02, manager-match F4).
        (
            "manager_match",
            {
                "answers": [
                    {"question_id": "mm-q%d" % (i + 1), "choice": "a"} for i in range(14)
                ]
                + [{"question_id": "mm-q99", "choice": "a"}]
            },
        ),
        ("wpll", {"answers": []}),
        # A null option_id: the rules engine cannot read one (2026-10-02, F10).
        ("wpll", {"answers": [{"question_id": "wpll-q1", "option_id": None}]}),
    ],
)
def test_a_malformed_body_is_refused_before_the_enqueue_with_the_scorers_error(
    client, auth, monkeypatch, kind, bad_body
):
    """`precheck` duplicates the submit guards; this is what stops it drifting.

    Without the pre-check the job route would answer 202 and turn an immediate,
    actionable 400 into a poll and a failure several seconds later. The drift
    guard used to compare the enqueue against the synchronous route; that door
    is a 410 now, so the copy is held against the scorer itself: a job forced
    past the precheck must fail with exactly the error the precheck answers,
    because both are quoting the same guard.
    """
    from app import app
    from model import ScoringJob, User, db
    from solverah.services import scoring_jobs

    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    queued = _queue(client, kind, bad_body, auth)
    assert queued.status_code == 400
    precheck_error = queued.get_json()["error"]

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        row = ScoringJob(
            user_id=None if kind == "wpll" else user.id,
            job_type=scoring_jobs.ASSESSMENT,
            kind=kind,
            payload=bad_body,
            status="queued",
        )
        db.session.add(row)
        db.session.commit()

        assert scoring_jobs.run(row.id) == scoring_jobs.FAILED

        # `run` writes the terminal state on its own Core connection; the
        # ORM instance in this session was loaded before that write and will
        # happily serve the stale `error=None` unless it is expired first.
        db.session.expire_all()
        assert db.session.get(ScoringJob, row.id).error == precheck_error


def test_a_refused_body_creates_no_job_row(client, auth, monkeypatch):
    """A 400 must not leave a queued row behind for the sweep to run later."""
    from app import app
    from model import ScoringJob

    _mock_openai(monkeypatch, WP_LLM_RESPONSE)
    _queue(client, "work_pulse", {"answers": []}, auth)

    with app.app_context():
        assert ScoringJob.query.count() == 0


# ── The states eager mode cannot reach, and the sweeps ──────────────────────


@pytest.fixture()
def queued_job(client, auth):
    """A queued Work Pulse job for the signed-in user, created without running it."""
    from app import app
    from model import ScoringJob, User, db
    from solverah.services import scoring_jobs

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        row = ScoringJob(
            user_id=user.id,
            job_type=scoring_jobs.ASSESSMENT,
            kind="work_pulse",
            payload={"answers": WP_ANSWERS},
            status="queued",
        )
        db.session.add(row)
        db.session.commit()
        return {"id": row.id, "public_id": row.public_id.hex, "user_id": user.id}


def test_a_queued_job_polls_as_queued_and_carries_no_result(client, auth, queued_job):
    resp = _poll(client, "work_pulse", queued_job["public_id"])

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "queued"
    assert body.get("result") is None


def test_a_second_worker_cannot_claim_a_running_job(
    client, auth, queued_job, monkeypatch
):
    """`task_acks_late` redelivers on a worker death, so the claim is the guard.

    One provider call on the second run is the assertion, and here it is the
    point rather than a nicety: a redelivered message that re-ran the scoring
    would be a second invoice for one submission.
    """
    from app import app
    from solverah.services import scoring_jobs

    provider = _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    with app.app_context():
        assert scoring_jobs.run(queued_job["id"]) == scoring_jobs.SUCCEEDED
        assert provider.chat.completions.create.call_count == 1

        assert scoring_jobs.run(queued_job["id"]) == "skipped"
        assert provider.chat.completions.create.call_count == 1


def test_a_provider_failure_is_reported_without_leaking_provider_detail(
    client, auth, queued_job, monkeypatch
):
    """A failed scoring must not put prompt text on a polling endpoint.

    Provider exceptions carry model names, request ids and prompt fragments --
    and the prompt for these instruments contains the user's own answers.
    """
    from app import app
    from solverah.services import scoring_jobs

    def _boom():
        raise RuntimeError(
            "openai.APIError: model gpt-4o-mini request req_abc123 prompt=<the answers>"
        )

    monkeypatch.setattr("solverah.infra.llm.get_openai_client", _boom)

    with app.app_context():
        assert scoring_jobs.run(queued_job["id"]) == scoring_jobs.FAILED

    resp = _poll(client, "work_pulse", queued_job["public_id"])

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "failed"
    assert "req_abc123" not in json.dumps(body)
    assert "gpt-4o-mini" not in json.dumps(body)


def test_a_terminal_job_no_longer_holds_the_submitted_answers(
    client, auth, queued_job, monkeypatch
):
    """The payload is dropped when the scoring finishes.

    The answers are in `assessment_submissions` by then; a second live copy is
    duplicate retention of assessment data with no reader.
    """
    from app import app
    from model import ScoringJob, db
    from solverah.services import scoring_jobs

    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    with app.app_context():
        scoring_jobs.run(queued_job["id"])
        assert db.session.get(ScoringJob, queued_job["id"]).payload == {}


def test_a_stalled_job_is_failed_rather_than_polled_forever(client, auth, queued_job):
    """A worker killed mid-scoring leaves a row nothing else will move."""
    import datetime

    from app import app
    from model import ScoringJob, db
    from solverah.services import scoring_jobs

    with app.app_context():
        row = db.session.get(ScoringJob, queued_job["id"])
        row.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=scoring_jobs.STALL_MINUTES + 1
        )
        db.session.commit()

        assert scoring_jobs.reap_stalled() == 1

    resp = _poll(client, "work_pulse", queued_job["public_id"])

    assert resp.get_json()["status"] == "failed"
    assert resp.get_json()["error"] == scoring_jobs.GENERIC_FAILURE


def test_a_recent_job_is_not_reaped(client, auth, queued_job):
    from app import app
    from solverah.services import scoring_jobs

    with app.app_context():
        assert scoring_jobs.reap_stalled() == 0

    assert _poll(client, "work_pulse", queued_job["public_id"]).get_json()["status"] == "queued"


def test_the_sweep_runs_jobs_whose_enqueue_was_lost(
    client, auth, queued_job, monkeypatch
):
    """A dropped enqueue is a delay, not a loss -- because the row is durable."""
    from app import app
    from solverah.tasks.scoring_tasks import sweep_scoring_jobs

    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    with app.app_context():
        assert sweep_scoring_jobs()["requeued"] == 1

    assert _poll(client, "work_pulse", queued_job["public_id"]).get_json()["status"] == "succeeded"


def test_terminal_jobs_are_purged_past_the_retention_window(client, auth, queued_job):
    """The table has no account to cascade from for `wpll`, so it needs a purge."""
    import datetime

    from app import app
    from model import ScoringJob, db
    from solverah.services import scoring_jobs

    with app.app_context():
        row = db.session.get(ScoringJob, queued_job["id"])
        row.status = "succeeded"
        row.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=scoring_jobs.PURGE_DAYS + 1
        )
        db.session.commit()

        assert scoring_jobs.purge_terminal() == 1
        assert ScoringJob.query.count() == 0


def test_a_recent_terminal_job_is_not_purged(client, auth, queued_job):
    from app import app
    from model import ScoringJob, db
    from solverah.services import scoring_jobs

    with app.app_context():
        db.session.get(ScoringJob, queued_job["id"]).status = "succeeded"
        db.session.commit()

        assert scoring_jobs.purge_terminal() == 0
        assert ScoringJob.query.count() == 1


# ── The schema holds the invariants the application could otherwise break ───


def test_an_ownerless_job_is_rejected_for_every_kind_but_wpll(client):
    """`ck_scoring_jobs_owner_required`, exercised.

    Anonymity is granted to one instrument by name in the schema rather than
    left to whichever handler happens to set `user_id`. An ownerless row of any
    other kind is a job nobody can be denied.
    """
    import sqlalchemy.exc

    from app import app
    from model import ScoringJob, db
    from solverah.services import scoring_jobs

    with app.app_context():
        db.session.add(
            ScoringJob(
                user_id=None,
                job_type=scoring_jobs.ASSESSMENT,
                kind="work_pulse",
                payload={},
                status="queued",
            )
        )
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_a_path_suggestion_job_cannot_carry_an_assessment_kind(client):
    """`ck_scoring_jobs_kind_matches_type`.

    A path-suggestion row carrying `kind='work_pulse'` would be served by the
    assessment poll under that instrument's response model.
    """
    import sqlalchemy.exc

    from app import app
    from model import ScoringJob, db
    from solverah.services import scoring_jobs

    with app.app_context():
        db.session.add(
            ScoringJob(
                user_id=None,
                job_type=scoring_jobs.PATH_SUGGESTIONS,
                kind="work_pulse",
                payload={},
                status="queued",
            )
        )
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            db.session.commit()
        db.session.rollback()


# ── Path suggestions ────────────────────────────────────────────────────────


def test_queueing_path_suggestions_answers_202_with_a_handle(client, auth, monkeypatch):
    _mock_path_scoring(monkeypatch)
    _set_profile(EMAIL, {"career_status": "employed"})

    resp = client.post("/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": auth})

    assert resp.status_code == 202
    body = resp.get_json()
    PathSuggestionJobAccepted.model_validate(body)
    assert body["status_url"] == "/me/path-suggestion-jobs/%s" % body["job_id"]


def test_polling_path_suggestions_returns_the_scored_paths(client, auth, monkeypatch):
    _mock_path_scoring(monkeypatch)
    _set_profile(EMAIL, {"career_status": "employed"})

    job_id = client.post(
        "/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": auth}
    ).get_json()["job_id"]

    resp = client.get("/api/v1/me/path-suggestion-jobs/%s" % job_id)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "succeeded"
    PathSuggestionJobStatus.model_validate(body)
    assert body["result"]["suggestions"][0]["onet_code"] == "11-2021.00"


def test_a_succeeded_path_job_warms_the_cache_the_get_reads(client, auth, monkeypatch):
    """The job computes, the GET serves -- and the work is done exactly once.

    Since 3c the cache a succeeded job stores into is the *only* thing `GET
    /me/path-suggestions` serves, so this pairing is the whole read path: a job
    then a read is one fan-out, not two.
    """
    _mock_path_scoring(monkeypatch)
    _set_profile(EMAIL, {"career_status": "employed"})

    client.post("/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": auth})

    assert path_scoring_mod.score_paths.call_count == 1

    resp = client.get("/api/v1/me/path-suggestions")

    assert resp.status_code == 200
    assert resp.get_json()["suggestions"]
    assert path_scoring_mod.score_paths.call_count == 1


def test_the_path_suggestions_get_computes_nothing_on_a_miss(
    client, auth, monkeypatch
):
    """The deletion, asserted -- the inverse of the guard that stood until 3c.

    The status code alone would not prove it: a handler that computed inline
    and *then* failed could also 404. The scorer's call count is what shows the
    fan-out never ran, and the pointer is what tells a client where the work
    went instead.
    """
    _mock_path_scoring(monkeypatch)
    _set_profile(EMAIL, {"career_status": "employed"})

    resp = client.get("/api/v1/me/path-suggestions")

    assert resp.status_code == 404
    assert path_scoring_mod.score_paths.call_count == 0
    body = resp.get_json()
    assert body["start_job_url"] == "/me/path-suggestion-jobs"


def test_a_missing_career_status_fails_the_job_with_the_same_reason(
    client, auth, monkeypatch
):
    """`career_status_not_set` is the 400 the GET answers; the job carries it too.

    The client's response to it is to prompt for the missing field, not to
    retry, so a generic failure string here would be a worse answer.
    """
    _mock_path_scoring(monkeypatch)

    job_id = client.post(
        "/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": auth}
    ).get_json()["job_id"]

    body = client.get("/api/v1/me/path-suggestion-jobs/%s" % job_id).get_json()

    assert body["status"] == "failed"
    assert body["error"] == "career_status_not_set"


def test_an_empty_profile_fails_the_job_with_profile_incomplete(
    client, auth, monkeypatch
):
    """The ACC-4 / S16.11 defect, fixed in F-4. A regression test for the wire.

    Before this, a profile with no job title and no skills produced an empty
    scored list, `intelligence_service` turned that into
    `500 "Unable to score career paths"`, and the SPA's `stateForFailure()` --
    which special-cases only `career_status_not_set` and `profile_incomplete` --
    fell through to a generic "something went wrong, try again" box. Retrying
    cannot add a job title. The frontend branch for this string already existed
    and was dead because the backend never sent it.

    `score_paths` is NOT mocked here: the typed `InsufficientProfile` it raises
    is the thing under test, and it is raised before any corpus, O*NET or
    OpenAI dependency is touched.
    """
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    monkeypatch.setattr(
        path_narrative_mod, "generate_narratives", MagicMock(return_value=PATH_SUGGESTIONS)
    )
    _set_profile(EMAIL, {"career_status": "employed", "experience": [], "skills": []})

    job_id = client.post(
        "/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": auth}
    ).get_json()["job_id"]

    body = client.get("/api/v1/me/path-suggestion-jobs/%s" % job_id).get_json()

    assert body["status"] == "failed"
    assert body["error"] == "profile_incomplete"
    assert body["error"] != "Unable to score career paths"


def test_a_scoring_outage_is_still_a_generic_failure_not_profile_incomplete(
    client, auth, monkeypatch
):
    """The other half of the F-4 split: transient failures must stay retryable.

    A profile that HAS signal but produces nothing -- an unreachable corpus, an
    embedding outage -- is a 500 the client should retry, and must not be
    mislabelled as the user's profile being incomplete.
    """
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    monkeypatch.setattr(path_scoring_mod, "score_paths", MagicMock(return_value=[]))
    _set_profile(
        EMAIL,
        {
            "career_status": "employed",
            "experience": [{"position": "Software Engineer", "endDate": "Present"}],
            "skills": ["Python"],
        },
    )

    job_id = client.post(
        "/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": auth}
    ).get_json()["job_id"]

    body = client.get("/api/v1/me/path-suggestion-jobs/%s" % job_id).get_json()

    assert body["status"] == "failed"
    assert body["error"] != "profile_incomplete"


def test_a_path_suggestion_handle_is_scoped_to_its_owner(client, auth, other_user):
    from app import app
    from model import ScoringJob, db
    from solverah.services import scoring_jobs

    with app.app_context():
        row = ScoringJob(
            user_id=other_user,
            job_type=scoring_jobs.PATH_SUGGESTIONS,
            payload={},
            status="succeeded",
            result={"suggestions": [], "career_status": "employed",
                    "generated_at": "2026-09-01T00:00:00Z"},
        )
        db.session.add(row)
        db.session.commit()
        handle = row.public_id.hex

    assert client.get("/api/v1/me/path-suggestion-jobs/%s" % handle).status_code == 404


def test_an_assessment_handle_is_not_a_path_suggestion_handle(
    client, auth, monkeypatch
):
    """`find_for_user` filters on `job_type`, not only on the owner.

    One table holds both job types, so without that filter a user's own Work
    Pulse job would be served by the path-suggestion poll under
    `PathSuggestionJobStatus`.
    """
    _mock_openai(monkeypatch, WP_LLM_RESPONSE)

    job_id = _queue(client, "work_pulse", {"answers": WP_ANSWERS}, auth).get_json()[
        "job_id"
    ]

    assert client.get("/api/v1/me/path-suggestion-jobs/%s" % job_id).status_code == 404


def test_the_path_suggestion_poll_requires_a_jwt(client):
    resp = client.get("/api/v1/me/path-suggestion-jobs/00000000000000000000000000000000")

    assert resp.status_code == 401


# ── The worker can actually reach the scorers ───────────────────────────────


def test_the_worker_entrypoint_keeps_the_repo_root_importable():
    """A worker that boots cleanly and then fails every task, as a test.

    Found by running a real job through the compose worker rather than by
    reading anything: the job was claimed, failed and written terminal
    correctly -- the mechanism worked and the scorer was simply not importable.

    The sequence this reproduces is Celery's. `celery` is an installed console
    script, so `sys.path[0]` is the script's directory and the repository root
    is absent. Celery resolves `--app` through `import_from_cwd`, whose
    `cwd_in_path` inserts the working directory *only if absent* and removes it
    again afterwards. So everything imported while `solverah.worker` is being
    imported resolves and is cached in `sys.modules`, and the worker looks
    healthy -- while the imports the services make lazily inside functions
    (`work_pulse`, `manager_match`, `focus_type`, `assessment_store`,
    `backend.services.*`) run after the path has been withdrawn and raise.

    This is why `solverah/worker.py` inserts the root *unconditionally*. The
    guarded version -- `if REPO_ROOT not in sys.path` -- reads as the careful
    one and is the broken one: at that moment the root is already on the path
    because Celery just put it there, so the insert is skipped and Celery's own
    `finally` then takes it away again. This test fails against that version.

    Run in a subprocess because it is about the state of `sys.path` at
    interpreter startup, which pytest has already made correct for itself.
    """
    import subprocess
    import sys
    import textwrap
    from pathlib import Path

    repo_root = str(Path(__file__).resolve().parents[1])

    program = textwrap.dedent(
        """
        import sys
        root = sys.argv[1]

        # A console script: the repository root is not on the path.
        sys.path[:] = [p for p in sys.path if p not in ("", ".", root)]

        # celery.utils.imports.cwd_in_path, entered.
        inserted = root not in sys.path
        if inserted:
            sys.path.insert(0, root)

        import solverah.worker  # noqa: F401  -- the entrypoint under test

        # cwd_in_path, exited: it removes only what it added.
        if inserted:
            try:
                sys.path.remove(root)
            except ValueError:
                pass

        # What a task body does, long after the above has unwound.
        import work_pulse.insight_engine       # noqa: F401
        import manager_match.score             # noqa: F401
        import focus_type.score                # noqa: F401
        import assessment_store                # noqa: F401
        import backend.services.path_scoring   # noqa: F401
        print("SCORERS REACHABLE")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", program, repo_root],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    assert "SCORERS REACHABLE" in result.stdout, (
        "a Celery worker would not be able to import the scorers:\n%s" % result.stderr[-2000:]
    )


def test_polling_is_not_throttled_by_the_global_default(enforcing, auth, queued_job):
    """A poll must survive being a poll.

    Measured before this limit was added: both job-poll endpoints 429'd after
    exactly 50 requests, because they inherited the global `50 per hour`
    default -- a budget a client polling every two seconds exhausts inside a
    single scoring, and one it shares with every other default-limited route the
    same browser is using.

    A poll is a single indexed-row read with no provider call, so A9's budgets do
    not reach it: they exist to bound provider spend and a poll spends nothing.
    60 consecutive polls is roughly two minutes at a two-second interval, which
    is longer than any scoring this queues.
    """
    statuses = [
        _poll(enforcing, "work_pulse", queued_job["public_id"]).status_code
        for _ in range(55)
    ]

    assert statuses == [200] * 55


def test_the_poll_limit_keeps_a_daily_backstop():
    """`@limiter.limit` overrides the defaults, so the day cap must be restated.

    Naming only a per-minute allowance would have removed the global
    `200 per day` while reading as a tightening -- the trap `SUBMISSION_LIMITS`
    documents for the submit route, one endpoint over.
    """
    from solverah.api.v1.assessments import POLL_LIMIT

    assert "per minute" in POLL_LIMIT
    assert "per day" in POLL_LIMIT
