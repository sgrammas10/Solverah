"""Queries against the profile tables.

Phase 2a moved the profile out of ``users.profile_data`` and into ``profiles``,
``profile_experiences``, ``profile_educations``, ``skills``, ``profile_skills``
and ``resumes``.  Nothing outside this module knows that.  Callers ask for a
*document* -- the same dict shape ``profile_data`` held -- and get one back; the
mapping between that document and the rows lives in
:mod:`solverah.domain.profile_document`, which is pure and therefore testable
without a database.

Two things in here are load-bearing.

**Every write goes through :func:`update_document`** -- or, for one of the
:data:`NARROW_EXTRA_KEYS`, through :func:`update_extra_key`, which is the same
compare-and-swap on the same ``profiles.version``.  There is no setter and no
way to assign a document, because a caller holding a document it read a moment
ago is exactly the read-modify-write that made P0-1 a lost update.  The mutate
callback is re-run against a fresh read whenever another writer got there first.

**Reads and writes use Core statements, not ORM instances.**  A retry has to see
what the other writer committed, and an ORM instance in the identity map does
not go and look.  Core `select()` always does.

The queries here are deliberately plain.  ``load_document`` is six round trips
where the blob was zero, because the blob rode along on the user row that was
already loaded.  Five of those are Phase 2a's decomposition; the sixth is Phase
2d fetching the FocusType and ManagerMatch results, which were blob keys and are
now rows -- both in one query, and none for a caller that passes
``include_assessments=False``.  A caller that needs only one of the
:data:`NARROW_EXTRA_KEYS` needs none of it: :func:`read_extra_key` is one SELECT.
The whole cost is paid on ``GET /me/profile``, not on the boot path --
``GET /auth/session`` never touches this module.  Phase 3's cache is where it
gets paid back.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from model import (
    IntakeSubmission,
    JobRecommendation,
    Profile,
    ProfileEducation,
    ProfileExperience,
    ProfileSkill,
    Resume,
    ResumeParseCorrection,
    Skill,
    db,
)
from solverah.infra import cache
from solverah.domain import profile_document as document_domain
from solverah.domain.profile_document import (
    EducationRow,
    ExperienceRow,
    ProfileState,
    ResumeRecord,
    SkillRow,
)
from solverah.repositories import assessment_repository

__all__ = [
    "MAX_WRITE_ATTEMPTS",
    "NARROW_EXTRA_KEYS",
    "ConcurrentProfileUpdate",
    "count_job_recommendations",
    "current_resume",
    "find_correction",
    "has_intake_submission",
    "load_document",
    "read_extra_key",
    "read_extra_key_for_users",
    "record_resume_corrections",
    "referenced_resume_keys",
    "resume_corrections_for_user",
    "update_document",
    "update_extra_key",
    "user_ids_missing",
]

#: How many times a losing writer re-reads and re-applies before giving up.
#:
#: Contention is naturally serialised: the conditional UPDATE takes a row lock,
#: so a second writer blocks until the first commits and then finds its version
#: stale on the first attempt rather than spinning. Five is a backstop against a
#: pathological pile-up, not a tuning parameter.
MAX_WRITE_ATTEMPTS = 5

#: ``profiles.extra`` keys that may be read and written on their own, without
#: assembling or decomposing the rest of the document.
#:
#: Each was checked for the three things that would let a one-key read or write
#: disagree with :func:`load_document` / :func:`update_document`, and
#: ``tests/test_dbopt_profile_repository.py`` re-checks all three:
#: ``decompose`` never promotes it to a column or a child row, so it lives in
#: ``extra`` verbatim whatever its value; ``assemble`` lays ``extra`` down first
#: and writes none of these keys over it; and it is not one of
#: ``PROFILE_COMPLETION_FIELDS``, so ``completeness`` cannot depend on it. None
#: is one of the two assessment result keys ``load_document`` merges from rows,
#: either. A key failing any of those belongs to the whole-document path.
NARROW_EXTRA_KEYS = frozenset(
    {"pulse_settings", "culture_preferences", "path_preferences", "quizInsights"}
)


def _require_narrow_key(key: str) -> None:
    if key not in NARROW_EXTRA_KEYS:
        raise ValueError(
            "%r is not one of NARROW_EXTRA_KEYS %s; read or write it through the "
            "whole document" % (key, sorted(NARROW_EXTRA_KEYS))
        )


class ConcurrentProfileUpdate(RuntimeError):
    """Raised when a write lost the compare-and-swap ``MAX_WRITE_ATTEMPTS`` times.

    Loud on purpose. The alternative -- writing anyway -- is the defect this
    whole phase exists to remove, and a silent 200 that discarded someone's edit
    is worse than a 500 that did not.
    """


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _read_state(user_id: int) -> Tuple[ProfileState, Optional[int]]:
    """The stored profile state and the version it was read at.

    A version of None means there is no ``profiles`` row yet, which is not an
    error: a user registered before the profile exists, and a document is
    assembled from nothing as ``{}``.
    """
    row = db.session.execute(
        sa.select(Profile).where(Profile.user_id == user_id)
    ).scalar_one_or_none()

    if row is None:
        return ProfileState(), None

    experiences = [
        ExperienceRow(
            company_name=item.company_name,
            title=item.title,
            ordinal=item.ordinal,
            start_date=item.start_date,
            end_date=item.end_date,
            is_current=item.is_current,
            description=item.description,
            source=item.source,
            extra=dict(item.extra or {}),
        )
        for item in db.session.execute(
            sa.select(ProfileExperience)
            .where(ProfileExperience.user_id == user_id)
            .order_by(ProfileExperience.ordinal)
        ).scalars()
    ]

    educations = [
        EducationRow(
            institution=item.institution,
            ordinal=item.ordinal,
            degree=item.degree,
            field_of_study=item.field_of_study,
            start_date=item.start_date,
            end_date=item.end_date,
            source=item.source,
            extra=dict(item.extra or {}),
        )
        for item in db.session.execute(
            sa.select(ProfileEducation)
            .where(ProfileEducation.user_id == user_id)
            .order_by(ProfileEducation.ordinal)
        ).scalars()
    ]

    skills = [
        SkillRow(
            slug=slug,
            label=item.label,
            ordinal=item.ordinal,
            proficiency=item.proficiency,
            source=item.source,
        )
        for item, slug in db.session.execute(
            sa.select(ProfileSkill, Skill.slug)
            .join(Skill, Skill.id == ProfileSkill.skill_id)
            .where(ProfileSkill.user_id == user_id)
            # NULLS LAST so the listed skills come first and the rated-but-not-
            # listed ones follow; `assemble` sorts the listed ones itself, so
            # this only has to be deterministic.
            .order_by(ProfileSkill.ordinal.nulls_last(), ProfileSkill.label)
        )
    ]

    resume_row = db.session.execute(
        sa.select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.created_at.desc(), Resume.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    resume = (
        ResumeRecord(
            object_key=resume_row.object_key,
            mime=resume_row.mime,
            size_bytes=resume_row.size_bytes,
            status=resume_row.status,
        )
        if resume_row is not None
        else None
    )

    state = ProfileState(
        scalars={
            "headline": row.headline,
            "summary": row.summary,
            "location_state": row.location_state,
            "location_city": row.location_city,
            "phone": row.phone,
            "linkedin_url": row.linkedin_url,
            "portfolio_url": row.portfolio_url,
            "career_status": row.career_status,
        },
        extra=dict(row.extra or {}),
        experiences=experiences,
        educations=educations,
        skills=skills,
        resume=resume,
        completeness=row.completeness,
    )
    return state, row.version


def load_document(user_id: int, *, include_assessments: bool = True) -> Dict[str, Any]:
    """The profile document for *user_id*, or ``{}`` when there is none.

    Byte-for-byte what ``users.profile_data`` used to hold. Everything that used
    to read the blob reads this instead, and nothing above this line can tell
    the difference -- which is the contract Phase 2a was required not to break
    and Phase 2d inherits.

    **Two keys are assembled from outside the profile tables.**
    ``focus_type_result`` and ``manager_match_result`` were blob keys, so 2a
    carried them into ``profiles.extra`` with everything else that had no
    column; 2d moved them to ``assessment_submissions``, where the other three
    instruments' results already live. They are still in this document because
    ``GET /me/profile`` and ``GET /me/export`` still return them and
    ``intelligence_service`` still reads them from here -- a storage change that
    dropped two keys off the wire would not be a storage change. Both rows come
    back from one :func:`assessment_repository.current_submissions` query.

    Merged after :func:`assemble` rather than inside it, and merged
    unconditionally, so the row is the only source: a stale copy left behind in
    ``extra`` cannot shadow it. (The migration removes those copies; this
    ordering is what makes a missed one harmless rather than silently
    authoritative.) Neither key is client-writable -- ``clean_profile_data``'s
    allowlist has never included them -- so nothing can put one back.

    ``include_assessments=False`` is for a caller that never sends either key
    anywhere: the assessment query is skipped and the document comes back
    without both keys -- exactly this document minus those two, never a stale
    copy from ``extra`` in their place.
    """
    state, _version = _read_state(user_id)
    document = document_domain.assemble(state)

    result_keys = document_domain.ASSESSMENT_RESULT_KEYS
    submissions = (
        assessment_repository.current_submissions(user_id, tuple(result_keys))
        if include_assessments
        else {}
    )
    for kind, key in result_keys.items():
        submission = submissions.get(kind)
        result = submission.result if submission is not None else None
        if result is None:
            document.pop(key, None)
        else:
            document[key] = result

    return document


def read_extra_key(user_id: int, key: str) -> Any:
    """``load_document(user_id).get(key)`` for one of :data:`NARROW_EXTRA_KEYS`.

    One SELECT of the one value, where the document is six. None when there is
    no ``profiles`` row, when the key is absent and when it holds JSON ``null``
    -- the three cases ``.get`` on the document does not tell apart either.

    Raises:
        ValueError: *key* is not in :data:`NARROW_EXTRA_KEYS`.
    """
    _require_narrow_key(key)
    return db.session.execute(
        sa.select(Profile.extra[key]).where(Profile.user_id == user_id)
    ).scalar_one_or_none()


def read_extra_key_for_users(user_ids: Sequence[int], key: str) -> Dict[int, Any]:
    """:func:`read_extra_key` for many users at once: ``{user_id: value}``, one SELECT.

    A user with no ``profiles`` row, or whose ``extra`` lacks the key, is left
    out rather than mapped to None, so ``result.get(user_id)`` reads the same as
    :func:`read_extra_key` either way; a key holding JSON ``null`` is present and
    maps to None. Sends nothing at all for an empty *user_ids*.

    Raises:
        ValueError: *key* is not in :data:`NARROW_EXTRA_KEYS`.
    """
    _require_narrow_key(key)
    ids = list(user_ids)
    if not ids:
        return {}
    rows = db.session.execute(
        sa.select(Profile.user_id, Profile.extra[key]).where(
            Profile.user_id.in_(ids),
            Profile.extra.has_key(key),  # noqa: W601 -- JSONB `?`, not dict
        )
    )
    return {user_id: value for user_id, value in rows}


def current_resume(user_id: int) -> Optional[Resume]:
    """The ``resumes`` row on this user's profile, or None.

    Exists so callers that need the MIME type do not have to reach into the
    document's ``uploadedResume`` sub-dict for it.
    """
    return db.session.execute(
        sa.select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.created_at.desc(), Resume.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def referenced_resume_keys() -> set:
    """Every object key the profile tables still point at.

    Used by the retention sweep, which deletes unreferenced objects, so a key
    missed here is a live resume deleted. Two places hold one: the ``resumes``
    row, and ``_parsedResumeSnapshot`` inside ``profiles.extra`` -- the snapshot
    keeps its key so a later edit can be diffed against what the parser produced
    even after the resume itself has been replaced.
    """
    keys = set()

    for (key,) in db.session.execute(sa.select(Resume.object_key)):
        if key:
            keys.add(key)

    # A profile carried over by the migration and never rewritten still has its
    # resumeKey in `extra` rather than in a `resumes` row. Both keys are pulled
    # out of `extra` in SQL, so the sweep reads two short strings per profile
    # instead of every profile's whole document. The JSON path is NULL wherever
    # a key is missing or a step is not an object -- the cases the Python walk
    # this replaced skipped with isinstance checks -- and an empty string is
    # skipped as before. The one difference is a value that is not a string: it
    # comes back as its JSON text, so `0` or `false` is named where the walk
    # skipped it and a list is named where the walk crashed. For a sweep that
    # deletes whatever is *not* named, naming an extra key is the safe way to
    # differ.
    legacy = Profile.extra["resumeKey"].astext
    snapshot = Profile.extra["_parsedResumeSnapshot"]["resumeKey"].astext
    for row in db.session.execute(
        sa.select(legacy, snapshot).where(sa.or_(legacy.isnot(None), snapshot.isnot(None)))
    ):
        keys.update(key for key in row if key)

    return keys


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _ensure_row(user_id: int) -> None:
    """Create the ``profiles`` row if it is missing, without racing.

    ``ON CONFLICT DO NOTHING`` rather than select-then-insert: two first-time
    writers for the same user would both see no row and both insert.
    """
    db.session.execute(
        pg_insert(Profile)
        .values(user_id=user_id, extra={}, completeness=0, version=0)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )


def _skill_ids(rows: List[SkillRow]) -> Dict[str, int]:
    """Resolve every slug to a ``skills`` row, creating what does not exist.

    The canonical ``label`` is first-writer-wins. A later user spelling the same
    skill differently does not rename the dimension; the spelling is appended to
    ``aliases`` instead, so the trigram index can find "Node.JS" on a row whose
    label says "Node.js".

    Three statements however many skills there are. The alias append is one
    UPDATE joined to the unnested ``(slug, label)`` pairs, not one per skill (an
    executemany is a round trip per row); ``by_slug`` holds each slug once, so no
    ``skills`` row can match two pairs.
    """
    if not rows:
        return {}

    by_slug: Dict[str, str] = {}
    for row in rows:
        by_slug.setdefault(row.slug, row.label)

    db.session.execute(
        pg_insert(Skill)
        .values([{"slug": slug, "label": label} for slug, label in by_slug.items()])
        .on_conflict_do_nothing(index_elements=["slug"])
    )

    db.session.execute(
        sa.text(
            "UPDATE skills SET aliases = skills.aliases || ARRAY[spelt.label]::text[] "
            "FROM unnest(CAST(:slugs AS text[]), CAST(:labels AS text[])) "
            "AS spelt(slug, label) "
            "WHERE skills.slug = spelt.slug AND skills.label <> spelt.label "
            "AND NOT (spelt.label = ANY(skills.aliases))"
        ),
        {"slugs": list(by_slug), "labels": list(by_slug.values())},
    )

    return {
        slug: skill_id
        for skill_id, slug in db.session.execute(
            sa.select(Skill.id, Skill.slug).where(Skill.slug.in_(by_slug))
        )
    }


def _json_identical(left: Any, right: Any) -> bool:
    """``left == right``, with the JSON types required to match as well.

    Python holds ``1 == 1.0 == True``; JSONB stores three different values. A
    list judged unchanged by ``==`` alone would never be written when the new
    document swapped one of those for another.
    """
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_identical(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_identical(a, b) for a, b in zip(left, right)
        )
    return left == right


def _same_rows(stored: Sequence[Any], wanted: Sequence[Any]) -> bool:
    """Whether writing *wanted* over *stored* would store exactly what is there.

    The rows are frozen dataclasses, so ``==`` compares every field the insert
    writes; ``extra`` is additionally compared type-strictly. Columns an insert
    leaves to their defaults (``id``, ``public_id``, the timestamps, and
    ``profile_skills.years``, which nothing writes) are the only ones a rewrite
    would change -- and not changing them is the point.
    """
    return len(stored) == len(wanted) and all(
        a == b and _json_identical(getattr(a, "extra", None), getattr(b, "extra", None))
        for a, b in zip(stored, wanted)
    )


def _by_slug(rows: Sequence[SkillRow]) -> List[SkillRow]:
    """Skill rows in a canonical order.

    ``_read_state`` returns the rated-but-unlisted rows sorted by label and
    ``decompose`` emits them in ``skill_levels`` order. Each row carries its own
    ordinal and a slug is unique per user, so sorting both sides by slug
    compares the rows rather than the order they were produced in.
    """
    return sorted(rows, key=lambda row: row.slug)


def _write_children(user_id: int, state: ProfileState, stored: ProfileState) -> None:
    """Bring the experience, education, skill and resume rows in line with *state*.

    *stored* is what this attempt read, and a list equal to its stored rows is
    not touched (``_same_rows`` defines equal). So an ``extra``-only save -- quiz
    insights, pulse settings, career status, the common case -- rewrites no child
    row at all, the lists a save did not change keep their ids, and the resume
    keeps its ``parsed_at``. The comparison is with the *rows*, not with the old
    document, which is what keeps lazy promotion working: a list the migration
    left riding in ``extra`` has no rows, so it differs, and its first write
    promotes it.

    A list that did change is replaced wholesale -- delete, then insert -- rather
    than diffed entry by entry. The document has no stable identity per entry --
    the frontend's list ``id`` is a timestamp for a new row and an array index
    for a parsed one -- so there is nothing to diff against.

    The consequence, stated so it is not discovered later: ``public_id`` on an
    experience or education row is **not** a stable handle; any change to its
    list reissues it. It becomes one when Part 5.2's ``/me/experiences`` lands and
    an entry is addressed and edited individually instead of arriving inside a
    whole document.

    Safe under concurrency only because the caller has already won the
    compare-and-swap on ``profiles.version``, which holds a row lock for the rest
    of the transaction. The same win is what makes *stored* trustworthy: it
    proves no other profile write committed between the read and the swap, and
    nothing writes these rows except after winning one.
    """
    if not _same_rows(stored.experiences, state.experiences):
        _write_experiences(user_id, state.experiences)
    if not _same_rows(stored.educations, state.educations):
        _write_educations(user_id, state.educations)
    if not _same_rows(_by_slug(stored.skills), _by_slug(state.skills)):
        _write_skills(user_id, state.skills)
    if stored.resume != state.resume:
        _write_resume(user_id, state.resume)


def _write_experiences(user_id: int, rows: List[ExperienceRow]) -> None:
    """Replace this user's ``profile_experiences`` rows with *rows*."""
    db.session.execute(
        sa.delete(ProfileExperience).where(ProfileExperience.user_id == user_id)
    )
    if rows:
        db.session.execute(
            sa.insert(ProfileExperience),
            [
                {
                    "user_id": user_id,
                    "company_name": row.company_name,
                    "title": row.title,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "is_current": row.is_current,
                    "description": row.description,
                    "source": row.source,
                    "ordinal": row.ordinal,
                    "extra": row.extra,
                }
                for row in rows
            ],
        )


