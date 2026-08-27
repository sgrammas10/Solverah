"""Scheduled data-retention cleanup — enforces DATA_RETENTION_SCHEDULE.md.

Run periodically (Render cron job, or manually):  python retention_cleanup.py
Idempotent; safe to run any number of times. Prints a summary line per rule.

Rules enforced here (the ⚙ rows of the schedule):
  1. Abandoned intake submissions — IntakeSubmission rows older than 90 days
     whose email never became a confirmed account: row deleted AND the R2
     resume object deleted.
  2. Audit-log IP/user-agent minimization — rows older than 365 days keep the
     event but lose ip_address and user_agent.
  3. Orphaned R2 objects — resume objects that no database row references and
     that are older than the upload grace period. These come from presigned
     uploads that were never finalized: the object lands in the bucket, the
     row is never written, and rules 1-2 (which walk rows) can never see them.

Deliberately NOT here: account deletion (user-initiated, account_lifecycle.py)
and anything touching assessment responses (D-16).
"""

from __future__ import annotations

import datetime
import os
import sys

ABANDONED_INTAKE_DAYS = 90
AUDIT_PII_DAYS = 365

# An unreferenced object is only orphaned once it is old enough that no upload
# could still be mid-flight: presigned URLs expire after 10 minutes and finalize
# follows immediately, so 48h is generous by three orders of magnitude.
ORPHAN_GRACE_HOURS = 48
SWEPT_PREFIXES = ("intake/", "profile/")


def _referenced_resume_keys(db, IntakeSubmission, ResumeParseCorrection, User) -> set:
    """Collect every resume object key the database still points at.

    Three separate places hold a key, and missing any one of them would make
    this sweep delete a live resume:
      * ``IntakeSubmission.resume_key`` — the intake flow's column;
      * ``ResumeParseCorrection.resume_key`` — retained parser training data;
      * ``User.profile_data`` JSON — both the active ``resumeKey`` and the
        ``_parsedResumeSnapshot.resumeKey`` used for correction diffing.

    Returns:
        Set of object keys that must never be deleted.
    """
    keys = set()
    for (key,) in db.session.query(IntakeSubmission.resume_key).all():
        if key:
            keys.add(key)
    for (key,) in db.session.query(ResumeParseCorrection.resume_key).all():
        if key:
            keys.add(key)
    for (profile,) in db.session.query(User.profile_data).all():
        if not isinstance(profile, dict):
            continue
        if profile.get("resumeKey"):
            keys.add(profile["resumeKey"])
        snapshot = profile.get("_parsedResumeSnapshot")
        if isinstance(snapshot, dict) and snapshot.get("resumeKey"):
            keys.add(snapshot["resumeKey"])
    return keys


def _iter_bucket_objects(s3, bucket: str):
    """Yield (key, last_modified) for every object under the swept prefixes."""
    paginator = s3.get_paginator("list_objects_v2")
    for prefix in SWEPT_PREFIXES:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"], obj["LastModified"]


def run_cleanup(dry_run_sweep: bool = False) -> dict:
    from app import app, get_s3_client
    from model import (AuditLog, IntakeSubmission, ResumeParseCorrection,
                       User, db)
    from sqlalchemy import func

    now = datetime.datetime.now(datetime.timezone.utc)
    summary = {"abandoned_intakes_deleted": 0, "r2_objects_deleted": 0,
               "r2_delete_failures": 0, "audit_rows_minimized": 0,
               "orphans_deleted": 0, "orphan_delete_failures": 0}

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

        # Commit rules 1-2 before sweeping, so rule 3 reads the row state this
        # run leaves behind rather than a pre-deletion snapshot.
        db.session.commit()

        # ── Rule 3: orphaned R2 objects ───────────────────────────────────

        if bucket and not dry_run_sweep:
            summary.update(
                _sweep_orphans(now, bucket, get_s3_client, db,
                               IntakeSubmission, ResumeParseCorrection, User)
            )

    return summary


def _sweep_orphans(now, bucket, get_s3_client, db,
                   IntakeSubmission, ResumeParseCorrection, User) -> dict:
    """Delete resume objects that no row references and that are past grace.

    Args:
        now:    Timezone-aware current time.
        bucket: Target R2/S3 bucket name.

    Returns:
        Dict with ``orphans_deleted`` and ``orphan_delete_failures`` counts.
    """
    out = {"orphans_deleted": 0, "orphan_delete_failures": 0}

    # Circuit breaker: an empty database would make every object look orphaned.
    # If there are no users and no intakes, assume this is pointed at the wrong
    # database rather than that the bucket is legitimately all garbage.
    if User.query.count() == 0 and IntakeSubmission.query.count() == 0:
        out["orphan_sweep_skipped"] = "empty database"
        return out

    referenced = _referenced_resume_keys(db, IntakeSubmission,
                                         ResumeParseCorrection, User)
    cutoff = now - datetime.timedelta(hours=ORPHAN_GRACE_HOURS)
    s3 = get_s3_client()

    for key, last_modified in _iter_bucket_objects(s3, bucket):
        if key in referenced or last_modified >= cutoff:
            continue
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            out["orphans_deleted"] += 1
        except Exception:
            out["orphan_delete_failures"] += 1

    return out


if __name__ == "__main__":
    # --skip-sweep runs rules 1-2 only, for a first look at what rule 3
    # would be operating against before letting it delete anything.
    result = run_cleanup(dry_run_sweep="--skip-sweep" in sys.argv)
    print(f"retention_cleanup: {result}")
    # Non-zero exit if object deletion failed, so a cron wrapper can alert.
    sys.exit(
        1
        if result["r2_delete_failures"] or result["orphan_delete_failures"]
        else 0
    )
