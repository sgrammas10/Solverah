"""DB ledger, package G2: the profile and account services, measured.

Every test here pins one ledger finding against ``profile_service`` or
``account_service`` and was written to fail on the code before the fix; the
characterisation tests that pass on both are marked as such. They share the
rule the whole ledger works under: a route returns the same bytes it returned
before, and only the number of statements it takes to produce them changes.
Where a test compares bodies, the reference is the pre-fix read path run in the
same test, on the same rows -- an oracle rather than a stored snapshot, because
most of what these routes return carries timestamps the database stamps.

Requests are made with no application context pushed (see ``_counted``): a
request inside one reuses it, and with it the test's session, which turns real
SELECTs into identity-map hits and makes a count come out too low.
"""

import contextlib
import copy
import datetime
import re

import pytest

EMAIL = "g2-owner@example.com"
OTHER_EMAIL = "g2-bystander@example.com"
PASSWORD = "Strongpass1!"
FORM_VERSION = "dbopt-g2"
#: What ``account_service._now`` is pinned to, so two exports can match to the byte.
FROZEN_NOW = "2026-09-28T12:00:00+00:00"
SITTING_AT = datetime.datetime(2026, 9, 1, 9, 30, tzinfo=datetime.timezone.utc)

#: The columns of ``user_intake`` beyond its keys: the live statement selections
#: and the dead Phase 2d quiz copies, JSON and prose.
_INTAKE_PAYLOAD_COLUMNS = (
    "selected_statement_ids",
    "wpll_answers",
    "wpll_insight_text",
    "wpl_answers",
    "wpl_narrative",
    "wpl_result",
)


def _app():
    from app import app

    return app


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def _no_outbound_email(monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)


@contextlib.contextmanager
def _counted():
    """``count_queries`` around a request made with no application context pushed.

    The shared counter resolves ``db.engine`` on entry, which needs a context;
    it is released again before the block runs, so the request under test
    pushes its own context and session.
    """
    from tests.query_count import count_queries

    with _app().app_context():
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


# ---------------------------------------------------------------------------
# Accounts and their data
# ---------------------------------------------------------------------------


def _sign_in(client, email=EMAIL):
    """Register through the API, confirm directly, sign in. ``(csrf, user_id)``."""
    from model import User, db

    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Ledger G2",
              "role": "job-seeker", "terms_accepted": True},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    with _app().app_context():
        user = User.query.filter_by(email=email).one()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        user_id = user.id

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["csrfToken"], user_id


def _resume_key(user_id, resume_id="abc"):
    return "profile/%s/%s/resume.pdf" % (user_id, resume_id)


def _document(user_id):
    """A profile that fills every child table and every ``extra`` shape the export carries."""
    return {
        "firstName": "Ada",
        "lastName": "Lovelace",
        "email": EMAIL,
        "summary": "Builds engines.",
        "phone": "555-0100",
        "career_status": "employed",
        "experience": [
            {"id": 1, "company": "Acme", "position": "Principal", "startDate": "2020-01-15",
             "endDate": "Present", "description": "led"},
            {"id": 2, "company": "Beta", "position": "Engineer", "startDate": "",
             "endDate": "2019 - 2020", "description": ""},
        ],
        "education": [
            {"id": 1, "institution": "State University", "degree": "BS",
             "field": "Computer Science", "gpa": "4.0"},
        ],
        "skills": ["Python", "C++", "Node.js"],
        "skill_levels": {"Rust": "beginner", "Python": "advanced"},
        "resumeKey": _resume_key(user_id),
        "uploadedResume": {"name": "cv.pdf", "size": 900, "type": "application/pdf"},
        "_parsedResumeSnapshot": {"resumeKey": _resume_key(user_id), "experience": [],
                                  "education": [], "skills": []},
        "quizInsights": {"careerQuizzes": {"q1": {"summary": "steady"}}},
        "pulse_settings": {"cadence": "weekly", "awaiting_response": False},
        "culture_preferences": {"empathy": 0.5, "pace": "fast"},
        "path_preferences": {"move_intent": "stay"},
    }