def _write_educations(user_id: int, rows: List[EducationRow]) -> None:
    """Replace this user's ``profile_educations`` rows with *rows*."""
    db.session.execute(
        sa.delete(ProfileEducation).where(ProfileEducation.user_id == user_id)
    )
    if rows:
        db.session.execute(
            sa.insert(ProfileEducation),
            [
                {
                    "user_id": user_id,
                    "institution": row.institution,
                    "degree": row.degree,
                    # `field_of_study`, the mapped attribute -- NOT `field`, the
                    # column. These statements are ORM-enabled bulk inserts
                    # (an entity plus a list of dicts), and those key on
                    # attribute names; a key matching no attribute is dropped
                    # silently, with no error and a NULL in the column.
                    # `ProfileEducation.field_of_study = db.Column("field", ...)`
                    # is the only renamed column in the profile tables, so this
                    # is the only key in the three inserts here where the two
                    # names differ and the only one that can go wrong this way.
                    # It did: every save between Phase 2a and 2026-08-27 wrote
                    # NULL here. tests/test_profile_decomposition.py
                    # ::test_the_education_field_survives_a_write.
                    "field_of_study": row.field_of_study,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "source": row.source,
                    "ordinal": row.ordinal,
                    "extra": row.extra,
                }
                for row in rows
            ],
        )


