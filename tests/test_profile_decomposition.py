"""Phase 2a: the profile lives in rows, and nothing above the repository can tell.

Two claims are being kept honest here and they pull in opposite directions, which
is why both need saying.

**The document is unchanged.**  ``GET /me/profile`` served ``users.profile_data``
verbatim and now serves six tables reassembled.  If a single key, value or list
order differs, the SPA is wrong and nobody finds out until a user notices their
skills are in a different order.  That is what the round-trip corpus below is
for, and it deliberately includes documents that are *malformed* -- a migration
that quietly repairs bad data has changed data it was not asked to change.

**The rows are real.**  A decomposition that put the whole blob in
``profiles.extra`` would satisfy every round-trip assertion in this file and
achieve nothing: no index, no row-level concurrency, no queryable skill.  So the
tests that matter most here are the ones counting rows.

Byte-identity, concretely
-------------------------
Flask serialises with ``sort_keys=True``, so JSON *object* key order is
alphabetical no matter what order a dict was built in, and byte-identity reduces
to the same keys with the same values.  *Array* order is not sorted and is not
free -- ``experience`` and ``skills`` come back in the order they went in only
because the rows carry an ``ordinal``.  ``test_the_response_is_sorted_json``
pins the assumption so flipping ``app.json.sort_keys`` cannot silently turn a
formatting preference into a contract change.
"""

import json

import pytest

from solverah.domain import profile_document as document_domain
from solverah.domain.auth import default_profile
from solverah.domain.profile import profile_completion_percent
from solverah.domain.skills import slugify

EMAIL = "decompose@example.com"
PASSWORD = "Strongpass1!"


def _noop(*_args, **_kwargs):
    return None


# ---------------------------------------------------------------------------
# The pure round trip: assemble(decompose(d)) == d, for every d
# ---------------------------------------------------------------------------

#: Documents chosen for the ways they can break the mapping, not for how typical
#: they are. Anything in here that stops round-tripping is a profile someone
#: loses.
ROUND_TRIP_CORPUS = [
    pytest.param({}, id="empty"),
    pytest.param(default_profile(email="a@b.c", name="Ada Lovelace"), id="fresh-registration"),
    pytest.param({"deleted_at": "2026-01-01T00:00:00+00:00"}, id="tombstone"),
    # Scalars: "" promotes, None does not, absent is absent. Three states that a
    # nullable column on its own collapses into two.
    pytest.param({"phone": ""}, id="empty-string-scalar"),
    pytest.param({"phone": None}, id="null-scalar"),
    pytest.param({"phone": 5551234}, id="wrong-typed-scalar"),
    pytest.param({"summary": "s", "linkedinUrl": "u", "career_status": "employed"}, id="all-scalars"),
    # Lists: empty and absent are different, and neither has any rows to be.
    pytest.param({"experience": []}, id="empty-experience"),
    pytest.param({"experience": "not a list"}, id="experience-is-a-string"),
    pytest.param({"experience": [{"position": "no company key"}]}, id="experience-missing-company"),
    pytest.param({"experience": [{"company": "A", "position": "B"}, "junk"]}, id="experience-mixed"),
    pytest.param(
        {"experience": [
            {"id": 1, "company": "Acme", "position": "Eng", "startDate": "2020-01-15",
             "endDate": "Present", "description": "x"},
            {"id": 2, "company": "Beta", "position": "Intern", "startDate": "",
             "endDate": "2019 - 2020", "description": ""},
        ]},
        id="experience-mixed-date-formats",
    ),
    pytest.param({"education": [{"institution": "MIT", "degree": "BS", "gpa": "4.0"}]}, id="education"),
    pytest.param({"education": [{"institution": "", "degree": "one free-text line"}]}, id="education-parser-fallback"),
    # Skills: the list and the ratings promote independently.
    pytest.param({"skills": ["Python", "C++", "C#", ".NET", "Node.js"]}, id="skills-with-symbols"),
    pytest.param({"skills": ["Python", "python"]}, id="skills-slug-collision"),
    pytest.param({"skills": ["Python", 5]}, id="skills-non-string"),
    pytest.param({"skills": ["Python"], "skill_levels": {"Python": "advanced"}}, id="skills-and-ratings"),
    pytest.param({"skills": ["Python"], "skill_levels": {"python": "advanced"}}, id="ratings-spelt-differently"),
    pytest.param({"skill_levels": {"Rust": "beginner"}}, id="rating-without-the-list"),
    pytest.param({"skill_levels": {"Rust": "wizard"}}, id="rating-outside-the-vocabulary"),
    pytest.param({"skills": [], "skill_levels": {}}, id="both-empty"),
    # Resume: the row carries the key, `uploadedResume` carries the filename.
    pytest.param({"resumeKey": ""}, id="empty-resume-key"),
    pytest.param(
        {"resumeKey": "profile/1/a/r.pdf",
         "uploadedResume": {"name": "r.pdf", "size": 12, "type": "application/pdf"}},
        id="resume",
    ),
    pytest.param(
        {"resumeKey": "profile/1/a/r.pdf",
         "uploadedResume": {"name": "r.pdf", "size": 12, "type": "application/pdf"},
         "_parsedResumeSnapshot": {"resumeKey": "profile/1/a/r.pdf",
                                   "experience": [], "education": [], "skills": []}},
        id="parsed-resume",
    ),
    pytest.param({"resumeKey": "profile/1/a/r.pdf", "uploadedResume": None}, id="resume-without-metadata"),
    # Whatever else has accumulated in the blob over the years.
    pytest.param(
        {"quizResults": {"a": [1, 2]}, "_quizSummary": {"a": {"counts": {}, "avgIndex": None, "n": 0}},
         "quizInsights": {"g": {"x": 1}}, "culture_preferences": {"empathy": 0.5},
         "path_preferences": {"move_intent": "stay"}, "focus_type_result": {"archetype": "X"},
         "manager_match_result": {"archetype": "Y"}, "applications": [{"job": "one"}],
         "skills_proficiency_confirmed": True},
        id="everything-else",
    ),
]


