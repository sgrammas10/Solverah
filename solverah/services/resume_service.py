"""Resume upload, text extraction, and parsing into profile fields.

The upload is a two-step presigned PUT: the browser asks for a URL, uploads
straight to R2, then tells the API the object key.  Resume bytes never transit
Flask.  Appendix B lists that as behaviour not to refactor away, and the
``ContentLength`` bound into the signature is what makes the declared size
enforced by R2 rather than merely asserted by the client.

Two things here are known to be wrong at scale and are preserved unchanged:

* Parsing runs inline in the request (P0-6).  A large PDF holds a worker for the
  duration, which is part of why ``gunicorn.conf.py`` carries a 120-second
  timeout.  Part 5.2 turns finalize into ``202 Accepted`` with a job handle, and
  Phase 3 moves the work onto the ``default`` queue.
* Extraction writes the file to a temp path because pdfminer and python-docx
  both want a filename.  Fine for one worker; it is disk I/O on the request path.
"""

from __future__ import annotations

import datetime
import importlib
import importlib.util
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from packages.ml.resume import parse_resume
from solverah.infra.storage import get_s3_client

__all__ = [
    "MIME_EXTENSIONS",
    "build_profile_from_resume_key",
    "download_url",
    "extract_resume_text",
    "object_key_for_user",
    "presign_upload",
    "snapshot_of",
]

#: How long a presigned URL stays usable.  Ten minutes is long enough for a slow
#: upload on a poor connection and short enough that a leaked URL expires before
#: it is much use.
PRESIGN_TTL_SECONDS = 10 * 60

MIME_EXTENSIONS = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _module_available(module_name: str) -> bool:
    """Return True if *module_name* can be imported in the current environment."""
    return importlib.util.find_spec(module_name) is not None


def extract_resume_text(file_path: Path, mime: str) -> str:
    """Extract plain text from a local resume file.

    Supports PDF (via pdfminer.six) and DOCX (via python-docx).  Returns an
    empty string if the required library is not installed or the MIME type is
    unsupported, allowing callers to degrade gracefully.

    Args:
        file_path: Path to the locally written temp file.
        mime:      MIME type string (e.g. ``"application/pdf"``).

    Returns:
        Extracted text as a single string, or ``""`` on failure.
    """
    if mime == "application/pdf":
        if not _module_available("pdfminer.high_level"):
            return ""
        extract_text = importlib.import_module("pdfminer.high_level").extract_text
        return extract_text(str(file_path)) or ""

    if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        if not _module_available("docx"):
            return ""
        docx = importlib.import_module("docx")
        doc = docx.Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text).strip()

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