def _write_skills(user_id: int, rows: List[SkillRow]) -> None:
    """Replace this user's ``profile_skills`` rows with *rows*."""
    db.session.execute(
        sa.delete(ProfileSkill).where(ProfileSkill.user_id == user_id)
    )
    if rows:
        skill_ids = _skill_ids(rows)
        db.session.execute(
            sa.insert(ProfileSkill),
            [
                {
                    "user_id": user_id,
                    "skill_id": skill_ids[row.slug],
                    "label": row.label,
                    "proficiency": row.proficiency,
                    "ordinal": row.ordinal,
                    "source": row.source,
                }
                for row in rows
            ],
        )


def _write_resume(user_id: int, resume: Optional[ResumeRecord]) -> None:
    """Bring ``resumes`` in line with the document's ``resumeKey``.

    Rows for keys the profile no longer names are deleted rather than kept, so
    the retention sweep can still reclaim a superseded upload. See the docstring
    on :class:`model.Resume`.

    Called only when the resume changed, so ``parsed_at`` -- stamped whenever a
    parsed resume is written here -- is when the resume was parsed, not when the
    profile was last saved.
    """
    if resume is None:
        db.session.execute(sa.delete(Resume).where(Resume.user_id == user_id))
        return

    db.session.execute(
        sa.delete(Resume).where(
            Resume.user_id == user_id, Resume.object_key != resume.object_key
        )
    )

    existing = db.session.execute(
        sa.select(Resume.id).where(
            Resume.user_id == user_id, Resume.object_key == resume.object_key
        )
    ).scalar_one_or_none()

    values = {
        "mime": resume.mime,
        "size_bytes": resume.size_bytes,
        "status": resume.status,
        "parsed_at": (
            datetime.datetime.now(datetime.timezone.utc)
            if resume.status == "parsed"
            else None
        ),
    }

    if existing is None:
        db.session.execute(
            sa.insert(Resume).values(
                user_id=user_id, object_key=resume.object_key, **values
            )
        )
    else:
        db.session.execute(sa.update(Resume).where(Resume.id == existing).values(**values))


