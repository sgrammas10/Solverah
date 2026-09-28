"""DB ledger, package A: the profile and assessment repositories, measured.

Every test here pins one of the ledger's findings against ``profile_repository``
or ``assessment_repository`` and was written to fail on the code before the fix
(the few characterisation tests that pass on both are marked as such). What they
share is the rule the whole package works under: the stored state and the
document the API serves do not change -- only the number of statements it takes
to produce them does.

Row identity is read from ``xmin`` as well as ``id``. ``profile_skills`` has no
surrogate key -- its primary key is ``(user_id, skill_id)``, which a
delete-and-reinsert reproduces exactly -- so "was this row rewritten" is a
question only the system column can answer for every child table alike.
"""

import contextlib
import copy
import datetime
import re
import threading

import pytest
import sqlalchemy as sa
from sqlalchemy import event

USER_A = 7101
USER_B = 7102
USER_C = 7103
USER_D = 7104

NARROW_KEYS = ("pulse_settings", "culture_preferences", "path_preferences", "quizInsights")

#: A document that exercises every child table and every narrow key. The
#: ratings are deliberately out of alphabetical order and two of them rate
#: skills the list does not name, because ``_read_state`` returns those rows
#: sorted by label while ``decompose`` emits them in dict order: a save that
#: changed nothing must still recognise the two orders as the same rows.
RICH = {
    "firstName": "Ada",
    "lastName": "Lovelace",
    "email": "ada@example.test",
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
    "skill_levels": {"Rust": "beginner", "Python": "advanced", "Go": "intermediate"},
    "resumeKey": "profile/7101/abc/resume.pdf",
    "uploadedResume": {"name": "cv.pdf", "size": 900, "type": "application/pdf"},
    "_parsedResumeSnapshot": {"resumeKey": "profile/7101/abc/resume.pdf",
                              "experience": [], "education": [], "skills": []},
    "quizInsights": {"careerQuizzes": {"q1": {"summary": "steady"}}},
    "pulse_settings": {"cadence": "weekly", "awaiting_response": False},
    "culture_preferences": {"empathy": 0.5, "pace": "fast"},
    "path_preferences": {"move_intent": "stay"},
}

_CHILD_TABLES = (
    ("profile_experiences", "id"),
    ("profile_educations", "id"),
    ("profile_skills", "skill_id"),
    ("resumes", "id"),
)


def _app():
    from app import app

    return app


def _rich():
    return copy.deepcopy(RICH)


@pytest.fixture()
def users(seed_user):
    seed_user(USER_A, USER_B, USER_C, USER_D)
    return USER_A, USER_B, USER_C, USER_D


def _seed(user_id, document):
    """Store *document* through the one write path and commit it."""
    from model import db
    from solverah.repositories import profile_repository

    stored = copy.deepcopy(document)
    profile_repository.update_document(user_id, lambda _existing: copy.deepcopy(stored))
    db.session.commit()


def _identities(user_id):
    """``(key, xmin)`` for every child row, per table. A rewrite changes the pair."""
    from model import db

    return {
        table: [
            tuple(row)
            for row in db.session.execute(
                sa.text(
                    "SELECT %s, xmin::text FROM %s WHERE user_id = :u ORDER BY %s"
                    % (key, table, key)
                ),
                {"u": user_id},
            )
        ]
        for table, key in _CHILD_TABLES
    }


_CONTENT_SQL = {
    "profile_experiences": (
        "SELECT company_name, title, start_date, end_date, is_current, description, "
        "source, ordinal, extra FROM profile_experiences WHERE user_id = :u ORDER BY ordinal"
    ),
    "profile_educations": (
        "SELECT institution, degree, field, start_date, end_date, source, ordinal, extra "
        "FROM profile_educations WHERE user_id = :u ORDER BY ordinal"
    ),
    "profile_skills": (
        "SELECT s.slug, ps.label, ps.proficiency, ps.ordinal, ps.source FROM profile_skills ps "
        "JOIN skills s ON s.id = ps.skill_id WHERE ps.user_id = :u ORDER BY s.slug"
    ),
    "resumes": (
        "SELECT object_key, mime, size_bytes, status, parsed_at FROM resumes "
        "WHERE user_id = :u ORDER BY id"
    ),
}


def _contents(user_id, exact_times=True):
    """Every stored child value, minus the columns only a rewrite changes.

    ``exact_times=False`` reduces ``resumes.parsed_at`` to whether it is set, for
    comparing two users whose resumes were parsed at different moments.
    """
    from model import db

    contents = {
        table: [tuple(row) for row in db.session.execute(sa.text(sql), {"u": user_id})]
        for table, sql in _CONTENT_SQL.items()
    }
    if not exact_times:
        contents["resumes"] = [row[:-1] + (row[-1] is not None,) for row in contents["resumes"]]
    return contents


