"""Account data export and deletion -- GDPR/CCPA-style user rights.

Implements the D-16 reconciliation decided by Sebastian on 2026-08-20
(recorded in Solverah_IP/compliance/ and STATE.md):

    On account deletion, all PERSONAL information is erased, but assessment
    response rows are RETAINED IN DE-IDENTIFIED FORM. D-16's append-only rule
    governs scoring integrity (no silent edits to raw responses); it does not
    require keeping the link between responses and an identifiable person.

Deletion strategy -- "tombstone", chosen over hard row deletion so that the
person-side tables' NOT NULL user_id foreign key stays intact without a schema
migration:

    * The ``user`` row is kept but scrubbed of every personal field.
    * The person-side response and dimension-score rows survive, linked only to
      the tombstone id -- de-identified research data. This module never touches
      those two tables directly; it reads them through ``assessment_store``, the
      single auditable doorway D-01 keeps the allowlist closed around.
    * Everything else containing personal content is destroyed, including every
      resume object in R2.
    * ``AuditLog`` event rows are kept (they now point at the tombstone); their
      IP/user-agent columns age out separately via retention_cleanup.py.

The order of operations in :func:`delete_account` is deliberate: **object
storage first**. A failed database transaction can be retried; a resume left in
a bucket after the row that pointed at it is gone has nothing left to find it.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from assessment_store import export_person_side
from model import IntakeSubmission, User, db
from solverah.domain import auth as auth_domain
from solverah.infra import storage
from solverah.repositories import (
    account_repository,
    assessment_repository,
    profile_repository,
)
from solverah.services import audit

__all__ = [
    "TOMBSTONE_DOMAIN",
    "AccountResult",
    "collect_resume_keys",
    "delete_account",
    "delete_r2_objects",
    "export_account_data",
]

TOMBSTONE_DOMAIN = "tombstone.invalid"

#: Required literal in the delete body, so a stray click or a replayed request
#: cannot destroy an account.
DELETE_CONFIRMATION = "DELETE"


@dataclass
class AccountResult:
    """A service outcome the API layer turns into a response."""

    status: int
    body: Dict[str, Any] = field(default_factory=dict)
    clear_session: bool = False

    @property
    def ok(self) -> bool:
        return self.status < 400


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def collect_resume_keys(user: User, intakes: List[IntakeSubmission]) -> List[str]:
    """Every R2 object key that stores this person's resume bytes."""
    keys = []
    profile = profile_repository.load_document(user.id)
    if profile.get("resumeKey"):
        keys.append(profile["resumeKey"])
    for intake in intakes:
        if intake.resume_key:
            keys.append(intake.resume_key)
    # De-dupe, preserve order
    return list(dict.fromkeys(keys))


def delete_r2_objects(keys: List[str]) -> List[str]:
    """Best-effort delete of resume objects. Returns keys that FAILED.

    A failed R2 delete must not abort the DB-side erasure -- but it must be
    surfaced, because 'deleted' with a live resume object is a false claim
    (D-07: never degrade to a silent safe default).
    """
    if not keys:
        return []

    try:
        s3 = storage.get_s3_client()
        bucket = os.environ["S3_BUCKET_NAME"]
    except Exception:  # noqa: BLE001 -- R2 unreachable/unconfigured
        return list(keys)  # report all as failed

    failed = []
    for key in keys:
        try:
            s3.delete_object(Bucket=bucket, Key=key)
        except Exception:  # noqa: BLE001 -- reported, not raised
            failed.append(key)
    return failed