def update_document(
    user_id: int, mutate: Callable[[Dict[str, Any]], Dict[str, Any]]
) -> Dict[str, Any]:
    """Read the profile, apply *mutate*, and store the result. The P0-1 fix.

    Args:
        user_id: Whose profile.
        mutate: A pure function from the stored document to the document that
            should replace it. It may be called more than once -- once per
            attempt -- so it must not have side effects and must not close over
            a document read outside this call. Closing over one is the bug.

    Returns:
        The document that was written.

    Raises:
        ConcurrentProfileUpdate: after ``MAX_WRITE_ATTEMPTS`` lost swaps.

    Does not commit; the caller owns the transaction, so a profile change and
    the audit row recording it still land together.

    The ordering inside the loop is the part that matters. The conditional
    UPDATE on ``profiles`` comes *first*, before a single child row is touched:
    a swap that loses has therefore written nothing and can simply go round
    again. Writing the children first would mean unwinding them, and unwinding
    inside a transaction the caller may also be using is not something this
    function is in a position to do.

    After a won swap, only the child lists that differ from the ones this
    attempt read are rewritten (see ``_write_children``). A save that changed
    nothing but ``extra`` or a scalar is the swap and nothing more: seven
    statements, where every save used to rewrite all four child tables.
    """
    _ensure_row(user_id)

    for _attempt in range(MAX_WRITE_ATTEMPTS):
        state, version = _read_state(user_id)
        if version is None:
            # _ensure_row ran, so the row exists; a None here means another
            # transaction deleted the user between the two statements.
            raise ConcurrentProfileUpdate(
                "profiles row for user %s disappeared mid-write" % user_id
            )

        document = document_domain.assemble(state)
        new_document = mutate(document)
        new_state = document_domain.decompose(new_document)

        result = db.session.execute(
            sa.update(Profile)
            .where(Profile.user_id == user_id, Profile.version == version)
            .values(
                extra=new_state.extra,
                completeness=new_state.completeness,
                version=Profile.version + 1,
                **new_state.scalars,
            )
            .execution_options(synchronize_session=False)
        )

        if result.rowcount == 0:
            # Somebody else committed between the read and here. Nothing of ours
            # has been written, so re-read and re-apply against what they left.
            continue

        _write_children(user_id, new_state, state)
        # The dashboard reads this document, so every successful swap retires its
        # cached payload (Phase 3). Registered here, in the write paths Phase 2a
        # left (this one and `update_extra_key`), rather than at each of the dozen
        # callers -- an invalidation a caller can forget is one that will be
        # forgotten, and the symptom is a stale number nobody reports. Dropped
        # after the caller's commit, never before: see solverah/infra/cache.py.
        cache.invalidate_on_commit(cache.dashboard_key(user_id))
        return new_document

    raise ConcurrentProfileUpdate(
        "gave up writing the profile for user %s after %d attempts"
        % (user_id, MAX_WRITE_ATTEMPTS)
    )


