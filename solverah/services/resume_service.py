"""Resume upload, text extraction, and parsing into profile fields.

The upload is a two-step presigned PUT: the browser asks for a URL, uploads
straight to R2, then tells the API the object key.  Resume bytes never transit
Flask.  Appendix B lists that as behaviour not to refactor away, and the
``ContentLength`` bound into the signature is what makes the declared size
enforced by R2 rather than merely asserted by the client.

Two things here are known to be wrong at scale and are preserved unchanged:

* Parsing runs inline in the request (P0-6).  A large PDF holds a worker for the
  duration.  Part 5.2 turns finalize into ``202 Accepted`` with a job handle, and
  Phase 3 moves the work onto the ``default`` queue.  (This once cited
  ``gunicorn.conf.py``'s 120-second timeout; that dropped to 30 in the Phase 3
  close-out, and under ``gthread`` it never bounded a busy thread anyway --
  :data:`PARSE_TIMEOUT_SECONDS` is what actually bounds a parse.)
* Extraction writes the file to a temp path because pdfminer and python-docx
  both want a filename.  Fine for one worker; it is disk I/O on the request path.

What is *not* preserved is running the parser itself in this process.  Since
SECURITY_AUDIT_2026-09 5.1 and 5.2 the parse happens in a child process under a
hard deadline, and a .docx is measured before it is unzipped: neither of those
bounds can be had in-process on a threaded worker that also has to run on
Windows.  :func:`_extract_out_of_process` and :func:`docx_expansion_refusal`
carry the reasoning; the cost is one interpreter start per parse, which is
noise next to the parse and next to the S3 round trip above it.
"""

from __future__ import annotations

import datetime
import importlib
import importlib.util
import logging
import os
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from packages.ml.resume import parse_resume
from solverah.infra.storage import get_s3_client

__all__ = [
    "MAX_DOCX_RATIO",
    "MAX_DOCX_UNCOMPRESSED_BYTES",
    "MIME_EXTENSIONS",
    "PARSE_TIMEOUT_SECONDS",
    "build_profile_from_resume_key",
    "docx_expansion_refusal",
    "download_url",
    "extract_resume_text",
    "object_key_for_user",
    "presign_upload",
    "snapshot_of",
]

logger = logging.getLogger("solverah.resume_service")

#: How long a presigned URL stays usable.  Ten minutes is long enough for a slow
#: upload on a poor connection and short enough that a leaked URL expires before
#: it is much use.
PRESIGN_TTL_SECONDS = 10 * 60

MIME_EXTENSIONS = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

#: Wall-clock ceiling on one resume parse, enforced by killing the child process.
#:
#: Deliberately generous.  The job is to bound malice, not to hurry a legitimate
#: file: a long scanned PDF taking twenty seconds must still parse, and only the
#: file that will never finish needs stopping.
#:
#: What this does and does not buy, stated plainly.  In Scenario A a parse runs
#: on a request thread either way -- the synchronous finalize does it directly,
#: and with no broker configured ``enqueue`` degrades to eager, so the job path
#: runs it inline too.  Nothing here moves that off the request.  What it
#: changes is the duration: a hostile upload holds one of the twenty-four
#: threads for at most this long instead of until the process is restarted, so
#: saturating the service costs an attacker a sustained request rate rather
#: than a handful of files.
#:
#: Not measured against ``gunicorn.conf.py``'s own ``timeout = 30``, which is
#: the same number and does a different job: under ``gthread`` that timeout
#: catches a worker whose *process* stops heartbeating, not a request thread
#: that is busy (measured, A21).  A parse overrunning this limit is therefore an
#: empty parse, not a killed worker, whichever of the two numbers is larger.
#:
#: Not a config knob.  There is no deployment in which the right answer to a
#: parse that will not terminate differs, and an environment variable here is a
#: way to turn the control off by accident.
PARSE_TIMEOUT_SECONDS = 30

#: Most a .docx may expand to before it is refused unread.  See
#: :func:`docx_expansion_refusal`.
MAX_DOCX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024

#: Most a .docx may expand *by* before it is refused unread.  Real Word output
#: sits an order of magnitude below this; nothing but a bomb reaches it.
MAX_DOCX_RATIO = 500

#: The ratio test is skipped below this much expanded content.  A few kilobytes
#: of XML out of a few hundred bytes is an unremarkable ratio on a file too
#: small to hurt anything, and testing it there would only produce false
#: refusals.
_RATIO_FLOOR_BYTES = 1024 * 1024

#: The script :func:`_extract_out_of_process` runs.  Resolved from this file so
#: it is found regardless of the working directory a worker or a CLI starts in.
_WORKER_PATH = (
    Path(__file__).resolve().parents[1] / "infra" / "resume_extract" / "worker.py"
)


