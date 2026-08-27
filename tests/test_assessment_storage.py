"""Phase 2d: five products, one storage shape, and the doorway no wider than it was.

The contract fixture (`Scripts/capture_contract.py`) already proves the wire did
not move -- 44 responses, zero differences. What it cannot prove is anything that
is true *underneath* the wire, and that is what this file is for. Four claims:

**The five share one shape.** Work Pulse, WPLL, FocusType and ManagerMatch write
`assessment_submissions` rows, and so does the core assessment. Before this phase
the same question had to be asked of `user_intake` columns, profile-document keys,
and the person-side tables, in three different ways.

**Nothing reads the old homes.** Not "the new code prefers the new home" -- the
old ones are unreachable. The tests below plant data in `user_intake.wpl_*` and in
`profiles.extra`, exactly as a pre-2d account would have it, and assert the API
reports nothing. A migration that carried the data across but left a read path
behind would pass every contract check and still be half a phase.

**D-01's doorway did not get wider.** A `core` row in the shared table carries no
result and no answers, under a check constraint. The whole risk of unifying
storage was that the person-side payload would end up in a table four other
products read; it does not, and the database refuses to let it.

**The submission id is a join key now, not a coincidence.** `submission_id` on the
person-side rows is `assessment_submissions.public_id.hex` -- same 32 hex
characters on the wire, but the two tables join.
"""

import pytest

PASSWORD = "Strongpass1!"

WPLL_ANSWERS = [
    {"question_id": "wpll-q%d" % i, "option_id": "wpll-q%d-c" % i} for i in range(1, 6)
]
WP_ANSWERS = [
    {"question_id": "wp-q%d" % i, "option_id": "wp-q%d-b" % i} for i in range(1, 13)
]
WP_LLM_RESPONSE = {
    "narrative": "You do your best work in long stretches.",
    "emerging_signals": [],
    "archetype": "The Deep Worker",
    "archetype_description": "Sustained focus.",
}

#: Work Pulse and ManagerMatch both run on `OPENAI_WP_MODEL` and check for
#: different required keys, so one stubbed provider serving both has to satisfy
#: the union. These tests are about where the result is stored, not what is in
#: it; the per-instrument payloads are pinned in each instrument's own file.
BOTH_LLM_RESPONSE = dict(
    WP_LLM_RESPONSE,
    what_to_look_for=["clear written goals"],
    red_flags=["decisions that only happen in the room"],
)

FORM_TOKEN_SECRET = "test-secret-not-a-real-one"


@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    """`respondent_id_for_user` reads this at call time and has no default (D-05)."""
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", FORM_TOKEN_SECRET)


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns (csrf_token, user_id)."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    email = "storage@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Storage User",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        user_id = user.id

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"], user_id


def _stub_llm(monkeypatch, payload=None):
    from unittest.mock import MagicMock

    import json as _json

    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(
            content=_json.dumps(payload or WP_LLM_RESPONSE)))]
    )
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: client)


def _submit_core(client, csrf):
    """Answer the served form. Tokens are salted per respondent, so they cannot
    be hard-coded."""
    form = client.get("/api/v1/assessments/core/form")
    assert form.status_code == 200
    responses = {
        item["token"]: item["options"][0]["key"]
        for block in form.get_json()["blocks"]
        for item in block["items"]
    }
    return client.post(
        "/api/v1/assessments/core/submissions",
        json={"responses": responses},
        headers={"X-CSRF-TOKEN": csrf},
    )


# ── The five share one shape ────────────────────────────────────────────────