def update_extra_key(user_id: int, key: str, mutate: Callable[[Any], Any]) -> Any:
    """:func:`update_document` for one of :data:`NARROW_EXTRA_KEYS`, without the document.

    Args:
        user_id: Whose profile.
        key: The ``profiles.extra`` key to rewrite.
        mutate: A pure function from the stored value -- None when the key is
            absent, as ``document.get(key)`` would give -- to the value that
            should replace it. Re-run against a fresh read after every lost
            swap, so the same rules apply as to ``update_document``'s.

    Returns:
        The value that was written.

    Raises:
        ValueError: *key* is not in :data:`NARROW_EXTRA_KEYS`.
        ConcurrentProfileUpdate: after ``MAX_WRITE_ATTEMPTS`` lost swaps.

    The same compare-and-swap on the same ``profiles.version``, in the same
    order, so this and :func:`update_document` serialise against each other and
    neither can lose the other's write. It leaves out only what the key cannot
    affect -- the verification is on :data:`NARROW_EXTRA_KEYS` -- namely the
    other keys, the scalar columns, ``completeness`` and the child rows. That is
    three statements: the row guarantee, a read of the one value and the
    version, and the swap, which merges ``{key: value}`` into ``extra`` with
    JSONB ``||`` so the rest of ``extra`` never travels in either direction.

    Does not commit, and queues the same dashboard invalidation.

    One difference, by design: a profile the Phase 2a migration carried into
    ``extra`` verbatim, and nobody has saved since, stays that way -- nothing
    here decomposes it, so its lists are not promoted to rows. ``assemble``
    reads both shapes identically, so no reader can tell.
    """
    _require_narrow_key(key)
    _ensure_row(user_id)

    for _attempt in range(MAX_WRITE_ATTEMPTS):
        row = db.session.execute(
            sa.select(Profile.extra[key], Profile.version).where(
                Profile.user_id == user_id
            )
        ).one_or_none()
        if row is None:
            # As in update_document: _ensure_row ran, so the user was deleted
            # between the two statements.
            raise ConcurrentProfileUpdate(
                "profiles row for user %s disappeared mid-write" % user_id
            )
        stored, version = row
        value = mutate(stored)

        result = db.session.execute(
            sa.update(Profile)
            .where(Profile.user_id == user_id, Profile.version == version)
            .values(
                extra=Profile.extra.op("||", return_type=JSONB)(
                    sa.bindparam("extra_patch", {key: value}, type_=JSONB)
                ),
                version=Profile.version + 1,
            )
            .execution_options(synchronize_session=False)
        )

        if result.rowcount == 0:
            # Lost the swap: nothing of ours was written. Re-read, re-apply.
            continue

        cache.invalidate_on_commit(cache.dashboard_key(user_id))
        return value

    raise ConcurrentProfileUpdate(
        "gave up writing profile key %r for user %s after %d attempts"
        % (key, user_id, MAX_WRITE_ATTEMPTS)
    )


