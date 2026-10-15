"""
assessment_store.py -- persistence for a scored person-side submission.

Split from assessment_form.py deliberately: that module is the instrument's doorway and has
no Flask or SQLAlchemy import, so it stays testable without an app context and cannot grow a
dependency on the product schema. This module is the only place the two meet.

WHAT IS STORED, AND WHY BOTH
----------------------------
Raw responses AND derived scores, always together, in one transaction.

The raw rows are the ones that matter long term. A score is a function of (choices, item
file, scoring method); two of those three change over time. schema.sql's own comment is
"keep them so scores can be RE-derived when the scoring key changes -- never overwrite raw
responses." Storing only scores would make every historical profile un-recomputable the
first time the ladder is revised, which is precisely the position the v1 -> v2 item change
would have put us in.

RETAKE SEMANTICS
----------------
Retakes are live since 2026-10-02 (Sebastian's ruling: retakeable, no cooldown for now; the
switch is `assessment_service.CORE_RETAKE_COOLDOWN`). Before that date the UI offered no way
to start a second sitting, though everything below already held.

Raw responses are append-only: a retake writes 24 new rows under a new submission_id, and
the old sitting stays readable forever. Derived scores are unique per
(user, dimension, scoring_key_version), so a retake under the same key version UPDATES the
score row in place and records which submission it now comes from.

That asymmetry is intentional. There is exactly one current score per person per dimension
per scoring key -- anything else means every consumer has to decide which row is live, and
they will not all decide the same way. The history is not lost; it is in the raw rows.

THE SUBMISSION ROW (Phase 2d)
-----------------------------
A sitting is now also one row in `assessment_submissions`, the table all five assessment
products share. It is written here rather than by `assessment_repository` for the same
reason everything else on this path is: the row and the raw responses it identifies must
land in one transaction, and the doorway is where that boundary lives.

The row is deliberately empty of content. `result` and `answers` are null for `core` -- a
check constraint, not a convention -- so nothing that reads the shared table learns an
individual's answers or dimension scores. That is what "unify the storage without widening
D-01" means concretely: the *record that a sitting happened* is shared, and everything the
sitting contains stays behind this module.

`submission_id` on the two person-side tables is unchanged in type and shape: 32 lowercase
hex characters. It is now `assessment_submissions.public_id.hex` rather than a free-standing
`uuid4()`, which makes it a join key to the shared table instead of an id that happened to
be unique. Both are UUIDs and `.hex` is 32 characters either way, so nothing on the wire
moved -- `Scripts/capture_contract.py` masks it with a pattern that only matches that shape,
so a change of format would show up as a diff rather than be hidden by the mask.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime

from assessment_form import ScoredSubmission
from solverah.domain.trait_preferences import TraitPreference

__all__ = [
    "completed_core_sittings",
    "dimension_scores_for_submission",
    "export_person_side",
    "first_completed_core_submission_id",
    "first_trait_preferences_after",
    "get_dimension_confidences",
    "get_dimension_scores",
    "get_trait_preferences",
    "has_completed_assessment",
    "latest_completed_core_submission_id",
    "latest_core_completed_at",
    "persist_submission",
    "respondent_id_for_user",
    "save_trait_preferences",
    "TraitPreference",
]


def respondent_id_for_user(user_id: int, secret: bytes | None = None) -> str:
    """A stable, opaque per-user id to seed the shuffle and salt the item tokens.

    Not `user.id` directly. `build_form` echoes respondent_id back in the payload, so a raw
    database id would be published to the client -- a sequential public counter, which is
    exactly what present_items' DECISION 3 rules out. HMAC of the id under the form secret is
    stable across sessions (so a resumed form does not reshuffle), opaque, and not guessable
    from another user's value.

    Derived rather than stored: a stored column would be a second source of truth that can
    drift, and this is reproducible from (user_id, secret) forever.
    """
    if secret is None:
        env = os.environ.get("SOLVERAH_FORM_TOKEN_SECRET")
        if not env:
            raise RuntimeError(
                "SOLVERAH_FORM_TOKEN_SECRET is not set. Deliberately no default (D-05)."
            )
        secret = env.encode("utf-8")
    return hmac.new(
        secret, f"respondent\x00{user_id}".encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]


def persist_submission(db, user_id: int, result: ScoredSubmission) -> str:
    """Write one sitting's raw responses and its six derived scores. Returns submission_id.

    Does NOT commit -- the caller owns the transaction boundary, so a route can roll the
    whole thing back if anything after this fails. All three writes are in the same
    transaction by construction: a scores row whose raw responses were not written is
    un-recomputable, raw responses with no scores are invisible to every consumer, and a
    submission row without either is a sitting that never happened.

    Four statements however many dimensions are scored, and none of them a read: the form
    registration, the sitting's INSERT (whose RETURNING brings `public_id` back), one
    multi-row INSERT of the raw responses, and one upsert of the scores.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from model import (
        AssessmentForm,
        AssessmentResponse,
        AssessmentSubmission,
        PersonDimensionScore,
    )

    # The form version has to be registered before a submission can name it: the
    # composite foreign key is what stops `form_version` being free text. Registering on
    # first use rather than on deploy means a new item file starts being usable the moment
    # it ships, with no ordering requirement between the two.
    AssessmentForm.register("core", result.form_version)

    sitting = AssessmentSubmission(
        user_id=user_id,
        kind="core",
        form_version=result.form_version,
        status="scored",
        completed_at=db.func.now(),
        scored_at=db.func.now(),
    )
    db.session.add(sitting)
    # Flushed because `public_id` defaults to `uuidv7()` in the database (A13) -- the value
    # does not exist until the INSERT has run. The INSERT fetches it back with RETURNING
    # (the mapper's eager_defaults="auto" on a driver that supports it), so there is no
    # second read. Added through the ORM rather than as a Core insert on purpose:
    # dashboard_feed's after_flush hook is what retires the cached Recent Activity when a
    # sitting lands, and a Core statement would slip past it.
    db.session.flush()
    submission_id = sitting.public_id.hex

    for item_id, choice in result.choices.items():
        db.session.add(
            AssessmentResponse(
                user_id=user_id,
                submission_id=submission_id,
                item_id=item_id,
                choice=choice,
                form_version=result.form_version,
            )
        )
    # One multi-row INSERT, sent now rather than at the caller's commit: the upsert below
    # is a Core statement, which does not autoflush, and the raw rows land before the
    # scores derived from them -- the order this function has always written them in.
    db.session.flush()

    scores = [
        {
            "user_id": user_id,
            "dimension_key": dimension_key,
            "score": score,
            # D-17: confidence comes from the submission, indexed strictly -- a dimension
            # the scorer scored but did not grade for confidence is a contract violation,
            # not a default-to-NULL (D-07). None is a legitimate VALUE here for exactly one
            # reason: CONFIDENCE_PENDING_DIMENSIONS (feedback, D-17(a)).
            "confidence": result.confidences[dimension_key],
            "scoring_key_version": result.scoring_key_version,
            "submission_id": submission_id,
        }
        for dimension_key, score in result.scores.items()
    ]
    if scores:
        # One statement on the table's own unique key, uq_pscore_person_dim_keyversion,
        # instead of a SELECT and a write per dimension. The first sitting under a key
        # inserts (scored_at from its column default); a retake overwrites in place, as
        # the RETAKE SEMANTICS above describe. Two first sittings at once no longer race:
        # the second waits for the first's rows and updates them, where select-then-insert
        # had already decided "no row" and failed on the unique key.
        upsert = pg_insert(PersonDimensionScore.__table__).values(scores)
        db.session.execute(
            upsert.on_conflict_do_update(
                index_elements=["user_id", "dimension_key", "scoring_key_version"],
                set_={
                    "score": upsert.excluded.score,
                    # A retake refreshes confidence with the score -- a new sitting's score
                    # carrying the OLD sitting's e would attribute one submission's answer
                    # pattern to another.
                    "confidence": upsert.excluded.confidence,
                    "submission_id": upsert.excluded.submission_id,
                    "scored_at": db.func.now(),
                },
            )
        )

    return submission_id


