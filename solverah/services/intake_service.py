"""The public intake flow: presign, finalize, and the four ways to attach it.

The intake funnel is: an anonymous visitor uploads a resume and fills in a form
(``presign`` then ``finalize``), and then attaches that submission to an account
one of four ways -- create a new one, sign in to an existing one, link it while
already signed in, or save an anonymous quiz session onto their account.

Part 5.2 collapses the four attachment endpoints into a single
``POST /intake/submissions/{id}/claim`` with a ``mode`` discriminator, which
removes three copies of the "does this email already exist" branch.  That is
Phase 1b; the four are preserved separately here.

One thing worth reading twice: the storage HEAD check in :func:`verify_upload`
is not decoration.  The presign step signs a ``ContentLength``, so R2 rejects a
body of a different size -- but nothing stops a client from skipping the upload
entirely and calling finalize anyway.  The HEAD is what makes the submission row
mean "a resume of this size and type exists at this key".
"""

from __future__ import annotations

import datetime
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from model import IntakeSubmission, User, db
from solverah.domain import auth as auth_domain
from solverah.domain import intake as domain
from solverah.infra import email as email_infra
from solverah.infra import storage
from solverah.infra.storage import ALLOWED_MIME, MAX_BYTES
from solverah.repositories import intake_repository, profile_repository, user_repository
from solverah.services import audit, resume_service

__all__ = [
    "IntakeResult",
    "create_account",
    "early_access_request",
    "finalize",
    "link_account",
    "presign",
    "save_to_account",
    "sign_in",
    "verify_upload",
]

PRESIGN_TTL_SECONDS = 10 * 60

#: Answer cap on the anonymous Work Pulse Lite-Lite session.
MAX_WPLL_ANSWERS = 5


@dataclass
class IntakeResult:
    """A service outcome the API layer turns into a response."""

    status: int
    body: Dict[str, Any] = field(default_factory=dict)
    user: Optional[User] = None
    issue_token: bool = False

    @property
    def ok(self) -> bool:
        return self.status < 400


def _error(status: int, message: str) -> IntakeResult:
    return IntakeResult(status=status, body={"error": message})


# ---------------------------------------------------------------------------
# Anonymous intake
# ---------------------------------------------------------------------------

def early_access_request(data: Dict[str, Any], logger) -> IntakeResult:
    """Forward the landing-page interest form to info@solverah.com.

    Does not persist to the database -- the submission exists only as an email,
    which is a real gap: a Resend outage loses the lead entirely, with only a log
    line behind. Phase 3's transactional outbox is what fixes it.
    """
    first_name = (data.get("firstName") or "").strip()
    last_name = (data.get("lastName") or "").strip()
    email = (data.get("email") or "").strip().lower()

    # Basic validation
    if not first_name or not last_name or not email:
        return _error(400, "First name, last name, and email are required.")

    try:
        email_infra.send_early_access_modal_notification(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=(data.get("phone") or "").strip(),
            preferred_contact=(data.get("preferredContact") or "").strip(),
            career_journey=(data.get("careerJourney") or "").strip(),
        )
    except Exception as exc:  # noqa: BLE001 -- reported to the caller below
        logger.error("Failed to send early access modal notification: %s", exc)
        return _error(500, "Failed to send notification.")

    return IntakeResult(status=200, body={"ok": True})


def presign(mime: str, size: int) -> IntakeResult:
    """Step 1 of 2: mint a submission id and a presigned PUT URL.

    The object key is ``intake/{submission_id}/resume.{ext}`` with a v4 UUID, so
    it is not guessable -- an anonymous submission has no other access control
    on it.
    """
    if mime not in ALLOWED_MIME:
        return _error(400, "Unsupported file type")
    if size <= 0 or size > MAX_BYTES:
        return _error(400, "File too large (max 10MB)")

    submission_id = str(uuid.uuid4())
    ext = resume_service.MIME_EXTENSIONS.get(mime, "bin")

    # Non-guessable object key
    object_key = "intake/%s/resume.%s" % (submission_id, ext)

    # Presigned PUT URL for direct browser upload.  ContentLength is part of
    # the signature so the declared size is binding: a client that PUTs a body
    # of any other length gets a signature mismatch from R2 instead of a
    # silently accepted oversized object.
    url = storage.get_s3_client().generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": os.environ["S3_BUCKET_NAME"],
            "Key": object_key,
            "ContentType": mime,
            "ContentLength": size,
        },
        ExpiresIn=PRESIGN_TTL_SECONDS,  # 10 minutes
        HttpMethod="PUT",
    )

    return IntakeResult(
        status=200,
        body={
            "submission_id": submission_id,
            "object_key": object_key,
            "upload_url": url,
            "max_bytes": MAX_BYTES,
        },
    )