def _profile_row(user_id):
    from model import db

    return db.session.execute(
        sa.text(
            "SELECT extra, completeness, version, headline, summary, location_state, "
            "location_city, phone, linkedin_url, portfolio_url, career_status "
            "FROM profiles WHERE user_id = :u"
        ),
        {"u": user_id},
    ).mappings().one()


def _version(user_id):
    from model import db

    return db.session.execute(
        sa.text("SELECT version FROM profiles WHERE user_id = :u"), {"u": user_id}
    ).scalar_one()


@contextlib.contextmanager
def _count_round_trips():
    """``count_queries``, except an executemany counts once per parameter set.

    psycopg2's ``executemany`` is one ``before_cursor_execute`` event and one
    round trip per row, which is exactly the shape the ``_skill_ids`` finding is
    about -- the shared counter would report it as one statement. Only a *list*
    of parameter sets is a real executemany: an "insertmanyvalues" batch also
    arrives flagged ``executemany`` but with one dict, and is one round trip.
    """
    from model import db

    trips = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        many = executemany and isinstance(parameters, (list, tuple))
        trips.extend([statement] * (len(parameters) if many else 1))

    event.listen(db.engine, "before_cursor_execute", _record)
    try:
        yield trips
    finally:
        event.remove(db.engine, "before_cursor_execute", _record)


def _in_another_transaction(work):
    """Run *work* to completion as a second writer: its own thread, app context,
    session and connection. Called from inside a mutate callback, it lands a
    commit between that writer's read and its compare-and-swap."""
    errors = []

    def target():
        try:
            with _app().app_context():
                work()
        except Exception as exc:  # noqa: BLE001 -- re-raised below
            errors.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout=30)
    assert not thread.is_alive(), "the competing writer never finished"
    if errors:
        raise errors[0]


# ---------------------------------------------------------------------------
# The narrow keys: verified, then read and written without the document
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["text", 7, [1, "two", None], {"a": {"b": 1}}, [], {}, None])
def test_every_narrow_key_rides_in_extra_untouched(value):
    """The verification the narrow helpers rest on, as an executable check.

    Each key must never be promoted by ``decompose``, must come back out of
    ``assemble`` exactly as ``extra`` holds it, and must not count toward
    ``completeness`` -- so reading or writing it alone cannot disagree with the
    whole-document path. Characterisation of the domain module; fails before
    the fix only because ``NARROW_EXTRA_KEYS`` does not exist.
    """
    from solverah.domain import profile_document as document_domain
    from solverah.domain.profile import PROFILE_COMPLETION_FIELDS
    from solverah.repositories import profile_repository

    assert profile_repository.NARROW_EXTRA_KEYS == frozenset(NARROW_KEYS)
    promoted = {key for key, _column in document_domain.SCALAR_COLUMNS} | {
        "experience", "education", "skills", "skill_levels", "resumeKey",
    }

    for key in profile_repository.NARROW_EXTRA_KEYS:
        document = {key: copy.deepcopy(value), "summary": "s", "skills": ["Python"]}
        state = document_domain.decompose(document)
        assert state.extra == {key: value}, key
        assert document_domain.assemble(state)[key] == value, key
        assert document_domain.assemble(
            document_domain.ProfileState(extra={key: copy.deepcopy(value)})
        ) == {key: value}, key
        assert key not in PROFILE_COMPLETION_FIELDS
        assert key not in document_domain.ASSESSMENT_RESULT_KEYS.values()
        assert key not in promoted


@pytest.mark.parametrize("key", ["summary", "skills", "resumeKey", "email", "focus_type_result"])
def test_the_narrow_helpers_refuse_every_other_key(users, key):
    """A key outside the set could be promoted, merged or counted, so the
    helpers refuse it rather than silently disagreeing with the document."""
    from solverah.repositories import profile_repository

    with _app().app_context():
        with pytest.raises(ValueError):
            profile_repository.read_extra_key(USER_A, key)
        with pytest.raises(ValueError):
            profile_repository.read_extra_key_for_users([USER_A], key)
        with pytest.raises(ValueError):
            profile_repository.update_extra_key(USER_A, key, lambda old: old)


def test_read_extra_key_is_load_document_get_in_one_select(users):
    from model import db
    from solverah.repositories import profile_repository
    from tests.query_count import count_queries

    with _app().app_context():
        _seed(USER_A, _rich())
        partial = _rich()
        del partial["path_preferences"]
        partial["pulse_settings"] = None  # present, and JSON null
        _seed(USER_B, partial)
        # USER_C has no profiles row at all.

        for user_id in (USER_A, USER_B, USER_C):
            document = profile_repository.load_document(user_id)
            for key in NARROW_KEYS:
                with count_queries() as statements:
                    value = profile_repository.read_extra_key(user_id, key)
                assert value == document.get(key), (user_id, key)
                assert len(statements) == 1, statements
        db.session.rollback()