def test_every_instrument_lands_in_one_table(client, auth, monkeypatch):
    """The phase, in one assertion.

    Four kinds arrive through four different handlers with four different
    scorers, and `core` arrives through `assessment_store` behind D-01's
    doorway. One query finds all five.
    """
    csrf, user_id = auth
    _stub_llm(monkeypatch, BOTH_LLM_RESPONSE)
    headers = {"X-CSRF-TOKEN": csrf}

    client.post(
        "/api/v1/intake/claims",
        json={"mode": "session", "selected_statement_ids": ["dir-1"],
              "wpll_answers": WPLL_ANSWERS, "wpll_insight_text": "teaser"},
        headers=headers,
    )
    client.post("/api/v1/assessments/work_pulse/submissions",
                json={"answers": WP_ANSWERS}, headers=headers)
    client.post("/api/v1/assessments/focus_type/submissions",
                json=_FOCUS_TYPE_PAYLOAD, headers=headers)
    client.post("/api/v1/assessments/manager_match/submissions",
                json={"answers": _MM_ANSWERS}, headers=headers)
    assert _submit_core(client, csrf).status_code == 200

    from app import app
    from model import AssessmentSubmission

    with app.app_context():
        kinds = {
            row.kind
            for row in AssessmentSubmission.query.filter_by(user_id=user_id).all()
        }
        assert kinds == {"core", "work_pulse", "wpll", "focus_type", "manager_match"}


def test_a_retake_updates_the_row_and_a_core_retake_appends(client, auth, monkeypatch):
    """The one asymmetry, asserted on both sides.

    The four client-rendered instruments have exactly one current sitting, which
    is what `user_intake` and a profile-document key gave them before and what
    `uq_assessment_submissions_current` gives them now. `core` is excluded from
    that index because its sittings are append-only -- that is what keeps a score
    re-derivable when the scoring key changes.
    """
    csrf, user_id = auth
    _stub_llm(monkeypatch)
    headers = {"X-CSRF-TOKEN": csrf}

    for _ in range(2):
        assert client.post("/api/v1/assessments/work_pulse/submissions",
                           json={"answers": WP_ANSWERS}, headers=headers).status_code == 200
        assert _submit_core(client, csrf).status_code == 200

    from app import app
    from model import AssessmentSubmission

    with app.app_context():
        rows = AssessmentSubmission.query.filter_by(user_id=user_id).all()
        assert len([r for r in rows if r.kind == "work_pulse"]) == 1
        assert len([r for r in rows if r.kind == "core"]) == 2


def test_every_submission_names_a_registered_form_version(client, auth, monkeypatch):
    """`assessment_forms` is load-bearing, not a lookup table nobody joins to.

    The composite foreign key is what stops `form_version` being free text, and
    the write path registers a version on first use so a new item file is usable
    the moment it ships rather than after a deploy step.
    """
    csrf, _user_id = auth
    _stub_llm(monkeypatch)
    client.post("/api/v1/assessments/work_pulse/submissions",
                json={"answers": WP_ANSWERS}, headers={"X-CSRF-TOKEN": csrf})
    assert _submit_core(client, csrf).status_code == 200

    from app import app
    from model import AssessmentForm, AssessmentSubmission

    with app.app_context():
        registered = {(f.kind, f.version) for f in AssessmentForm.query.all()}
        for row in AssessmentSubmission.query.all():
            assert (row.kind, row.form_version) in registered