def has_completed_assessment(user_id: int) -> bool:
    """True if this user has a sitting of the CURRENT instrument on record.

    Keyed to the current scoring_key_version deliberately, not to "any submission ever".
    Completion is a fact about an instrument, not about the user: when the item file or the
    scoring method changes, every profile reverts to not-completed and the product re-prompts
    (decided with Sebastian 2026-08-19 for the v1-WorkPulse -> v2 replacement, and the same
    logic applies to any future v3). The old raw rows are not lost -- they stay append-only
    per D-16 -- but a sitting of one instrument says nothing the next instrument may consume.

    This is the read path the web layer must use for completion gating. Querying the
    person-side tables from app.py directly fails tests/test_employer_visibility.py, and
    adding app.py to that allowlist is explicitly the wrong fix (D-01).
    """
    from assessment_form import scoring_key_version
    from model import PersonDimensionScore

    return (
        PersonDimensionScore.query.filter_by(
            user_id=user_id,
            scoring_key_version=scoring_key_version(),
        ).first()
        is not None
    )


def get_dimension_scores(user_id: int) -> dict[str, float] | None:
    """The user's current dimension scores, {dimension_key: score}, or None.

    THE sanctioned read for match scoring (decided with Sebastian 2026-08-19): the match
    pipeline consumes a person's profile through this function, keeping the
    test_employer_visibility.py allowlist closed -- match_scoring.py takes plain dicts
    and never touches the person-side tables itself. What leaves this function is
    already the full D-01-sensitive object, so every caller inherits D-01's constraint:
    scores feed the model; they are never surfaced to an employer, and anything shown
    anywhere is a match RESULT.

    Keyed to the CURRENT scoring_key_version, same reasoning as
    has_completed_assessment: scores from a superseded instrument are not comparable to
    company scores calibrated against the current one. None means "no current profile"
    -- an ordinary state (new user, or instrument changed), not an error. Consumers must
    treat None as "cannot be matched yet", never as a zero/default profile (D-07);
    match_core refuses a partial dimension dict for the same reason.
    """
    from assessment_form import scoring_key_version
    from model import PersonDimensionScore

    rows = PersonDimensionScore.query.filter_by(
        user_id=user_id,
        scoring_key_version=scoring_key_version(),
    ).all()
    if not rows:
        return None
    return {r.dimension_key: r.score for r in rows}