def _save(user_id, document):
    """Store *document* through the one write path and commit it."""
    from model import db
    from solverah.repositories import profile_repository

    stored = copy.deepcopy(document)
    profile_repository.update_document(user_id, lambda _existing: copy.deepcopy(stored))
    db.session.commit()


def _sit(user_id, kind, **payloads):
    """One completed sitting of *kind*. A payload left out stays SQL NULL."""
    from model import AssessmentForm, AssessmentSubmission, db

    AssessmentForm.register(kind, FORM_VERSION)
    db.session.add(
        AssessmentSubmission(
            user_id=user_id, kind=kind, form_version=FORM_VERSION, status="scored",
            completed_at=SITTING_AT,
            **{name: value for name, value in payloads.items() if value is not None},
        )
    )
    db.session.flush()


#: The two instruments whose results the profile document merges in, as sat.
_RESULT_SITTINGS = {
    "focus_type": {"result": {"archetype": "Deep Diver"},
                   "answers": {"scene_1": ["big_project", "emails"]}},
    "manager_match": {"result": {"archetype": "Coach", "narrative": "Coached."},
                      "answers": [{"question_id": "mm-q1", "choice": "a"}],
                      "narrative": "Coached."},
}

#: The legacy quiz's two kinds, as sat.
_QUIZ_SITTINGS = {
    "wpll": {"answers": [{"statement_id": "s1", "agree": True}],
             "narrative": "Lite-lite insight."},
    "work_pulse": {"answers": {"q1": 4, "q2": 2},
                   "result": {"archetype": "Independent Worker", "narrative": "Pulse prose."},
                   "narrative": "Pulse prose."},
}


def _seed_everything(user_id, quiz, *, intake_row):
    """Every data class ``GET /me/export`` carries, for *user_id*.

    Each is written through its own store, as the product writes it. *quiz* maps
    the legacy quiz kinds to sit onto their payloads, so each ``legacy_quiz``
    branch can be reached; *intake_row* decides whether a ``user_intake`` row
    exists, which is what keeps the block present when neither kind was sat.
    """
    from assessment_form import ScoredSubmission
    from assessment_store import persist_submission
    from environment_report_store import write_environment_report
    from experiment_store import start_experiment
    from manager_profile_store import write_manager_profile
    from model import ENV_DIMENSIONS, IntakeSubmission, JobRecommendation, db
    from pulse_store import write_pulse_checkin, write_pulse_event
    from situation_report_pin_store import set_pin
    from solverah.repositories import intake_repository, profile_repository
    from work_pulse.pulse_items import dimensions_for_checkin

    with _app().app_context():
        _save(user_id, _document(user_id))

        def intake(submission_id, email):
            return IntakeSubmission(
                id=submission_id, first_name="Ada", last_name="Lovelace", email=email,
                state="NY", phone="555-0100", linkedin_url="https://linkedin.example/ada",
                resume_key="intake/%s/resume.pdf" % submission_id,
                resume_mime="application/pdf", resume_size_bytes=1234, status="uploaded",
            )

        # Two under this address, one of them in another case; one that is not theirs.
        db.session.add_all([
            intake("g2-intake-1", EMAIL),
            intake("g2-intake-2", EMAIL.upper()),
            intake("g2-intake-3", OTHER_EMAIL),
        ])
        if intake_row:
            intake_repository.upsert_user_intake(user_id, ["s1", "s2"])

        for kind, payloads in quiz.items():
            _sit(user_id, kind, **payloads)
        for kind, payloads in _RESULT_SITTINGS.items():
            _sit(user_id, kind, **payloads)

        persist_submission(db, user_id, ScoredSubmission(
            form_version="v2-2026-08-18",
            scoring_key_version="v2-2026-08-18+mean_pole",
            scores={"autonomy": 0.75},
            choices={"au1v2": "A"},
            confidences={"autonomy": 1.0},
        ))
        db.session.add_all([
            JobRecommendation(user_id=user_id, job_id=11, score=0.75),
            JobRecommendation(user_id=user_id, job_id=12, score=0.5),
        ])
        profile_repository.record_resume_corrections(
            user_id, _resume_key(user_id), [("phone", "555-0000", "555-0100")]
        )
        write_pulse_checkin(
            db, user_id, sequence=0,
            item_scores={dim: 4 for dim in dimensions_for_checkin(user_id, 0)},
            experienced=3, version="pulse-v1-test",
        )
        write_pulse_event(db, user_id, event_type="reorg", note="team split in two")
        start_experiment(db, user_id, dimension="autonomy", direction="under")
        write_environment_report(
            db, user_id,
            raw_answers={"env-autonomy-1": "mixed-a"},
            dimension_scores={dim: 0.5 for dim in ENV_DIMENSIONS},
            stage_size=3, comp=3, experienced_outcome=3,
            career_status="employed", version="v1-2026-09-10",
        )
        write_manager_profile(
            db, user_id,
            answers=[{"question_id": "mp-q1", "choice": "a"}],
            dimension_scores={"autonomy": 0.6, "feedback_style": 0.5,
                              "relationship": 0.5, "growth_focus": 0.5},
            scoring_key="v1-2026-09-10", version="v1-2026-09-10",
        )
        set_pin(db, user_id, "a" * 32)
        db.session.commit()