def test_losing_the_race_for_a_row_does_not_discard_the_caller_s_other_write(
    client, auth, monkeypatch
):
    """The collision recovery must unwind the failed INSERT and nothing else.

    `save_to_account` writes the statement selections to `user_intake` and *then*
    opens the WPLL submission. `get_or_create_user_intake`, which `open_current`
    replaced, recovered from a duplicate with a plain `db.session.rollback()` --
    safe only because it happened to be the first write in its transaction. Here
    it would throw away the selections the same request had just made and commit
    the submission without them, and the request would still answer 200.

    The race is forced rather than waited for: `current_submission` is stubbed to
    miss once, so the INSERT runs against a row that already exists and hits
    `uq_assessment_submissions_current` exactly as a real concurrent claim would.
    """
    csrf, user_id = auth
    headers = {"X-CSRF-TOKEN": csrf}
    claim = {"mode": "session", "wpll_answers": WPLL_ANSWERS,
             "wpll_insight_text": "teaser"}

    first = client.post(
        "/api/v1/intake/claims",
        json=dict(claim, selected_statement_ids=["dir-1"]),
        headers=headers,
    )
    assert first.status_code == 200

    from solverah.repositories import assessment_repository

    real = assessment_repository.current_submission
    missed = {"once": False}

    def _miss_once(uid, kind):
        if kind == "wpll" and not missed["once"]:
            missed["once"] = True
            return None
        return real(uid, kind)

    monkeypatch.setattr(assessment_repository, "current_submission", _miss_once)

    second = client.post(
        "/api/v1/intake/claims",
        json=dict(claim, selected_statement_ids=["sus-2", "dir-3"]),
        headers=headers,
    )
    assert second.status_code == 200
    assert missed["once"], "the collision path was never reached"

    from app import app
    from model import AssessmentSubmission, UserIntake

    with app.app_context():
        intake = UserIntake.query.filter_by(user_id=user_id).one()
        assert intake.selected_statement_ids == ["sus-2", "dir-3"]
        assert AssessmentSubmission.query.filter_by(
            user_id=user_id, kind="wpll"
        ).count() == 1


# ── Nothing reads the old homes ─────────────────────────────────────────────


def test_work_pulse_data_left_on_user_intake_is_not_read(client, auth):
    """A pre-2d account's `wpl_*` columns are inert.

    This plants exactly what an unmigrated row looks like. If any read path still
    reached for those columns, the session flag would be true and the result
    endpoint would answer 200 -- both of which would pass the contract diff,
    because the contract fixture's user has been through the *new* write path.
    """
    _csrf, user_id = auth

    from app import app
    from model import UserIntake, db
    from solverah.domain import auth as auth_domain

    with app.app_context():
        db.session.add(UserIntake(
            user_id=user_id,
            selected_statement_ids=[],
            wpll_answers=WPLL_ANSWERS,
            wpll_insight_text="stale teaser",
            wpll_completed_at=auth_domain.utcnow(),
            wpl_answers=WP_ANSWERS,
            wpl_narrative="stale narrative",
            wpl_result=WP_LLM_RESPONSE,
            wpl_completed_at=auth_domain.utcnow(),
        ))
        db.session.commit()

    flags = client.get("/api/v1/auth/session").get_json()["flags"]
    assert flags["wpl_completed"] is False
    assert flags["wpll_completed"] is False

    assert client.get("/api/v1/me/assessments/work_pulse/result").status_code == 404

    catalogue = client.get("/api/v1/assessments").get_json()["data"]
    completed = {entry["kind"] for entry in catalogue if entry["completed"]}
    assert completed == set()


def test_a_result_left_in_the_profile_document_is_not_read(client, auth):
    """A stale `manager_match_result` in `profiles.extra` is shadowed, not served.

    The migration removes both keys, so this is the belt to that braces: the
    submission row is merged over the document unconditionally, which makes a key
    the migration missed harmless rather than silently authoritative.
    """
    _csrf, user_id = auth

    from app import app
    from model import db
    from solverah.repositories import profile_repository

    with app.app_context():
        profile_repository.update_document(
            user_id,
            lambda existing: {**existing,
                              "manager_match_result": {"archetype": "Stale"},
                              "focus_type_result": {"archetype": "Also stale"}},
        )
        db.session.commit()

    assert client.get("/api/v1/me/assessments/manager_match/result").status_code == 404
    assert client.get("/api/v1/me/assessments/focus_type/result").status_code == 404

    document = client.get("/api/v1/me/profile").get_json()["profile"]
    assert "manager_match_result" not in document
    assert "focus_type_result" not in document


