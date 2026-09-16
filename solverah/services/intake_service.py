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
from solverah.infra import storage
from solverah.infra.storage import ALLOWED_MIME, MAX_BYTES
from solverah.repositories import (
    assessment_repository,
    intake_repository,
    profile_repository,
    user_repository,
)
from solverah.services import assessment_service, audit, outbox, resume_service

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

def early_access_request(data: Dict[str, Any]) -> IntakeResult:
    """Forward the landing-page interest form to info@solverah.com.

    **This used to be the only endpoint in the intake funnel that returned 500
    on a mail failure, and it was right to.** Nothing was persisted -- the lead
    existed only as an email -- so swallowing the error lost it outright, and a
    500 at least told the visitor to try again.

    Phase 3 removes the reason rather than the behaviour. The lead is now written
    to the outbox before anything is returned, so it is durable the instant this
    function commits and a worker retries delivery until it lands. There is no
    longer a failure that loses it, so there is no longer a failure to report:
    the endpoint answers 200, which is the truth -- the submission was accepted.

    Still not a row in a real table. `outbox` is a queue and `purge_published`
    deletes delivered rows, so the lead's durable home is still the recipient's
    inbox. That is a product decision this phase does not get to make; what it
    fixes is the window in which the lead existed nowhere at all.
    """
    first_name = (data.get("firstName") or "").strip()
    last_name = (data.get("lastName") or "").strip()
    email = (data.get("email") or "").strip().lower()

    # Basic validation
    if not first_name or not last_name or not email:
        return _error(400, "First name, last name, and email are required.")

    entry_id = outbox.enqueue(
        outbox.TOPIC_EMAIL_EARLY_ACCESS,
        {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": (data.get("phone") or "").strip(),
            "preferred_contact": (data.get("preferredContact") or "").strip(),
            "career_journey": (data.get("careerJourney") or "").strip(),
        },
    )
    db.session.commit()
    outbox.publish_soon(entry_id)

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


def finalize(data: Dict[str, Any]) -> IntakeResult:
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

    # The notification and the submission row are one commit. Previously the row
    # was committed by insert_submission and the email followed it, so a Resend
    # outage left a submission nobody was told about -- recoverable only by
    # someone thinking to query the table.
    entry_id = outbox.enqueue(
        outbox.TOPIC_EMAIL_INTAKE_NOTIFICATION,
        {
            "first_name": fields.first_name,
            "last_name": fields.last_name,
            "email": fields.email,
            "state": fields.state,
            "phone": fields.phone,
            "linkedin_url": fields.linkedin_url,
            "portfolio_url": fields.portfolio_url,
            "object_key": fields.object_key,
            "mime": fields.mime,
            "size": fields.size,
        },
    )
    db.session.commit()
    outbox.publish_soon(entry_id)

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

    # This path and /register now mint the same thing: a 6-digit code from
    # generate_verification_code(). Until G9 this one minted uuid.uuid4().hex,
    # and the comment here argued the two flows were "compatible" because
    # POST /auth/email/verify compares against confirmation_token either way.
    # That was true at the API layer and false everywhere a user stands.
    # Walked live on production 2026-09-15 (docs/USER_SCENARIOS.md G9): the
    # 32-hex value is mailed inside a template that labels it a "6-digit code"
    # and carries no link at all, and /verify-email strips non-digits and caps
    # input at six characters -- so the value actually sent cannot be typed
    # into the only screen that accepts it. An account created here could not
    # be verified except by failing a login and using the resend link, which
    # silently replaced the token with a compatible one. Unifying the
    # generator is what makes the email template's own words true.
    code = auth_domain.generate_verification_code()
    hashed_pw = hash_password(password).decode("utf-8")
    full_name = ("%s %s" % (intake.first_name, intake.last_name)).strip()
    profile_data = resume_service.build_profile_from_intake(intake)

    new_user = User(
        email=intake.email.lower(),
        password_hash=hashed_pw,
        name=full_name,
        role=role,
        email_confirmed=False,
        confirmation_token=code,
        confirmation_sent_at=auth_domain.utcnow(),
    )
    db.session.add(new_user)
    # Flushed for its id, not committed: the user and their profile land in one
    # transaction. See the same note in auth_service.register.
    db.session.flush()
    profile_repository.update_document(new_user.id, lambda _existing: profile_data)

    intake.status = "account_created"
    entry_id = outbox.enqueue(
        outbox.TOPIC_EMAIL_VERIFICATION, {"to": new_user.email, "code": code}
    )
    db.session.commit()
    outbox.publish_soon(entry_id)

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

    # Two halves, two homes, and the split is the point of Phase 2d: the
    # statement selections are intake data and stay on `user_intake`; the WPLL
    # answers and their insight are one of the five assessment products and go
    # where the other four go.
    intake_repository.upsert_user_intake(
        user_id=user.id, selected_ids=selected_ids
    )

    submission = assessment_repository.open_current(
        user.id, "wpll", assessment_service.CLIENT_FORM_VERSION
    )
    submission.answers = wpll_answers
    submission.narrative = wpll_insight_text or None
    submission.status = "complete"
    # Set on the first save that carries answers and never moved afterwards. A
    # re-save replaces the answers -- it always has -- but "when did this person
    # finish WPLL" is a fact about the first sitting, and a re-save is not a
    # retake. This is the one instrument whose completion timestamp is not
    # refreshed, which is why `open_current` leaves the field to the caller.
    if wpll_answers and submission.completed_at is None:
        submission.completed_at = auth_domain.utcnow()

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
            "wpll_completed": submission.completed_at is not None,
        },
    )