def _module_available(module_name: str) -> bool:
    """Return True if *module_name* can be imported in the current environment."""
    return importlib.util.find_spec(module_name) is not None


def docx_expansion_refusal(file_path: Path) -> Optional[str]:
    """Why this .docx must not be unzipped, or None if it may be.

    SECURITY_AUDIT_2026-09 5.2.  ``docx.Document`` hands the archive to zipfile
    and lxml, which expand it in full; the 10 MB upload cap bounds the archive,
    and XML compresses well past 1000:1, so the bound on what comes *out* has to
    be applied separately.  It is applied here, before the file reaches a
    parser, because that is the only point at which refusing is free.

    Two limits, catching different shapes of the same attack.
    ``MAX_DOCX_UNCOMPRESSED_BYTES`` catches the plain one: a resume that expands
    past tens of megabytes is not a resume.  ``MAX_DOCX_RATIO`` catches the one
    that stays under it -- 60 MB out of a 10 KB upload is inside the absolute
    cap and still nothing a word processor produces.  The ratio sits far above
    what real files reach (a text-heavy ``document.xml`` lands around 10:1 to
    50:1) and applies only above ``_RATIO_FLOOR_BYTES``, so a small archive of
    well-compressed boilerplate cannot trip it.

    The sizes read here are the ones the archive *declares*.  A hostile archive
    may under-declare them, which is why this is the cheap layer and not the
    only one: the subprocess in :func:`extract_resume_text` -- its deadline, and
    the address-space cap the worker sets on itself -- is what holds when the
    declaration lies.

    Returns:
        A short reason for the log, or None when the file is within limits.
    """
    try:
        with zipfile.ZipFile(file_path) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        # A .docx that is not a zip at all. Refused here rather than left for
        # python-docx so that "unreadable" and "hostile" leave by the same door.
        return "not a readable zip archive (%s)" % type(exc).__name__

    uncompressed = sum(entry.file_size for entry in entries)
    compressed = sum(entry.compress_size for entry in entries)

    if uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
        return "declared uncompressed size %d exceeds %d" % (
            uncompressed,
            MAX_DOCX_UNCOMPRESSED_BYTES,
        )

    if uncompressed >= _RATIO_FLOOR_BYTES and compressed > 0:
        ratio = uncompressed / compressed
        if ratio > MAX_DOCX_RATIO:
            return "compression ratio %.0f:1 exceeds %d:1" % (ratio, MAX_DOCX_RATIO)

    return None