def test_read_extra_key_for_users_is_one_select_and_omits_the_absent(users):
    from solverah.repositories import profile_repository
    from tests.query_count import count_queries

    with _app().app_context():
        _seed(USER_A, _rich())
        with_null = _rich()
        with_null["culture_preferences"] = None
        _seed(USER_B, with_null)
        without = _rich()
        del without["culture_preferences"]
        _seed(USER_C, without)
        # USER_D has no profiles row.

        with count_queries() as statements:
            found = profile_repository.read_extra_key_for_users(
                [USER_A, USER_B, USER_C, USER_D], "culture_preferences"
            )
        assert len(statements) == 1, statements
        assert found == {USER_A: RICH["culture_preferences"], USER_B: None}
        for user_id, value in found.items():
            assert value == profile_repository.read_extra_key(user_id, "culture_preferences")

        with count_queries() as statements:
            assert profile_repository.read_extra_key_for_users([], "culture_preferences") == {}
        assert statements == []


@pytest.mark.parametrize("key", NARROW_KEYS)
def test_update_extra_key_stores_exactly_what_update_document_would(users, key):
    """Same ``extra``, same ``completeness``, same version bump, same children --
    three statements instead of seven-plus. Also the cache contract: the
    dashboard key is queued for invalidation on commit, never before."""
    from model import db
    from solverah.infra import cache
    from solverah.repositories import profile_repository
    from tests.query_count import count_queries

    def mutate(old):
        updated = dict(old) if isinstance(old, dict) else {}
        updated["touched"] = True
        return updated

    with _app().app_context():
        _seed(USER_A, _rich())
        _seed(USER_B, _rich())
        seeded_version = _version(USER_A)

        with count_queries() as statements:
            returned = profile_repository.update_extra_key(USER_A, key, mutate)
        pending = list(db.session.info.get(cache.SESSION_INVALIDATION_KEY, []))
        profile_repository.update_document(
            USER_B, lambda document: {**document, key: mutate(document.get(key))}
        )
        db.session.commit()

        a, b = _profile_row(USER_A), _profile_row(USER_B)
        contents_a = _contents(USER_A, exact_times=False)
        contents_b = _contents(USER_B, exact_times=False)
        document_a = profile_repository.load_document(USER_A)
        document_b = profile_repository.load_document(USER_B)

    assert returned == mutate(RICH[key])
    assert len(statements) <= 3, statements
    assert cache.dashboard_key(USER_A) in pending
    assert dict(a) == dict(b)
    assert a["version"] == seeded_version + 1
    assert contents_a == contents_b
    assert document_a == document_b == {**RICH, key: mutate(RICH[key])}


def test_update_extra_key_creates_a_missing_row_like_update_document(users):
    from model import db
    from solverah.repositories import profile_repository

    with _app().app_context():
        returned = profile_repository.update_extra_key(
            USER_C, "path_preferences", lambda old: {"was": old, "move_intent": "leave"}
        )
        profile_repository.update_document(
            USER_D, lambda document: {**document, "path_preferences": {"was": None, "move_intent": "leave"}}
        )
        db.session.commit()
        c, d = dict(_profile_row(USER_C)), dict(_profile_row(USER_D))

    assert returned == {"was": None, "move_intent": "leave"}
    assert c == d
    assert c["version"] == 1 and c["completeness"] == 0


# ---------------------------------------------------------------------------
# Mixed concurrent writes (Review Focus 2): a swap that loses is retried
# ---------------------------------------------------------------------------


def test_update_extra_key_retries_when_a_document_write_commits_in_between(users):
    from model import db
    from solverah.repositories import profile_repository

    with _app().app_context():
        _seed(USER_A, {"summary": "original", "pulse_settings": {"cadence": "weekly"}})
        start = _version(USER_A)

    def competitor():
        profile_repository.update_document(
            USER_A, lambda d: {**d, "summary": "theirs", "culture_preferences": {"x": 1}}
        )
        db.session.commit()

    seen = []

    def mutate(old):
        seen.append(copy.deepcopy(old))
        if len(seen) == 1:
            _in_another_transaction(competitor)
        return {**(old or {}), "cadence": "monthly"}

    with _app().app_context():
        profile_repository.update_extra_key(USER_A, "pulse_settings", mutate)
        db.session.commit()
        document = profile_repository.load_document(USER_A)
        version = _version(USER_A)

    assert len(seen) == 2, "the losing swap was not retried: %r" % seen
    assert document["summary"] == "theirs"
    assert document["culture_preferences"] == {"x": 1}
    assert document["pulse_settings"] == {"cadence": "monthly"}
    assert version == start + 2


def test_update_document_retries_when_an_extra_key_write_commits_in_between(users):
    from model import db
    from solverah.repositories import profile_repository

    with _app().app_context():
        _seed(USER_A, _rich())
        start = _version(USER_A)

    def competitor():
        profile_repository.update_extra_key(
            USER_A, "path_preferences", lambda _old: {"move_intent": "leave"}
        )
        db.session.commit()

    seen = []

    def mutate(document):
        seen.append(copy.deepcopy(document))
        if len(seen) == 1:
            _in_another_transaction(competitor)
        return {**document, "summary": "mine", "skills": ["Python", "Go"]}

    with _app().app_context():
        profile_repository.update_document(USER_A, mutate)
        db.session.commit()
        document = profile_repository.load_document(USER_A)
        version = _version(USER_A)

    assert len(seen) == 2
    assert seen[1]["path_preferences"] == {"move_intent": "leave"}
    assert document["path_preferences"] == {"move_intent": "leave"}
    assert document["summary"] == "mine"
    assert document["skills"] == ["Python", "Go"]
    assert version == start + 2