# ---------------------------------------------------------------------------
# GET /me/export
# ---------------------------------------------------------------------------


def _export_as_it_was(user_id):
    """``GET /me/export``'s body, as bytes, with the pre-fix reads. The oracle.

    The blocks this package reads differently -- ``legacy_quiz`` and the two
    raw-answer keys -- are recomputed exactly as the code before the fix did:
    one ``current_submission`` per kind, and the whole ``user_intake`` row to
    decide whether the block exists. Every other block is taken from the
    service under test, because nothing about how it is read changed -- so those
    untouched blocks are compared against themselves, and a test built on this
    oracle says nothing about them.
    """
    from flask import jsonify

    from model import User, db
    from solverah.repositories import account_repository, assessment_repository
    from solverah.services import account_service

    with _app().test_request_context():
        user = db.session.get(User, user_id)
        payload = account_service.export_account_data(user).body

        wpll = assessment_repository.current_submission(user_id, "wpll")
        work_pulse = assessment_repository.current_submission(user_id, "work_pulse")
        if (
            wpll is None and work_pulse is None
            and account_repository.find_user_intake(user_id) is None
        ):
            payload["legacy_quiz"] = None
        else:
            payload["legacy_quiz"] = {
                "wpll_answers": (wpll.answers if wpll else None) or [],
                "wpll_insight_text": wpll.narrative if wpll else None,
                "wpl_answers": work_pulse.answers if work_pulse else None,
                "wpl_narrative": work_pulse.narrative if work_pulse else None,
                "wpl_result": work_pulse.result if work_pulse else None,
            }

        focus_type = assessment_repository.current_submission(user_id, "focus_type")
        manager_match = assessment_repository.current_submission(user_id, "manager_match")
        payload["focus_type_answers"] = focus_type.answers if focus_type is not None else None
        payload["manager_match_answers"] = (
            manager_match.answers if manager_match is not None else None
        )
        return jsonify(payload).get_data()


@pytest.mark.parametrize(
    "quiz, intake_row",
    [
        (_QUIZ_SITTINGS, True),
        ({}, True),
        ({}, False),
        ({"wpll": {"narrative": "Answers never saved."}}, False),
        ({"work_pulse": _QUIZ_SITTINGS["work_pulse"]}, False),
    ],
    ids=["both-quizzes", "no-quiz-intake-row", "no-quiz-no-intake-row",
         "wpll-without-answers", "work-pulse-only"],
)
def test_the_export_body_is_what_the_pre_fix_reads_produced(client, monkeypatch, quiz, intake_row):
    """Characterisation (passes before and after): a subject-access export is a
    published contract, so the body must match the pre-fix reads to the byte,
    through every ``legacy_quiz`` branch -- both kinds, none with and without
    the ``user_intake`` row that keeps the block, and each kind alone, one with
    its answers never saved, which must still export ``[]`` rather than null."""
    from solverah.repositories import profile_repository

    _, user_id = _sign_in(client)
    _seed_everything(user_id, quiz, intake_row=intake_row)
    monkeypatch.setattr("solverah.services.account_service._now", lambda: FROZEN_NOW)

    resp = client.get("/api/v1/me/export")

    assert resp.status_code == 200
    assert resp.get_data() == _export_as_it_was(user_id)

    body = resp.get_json()
    with _app().app_context():
        # The profile block keeps both merged results: the export is one of the
        # readers ``load_document``'s default exists for.
        assert body["profile"] == profile_repository.load_document(user_id)
    assert body["profile"]["focus_type_result"] == {"archetype": "Deep Diver"}
    assert body["profile"]["manager_match_result"]["archetype"] == "Coach"
    assert body["focus_type_answers"] == _RESULT_SITTINGS["focus_type"]["answers"]
    assert body["manager_match_answers"] == _RESULT_SITTINGS["manager_match"]["answers"]


