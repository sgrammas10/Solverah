"""DB-ledger regression tests for package G1: assessments and insights.

Four promises, each pinned against the real Postgres tables:

* **The core submit's cost does not grow with the dimensions.** The six scores
  are one ``INSERT ... ON CONFLICT DO UPDATE`` on the existing unique key, not a
  SELECT and a write per dimension, and the sitting's ``public_id`` comes back
  from the INSERT's RETURNING instead of a second read. Two first sittings at
  once both land: select-then-insert lost that race with an IntegrityError.
* **No paid provider call runs inside a transaction.** Work Pulse used to open
  (and flush) its submission row before the call, and every provider-scored
  path inherited the caller's user lookup, so a connection sat idle in
  transaction for the whole round trip. The state is recorded from inside the
  stubbed call itself -- the one moment that matters.
* **One profile key is written as one key.** ``culture_preferences`` and
  ``quizInsights`` go through ``update_extra_key``, which never reads the
  profile's lists; the stored value and the rule for when it is written are
  pinned unchanged.
* **Result reads skip the prose, and nothing reloads the user.** The result
  endpoints read the row without ``narrative`` and answer the same payload; a
  submit uses the id it was handed rather than reloading an expired user row
  after its own commit.

This file never names the person-side tables (tests/test_employer_visibility.py
scans string literals too). It writes through ``persist_submission`` and reads
through ``export_person_side`` -- the doorway, from both ends.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import json
import logging
import re
import threading
import time
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa

from tests.query_count import count_queries

PASSWORD = "Strongpass1!"
LOGGER = logging.getLogger("tests.dbopt.g1")

DIMENSIONS = ("autonomy", "pace", "collaboration", "feedback", "innovation", "decision")

WP_ANSWERS = [
    {"question_id": "wp-q%d" % i, "option_id": "wp-q%d-b" % i} for i in range(1, 13)
]
WP_RETAKE_ANSWERS = [
    {"question_id": "wp-q%d" % i, "option_id": "wp-q%d-a" % i} for i in range(1, 13)
]
MM_ANSWERS = [
    {"question_id": "mm-q%d" % i, "choice": "a" if i % 2 == 0 else "b"} for i in range(1, 16)
]
MP_ANSWERS = [
    {"question_id": "mp-q%d" % i, "choice": "a" if i % 2 == 0 else "b"} for i in range(1, 17)
]

WP_LLM_RESPONSE = {
    "narrative": "You do your best work in long uninterrupted stretches.",
    "emerging_signals": [{"title": "Deep Focus Seeker", "description": "Needs quiet."}],
    "archetype": "The Deep Worker",
    "archetype_description": "Sustained focus is where your output comes from.",
}
MM_LLM_RESPONSE = {
    "narrative": "You want a manager who explains the why.",
    "what_to_look_for": ["Clear written context"],
    "red_flags": ["Decisions with no stated reasoning"],
    "archetype_description": "You do your best work under an explainer.",
}
#: Work Pulse and ManagerMatch share OPENAI_WP_MODEL and check different
#: required keys, so a provider stub serving both has to carry the union.
BOTH_LLM_RESPONSE = dict(WP_LLM_RESPONSE, **MM_LLM_RESPONSE)

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

ONE_QUIZ = [
    {
        "key": "yourFutureYourWay",
        "title": "Your Future, Your Way",
        "items": [{"question": "What matters most?", "selected": "Growth"}],
    }
]
CAREER_QUIZ = [
    {
        "key": "earlyCareer",
        "title": "Quiz 1: Early Career",
        "items": [{"question": "What motivates you?", "selected": "Recognition"}],
    }
]
QUIZ_LLM_RESPONSE = {
    "overallInsight": {
        "summary": "Across everything, growth is the throughline.",
        "keyTakeaways": ["Growth-oriented"],
        "nextSteps": ["Seek a growth-path role"],
    },
    "insights": [
        {
            "key": "yourFutureYourWay",
            "title": "Your Future, Your Way",
            "summary": "You are drawn to roles with visible growth trajectories.",
            "keyTakeaways": ["Values growth"],
            "combinedMeaning": "Growth over stability.",
            "nextSteps": ["Ask about promotion timelines"],
        }
    ],
}
CAREER_LLM_RESPONSE = {
    "overallInsight": {"summary": "Career synthesis."},
    "insights": [
        {
            "key": "earlyCareer",
            "title": "Quiz 1: Early Career",
            "summary": "Drawn to fast-moving, hands-on roles.",
        }
    ],
}

#: The profile's list tables. ``update_document`` reads all four to assemble the
#: document it rewrites; a one-key write has no business with any of them.
PROFILE_LIST_TABLES = ("profile_experiences", "profile_educations", "profile_skills", "resumes")

SUBMISSION_NARRATIVE = "assessment_submissions.narrative"


# ── Fixtures and helpers ────────────────────────────────────────────────────


# `respondent_id_for_user` reads this at call time and has no default by design
# (D-05). Set here rather than in tests/conftest.py because test_assessment_form.py
# deliberately deletes it to prove the no-default rule holds.
@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


@pytest.fixture(autouse=True)
def _no_mail_or_audit(monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", lambda *a, **k: None)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", lambda *a, **k: None)


def _sign_in(client, email):
    """Register, confirm and log in *email*. Returns (write headers, user id)."""
    from app import app
    from model import User, db

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Ledger G1",
              "role": "job-seeker", "terms_accepted": True},
    )
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        user_id = user.id

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return {"X-CSRF-TOKEN": resp.get_json()["csrfToken"]}, user_id


def _account(email):
    """A bare users row, for the service-level tests that need no session cookie."""
    from app import app
    from model import User, db

    with app.app_context():
        user = User(email=email, password_hash="not-a-real-hash")
        db.session.add(user)
        db.session.commit()
        return user.id


def _provider(monkeypatch, payload, seen=None):
    """Stub the provider. With *seen*, every call first records the session's
    state -- the moment a real call would sit on the connection for seconds."""
    from model import db

    def _create(**_kwargs):
        if seen is not None:
            session = db.session()
            seen.append({
                "in_transaction": session.in_transaction(),
                "pending": sorted(
                    type(obj).__name__
                    for obj in (*session.new, *session.dirty, *session.deleted)
                ),
            })
        message = MagicMock()
        message.content = json.dumps(payload)
        return MagicMock(choices=[MagicMock(message=message)])

    client = MagicMock()
    client.chat.completions.create.side_effect = _create
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: client)
    return client


def _failing_provider(monkeypatch):
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("provider down")
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: client)
    return client


@contextlib.contextmanager
def _statements():
    """``count_queries`` for requests made with NO outer app context.

    The test client reuses an app context that is already pushed, so a request
    made inside one would share this test's session and identity map instead of
    getting its own, as it does in production. The context here lives only long
    enough to resolve the engine the counter listens on.
    """
    from app import app

    with app.app_context():
        counting = count_queries()
        statements = counting.__enter__()
    try:
        yield statements
    finally:
        counting.__exit__(None, None, None)


def _reads_of(statements, table):
    """The SELECTs in *statements* whose FROM clause starts at *table*."""
    source = re.compile(r"\bFROM\s+%s\b" % re.escape(table), re.IGNORECASE)
    return [
        s for s in statements
        if s.lstrip().upper().startswith("SELECT") and source.search(s)
    ]


def _touching_profile_lists(statements):
    pattern = re.compile(r"\b(%s)\b" % "|".join(PROFILE_LIST_TABLES))
    return [s for s in statements if pattern.search(s)]


def _queue(client, kind, answers, headers):
    return client.post(
        "/api/v1/assessments/%s/scoring-jobs" % kind, json={"answers": answers}, headers=headers
    )


def _poll(client, queued):
    return client.get("/api/v1" + queued.get_json()["status_url"])


def _document(user_id):
    from app import app
    from solverah.repositories import profile_repository

    with app.app_context():
        return profile_repository.load_document(user_id)


def _write_document(user_id, **keys):
    """Store *keys* through the whole-document path, as a profile save would."""
    from app import app
    from model import db
    from solverah.repositories import profile_repository

    with app.app_context():
        profile_repository.update_document(user_id, lambda doc: {**doc, **keys})
        db.session.commit()


def _extra_key(user_id, key):
    from app import app
    from solverah.repositories import profile_repository

    with app.app_context():
        return profile_repository.read_extra_key(user_id, key)


def _stored_row(user_id, kind):
    """The full current row as plain values, read independently of the code under test."""
    from app import app
    from solverah.repositories import assessment_repository

    with app.app_context():
        row = assessment_repository.current_submission(user_id, kind)
        if row is None:
            return None
        return {
            "status": row.status,
            "answers": row.answers,
            "result": row.result,
            "narrative": row.narrative,
            "completed_at": row.completed_at,
            "scored_at": row.scored_at,
        }


def _seed_manager_match(user_id):
    """A completed ManagerMatch sitting, through the sanctioned write path."""
    from app import app
    from model import db
    from solverah.domain import auth as auth_domain
    from solverah.repositories import assessment_repository
    from solverah.services import assessment_service

    with app.app_context():
        submission = assessment_repository.open_current(
            user_id, "manager_match", assessment_service.CLIENT_FORM_VERSION
        )
        submission.answers = MM_ANSWERS
        submission.result = {"archetype": "The Operator", "dimension_scores": {}}
        submission.narrative = "A narrative nobody on the playbook path reads."
        submission.status = "scored"
        submission.completed_at = submission.scored_at = auth_domain.utcnow()
        db.session.commit()


def _scored(key_version, score, *, confidence=0.9, tag="v2"):
    """A shaped ScoredSubmission. This file tests persistence, not the scorer."""
    from assessment_form import ScoredSubmission

    return ScoredSubmission(
        form_version="v2-2026-08-18",
        scoring_key_version=key_version,
        scores={d: score for d in DIMENSIONS},
        choices={"%s%d%s" % (d[:2], rung, tag): "A" for d in DIMENSIONS for rung in range(1, 5)},
        # Shaped like the real thing: feedback's confidence is pending (D-17(a)).
        confidences={d: (None if d == "feedback" else confidence) for d in DIMENSIONS},
    )


def _core_responses(client):
    """Answer the served form; tokens are salted per respondent."""
    form = client.get("/api/v1/assessments/core/form")
    assert form.status_code == 200
    return {
        item["token"]: item["options"][0]["key"]
        for block in form.get_json()["blocks"]
        for item in block["items"]
    }


# ── The core submit: one upsert for the six scores ──────────────────────────


def test_the_core_submit_sends_as_many_statements_for_one_dimension_as_for_six(
    client, monkeypatch
):
    """The ledger's query-in-loop, through the real route.

    The scorer runs for real and a wrapper keeps only its first N dimensions, so
    the two respondents differ in nothing but how many scores are written. Before
    the fix each dimension cost a SELECT and its own INSERT or UPDATE: a first
    sitting with six dimensions sent ten statements more than one with one.
    """
    import assessment_form

    real_submit_form = assessment_form.submit_form
    keep = {"count": len(DIMENSIONS)}

    def _first_dimensions_only(*args, **kwargs):
        full = real_submit_form(*args, **kwargs)
        kept = sorted(full.scores)[: keep["count"]]
        return dataclasses.replace(
            full,
            scores={key: full.scores[key] for key in kept},
            confidences={key: full.confidences[key] for key in kept},
        )

    monkeypatch.setattr(assessment_form, "submit_form", _first_dimensions_only)

    counts = {}
    for dimensions in (1, len(DIMENSIONS)):
        keep["count"] = dimensions
        headers, _user_id = _sign_in(client, "g1-core-%d@example.test" % dimensions)
        responses = _core_responses(client)
        for sitting in ("first", "retake"):
            with _statements() as sent:
                resp = client.post(
                    "/api/v1/assessments/core/submissions",
                    json={"responses": responses},
                    headers=headers,
                )
            assert resp.status_code == 200, resp.get_data(as_text=True)
            assert resp.get_json()["dimensions_scored"] == dimensions
            counts[(dimensions, sitting)] = len(sent)

    assert counts[(1, "first")] == counts[(len(DIMENSIONS), "first")], counts
    assert counts[(1, "retake")] == counts[(len(DIMENSIONS), "retake")], counts


def test_persist_submission_reads_nothing_and_takes_public_id_from_the_insert(
    client, seed_user
):
    """No SELECT at all: not per dimension, and not to learn the new ``public_id``.

    ``public_id`` is a database default (``uuidv7()``), so the value does not
    exist until the INSERT runs; the INSERT's RETURNING is where it comes back.
    The old ``refresh`` after the flush was a second round trip for it.
    """
    from app import app
    from assessment_form import scoring_key_version
    from assessment_store import persist_submission
    from model import db

    seed_user(7201)
    key = scoring_key_version()

    with app.app_context():
        with count_queries() as first_sitting:
            first_id = persist_submission(db, 7201, _scored(key, 0.4))
        db.session.commit()
        with count_queries() as retake:
            retake_id = persist_submission(db, 7201, _scored(key, 0.6, tag="rt"))
        db.session.commit()

    assert first_id != retake_id
    for statements in (first_sitting, retake):
        reads = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
        assert reads == [], statements
        sitting_inserts = [
            s for s in statements if s.startswith("INSERT INTO assessment_submissions")
        ]
        assert len(sitting_inserts) == 1, statements
        assert "RETURNING" in sitting_inserts[0] and "public_id" in sitting_inserts[0]
        upserts = [
            s for s in statements
            if "ON CONFLICT (user_id, dimension_key, scoring_key_version) DO UPDATE" in s
        ]
        assert len(upserts) == 1, statements
    assert len(first_sitting) == len(retake), (first_sitting, retake)


def test_a_retake_updates_each_score_in_place_and_touches_nothing_else(client, seed_user):
    """The stored values the upsert must reproduce, read back through the doorway.

    A retake under the same scoring key overwrites score, confidence and
    submission_id and refreshes scored_at, one row per dimension; the raw
    responses append; a superseded key's rows and another user's rows are left
    exactly as they were.
    """
    from app import app
    from assessment_form import scoring_key_version
    from assessment_store import export_person_side, persist_submission
    from model import db

    seed_user(7301, 7302)
    key, stale = scoring_key_version(), "v1-superseded+mean_pole"

    with app.app_context():
        first_id = persist_submission(db, 7301, _scored(key, 0.2, confidence=0.9))
        db.session.commit()
        persist_submission(db, 7301, _scored(stale, 0.1, confidence=0.5, tag="st"))
        db.session.commit()
        persist_submission(db, 7302, _scored(key, 0.3, confidence=0.7, tag="ou"))
        db.session.commit()
        before = export_person_side(7301)
        other_before = export_person_side(7302)

        retake_id = persist_submission(db, 7301, _scored(key, 0.8, confidence=0.25, tag="rt"))
        db.session.commit()
        after = export_person_side(7301)
        other_after = export_person_side(7302)

    def by_key(rows, version):
        return {
            row["dimension"]: row for row in rows if row["scoring_key_version"] == version
        }

    current_before = by_key(before["dimension_scores"], key)
    current_after = by_key(after["dimension_scores"], key)
    assert set(current_after) == set(DIMENSIONS)
    assert len([r for r in after["dimension_scores"] if r["scoring_key_version"] == key]) == 6
    for dimension, row in current_after.items():
        assert row["score"] == 0.8
        assert row["confidence"] == (None if dimension == "feedback" else 0.25)
        assert row["submission_id"] == retake_id
        assert current_before[dimension]["submission_id"] == first_id
        assert datetime.datetime.fromisoformat(row["scored_at"]) > (
            datetime.datetime.fromisoformat(current_before[dimension]["scored_at"])
        )

    assert by_key(after["dimension_scores"], stale) == by_key(before["dimension_scores"], stale)
    assert other_after == other_before
    assert len(after["answers"]) == len(before["answers"]) + 24
    assert {a["submission_id"] for a in after["answers"]} >= {first_id, retake_id}


def _release_when_waiting(engine, pid, release, deadline_seconds=20.0):
    """Set *release* once backend *pid* is waiting on a lock (or at the deadline)."""
    deadline = time.monotonic() + deadline_seconds
    with engine.connect() as watcher:
        while time.monotonic() < deadline:
            waiting = watcher.execute(
                sa.text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": pid},
            ).scalar()
            watcher.rollback()
            if waiting == "Lock":
                break
            time.sleep(0.05)
    release.set()


def test_two_first_sittings_at_once_both_land(client, seed_user):
    """The ledger's possible-race row, forced rather than waited for.

    A competing sitting writes its six scores and holds them uncommitted. This
    sitting then runs; once its backend is seen waiting on the competitor's
    lock, the competitor commits. Select-then-insert had already decided "no
    row" and failed on the unique key with an IntegrityError -- a 500 for a
    respondent who did nothing wrong. The upsert waits, then updates.
    """
    from app import app
    from assessment_form import scoring_key_version
    from assessment_store import export_person_side, persist_submission
    from model import AssessmentForm, db

    seed_user(7401)
    key = scoring_key_version()
    competitor_sitting, this_sitting = _scored(key, 0.25, tag="ca"), _scored(key, 0.75, tag="cb")

    with app.app_context():
        # Registered and committed up front, so the competitor's registration
        # holds no lock and the only contention left is the scores' unique key.
        AssessmentForm.register("core", competitor_sitting.form_version)
        db.session.commit()
        engine = db.engine

    flushed, release = threading.Event(), threading.Event()
    competitor_errors = []

    def competitor():
        try:
            with app.app_context():
                persist_submission(db, 7401, competitor_sitting)
                db.session.flush()
                flushed.set()
                release.wait(timeout=30)
                db.session.commit()
        except Exception as exc:  # noqa: BLE001 -- asserted below
            competitor_errors.append(exc)
        finally:
            flushed.set()

    rival = threading.Thread(target=competitor)
    rival.start()
    assert flushed.wait(timeout=30)

    failure = None
    with app.app_context():
        pid = db.session.execute(sa.text("SELECT pg_backend_pid()")).scalar()
        watcher = threading.Thread(target=_release_when_waiting, args=(engine, pid, release))
        watcher.start()
        try:
            submission_id = persist_submission(db, 7401, this_sitting)
            db.session.commit()
        except Exception as exc:  # noqa: BLE001 -- reported below
            failure = exc
            db.session.rollback()
        finally:
            release.set()
            watcher.join(timeout=30)
            rival.join(timeout=30)

        assert competitor_errors == []
        assert failure is None, "the second first-sitting failed: %r" % (failure,)

        scores = [
            row for row in export_person_side(7401)["dimension_scores"]
            if row["scoring_key_version"] == key
        ]

    assert len(scores) == 6
    assert {row["submission_id"] for row in scores} == {submission_id}
    assert {row["score"] for row in scores} == {0.75}


# ── Work Pulse: nothing held across the provider call ───────────────────────


def test_the_work_pulse_provider_call_holds_no_transaction(client, monkeypatch):
    """Recorded from inside the stubbed call, on a first sitting and a retake.

    Before: ``open_current`` ran first -- registering the form version, reading
    the row and, on a first sitting, flushing its INSERT -- so the connection sat
    idle in transaction (holding the new row's key, when there was one) for the
    whole paid round trip.
    """
    headers, _user_id = _sign_in(client, "g1-wp-txn@example.test")
    seen = []
    _provider(monkeypatch, WP_LLM_RESPONSE, seen)

    for answers in (WP_ANSWERS, WP_RETAKE_ANSWERS):
        queued = _queue(client, "work_pulse", answers, headers)
        assert queued.status_code == 202
        assert _poll(client, queued).get_json()["status"] == "succeeded"

    assert seen == [{"in_transaction": False, "pending": []}] * 2


def test_work_pulse_writes_culture_preferences_as_one_key(client, monkeypatch):
    """Same stored value, same rule (every successful sitting writes it), and the
    rest of the document untouched -- without reading the profile's lists.

    The value assertions come first so that, against the old code, they are
    shown to hold before the list-read assertion fails.
    """
    from work_pulse.derive_preferences import derive_culture_preferences

    headers, user_id = _sign_in(client, "g1-wp-prefs@example.test")
    _write_document(
        user_id,
        headline="Staff engineer",
        skills=["Python", "SQL"],
        experience=[{"company": "Acme", "position": "Engineer"}],
        culture_preferences={"pace": "stale value from an older sitting"},
        path_preferences={"avoid": ["sales"]},
    )
    before = _document(user_id)
    _provider(monkeypatch, WP_LLM_RESPONSE)

    sent_per_sitting = []
    for answers in (WP_ANSWERS, WP_RETAKE_ANSWERS):
        with _statements() as sent:
            queued = _queue(client, "work_pulse", answers, headers)
        sent_per_sitting.append(sent)
        assert queued.status_code == 202
        assert _poll(client, queued).get_json()["status"] == "succeeded"

        after = _document(user_id)
        assert after.pop("culture_preferences") == derive_culture_preferences(answers)
        assert after == {k: v for k, v in before.items() if k != "culture_preferences"}

    for sent in sent_per_sitting:
        assert _touching_profile_lists(sent) == []


def test_a_failed_second_commit_still_leaves_the_sitting_complete(client, monkeypatch):
    """The two-commit guarantee, unchanged by the reorder.

    Commit 1 (answers, completion, culture_preferences) lands; commit 2's failure
    is rolled back and logged, the job still answers with the result, and the
    result endpoint answers 422 -- "resubmit", not "take the assessment".
    """
    from work_pulse.derive_preferences import derive_culture_preferences

    headers, user_id = _sign_in(client, "g1-wp-commit2@example.test")
    _provider(monkeypatch, WP_LLM_RESPONSE)

    def _commit_two_fails(_user_id):
        raise RuntimeError("commit 2 fails")

    monkeypatch.setattr(
        "solverah.repositories.path_fit_repository.invalidate", _commit_two_fails
    )

    queued = _queue(client, "work_pulse", WP_ANSWERS, headers)
    poll = _poll(client, queued).get_json()
    assert poll["status"] == "succeeded"
    assert poll["result"] == WP_LLM_RESPONSE

    row = _stored_row(user_id, "work_pulse")
    assert row["status"] == "complete"
    assert row["answers"] == WP_ANSWERS
    assert row["completed_at"] is not None
    assert row["result"] is None and row["narrative"] is None and row["scored_at"] is None
    assert _extra_key(user_id, "culture_preferences") == derive_culture_preferences(WP_ANSWERS)

    pending = client.get("/api/v1/me/assessments/work_pulse/result")
    assert pending.status_code == 422


def test_a_work_pulse_provider_failure_writes_nothing(client, monkeypatch):
    headers, user_id = _sign_in(client, "g1-wp-fail@example.test")
    _failing_provider(monkeypatch)

    queued = _queue(client, "work_pulse", WP_ANSWERS, headers)
    poll = _poll(client, queued).get_json()

    assert poll["status"] == "failed"
    assert poll["error"] == "Unable to generate Work Pulse results"
    assert _stored_row(user_id, "work_pulse") is None
    assert _extra_key(user_id, "culture_preferences") is None


def test_the_manager_match_provider_call_holds_no_transaction(client, monkeypatch):
    """The same rule on the other provider-scored instrument with an account.

    The worker loads the user before scoring, so without an explicit end the
    connection sat idle in transaction through the ManagerMatch call too.
    """
    headers, _user_id = _sign_in(client, "g1-mm-txn@example.test")
    seen = []
    _provider(monkeypatch, MM_LLM_RESPONSE, seen)

    queued = _queue(client, "manager_match", MM_ANSWERS, headers)
    assert queued.status_code == 202
    assert _poll(client, queued).get_json()["status"] == "succeeded"
    assert seen == [{"in_transaction": False, "pending": []}]


@pytest.mark.parametrize(
    "kind", ["work_pulse", "manager_match", "focus_type", "manager_profile"]
)
def test_a_submit_never_reloads_the_user_it_was_handed(client, monkeypatch, kind):
    """Ids are captured before the commits that expire the caller's user row.

    Before, each of these read ``user.id`` after a commit had expired the row,
    and reloaded it to learn the id: at ``path_cache.invalidate`` (Work Pulse
    also at the stored fits' invalidation after commit 1), and, for the manager
    profile, at the ManagerMatch read.
    """
    from app import app
    from model import User, db
    from solverah.services import assessment_service, manager_playbook_service

    _provider(monkeypatch, BOTH_LLM_RESPONSE)
    user_id = _account("g1-reload-%s@example.test" % kind)
    if kind == "manager_profile":
        _seed_manager_match(user_id)

    submits = {
        "work_pulse": lambda u: assessment_service.submit_work_pulse(u, WP_ANSWERS, LOGGER),
        "manager_match": lambda u: assessment_service.submit_manager_match(
            u, MM_ANSWERS, LOGGER
        ),
        "focus_type": lambda u: assessment_service.submit_focus_type(u, FOCUS_TYPE_PAYLOAD),
        "manager_profile": lambda u: manager_playbook_service.submit_manager_profile(
            u, MP_ANSWERS
        ),
    }

    with app.app_context():
        user = db.session.get(User, user_id)  # what the route or the worker hands in
        with count_queries() as statements:
            outcome = submits[kind](user)
        assert outcome.status == 200, outcome.body
        if kind == "manager_profile":
            assert outcome.body["playbook"] is not None

    assert _reads_of(statements, "users") == [], statements


# ── Quiz insights ───────────────────────────────────────────────────────────


def test_the_quiz_insight_provider_call_holds_no_transaction(client, monkeypatch):
    """The route's user lookup opened a transaction; the call used to run inside it."""
    headers, _user_id = _sign_in(client, "g1-qi-txn@example.test")
    seen = []
    _provider(monkeypatch, QUIZ_LLM_RESPONSE, seen)

    resp = client.post(
        "/api/v1/me/quiz-insights",
        json={"quizGroup": "yourFutureYourWay", "quizzes": ONE_QUIZ},
        headers=headers,
    )

    assert resp.status_code == 200
    assert seen == [{"in_transaction": False, "pending": []}]


def test_quiz_insights_are_written_as_one_key_with_the_same_value(client, monkeypatch):
    """The stored value and the merge rules, pinned: a flat group replaces only
    itself, ``careerQuizzes`` merges per quiz, every other group survives -- and
    none of it reads the profile's lists (asserted last, so the value checks are
    seen to hold against the old code too)."""
    headers, user_id = _sign_in(client, "g1-qi-value@example.test")
    _write_document(
        user_id,
        skills=["Python"],
        quizInsights={
            "otherGroup": {"summary": "kept"},
            "careerQuizzes": {"midCareer": {"summary": "kept too"}, "_model": "older"},
        },
    )

    _provider(monkeypatch, QUIZ_LLM_RESPONSE)
    with _statements() as flat_sent:
        flat = client.post(
            "/api/v1/me/quiz-insights",
            json={"quizGroup": "yourFutureYourWay", "quizzes": ONE_QUIZ},
            headers=headers,
        )
    assert flat.status_code == 200
    assert flat.get_json() == {
        "quizGroup": "yourFutureYourWay",
        "overallInsight": QUIZ_LLM_RESPONSE["overallInsight"],
        "insights": QUIZ_LLM_RESPONSE["insights"],
    }

    stored = _extra_key(user_id, "quizInsights")
    group = stored["yourFutureYourWay"]
    insight = QUIZ_LLM_RESPONSE["insights"][0]
    assert {k: v for k, v in group.items() if k != "generatedAt"} == {
        "title": insight["title"],
        "summary": insight["summary"],
        "keyTakeaways": insight["keyTakeaways"],
        "combinedMeaning": insight["combinedMeaning"],
        "nextSteps": insight["nextSteps"],
        "overallInsight": QUIZ_LLM_RESPONSE["overallInsight"],
        "model": "gpt-4o-mini",
    }
    assert isinstance(group["generatedAt"], str)
    assert stored["otherGroup"] == {"summary": "kept"}
    assert stored["careerQuizzes"] == {"midCareer": {"summary": "kept too"}, "_model": "older"}

    _provider(monkeypatch, CAREER_LLM_RESPONSE)
    with _statements() as career_sent:
        career = client.post(
            "/api/v1/me/quiz-insights",
            json={"quizGroup": "careerQuizzes", "quizzes": CAREER_QUIZ},
            headers=headers,
        )
    assert career.status_code == 200

    merged = _extra_key(user_id, "quizInsights")
    career_group = merged["careerQuizzes"]
    assert career_group["midCareer"] == {"summary": "kept too"}
    assert career_group["_overallInsight"] == {"summary": "Career synthesis."}
    assert career_group["_model"] == "gpt-4o-mini"
    assert career_group["earlyCareer"]["summary"] == "Drawn to fast-moving, hands-on roles."
    assert career_group["earlyCareer"]["generatedAt"] == career_group["_generatedAt"]
    assert merged["yourFutureYourWay"] == group
    assert merged["otherGroup"] == {"summary": "kept"}
    assert _document(user_id)["skills"] == ["Python"]

    assert _touching_profile_lists(flat_sent) == []
    assert _touching_profile_lists(career_sent) == []


def test_a_quiz_insight_for_a_vanished_user_is_still_paid_for_then_404s(client, monkeypatch):
    """The documented ordering survives: the provider runs before the user check."""
    from app import app
    from solverah.services import insight_service

    provider = _provider(monkeypatch, QUIZ_LLM_RESPONSE)

    with app.app_context():
        outcome = insight_service.generate_for_user(
            None, {"quizGroup": "yourFutureYourWay", "quizzes": ONE_QUIZ}, LOGGER
        )

    assert outcome.status == 404
    assert outcome.body == {"error": "User not found"}
    assert provider.chat.completions.create.call_count == 1


# ── Result reads ────────────────────────────────────────────────────────────


def test_result_reads_skip_the_narrative_and_answer_the_same_payload(client, monkeypatch):
    """Each result endpoint returns exactly the stored ``result``, read with a
    SELECT that leaves out ``narrative`` -- the one large column none of them
    uses. 404 before a sitting, as before."""
    headers, user_id = _sign_in(client, "g1-results@example.test")

    for kind in ("work_pulse", "manager_match", "focus_type"):
        missing = client.get("/api/v1/me/assessments/%s/result" % kind)
        assert missing.status_code == 404

    _provider(monkeypatch, WP_LLM_RESPONSE)
    assert _poll(client, _queue(client, "work_pulse", WP_ANSWERS, headers)).status_code == 200
    _provider(monkeypatch, MM_LLM_RESPONSE)
    assert _poll(client, _queue(client, "manager_match", MM_ANSWERS, headers)).status_code == 200
    assert client.post(
        "/api/v1/assessments/focus_type/submissions", json=FOCUS_TYPE_PAYLOAD, headers=headers
    ).status_code == 200

    sent_per_kind = {}
    for kind in ("work_pulse", "manager_match", "focus_type"):
        stored = _stored_row(user_id, kind)
        assert stored["result"], kind
        with _statements() as sent:
            resp = client.get("/api/v1/me/assessments/%s/result" % kind)
        sent_per_kind[kind] = sent
        assert resp.status_code == 200, kind
        assert resp.get_json() == stored["result"], kind

    # After every payload check, so the old code is seen to pass those first.
    for kind, sent in sent_per_kind.items():
        assert [s for s in sent if SUBMISSION_NARRATIVE in s] == [], (kind, sent)
        assert len(_reads_of(sent, "assessment_submissions")) == 1, (kind, sent)


def test_the_manager_playbook_reads_skip_the_narrative(client, monkeypatch):
    """``_require_manager_match`` and the submit's ManagerMatch read need only
    ``answers``; the payloads are the ones the playbook has always served."""
    headers, user_id = _sign_in(client, "g1-playbook@example.test")
    _seed_manager_match(user_id)

    with _statements() as posted:
        submitted = client.post(
            "/api/v1/assessments/manager-profile", json={"answers": MP_ANSWERS}, headers=headers
        )
    assert submitted.status_code == 200
    with _statements() as read:
        playbook = client.get("/api/v1/me/manager-playbook")
    assert playbook.status_code == 200

    body = playbook.get_json()
    assert body.pop("created_at")
    assert body == submitted.get_json()
    assert body["playbook"] is not None

    for sent in (posted, read):
        assert [s for s in sent if SUBMISSION_NARRATIVE in s] == [], sent
        assert len(_reads_of(sent, "assessment_submissions")) == 1, sent
