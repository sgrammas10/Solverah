"""The blob-shaped profile document, decomposed into rows and put back together.

Phase 2a is a *storage* change.  ``GET /me/profile`` served the ``profile_data``
JSON column verbatim; it now serves this module's :func:`assemble` output, and
the two must be indistinguishable.  Everything here is pure -- dicts in, plain
dataclasses out -- so the round-trip can be tested without a database, which is
the only reason it can be tested exhaustively at all.

The invariant
-------------

    assemble(decompose(document)) == document

for **every** document, not merely the well-formed ones.  A profile with
``{"experience": "oops"}`` in it is not a profile the UI can render, but it is a
profile that exists in the database, and a migration that quietly repairs it is
a migration that changed data it was not asked to change.

How that invariant is kept
--------------------------

One rule, applied everywhere:

    A key is promoted to a column only when its value fits that column exactly.
    Anything else rides in ``extra`` verbatim.  A NULL column means the key was
    absent; a key in ``extra`` means it was present with that value.

So ``"phone": ""`` promotes (``""`` is a string) and comes back as ``""``.
``"phone": null`` does not promote, rides in ``extra``, and comes back as
``null``.  A missing ``phone`` leaves the column NULL and the key absent.  The
three states stay three states, which a nullable column alone cannot do.

Lists follow the same rule at list level rather than entry level: if any entry
of ``experience`` is not decomposable, the whole key rides in ``extra``.  Partial
decomposition would mean one profile's experience lived half in rows and half in
a blob, and the assembled order of the two halves would be a coin toss.

An empty list has no rows to be stored as, so ``"experience": []`` also rides in
``extra``.  That is not a special case in the code -- an empty list produces zero
rows, and zero rows is indistinguishable from "the key was absent", so the key
has to be recorded somewhere.

What is deliberately *not* promoted
-----------------------------------

``profiles`` declares ``headline``, ``location_state``, ``location_city`` and
``portfolio_url``, and this module leaves all four NULL.  Nothing in today's
document maps onto them: there is no headline and no portfolio URL at all, and
``location``/``primaryLocation`` are one free-text field that may hold a state,
a city, or "Austin, TX".  Splitting it would require guessing, and a guess
written into a column is indistinguishable from a fact once it is there.  Part
4.3's own model covers this -- "anything not yet promoted rides in ``extra``,
and each promotion is a follow-up migration" -- and the follow-up here is gated
on the frontend collecting city and state separately.

``skill_levels`` *is* promoted, onto ``profile_skills.proficiency``.  The blob's
three levels map onto the 1-5 scale as 1/3/5, and ``validate_skill_ratings``
plus ``clean_profile_data`` between them guarantee no fourth value has ever been
stored, so the mapping is total in both directions.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from solverah.domain.profile import profile_completion_percent
from solverah.domain.skills import slugify

__all__ = [
    "CURRENT_ROLE_MARKERS",
    "EducationRow",
    "ExperienceRow",
    "PROFICIENCY_BY_SCORE",
    "PROFICIENCY_SCORES",
    "ProfileState",
    "ResumeRecord",
    "SkillRow",
    "assemble",
    "decompose",
]

#: ``endDate`` values meaning the user still holds the role. Same pair
#: ``intelligence_service.derive_career_status`` matches on, and for the same
#: reason -- the blob has no "current" flag, only this convention.
CURRENT_ROLE_MARKERS = ("present", "current")

#: ``skill_levels`` value -> ``profile_skills.proficiency``. Spread across the
#: 1-5 scale rather than packed into 1-3 so a future five-point rating widget
#: does not have to renumber the rows that already exist.
PROFICIENCY_SCORES = {"beginner": 1, "intermediate": 3, "advanced": 5}

#: The inverse. Injective, so the round-trip is exact.
PROFICIENCY_BY_SCORE = {score: level for level, score in PROFICIENCY_SCORES.items()}

#: ``profiles`` columns that take a top-level string key straight across.
#: ``(document key, column name)``.
SCALAR_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("summary", "summary"),
    ("phone", "phone"),
    ("linkedinUrl", "linkedin_url"),
    ("career_status", "career_status"),
)

#: Columns that exist in the table and have no source in today's document.
#: Listed so the omission is a decision with a name rather than four columns
#: nobody noticed were empty. See the module docstring.
UNPROMOTED_COLUMNS = ("headline", "location_state", "location_city", "portfolio_url")


# ---------------------------------------------------------------------------
# Row shapes -- plain data, no ORM, no database types beyond `date`
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExperienceRow:
    """One ``profile_experiences`` row."""

    company_name: str
    title: str
    ordinal: int
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    is_current: bool = False
    description: Optional[str] = None
    source: str = "user"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EducationRow:
    """One ``profile_educations`` row."""

    institution: str
    ordinal: int
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    source: str = "user"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillRow:
    """One ``profile_skills`` row, plus the ``skills`` row it points at.

    ``label`` is what the user actually typed, and it is stored per-user rather
    than only on the shared ``skills`` row because the shared row can hold one
    spelling and two users can type two. Reassembling a list from the canonical
    label would hand the second user the first user's capitalisation.

    ``ordinal`` is the position in the document's ``skills`` array, or None for
    a row that exists only because ``skill_levels`` rated a skill absent from
    that array -- rated-but-not-listed is a state the blob can represent, so it
    is a state the rows have to represent.
    """

    slug: str
    label: str
    ordinal: Optional[int] = None
    proficiency: Optional[int] = None
    source: str = "user"


@dataclass(frozen=True)
class ResumeRecord:
    """The current ``resumes`` row.

    One row per user, not a history. The blob holds exactly one ``resumeKey``,
    and ``retention_cleanup`` sweeps object-storage keys no row references --
    so keeping superseded resumes here would silently stop old uploads from
    ever being deleted, which is a retention change disguised as a schema
    change.
    """

    object_key: str
    mime: Optional[str] = None
    size_bytes: int = 0
    status: str = "stored"


@dataclass(frozen=True)
class ProfileState:
    """Everything the profile tables hold for one user."""

    scalars: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)
    experiences: List[ExperienceRow] = field(default_factory=list)
    educations: List[EducationRow] = field(default_factory=list)
    skills: List[SkillRow] = field(default_factory=list)
    resume: Optional[ResumeRecord] = None
    completeness: int = 0


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _as_date(value: Any) -> Optional[datetime.date]:
    """*value* as a ``date``, but only when it round-trips to itself.

    ``date.fromisoformat`` accepts more spellings on newer Pythons than it did
    on 3.10 (``"20200115"`` among them), and a spelling that parses but does not
    re-emit character-for-character would come back changed. Requiring equality
    with ``isoformat()`` makes the promotion safe on every version rather than
    on the one this was written against.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _is_current(end_date: Any) -> bool:
    """Whether an ``endDate`` says the role is still held."""
    return str(end_date or "").strip().lower() in CURRENT_ROLE_MARKERS