def test_the_export_reads_every_current_sitting_in_one_statement(client):
    """Ledger ``account_service``:166/167/195/196: four single-kind reads of the
    same user's sittings, one per kind, become one. What remains beside it is
    ``load_document``'s own read of the two results the profile block carries."""
    _, user_id = _sign_in(client)
    _seed_everything(user_id, _QUIZ_SITTINGS, intake_row=True)

    with _counted() as statements:
        resp = client.get("/api/v1/me/export")

    assert resp.status_code == 200
    sittings = _reads_of(statements, "assessment_submissions")
    assert len(sittings) == 2, sittings


def test_the_legacy_quiz_asks_only_whether_the_intake_row_exists(client):
    """Ledger ``account_service``:170: with neither quiz sat, the block hangs on
    whether a ``user_intake`` row exists -- and the pre-fix read loaded the whole
    row, dead JSON answer columns included, to find that out."""
    _, user_id = _sign_in(client)
    _seed_everything(user_id, {}, intake_row=True)

    with _counted() as statements:
        resp = client.get("/api/v1/me/export")

    assert resp.status_code == 200
    probes = _reads_of(statements, "user_intake")
    assert len(probes) == 1, probes
    loaded = [column for column in _INTAKE_PAYLOAD_COLUMNS if column in probes[0]]
    assert loaded == [], probes[0]
    assert resp.get_json()["legacy_quiz"] == {
        "wpll_answers": [],
        "wpll_insight_text": None,
        "wpl_answers": None,
        "wpl_narrative": None,
        "wpl_result": None,
    }


# ---------------------------------------------------------------------------
# Internal readers: GET /me/dashboard and GET /me/skills
# ---------------------------------------------------------------------------


def _get_as_it_was(client, monkeypatch, path):
    """GET *path* with every ``load_document`` call reading both assessment
    results, as every caller did before ``include_assessments`` existed.
    ``(body bytes, statements)``."""
    from solverah.repositories import profile_repository

    full = profile_repository.load_document
    with monkeypatch.context() as patch:
        patch.setattr(
            profile_repository, "load_document", lambda user_id, **_ignored: full(user_id)
        )
        with _counted() as statements:
            resp = client.get(path)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_data(), statements


def _seed_results_and_profile(user_id):
    """A profile, both merged results and some activity: the full document
    carries both result keys, so leaving them out is visible if it leaks."""
    from model import db

    with _app().app_context():
        _save(user_id, _document(user_id))
        for kind, payloads in _RESULT_SITTINGS.items():
            _sit(user_id, kind, **payloads)
        db.session.commit()


@pytest.mark.parametrize(
    "path", ["/api/v1/me/dashboard", "/api/v1/me/skills"], ids=["dashboard", "skills"]
)
def test_an_internal_reader_skips_the_assessment_results(client, monkeypatch, path):
    """Ledger ``profile_service``:300 and :416. Neither body carries
    ``focus_type_result`` or ``manager_match_result``, and nothing that builds
    them reads either, so the read that merges them in is dropped: one statement
    fewer, the same bytes. The dashboard is measured on a cache miss."""
    _, user_id = _sign_in(client)
    _seed_results_and_profile(user_id)
    monkeypatch.setattr("solverah.infra.cache.get_json", lambda _key: None)

    old_body, old_statements = _get_as_it_was(client, monkeypatch, path)
    with _counted() as statements:
        resp = client.get(path)

    assert resp.status_code == 200
    assert resp.get_data() == old_body
    assert len(statements) == len(old_statements) - 1, statements