def _legacy_quiz(user_id: int):
    """The export's ``legacy_quiz`` block, unchanged on the wire since Phase 2d.

    The five keys were columns on ``user_intake`` and are now two rows in
    ``assessment_submissions``. The block's *shape* is a published contract --
    a subject-access response is not a place to quietly rename things -- so the
    keys stay, and only where they are read from moved.

    Three details keep it byte-identical rather than merely equivalent:

    * ``wpll_answers`` falls back to ``[]``, never ``null``. The column it
      replaced was ``NOT NULL DEFAULT '[]'``, so an account that selected
      statements but never answered the quiz exported an empty list, and an
      export that started answering ``null`` there would be a changed contract
      for the accounts least likely to notice.
    * The block is present, rather than ``null``, whenever the account has a
      ``user_intake`` row -- even with no submissions behind it. That is the
      condition the old code had, because the five values lived on that row.
      Its *existence* is what is read here, not any assessment column on it;
      the row is still live and still holds ``selected_statement_ids``.
    * ``null`` survives as the answer for an account that has neither.

    The name stays ``legacy_quiz`` too. It reads oddly now that these are
    ordinary submissions, but renaming an export key to suit the storage
    underneath it is precisely the coupling the key was named to avoid.
    """
    wpll = assessment_repository.current_submission(user_id, "wpll")
    work_pulse = assessment_repository.current_submission(user_id, "work_pulse")

    if wpll is None and work_pulse is None:
        if account_repository.find_user_intake(user_id) is None:
            return None

    return {
        "wpll_answers": (wpll.answers if wpll else None) or [],
        "wpll_insight_text": wpll.narrative if wpll else None,
        "wpl_answers": work_pulse.answers if work_pulse else None,
        "wpl_narrative": work_pulse.narrative if work_pulse else None,
        "wpl_result": work_pulse.result if work_pulse else None,
    }


def export_account_data(user: User) -> AccountResult:
    """One JSON document of every identified data class held for this user."""
    intakes = account_repository.find_intakes_for_email(user.email)
    person_side = export_person_side(user.id)
    recommendations = account_repository.find_job_recommendations(user.id)

    payload = {
        "exported_at": _now(),
        "account": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "email_confirmed": user.email_confirmed,
        },
        "profile": profile_repository.load_document(user.id),
        "intake_submissions": [
            {
                "id": i.id,
                "first_name": i.first_name,
                "last_name": i.last_name,
                "email": i.email,
                "state": i.state,
                "phone": i.phone,
                "linkedin_url": i.linkedin_url,
                "portfolio_url": i.portfolio_url,
                # The basename, not the key: the key is an internal storage
                # locator and exporting it hands out a path into the bucket.
                "resume_filename": i.resume_key.rsplit("/", 1)[-1] if i.resume_key else None,
                "status": i.status,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in intakes
        ],
        "legacy_quiz": _legacy_quiz(user.id),
        # Keyed "assessment_answers" rather than after the table it comes from:
        # the export is the subject's answers, and mirroring an internal table
        # name into a public payload is how a schema detail becomes an API
        # contract.
        "assessment_answers": person_side["answers"],
        "dimension_scores": person_side["dimension_scores"],
        "job_recommendations": [
            {
                "job_id": r.job_id,
                "score": r.score,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recommendations
        ],
    }

    audit.log_audit_event(
        action="account_export", actor_user_id=user.id, resource="account"
    )
    db.session.commit()
    return AccountResult(status=200, body=payload)


def delete_account(user: User, confirm: Any) -> AccountResult:
    """Erase personal data, retaining de-identified assessment rows."""
    if confirm != DELETE_CONFIRMATION:
        return AccountResult(
            status=400,
            body={"error": 'Confirmation required: send {"confirm": "DELETE"}'},
        )

    intakes = account_repository.find_intakes_for_email(user.email)

    # 1. Resume bytes out of R2 first -- object storage is the copy that would
    #    otherwise be forgotten.
    failed_keys = delete_r2_objects(collect_resume_keys(user, intakes))

    # 2. Rows whose CONTENT is personal: destroy.
    account_repository.delete_personal_rows(user.id, intakes)

    # 3. The user row: tombstone.
    account_repository.tombstone_user(
        user,
        tombstone_domain=TOMBSTONE_DOMAIN,
        now_iso=_now(),
        dead_password=auth_domain.unusable_password_hash(),
    )

    # 4. The person-side response and dimension-score rows are deliberately kept
    #    -- de-identified via the tombstone (the decided D-16 reconciliation).
    #    Nothing to do here; that is the point of tombstoning instead of
    #    deleting the row.

    audit.log_audit_event(
        action="account_deleted",
        actor_user_id=user.id,
        resource="account",
        metadata={"r2_delete_failures": len(failed_keys)},
    )
    db.session.commit()

    return AccountResult(
        status=200,
        body={
            "message": (
                "Account deleted. Assessment responses are retained in "
                "de-identified form."
            ),
            # Non-empty => surface, never hide (D-07).
            "r2_delete_failures": failed_keys,
        },
        clear_session=True,
    )