def _extract_out_of_process(file_path: Path, mime: str) -> str:
    """Run the worker over *file_path* under a hard deadline; "" if it overruns.

    SECURITY_AUDIT_2026-09 5.1: the parse is unbounded work on a stranger's
    file, and in production it runs inline on a gunicorn ``gthread`` thread with
    no queue behind it, so "unbounded" means one upload holding one of the
    twenty-four threads this service has.

    The deadline is enforced by killing a child process rather than by
    interrupting this one.  ``signal.alarm`` is not an option, and not a close
    call: it is delivered to the main thread and this code is not on it, and it
    does not exist on Windows where the same function runs during development.
    ``subprocess.run(timeout=...)`` kills on expiry from whichever thread is
    waiting, on both platforms, and brings two properties a timeout alone would
    not -- a parser that dies takes only the child with it, and the child caps
    its own address space (see the worker) so a memory blowup cannot outrun the
    clock.

    Failure of any kind returns "", the same answer this module has always given
    for a file it could not read: the caller merges an empty parse and the user
    sees the upload succeed with nothing filled in.  A timeout is therefore not
    a new outcome for callers to handle, only a new way to reach an old one.
    """
    if not sys.executable:
        # An embedded interpreter has nothing to re-launch. Extracting nothing
        # beats falling back to an unbounded in-process parse.
        logger.error(
            "resume_extract_no_interpreter",
            extra={"event": "resume_extract_no_interpreter"},
        )
        return ""

    output_handle = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    output_path = Path(output_handle.name)
    output_handle.close()

    try:
        completed = subprocess.run(
            [sys.executable, str(_WORKER_PATH), mime, str(file_path), str(output_path)],
            capture_output=True,
            timeout=PARSE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # `run` has already killed the child and reaped it.
        logger.warning(
            "resume_extract_timeout",
            extra={
                "event": "resume_extract_timeout",
                "mime": mime,
                "timeout_seconds": PARSE_TIMEOUT_SECONDS,
            },
        )
        return ""
    except OSError as exc:
        logger.error(
            "resume_extract_spawn_failed",
            extra={"event": "resume_extract_spawn_failed", "error": str(exc)},
        )
        return ""
    else:
        if completed.returncode != 0:
            # Covers the address-space cap firing, which arrives as a
            # MemoryError traceback rather than as a distinguishable status.
            logger.warning(
                "resume_extract_failed",
                extra={
                    "event": "resume_extract_failed",
                    "mime": mime,
                    "returncode": completed.returncode,
                    "stderr": completed.stderr.decode("utf-8", "replace")[-2000:],
                },
            )
            return ""
        return output_path.read_text(encoding="utf-8", errors="replace")
    finally:
        if output_path.exists():
            output_path.unlink()


def extract_resume_text(file_path: Path, mime: str) -> str:
    """Extract plain text from a local resume file.

    Supports PDF (via pdfminer.six) and DOCX (via python-docx).  Returns an
    empty string if the required library is not installed, the MIME type is
    unsupported, the file is refused by :func:`docx_expansion_refusal`, or the
    parse does not finish inside :data:`PARSE_TIMEOUT_SECONDS` -- allowing
    callers to degrade gracefully.

    The parse itself happens in a child process; see
    :func:`_extract_out_of_process` for why that is the only bound available to
    a threaded worker that also has to run on Windows.

    Args:
        file_path: Path to the locally written temp file.
        mime:      MIME type string (e.g. ``"application/pdf"``).

    Returns:
        Extracted text as a single string, or ``""`` on failure.
    """
    if mime == "application/pdf":
        if not _module_available("pdfminer.high_level"):
            return ""
        return _extract_out_of_process(file_path, mime)

    if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        if not _module_available("docx"):
            return ""
        refusal = docx_expansion_refusal(file_path)
        if refusal is not None:
            logger.warning(
                "resume_docx_refused",
                extra={"event": "resume_docx_refused", "reason": refusal},
            )
            return ""
        return _extract_out_of_process(file_path, mime)

    return ""


def object_key_for_user(user_id: int, mime: str) -> str:
    """Return the R2 key a user's resume upload must land on.

    Scoped to ``profile/{user_id}/{uuid}/resume.{ext}`` so one user cannot
    overwrite another's file.  The finalize step re-checks the ``profile/{id}/``
    prefix against the caller, so a client that invents a key for someone else's
    id is rejected there rather than trusted here.
    """
    ext = MIME_EXTENSIONS.get(mime, "bin")
    return "profile/%s/%s/resume.%s" % (user_id, uuid.uuid4(), ext)


def presign_upload(object_key: str, mime: str, size: int) -> str:
    """Return a presigned PUT URL bound to *mime* and *size*.

    ``ContentLength`` is signed for the same reason as the intake presign: it
    makes the declared size binding rather than advisory.  Without it a client
    can declare 1 KB, get a URL, and upload a gigabyte.
    """
    return get_s3_client().generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": os.environ["S3_BUCKET_NAME"],
            "Key": object_key,
            "ContentType": mime,
            "ContentLength": size,
        },
        ExpiresIn=PRESIGN_TTL_SECONDS,
        HttpMethod="PUT",
    )


def download_url(resume_key: str) -> str:
    """Return a short-lived presigned GET URL for a stored resume."""
    return get_s3_client().generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": os.environ["S3_BUCKET_NAME"],
            "Key": resume_key,
        },
        ExpiresIn=PRESIGN_TTL_SECONDS,
    )


