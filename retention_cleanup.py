"""Scheduled data-retention cleanup — enforces DATA_RETENTION_SCHEDULE.md.

Production runs it daily as ``flask retention cleanup`` (solverah/cli.py), right
after ``flask retention run`` on the solverah-retention cron. It also runs by
hand:  python retention_cleanup.py [--dry-run] [--skip-sweep]
Idempotent; safe to run any number of times. Prints one summary line.

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

``dry_run`` covers all three rules: each reports what it would delete or scrub
(a count and up to SAMPLE_SIZE ids or keys) and nothing is written to the
database or deleted from R2. Rule 3 still LISTS the bucket, read-only, because
the listing is the only way to know what it would delete.

R2 unconfigured is a failure, not a quiet skip (:func:`exit_code`). Rules 1 and
3 both need it, and rule 3's work can only be known by listing the bucket, so
any pass that cannot reach R2 exits non-zero unless the sweep was explicitly
skipped and rule 1 had no object to delete. Rule 1 deletes no row whose object
it could not delete, so an unconfigured pass changes nothing but rule 2.

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

#: How many ids or keys a dry run names per rule, next to the full count. Keys
#: are ``intake/{uuid}/resume.{ext}`` and ``profile/{user_id}/{uuid}/resume.{ext}``:
#: no filename, so a sample is safe to print into a log.
SAMPLE_SIZE = 20

#: A parse job names its object key before the profile does: the route queues
#: the job with the key and only the job's run writes it into the ``resumes``
#: row. These are the states in which the job row is the key's only holder --
#: the predicate of ``ix_resume_parse_jobs_pending``.
UNFINISHED_PARSE_STATES = ("queued", "running")


def _referenced_resume_keys(db, IntakeSubmission, ResumeParseCorrection, User) -> set:
    """Collect every resume object key the database still points at.

    Four separate places hold a key, and missing any one of them would make
    this sweep delete a live resume:
      * ``IntakeSubmission.resume_key`` — the intake flow's column;
      * ``ResumeParseCorrection.resume_key`` — retained parser training data;
      * the profile tables — the ``resumes`` row, and the
        ``_parsedResumeSnapshot.resumeKey`` inside ``profiles.extra`` that
        correction diffing needs long after the resume itself was replaced;
      * ``ResumeParseJob.object_key`` of a queued or running job — a newer
        upload is not on the profile until its parse has run.

    Returns:
        Set of object keys that must never be deleted.
    """
    from model import ResumeParseJob

    keys = set()
    for (key,) in db.session.query(IntakeSubmission.resume_key).all():
        if key:
            keys.add(key)
    # DISTINCT: corrections are one row per (user, resume, field), so each key
    # would otherwise come back once per corrected field.
    for (key,) in db.session.query(ResumeParseCorrection.resume_key).distinct().all():
        if key:
            keys.add(key)
    for (key,) in (
        db.session.query(ResumeParseJob.object_key)
        .filter(ResumeParseJob.status.in_(UNFINISHED_PARSE_STATES))
        .distinct()
    ):
        if key:
            keys.add(key)
    from solverah.repositories import profile_repository

    keys |= profile_repository.referenced_resume_keys()
    return keys


def _iter_bucket_objects(s3, bucket: str):
    """Yield (key, last_modified) for every object under the swept prefixes."""
    paginator = s3.get_paginator("list_objects_v2")
    for prefix in SWEPT_PREFIXES:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"], obj["LastModified"]


def _sample(items: list, key: str) -> dict:
    """A dry run's report for one rule: the count and the first few items."""
    return {"count": len(items), key: items[:SAMPLE_SIZE]}


def _storage(get_s3_client):
    """Resolve R2 once. Returns ``(bucket, client, problem)``.

    *problem* is None when R2 is usable and otherwise says why not, naming the
    variable. Building the client makes no network call, so this answers "is it
    configured", not "is it up".
    """
    bucket = os.environ.get("S3_BUCKET_NAME")
    if not bucket:
        return None, None, "S3_BUCKET_NAME is not set"
    try:
        return bucket, get_s3_client(), None
    except KeyError as exc:  # storage.get_s3_client reads os.environ[...] directly
        return bucket, None, "%s is not set" % exc.args[0]
    except Exception as exc:  # noqa: BLE001 -- named by type only; reported, not raised
        return bucket, None, "storage client failed: %s" % type(exc).__name__