@pytest.mark.parametrize("document", ROUND_TRIP_CORPUS)
def test_the_document_survives_the_round_trip(document):
    """The invariant the whole phase rests on. No database needed."""
    assert document_domain.assemble(document_domain.decompose(document)) == document


@pytest.mark.parametrize("document", ROUND_TRIP_CORPUS)
def test_every_key_lands_somewhere(document):
    """Nothing is dropped on the way in.

    The round trip above would also pass if a key were dropped and then
    reinvented with the same value. This says where each key actually went:
    a column, a child table, or ``extra`` -- exactly one of the three.
    """
    state = document_domain.decompose(document)

    promoted = set()
    for key, column in document_domain.SCALAR_COLUMNS:
        if state.scalars.get(column) is not None:
            promoted.add(key)
    if state.experiences:
        promoted.add("experience")
    if state.educations:
        promoted.add("education")
    if any(row.ordinal is not None for row in state.skills):
        promoted.add("skills")
    if any(row.proficiency is not None for row in state.skills):
        promoted.add("skill_levels")
    if state.resume is not None:
        promoted.add("resumeKey")

    assert promoted | set(state.extra) == set(document)
    assert promoted & set(state.extra) == set(), "a key is in two places at once"


# ---------------------------------------------------------------------------
# The skill slug rule -- what it collapses, and what it deliberately does not
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "labels, slug",
    [
        (["Python", "python", "PYTHON", " Python "], "python"),
        (["Node.js", "Node JS", "node-js", "node_js", "NODE.JS"], "node-js"),
        (["machine learning", "  machine   learning ", "Machine-Learning"], "machine-learning"),
        (["Café Management", "Cafe Management"], "cafe-management"),
    ],
)
def test_these_spellings_are_one_skill(labels, slug):
    assert {slugify(label) for label in labels} == {slug}


