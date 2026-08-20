"""Account deletion and data export — GDPR/CCPA-style user rights endpoints.

Implements the D-16 reconciliation decided by Sebastian on 2026-08-20
(recorded in Solverah_IP/compliance/ and STATE.md):

    On account deletion, all PERSONAL information is erased, but assessment
    response rows are RETAINED IN DE-IDENTIFIED FORM. D-16's append-only rule
    governs scoring integrity (no silent edits to raw responses); it does not
    require keeping the link between responses and an identifiable person.

Deletion strategy — "tombstone", chosen over hard row deletion so that
``assessment_response.user_id``'s NOT NULL foreign key stays intact without a
schema migration:

    * The ``user`` row is kept but scrubbed of every personal field
      (email -> ``deleted-<id>@tombstone.invalid``, random unusable password
      hash, name/profile/tokens cleared, ``deleted_at`` marker inside
      ``profile_data``).
    * ``AssessmentResponse`` / ``PersonDimensionScore`` rows survive, linked
      only to the tombstone id — de-identified research data.
    * Everything else that contains personal content is destroyed:
      ``UserIntake`` (legacy quiz results + narratives), ``JobRecommendation``,
      ``ResumeParseCorrection`` (parsed resume content is PII),
      ``IntakeSubmission`` rows matching the account email, and every resume
      object in R2 (profile resume + intake resumes).
    * ``AuditLog`` event rows are kept (they now point at the tombstone);
      their IP/user-agent columns age out separately via retention_cleanup.py.

Export returns one JSON document with every identified data class we hold,
fulfilling access/portability requests without support tickets.
"""

from __future__ import annotations

import datetime
import secrets

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, unset_jwt_cookies
from sqlalchemy import func

from model import (
    AssessmentResponse,
    IntakeSubmission,
    JobRecommendation,
    PersonDimensionScore,
    ResumeParseCorrection,
    User,
    UserIntake,
    db,
)

account_bp = Blueprint("account_lifecycle", __name__)

_TOMBSTONE_DOMAIN = "tombstone.invalid"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _collect_resume_keys(user: User, intakes: list[IntakeSubmission]) -> list[str]:
    """Every R2 object key that stores this person's resume bytes."""
    keys = []
    profile = user.profile_data or {}
    if profile.get("resumeKey"):
        keys.append(profile["resumeKey"])
    for intake in intakes:
        if intake.resume_key:
            keys.append(intake.resume_key)
    # De-dupe, preserve order
    return list(dict.fromkeys(keys))


def _delete_r2_objects(keys: list[str]) -> list[str]:
    """Best-effort delete of resume objects. Returns keys that FAILED.

    A failed R2 delete must not abort the DB-side erasure — but it must be
    surfaced, because 'deleted' with a live resume object is a false claim
    (D-07: never degrade to a silent safe default).
    """
    if not keys:
        return []
    # Imported lazily to avoid a circular import at module load; app.py is the
    # only module that knows the R2 configuration.
    from app import get_s3_client  # noqa: PLC0415
    import os

    failed = []
    try:
        s3 = get_s3_client()
        bucket = os.environ["S3_BUCKET_NAME"]
    except Exception:
        return list(keys)  # R2 unreachable/unconfigured: report all as failed
    for key in keys:
        try:
            s3.delete_object(Bucket=bucket, Key=key)
        except Exception:
            failed.append(key)
    return failed


