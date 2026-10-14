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
    * ``environment_reports``/``environment_dimension_score``, ``manager_profiles``,
      ``situation_report_pins`` (BUILD_PLAN D-7), ``pulse_checkins`` (BUILD_PLAN
      D-7b, 2026-09-11), and ``experiments`` (BUILD_PLAN B-5) follow the identical
      reconciliation and for the identical reason: none carries a name, email, or
      free-text identifier -- a `user_id` pointing at the now-anonymous tombstone is
      all that is left. This module does not touch any of them either; nothing in
      :func:`delete_account` needs to, which is the point. ``pulse_checkins`` and
      ``experiments`` differ from the other three in *why* they qualify: neither is
      D-16 append-only research data, they qualify because none of their columns are
      free text (`item_scores`/`experienced` on one, `dimension`/`direction`/
      `register`/`status` -- all closed vocabularies -- on the other) -- the D-7b
      ruling's actual test, which the other three also happen to pass.
    * Everything else containing personal content is destroyed, including
      ``pulse_events`` (``note`` is free text, so D-7b puts it on the other side of
      that same line) and every resume object in R2.
    * ``AuditLog`` event rows are kept (they now point at the tombstone); their
      IP/user-agent columns age out separately via retention_cleanup.py. This is also
      where ``situation_report_recalibrate`` events end up -- an ordinary
      ``log_audit_event`` call (`solverah/services/situation_report_service.py`), so it
      rides this existing handling rather than needing a mechanism of its own.

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
from environment_report_store import environment_report_history
from experiment_store import experiments_for_user
from manager_profile_store import manager_profile_history
from model import AssessmentSubmission, IntakeSubmission, User, db
from pulse_store import pulse_checkin_history, pulse_events_in_range
from situation_report_pin_store import explicit_pin
from solverah.domain import auth as auth_domain
from solverah.infra import storage
from solverah.repositories import (
    account_repository,
    assessment_repository,
    intake_repository,
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

#: Every kind whose current sitting the export reads, in one query: the legacy
#: quiz's two (``_legacy_quiz``) and the two whose raw answers D-7b added.
_EXPORT_SUBMISSION_KINDS = ("wpll", "work_pulse", "focus_type", "manager_match")


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


def _profile_resume_key(user_id: int) -> Any:
    """``load_document(user_id).get("resumeKey")``, read without the document when it can be.

    The key is in one of two places. A profile written since Phase 2a keeps it
    on its ``resumes`` row, and ``assemble`` lays that row over anything in
    ``extra`` -- so a row, when there is one, is the answer, and one indexed read
    finds it. Every such row was written after its ``profiles`` row existed (the
    migration inserted every profile first; ``update_document`` ensures the row
    before writing one), so it is always a row ``load_document`` would read too.
    With no row, whatever key there is rides in ``extra`` -- on a profile the
    migration carried over verbatim and nobody has saved since, or as a value
    too malformed to promote -- and the document itself answers, as it does
    when there is no resume at all: nothing short of reading ``extra`` tells
    those cases apart.
    """
    resume = profile_repository.current_resume(user_id)
    if resume is not None:
        return resume.object_key
    return profile_repository.load_document(user_id, include_assessments=False).get(
        "resumeKey"
    )


def collect_resume_keys(user: User, intakes: List[IntakeSubmission]) -> List[str]:
    """Every R2 object key that stores this person's resume bytes."""
    keys = []
    profile_key = _profile_resume_key(user.id)
    if profile_key:
        keys.append(profile_key)
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


def _legacy_quiz(
    user_id: int, submissions: Dict[str, AssessmentSubmission]
) -> Optional[Dict[str, Any]]:
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
      Its *existence* is all that is read here -- its id, not the row. The row
      is still live and still holds ``selected_statement_ids``, beside dead
      quiz columns of JSON that a yes-or-no question has no use for.
    * ``null`` survives as the answer for an account that has neither.

    The name stays ``legacy_quiz`` too. It reads oddly now that these are
    ordinary submissions, but renaming an export key to suit the storage
    underneath it is precisely the coupling the key was named to avoid.

    *submissions* is the export's one ``current_submissions`` read. It holds
    both kinds' full rows, ``narrative`` included, so nothing is read again here.
    """
    wpll = submissions.get("wpll")
    work_pulse = submissions.get("work_pulse")

    if wpll is None and work_pulse is None:
        if intake_repository.find_user_intake(user_id, only=("id",)) is None:
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
    resume_corrections = profile_repository.resume_corrections_for_user(user.id)
    # BUILD_PLAN D-7b: focus_type/manager_match's *answers* are the export gap this
    # closes. Their scored `result` is NOT missing -- it never was -- it reaches
    # export already, nested at `profile.focus_type_result`/`profile.manager_match_result`
    # via `profile_repository.load_document`'s merge of `document_domain.ASSESSMENT_RESULT_KEYS`
    # (confirmed on the wire by A25's contract ledger, docs/ARCHITECTURE.md: `export` is
    # one of the six steps `manager_match_result` is embedded in). Only the raw
    # submitted answers were absent from every part of the payload.
    #
    # One read for every sitting the export carries -- these two and the legacy
    # quiz's two -- where each kind used to be a query of its own.
    submissions = assessment_repository.current_submissions(
        user.id, _EXPORT_SUBMISSION_KINDS
    )
    focus_type_submission = submissions.get("focus_type")
    manager_match_submission = submissions.get("manager_match")

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
        "legacy_quiz": _legacy_quiz(user.id, submissions),
        # Keyed "assessment_answers" rather than after the table it comes from:
        # the export is the subject's answers, and mirroring an internal table
        # name into a public payload is how a schema detail becomes an API
        # contract.
        "assessment_answers": person_side["answers"],
        "dimension_scores": person_side["dimension_scores"],
        # BUILD_PLAN B-1's D-7 rule: pulse_checkins/pulse_events join export the same
        # commit that creates them. Unbounded reads (no since/until) -- a subject-access
        # export is "everything held", not a recent window.
        "pulse_checkins": pulse_checkin_history(user.id),
        "pulse_events": pulse_events_in_range(user.id),
        # BUILD_PLAN B-5: experiments joins export the same commit that creates it,
        # per the cross-cutting D-7 rule. Unbounded, same reasoning as the pulse
        # reads above -- every experiment a user has ever started, not a recent
        # window. Raw store rows, not the service layer's enriched shape: the
        # derived `phase`/`readout` are computed from live Pulse data at read time
        # and are not this user's own stored content, so an export is the row as
        # written, the same distinction `dimension_scores` above draws for the
        # person-side tables.
        "experiments": experiments_for_user(user.id),
        # BUILD_PLAN D-7: environment_reports and manager_profiles are append-only
        # (D-16) -- every sitting is a real one, so the export is the full history,
        # unbounded, same reasoning as the pulse reads above. situation_report_pin is
        # the opposite shape on purpose: at most one row per user (the table's own
        # docstring), so a single object-or-null is the honest export, not a list.
        "environment_reports": environment_report_history(user.id),
        "manager_profiles": manager_profile_history(user.id),
        "situation_report_pin": explicit_pin(user.id),
        "job_recommendations": [
            {
                "job_id": r.job_id,
                "score": r.score,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recommendations
        ],
        # BUILD_PLAN D-7b: corrected_value is what the user typed to fix a
        # parser-extracted field, so it is their own content the same way
        # `assessment_answers` above is.
        "resume_parse_corrections": [
            {
                "resume_key": c.resume_key,
                "field": c.field,
                "parsed_value": c.parsed_value,
                "corrected_value": c.corrected_value,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in resume_corrections
        ],
        # BUILD_PLAN D-7b. See the comment above these two submissions are fetched:
        # this is deliberately only the raw answers, not a repeat of `result`, which
        # already reaches export inside `profile`.
        "focus_type_answers": (
            focus_type_submission.answers if focus_type_submission is not None else None
        ),
        "manager_match_answers": (
            manager_match_submission.answers if manager_match_submission is not None else None
        ),
    }

    # `GET /me/export` is a read, so it does not commit (Phase 3, P0-3's server
    # half). The event is still recorded -- a subject-access export is the last
    # thing to lose a trail on -- but a worker writes the row.
    audit.record_read_event(
        action="account_export", actor_user_id=user.id, resource="account"
    )
    return AccountResult(status=200, body=payload)


def _end_read_transaction_keeping_rows() -> None:
    """Commit a transaction that has only read, without expiring what it loaded.

    A plain commit or rollback would expire the user row and every intake, and
    :func:`delete_account` goes on to write through the one and read the ids of
    the others -- one reload each, for rows it already holds. Nothing is
    pending, so the commit writes nothing; it only returns the connection.
    """
    session = db.session()
    expire = session.expire_on_commit
    session.expire_on_commit = False
    try:
        session.commit()
    finally:
        session.expire_on_commit = expire


def delete_account(user: User, confirm: Any) -> AccountResult:
    """Erase personal data, retaining de-identified assessment rows."""
    if confirm != DELETE_CONFIRMATION:
        return AccountResult(
            status=400,
            body={"error": 'Confirmation required: send {"confirm": "DELETE"}'},
        )

    intakes = account_repository.find_intakes_for_email(user.email)
    resume_keys = collect_resume_keys(user, intakes)

    # DB ledger I. Everything above only read, and the R2 deletes below are up
    # to three network calls a key: end the transaction first, so the
    # connection is not held idle in transaction across them.
    _end_read_transaction_keeping_rows()

    # 1. Resume bytes out of R2 first -- object storage is the copy that would
    #    otherwise be forgotten.
    failed_keys = delete_r2_objects(resume_keys)

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
    #    deleting the row. environment_reports/environment_dimension_score,
    #    manager_profiles, situation_report_pins (BUILD_PLAN D-7), and
    #    pulse_checkins (BUILD_PLAN D-7b, 2026-09-11) ride the identical
    #    mechanism -- see this module's docstring -- so there is nothing to do
    #    for any of them here either.

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