@pytest.mark.parametrize(
    "label, slug",
    [("C", "c"), ("C++", "cpp"), ("C#", "csharp"), ("F#", "fsharp"), (".NET", "dotnet")],
)
def test_symbol_bearing_names_stay_distinct(label, slug):
    """The trap the substitution table exists for.

    Strip punctuation first and ``C``, ``C++`` and ``C#`` all become ``c``:
    three unrelated skills in one row, and every profile claiming one claims all
    three. Substituting while the symbols are still there keeps them apart.
    """
    assert slugify(label) == slug


@pytest.mark.parametrize(
    "left, right",
    [("JS", "JavaScript"), ("React", "React.js"), ("k8s", "Kubernetes"), ("Postgres", "PostgreSQL")],
)
def test_near_duplicates_are_not_merged(left, right):
    """Deliberate. See solverah/domain/skills.py.

    Merging these needs a curated dictionary. Inventing one inside a storage
    migration would change which skills a profile matches on, which is a scoring
    change wearing a schema change's clothes. `skills.aliases` and the trigram
    index exist so the curation can happen later as data.
    """
    assert slugify(left) != slugify(right)


@pytest.mark.parametrize("label", ["", "   ", "---", "🙂", None, 5, ["Python"]])
def test_things_that_do_not_name_a_skill(label):
    assert slugify(label) is None


# ---------------------------------------------------------------------------
# The rows are real
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns (csrf_token, user_id)."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Decompose User",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        user.email_confirmed = True
        db.session.commit()
        user_id = user.id

    resp = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"], user_id


RICH_PATCH = {
    "experience": [
        {"id": 1, "company": "Acme", "position": "Principal", "startDate": "2020-01-15",
         "endDate": "Present", "description": "led"},
        {"id": 2, "company": "Beta", "position": "Engineer", "startDate": "",
         "endDate": "2019 - 2020", "description": ""},
    ],
    "education": [{"id": 1, "institution": "MIT", "degree": "BS", "gpa": "4.0"}],
    "skills": ["Python", "C++", "Node.js"],
    "skill_levels": {"Python": "advanced"},
    "summary": "A summary.",
    "phone": "555-0100",
    "linkedinUrl": "https://example.com/in/x",
    "career_status": "employed",
    "resumeKey": "profile/1/abc/resume.pdf",
    "uploadedResume": {"name": "cv.pdf", "size": 900, "type": "application/pdf"},
}


