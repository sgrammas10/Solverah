"""Queries behind the GDPR/CCPA export and deletion endpoints.

Deletion is a **tombstone**, not a row delete.  The person-side response and
dimension-score rows carry a NOT NULL foreign key to the user, and keeping the
row alive but scrubbed lets those survive de-identified without a schema
migration -- which is the D-16 reconciliation decided 2026-08-20: D-16's
append-only rule governs scoring integrity, not the link between a response and
an identifiable person.

Nothing here reaches the person-side tables.  They are read through
``assessment_store`` -- the single auditable doorway D-01 keeps the allowlist
closed around.
"""

from __future__ import annotations

from typing import List

from sqlalchemy import delete, func

from model import (
    IntakeSubmission,
    JobRecommendation,
    PathFeedback,
    PathFit,
    PathWant,
    PulseCheckin,
    PulseEvent,
    ResumeParseCorrection,
    ResumeParseJob,
    ScoringJob,
    User,
    UserIntake,
    UserSession,
    db,
)
from solverah.repositories import (
    assessment_repository,
    intake_repository,
    path_narrative_repository,
    profile_repository,
)

__all__ = [
    "delete_personal_rows",
    "find_intakes_for_email",
    "find_job_recommendations",
    "find_user_intake",
    "tombstone_user",
]


def find_intakes_for_email(email: str) -> List[IntakeSubmission]:
    """Every intake submission filed under this address.

    Case-insensitive: an intake filed as ``Alice@Example.com`` belongs to
    ``alice@example.com``, and missing it on deletion would leave a resume and a
    full contact record behind. Compares through ``IntakeSubmission.email_key``,
    the expression ``ix_intake_submissions_email_lower`` is built on, with the
    argument lowered by the same ``lower()`` in the database.
    """
    return IntakeSubmission.query.filter(
        IntakeSubmission.email_key == func.lower(email or "")
    ).all()


def find_user_intake(user_id: int):
    """The legacy quiz payloads attached to this account, or None.

    No production caller is left (the export asks
    ``intake_repository.find_user_intake(user_id, only=("id",))``); kept because
    tests/test_dbopt_profile_account.py still recomputes the export with it, and
    now simply the whole-row form of that one reader rather than a second copy.
    """
    return intake_repository.find_user_intake(user_id)


def find_job_recommendations(user_id: int) -> List[JobRecommendation]:
    return JobRecommendation.query.filter_by(user_id=user_id).all()