def test_same_key_racers_both_apply_rather_than_one_overwriting(users):
    """The lost update itself: two increments must make two."""
    from model import db
    from solverah.repositories import profile_repository

    with _app().app_context():
        _seed(USER_A, {"quizInsights": {"n": 0}})

    def competitor():
        profile_repository.update_document(
            USER_A, lambda d: {**d, "quizInsights": {"n": d["quizInsights"]["n"] + 1}}
        )
        db.session.commit()

    seen = []

    def mutate(old):
        seen.append(old["n"])
        if len(seen) == 1:
            _in_another_transaction(competitor)
        return {"n": old["n"] + 1}

    with _app().app_context():
        profile_repository.update_extra_key(USER_A, "quizInsights", mutate)
        db.session.commit()
        stored = profile_repository.read_extra_key(USER_A, "quizInsights")

    assert seen == [0, 1]
    assert stored == {"n": 2}


def test_update_extra_key_gives_up_loudly_after_max_attempts(users):
    from model import db
    from solverah.repositories import profile_repository

    with _app().app_context():
        _seed(USER_A, {"quizInsights": {"n": 0}})
        start = _version(USER_A)

    calls = []

    def mutate(old):
        calls.append(old)
        with db.engine.begin() as other:  # a second connection, committed at once
            other.execute(
                sa.text("UPDATE profiles SET version = version + 1 WHERE user_id = :u"),
                {"u": USER_A},
            )
        return {"n": 99}

    with _app().app_context():
        with pytest.raises(profile_repository.ConcurrentProfileUpdate):
            profile_repository.update_extra_key(USER_A, "quizInsights", mutate)
        db.session.rollback()
        stored = profile_repository.read_extra_key(USER_A, "quizInsights")
        version = _version(USER_A)

    assert len(calls) == profile_repository.MAX_WRITE_ATTEMPTS
    assert stored == {"n": 0}
    assert version == start + profile_repository.MAX_WRITE_ATTEMPTS


# ---------------------------------------------------------------------------
# update_document: unchanged child lists are left alone
# ---------------------------------------------------------------------------


def test_an_extra_only_save_is_at_most_eight_statements_and_rewrites_no_child_row(users):
    from model import db
    from solverah.infra import cache
    from solverah.repositories import profile_repository
    from tests.query_count import count_queries

    new_insights = {"careerQuizzes": {"q1": {"summary": "changed"}}}
    with _app().app_context():
        _seed(USER_A, _rich())
        before = _identities(USER_A)
        contents_before = _contents(USER_A)
        start = _version(USER_A)

        with count_queries() as statements:
            returned = profile_repository.update_document(
                USER_A, lambda d: {**d, "quizInsights": new_insights}
            )
        pending = list(db.session.info.get(cache.SESSION_INVALIDATION_KEY, []))
        db.session.commit()

        after = _identities(USER_A)
        contents_after = _contents(USER_A)
        document = profile_repository.load_document(USER_A)
        version = _version(USER_A)

    expected = {**RICH, "quizInsights": new_insights}
    assert len(statements) <= 8, "\n".join(statements)
    assert after == before
    assert contents_after == contents_before
    assert returned == expected
    assert document == expected
    assert version == start + 1
    assert cache.dashboard_key(USER_A) in pending


def _change_experience(d):
    d["experience"][0]["description"] = "led, then left"
    return d


def _change_education(d):
    d["education"][0]["degree"] = "BA"
    return d


def _change_skills(d):
    d["skills"] = ["Python", "C++", "Node.js", "Haskell"]
    return d


def _change_ratings(d):
    d["skill_levels"] = {**d["skill_levels"], "Rust": "advanced"}
    return d


def _change_resume(d):
    d["resumeKey"] = "profile/7101/def/resume.pdf"
    d["uploadedResume"] = {"name": "cv2.pdf", "size": 1200, "type": "application/pdf"}
    return d