def run_cleanup(dry_run_sweep: bool = False, dry_run: bool = False) -> dict:
    """Run all three rules and return the summary.

    Args:
        dry_run_sweep: Skip rule 3 entirely (``--skip-sweep``). Despite the name
            this never was a dry run; it is kept for its existing callers.
        dry_run: Change nothing anywhere; report what each rule would do under
            ``summary["would"]``.
    """
    # `get_s3_client` came from `app` until app.py became a thin shell over the
    # factory (bb67227) and stopped exporting it; from then until 2026-09-28 this
    # import raised and no rule here could run.
    from app import app
    from model import IntakeSubmission, ResumeParseCorrection, User, db
    from solverah.infra.storage import get_s3_client

    now = datetime.datetime.now(datetime.timezone.utc)
    bucket, s3, problem = _storage(get_s3_client)
    summary = {"dry_run": dry_run, "r2_unconfigured": problem,
               "abandoned_intakes_deleted": 0, "r2_objects_deleted": 0,
               "r2_delete_failures": 0, "r2_objects_left_unconfigured": 0,
               "audit_rows_minimized": 0,
               "orphans_deleted": 0, "orphan_delete_failures": 0}
    if dry_run:
        summary["would"] = {}

    with app.app_context():
        _abandoned_intakes(summary, now, bucket, s3, db, IntakeSubmission, User)
        _minimize_audit_pii(summary, now, db)

        # Commit rules 1-2 before sweeping, so rule 3 reads the row state this
        # run leaves behind rather than a pre-deletion snapshot.
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()

        # ── Rule 3: orphaned R2 objects ───────────────────────────────────
        if dry_run_sweep:
            summary["orphan_sweep_skipped"] = "--skip-sweep"
        elif problem:
            summary["orphan_sweep_skipped"] = "R2 not configured: " + problem
        else:
            swept = _sweep_orphans(now, bucket, lambda: s3, db,
                                   IntakeSubmission, ResumeParseCorrection, User,
                                   dry_run=dry_run)
            if dry_run and "orphan_sweep_skipped" not in swept:
                summary["would"]["orphans"] = swept.pop("would_delete")
            summary.update(swept)

    # The storage half of the work could not be done: rule 1 left objects
    # behind, or rule 3 (whose work only a listing could reveal) never ran.
    summary["r2_work_blocked"] = bool(problem) and (
        summary["r2_objects_left_unconfigured"] > 0
        or summary.get("would", {}).get("intake_objects", {}).get("count", 0) > 0
        or not dry_run_sweep
    )
    return summary


def _abandoned_intakes(summary, now, bucket, s3, db, IntakeSubmission, User) -> None:
    """Rule 1: delete accountless intakes past their window, each after its object.

    R2 unusable is a failed object delete for every row that has one: with no
    bucket the row is kept and counted in ``r2_objects_left_unconfigured``,
    with a bucket but no usable client it is kept and counted in
    ``r2_delete_failures``. Either way an unconfigured pass deletes nothing
    here and exits non-zero, and the next configured run does both halves.
    """
    from sqlalchemy import delete, func, select

    # "Abandoned" = no account exists for this email. Account-attached
    # intakes are governed by account deletion instead. One anti-join
    # finds them, where this used to ask `users` once per stale row, and
    # only the two columns the loop reads come back.
    #
    # The age filter is served by ix_intake_submissions_created_at, and the
    # intake side of the email match is `IntakeSubmission.email_key`, the
    # one expression every intake email lookup uses.
    cutoff = now - datetime.timedelta(days=ABANDONED_INTAKE_DAYS)
    has_account = (
        select(User.id)
        .where(func.lower(User.email) == IntakeSubmission.email_key)
        .exists()
    )
    stale = db.session.execute(
        select(IntakeSubmission.id, IntakeSubmission.resume_key)
        .where(IntakeSubmission.created_at < cutoff, ~has_account)
    ).all()
    # End the read's transaction before any storage call. Nothing has been
    # written yet, so this discards nothing; it stops the connection sitting
    # idle in a transaction through one R2 delete per stale row, which the
    # server's idle-in-transaction timeout would kill. The DELETE below opens
    # a fresh transaction once every object's outcome is known.
    db.session.rollback()

    if summary["dry_run"]:
        keys = [key for _, key in stale if key]
        summary["would"]["abandoned_intakes"] = _sample([i for i, _ in stale], "sample_ids")
        summary["would"]["intake_objects"] = _sample(keys, "sample_keys")
        return

    abandoned = []
    for intake_id, resume_key in stale:
        if resume_key and not bucket:
            summary["r2_objects_left_unconfigured"] += 1
            continue  # a failed delete by another name: the row waits for R2
        if resume_key:
            try:
                if s3 is None:
                    raise RuntimeError("R2 client unavailable")
                s3.delete_object(Bucket=bucket, Key=resume_key)
                summary["r2_objects_deleted"] += 1
            except Exception:
                summary["r2_delete_failures"] += 1
                continue  # keep the row so the next run retries the object
        abandoned.append(intake_id)

    # Every object's outcome is known by now, so the rows go in one DELETE.
    # Each row still goes only after its object did: deleting the row first
    # would leave an object that nothing points at.
    if abandoned:
        db.session.execute(
            delete(IntakeSubmission)
            .where(IntakeSubmission.id.in_(abandoned))
            .execution_options(synchronize_session=False)
        )
    summary["abandoned_intakes_deleted"] = len(abandoned)