def delete_personal_rows(user_id: int, intakes: List[IntakeSubmission]) -> None:
    """Destroy every row whose *content* is personal.

    Kept separate from :func:`tombstone_user` because the two answer different
    questions: this is "what must be destroyed", that is "what must survive
    scrubbed". Rows here hold parsed resume content, quiz narratives, and
    contact details -- none of which have research value once de-identified.

    Does not commit.
    """
    # One DELETE ... WHERE id IN (...) for every intake, where a session.delete()
    # per row used to flush one statement each. The default synchronisation marks
    # the matching instances in the session deleted, so the caller's loaded list
    # cannot be flushed back or lazily re-read afterwards.
    intake_ids = [intake.id for intake in intakes]
    if intake_ids:
        db.session.execute(
            delete(IntakeSubmission).where(IntakeSubmission.id.in_(intake_ids))
        )
    UserIntake.query.filter_by(user_id=user_id).delete()
    JobRecommendation.query.filter_by(user_id=user_id).delete()
    ResumeParseCorrection.query.filter_by(user_id=user_id).delete()
    # Assessment submissions hold narratives, archetypes and raw answers, so
    # they are in this function rather than in `tombstone_user`. An explicit
    # delete and not the `ON DELETE CASCADE` on `user_id`: deletion tombstones
    # the user row instead of removing it, so the cascade never fires.
    #
    # This does NOT reach the core assessment's answers or dimension scores.
    # Those survive de-identified -- a decided reconciliation, asserted in
    # tests/test_account_lifecycle.py -- and they are behind D-01's doorway,
    # which is exactly why the submission row it is joined to holds none of them.
    assessment_repository.delete_for_user(user_id)
    # Pulse events (BUILD_PLAN B-1). `note` is short free text, and free text is never
    # retained de-identified (D-7b ruling, 2026-09-11) -- so the row is destroyed here,
    # the same as everything else in this function, and is not behind D-01's doorway the
    # way the core assessment rows are.
    #
    # `pulse_checkins` does NOT appear in this function any more. Its `item_scores` and
    # `experienced` columns are plain 1..5 integers -- no free text anywhere on the row
    # -- so Sebastian's 2026-09-11 ruling keeps it out of the "must be destroyed" class
    # and rides the tombstone instead, exactly like `environment_reports`: nothing to do
    # here, which is the point of tombstoning instead of deleting (see
    # `tombstone_user`/`solverah/services/account_service.py`'s module docstring).
    PulseEvent.query.filter_by(user_id=user_id).delete()
    # Resume-parser job receipts (SECURITY_AUDIT_2026-09 #7, closed D-7b). `resume_name`
    # is often a person's own name and `object_key` locates their resume bytes; neither
    # survived past `resume_jobs.purge_terminal`'s window before that fix, and even after
    # it a fresh row could outlive a deleted account for up to `PURGE_DAYS`. Destroyed
    # rather than retained -- a job receipt has no research value once resolved, unlike
    # the append-only (D-16) tables above.
    ResumeParseJob.query.filter_by(user_id=user_id).delete()
    # Scoring job receipts (3b). `payload` holds submitted answers until the job goes
    # terminal, and `result` -- narratives and archetypes for the three LLM-backed
    # instruments, computed path suggestions for the fourth -- survives for
    # `scoring_jobs.PURGE_DAYS` after that regardless of what happens to the account in
    # between. Both are already destroyed elsewhere the moment they have a permanent
    # home (`assessment_repository.delete_for_user` above); this row is a duplicate
    # receipt with no reader once the account is gone, so it is destroyed rather than
    # left to the purge sweep.
    ScoringJob.query.filter_by(user_id=user_id).delete()
    # Refresh sessions (S3). Not personal *content* like everything above it,
    # but live credentials: `tombstone_user` frees the address by rewriting it
    # and every other route back into the account dies with the password -- a
    # surviving refresh token would be the one that did not, and it would mint
    # access tokens for the tombstoned row indefinitely.
    #
    # Deleted rather than retired, which is the opposite of what happens to
    # these rows everywhere else. A retired row is kept because it is the audit
    # trail of a session that ended; there is no account left for that trail to
    # be about, and `family_id` plus `user_id` on a deleted user is retention
    # with no reader -- the shape SECURITY_AUDIT_2026-09 #7 and #18 are both
    # about. The `ON DELETE CASCADE` on `user_id` never fires here because
    # deletion tombstones the user row instead of removing it, so the delete has
    # to be explicit; the same reasoning as the assessment submissions above.
    UserSession.query.filter_by(user_id=user_id).delete()
    # Stored Tier-2 deep fits (BUILD_PLAN F-5). `payload.matched_skills` is the user's
    # own typed skill names and `gap_skills` is derived from them, so the row carries
    # free text about a person -- destroyed, not retained de-identified, which is the
    # D-7b line `pulse_events` falls on and `pulse_checkins` does not. Explicit rather
    # than by cascade, for the reason the two paragraphs above give: deletion tombstones
    # the user row instead of removing it, so `fk_pathfit_user` never fires.
    PathFit.query.filter_by(user_id=user_id).delete()
    # Inline card judgements (BUILD_PLAN F-6). Destroyed rather than retained
    # de-identified, and this one is NOT the free-text test the two rows above turn
    # on: `verdict` is a closed vocabulary and `onet_code` is a catalogue key, so
    # nothing here is prose. It is destroyed because of what the row *means* rather
    # than how it is spelled -- a judgement is a statement a person made about their
    # own career ("this is too close to what I already do"), and a de-identified
    # opinion is still that person's opinion. The D-16 research argument that keeps
    # `pulse_checkins` and `experiments` does not reach it: nothing downstream reads
    # these rows for anything but rebuilding one user's own query.
    PathFeedback.query.filter_by(user_id=user_id).delete()
    # Stated wants (BUILD_PLAN W-4). Destroyed on `path_feedback`'s reasoning
    # exactly, and it is worth saying why the two reach the same answer from
    # different sides. Nothing on this row is prose either -- `verdict` and
    # `kind` are closed vocabularies, `anchor_onet_code` is a catalogue key,
    # `item_key` is a digest and `item_text` is O*NET's own published sentence,
    # not a word the user typed -- so the D-7b *spelling* rule would retain it.
    # It is destroyed because of what the row MEANS: "I want less of this part of
    # my job" is a statement a person made about their own working life, and a
    # de-identified statement is still theirs. Nothing downstream reads these
    # rows for anything but rotating one user's own retrieval query, so a
    # retained row would be retention with no reader.
    PathWant.query.filter_by(user_id=user_id).delete()
    # Stored narrator sentences (BUILD_PLAN W-16). `why_text` is model-written
    # prose ABOUT the person -- "uses your Python and SQL" -- and free text about a
    # person is never retained de-identified: the `path_fits` answer. Explicit
    # rather than by the `ON DELETE CASCADE` on `fk_pathnarrative_user`, for the
    # reason the paragraphs above give: deletion tombstones the user row.
    path_narrative_repository.delete_for_user(user_id)