def test_the_work_pulse_prompt_still_gets_its_claimed_wpll_context(
    client, auth, monkeypatch
):
    """The narrative prompt reads two things that moved in this phase.

    `wpll_answers` came off `user_intake` and is now the WPLL submission;
    `selected_statement_ids` stayed on `user_intake`, because statement
    selections are intake data and not an assessment. Neither reaches the wire,
    so the contract fixture cannot see this -- it stubs the prompt builders --
    and without this test the Work Pulse narrative could quietly lose its context
    with every response still byte-identical.
    """
    csrf, _user_id = auth
    _stub_llm(monkeypatch)
    headers = {"X-CSRF-TOKEN": csrf}

    client.post(
        "/api/v1/intake/claims",
        json={"mode": "session", "selected_statement_ids": ["dir-1", "sus-2"],
              "wpll_answers": WPLL_ANSWERS, "wpll_insight_text": "teaser"},
        headers=headers,
    )

    seen = {}

    def _capture(answers, wpll_answers=None, selected_statement_ids=None):
        seen["answers"] = answers
        seen["wpll_answers"] = wpll_answers
        seen["selected_statement_ids"] = selected_statement_ids
        return [{"role": "system", "content": "x"}]

    monkeypatch.setattr(
        "solverah.services.assessment_prompts.build_wp_narrative_prompt", _capture
    )

    assert client.post("/api/v1/assessments/work_pulse/submissions",
                       json={"answers": WP_ANSWERS},
                       headers=headers).status_code == 200

    assert seen["answers"] == WP_ANSWERS
    assert seen["wpll_answers"] == WPLL_ANSWERS
    assert seen["selected_statement_ids"] == ["dir-1", "sus-2"]


# ── D-01's doorway did not get wider ────────────────────────────────────────


def test_a_core_row_in_the_shared_table_carries_nothing(client, auth):
    """The condition the whole phase was allowed to proceed under.

    `assessment_submissions` is read by four other products' code paths and by
    the account export. A `core` row in it holds a kind, a version, a status and
    three timestamps -- no answers, no scores, no narrative. The check constraint
    is what makes that a guarantee rather than an omission somebody could fill in
    later without noticing.
    """
    csrf, user_id = auth
    assert _submit_core(client, csrf).status_code == 200

    from app import app
    from model import AssessmentSubmission, db
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        row = AssessmentSubmission.query.filter_by(
            user_id=user_id, kind="core"
        ).one()
        assert row.result is None
        assert row.answers is None
        assert row.narrative is None
        assert row.status == "scored"

        # And the database refuses the alternative.
        row.result = {"autonomy": 0.9}
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_the_core_submission_id_joins_the_two_tables(client, auth):
    """`submission_id` is `public_id.hex` -- 32 hex characters either way.

    It was a free-standing `uuid4()` before, unique but joined to nothing. The
    shape is unchanged on the wire, which is why the contract fixture masks it
    with a pattern that only matches 32 lowercase hex: a format change shows up
    as a diff instead of being hidden by the mask.
    """
    csrf, user_id = auth
    body = _submit_core(client, csrf).get_json()
    returned = body["submission_id"]

    assert len(returned) == 32
    assert returned == returned.lower()
    int(returned, 16)  # raises if it is not hex

    from app import app
    from assessment_store import export_person_side
    from model import AssessmentSubmission

    with app.app_context():
        row = AssessmentSubmission.query.filter_by(
            user_id=user_id, kind="core"
        ).one()
        assert row.public_id.hex == returned

        # The person-side rows carry the same value, read through the doorway.
        exported = export_person_side(user_id)
        assert {a["submission_id"] for a in exported["answers"]} == {returned}
        assert {s["submission_id"] for s in exported["dimension_scores"]} == {returned}


# ── Payloads, kept at the bottom because they are long and uninteresting ────

_MM_ANSWERS = [{"question_id": "mm-q%d" % i, "choice": "a"} for i in range(1, 16)]

_FOCUS_TYPE_PAYLOAD = {
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
