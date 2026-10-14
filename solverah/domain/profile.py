"""Pure profile computations: merge rules, quiz summaries, completion scoring.

Everything here is a function of its arguments.  The profile *blob* is passed in
and a new blob comes back -- nothing reads the session, the request, or the
database, which is what makes the merge semantics testable without a user.

The merge is a shallow ``{**existing, **incoming}`` with two special cases, and
it is worth being explicit that this is P0-1 in docs/ARCHITECTURE.md, not a
design: two concurrent writers both read the blob, both merge, and the second
commit silently discards the first.  There is no optimistic lock to take.
Phase 2 decomposes the blob into columns; until then the semantics are preserved
exactly, because changing them would change which of two racing writes wins.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "CAREER_STATUSES",
    "PATH_INPUT_KEYS",
    "PROFILE_COMPLETION_FIELDS",
    "PROFICIENCY_LEVELS",
    "TRACKED_RESUME_FIELDS",
    "apply_skill_levels",
    "compute_quiz_stats",
    "merge_profile",
    "merge_resume_parse",
    "profile_completion_percent",
    "resume_field_corrections",
    "validate_career_status",
    "validate_skill_ratings",
]

#: Career statuses the API accepts.
CAREER_STATUSES = {"employed", "between_jobs", "first_job"}

#: Self-rated proficiency levels.
PROFICIENCY_LEVELS = {"beginner", "intermediate", "advanced"}

#: Fields diffed against the parser snapshot to build ResumeParseCorrection rows.
TRACKED_RESUME_FIELDS = ("experience", "education", "skills")

#: Fields counted toward the dashboard's completion percentage.
PROFILE_COMPLETION_FIELDS = (
    "firstName",
    "lastName",
    "email",
    "summary",
    "skills",
    "experience",
    "education",
)

#: Profile keys whose change invalidates cached path suggestions.
PATH_INPUT_KEYS = {"experience", "skills", "skill_levels"}


def compute_quiz_stats(answers: Any) -> Dict[str, Any]:
    """Summarise one quiz's answers as counts, mean index, and sample size.

    Walks arbitrarily nested dicts and lists and treats every ``int`` it finds as
    a selected option index.  Booleans are ``int`` subclasses in Python and are
    therefore counted -- preserved from the original, because a stored boolean
    answer contributes ``0``/``1`` to the mean today and excluding it would
    change every historical summary.
    """
    counts: Dict[str, int] = {}
    total = 0
    n = 0

    def walk(value: Any) -> None:
        nonlocal total, n
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, int):
            counts[str(value)] = counts.get(str(value), 0) + 1
            total += value
            n += 1

    walk(answers)
    avg = (total / n) if n > 0 else None
    return {"counts": counts, "avgIndex": avg, "n": n}


def merge_profile(existing: Optional[dict], incoming: dict) -> Dict[str, Any]:
    """Merge *incoming* profile keys over *existing*, with the two special cases.

    1. ``quizResults`` merges at the sub-key level, so submitting one quiz does
       not erase the others.
    2. When ``quizResults`` changed, ``_quizSummary`` is recomputed for every
       quiz -- not only the incoming one, since the summary is a single document.
    3. Adding a skill clears ``skills_proficiency_confirmed`` so the rating modal
       re-prompts.  Removing one does not: the user has already rated what is
       left.

    Returns:
        A new dict.  Neither argument is mutated, which matters because the
        caller still holds ``existing`` as the pre-write state for diffing.
    """
    existing = existing or {}
    merged: Dict[str, Any] = {**existing, **incoming}

    incoming_quiz = incoming.get("quizResults")
    existing_quiz = existing.get("quizResults") if isinstance(existing, dict) else None

    if incoming_quiz:
        merged_quiz: Dict[str, Any] = {}
        if existing_quiz and isinstance(existing_quiz, dict):
            merged_quiz.update(existing_quiz)
        # overwrite/insert incoming quiz entries
        merged_quiz.update(incoming_quiz if isinstance(incoming_quiz, dict) else {})
        merged["quizResults"] = merged_quiz

        summary = {}
        for quiz_key, quiz_value in merged.get("quizResults", {}).items():
            try:
                summary[quiz_key] = compute_quiz_stats(quiz_value)
            except Exception:  # noqa: BLE001 -- a malformed quiz must not fail the save
                summary[quiz_key] = {"counts": {}, "avgIndex": None, "n": 0}

        merged["_quizSummary"] = summary

    # Reset proficiency confirmation when skills list actually changes so the
    # modal re-prompts the user to rate their new skills.
    if "skills" in incoming:
        new_skills = set(incoming.get("skills") or [])
        old_skills = set(existing.get("skills") or [])
        if new_skills - old_skills:
            merged["skills_proficiency_confirmed"] = False

    return merged


def merge_resume_parse(
    existing: Optional[dict], updates: dict, snapshot: dict
) -> Dict[str, Any]:
    """Merge a resume parse over *existing* without letting an empty section win.

    A parsed section (``experience``, ``education``, ``skills``) that came back
    empty leaves the stored section exactly as it was. Before 2026-10-02 the
    parse was a plain ``{**existing, **updates}``, so a resume the parser found
    nothing in wiped all three and the job still said ``succeeded`` (audit item
    1). A NON-empty section still replaces the stored one wholesale: whether it
    should merge instead is an open product decision, not this function's.

    Every other key in *updates* (``uploadedResume``, ``resumeKey``) is taken
    as sent, and *snapshot* is recorded as ``_parsedResumeSnapshot``.
    """
    merged: Dict[str, Any] = dict(existing or {})
    for key, value in updates.items():
        if key in TRACKED_RESUME_FIELDS and not value:
            continue
        merged[key] = value
    merged["_parsedResumeSnapshot"] = snapshot
    return merged


def validate_career_status(profile_data: dict) -> Optional[str]:
    """``"invalid_status"`` when *profile_data* carries an unknown career status.

    Only a key that is present is checked: a partial profile without
    ``career_status`` leaves the stored one alone. ``None`` is not a status
    either -- ``PATCH /me/career-status`` has never accepted it, and the
    profile PATCH accepting it would be a second, weaker door to the same
    column (audit 2026-10-02, item 13).
    """
    if "career_status" in profile_data and profile_data["career_status"] not in CAREER_STATUSES:
        return "invalid_status"
    return None


def resume_field_corrections(
    existing: Optional[dict], incoming: dict
) -> Tuple[Optional[str], List[Tuple[str, Any, Any]]]:
    """Find edits the user made to parser output.

    Diffs ``experience``/``education``/``skills`` in *incoming* against the
    ``_parsedResumeSnapshot`` stored in *existing*.  Each difference becomes a
    ``ResumeParseCorrection`` row -- training data for improving the parser.

    Returns:
        ``(resume_key, [(field, parsed_value, corrected_value), ...])``.  The key
        is None when there is no snapshot to diff against, in which case the list
        is empty.
    """
    existing = existing or {}
    snapshot = existing.get("_parsedResumeSnapshot")
    if not snapshot or not isinstance(snapshot, dict):
        return None, []

    resume_key = snapshot.get("resumeKey")
    if not resume_key:
        return None, []

    corrections = []
    for field in TRACKED_RESUME_FIELDS:
        if field not in incoming:
            continue
        new_value = incoming[field]
        parsed_value = snapshot.get(field)
        if new_value != parsed_value:
            corrections.append((field, parsed_value, new_value))
    return resume_key, corrections


def validate_skill_ratings(skills: Any) -> Optional[str]:
    """Validate a bulk proficiency payload.

    Returns:
        None when valid, otherwise the error code the API should return --
        ``"invalid_body"`` for a structural problem, ``"invalid_proficiency"``
        for an unrecognised level.
    """
    if not isinstance(skills, list):
        return "invalid_body"
    for item in skills:
        if not isinstance(item, dict) or "name" not in item:
            return "invalid_body"
        if item.get("proficiency") not in PROFICIENCY_LEVELS:
            return "invalid_proficiency"
    return None


def apply_skill_levels(
    profile: Optional[dict], skills: Sequence[dict]
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Write proficiency ratings into a copy of *profile*.

    Returns:
        ``(new_profile, skill_levels)``.  Ratings are merged over any existing
        ones rather than replacing the dict, so rating three skills does not
        erase the other twenty.
    """
    new_profile = dict(profile or {})
    skill_levels = dict(new_profile.get("skill_levels") or {})
    for item in skills:
        skill_levels[item["name"]] = item["proficiency"]
    new_profile["skill_levels"] = skill_levels
    new_profile["skills_proficiency_confirmed"] = True
    return new_profile, skill_levels


def profile_completion_percent(
    profile: Optional[dict], fields: Iterable[str] = PROFILE_COMPLETION_FIELDS
) -> int:
    """Percentage of *fields* present and truthy in *profile*.

    Truthiness, not presence: an empty ``skills`` list reads as not filled in,
    which is what the dashboard means to show.
    """
    profile = profile or {}
    fields = tuple(fields)
    if not fields:
        return 0
    filled = sum(1 for field in fields if profile.get(field))
    return int((filled / len(fields)) * 100)