def get_dimension_confidences(user_id: int) -> dict[str, float | None] | None:
    """The user's current stored confidences, {dimension_key: confidence_or_None}, or None
    if no current profile exists. The sanctioned read for D-17 confidence, same doorway
    logic as get_dimension_scores.

    D-17's semantics bind every caller: confidence describes how well one ladder position
    summarizes four answers -- low is never read as gaming, high is never read as honesty,
    and a None value (feedback, pending S-18 per D-17(a) -- or any pre-S-31 row) is never
    read as high. D-17(b): analyses upstream of S-18 may not filter or weight by these
    values at all.
    """
    from assessment_form import scoring_key_version
    from model import PersonDimensionScore

    rows = PersonDimensionScore.query.filter_by(
        user_id=user_id,
        scoring_key_version=scoring_key_version(),
    ).all()
    if not rows:
        return None
    return {r.dimension_key: r.confidence for r in rows}


def dimension_scores_for_submission(submission_id: str) -> dict[str, float] | None:
    """Re-derive the six dimension scores for one identified `core` sitting, from its
    raw responses -- independent of what `PersonDimensionScore` currently holds.

    THE sanctioned read for BUILD_PLAN A-5's D-15 pin (⚑5): the Situation Report pins
    to a NAMED sitting rather than "whatever is current", and `PersonDimensionScore`
    is upserted per (user, dimension, scoring_key_version) -- a retake overwrites it
    in place (see that model's docstring). `AssessmentResponse` rows are append-only
    (D-16) and never touched by a retake, so re-deriving from the pinned submission's
    own rows via `assessment_form.score_stored_choices` is the only way to read that
    sitting's scores once a later retake has moved "current" on.

    Returns None if `submission_id` names no responses -- an unknown or malformed
    handle, never a partial score (D-07): a caller with a real pin always gets either
    a complete six-dimension dict or an explicit absence to handle.

    Also None when the sitting's rows cannot be scored against the CURRENT item file
    -- a sitting from before an item-bank change whose item ids the file no longer
    holds. The Situation Report's default pin (`situation_report_service._default_pin`,
    over `completed_core_sittings`) is deliberately not keyed to the scoring-key
    version, so it can name such a sitting; raising here turned that into a 500. An
    absence is the honest answer: the default pin falls forward to the next readable
    sitting on it, and an explicit pin gates on `core_unreadable`.
    """
    from model import AssessmentResponse

    rows = AssessmentResponse.query.filter_by(submission_id=submission_id).all()
    if not rows:
        return None

    from assessment_form import AssessmentError, score_stored_choices

    choices = {r.item_id: r.choice for r in rows}
    try:
        return score_stored_choices(choices)
    except AssessmentError:
        return None