@account_bp.get("/api/account/export")
@jwt_required()
def export_account_data():
    """GET /api/account/export — one JSON document of everything we hold."""
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return jsonify({"error": "User not found"}), 404

    intakes = IntakeSubmission.query.filter(
        func.lower(IntakeSubmission.email) == (user.email or "").lower()
    ).all()
    user_intake = UserIntake.query.filter_by(user_id=user.id).first()
    responses = (
        AssessmentResponse.query.filter_by(user_id=user.id)
        .order_by(AssessmentResponse.answered_at)
        .all()
    )
    scores = PersonDimensionScore.query.filter_by(user_id=user.id).all()
    recommendations = JobRecommendation.query.filter_by(user_id=user.id).all()

    payload = {
        "exported_at": _now(),
        "account": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "email_confirmed": user.email_confirmed,
        },
        "profile": user.profile_data or {},
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
                "resume_filename": i.resume_key.rsplit("/", 1)[-1] if i.resume_key else None,
                "status": i.status,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in intakes
        ],
        "legacy_quiz": (
            {
                "wpll_answers": user_intake.wpll_answers,
                "wpll_insight_text": user_intake.wpll_insight_text,
                "wpl_answers": user_intake.wpl_answers,
                "wpl_narrative": user_intake.wpl_narrative,
                "wpl_result": user_intake.wpl_result,
            }
            if user_intake
            else None
        ),
        "assessment_responses": [
            {
                "submission_id": r.submission_id,
                "item_id": r.item_id,
                "choice": r.choice,
                "form_version": r.form_version,
                "answered_at": r.answered_at.isoformat() if r.answered_at else None,
            }
            for r in responses
        ],
        "dimension_scores": [
            {
                "dimension": s.dimension_key,
                "score": s.score,
                "confidence": s.confidence,
                "scoring_key_version": s.scoring_key_version,
            }
            for s in scores
        ],
        "job_recommendations": [
            {"job_id": r.job_id, "score": r.score, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in recommendations
        ],
    }

    from app import log_audit_event  # noqa: PLC0415

    log_audit_event(action="account_export", actor_user_id=user.id, resource="account")
    db.session.commit()
    return jsonify(payload), 200


@account_bp.post("/api/account/delete")
@jwt_required()
def delete_account():
    """POST /api/account/delete — erase personal data; keep de-identified research rows.

    Body (JSON): {"confirm": "DELETE"} — explicit confirmation string so a
    stray click or replayed request cannot destroy an account.
    """
    data = request.get_json(silent=True) or {}
    if data.get("confirm") != "DELETE":
        return jsonify({"error": 'Confirmation required: send {"confirm": "DELETE"}'}), 400

    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return jsonify({"error": "User not found"}), 404

    original_email_lower = (user.email or "").lower()
    intakes = IntakeSubmission.query.filter(
        func.lower(IntakeSubmission.email) == original_email_lower
    ).all()

    # 1. Resume bytes out of R2 first — object storage is the copy that would
    #    otherwise be forgotten.
    failed_keys = _delete_r2_objects(_collect_resume_keys(user, intakes))

    # 2. Rows whose CONTENT is personal: destroy.
    for intake in intakes:
        db.session.delete(intake)
    UserIntake.query.filter_by(user_id=user.id).delete()
    JobRecommendation.query.filter_by(user_id=user.id).delete()
    ResumeParseCorrection.query.filter_by(user_id=user.id).delete()

    # 3. The user row: tombstone. Email keeps uniqueness; password becomes an
    #    unusable random string (it is compared via bcrypt, so a non-bcrypt
    #    value can never verify); every personal field is cleared.
    user.email = f"deleted-{user.id}@{_TOMBSTONE_DOMAIN}"
    user.password = f"!deleted!{secrets.token_hex(16)}"
    user.name = None
    user.profile_data = {"deleted_at": _now()}
    user.email_confirmed = False
    user.confirmation_token = None
    user.confirmation_sent_at = None
    user.reset_token = None
    user.reset_sent_at = None

    # 4. AssessmentResponse / PersonDimensionScore rows are deliberately kept —
    #    de-identified via the tombstone (the decided D-16 reconciliation).

    from app import log_audit_event  # noqa: PLC0415

    log_audit_event(
        action="account_deleted",
        actor_user_id=user.id,
        resource="account",
        metadata={"r2_delete_failures": len(failed_keys)},
    )
    db.session.commit()

    resp = jsonify(
        {
            "message": "Account deleted. Assessment responses are retained in de-identified form.",
            "r2_delete_failures": failed_keys,  # non-empty => surface, never hide (D-07)
        }
    )
    unset_jwt_cookies(resp)
    return resp, 200
