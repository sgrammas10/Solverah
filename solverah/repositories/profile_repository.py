"""Queries against the profile tables.

Phase 2a moved the profile out of ``users.profile_data`` and into ``profiles``,
``profile_experiences``, ``profile_educations``, ``skills``, ``profile_skills``
and ``resumes``.  Nothing outside this module knows that.  Callers ask for a
*document* -- the same dict shape ``profile_data`` held -- and get one back; the
mapping between that document and the rows lives in
:mod:`solverah.domain.profile_document`, which is pure and therefore testable
without a database.

Two things in here are load-bearing.

**Every write goes through :func:`update_document`.**  There is no setter and no
way to assign a document, because a caller holding a document it read a moment
ago is exactly the read-modify-write that made P0-1 a lost update.  The mutate
callback is re-run against a fresh read whenever another writer got there first.

**Reads and writes use Core statements, not ORM instances.**  A retry has to see
what the other writer committed, and an ORM instance in the identity map does
not go and look.  Core `select()` always does.

The queries here are deliberately plain.  ``load_document`` is seven round trips
where the blob was zero, because the blob rode along on the user row that was
already loaded.  Five of those are Phase 2a's decomposition; the other two are
Phase 2d fetching the FocusType and ManagerMatch results, which were blob keys
and are now rows.  The whole cost is paid on ``GET /me/profile``, not on the boot
path -- ``GET /auth/session`` never touches this module.  Phase 3's cache is
where it gets paid back.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import sqlalchemy as sa
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
    "ConcurrentProfileUpdate",
    "count_job_recommendations",
    "current_resume",
    "find_correction",
    "has_intake_submission",
    "load_document",
    "record_resume_corrections",
    "referenced_resume_keys",
    "update_document",
    "user_ids_missing",
]

#: How many times a losing writer re-reads and re-applies before giving up.
#:
#: Contention is naturally serialised: the conditional UPDATE takes a row lock,
#: so a second writer blocks until the first commits and then finds its version
#: stale on the first attempt rather than spinning. Five is a backstop against a
#: pathological pile-up, not a tuning parameter.
MAX_WRITE_ATTEMPTS = 5


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


def load_document(user_id: int) -> Dict[str, Any]:
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
    dropped two keys off the wire would not be a storage change.

    Merged after :func:`assemble` rather than inside it, and merged
    unconditionally, so the row is the only source: a stale copy left behind in
    ``extra`` cannot shadow it. (The migration removes those copies; this
    ordering is what makes a missed one harmless rather than silently
    authoritative.) Neither key is client-writable -- ``clean_profile_data``'s
    allowlist has never included them -- so nothing can put one back.
    """
    state, _version = _read_state(user_id)
    document = document_domain.assemble(state)

    for kind, key in document_domain.ASSESSMENT_RESULT_KEYS.items():
        submission = assessment_repository.current_submission(user_id, kind)
        result = submission.result if submission is not None else None
        if result is None:
            document.pop(key, None)
        else:
            document[key] = result

    return document


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

    for (extra,) in db.session.execute(sa.select(Profile.extra)):
        if not isinstance(extra, dict):
            continue
        # A profile carried over by the migration and never rewritten still has
        # its resumeKey in `extra` rather than in a `resumes` row.
        if extra.get("resumeKey"):
            keys.add(extra["resumeKey"])
        snapshot = extra.get("_parsedResumeSnapshot")
        if isinstance(snapshot, dict) and snapshot.get("resumeKey"):
            keys.add(snapshot["resumeKey"])

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
            "UPDATE skills SET aliases = aliases || ARRAY[:label]::text[] "
            "WHERE slug = :slug AND label <> :label "
            "AND NOT (:label = ANY(aliases))"
        ),
        [{"slug": slug, "label": label} for slug, label in by_slug.items()],
    )

    return {
        slug: skill_id
        for skill_id, slug in db.session.execute(
            sa.select(Skill.id, Skill.slug).where(Skill.slug.in_(by_slug))
        )
    }


