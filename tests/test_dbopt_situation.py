"""DB-ledger package E: the Situation Report's reads.

``GET /me/situation-report`` keeps its exact bytes while each read it makes gets
narrower: the manager section is an EXISTS probe, the environment report is read
without its ``raw_answers`` blob (the export still gets it), the events since the
report are filtered in SQL and never ship their free-text note, and the live
career status skips the assessment-result query it never used. Recalibrate reads
the pin once, now that ``set_pin`` is an upsert.

The payload test is characterisation (it passed before the change); the others
failed on the code before it, as each docstring says.
"""

from __future__ import annotations

import contextlib
import datetime
import re

import pytest

from tests.query_count import count_queries
from work_pulse import situation_items

UTC = datetime.timezone.utc
PASSWORD = "Strongpass1!"


@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def ctx(client):
    """An application context over the ``client`` fixture's schema, left with no
    open transaction (``client``'s teardown drops every table and would wait on it)."""
    from app import app
    from model import db

    with app.app_context():
        yield app
        db.session.rollback()
        db.session.remove()


@contextlib.contextmanager
def _statements():
    """``count_queries()`` around test-client requests, entered in an app context
    of its own so each request pushes its own context and session."""
    from app import app

    with contextlib.ExitStack() as stack:
        with app.app_context():
            statements = stack.enter_context(count_queries())
        yield statements


def _reads_of(statements, table):
    source = re.compile(r"\bFROM\s+%s\b" % re.escape(table), re.IGNORECASE)
    return [s for s in statements if s.lstrip().upper().startswith("SELECT") and source.search(s)]


# ---------------------------------------------------------------------------
# Building each state through the real routes
# ---------------------------------------------------------------------------


def _sign_in(client, monkeypatch, email):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Ledger E", "terms_accepted": True},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).one()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        user_id = user.id

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["csrfToken"], user_id


def _career_status(client, csrf, status):
    resp = client.patch(
        "/api/v1/me/career-status", json={"status": status}, headers={"X-CSRF-TOKEN": csrf}
    )
    assert resp.status_code == 200, resp.get_json()