# ---------------------------------------------------------------------------
# Resume parser corrections, and the two counts the dashboard needs
# ---------------------------------------------------------------------------


def find_correction(
    user_id: int, resume_key: str, field: str
) -> Optional[ResumeParseCorrection]:
    """Return the existing correction row for this (user, resume, field)."""
    return ResumeParseCorrection.query.filter_by(
        user_id=user_id,
        resume_key=resume_key,
        field=field,
    ).first()


def record_resume_corrections(
    user_id: int,
    resume_key: str,
    corrections: List[tuple],
) -> int:
    """Upsert one ``ResumeParseCorrection`` per changed field, in one statement.

    Args:
        corrections: ``(field, parsed_value, corrected_value)`` triples, as
            produced by :func:`solverah.domain.profile.resume_field_corrections`.

    Returns:
        How many rows were written or updated -- one per triple.

    Note:
        ``parsed_value`` is only set on insert.  On a second edit of the same
        field the original parser output is preserved and only the corrected
        value moves -- otherwise the row would end up comparing the user's first
        edit to their second, and the parser signal would be lost.

    One ``INSERT ... ON CONFLICT (user_id, resume_key, field) DO UPDATE`` for all
    the fields together, where there was a SELECT and a write per field. The
    unique key the per-field lookup used to check by hand now arbitrates, so of
    two saves racing on one new field the second takes the update branch rather
    than failing its commit on ``uq_correction_user_resume_field``. Both branches
    store what the ORM path stored: an insert takes both values as given (None
    as JSON ``null``) and the columns' server defaults; a conflict moves
    ``corrected_value`` and stamps ``updated_at`` with naive UTC, leaving
    ``parsed_value`` and ``created_at`` alone. A field named twice in one call
    keeps its first parsed value and its last corrected value, as the loop's
    second pass over it did -- and has to be merged here first, because one
    statement cannot update the same row twice.
    """
    if not corrections:
        return 0

    rows: Dict[str, Dict[str, Any]] = {}
    for field, parsed_value, corrected_value in corrections:
        if field in rows:
            rows[field]["corrected_value"] = corrected_value
        else:
            rows[field] = {
                "user_id": user_id,
                "resume_key": resume_key,
                "field": field,
                "parsed_value": parsed_value,
                "corrected_value": corrected_value,
            }

    statement = pg_insert(ResumeParseCorrection).values(list(rows.values()))
    db.session.execute(
        statement.on_conflict_do_update(
            index_elements=["user_id", "resume_key", "field"],
            set_={
                "corrected_value": statement.excluded.corrected_value,
                # What `datetime.utcnow()` returned for the ORM path, without the
                # call Python 3.12 deprecated.
                "updated_at": datetime.datetime.now(datetime.timezone.utc).replace(
                    tzinfo=None
                ),
            },
        )
    )
    return len(corrections)