# ---------------------------------------------------------------------------
# Writes: nothing re-reads the account after the commit
# ---------------------------------------------------------------------------


def test_renaming_answers_without_reloading_the_account(client):
    """Ledger ``profile_service``:371: the identity was read back after the
    commit, which expires the row, so answering cost a SELECT of the row the
    request had just written. The answer is the same bytes a fresh read gives."""
    csrf, _ = _sign_in(client)

    with _counted() as statements:
        resp = client.patch(
            "/api/v1/me", json={"name": "Renamed Owner"}, headers={"X-CSRF-TOKEN": csrf}
        )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    lookups = _reads_of(statements, "users")
    assert len(lookups) == 1, lookups
    assert resp.get_json()["name"] == "Renamed Owner"
    assert resp.get_data() == client.get("/api/v1/me").get_data()


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("patch", "/api/v1/me/career-status", {"status": "between_jobs"}),
        ("put", "/api/v1/me/skills",
         {"skills": [{"name": "Python", "proficiency": "advanced"}]}),
        ("patch", "/api/v1/me/profile", {"profile": {"skills": ["Python", "SQL"]}}),
    ],
    ids=["career-status", "skills", "profile"],
)
def test_a_profile_write_does_not_reload_the_account_after_its_commit(
    client, method, path, body
):
    """Ledger ``profile_service``:176, :213 and :237: ``path_cache.invalidate``
    ran after the commit with ``user.id``, and reading an attribute of an
    expired row reloads the whole row. The route's own lookup is the only read
    of ``users`` left."""
    csrf, _ = _sign_in(client)

    with _counted() as statements:
        resp = getattr(client, method)(path, json=body, headers={"X-CSRF-TOKEN": csrf})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    lookups = _reads_of(statements, "users")
    assert len(lookups) == 1, lookups


def test_a_profile_save_reads_the_profile_once(client):
    """Characterisation (passes before and after), ledger ``profile_service``:151:
    there is no second full read to drop. The parser-correction diff runs inside
    ``update_document``'s mutate callback against the read that attempt made, and
    the response is ``update_document``'s own return value."""
    csrf, user_id = _sign_in(client)
    with _app().app_context():
        _save(user_id, _document(user_id))

    with _counted() as statements:
        resp = client.patch(
            "/api/v1/me/profile",
            json={"profile": {"summary": "Builds analytical engines."}},
            headers={"X-CSRF-TOKEN": csrf},
        )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert len(_reads_of(statements, "profiles")) == 1, statements
    assert resp.get_json()["profile"]["summary"] == "Builds analytical engines."


# ---------------------------------------------------------------------------
# Resume keys
# ---------------------------------------------------------------------------


def test_resolving_a_resume_key_reads_the_row_only_when_the_answer_needs_it(client):
    """Ledger ``profile_service``:478: the stored resume was read before the
    branch was known, so rebuilding a key to write to -- which never looks at
    it -- and rejecting a malformed id both paid for the read."""
    from model import User, db
    from solverah.services import profile_service
    from tests.query_count import count_queries

    _, user_id = _sign_in(client)
    stored = _resume_key(user_id)
    with _app().app_context():
        _save(user_id, {"resumeKey": stored,
                        "uploadedResume": {"name": "cv.pdf", "type": "application/pdf"}})

    cases = [
        # (resume_id, mime) -> (answer, statements)
        (("fresh1", "application/pdf"), (_resume_key(user_id, "fresh1"), 0)),
        (("", "application/pdf"), (None, 0)),
        (("a/b", None), (None, 0)),
        (("current", None), (stored, 1)),
        (("current", "application/pdf"), (stored, 1)),
        (("abc", None), (stored, 1)),
        (("other", None), (None, 1)),
    ]
    with _app().app_context():
        user = db.session.get(User, user_id)
        for (resume_id, mime), (answer, sent) in cases:
            with count_queries() as statements:
                assert profile_service.resolve_resume_key(user, resume_id, mime=mime) == answer
            assert len(statements) == sent, (resume_id, mime, statements)


