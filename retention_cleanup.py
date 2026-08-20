"""Scheduled data-retention cleanup — enforces DATA_RETENTION_SCHEDULE.md.

Run periodically (Render cron job, or manually):  python retention_cleanup.py
Idempotent; safe to run any number of times. Prints a summary line per rule.

Rules enforced here (the ⚙ rows of the schedule):
  1. Abandoned intake submissions — IntakeSubmission rows older than 90 days
     whose email never became a confirmed account: row deleted AND the R2
     resume object deleted.
  2. Audit-log IP/user-agent minimization — rows older than 365 days keep the
     event but lose ip_address and user_agent.

Deliberately NOT here: account deletion (user-initiated, account_lifecycle.py)
and anything touching assessment responses (D-16).
"""

from __future__ import annotations

import datetime
import os
import sys

ABANDONED_INTAKE_DAYS = 90
AUDIT_PII_DAYS = 365


def run_cleanup() -> dict:
    from app import app, get_s3_client
    from model import AuditLog, IntakeSubmission, User, db
    from sqlalchemy import func

    now = datetime.datetime.now(datetime.timezone.utc)
    summary = {"abandoned_intakes_deleted": 0, "r2_objects_deleted": 0,
               "r2_delete_failures": 0, "audit_rows_minimized": 0}

    with app.app_context():
        # ── Rule 1: abandoned intakes ─────────────────────────────────────
        cutoff = now - datetime.timedelta(days=ABANDONED_INTAKE_DAYS)
        stale = IntakeSubmission.query.filter(IntakeSubmission.created_at < cutoff).all()

        s3 = None
        bucket = os.environ.get("S3_BUCKET_NAME")
        for intake in stale:
            # "Abandoned" = no account exists for this email. Account-attached
            # intakes are governed by account deletion instead.
            has_account = (
                User.query.filter(func.lower(User.email) == (intake.email or "").lower()).first()
                is not None
            )
            if has_account:
                continue
            if intake.resume_key and bucket:
                try:
                    if s3 is None:
                        s3 = get_s3_client()
                    s3.delete_object(Bucket=bucket, Key=intake.resume_key)
                    summary["r2_objects_deleted"] += 1
                except Exception:
                    summary["r2_delete_failures"] += 1
                    continue  # keep the row so the next run retries the object
            db.session.delete(intake)
            summary["abandoned_intakes_deleted"] += 1

        # ── Rule 2: audit-log PII minimization ────────────────────────────
        audit_cutoff = now - datetime.timedelta(days=AUDIT_PII_DAYS)
        summary["audit_rows_minimized"] = (
            AuditLog.query.filter(
                AuditLog.created_at < audit_cutoff,
                (AuditLog.ip_address.isnot(None)) | (AuditLog.user_agent.isnot(None)),
            ).update(
                {AuditLog.ip_address: None, AuditLog.user_agent: None},
                synchronize_session=False,
            )
        )

        db.session.commit()

    return summary


if __name__ == "__main__":
    result = run_cleanup()
    print(f"retention_cleanup: {result}")
    # Non-zero exit if object deletion failed, so a cron wrapper can alert.
    sys.exit(1 if result["r2_delete_failures"] else 0)