def first_completed_core_submission_id(user_id: int) -> str | None:
    """This user's earliest `core` sitting's `submission_id`, or None.

    THE anchor for BUILD_PLAN A-5's D-15 pin (⚑5): "the first completed core
    sitting" means this row, by `completed_at` ascending (`id` ascending as the
    tiebreak two sittings in the same instant would otherwise leave ambiguous).
    Stable by construction -- `core` sittings are append-only
    (`assessment_repository`'s docstring), so a later retake can never change which
    row was first.

    Reads `AssessmentSubmission` rather than the gated person-side tables (it is not
    on `tests/test_employer_visibility.py`'s allowlist because it does not need to
    be: a `core` row's `result`/`answers` are null by a check constraint, so its
    identity carries no answer or score). Kept behind this doorway anyway, alongside
    `latest_completed_core_submission_id` below, because
    `solverah/repositories/assessment_repository.py`'s own docstring is explicit that
    nothing reads a `core` row through it -- everything a caller wants from a core
    sitting stays behind `assessment_store`.
    """
    from model import AssessmentSubmission

    row = (
        AssessmentSubmission.query.filter_by(user_id=user_id, kind="core")
        .order_by(AssessmentSubmission.completed_at.asc(), AssessmentSubmission.id.asc())
        .first()
    )
    return row.public_id.hex if row is not None else None


def latest_completed_core_submission_id(user_id: int) -> str | None:
    """This user's most recent `core` sitting's `submission_id`, or None.

    The "latest" half of BUILD_PLAN A-5's D-15 pin (⚑5): what an explicit
    `POST /me/situation-report/recalibrate` re-pins to. Mirrors
    `assessment_repository.current_submission`'s descending order, kept here rather
    than there for the same reason `first_completed_core_submission_id` is -- see its
    docstring.
    """
    from model import AssessmentSubmission

    row = (
        AssessmentSubmission.query.filter_by(user_id=user_id, kind="core")
        .order_by(AssessmentSubmission.completed_at.desc(), AssessmentSubmission.id.desc())
        .first()
    )
    return row.public_id.hex if row is not None else None


def completed_core_sittings(user_id: int) -> list[tuple[str, datetime]]:
    """Every completed `core` sitting this user has, as `(submission_id, completed_at)`
    pairs, oldest first. Empty list if none. Read-only.

    The candidate list for BUILD_PLAN A-5's default D-15 pin (⚑5) once core became
    retakeable (6babb39): `situation_report_service._default_pin` picks the sitting
    that was current when the user's first Environment Report was filed, which needs
    the sittings in time order rather than just the two ends of it. Same order as
    `first_completed_core_submission_id` (`completed_at`, then `id`, ascending), so
    element 0 is always that function's answer and element -1 is
    `latest_completed_core_submission_id`'s.

    Deliberately NOT keyed to the scoring-key version, like the two functions it
    mirrors. The pin rule is about WHEN a sitting happened relative to the report, and
    a version filter would silently drop the sitting that was current at filing time
    and anchor on a different one. Whether a sitting can still be scored is
    `dimension_scores_for_submission`'s question (it returns None for one it cannot),
    and the caller asks it per candidate. `completed_at IS NULL` rows are excluded: a
    `core` row is always written complete (`persist_submission`), and a sitting with no
    completion time cannot be placed before or after anything.

    Ids only, never answers or scores -- same D-01 reasoning as
    `first_completed_core_submission_id`.
    """
    from model import AssessmentSubmission

    rows = (
        AssessmentSubmission.query.filter(
            AssessmentSubmission.user_id == user_id,
            AssessmentSubmission.kind == "core",
            AssessmentSubmission.completed_at.isnot(None),
        )
        .order_by(AssessmentSubmission.completed_at.asc(), AssessmentSubmission.id.asc())
        .with_entities(AssessmentSubmission.public_id, AssessmentSubmission.completed_at)
        .all()
    )
    return [(public_id.hex, completed_at) for public_id, completed_at in rows]