def _complete_core(client, csrf, varied=False):
    """One real ``core`` sitting through the token form (a varied pattern scores
    differently from the uniform one, so a retake can move the pin)."""
    form = client.get("/api/v1/assessments/core/form")
    assert form.status_code == 200
    responses, position = {}, 0
    for block in form.get_json()["blocks"]:
        for item in block["items"]:
            index = (1 if position % 3 == 0 else 0) if varied else 0
            responses[item["token"]] = item["options"][index % len(item["options"])]["key"]
            position += 1
    resp = client.post(
        "/api/v1/assessments/core/submissions",
        json={"responses": responses},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200, resp.get_json()


def _environment_answers(pole):
    answers = {}
    for item in situation_items.ENVIRONMENT_ITEMS:
        option = next(o for o in item["options"] if o["pole"] == pole)
        answers[item["item_id"]] = option["key"]
    return answers


def _submit_environment(client, csrf, pole="mixed"):
    resp = client.post(
        "/api/v1/me/environment-report",
        json={"answers": _environment_answers(pole), "stage_size": 3, "comp": 3, "experienced": 3},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200, resp.get_json()


def _manager_profile(user_id):
    import manager_profile_store
    from app import app
    from model import db

    with app.app_context():
        manager_profile_store.write_manager_profile(
            db,
            user_id,
            answers=[{"question_id": "mp-q1", "choice": "a"}],
            dimension_scores={"autonomy": 0.5, "feedback_style": 0.5, "relationship": 0.5, "growth_focus": 0.5},
            scoring_key="ledger-e-test",
            version="ledger-e-test",
        )
        db.session.commit()


def _save_document(user_id, **fields):
    from app import app
    from model import db
    from solverah.repositories import profile_repository

    with app.app_context():
        profile_repository.update_document(user_id, lambda document: {**document, **fields})
        db.session.commit()


_PRESENT_ROLE = [{"company": "Acme", "title": "Engineer", "startDate": "2021-01", "endDate": "Present"}]


def _events_around_the_report(client, csrf, user_id):
    """Pulse events just before, exactly at, and after the report's ``submitted_at``."""
    import environment_report_store
    from app import app
    from model import EnvironmentReport, PulseEvent, db

    with app.app_context():
        report = (
            EnvironmentReport.query.filter_by(user_id=user_id)
            .order_by(EnvironmentReport.submitted_at.desc(), EnvironmentReport.id.desc())
            .first()
        )
        report.submitted_at = report.submitted_at - datetime.timedelta(hours=1)
        db.session.commit()
        submitted_at = datetime.datetime.fromisoformat(
            environment_report_store.latest_environment_report(user_id)["submitted_at"]
        )

    tick = datetime.timedelta(microseconds=1)
    placed = [
        ("reorg", None, submitted_at - tick),
        ("new_manager", None, submitted_at),
        ("other", "a private detail only this user typed", submitted_at + tick),
        ("remote_change", None, submitted_at + datetime.timedelta(minutes=1)),
    ]
    for event_type, note, at in placed:
        body = {"event_type": event_type}
        if note is not None:
            body["note"] = note
        resp = client.post("/api/v1/me/pulse/events", json=body, headers={"X-CSRF-TOKEN": csrf})
        assert resp.status_code == 200, resp.get_json()
        with app.app_context():
            db.session.get(PulseEvent, resp.get_json()["id"]).at = at
            db.session.commit()
    return submitted_at


def _nothing(client, csrf, user_id):
    return None


def _environment_and_manager_without_core(client, csrf, user_id):
    _career_status(client, csrf, "employed")
    _submit_environment(client, csrf, pole="high")
    _manager_profile(user_id)


def _core_for_a_first_job(client, csrf, user_id):
    _career_status(client, csrf, "first_job")
    _complete_core(client, csrf)


def _core_with_status_derived_from_experience(client, csrf, user_id):
    _save_document(user_id, headline="Engineer", experience=_PRESENT_ROLE)
    _complete_core(client, csrf)


def _core_with_no_status_at_all(client, csrf, user_id):
    _complete_core(client, csrf)


def _complete_with_events_and_a_manager(client, csrf, user_id):
    _career_status(client, csrf, "employed")
    _complete_core(client, csrf, varied=True)
    _submit_environment(client, csrf, pole="high")
    _manager_profile(user_id)
    _events_around_the_report(client, csrf, user_id)


def _complete_needs_forward(client, csrf, user_id):
    _career_status(client, csrf, "between_jobs")
    _complete_core(client, csrf)
    _submit_environment(client, csrf, pole="low")


SCENARIOS = {
    "needs_core_nothing_yet": ("needs_core", _nothing),
    "needs_core_with_environment_and_manager": ("needs_core", _environment_and_manager_without_core),
    "needs_environment_first_job": ("needs_environment_report", _core_for_a_first_job),
    "needs_environment_status_from_experience": (
        "needs_environment_report",
        _core_with_status_derived_from_experience,
    ),
    "needs_environment_no_status": ("needs_environment_report", _core_with_no_status_at_all),
    "complete_with_events_and_manager": ("complete", _complete_with_events_and_a_manager),
    "complete_needs_forward": ("complete", _complete_needs_forward),
}


def _install_the_full_reads(patched):
    """Put back the reads the page made before this package: the whole newest
    manager sitting, the whole profile document, every event from ``submitted_at``
    on (note included) filtered in Python, and the environment report with its
    ``raw_answers``. Built only from functions that exist before and after."""
    import environment_report_store
    import manager_profile_store
    import pulse_store
    from solverah.repositories import profile_repository
    from solverah.services import situation_report_service as service
    from solverah.services.intelligence_service import derive_career_status

    whole_report = environment_report_store.latest_environment_report

    def latest_environment_report(user_id, **_narrowing):
        return whole_report(user_id)

    def manager_section(user_id):
        return {"has_profile": manager_profile_store.latest_manager_profile(user_id) is not None}

    def live_career_status(user_id):
        profile = profile_repository.load_document(user_id)
        status = profile.get("career_status")
        if not status:
            status = derive_career_status(profile)
        return status

    def events_since_report(user_id, submitted_at):
        if not submitted_at:
            return []
        since = datetime.datetime.fromisoformat(submitted_at)
        events = pulse_store.pulse_events_in_range(user_id, since=since)
        return [
            {"type": event["event_type"], "date": event["at"]}
            for event in events
            if event["at"] is not None and datetime.datetime.fromisoformat(event["at"]) > since
        ]

    patched.setattr(environment_report_store, "latest_environment_report", latest_environment_report)
    patched.setattr(service, "_manager_section", manager_section)
    patched.setattr(service, "_live_career_status", live_career_status)
    patched.setattr(service, "_events_since_report", events_since_report)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_situation_report_payload_is_byte_identical_to_the_full_reads(client, monkeypatch, scenario):
    """Characterisation across all three states: the narrowed reads answer every
    question the page asks exactly as the full reads did -- same status, same
    bytes -- including the event on the report's own instant, the note that
    must never ship, and a career status derived from experience."""
    expected_state, build = SCENARIOS[scenario]
    csrf, user_id = _sign_in(client, monkeypatch, "%s@example.test" % scenario.replace("_", "-"))
    build(client, csrf, user_id)

    narrowed = client.get("/api/v1/me/situation-report")
    with monkeypatch.context() as patched:
        _install_the_full_reads(patched)
        full = client.get("/api/v1/me/situation-report")

    assert narrowed.status_code == full.status_code == 200
    assert narrowed.get_json()["state"] == expected_state
    assert narrowed.get_data() == full.get_data()
    if scenario == "complete_with_events_and_manager":
        body = narrowed.get_json()
        assert body["manager"] == {"has_profile": True}
        assert [event["type"] for event in body["events_since_report"]] == ["remote_change", "other"]
        assert b"a private detail" not in narrowed.get_data()


# ---------------------------------------------------------------------------
# Each read, narrowed
# ---------------------------------------------------------------------------


def test_the_manager_section_is_one_exists_probe(ctx, seed_user):
    """Ledger ``situation_report_service``:67, ``manager_profile_store``:81.

    Before: the whole newest sitting, both JSONB columns included, to test
    ``is not None``. Now one EXISTS that ships neither.
    """
    from solverah.services import situation_report_service as service

    seed_user(1)
    with count_queries() as absent:
        without = service._manager_section(1)
    _manager_profile(1)
    with count_queries() as present:
        with_one = service._manager_section(1)

    assert without == {"has_profile": False}
    assert with_one == {"has_profile": True}
    for statements in (absent, present):
        assert len(statements) == 1, statements
        assert re.match(r"\s*SELECT EXISTS\b", statements[0]), statements[0]
        assert "answers" not in statements[0] and "dimension_scores" not in statements[0]


def test_the_page_never_selects_raw_answers_and_the_export_still_gets_them(client, monkeypatch):
    """Ledger ``environment_report_store``:147, ``situation_report_service``:344.

    Before: the page read loaded the ``raw_answers`` JSONB it never uses. Now it
    is deferred on that read only; the export's history read and the default
    ``latest_environment_report`` still return it.
    """
    import environment_report_store
    from app import app

    csrf, user_id = _sign_in(client, monkeypatch, "raw-answers@example.test")
    _career_status(client, csrf, "employed")
    _submit_environment(client, csrf, pole="high")

    with _statements() as before_core:
        needs_core = client.get("/api/v1/me/situation-report")
    _complete_core(client, csrf)
    with _statements() as after_core:
        complete = client.get("/api/v1/me/situation-report")

    assert needs_core.get_json()["state"] == "needs_core"
    assert complete.get_json()["state"] == "complete"
    for statements in (before_core, after_core):
        assert [s for s in statements if "raw_answers" in s] == [], statements

    with app.app_context():
        assert environment_report_store.latest_environment_report(user_id)["raw_answers"] == (
            _environment_answers("high")
        )
        history = environment_report_store.environment_report_history(user_id)
        assert history[0]["raw_answers"] == _environment_answers("high")
        narrowed = environment_report_store.latest_environment_report(
            user_id, include_raw_answers=False
        )
        assert "raw_answers" not in narrowed
        whole = environment_report_store.latest_environment_report(user_id)
        assert narrowed == {key: value for key, value in whole.items() if key != "raw_answers"}


def test_events_since_the_report_are_filtered_in_sql_and_never_select_the_note(ctx, seed_user):
    """Ledger ``situation_report_service``:239, ``pulse_store``:341.

    Before: every event from ``submitted_at`` on, note included, with the
    boundary dropped in Python. Now ``at > submitted_at`` is in the query, and
    only the type and the date are selected.
    """
    from model import PulseEvent, db
    from solverah.services import situation_report_service as service

    seed_user(1)
    since = datetime.datetime(2026, 9, 1, 9, 30, tzinfo=UTC)
    tick = datetime.timedelta(microseconds=1)
    for event_type, at in (("reorg", since - tick), ("new_manager", since), ("other", since + tick)):
        db.session.add(PulseEvent(user_id=1, event_type=event_type, note="typed by the user", at=at))
    db.session.commit()

    with count_queries() as statements:
        events = service._events_since_report(1, since.isoformat())

    assert events == [{"type": "other", "date": (since + tick).isoformat()}]
    assert len(statements) == 1, statements
    assert "note" not in statements[0], statements[0]
    assert re.search(r"pulse_events\.at > ", statements[0]), statements[0]


def test_the_live_career_status_skips_the_assessment_result_read(ctx, seed_user):
    """Ledger ``situation_report_service``:78/117.

    Before: the whole document, including the query for the two assessment
    result keys it never reads. Now ``load_document(include_assessments=False)``.
    """
    from solverah.services import situation_report_service as service

    seed_user(1, 2)
    _save_document(1, headline="Engineer", experience=_PRESENT_ROLE)
    _save_document(2, career_status="between_jobs")

    with count_queries() as derived:
        status = service._live_career_status(1)
    with count_queries() as explicit:
        chosen = service._live_career_status(2)

    assert status == "employed"
    assert chosen == "between_jobs"
    for statements in (derived, explicit):
        assert [s for s in statements if "assessment_submissions" in s] == [], statements


def test_recalibrate_reads_the_pin_once(client, monkeypatch):
    """Ledger ``situation_report_service``:453: the pin row is read once, by the
    pin resolution, and written by one upsert -- ``set_pin`` (wave 1) no longer
    re-reads it. Guards the pair as ``recalibrate`` uses it."""
    csrf, _user_id = _sign_in(client, monkeypatch, "recalibrate-once@example.test")
    _career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    _submit_environment(client, csrf)
    _complete_core(client, csrf, varied=True)

    with _statements() as statements:
        resp = client.post(
            "/api/v1/me/situation-report/recalibrate", headers={"X-CSRF-TOKEN": csrf}
        )

    assert resp.status_code == 200 and resp.get_json() == {"recalibrated": True}
    assert len(_reads_of(statements, "situation_report_pins")) == 1, statements
    writes = [s for s in statements if re.match(r"\s*INSERT INTO situation_report_pins\b", s)]
    assert len(writes) == 1 and "ON CONFLICT" in writes[0], statements
