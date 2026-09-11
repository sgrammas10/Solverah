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

from sqlalchemy import func

from model import (
    IntakeSubmission,
    JobRecommendation,
    PulseCheckin,
    PulseEvent,
    ResumeParseCorrection,
    User,
    UserIntake,
    UserSession,
    db,
)
from solverah.repositories import assessment_repository, profile_repository

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
    full contact record behind.
    """
    return IntakeSubmission.query.filter(
        func.lower(IntakeSubmission.email) == (email or "").lower()
    ).all()


def find_user_intake(user_id: int):
    """The legacy quiz payloads attached to this account, or None."""
    return UserIntake.query.filter_by(user_id=user_id).first()


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
    for intake in intakes:
        db.session.delete(intake)
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
    # Pulse check-ins and events (BUILD_PLAN B-1, the D-7 cross-cutting rule: a table
    # joins export/delete the day it is created rather than waiting for the D-7
    # catch-up chunk that `environment_reports`/`manager_profiles` still owe). Both
    # hold personal content -- a check-in's own answers, an event's free-text note --
    # so they are destroyed here, not tombstoned or retained de-identified; neither is
    # behind D-01's doorway the way the core assessment rows are.
    PulseCheckin.query.filter_by(user_id=user_id).delete()
    PulseEvent.query.filter_by(user_id=user_id).delete()
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
