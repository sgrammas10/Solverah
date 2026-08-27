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

from solverah.repositories import profile_repository
from model import (
    IntakeSubmission,
    JobRecommendation,
    ResumeParseCorrection,
    User,
    UserIntake,
    db,
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