def _write_children(user_id: int, state: ProfileState) -> None:
    """Replace this user's experience, education, skill and resume rows.

    Delete-then-insert rather than a diff. The document has no stable identity
    per entry -- the frontend's list ``id`` is a timestamp for a new row and an
    array index for a parsed one -- so there is nothing to diff against, and a
    profile save has always been a wholesale replacement of these lists.

    The consequence, stated so it is not discovered later: ``public_id`` on an
    experience or education row is **not** a stable handle. It becomes one when
    Part 5.2's ``/me/experiences`` lands and an entry is addressed and edited
    individually instead of arriving inside a whole document.

    Safe under concurrency only because the caller has already won the
    compare-and-swap on ``profiles.version``, which holds a row lock for the rest
    of the transaction.
    """
    db.session.execute(
        sa.delete(ProfileExperience).where(ProfileExperience.user_id == user_id)
    )
    if state.experiences:
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
                for row in state.experiences
            ],
        )

    db.session.execute(
        sa.delete(ProfileEducation).where(ProfileEducation.user_id == user_id)
    )
    if state.educations:
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
                for row in state.educations
            ],
        )

    db.session.execute(
        sa.delete(ProfileSkill).where(ProfileSkill.user_id == user_id)
    )
    if state.skills:
        skill_ids = _skill_ids(state.skills)
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
                for row in state.skills
            ],
        )

    _write_resume(user_id, state.resume)


def _write_resume(user_id: int, resume: Optional[ResumeRecord]) -> None:
    """Bring ``resumes`` in line with the document's ``resumeKey``.

    Rows for keys the profile no longer names are deleted rather than kept, so
    the retention sweep can still reclaim a superseded upload. See the docstring
    on :class:`model.Resume`.
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

        _write_children(user_id, new_state)
        # The dashboard reads this document, so every successful swap retires its
        # cached payload (Phase 3). Registered here, in the one write path Phase
        # 2a left, rather than at each of the dozen callers -- an invalidation a
        # caller can forget is one that will be forgotten, and the symptom is a
        # stale number nobody reports. Dropped after the caller's commit, never
        # before: see solverah/infra/cache.py.
        cache.invalidate_on_commit(cache.dashboard_key(user_id))
        return new_document

    raise ConcurrentProfileUpdate(
        "gave up writing the profile for user %s after %d attempts"
        % (user_id, MAX_WRITE_ATTEMPTS)
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
    """Upsert one ``ResumeParseCorrection`` per changed field.

    Args:
        corrections: ``(field, parsed_value, corrected_value)`` triples, as
            produced by :func:`solverah.domain.profile.resume_field_corrections`.

    Returns:
        How many rows were written or updated.

    Note:
        ``parsed_value`` is only set on insert.  On a second edit of the same
        field the original parser output is preserved and only the corrected
        value moves -- otherwise the row would end up comparing the user's first
        edit to their second, and the parser signal would be lost.
    """
    written = 0
    for field, parsed_value, corrected_value in corrections:
        existing = find_correction(user_id, resume_key, field)
        if existing:
            existing.corrected_value = corrected_value
            existing.updated_at = datetime.datetime.utcnow()
        else:
            db.session.add(
                ResumeParseCorrection(
                    user_id=user_id,
                    resume_key=resume_key,
                    field=field,
                    parsed_value=parsed_value,
                    corrected_value=corrected_value,
                )
            )
        written += 1
    return written


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

    Case-sensitive, matching the original query.  ``IntakeSubmission.email`` is
    stored as submitted, so an address that differs only in case reads as absent
    -- a real bug, fixed by Phase 2's ``citext`` columns rather than by changing
    the comparison here, since changing it would alter which dashboards show the
    intake banner.
    """
    return IntakeSubmission.query.filter_by(email=email).first() is not None