def tombstone_user(user: User, tombstone_domain: str, now_iso: str, dead_password: str) -> None:
    """Scrub every personal field on the user row, keeping the row itself.

    The email becomes ``deleted-{id}@{tombstone_domain}`` so the unique
    constraint still holds and the address is freed for re-registration. The
    password becomes a non-bcrypt string, which no ``check_password_hash`` can
    ever match -- it is not a weak password, it is not a password.

    Does not commit.
    """
    user.email = "deleted-%s@%s" % (user.id, tombstone_domain)
    user.password_hash = dead_password
    user.name = None
    # Replaces the whole profile document with the tombstone, which also drops
    # every experience, education, skill and resume row the user had: the write
    # path rebuilds the child tables from the document it is given, and this
    # document has none of them. Going through `update_document` rather than
    # deleting the rows by hand means a field added to the profile in future is
    # erased here without anyone having to remember to come back.
    profile_repository.update_document(user.id, lambda _existing: {"deleted_at": now_iso})
    # The pre-Phase-2a copy of that same document. `users.profile_data` is no
    # longer read or written (model.py), and is kept only so a rollback of the
    # decomposition is a redeploy -- but "nothing reads it" is not "nothing
    # holds it": for every account created before Phase 2a the column still has
    # the phone number, LinkedIn URL, parsed resume text, employment history and
    # quiz results verbatim, and none of that was reachable by the line above.
    # SECURITY_AUDIT_2026-09 4.1: a deletion that leaves it is a deletion in
    # name only. Emptied rather than nulled so the shape still matches the
    # column default, and here rather than in a sweep so it lands in the same
    # transaction as the tombstone -- a scrub that can be committed separately
    # is a scrub that can be missed.
    user.profile_data = {}
    user.email_confirmed = False
    # `users.status`, added in Phase 2c. `users.deleted_at` is deliberately *not*
    # set: the address is still freed by the rewrite above, so the partial unique
    # index `uq_users_email ... WHERE deleted_at IS NULL` keeps behaving like the
    # full constraint it replaced. Turning this into a real soft-delete is a
    # deletion-policy change and needs every user query to grow a filter it does
    # not have yet.
    user.status = "deleted"
    user.confirmation_token = None
    user.confirmation_sent_at = None
    user.reset_token = None
    user.reset_sent_at = None