@pytest.mark.parametrize(
    "change, rewritten",
    [
        (_change_experience, "profile_experiences"),
        (_change_education, "profile_educations"),
        (_change_skills, "profile_skills"),
        (_change_ratings, "profile_skills"),
        (_change_resume, "resumes"),
    ],
    ids=["experience", "education", "skills", "skill_levels", "resume"],
)
def test_a_one_list_save_rewrites_that_list_and_nothing_else(users, change, rewritten):
    """Review Focus 1. The changed list is still replaced; every other list --
    including ``education.field`` and the experience rows' ``extra`` -- stays the
    same rows with the same values, and the served document is exactly the
    mutated one."""
    from model import db
    from solverah.repositories import profile_repository

    with _app().app_context():
        _seed(USER_A, _rich())
        before = _identities(USER_A)
        contents_before = _contents(USER_A)

        returned = profile_repository.update_document(USER_A, lambda d: change(copy.deepcopy(d)))
        db.session.commit()

        after = _identities(USER_A)
        contents_after = _contents(USER_A)
        document = profile_repository.load_document(USER_A)

    expected = change(_rich())
    assert returned == expected
    assert document == expected
    assert after[rewritten] != before[rewritten], "the changed list was not written"
    for table, _key in _CHILD_TABLES:
        if table != rewritten:
            assert after[table] == before[table], "%s was rewritten" % table
            assert contents_after[table] == contents_before[table], table
    assert contents_after["profile_educations"][0][2] == "Computer Science"
    assert contents_after["profile_experiences"][1][-1] == {
        "id": 2, "startDate": "", "endDate": "2019 - 2020",
    }