def _fetch_text(resume_key: str, resume_mime: str) -> str:
    """Download an object and extract its text, or return "" on any failure.

    Broad by design: a resume that cannot be read should leave the user with an
    empty parse to fill in by hand, not a 500 on an upload that succeeded.
    """
    temp_path = None
    try:
        s3 = get_s3_client()
        bucket = os.environ["S3_BUCKET_NAME"]
        obj = s3.get_object(Bucket=bucket, Key=resume_key)
        raw_bytes = obj["Body"].read()

        suffix = Path(resume_key).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(raw_bytes)
            temp_path = Path(tmp_file.name)

        return extract_resume_text(temp_path, resume_mime)
    except Exception:  # noqa: BLE001 -- see docstring
        return ""
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def build_profile_from_resume_key(
    resume_key: str,
    resume_mime: str,
    resume_size_bytes: int,
    resume_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse a resume stored in S3 and return profile field updates.

    Used by the authenticated resume-upload flow (``/profile/resume/finalize``)
    where the user is already registered.  Returns only the fields that can be
    derived from the resume (experience, education, skills, uploadedResume,
    resumeKey); callers merge this into the existing ``profile_data``.

    Args:
        resume_key:        S3/R2 object key for the uploaded resume.
        resume_mime:       MIME type of the file.
        resume_size_bytes: File size in bytes (stored in the profile metadata).
        resume_name:       Original filename shown in the UI; falls back to the
                           key's basename if not provided.

    Returns:
        Partial profile dict with keys:
        ``experience``, ``education``, ``skills``, ``uploadedResume``, ``resumeKey``.
    """
    resume_text = _fetch_text(resume_key, resume_mime)
    parsed = parse_resume(resume_text) if resume_text else {}
    if not isinstance(parsed, dict):
        parsed = {}

    experience_entries = []
    for idx, exp in enumerate(parsed.get("experience", [])):
        bullets = exp.get("impact_bullets") or []
        description = "\n".join("- %s" % bullet for bullet in bullets) if bullets else ""
        experience_entries.append(
            {
                "id": idx + 1,
                "company": exp.get("company", ""),
                "position": exp.get("title", ""),
                "startDate": "",
                "endDate": exp.get("duration", ""),
                "description": description,
            }
        )

    education_entries = _education_entries(parsed)

    skills = parsed.get("skills", [])
    if isinstance(skills, str):
        skills = [skills]
    skills = [skill for skill in skills if skill]

    filename = resume_name or Path(resume_key).name

    return {
        "experience": experience_entries,
        "education": education_entries,
        "skills": skills,
        "uploadedResume": {
            "name": filename,
            "size": resume_size_bytes,
            "type": resume_mime,
        },
        "resumeKey": resume_key,
    }


def _education_entries(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise the parser's education output into UI rows.

    The parser emits ``education_entries`` (structured) when it can and a plain
    ``education`` string when it cannot.  Both are handled, and the structured
    form wins -- the fallback puts the whole line in ``degree`` with an empty
    institution, which is worse data but better than dropping it.
    """
    structured = parsed.get("education_entries")
    entries: List[Dict[str, Any]] = []

    if isinstance(structured, list) and structured:
        for idx, entry in enumerate(structured):
            if not isinstance(entry, dict):
                continue
            entries.append(
                {
                    "id": idx + 1,
                    "institution": entry.get("institution", ""),
                    "degree": entry.get("degree", ""),
                    "startDate": entry.get("startDate", ""),
                    "endDate": entry.get("endDate", ""),
                    "gpa": entry.get("gpa", ""),
                    "description": "",
                }
            )
        return entries

    education_raw = parsed.get("education", "")
    lines = [item.strip() for item in str(education_raw).splitlines() if item.strip()]
    for idx, line in enumerate(lines):
        entries.append(
            {
                "id": idx + 1,
                "institution": "",
                "degree": line,
                "startDate": "",
                "endDate": "",
                "gpa": "",
                "description": "",
            }
        )
    return entries


def snapshot_of(object_key: str, profile_updates: Dict[str, Any]) -> Dict[str, Any]:
    """The ``_parsedResumeSnapshot`` recorded alongside a finalize.

    Stored so later user edits can be diffed against what the parser originally
    produced -- see :func:`solverah.domain.profile.resume_field_corrections`.
    That diff is the product's parser-improvement training data, which is why the
    snapshot is written even though nothing reads it on the happy path.
    """
    return {
        "resumeKey": object_key,
        "parsedAt": datetime.datetime.utcnow().isoformat(),
        "experience": profile_updates.get("experience", []),
        "education": profile_updates.get("education", []),
        "skills": profile_updates.get("skills", []),
    }


def build_profile_from_intake(intake) -> Dict[str, Any]:
    """Build a full ``profile_data`` dict from an ``IntakeSubmission`` record.

    Downloads the resume from S3, extracts text, runs the rule-based parser,
    then maps the parsed output to the profile schema expected by the frontend.
    Any step can fail silently -- the user still gets a profile seeded with their
    intake contact details even if the resume parse yields nothing.

    This is the anonymous-intake twin of :func:`build_profile_from_resume_key`.
    They share the parse pipeline and differ in what they seed around it: this
    one starts from a blank profile and fills in the contact details the intake
    form collected, where the other returns only the resume-derived keys for the
    caller to merge over an existing profile.

    Args:
        intake: An ``IntakeSubmission`` ORM instance (must have ``resume_key``
                and ``resume_mime`` populated).

    Returns:
        Dict matching the ``ProfileFormData`` shape used by the frontend.
    """
    from solverah.domain.auth import default_profile

    parsed_fields = build_profile_from_resume_key(
        resume_key=intake.resume_key,
        resume_mime=intake.resume_mime,
        resume_size_bytes=intake.resume_size_bytes,
        resume_name=Path(intake.resume_key).name,
    )

    profile = default_profile(
        email=intake.email,
        name=("%s %s" % (intake.first_name, intake.last_name)).strip(),
    )
    profile.update(
        {
            "firstName": intake.first_name,
            "lastName": intake.last_name,
            "email": intake.email,
            "phone": intake.phone or "",
            "location": intake.state or "",
            "primaryLocation": intake.state or "",
            "linkedinUrl": intake.linkedin_url or "",
            "experience": parsed_fields["experience"],
            "education": parsed_fields["education"],
            "skills": parsed_fields["skills"],
            "uploadedResume": parsed_fields["uploadedResume"],
            "resumeKey": intake.resume_key,
        }
    )
    return profile