def _minimize_audit_pii(summary, now, db) -> None:
    """Rule 2: audit rows past their window lose ip_address and user_agent."""
    from model import AuditLog

    audit_cutoff = now - datetime.timedelta(days=AUDIT_PII_DAYS)
    due = AuditLog.query.filter(
        AuditLog.created_at < audit_cutoff,
        (AuditLog.ip_address.isnot(None)) | (AuditLog.user_agent.isnot(None)),
    )
    if summary["dry_run"]:
        summary["would"]["audit_rows_minimized"] = {
            "count": due.count(),
            "sample_ids": [i for (i,) in due.with_entities(AuditLog.id)
                           .order_by(AuditLog.created_at).limit(SAMPLE_SIZE)],
        }
        return
    summary["audit_rows_minimized"] = due.update(
        {AuditLog.ip_address: None, AuditLog.user_agent: None},
        synchronize_session=False,
    )


def _sweep_orphans(now, bucket, get_s3_client, db,
                   IntakeSubmission, ResumeParseCorrection, User,
                   dry_run: bool = False) -> dict:
    """Delete resume objects that no row references and that are past grace.

    Args:
        now:     Timezone-aware current time.
        bucket:  Target R2/S3 bucket name.
        dry_run: List and decide, but delete nothing; the candidates come back
                 under ``would_delete``.

    Returns:
        Dict with ``orphans_deleted`` and ``orphan_delete_failures`` counts.
    """
    from sqlalchemy import or_, select

    out = {"orphans_deleted": 0, "orphan_delete_failures": 0}

    # Circuit breaker: an empty database would make every object look orphaned.
    # If there are no users and no intakes, assume this is pointed at the wrong
    # database rather than that the bucket is legitimately all garbage. One
    # EXISTS each, not two count(*)s: the question is whether any row exists.
    populated = db.session.execute(
        select(or_(select(User.id).exists(), select(IntakeSubmission.id).exists()))
    ).scalar()
    if not populated:
        out["orphan_sweep_skipped"] = "empty database"
        return out

    referenced = _referenced_resume_keys(db, IntakeSubmission,
                                         ResumeParseCorrection, User)
    # Every database read this rule needs is done. Close the read-only
    # transaction before the bucket listing and its deletes, which are unbounded
    # and would otherwise hold the connection idle in a transaction throughout.
    db.session.rollback()
    cutoff = now - datetime.timedelta(hours=ORPHAN_GRACE_HOURS)

    # Rules 1-2 have committed by now. A storage error here is reported, by
    # type only, rather than raised: raising would lose the summary of what
    # those two rules already did. `exit_code` still fails the pass.
    try:
        s3 = get_s3_client()
        listed = list(_iter_bucket_objects(s3, bucket))
    except Exception as exc:  # noqa: BLE001 -- EndpointConnectionError, ClientError, ...
        out["orphan_sweep_skipped"] = "storage error: %s" % type(exc).__name__
        return out
    orphans = [key for key, last_modified in listed
               if key not in referenced and last_modified < cutoff]
    if dry_run:
        # `listed` is the denominator a human needs: orphans that are most of
        # the bucket mean a missed reference, not a lot of garbage.
        out["would_delete"] = {**_sample(orphans, "sample_keys"), "listed": len(listed)}
        return out

    for key in orphans:
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            out["orphans_deleted"] += 1
        except Exception:
            out["orphan_delete_failures"] += 1

    return out


def exit_code(summary: dict) -> int:
    """The process exit status a cron should see for *summary*.

    Non-zero when an object delete failed, when R2 is not configured while
    rule 1 or rule 3 had work for it (``r2_work_blocked``), or when rule 3 did
    not run for any reason but ``--skip-sweep`` -- R2 unconfigured, a storage
    error, or an empty database (a cron pointed at the wrong one). A crash
    never gets here; it exits non-zero on its own.
    """
    failed = summary.get("r2_delete_failures") or summary.get("orphan_delete_failures")
    skipped = summary.get("orphan_sweep_skipped")
    swept_badly = skipped is not None and skipped != "--skip-sweep"
    return 1 if failed or summary.get("r2_work_blocked") or swept_badly else 0


if __name__ == "__main__":
    # --skip-sweep runs rules 1-2 only. --dry-run runs all three and changes
    # nothing, which is the first look to take before letting any of them delete.
    result = run_cleanup(dry_run_sweep="--skip-sweep" in sys.argv,
                         dry_run="--dry-run" in sys.argv)
    print(f"retention_cleanup: {result}")
    # Non-zero exit on the same rule as the flask command (`exit_code`), so a
    # cron wrapper can alert.
    sys.exit(exit_code(result))