def verify_upload(object_key: str, mime: str, size: int) -> Optional[str]:
    """HEAD the uploaded object and confirm it matches what was declared.

    Returns:
        None when it matches, otherwise the error message to return with a 400.
    """
    try:
        head = storage.get_s3_client().head_object(
            Bucket=os.environ["S3_BUCKET_NAME"], Key=object_key
        )
        actual_size = int(head.get("ContentLength", 0))
        actual_mime = head.get("ContentType", "")
        if actual_size != size:
            return "Uploaded file size mismatch"
        if actual_mime != mime:
            return "Uploaded file type mismatch"
    except Exception:  # noqa: BLE001 -- a missing key and an unreachable bucket
        # are the same answer to the caller: we cannot confirm the upload.
        return "Upload not found in storage"
    return None


def finalize(data: Dict[str, Any], logger) -> IntakeResult:
    """Step 2 of 2: validate, confirm the upload, insert the row, notify."""
    fields = domain.parse_submission(data)
    problem = domain.validate_submission(
        fields,
        allowed_mime=ALLOWED_MIME,
        max_bytes=MAX_BYTES,
        require_email=True,
        name_too_long_message="First or last name is too long",
    )
    if problem:
        return _error(400, problem)

    upload_problem = verify_upload(fields.object_key, fields.mime, fields.size)
    if upload_problem:
        return _error(400, upload_problem)

    intake_repository.insert_submission(fields, email=fields.email, status="uploaded")

    try:
        email_infra.send_intake_notification(
            first_name=fields.first_name,
            last_name=fields.last_name,
            email=fields.email,
            state=fields.state,
            phone=fields.phone,
            linkedin_url=fields.linkedin_url,
            portfolio_url=fields.portfolio_url,
            object_key=fields.object_key,
            mime=fields.mime,
            size=fields.size,
        )
    except Exception as exc:  # noqa: BLE001 -- the row is committed; the
        # notification is ours to chase, not the submitter's problem.
        logger.error(
            "Failed to send intake notification to info@solverah.com: %s", exc
        )

    return IntakeResult(status=200, body={"ok": True})


# ---------------------------------------------------------------------------
# Attaching a submission to an account
# ---------------------------------------------------------------------------

def create_account(
    data: Dict[str, Any], *, hash_password, validate_password
) -> IntakeResult:
    """Register a new account from an intake submission."""
    submission_id = (data.get("submission_id") or "").strip()
    password = data.get("password") or ""
    role = data.get("role") or "job-seeker"

    if not domain.is_valid_uuid(submission_id):
        return _error(400, "Invalid submission_id")

    if role != "job-seeker":
        return _error(400, "Only job seeker accounts are supported")

    is_valid, validation_message = validate_password(password)
    if not is_valid:
        return _error(400, validation_message)

    intake = intake_repository.find_submission(submission_id)
    if not intake:
        return _error(404, "Submission not found")

    if user_repository.email_exists(intake.email):
        return _error(400, "User already exists")

    # Note: this path issues a UUID-hex confirmation token rather than the
    # 6-digit code /register uses, and POST /confirm-email compares against
    # confirmation_token either way -- so the two flows are compatible, but a
    # user arriving here gets a link-style token in an email templated for a
    # code. Preserved as-is; unifying it changes what lands in an inbox.
    token = uuid.uuid4().hex
    hashed_pw = hash_password(password).decode("utf-8")
    full_name = ("%s %s" % (intake.first_name, intake.last_name)).strip()
    profile_data = resume_service.build_profile_from_intake(intake)

    new_user = User(
        email=intake.email.lower(),
        password_hash=hashed_pw,
        name=full_name,
        role=role,
        email_confirmed=False,
        confirmation_token=token,
        confirmation_sent_at=auth_domain.utcnow(),
    )
    db.session.add(new_user)
    # Flushed for its id, not committed: the user and their profile land in one
    # transaction. See the same note in auth_service.register.
    db.session.flush()
    profile_repository.update_document(new_user.id, lambda _existing: profile_data)

    intake.status = "account_created"
    db.session.commit()

    # Send confirmation email (best-effort)
    try:
        email_infra.send_confirmation_email(new_user.email, token)
    except Exception:  # noqa: BLE001 -- account exists; recoverable by resend
        audit.log_audit_event(
            action="email_send_failed",
            actor_user_id=new_user.id,
            resource="email",
            metadata={},
        )

    return IntakeResult(
        status=201,
        body={
            "message": "registered",
            "user": {
                "id": new_user.id,
                "email": new_user.email,
                "name": new_user.name,
                "role": new_user.role,
            },
        },
        user=new_user,
    )