def latest_core_completed_at(user_id: int):
    """When this user's most recent `core` sitting completed (aware datetime), or None.

    Read by `assessment_service.CORE_RETAKE_COOLDOWN`'s check and nothing else. Same row
    and same order as `latest_completed_core_submission_id`.
    """
    from model import AssessmentSubmission

    row = (
        AssessmentSubmission.query.filter_by(user_id=user_id, kind="core")
        .order_by(AssessmentSubmission.completed_at.desc(), AssessmentSubmission.id.desc())
        .with_entities(AssessmentSubmission.completed_at)
        .first()
    )
    return row[0] if row is not None else None


def get_trait_preferences(
    db, user_id: int, *, as_of: datetime | None = None
) -> dict[str, TraitPreference]:
    """The user's per-trait tolerance and must-have flags, from their LATEST sitting --
    or, with *as_of*, from the latest sitting created at or before that instant.

    THE sanctioned read for the six-trait match model's person-side preferences
    (PRODUCT_DECISIONS.md §2, 2026-10-13): the Situation Report and the match service
    read tolerance through here, never through the table.

    *as_of* (an aware datetime) is the Situation Report's D-15 pin (Sebastian,
    2026-10-14: "tolerance follows D-15"): the report reads the sitting that was current
    when its pin took hold, so a later tolerance change does nothing until the next
    re-pin. A user whose first sitting is newer than *as_of* reads as UNANSWERED here;
    the report then asks `first_trait_preferences_after` for the step that followed its
    pinned core sitting. Sittings are append-only, so the answer for a fixed
    *as_of* never changes. The match service passes no *as_of* and reads the latest.

    Always all six keys. A user with no sitting gets every trait UNANSWERED
    (steps None, must_have False, answered False) -- which means "today's behaviour"
    downstream, never a default tolerance. `solverah.domain.trait_preferences.flat_zones`
    turns the result into zones, or None for an unanswered user.

    One statement: the latest sitting is the one holding the user's highest row id
    (among rows created at or before *as_of*, when given), found by a scalar subquery
    on `ix_ptpref_user_latest`. A sitting's six rows share one `created_at` (one
    flush, one transaction's `now()`), so the cut never splits a sitting.
    """
    from sqlalchemy import select

    from model import PersonTraitPreference as Pref

    latest_sitting = select(Pref.sitting_id).where(Pref.user_id == user_id)
    if as_of is not None:
        latest_sitting = latest_sitting.where(Pref.created_at <= as_of)
    latest_sitting = latest_sitting.order_by(Pref.id.desc()).limit(1).scalar_subquery()
    return _trait_preferences_of_sitting(db, user_id, latest_sitting)


def first_trait_preferences_after(
    db, user_id: int, *, after: datetime, before: datetime | None = None
) -> dict[str, TraitPreference]:
    """The user's FIRST tolerance sitting created strictly after *after* (and strictly
    before *before*, when given), in `get_trait_preferences`' shape -- every trait
    UNANSWERED when there is none in that window.

    The Situation Report's fallback for its D-15 tolerance pin (orchestrator ruling
    2026-10-14): a user with no sitting by the report's anchor gets the tolerance step
    that followed the pinned core sitting -- *after* is that sitting's `completed_at`,
    *before* the next core sitting's, if any. "First", not "latest": the step belongs
    to that core sitting, and a later change waits for a re-pin. Append-only rows, so
    once a sitting exists in the window this answer never changes.

    Same single statement as `get_trait_preferences`, lowest row id instead of highest.
    """
    from sqlalchemy import select

    from model import PersonTraitPreference as Pref

    first_sitting = select(Pref.sitting_id).where(
        Pref.user_id == user_id, Pref.created_at > after
    )
    if before is not None:
        first_sitting = first_sitting.where(Pref.created_at < before)
    first_sitting = first_sitting.order_by(Pref.id.asc()).limit(1).scalar_subquery()
    return _trait_preferences_of_sitting(db, user_id, first_sitting)


def _trait_preferences_of_sitting(db, user_id: int, sitting_subquery) -> dict[str, TraitPreference]:
    """All six traits of the one sitting *sitting_subquery* selects; unanswered when it
    selects none."""
    from sqlalchemy import select

    from model import PersonTraitPreference as Pref
    from solverah.domain.trait_preferences import unanswered_preferences

    rows = db.session.execute(
        select(
            Pref.dimension_key, Pref.under_steps, Pref.over_steps, Pref.must_have
        ).where(Pref.user_id == user_id, Pref.sitting_id == sitting_subquery)
    ).all()

    prefs = unanswered_preferences()
    for dimension_key, under_steps, over_steps, must_have in rows:
        prefs[dimension_key] = TraitPreference(
            dimension_key=dimension_key,
            under_steps=under_steps,
            over_steps=over_steps,
            must_have=bool(must_have),
            answered=True,
        )
    return prefs