@pytest.fixture()
def rich_profile(client, auth):
    csrf, user_id = auth
    resp = client.patch(
        "/api/v1/me/profile", json={"profile": RICH_PATCH},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    return csrf, user_id


def _rows(user_id):
    from app import app
    from model import Profile, ProfileEducation, ProfileExperience, ProfileSkill, Resume, db

    with app.app_context():
        return {
            "profile": db.session.get(Profile, user_id),
            "experiences": ProfileExperience.query.filter_by(user_id=user_id)
            .order_by(ProfileExperience.ordinal).all(),
            "educations": ProfileEducation.query.filter_by(user_id=user_id).all(),
            "skills": ProfileSkill.query.filter_by(user_id=user_id).all(),
            "resumes": Resume.query.filter_by(user_id=user_id).all(),
        }


def test_experience_becomes_rows_not_a_blob(rich_profile):
    """The point of the phase. Without this, everything else is bookkeeping."""
    _csrf, user_id = rich_profile
    rows = _rows(user_id)["experiences"]

    assert len(rows) == 2
    assert [row.company_name for row in rows] == ["Acme", "Beta"]
    assert [row.title for row in rows] == ["Principal", "Engineer"]
    assert [row.ordinal for row in rows] == [0, 1]


def test_an_iso_date_becomes_a_date_and_free_text_does_not(rich_profile):
    """Promotion is by fit, not by hope.

    "2020-01-15" is a date and becomes one. "2019 - 2020" and "Present" are not,
    and forcing them would either fail the write or silently change what the user
    typed, so they ride in the row's ``extra`` and come back verbatim.
    """
    _csrf, user_id = rich_profile
    first, second = _rows(user_id)["experiences"]

    assert first.start_date.isoformat() == "2020-01-15"
    assert first.end_date is None
    assert first.extra["endDate"] == "Present"
    assert second.start_date is None
    assert second.extra["endDate"] == "2019 - 2020"


def test_a_current_role_is_flagged_on_the_row(rich_profile):
    """`is_current` is derived so it can be queried, and never read back out.

    The document's own ``endDate`` is what round-trips. This column is what makes
    "who is currently employed" an index scan instead of a JSON walk.
    """
    _csrf, user_id = rich_profile
    first, second = _rows(user_id)["experiences"]

    assert first.is_current is True
    assert second.is_current is False


#: An education entry that exercises the one column in the profile tables whose
#: attribute name and column name differ. ``RICH_PATCH``'s entry carries no
#: ``field``, which is exactly why every test in this file passed while the value
#: was being dropped.
EDUCATION_WITH_FIELD = {
    "education": [
        {
            "id": 1,
            # `institution`, not `school`. `_decompose_educations` requires
            # `institution` and leaves the entry whole in `extra` without it --
            # where `field` survives for the wrong reason, and this test would
            # pass against the broken write path.
            "institution": "State University",
            "degree": "BS",
            "field": "Computer Science",
        }
    ],
}


def test_the_education_field_survives_a_write(client, auth):
    """Regression: ``education[].field`` was silently dropped on every save.

    ``_write_children`` builds an **ORM-enabled** bulk insert --
    ``sa.insert(ProfileEducation)`` with a list of dicts -- and an ORM bulk
    insert keys on *attribute* names. ``ProfileEducation.field_of_study`` is
    declared as ``db.Column("field", ...)``, so the dict key ``"field"`` matched
    no attribute, and SQLAlchemy dropped it without raising. The column went in
    NULL, ``assemble`` omits a null ``field_of_study``, and the key vanished from
    the document.

    Every other key in those three insert dicts happens to have an identical
    attribute and column name, which is why this was the only field affected --
    and why the fix is to spell the attribute rather than to stop using bulk
    inserts.

    The migration was never wrong: it writes raw SQL against the real column
    name, so data carried across by Phase 2a is intact. Only writes through the
    application lost the value.
    """
    csrf, user_id = auth

    resp = client.patch(
        "/api/v1/me/profile", json={"profile": EDUCATION_WITH_FIELD},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200

    served = client.get("/api/v1/me/profile").get_json()["profile"]["education"][0]
    assert served["field"] == "Computer Science"
    assert served["institution"] == "State University"
    assert served["degree"] == "BS"

    # The read path reads the attribute and always looked right; this asserts it
    # against a row the corrected insert actually wrote, rather than assuming.
    row = _rows(user_id)["educations"][0]
    assert row.field_of_study == "Computer Science"


#: Every column in the schema whose database name differs from its ORM
#: attribute, as of 2026-08-27. Read off the mapper by the test below.
RENAMED_COLUMNS = {
    ("profile_educations", "field_of_study", "field"),
    ("audit_log", "event_metadata", "metadata"),
}


def test_the_set_of_renamed_columns_is_still_these_two():
    """A tripwire for the next renamed column, not a schema inventory.

    A column whose attribute and database names differ is the only way an
    ORM-enabled bulk insert can drop a value in silence: the insert keys on
    attribute names, the schema is written in column names, and a key that
    matches no attribute produces no error. ``profile_educations.field`` was
    written that way for the whole life of Phase 2a and nothing failed.

    So the trap is set at the moment a third renamed column appears, which is
    months before someone bulk-inserts into it. If this test fails, the new
    column is fine -- go and check that every ``sa.insert(Entity)`` writing to it
    spells the *attribute*, then add it here.

    ``audit_log.event_metadata`` is in the set and is safe today: its only write
    is the ORM constructor in ``solverah/services/audit.py``, and a constructor
    keys on attributes. Nothing bulk-inserts into it.
    """
    from sqlalchemy import inspect

    from model import db

    found = set()
    for mapped in db.Model.registry._class_registry.values():
        if not hasattr(mapped, "__tablename__"):
            continue
        for prop in inspect(mapped).mapper.column_attrs:
            column = prop.columns[0]
            if column.name != prop.key:
                found.add((mapped.__tablename__, prop.key, column.name))

    assert found == RENAMED_COLUMNS


def test_skills_reference_the_dimension_table(rich_profile):
    """Free text on the way in, a foreign key on the way out."""
    from app import app
    from model import Skill

    _csrf, user_id = rich_profile
    rows = _rows(user_id)["skills"]

    assert len(rows) == 3
    from model import db

    with app.app_context():
        slugs = {db.session.get(Skill, row.skill_id).slug: row.label for row in rows}
    assert slugs == {"python": "Python", "cpp": "C++", "node-js": "Node.js"}


def test_a_rating_lands_on_the_skill_row(rich_profile):
    """`skill_levels` is not a second blob; it is a column on the skill."""
    _csrf, user_id = rich_profile
    rated = {row.label: row.proficiency for row in _rows(user_id)["skills"]}

    assert rated["Python"] == document_domain.PROFICIENCY_SCORES["advanced"]
    assert rated["C++"] is None


def test_two_users_spelling_a_skill_differently_share_one_row(client, rich_profile, monkeypatch):
    """The dedupe, end to end.

    The dimension keeps the first spelling and records the second as an alias;
    each user still reads back the capitalisation they typed. A shared row that
    renamed itself for whoever wrote last would give the earlier user someone
    else's spelling.
    """
    from app import app
    from model import Skill, User, db
    from solverah.repositories import profile_repository

    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    client.post(
        "/api/v1/auth/register",
        json={"email": "second@example.com", "password": PASSWORD, "name": "Second",
              "role": "job-seeker", "terms_accepted": True},
    )

    with app.app_context():
        other = User.query.filter_by(email="second@example.com").first()
        profile_repository.update_document(
            other.id, lambda existing: {**existing, "skills": ["PYTHON"]}
        )
        db.session.commit()

        assert Skill.query.filter_by(slug="python").count() == 1
        row = Skill.query.filter_by(slug="python").one()
        assert row.label == "Python"
        assert "PYTHON" in row.aliases

        assert profile_repository.load_document(other.id)["skills"] == ["PYTHON"]


def test_the_resume_gets_a_row(rich_profile):
    _csrf, user_id = rich_profile
    rows = _rows(user_id)["resumes"]

    assert len(rows) == 1
    assert rows[0].object_key == "profile/1/abc/resume.pdf"
    assert rows[0].mime == "application/pdf"
    assert rows[0].size_bytes == 900


def test_a_replaced_resume_leaves_no_row_behind(client, rich_profile):
    """Retention depends on this.

    `retention_cleanup` deletes object-storage keys no row references. If the
    superseded resume kept its row, its bytes would be referenced forever and
    never swept -- a retention change smuggled in with a storage change.
    """
    csrf, user_id = rich_profile
    client.patch(
        "/api/v1/me/profile",
        json={"profile": {"resumeKey": "profile/1/def/resume.pdf"}},
        headers={"X-CSRF-TOKEN": csrf},
    )

    rows = _rows(user_id)["resumes"]
    assert [row.object_key for row in rows] == ["profile/1/def/resume.pdf"]


def test_an_undecomposable_list_stays_whole_in_extra(client, auth):
    """One bad entry parks the list, and the profile is still served intact.

    Half in rows and half in a blob would make the assembled order a coin toss,
    so the rule is all-or-nothing per list. What must never happen is data loss,
    and it does not: ``extra`` reassembles to exactly what it holds.
    """
    csrf, user_id = auth
    payload = {"experience": [{"company": "A", "position": "B"}, {"position": "no company"}]}

    client.patch("/api/v1/me/profile", json={"profile": payload},
                 headers={"X-CSRF-TOKEN": csrf})

    assert _rows(user_id)["experiences"] == []
    assert _rows(user_id)["profile"].extra["experience"] == payload["experience"]
    assert client.get("/api/v1/me/profile").get_json()["profile"]["experience"] == payload["experience"]


# ---------------------------------------------------------------------------
# The columns the service is supposed to maintain
# ---------------------------------------------------------------------------


def test_the_version_advances_on_every_write(client, rich_profile):
    """`profiles.version` is the compare-and-swap token, so it has to move."""
    csrf, user_id = rich_profile
    before = _rows(user_id)["profile"].version

    client.patch("/api/v1/me/profile", json={"profile": {"summary": "again"}},
                 headers={"X-CSRF-TOKEN": csrf})

    assert _rows(user_id)["profile"].version == before + 1


def test_updated_at_moves_without_the_application_touching_it(client, rich_profile):
    """Part 4.1 rule 5: the trigger does it, not the write path.

    The write path builds its UPDATE column by column from the optimistic-lock
    comparison, so a column it forgets is a column that stops being maintained.
    This asserts the one that cannot be forgotten.
    """
    csrf, user_id = rich_profile
    before = _rows(user_id)["profile"].updated_at

    client.patch("/api/v1/me/profile", json={"profile": {"summary": "later"}},
                 headers={"X-CSRF-TOKEN": csrf})

    assert _rows(user_id)["profile"].updated_at > before


def test_completeness_agrees_with_what_the_dashboard_reports(client, rich_profile):
    """The column and the request path must not be able to disagree.

    ``profiles.completeness`` is maintained on write so "how many profiles are
    more than 80% complete" is a query rather than a scan of a JSON column. The
    dashboard still computes its own percentage from the assembled document, and
    that is on purpose -- a read-time computation cannot drift. This asserts the
    two say the same thing, which is what makes the column trustworthy enough to
    query later.
    """
    _csrf, user_id = rich_profile
    from solverah.repositories import profile_repository
    from app import app

    with app.app_context():
        document = profile_repository.load_document(user_id)

    stored = _rows(user_id)["profile"].completeness
    assert stored == profile_completion_percent(document)
    assert client.get("/api/v1/me/dashboard").get_json()["profileCompletion"] == "%d%%" % stored


# ---------------------------------------------------------------------------
# The contract the frontend is holding us to
# ---------------------------------------------------------------------------


def test_the_response_is_sorted_json(client, rich_profile):
    """Byte-identity rests on this, so it is asserted rather than assumed.

    With ``sort_keys=True`` a dict's insertion order is invisible in the output
    and byte-identity reduces to "same keys, same values". Flip it and every
    reassembled object could serialise in a different order from the blob that
    preceded it -- a contract change made by a formatting setting.
    """
    from app import app

    assert app.json.sort_keys is True

    # `.rstrip()` only for the newline jsonify appends; everything before it is
    # the assertion.
    body = client.get("/api/v1/me/profile").data.decode("utf-8").rstrip("\n")
    assert body == json.dumps(json.loads(body), sort_keys=True, separators=(",", ":"))


def test_list_order_is_preserved_across_a_write(client, rich_profile):
    """Arrays are not sorted by the serialiser; ``ordinal`` is what holds them.

    JSON object keys come back sorted whatever happens. Arrays come back in the
    order the rows were read, so ``skills`` in the order the user arranged them
    is a property of the schema, not of the encoder.
    """
    _csrf, user_id = rich_profile
    body = client.get("/api/v1/me/profile").get_json()["profile"]

    assert body["skills"] == ["Python", "C++", "Node.js"]
    assert [entry["company"] for entry in body["experience"]] == ["Acme", "Beta"]


def test_the_served_document_is_exactly_what_was_stored(client, rich_profile):
    """The end-to-end version of the round-trip property.

    ``clean_profile_data`` strips unknown keys on the way in and the merge adds
    ``skills_proficiency_confirmed``, so the served document is not the patch
    body -- it is the patch body merged over what was there. What it must equal
    is what the repository says is stored.
    """
    from app import app
    from solverah.repositories import profile_repository

    _csrf, user_id = rich_profile
    with app.app_context():
        stored = profile_repository.load_document(user_id)

    assert client.get("/api/v1/me/profile").get_json()["profile"] == stored
    for key, value in RICH_PATCH.items():
        assert stored[key] == value, "%s did not survive the write" % key