def test_a_profile_still_in_extra_is_promoted_on_its_next_write(users):
    """Characterisation (passes before and after): a profile the Phase 2a
    migration carried verbatim has its lists in ``extra`` and no child rows.
    Skipping "unchanged" lists must compare against the rows, not the document,
    or this profile would never be promoted."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from model import Profile, db
    from solverah.repositories import profile_repository

    legacy = {"summary": "s", "experience": [{"company": "Acme", "position": "Eng"}],
              "skills": ["Python"]}
    with _app().app_context():
        db.session.execute(pg_insert(Profile).values(
            user_id=USER_A, extra=legacy, completeness=0, version=0))
        db.session.commit()

        profile_repository.update_document(USER_A, lambda d: {**d, "quizInsights": {"g": 1}})
        db.session.commit()
        contents = _contents(USER_A)
        extra = _profile_row(USER_A)["extra"]
        document = profile_repository.load_document(USER_A)

    assert [row[0] for row in contents["profile_experiences"]] == ["Acme"]
    assert [row[0] for row in contents["profile_skills"]] == ["python"]
    assert "experience" not in extra and "skills" not in extra
    assert document == {**legacy, "quizInsights": {"g": 1}}


def test_parsed_at_survives_an_unrelated_save(users):
    from model import db
    from solverah.repositories import profile_repository

    def parsed_at():
        return db.session.execute(
            sa.text("SELECT parsed_at FROM resumes WHERE user_id = :u"), {"u": USER_A}
        ).scalar_one()

    with _app().app_context():
        _seed(USER_A, _rich())
        first = parsed_at()
        assert first is not None, "the seed resume should be parsed"

        profile_repository.update_document(USER_A, lambda d: {**d, "summary": "Edited."})
        db.session.commit()
        after_unrelated = parsed_at()

        reparsed_key = "profile/7101/xyz/resume.pdf"
        profile_repository.update_document(USER_A, lambda d: {
            **d, "resumeKey": reparsed_key,
            "_parsedResumeSnapshot": {**d["_parsedResumeSnapshot"], "resumeKey": reparsed_key},
        })
        db.session.commit()
        after_new_resume = parsed_at()

    assert after_unrelated == first
    assert after_new_resume is not None and after_new_resume != first


def test_skill_aliases_are_one_statement_whatever_the_number_of_skills(users):
    """``_skill_ids``: the alias UPDATE was one round trip per skill."""
    from model import Skill, db
    from solverah.repositories import profile_repository

    canonical = ["Python", "Go", "Rust", "Haskell", "Elixir", "Scala"]

    def alias_updates(user_id, skills):
        with _count_round_trips() as trips:
            profile_repository.update_document(user_id, lambda d: {**d, "skills": skills})
        db.session.commit()
        return [t for t in trips if " ".join(t.split()).upper().startswith("UPDATE SKILLS")]

    with _app().app_context():
        _seed(USER_A, {"skills": canonical})
        one = alias_updates(USER_B, ["PYTHON"])
        six = alias_updates(USER_C, [label.upper() for label in canonical])
        alias_updates(USER_D, ["Python"])  # the canonical spelling adds nothing
        rows = {row.slug: (row.label, list(row.aliases)) for row in Skill.query.all()}

    assert len(one) == len(six) == 1, (one, six)
    assert rows["python"] == ("Python", ["PYTHON"])
    for label in canonical[1:]:
        assert rows[label.lower()] == (label, [label.upper()])


# ---------------------------------------------------------------------------
# load_document, current_submissions, current_result
# ---------------------------------------------------------------------------


def _submit(user_id, kind, *, result=None, answers=None, narrative=None,
            completed_at=None, status="scored"):
    from model import AssessmentForm, AssessmentSubmission, db

    AssessmentForm.register(kind, "dbopt-a")
    # Omitted rather than passed as None: the ORM stores an explicit None in a
    # JSON column as JSON `null`, which is not the SQL NULL a `core` row's check
    # constraint (and an unscored sitting) has.
    payloads = {"result": result, "answers": answers, "narrative": narrative}
    row = AssessmentSubmission(
        user_id=user_id, kind=kind, form_version="dbopt-a", status=status,
        completed_at=completed_at,
        **{name: value for name, value in payloads.items() if value is not None},
    )
    db.session.add(row)
    db.session.flush()
    return row.id


def _load_document_as_it_was(user_id):
    """The pre-fix ``load_document``: the same assembly, then one
    ``current_submission`` per result key. The oracle for "identical"."""
    from solverah.domain import profile_document as document_domain
    from solverah.repositories import assessment_repository, profile_repository

    state, _version = profile_repository._read_state(user_id)
    document = document_domain.assemble(state)
    for kind, key in document_domain.ASSESSMENT_RESULT_KEYS.items():
        submission = assessment_repository.current_submission(user_id, kind)
        result = submission.result if submission is not None else None
        if result is None:
            document.pop(key, None)
        else:
            document[key] = result
    return document


def test_load_document_is_identical_and_one_statement_cheaper(users):
    from model import db
    from solverah.repositories import profile_repository
    from tests.query_count import count_queries

    now = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
    stale = {"focus_type_result": {"stale": True}, "manager_match_result": {"stale": True}}
    with _app().app_context():
        # A: both results on rows. B: stale copies in extra, and a focus_type
        # sitting with no result yet. C: stale copies and no sittings. D: no
        # profile row, one result.
        _seed(USER_A, _rich())
        _submit(USER_A, "focus_type", result={"archetype": "Deep"}, completed_at=now)
        _submit(USER_A, "manager_match", result={"archetype": "Coach"}, answers=[1, 2],
                narrative="n", completed_at=now)
        _submit(USER_A, "work_pulse", result={"archetype": "WP"}, completed_at=now)
        _seed(USER_B, {**_rich(), **stale})
        _submit(USER_B, "focus_type", status="in_progress")
        _seed(USER_C, {"summary": "only", **stale})
        _submit(USER_D, "manager_match", result={"archetype": "Solo"}, completed_at=now)
        db.session.commit()

    for user_id in (USER_A, USER_B, USER_C, USER_D):
        with _app().app_context():
            with count_queries() as old_statements:
                expected = _load_document_as_it_was(user_id)
        with _app().app_context():
            with count_queries() as statements:
                document = profile_repository.load_document(user_id)

        assert document == expected, user_id
        assert len(statements) == len(old_statements) - 1, (user_id, statements)

        with _app().app_context():
            with count_queries() as narrow_statements:
                internal = profile_repository.load_document(user_id, include_assessments=False)
        assert internal == {
            k: v for k, v in expected.items()
            if k not in ("focus_type_result", "manager_match_result")
        }, user_id
        assert len(narrow_statements) == len(old_statements) - 2, (user_id, narrow_statements)
        assert not any("assessment_submissions" in s for s in narrow_statements)

    with _app().app_context():
        a = profile_repository.load_document(USER_A)
        c = profile_repository.load_document(USER_C)
    assert a["focus_type_result"] == {"archetype": "Deep"}
    assert a["manager_match_result"] == {"archetype": "Coach"}
    # Only the two result keys are merged; the Work Pulse sitting is not.
    assert set(a) == set(RICH) | {"focus_type_result", "manager_match_result"}
    assert "focus_type_result" not in c and "manager_match_result" not in c


def test_current_submissions_applies_the_current_rule_in_one_query(users):
    """Same rule as ``current_submission``: newest ``completed_at`` with the
    unfinished last, then highest id -- which only matters for ``core``, the
    kind that appends."""
    from model import db
    from solverah.repositories import assessment_repository
    from tests.query_count import count_queries

    t1 = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    t2 = datetime.datetime(2026, 2, 1, tzinfo=datetime.timezone.utc)
    kinds = ["core", "work_pulse", "wpll", "focus_type", "manager_match"]
    with _app().app_context():
        _submit(USER_A, "core", completed_at=t1)
        _submit(USER_A, "core", completed_at=t2)
        _submit(USER_A, "core", completed_at=None, status="in_progress")
        _submit(USER_A, "core", completed_at=t2)  # ties t2; the higher id wins
        _submit(USER_A, "work_pulse", result={"a": 1}, answers=[1], completed_at=t1)
        _submit(USER_A, "focus_type", completed_at=None, status="in_progress")
        _submit(USER_B, "wpll", answers=[9], completed_at=t2)
        _submit(USER_B, "core", completed_at=t2)
        db.session.commit()

    for user_id in (USER_A, USER_B, USER_C):
        with _app().app_context():
            expected = {}
            for kind in kinds:
                row = assessment_repository.current_submission(user_id, kind)
                if row is not None:
                    expected[kind] = row.id
        with _app().app_context():
            with count_queries() as statements:
                found = assessment_repository.current_submissions(user_id, kinds + ["core"])
            assert {kind: row.id for kind, row in found.items()} == expected, user_id
            assert all(row.kind == kind and row.user_id == user_id for kind, row in found.items())
            assert len(statements) == 1

    with _app().app_context():
        with count_queries() as statements:
            assert assessment_repository.current_submissions(USER_A, []) == {}
        assert statements == []


def test_current_result_is_the_current_row_without_the_narrative(users):
    """Every column the result readers touch -- ``result``, ``completed_at``,
    and the ``answers`` ManagerMatch's precondition diffs against -- arrives in
    the one SELECT. ``narrative`` (a copy of ``result["narrative"]``) does not,
    and stays reachable by a lazy load."""
    from model import db
    from solverah.repositories import assessment_repository
    from tests.query_count import count_queries

    t1 = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    with _app().app_context():
        _submit(USER_A, "manager_match", result={"narrative": "long", "archetype": "Coach"},
                answers=[1, 2, 3], narrative="long", completed_at=t1)
        _submit(USER_A, "core", completed_at=t1)
        _submit(USER_A, "core", completed_at=None, status="in_progress")
        db.session.commit()

    def reader_view(row):
        return None if row is None else (
            row.id, row.kind, row.status, row.result, row.answers, row.completed_at)

    for kind in ("manager_match", "core", "focus_type"):
        with _app().app_context():
            full = assessment_repository.current_submission(USER_A, kind)
            expected = reader_view(full)
            narrative = None if full is None else full.narrative
        with _app().app_context():
            with count_queries() as statements:
                row = assessment_repository.current_result(USER_A, kind)
                seen = reader_view(row)
            assert seen == expected, kind
            assert len(statements) == 1, "a result reader's column was lazy-loaded: %r" % statements
            assert "narrative" not in statements[0]
            if row is not None:
                assert "narrative" in sa.inspect(row).unloaded
                assert row.narrative == narrative  # still reachable, by one lazy load


def test_a_full_read_after_current_result_completes_the_same_instance(users):
    """The two readers share one identity-map instance, so a full read after a
    narrow one fills in the narrative rather than leaving a hole behind it."""
    from model import db
    from solverah.repositories import assessment_repository
    from tests.query_count import count_queries

    t1 = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    with _app().app_context():
        _submit(USER_A, "manager_match", result={"archetype": "Coach"}, answers=[1],
                narrative="long", completed_at=t1)
        db.session.commit()

    with _app().app_context():
        narrow = assessment_repository.current_result(USER_A, "manager_match")
        assert "narrative" in sa.inspect(narrow).unloaded
        full = assessment_repository.current_submission(USER_A, "manager_match")
        assert full is narrow
        with count_queries() as statements:
            assert full.narrative == "long"
        assert statements == []


# ---------------------------------------------------------------------------
# The retention sweep's keys, parser corrections, the intake probe
# ---------------------------------------------------------------------------


def _referenced_keys_as_it_was():
    """The pre-fix Python walk over every ``extra`` blob. The oracle."""
    from model import Profile, Resume, db

    keys = set()
    for (key,) in db.session.execute(sa.select(Resume.object_key)):
        if key:
            keys.add(key)
    for (extra,) in db.session.execute(sa.select(Profile.extra)):
        if not isinstance(extra, dict):
            continue
        if extra.get("resumeKey"):
            keys.add(extra["resumeKey"])
        snapshot = extra.get("_parsedResumeSnapshot")
        if isinstance(snapshot, dict) and snapshot.get("resumeKey"):
            keys.add(snapshot["resumeKey"])
    return keys


def test_referenced_resume_keys_are_identical_without_shipping_extra(users):
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from model import Profile, db
    from solverah.repositories import profile_repository
    from tests.query_count import count_queries

    snapshot_only = "profile/7101/old/resume.pdf"
    with _app().app_context():
        # A: a promoted profile -- a resumes row, and a snapshot of an older key.
        rich = _rich()
        rich["_parsedResumeSnapshot"] = {**rich["_parsedResumeSnapshot"], "resumeKey": snapshot_only}
        _seed(USER_A, rich)
        # B: carried by the migration and never rewritten -- the key is in extra.
        # C: nothing usable. D: only a snapshot.
        for user_id, extra in (
            (USER_B, {"resumeKey": "profile/7102/legacy/r.pdf", "quizInsights": {"big": "x" * 5000}}),
            (USER_C, {"resumeKey": "", "_parsedResumeSnapshot": "not a dict"}),
            (USER_D, {"_parsedResumeSnapshot": {"resumeKey": "profile/7104/snap/r.pdf"}}),
        ):
            db.session.execute(pg_insert(Profile).values(
                user_id=user_id, extra=extra, completeness=0, version=0))
        db.session.commit()

        expected = _referenced_keys_as_it_was()
        with count_queries() as statements:
            keys = profile_repository.referenced_resume_keys()

    assert keys == expected == {
        RICH["resumeKey"], snapshot_only, "profile/7102/legacy/r.pdf", "profile/7104/snap/r.pdf",
    }
    profile_reads = [" ".join(s.split()) for s in statements if "FROM profiles" in s]
    assert profile_reads, statements
    for statement in profile_reads:
        bare = re.findall(r"profiles\.extra(?!\s*(?:\[|->|#>))", statement)
        assert not bare, "whole extra blobs are shipped: %s" % statement


def _corrections(user_id):
    from model import db

    return {
        row.field: row
        for row in db.session.execute(
            sa.text(
                "SELECT field, resume_key, parsed_value::text AS parsed, "
                "corrected_value::text AS corrected, created_at, updated_at "
                "FROM resume_parse_correction WHERE user_id = :u"
            ),
            {"u": user_id},
        )
    }


def test_correction_upsert_stores_what_the_loop_stored(users):
    """Characterisation (passes before and after): the insert stores both values
    as given -- a Python None as JSON ``null`` -- and a second edit moves only
    ``corrected_value`` and ``updated_at``, keeping the parser's original."""
    from model import db
    from solverah.repositories import profile_repository

    key = "profile/7101/abc/resume.pdf"
    with _app().app_context():
        written = profile_repository.record_resume_corrections(USER_A, key, [
            ("experience", [{"company": "Parsed"}], [{"company": "Fixed"}]),
            ("education", None, [{"institution": "MIT"}]),
            ("skills", ["py"], None),
        ])
        db.session.commit()
        first = _corrections(USER_A)

        again = profile_repository.record_resume_corrections(USER_A, key, [
            ("experience", [{"company": "IGNORED"}], [{"company": "Fixed again"}]),
        ])
        db.session.commit()
        second = _corrections(USER_A)

        dup_key = "profile/7101/dup/resume.pdf"
        dup = profile_repository.record_resume_corrections(USER_B, dup_key, [
            ("skills", ["a"], ["b"]),
            ("skills", ["IGNORED"], ["c"]),
        ])
        db.session.commit()
        duplicates = _corrections(USER_B)

    assert (written, again, dup) == (3, 1, 2)
    assert {f: (r.parsed, r.corrected) for f, r in first.items()} == {
        "experience": ('[{"company": "Parsed"}]', '[{"company": "Fixed"}]'),
        "education": ("null", '[{"institution": "MIT"}]'),
        "skills": ('["py"]', "null"),
    }
    assert all(r.created_at == r.updated_at for r in first.values())
    assert len(second) == 3
    assert second["experience"].parsed == '[{"company": "Parsed"}]'
    assert second["experience"].corrected == '[{"company": "Fixed again"}]'
    assert second["experience"].created_at == first["experience"].created_at
    assert second["experience"].updated_at != first["experience"].updated_at
    assert second["education"] == first["education"]
    assert {f: (r.parsed, r.corrected) for f, r in duplicates.items()} == {
        "skills": ('["a"]', '["c"]'),
    }