def save_trait_preferences(db, user_id: int, prefs) -> str:
    """Append one sitting of trait preferences. Returns its sitting id (32 hex chars).

    `prefs` is `{trait: TraitPreference}` covering all six traits, each answered.
    Validated here as well as at the route (`validate_trait_preferences` raises
    `TraitPreferenceError`), because this is the write path every caller shares and the
    two-must-have rule has no database constraint behind it.

    Append-only: earlier sittings stay (Julie's principle, 2026-10-13: never overwrite
    earlier context automatically); the newest becomes current for
    `get_trait_preferences`. Does NOT commit -- the caller owns the transaction,
    as with `persist_submission`.
    """
    import uuid

    from model import PersonTraitPreference as Pref
    from solverah.domain.trait_preferences import (
        FORM_VERSION,
        TRAIT_KEYS,
        validate_trait_preferences,
    )

    validate_trait_preferences(prefs)
    sitting_id = uuid.uuid4()
    db.session.add_all(
        Pref(
            user_id=user_id,
            sitting_id=sitting_id,
            dimension_key=key,
            under_steps=prefs[key].under_steps,
            over_steps=prefs[key].over_steps,
            must_have=prefs[key].must_have,
            form_version=FORM_VERSION,
        )
        for key in TRAIT_KEYS
    )
    db.session.flush()
    return sitting_id.hex


def _export_trait_preferences(user_id: int) -> list[dict]:
    """Every trait-preference row this user has, every sitting, oldest first."""
    from model import PersonTraitPreference as Pref

    rows = Pref.query.filter_by(user_id=user_id).order_by(Pref.id).all()
    return [
        {
            "sitting_id": r.sitting_id.hex,
            "dimension": r.dimension_key,
            "under_steps": r.under_steps,
            "over_steps": r.over_steps,
            "must_have": r.must_have,
            "form_version": r.form_version,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def export_person_side(user_id: int) -> dict[str, list[dict]]:
    """Every person-side row we hold for one user, as plain dicts.

    THE doorway for account-rights requests -- GDPR/CCPA access, portability, and the
    "what survives deletion" assertions that go with them. account_lifecycle.py calls
    this instead of importing the models: an export endpoint is precisely the module
    that would otherwise widen the tests/test_employer_visibility.py allowlist, and D-01
    keeps that list closed. Adding account_lifecycle.py to ALLOWED is the wrong fix.

    Deliberately NOT keyed to the current scoring_key_version, unlike
    get_dimension_scores. Those reads answer "what can be consumed now", so a superseded
    instrument correctly drops out. A subject-access request asks a different question --
    what do you HOLD about me -- and a version filter there would silently return an
    incomplete answer to a legal request (D-07: never degrade to a quiet default).

    Returns plain dicts rather than ORM rows on purpose: the caller cannot navigate back
    to the tables through the objects it was handed, so the doorway stays a doorway.
    """
    from model import AssessmentResponse, PersonDimensionScore

    answers = (
        AssessmentResponse.query.filter_by(user_id=user_id)
        .order_by(AssessmentResponse.answered_at, AssessmentResponse.id)
        .all()
    )
    scores = (
        PersonDimensionScore.query.filter_by(user_id=user_id)
        .order_by(PersonDimensionScore.dimension_key)
        .all()
    )
    return {
        "answers": [
            {
                "submission_id": a.submission_id,
                "item_id": a.item_id,
                "choice": a.choice,
                "form_version": a.form_version,
                "answered_at": a.answered_at.isoformat() if a.answered_at else None,
            }
            for a in answers
        ],
        "dimension_scores": [
            {
                "dimension": s.dimension_key,
                "score": s.score,
                "confidence": s.confidence,
                "scoring_key_version": s.scoring_key_version,
                "submission_id": s.submission_id,
                "scored_at": s.scored_at.isoformat() if s.scored_at else None,
            }
            for s in scores
        ],
        # Every sitting, not just the current one -- the same "what do you HOLD" reading
        # as the two keys above. account_service picks keys from this dict by name, so
        # this reaches /me/export only once auth-accounts wires it in.
        "trait_preferences": _export_trait_preferences(user_id),
    }