def _promoted(user_id):
    _save(user_id, {"summary": "promoted", "resumeKey": _resume_key(user_id),
                    "uploadedResume": {"name": "cv.pdf", "size": 900,
                                       "type": "application/pdf"}})


def _drop_profile_row(user_id):
    """Delete the ``profiles`` row registration wrote. It has no child rows."""
    import sqlalchemy as sa

    from model import Profile, db

    db.session.execute(sa.delete(Profile).where(Profile.user_id == user_id))
    db.session.commit()


def _carried_verbatim(extra):
    """A profile the Phase 2a migration carried into ``extra`` whole and nobody
    has saved since: a ``profiles`` row, no child rows, no ``resumes`` row."""

    def seed(user_id):
        from model import Profile, db

        _drop_profile_row(user_id)
        db.session.add(Profile(user_id=user_id, extra=extra(user_id), completeness=0,
                               version=0))
        db.session.commit()

    return seed


def _row_and_a_stale_copy(user_id):
    """A ``resumes`` row, and an older key left in ``extra`` beside it."""
    import sqlalchemy as sa

    from model import Profile, db

    _promoted(user_id)
    db.session.execute(
        sa.update(Profile)
        .where(Profile.user_id == user_id)
        .values(extra=Profile.extra.op("||")(
            sa.bindparam("stale", {"resumeKey": _resume_key(user_id, "old")},
                         type_=Profile.extra.type)
        ))
    )
    db.session.commit()


_PROFILE_SHAPES = {
    "promoted": _promoted,
    "legacy": _carried_verbatim(lambda user_id: {
        "summary": "legacy", "resumeKey": _resume_key(user_id, "legacy"),
        "uploadedResume": {"name": "cv.pdf", "type": "application/pdf"},
    }),
    "legacy-empty-key": _carried_verbatim(lambda user_id: {"resumeKey": ""}),
    "legacy-non-string-key": _carried_verbatim(lambda user_id: {"resumeKey": 7}),
    "row-and-a-stale-extra-copy": _row_and_a_stale_copy,
    "no-resume": lambda user_id: _save(user_id, {"summary": "no resume"}),
    "no-profile-row": _drop_profile_row,
}


@pytest.mark.parametrize("shape", sorted(_PROFILE_SHAPES))
def test_collect_resume_keys_names_what_the_document_names(client, shape):
    """Ledger ``account_service``:105/309. The erasure path read the whole
    document for one key. Whatever the profile's shape -- the key promoted to a
    ``resumes`` row, still riding in ``extra`` from the migration, junk there,
    absent, or no profile row at all -- the key it names is the one
    ``load_document`` names, and intake keys follow it, de-duplicated."""
    from model import IntakeSubmission, User, db
    from solverah.repositories import profile_repository
    from solverah.services import account_service

    _, user_id = _sign_in(client)
    with _app().app_context():
        _PROFILE_SHAPES[shape](user_id)

    with _app().app_context():
        document_key = profile_repository.load_document(user_id).get("resumeKey")
        expected = [document_key] if document_key else []
        user = db.session.get(User, user_id)

        assert account_service.collect_resume_keys(user, []) == expected

        intakes = [IntakeSubmission(resume_key=key) for key in
                   (document_key or "intake/x/resume.pdf", "intake/y/resume.pdf", None)]
        assert account_service.collect_resume_keys(user, intakes) == list(
            dict.fromkeys(expected + [i.resume_key for i in intakes if i.resume_key])
        )


def test_collect_resume_keys_reads_one_row_for_a_promoted_profile(client):
    """Ledger ``account_service``:105: a profile with its resume on a row answers
    from that row alone, where the document was five profile reads and the
    assessment one."""
    from model import User, db
    from solverah.services import account_service
    from tests.query_count import count_queries

    _, user_id = _sign_in(client)
    with _app().app_context():
        _promoted(user_id)

    with _app().app_context():
        user = db.session.get(User, user_id)
        with count_queries() as statements:
            keys = account_service.collect_resume_keys(user, [])

    assert keys == [_resume_key(user_id)]
    assert len(statements) == 1, statements
    assert _reads_of(statements, "resumes") == statements