def test_correction_upsert_is_one_statement_whatever_the_number_of_fields(users):
    from model import db
    from solverah.repositories import profile_repository
    from tests.query_count import count_queries

    three = [("experience", [1], [2]), ("education", [3], [4]), ("skills", [5], [6])]

    def measure(user_id, corrections):
        with count_queries() as statements:
            profile_repository.record_resume_corrections(user_id, "k", corrections)
            db.session.flush()
        db.session.commit()
        return len(statements)

    with _app().app_context():
        inserts = (measure(USER_A, three[:1]), measure(USER_B, three))
        updates = (measure(USER_A, three[:1]), measure(USER_B, three))
        rows = db.session.execute(sa.text(
            "SELECT user_id, count(*) FROM resume_parse_correction GROUP BY user_id "
            "ORDER BY user_id")).all()

    assert inserts[0] == inserts[1], inserts
    assert updates[0] == updates[1], updates
    assert [tuple(r) for r in rows] == [(USER_A, 1), (USER_B, 3)]


def test_has_intake_submission_is_an_exists_probe(users):
    from model import IntakeSubmission, db
    from solverah.repositories import profile_repository
    from tests.query_count import count_queries

    with _app().app_context():
        db.session.add(IntakeSubmission(
            id="dbopt-a-intake", first_name="I", last_name="S", email="Intake@Example.test",
            state="TX", resume_key="intake/x/r.pdf", resume_mime="application/pdf",
            resume_size_bytes=10,
        ))
        db.session.commit()

        with count_queries() as statements:
            present = profile_repository.has_intake_submission("Intake@Example.test")
        absent = profile_repository.has_intake_submission("nobody@example.test")
        # Case-sensitive: the rule the docstring records until wave 3 normalises it.
        other_case = profile_repository.has_intake_submission("intake@example.test")

    assert (present, absent, other_case) == (True, False, False)
    assert len(statements) == 1
    assert "EXISTS" in statements[0].upper(), statements[0]
    assert "first_name" not in statements[0], "a whole row is loaded to test existence"