def sign_in(data: Dict[str, Any], *, check_password) -> IntakeResult:
    """Authenticate, then merge the submission into the existing profile.

    Intake values win on conflict: the user just typed them, so they are newer
    than whatever is on the profile.
    """
    from solverah.services.auth_service import LOGIN_LOCKOUT_MINUTES, MAX_LOGIN_ATTEMPTS

    submission_id = (data.get("submission_id") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not domain.is_valid_uuid(submission_id):
        return _error(400, "Invalid submission_id")

    if not email or not domain.is_valid_email(email):
        return _error(400, "Valid email is required")

    intake = intake_repository.find_submission(submission_id)
    if not intake:
        return _error(404, "Submission not found")

    if intake.email.lower() != email:
        return _error(400, "Email does not match submission")

    user = user_repository.find_by_email(email)
    if not user:
        return _error(404, "Account not found")

    if user.locked_until and user.locked_until > auth_domain.utcnow():
        return _error(423, "Account locked. Try again later.")

    if not check_password(user.password_hash, password):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_LOGIN_ATTEMPTS:
            user.locked_until = auth_domain.lockout_until(LOGIN_LOCKOUT_MINUTES)
            user.failed_login_count = 0
        db.session.commit()
        return _error(401, "Invalid credentials")

    user.failed_login_count = 0
    user.locked_until = None

    if not getattr(user, "email_confirmed", False):
        return _error(
            403, "Email not confirmed. Please confirm your email before signing in."
        )

    intake_profile = resume_service.build_profile_from_intake(intake)
    profile_repository.update_document(
        user.id, lambda existing: {**existing, **intake_profile}
    )

    full_name = ("%s %s" % (intake.first_name, intake.last_name)).strip()
    if full_name:
        user.name = full_name

    intake.status = "account_linked"
    audit.log_audit_event(
        action="intake_attach",
        actor_user_id=user.id,
        resource="intake",
        metadata={"submission_id": intake.id, "user_id": user.id},
    )
    db.session.commit()

    return IntakeResult(
        status=200,
        body={
            "message": "signed in",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
            },
        },
        user=user,
        issue_token=True,
    )


def link_account(user: User, current_email: str, data: Dict[str, Any]) -> IntakeResult:
    """Submit the intake form for an already-authenticated user.

    The row is recorded against the JWT identity, not against any email in the
    body -- otherwise a signed-in user could file a submission under someone
    else's address.
    """
    fields = domain.parse_submission(data)
    problem = domain.validate_submission(
        fields,
        allowed_mime=ALLOWED_MIME,
        max_bytes=MAX_BYTES,
        require_email=False,
        name_too_long_message="Name is too long",
    )
    if problem:
        return _error(400, problem)

    upload_problem = verify_upload(fields.object_key, fields.mime, fields.size)
    if upload_problem:
        return _error(400, upload_problem)

    intake_repository.insert_submission(
        fields, email=current_email, status="account_linked"
    )

    intake = intake_repository.find_submission(fields.submission_id)
    if intake:
        intake_profile = resume_service.build_profile_from_intake(intake)
        profile_repository.update_document(
            user.id, lambda existing: {**existing, **intake_profile}
        )
        full_name = ("%s %s" % (fields.first_name, fields.last_name)).strip()
        if full_name:
            user.name = full_name
        db.session.commit()

    audit.log_audit_event(
        action="intake_link_account",
        actor_user_id=user.id,
        resource="intake",
        metadata={"submission_id": fields.submission_id, "email": current_email},
    )

    return IntakeResult(status=200, body={"ok": True})


def save_to_account(user: User, data: Dict[str, Any]) -> IntakeResult:
    """Persist an anonymous Work Pulse Lite-Lite session onto the account.

    Called by the frontend immediately after login when sessionStorage carries
    intake data from the ``/start`` flow.
    """
    selected_ids = data.get("selected_statement_ids", [])
    wpll_answers = data.get("wpll_answers", [])
    wpll_insight_text = data.get("wpll_insight_text", "") or ""

    if not isinstance(selected_ids, list):
        return _error(400, "selected_statement_ids must be a list")
    if not isinstance(wpll_answers, list):
        return _error(400, "wpll_answers must be a list")
    if len(wpll_answers) > MAX_WPLL_ANSWERS:
        return _error(400, "wpll_answers must contain at most 5 items")

    intake = intake_repository.upsert_user_intake(
        user_id=user.id,
        selected_ids=selected_ids,
        wpll_answers=wpll_answers,
        wpll_insight_text=wpll_insight_text,
        now=auth_domain.utcnow(),
    )

    audit.log_audit_event(
        action="create",
        actor_user_id=user.id,
        resource="user_intake",
        metadata={
            "statement_count": len(selected_ids),
            "answer_count": len(wpll_answers),
        },
    )
    db.session.commit()

    return IntakeResult(
        status=200,
        body={
            "message": "Intake saved",
            "wpll_completed": intake.wpll_completed_at is not None,
        },
    )