def resume_corrections_for_user(user_id: int) -> List[ResumeParseCorrection]:
    """Every resume-parser correction this user has saved, newest first.

    BUILD_PLAN D-7b: ``corrected_value`` is what the user typed to fix a
    parser-extracted field, so ``/me/export`` owes it the same way it owes any other
    answer the user gave -- this is the query that closes that gap.
    """
    return (
        ResumeParseCorrection.query.filter_by(user_id=user_id)
        .order_by(ResumeParseCorrection.created_at.desc())
        .all()
    )


def count_job_recommendations(user_id: int) -> int:
    """How many recommendation rows exist for this user."""
    return JobRecommendation.query.filter_by(user_id=user_id).count()


def user_ids_missing(extra_key: str, limit: int = 500) -> List[int]:
    """User ids whose ``profiles.extra`` has no *extra_key*. For backfills.

    ``NOT (extra ? key)`` is the JSONB key-existence operator, so the filter runs
    in the database rather than by loading every document into Python -- which
    matters because the only caller is a sweep over accounts that have not been
    backfilled yet, and that set starts as "all of them".

    Unindexable as written: `extra` has no GIN index, so this is a sequential
    scan of `profiles`. That is the right trade for a bounded maintenance sweep
    and would not be for anything on a request path. Nothing on a request path
    may call this.

    Ordered by ``user_id`` and bounded by *limit*, so repeated runs make
    progress in a stable order instead of re-reading the same page.
    """
    rows = db.session.execute(
        sa.select(Profile.user_id)
        .where(~Profile.extra.has_key(extra_key))  # noqa: W601 -- JSONB `?`, not dict
        .order_by(Profile.user_id)
        .limit(limit)
    )
    return [row[0] for row in rows]


def has_intake_submission(email: str) -> bool:
    """Whether a pre-launch intake submission exists for this address.

    Case-insensitive, through ``IntakeSubmission.email_key`` -- the expression
    the account export and deletion and the retention sweep compare, and the one
    ``ix_intake_submissions_email_lower`` indexes.  ``IntakeSubmission.email`` is
    stored as submitted, so the case-sensitive comparison this used until the DB
    ledger's wave 3 read an address that differed only in case as absent, and
    could use no index.  Both writers lower-case the address today, so the
    change reaches only rows filed before they did.

    An ``EXISTS`` probe: the answer is one boolean, so no row is loaded to
    produce it.
    """
    return bool(
        db.session.execute(
            sa.select(
                sa.exists().where(IntakeSubmission.email_key == sa.func.lower(email))
            )
        ).scalar()
    )
