"""Import pilot-form responses into a LOCAL research database, through the app's own doorways.

    SOLVERAH_IGNORE_DOTENV=1 FLASK_SKIP_DOTENV=1 APP_ENV=development \\
    DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah_pilot \\
    python -m causal_graph.v1_model.pilot_form.import_responses responses.csv

THE GUARD
---------
`devfit.guard` with PILOT_DB_PREFIX, before any connection: the host must be localhost or
127.0.0.1, the database name must start with `solverah_pilot`, APP_ENV must not be
production, and the URL may carry no query parameter that redirects the driver. No --force.
The repo's .env holds the PRODUCTION database URL; this script never reads it (it sets
SOLVERAH_IGNORE_DOTENV=1 itself before the app is imported, and the URL must be given).

THE DOORWAYS (the devfit seeder is the model; nothing here writes a table directly)
-----------------------------------------------------------------------------------
    user            the ORM User, email `pilot-<pilot_id>@pilotform.solverah.invalid`, with
                    a password hash no password matches (it cannot sign in)
    career status   profile_repository.update_document -- what PATCH /me/career-status uses
    core sitting    assessment_store.persist_submission with a ScoredSubmission built the
                    way assessment_form.submit_form builds one
    job reports     situation_report_service.submit_environment_report -- the POST
                    /me/environment-report service itself: same validation, same scoring,
                    same career-status snapshot, same first_job refusal, same one-past-
                    report rule, same FORM_VERSION stamp

so a pilot row differs from an app row only in the email domain, which is what
`assemble_training_data` turns into `respondent_source = 'pilot_form'`.

IDEMPOTENT. A respondent whose pilot email already exists is skipped as already imported,
so the same CSV (or a later export containing the same rows) can be imported any number of
times. Each respondent is one transaction up to their current-job report; a failure rolls
that respondent back and the summary says why.

RESPONDENT EMAILS never reach the database, the repo or the console. Where a respondent left
one, it is written to --emails-out (default: Desktop/solverah-pilot/emails.csv, OUTSIDE the
repo; a path inside the repo is refused), keyed by pilot id.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from . import DEFAULT_PRIVATE_DIR, REPO_ROOT
from .responses import MappingMismatch, ParsedResponse, load_mapping, read_csv

from ..devfit.guard import PILOT_DB_PREFIX, require_database_url

import assemble_training_data as _atd  # noqa: E402  -- via MODEL_DIR on sys.path

PILOT_FORM_EMAIL_DOMAIN = _atd.PILOT_FORM_EMAIL_DOMAIN

DEFAULT_EMAILS_PATH = Path(DEFAULT_PRIVATE_DIR) / "emails.csv"

EMAILS_HEADER = ("pilot_id", "email")


def pilot_email(pilot_id: str) -> str:
    """The user email a pilot respondent is stored under. RFC 2606 `.invalid`: it can
    never resolve, so nothing can ever be mailed to it, and no real person can register
    it -- which is what makes the domain a trustworthy provenance label."""
    if not pilot_id or not pilot_id.isalnum():
        raise ValueError("pilot id must be non-empty and alphanumeric")
    return "pilot-%s%s" % (pilot_id.lower(), PILOT_FORM_EMAIL_DOMAIN)


@dataclass
class ImportSummary:
    rows: int = 0
    imported: int = 0
    already_imported: int = 0
    current_reports: int = 0
    past_reports: int = 0
    first_job: int = 0
    emails_recorded: int = 0
    skipped: list = field(default_factory=list)   # (row_number, pilot_id, reason)
    notes: list = field(default_factory=list)     # (row_number, pilot_id, note)
    failed: list = field(default_factory=list)    # (row_number, pilot_id, error)
    #: pilot ids now present in the database (imported now or before) -- the only
    #: respondents whose email is worth keeping.
    present: set = field(default_factory=set)

    def lines(self) -> list:
        out = [
            "rows in file:          %d" % self.rows,
            "imported now:          %d" % self.imported,
            "already imported:      %d" % self.already_imported,
            "  current-job reports: %d" % self.current_reports,
            "  past-job reports:    %d" % self.past_reports,
            "  first_job (no report): %d" % self.first_job,
            "skipped:               %d" % len(self.skipped),
            "failed:                %d" % len(self.failed),
            "emails kept (outside the repo, not in the DB): %d" % self.emails_recorded,
        ]
        for title, items in (("SKIPPED", self.skipped), ("FAILED", self.failed),
                             ("NOTES", self.notes)):
            if items:
                out.append("")
                out.append(title)
                for row_number, pilot_id, reason in items:
                    out.append("  row %d  %s  %s" % (row_number, pilot_id, _ascii(reason)))
        return out


def _ascii(text: str) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


# ---------------------------------------------------------------------------
# Version check: the form must have been generated from the banks the app scores with
# ---------------------------------------------------------------------------
def check_bank_versions(mapping: dict) -> None:
    import assessment_form
    from work_pulse import situation_items

    live_core = assessment_form.load_items(Path(assessment_form.DEFAULT_ITEMS_PATH))["form_version"]
    problems = []
    if mapping["core_form_version"] != live_core:
        problems.append("core: form %s, app %s" % (mapping["core_form_version"], live_core))
    if mapping["env_form_version"] != situation_items.FORM_VERSION:
        problems.append("environment: form %s, app %s"
                        % (mapping["env_form_version"], situation_items.FORM_VERSION))
    if problems:
        raise SystemExit(
            "refusing to import: the form was generated from different item banks than the "
            "app now scores with (%s). Answers to one version scored as another is the "
            "silent corruption D-07 forbids." % "; ".join(problems)
        )


# ---------------------------------------------------------------------------
# Writing one respondent
# ---------------------------------------------------------------------------
def scored_submission(choices: dict):
    """A ScoredSubmission for already-resolved {item_id: option_key} choices, derived
    exactly as assessment_form.submit_form derives it after its token step."""
    import assessment_form

    items_index = assessment_form.load_items(Path(assessment_form.DEFAULT_ITEMS_PATH))
    if len(choices) != assessment_form.EXPECTED_RESPONSE_COUNT:
        raise ValueError("expected %d core choices, got %d"
                         % (assessment_form.EXPECTED_RESPONSE_COUNT, len(choices)))
    scores = assessment_form.score_stored_choices(choices)
    errors = assessment_form.error_counts_all_dimensions(choices, items_index)
    return assessment_form.ScoredSubmission(
        form_version=items_index["form_version"],
        scoring_key_version=assessment_form.scoring_key_version(),
        scores=scores,
        choices=dict(choices),
        confidences={
            dim: (None if dim in assessment_form.CONFIDENCE_PENDING_DIMENSIONS
                  else assessment_form.confidence_from_error(e))
            for dim, e in errors.items()
        },
    )


class _Refused(RuntimeError):
    pass


def _submit_job(user, job) -> None:
    from solverah.services import situation_report_service

    result = situation_report_service.submit_environment_report(user, job.payload())
    if not result.ok:
        raise _Refused("%s report refused: %s" % (job.subject, result.body.get("error")))


def import_one(db, response: ParsedResponse, summary: ImportSummary) -> None:
    """Write one parsed respondent. Owns its transactions; never raises."""
    import assessment_store
    from model import User
    from solverah.repositories import profile_repository

    from ..devfit.seed_synthetic import UNUSABLE_PASSWORD_HASH

    ref = (response.row_number, response.pilot_id)
    email = pilot_email(response.pilot_id)
    if User.query.filter_by(email=email).first() is not None:
        summary.already_imported += 1
        summary.present.add(response.pilot_id)
        return

    status = response.career_status
    try:
        user = User(email=email, password_hash=UNUSABLE_PASSWORD_HASH)
        db.session.add(user)
        db.session.flush()
        profile_repository.update_document(
            user.id, lambda existing: {**existing, "career_status": status}
        )
        assessment_store.persist_submission(db, user.id, scored_submission(response.core_choices))
        if response.current is not None:
            _submit_job(user, response.current)  # commits user + profile + core + report
        else:
            db.session.commit()
    except Exception as exc:  # noqa: BLE001 -- one respondent must not stop the file
        db.session.rollback()
        summary.failed.append(ref + ("%s: %s" % (type(exc).__name__, exc),))
        return

    summary.imported += 1
    summary.present.add(response.pilot_id)
    if status == "first_job":
        summary.first_job += 1
    if response.current is not None:
        summary.current_reports += 1

    if response.previous is not None:
        try:
            _submit_job(user, response.previous)
            summary.past_reports += 1
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            summary.notes.append(ref + ("past-job report not written: %s" % exc,))

    for note in response.notes:
        summary.notes.append(ref + (note,))


def import_parsed(db, parsed: Iterable[ParsedResponse]) -> ImportSummary:
    summary = ImportSummary()
    for response in parsed:
        summary.rows += 1
        if response.skip_reason is not None:
            summary.skipped.append((response.row_number, response.pilot_id,
                                    response.skip_reason))
            continue
        import_one(db, response, summary)
    return summary


# ---------------------------------------------------------------------------
# Respondent emails: outside the repo, never in the DB, never printed
# ---------------------------------------------------------------------------
def _inside_repo(path: Path) -> bool:
    repo = Path(REPO_ROOT).resolve()
    try:
        Path(path).resolve().relative_to(repo)
        return True
    except ValueError:
        return False


class UnsafeOutputPath(ValueError):
    """A private output (emails, reports) aimed inside the repository."""


def assert_outside_repo(path, what: str) -> Path:
    path = Path(path)
    if _inside_repo(path):
        raise UnsafeOutputPath(
            "refusing to write %s inside the repository (%s). They belong outside it, "
            "under %s." % (what, path, DEFAULT_PRIVATE_DIR)
        )
    return path


def write_emails(path: Path, parsed: Iterable[ParsedResponse],
                 only: Optional[set] = None) -> int:
    """Merge {pilot_id: email} into `path` for respondents in `only` (default: every
    importable one). Returns how many were written. Refuses any path inside the
    repository."""
    path = assert_outside_repo(path, "respondent emails")
    wanted = {
        p.pilot_id: p.email for p in parsed
        if p.email and p.skip_reason is None and (only is None or p.pilot_id in only)
    }
    if not wanted:
        return 0
    existing: dict = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                existing[row["pilot_id"]] = row["email"]
    existing.update(wanted)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(EMAILS_HEADER)
        for pilot_id in sorted(existing):
            writer.writerow((pilot_id, existing[pilot_id]))
    return len(wanted)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def open_app(url: str):
    """Point the app at the guarded URL and return (app, db). SOLVERAH_IGNORE_DOTENV is
    forced on BEFORE app.py is imported, so the repo's .env (production URL) is never
    loaded, whatever the shell says."""
    os.environ["SOLVERAH_IGNORE_DOTENV"] = "1"
    os.environ["DATABASE_URL"] = url
    from app import app
    from model import db

    return app, db


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Import pilot-form responses into a local solverah_pilot* database."
    )
    parser.add_argument("csv_path", help="the response CSV exported from the form's Sheet")
    parser.add_argument("--database-url", default=None,
                        help="postgresql://... for a LOCAL solverah_pilot* database; falls "
                             "back to $DATABASE_URL. Refused unless host is local, the name "
                             "starts with %r and APP_ENV is not production." % PILOT_DB_PREFIX)
    parser.add_argument("--emails-out", default=str(DEFAULT_EMAILS_PATH),
                        help="where respondent emails go (outside the repo). Default %s"
                             % DEFAULT_EMAILS_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="parse and report only; no database, no email file")
    args = parser.parse_args(argv)

    url: Optional[str] = None
    if not args.dry_run:
        url = require_database_url(args.database_url, prefix=PILOT_DB_PREFIX)

    mapping = load_mapping()
    check_bank_versions(mapping)
    try:
        parsed = read_csv(args.csv_path)
    except MappingMismatch as exc:
        print("REFUSED: %s" % _ascii(exc))
        return 2

    if args.dry_run:
        summary = ImportSummary()
        for response in parsed:
            summary.rows += 1
            ref = (response.row_number, response.pilot_id)
            if response.skip_reason:
                summary.skipped.append(ref + (response.skip_reason,))
                continue
            summary.notes.extend(ref + (n,) for n in response.notes)
        print("DRY RUN -- nothing written")
        print("\n".join(summary.lines()))
        return 0

    app, db = open_app(url)
    with app.app_context():
        summary = import_parsed(db, parsed)
    summary.emails_recorded = write_emails(Path(args.emails_out), parsed, summary.present)

    print("imported into %s" % url.rsplit("/", 1)[-1])
    print("\n".join(summary.lines()))
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