def _split_entry(
    entry: Dict[str, Any], mapping: Sequence[Tuple[str, str]]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Partition *entry* into promoted column values and the leftover ``extra``.

    ``mapping`` is ``(document key, kind)`` where kind is ``"text"`` or
    ``"date"``. A value that does not fit its kind is left in ``extra``, so the
    column stays NULL and the key still comes back with the value it had.
    """
    promoted: Dict[str, Any] = {}
    leftover = dict(entry)

    for key, kind in mapping:
        if key not in leftover:
            continue
        value = leftover[key]
        if kind == "text":
            if isinstance(value, str):
                promoted[key] = value
                del leftover[key]
        elif kind == "date":
            parsed = _as_date(value)
            if parsed is not None:
                promoted[key] = parsed
                del leftover[key]

    return promoted, leftover


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------

#: ``profile_experiences`` columns fed from an entry, and what each accepts.
_EXPERIENCE_MAPPING = (
    ("company", "text"),
    ("position", "text"),
    ("description", "text"),
    ("startDate", "date"),
    ("endDate", "date"),
)


def _decompose_experiences(value: Any) -> Optional[List[ExperienceRow]]:
    """Rows for an ``experience`` array, or None when it does not decompose.

    None means "leave the key in ``extra``". It is returned for an empty list, a
    non-list, an entry that is not a dict, and an entry missing ``company`` or
    ``position`` as strings -- those two are NOT NULL columns, and inventing an
    empty string for an absent key would add a key on the way back out.
    """
    if not isinstance(value, list) or not value:
        return None

    rows: List[ExperienceRow] = []
    for ordinal, entry in enumerate(value):
        if not isinstance(entry, dict):
            return None
        if not isinstance(entry.get("company"), str):
            return None
        if not isinstance(entry.get("position"), str):
            return None

        promoted, leftover = _split_entry(entry, _EXPERIENCE_MAPPING)
        rows.append(
            ExperienceRow(
                company_name=promoted["company"],
                title=promoted["position"],
                ordinal=ordinal,
                start_date=promoted.get("startDate"),
                end_date=promoted.get("endDate"),
                # Derived, never read back into the document: the document's own
                # ``endDate`` is what round-trips, whether it promoted to the
                # date column or stayed in `extra` as the word "Present".
                is_current=_is_current(entry.get("endDate")),
                description=promoted.get("description"),
                extra=leftover,
            )
        )
    return rows


def _assemble_experience(row: ExperienceRow) -> Dict[str, Any]:
    entry = dict(row.extra)
    entry["company"] = row.company_name
    entry["position"] = row.title
    if row.description is not None:
        entry["description"] = row.description
    if row.start_date is not None:
        entry["startDate"] = row.start_date.isoformat()
    if row.end_date is not None:
        entry["endDate"] = row.end_date.isoformat()
    return entry


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------

_EDUCATION_MAPPING = (
    ("institution", "text"),
    ("degree", "text"),
    ("field", "text"),
    ("startDate", "date"),
    ("endDate", "date"),
)


def _decompose_educations(value: Any) -> Optional[List[EducationRow]]:
    """Rows for an ``education`` array, or None to leave it in ``extra``.

    Only ``institution`` is required, because only ``institution`` is NOT NULL.
    The parser's fallback path emits entries with an empty institution and the
    whole line in ``degree``; those decompose, which is the point -- they are the
    common case for a resume the structured parser could not read.
    """
    if not isinstance(value, list) or not value:
        return None

    rows: List[EducationRow] = []
    for ordinal, entry in enumerate(value):
        if not isinstance(entry, dict):
            return None
        if not isinstance(entry.get("institution"), str):
            return None

        promoted, leftover = _split_entry(entry, _EDUCATION_MAPPING)
        rows.append(
            EducationRow(
                institution=promoted["institution"],
                ordinal=ordinal,
                degree=promoted.get("degree"),
                field_of_study=promoted.get("field"),
                start_date=promoted.get("startDate"),
                end_date=promoted.get("endDate"),
                extra=leftover,
            )
        )
    return rows


def _assemble_education(row: EducationRow) -> Dict[str, Any]:
    entry = dict(row.extra)
    entry["institution"] = row.institution
    if row.degree is not None:
        entry["degree"] = row.degree
    if row.field_of_study is not None:
        entry["field"] = row.field_of_study
    if row.start_date is not None:
        entry["startDate"] = row.start_date.isoformat()
    if row.end_date is not None:
        entry["endDate"] = row.end_date.isoformat()
    return entry


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


def _decompose_skills(
    skills_value: Any, levels_value: Any
) -> Tuple[List[SkillRow], bool, bool]:
    """Rows for ``skills`` and ``skill_levels``, and whether each promoted.

    The two keys share one table but promote independently, so either can fall
    back to ``extra`` without dragging the other with it. What they cannot do is
    disagree: a ``skill_levels`` key that slugs onto a listed skill but is spelt
    differently would need the row to hold two raw labels, so in that case the
    ratings stay in ``extra`` and the list still promotes.

    Returns:
        ``(rows, skills_promoted, levels_promoted)``.
    """
    rows: List[SkillRow] = []
    by_slug: Dict[str, int] = {}
    skills_promoted = False

    if isinstance(skills_value, list) and skills_value:
        listed: List[SkillRow] = []
        for ordinal, label in enumerate(skills_value):
            slug = slugify(label)
            if slug is None or slug in by_slug:
                # Unslugifiable, or two entries that are the same skill: one
                # (user_id, skill_id) row cannot hold both, and dropping one
                # would lose a skill.
                listed = []
                by_slug = {}
                break
            by_slug[slug] = ordinal
            listed.append(SkillRow(slug=slug, label=label, ordinal=ordinal))
        if listed:
            rows = listed
            skills_promoted = True

    levels_promoted = False
    if isinstance(levels_value, dict) and levels_value:
        rated: Dict[str, int] = {}
        extra_rows: List[SkillRow] = []
        ok = True
        for name, level in levels_value.items():
            slug = slugify(name)
            if slug is None or level not in PROFICIENCY_SCORES or slug in rated:
                ok = False
                break
            if slug in by_slug:
                if rows[by_slug[slug]].label != name:
                    # Same skill, different spelling from the listed one.
                    ok = False
                    break
                rated[slug] = PROFICIENCY_SCORES[level]
            else:
                rated[slug] = PROFICIENCY_SCORES[level]
                extra_rows.append(
                    SkillRow(
                        slug=slug,
                        label=name,
                        ordinal=None,
                        proficiency=PROFICIENCY_SCORES[level],
                    )
                )
        if ok:
            levels_promoted = True
            rows = [
                SkillRow(
                    slug=row.slug,
                    label=row.label,
                    ordinal=row.ordinal,
                    proficiency=rated.get(row.slug),
                )
                for row in rows
            ] + extra_rows

    return rows, skills_promoted, levels_promoted


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def _decompose_resume(document: Dict[str, Any]) -> Optional[ResumeRecord]:
    """The ``resumes`` row for this document, or None when no resume is on file.

    ``uploadedResume`` stays in ``extra`` -- it carries the original filename,
    which has no column -- and its ``type``/``size`` are *copied* here so the
    queryable row is complete. The copy cannot drift: every write rewrites the
    whole profile state from the document, so the two are re-derived together or
    not at all.
    """
    object_key = document.get("resumeKey")
    if not isinstance(object_key, str) or not object_key:
        return None

    uploaded = document.get("uploadedResume")
    uploaded = uploaded if isinstance(uploaded, dict) else {}

    mime = uploaded.get("type")
    size = uploaded.get("size")
    snapshot = document.get("_parsedResumeSnapshot")
    parsed = isinstance(snapshot, dict) and snapshot.get("resumeKey") == object_key

    return ResumeRecord(
        object_key=object_key,
        mime=mime if isinstance(mime, str) and mime else None,
        # 0 means "not recorded". `bool` is an `int` subclass and a `True` size
        # would store as 1, so it is excluded explicitly.
        size_bytes=size if isinstance(size, int) and not isinstance(size, bool) else 0,
        status="parsed" if parsed else "stored",
    )


# ---------------------------------------------------------------------------
# The two public functions
# ---------------------------------------------------------------------------


def decompose(document: Optional[Dict[str, Any]]) -> ProfileState:
    """Split a profile document into the rows that store it.

    Every key of *document* ends up in exactly one place: a column, a child
    table, or ``extra``. Nothing is dropped and nothing is rewritten.
    """
    document = document or {}
    extra = dict(document)
    scalars: Dict[str, Any] = {column: None for column in UNPROMOTED_COLUMNS}

    for key, column in SCALAR_COLUMNS:
        value = extra.get(key)
        if key in extra and isinstance(value, str):
            scalars[column] = value
            del extra[key]
        else:
            scalars[column] = None

    experiences = _decompose_experiences(document.get("experience"))
    if experiences is not None:
        del extra["experience"]
    else:
        experiences = []

    educations = _decompose_educations(document.get("education"))
    if educations is not None:
        del extra["education"]
    else:
        educations = []

    skills, skills_promoted, levels_promoted = _decompose_skills(
        document.get("skills"), document.get("skill_levels")
    )
    if skills_promoted:
        del extra["skills"]
    if levels_promoted:
        del extra["skill_levels"]

    resume = _decompose_resume(document)
    if resume is not None:
        del extra["resumeKey"]

    return ProfileState(
        scalars=scalars,
        extra=extra,
        experiences=experiences,
        educations=educations,
        skills=skills,
        resume=resume,
        completeness=profile_completion_percent(document),
    )


def assemble(state: ProfileState) -> Dict[str, Any]:
    """Rebuild the profile document from the rows that store it.

    ``extra`` goes down first and promoted values go over the top, which is the
    ordering that makes lazy promotion safe: a profile carried into ``extra`` by
    the migration and never rewritten assembles from ``extra`` alone, and the
    same profile after one write assembles from its columns. Both give the same
    document, so a user cannot tell which state their row is in.
    """
    document: Dict[str, Any] = dict(state.extra)

    for key, column in SCALAR_COLUMNS:
        value = state.scalars.get(column)
        if value is not None:
            document[key] = value

    if state.experiences:
        document["experience"] = [
            _assemble_experience(row)
            for row in sorted(state.experiences, key=lambda r: r.ordinal)
        ]

    if state.educations:
        document["education"] = [
            _assemble_education(row)
            for row in sorted(state.educations, key=lambda r: r.ordinal)
        ]

    listed = sorted(
        (row for row in state.skills if row.ordinal is not None),
        key=lambda r: r.ordinal,
    )
    if listed:
        document["skills"] = [row.label for row in listed]

    rated = [row for row in state.skills if row.proficiency is not None]
    if rated:
        document["skill_levels"] = {
            row.label: PROFICIENCY_BY_SCORE[row.proficiency] for row in rated
        }

    if state.resume is not None:
        document["resumeKey"] = state.resume.object_key

    return document
