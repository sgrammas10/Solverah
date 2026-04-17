"""Solverah Flask application — main API server.

This module is the single entry-point for the backend API.  It wires together:

  * Authentication: JWT (HttpOnly cookies) + CSRF protection, bcrypt password
    hashing, email confirmation (6-digit OTP via Resend), and account lockout
    after repeated failed logins.
  * User profiles: CRUD over a flexible JSON column (``User.profile_data``) with
    server-side field whitelisting.  Resume uploads flow through a two-step
    presigned-PUT / finalize pattern against Cloudflare R2 (S3-compatible).
  * Resume parsing: Deterministic, offline rule-based parser
    (``job_descr_LLM/user_input_pipeline/resume_parser.py``) runs on finalization
    to pre-populate experience / education / skills.  User edits are tracked in
    ``ResumeParseCorrection`` for future parser improvement.
  * Quiz insights: OpenAI GPT-4o-mini generates personalized career insights from
    structured quiz answers.  Results are persisted in ``profile_data.quizInsights``.
  * Early-access intake: Two-step flow (presign → finalize) stores pre-launch
    submissions with uploaded resumes.  Optionally converts to a registered
    account via ``/api/intake/create-account`` or ``/api/intake/sign-in``.
  * Job recommendations: SentenceTransformer-based ML pipeline (gated behind
    ``ML_ENABLED`` env flag; disabled in demo mode).

Key environment variables (required unless otherwise noted):
    DATABASE_URL        — PostgreSQL connection string.
    JWT_SECRET_KEY      — Secret key for signing JWTs.
    S3_ENDPOINT_URL     — Cloudflare R2 (or any S3-compatible) endpoint.
    S3_ACCESS_KEY_ID    — R2 access key.
    S3_SECRET_ACCESS_KEY — R2 secret key.
    S3_BUCKET_NAME      — Target bucket for resume uploads.
    OPENAI_API_KEY      — Required for quiz-insight generation.
    RESEND_API_KEY      — Required for transactional emails.
    EMAIL_FROM          — Sender address (defaults to no-reply@solverah.com).
    FLASK_ENV / APP_ENV / ENV — Set to "production" to enable HTTPS-only cookies
                                and HSTS headers.
    ML_ENABLED          — "1" to enable the SentenceTransformer recommendation
                          pipeline (requires LLM module).
    DEMO_MODE           — "1" to return empty recommendations without hitting ML.
    MAX_LOGIN_ATTEMPTS  — Failed attempts before lockout (default 5).
    LOGIN_LOCKOUT_MINUTES — Lockout duration in minutes (default 15).
"""

from flask import Flask, jsonify, request
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
    set_access_cookies,
    unset_jwt_cookies,
    get_csrf_token,
)
from flask_talisman import Talisman

import os
import json
import uuid
import random
import datetime
import re
import importlib
import importlib.util
import sys
import tempfile
import traceback
from pathlib import Path
from urllib.parse import urlparse
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

from dotenv import load_dotenv
load_dotenv()
try:
    from openai import OpenAI
except Exception:
    OpenAI = None


JOB_LLM_DIR = Path(__file__).resolve().parent / "job_descr_LLM"

def _load_resume_parser():
    """Dynamically load ``parse_resume`` from the job_descr_LLM sub-package.

    The resume parser lives in a sibling directory that is not on sys.path, so
    we use importlib to load it at startup rather than a top-level import.  This
    avoids circular-import issues and keeps the ML/parsing module decoupled from
    the Flask layer.

    Returns:
        The ``parse_resume(text: str) -> dict`` callable.

    Raises:
        FileNotFoundError: If resume_parser.py is missing from the expected path.
        ImportError: If the module spec cannot be constructed.
    """
    parser_path = JOB_LLM_DIR / "user_input_pipeline" / "resume_parser.py"
    if not parser_path.exists():
        raise FileNotFoundError("resume_parser.py not found in job_descr_LLM/user_input_pipeline")
    spec = importlib.util.spec_from_file_location("resume_parser", parser_path)
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load resume_parser module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_resume

parse_resume = _load_resume_parser()

ALLOWED_MIME = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_BYTES = 10 * 1024 * 1024  # 10MB

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^[0-9+().\-\s]{7,25}$")
LINKEDIN_ALLOWED_HOSTS = {
    "linkedin.com",
    "www.linkedin.com",
}

def _normalize_whitespace(value: str) -> str:
    """Collapse runs of whitespace in *value* to a single space and strip ends."""
    return " ".join(value.split())


def _is_valid_email(email: str) -> bool:
    """Return True if *email* matches a basic ``local@domain.tld`` pattern."""
    return bool(EMAIL_PATTERN.match(email))


def _is_valid_phone(phone: str) -> bool:
    """Return True if *phone* contains 7–25 digit/punctuation characters."""
    return bool(PHONE_PATTERN.match(phone))


def _is_valid_https_url(value: str) -> bool:
    """Return True if *value* is an HTTPS URL with a non-empty host."""
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _is_valid_linkedin_url(value: str) -> bool:
    """Return True if *value* is an HTTPS LinkedIn URL (linkedin.com or www.linkedin.com)."""
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.netloc in LINKEDIN_ALLOWED_HOSTS

#from LLM.profile2model import sorted_mlscores

from flask_migrate import Migrate

from model import AuditLog, IntakeSubmission, JobRecommendation, ResumeParseCorrection, User, db
from datetime import timedelta
import pandas as pd

#from LLM.profile2model import jobs_path

# from geo_utils import geocode_city, haversine_miles


app = Flask(__name__)
from security import init_rate_limiter
from validators import validate_password, clean_profile_data

from flask_cors import CORS


def _is_production() -> bool:
    """Return True if any of the standard environment indicators say 'production'.

    Checks FLASK_ENV, APP_ENV, and ENV in that order.  Used to gate HTTPS-only
    cookies, HSTS headers, and Talisman's ``force_https`` flag.
    """
    env_name = (
        os.environ.get("FLASK_ENV")
        or os.environ.get("APP_ENV")
        or os.environ.get("ENV")
        or ""
    )
    return env_name.lower() in {"production", "prod"}


def _parse_bool_env(value, default: bool) -> bool:
    """Coerce an environment-variable string to bool.

    Args:
        value:   Raw string from ``os.environ.get(...)`` (may be None).
        default: Fallback value when *value* is None.

    Returns:
        True for '1', 'true', 'yes', 'y', 'on' (case-insensitive); False
        for everything else; *default* if *value* is None.
    """
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


is_production = _is_production()

# Security headers with Talisman for CSP
Talisman(
    app,
    content_security_policy={
        "default-src": ["'self'", "https://fonts.gstatic.com", "https://fonts.googleapis.com"],
    },
    force_https=is_production,
    strict_transport_security=is_production,
    strict_transport_security_max_age=31536000 if is_production else None,
    strict_transport_security_include_subdomains=is_production,
    strict_transport_security_preload=is_production,
)


# update to the one above when domain is ready
CORS(
    app,
    resources={r"/api/*": {
        "origins": [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://solverah.vercel.app",
            "https://solverah.com",
            "https://www.solverah.com",
            r"^https://.*\.vercel\.app$",
        ],
        # "allow_origin_regex": r"^https://.*\.vercel\.app$",
    }},
    supports_credentials=True,
    allow_headers=["Content-Type", "X-CSRF-TOKEN"],
)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


#Configuring secret keys for JWTs
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")
if not app.config["JWT_SECRET_KEY"]:
    raise RuntimeError("JWT_SECRET_KEY is not set")
app.config["JWT_ACCESS_TOKEN_EXPIRES"]= timedelta(hours=1) #token expires in 1 hours

# Tell JWTs to live in cookies instead of headers
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]

# In dev (http://localhost), this must be False; in prod over HTTPS set to True



app.config["JWT_COOKIE_SECURE"] = _parse_bool_env(
    os.environ.get("JWT_COOKIE_SECURE"),
    default=is_production,
)

# If frontend and backend are on same origin, "Lax" is fine; if cross-site + HTTPS, use "None"
app.config["JWT_COOKIE_SAMESITE"] = os.environ.get(
    "JWT_COOKIE_SAMESITE",
    "None" if is_production else "Lax",
)

# CSRF protection on state-changing methods
app.config["JWT_COOKIE_CSRF_PROTECT"] = True
app.config["JWT_CSRF_METHODS"] = ["POST", "PUT", "PATCH", "DELETE"]
app.config["JWT_CSRF_HEADER_NAME"] = "X-CSRF-TOKEN"


db.init_app(app)
migrate = Migrate(app, db)


bcrypt = Bcrypt(app)
jwt = JWTManager(app)

limiter = init_rate_limiter(app)


@app.post("/api/early-access-request")
def early_access_request():
    """POST /api/early-access-request — Early-access interest form (no resume).

    Accepts a lightweight JSON body from the landing-page modal and forwards the
    details to info@solverah.com via Resend.  Does not persist to the database.

    Body (JSON):
        firstName, lastName, email (required)
        phone, preferredContact, careerJourney (optional)

    Returns:
        200 {"ok": true}
        400 if required fields are missing
        500 if the notification email fails to send
    """
    data = request.get_json(silent=True) or {}
    first_name = (data.get("firstName") or "").strip()
    last_name = (data.get("lastName") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    preferred_contact = (data.get("preferredContact") or "").strip()
    career_journey = (data.get("careerJourney") or "").strip()

    # Basic validation
    if not first_name or not last_name or not email:
        return jsonify({"error": "First name, last name, and email are required."}), 400

    # Send notification email to info@solverah.com
    try:
        from email_utils import send_early_access_modal_notification
        send_early_access_modal_notification(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            preferred_contact=preferred_contact,
            career_journey=career_journey,
        )
    except Exception as e:
        app.logger.error(f"Failed to send early access modal notification: {e}")
        return jsonify({"error": "Failed to send notification."}), 500
    return jsonify({"ok": True})


MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))

def get_db_conn():
    """Open a raw psycopg2 connection returning rows as dicts.

    Used in endpoints that bypass SQLAlchemy for bulk INSERT performance or
    direct SQL control.  Callers are responsible for calling ``conn.close()``.
    """
    return psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)


def get_s3_client():
    """Return a boto3 S3 client configured for Cloudflare R2.

    R2 is S3-compatible, so the same boto3 API works with a custom endpoint URL.
    Credentials and endpoint are sourced from environment variables:
        S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_REGION.
    """
    # Cloudflare R2 is S3-compatible; endpoint_url overrides the default AWS endpoint
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("S3_REGION", "auto"),
    )


def _module_available(module_name: str) -> bool:
    """Return True if *module_name* can be imported in the current environment."""
    return importlib.util.find_spec(module_name) is not None


def _get_openai_client():
    """Build and return an OpenAI client with standard retry/timeout settings.

    Uses a 60-second timeout and 2 automatic retries to handle transient
    API errors without hanging the request indefinitely.

    Raises:
        RuntimeError: If the ``openai`` package is not installed or
                      OPENAI_API_KEY is missing from the environment.
    """
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK not installed")
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key, timeout=60.0, max_retries=2)


def _build_quiz_insight_prompt(quiz_group: str, quizzes: list[dict]) -> list[dict]:
    """Construct the system + user messages for the quiz-insight OpenAI call.

    The prompt instructs the model to:
      - Return strictly valid JSON (no markdown or extra text).
      - Produce exactly one insight per quiz in input order.
      - Use each quiz's ``key`` field verbatim in its response.

    Args:
        quiz_group: Logical group label (e.g. ``"careerQuizzes"``).
        quizzes:    List of normalized quiz dicts, each with ``key``, ``title``,
                    and ``items`` (list of ``{question, selected}``).

    Returns:
        A two-element list of OpenAI chat message dicts:
        ``[{"role": "system", ...}, {"role": "user", ...}]``.
    """
    quiz_keys = [q.get("key", f"quiz_{i}") for i, q in enumerate(quizzes)]
    system = (
        "You are an expert career insights engine designed to analyze structured quiz responses "
        "and extract meaningful career-related patterns.\n\n"

        "PRIMARY OBJECTIVE:\n"
        "Generate one distinct, personalized insight for EACH quiz provided. "
        "Each insight must be specific to that quiz's answers — do not merge or combine quizzes.\n\n"

        "STRICT RULES:\n"
        "- Output VALID JSON only. Do not include markdown, commentary, or extra text.\n"
        "- The 'insights' array MUST contain exactly one entry per quiz, in the same order as the input.\n"
        "- Each insight's 'key' MUST exactly match the corresponding quiz's 'key' field.\n"
        "- Do NOT invent traits, preferences, or experiences not supported by the input.\n"
        "- Do NOT provide medical, psychological, or legal advice.\n"
        "- Avoid generic career advice that could apply to anyone.\n"
        "- Maintain a professional, supportive, and non-judgmental tone.\n"
        "- Be concise but information-dense.\n"

        "INSIGHT QUALITY GUIDELINES:\n"
        "- Each insight should reveal something specific to that quiz's answers.\n"
        "- Prefer specificity over broad statements.\n"
        "- Recommendations must be practical and immediately actionable.\n"
        f"- You will receive {len(quizzes)} quiz(zes). Return exactly {len(quizzes)} insight(s).\n"
        f"- Expected keys in order: {quiz_keys}\n"
    )
    user_payload = {
        "quiz_group": quiz_group,
        "quizzes": quizzes,
        "output_rules": {
            "tone": "clear, supportive, non-judgmental",
            "length": "short but meaningful",
            "key_takeaways_count": "3-5",
            "next_steps_count": "2-4",
            "insights_count": len(quizzes),
        },
        "output_format": {
            "overallInsight": {
                "summary": "string — synthesis across ALL quizzes combined",
                "keyTakeaways": ["string — cross-quiz pattern or theme"],
                "nextSteps": ["string — actionable step informed by all quizzes"],
            },
            "insights": [
                {
                    "key": "must match the quiz key exactly",
                    "title": "string — name of this specific quiz",
                    "summary": "string — insight specific to this quiz only",
                    "keyTakeaways": ["string"],
                    "combinedMeaning": "string",
                    "nextSteps": ["string"],
                },
                {
                    "key": "next quiz key",
                    "title": "string",
                    "summary": "string",
                    "keyTakeaways": ["string"],
                    "combinedMeaning": "string",
                    "nextSteps": ["string"],
                },
            ],
        },
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload)},
    ]


def _coerce_insight_payload(payload: dict, quiz_group: str, fallback_quizzes: list[dict]) -> dict:
    """Normalise the raw JSON returned by the OpenAI insight call.

    The model occasionally returns a single insight dict instead of a list, or
    omits the ``key`` field.  This function defensively coerces the payload to a
    canonical structure so the rest of the endpoint doesn't need to handle every
    malformed variant.

    Args:
        payload:          Parsed JSON dict from the OpenAI response.
        quiz_group:       Used to generate a fallback key if none is present.
        fallback_quizzes: The original quiz list — used to recover ``key`` values
                          when the model forgets to echo them back.

    Returns:
        Dict with ``{"overallInsight": ..., "insights": [...]}``, or ``{}`` if
        the payload cannot be salvaged.
    """
    if not isinstance(payload, dict):
        return {}
    insights = payload.get("insights")
    raw_overall = payload.get("overallInsight")
    overall_insight = raw_overall if isinstance(raw_overall, dict) else None

    if isinstance(insights, dict):
        insights = [insights]

    if not isinstance(insights, list):
        return {}

    normalized = []
    for idx, item in enumerate(insights):
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not key and fallback_quizzes and idx < len(fallback_quizzes):
            key = fallback_quizzes[idx].get("key")
        normalized.append(
            {
                "key": key or f"{quiz_group}-{idx+1}",
                "title": item.get("title"),
                "summary": item.get("summary"),
                "keyTakeaways": item.get("keyTakeaways"),
                "combinedMeaning": item.get("combinedMeaning"),
                "nextSteps": item.get("nextSteps"),
            }
        )

    if not normalized:
        return {}

    return {"overallInsight": overall_insight, "insights": normalized}


def _extract_resume_text(file_path: Path, mime: str) -> str:
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


def _build_profile_from_intake(intake: IntakeSubmission) -> dict:
    """Build a full ``profile_data`` dict from an ``IntakeSubmission`` record.

    Downloads the resume from S3, extracts text, runs the rule-based parser,
    then maps the parsed output to the profile schema expected by the frontend.
    Any step can fail silently — the user still gets a profile seeded with their
    intake contact details even if the resume parse yields nothing.

    Args:
        intake: An ``IntakeSubmission`` ORM instance (must have ``resume_key``
                and ``resume_mime`` populated).

    Returns:
        Dict matching the ``ProfileFormData`` shape used by the frontend.
    """
    resume_text = ""
    try:
        s3 = get_s3_client()
        bucket = os.environ["S3_BUCKET_NAME"]
        obj = s3.get_object(Bucket=bucket, Key=intake.resume_key)
        raw_bytes = obj["Body"].read()

        suffix = Path(intake.resume_key).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(raw_bytes)
            temp_path = Path(tmp_file.name)

        resume_text = _extract_resume_text(temp_path, intake.resume_mime)
    except Exception:
        resume_text = ""
    finally:
        if "temp_path" in locals() and temp_path.exists():
            temp_path.unlink()

    parsed = parse_resume(resume_text) if resume_text else {}

    experience_entries = []
    for idx, exp in enumerate(parsed.get("experience", []) if isinstance(parsed, dict) else []):
        bullets = exp.get("impact_bullets") or []
        description = "\n".join(f"- {bullet}" for bullet in bullets) if bullets else ""
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

    education_entries = []
    education_structured = parsed.get("education_entries") if isinstance(parsed, dict) else None
    if isinstance(education_structured, list) and education_structured:
        for idx, entry in enumerate(education_structured):
            if not isinstance(entry, dict):
                continue
            education_entries.append(
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
    else:
        education_raw = parsed.get("education", "") if isinstance(parsed, dict) else ""
        for idx, line in enumerate([item.strip() for item in str(education_raw).splitlines() if item.strip()]):
            education_entries.append(
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

    skills = parsed.get("skills", []) if isinstance(parsed, dict) else []
    if isinstance(skills, str):
        skills = [skills]
    skills = [skill for skill in skills if skill]

    profile = default_profile(
        email=intake.email,
        name=f"{intake.first_name} {intake.last_name}".strip(),
        role="job-seeker",
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
            "experience": experience_entries,
            "education": education_entries,
            "skills": skills,
            "uploadedResume": {
                "name": Path(intake.resume_key).name,
                "size": intake.resume_size_bytes,
                "type": intake.resume_mime,
            },
            "resumeKey": intake.resume_key,
        }
    )

    return profile


def _build_profile_from_resume_key(
    resume_key: str,
    resume_mime: str,
    resume_size_bytes: int,
    resume_name: str | None = None,
) -> dict:
    """Parse a resume stored in S3 and return profile field updates.

    Used by the authenticated resume-upload flow (``/api/profile/resume/finalize``)
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
    resume_text = ""
    try:
        s3 = get_s3_client()
        bucket = os.environ["S3_BUCKET_NAME"]
        obj = s3.get_object(Bucket=bucket, Key=resume_key)
        raw_bytes = obj["Body"].read()

        suffix = Path(resume_key).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(raw_bytes)
            temp_path = Path(tmp_file.name)

        resume_text = _extract_resume_text(temp_path, resume_mime)
    except Exception:
        resume_text = ""
    finally:
        if "temp_path" in locals() and temp_path.exists():
            temp_path.unlink()

    parsed = parse_resume(resume_text) if resume_text else {}

    experience_entries = []
    for idx, exp in enumerate(parsed.get("experience", []) if isinstance(parsed, dict) else []):
        bullets = exp.get("impact_bullets") or []
        description = "\n".join(f"- {bullet}" for bullet in bullets) if bullets else ""
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

    education_entries = []
    education_structured = parsed.get("education_entries") if isinstance(parsed, dict) else None
    if isinstance(education_structured, list) and education_structured:
        for idx, entry in enumerate(education_structured):
            if not isinstance(entry, dict):
                continue
            education_entries.append(
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
    else:
        education_raw = parsed.get("education", "") if isinstance(parsed, dict) else ""
        for idx, line in enumerate([item.strip() for item in str(education_raw).splitlines() if item.strip()]):
            education_entries.append(
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

    skills = parsed.get("skills", []) if isinstance(parsed, dict) else []
    if isinstance(skills, str):
        skills = [skills]
    skills = [skill for skill in skills if skill]

    filename = resume_name.strip() if resume_name else Path(resume_key).name

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

def log_audit_event(action: str, actor_user_id, resource: str, metadata=None) -> None:
    """Append an ``AuditLog`` row to the current SQLAlchemy session.

    Does NOT commit — the caller must ``db.session.commit()`` to persist.
    This function is intentionally low-level; the caller owns the transaction
    so that audit rows are committed atomically with the surrounding changes.

    Args:
        action:        Short verb describing the operation (e.g. ``"read"``,
                       ``"update"``, ``"email_send_failed"``).
        actor_user_id: ``User.id`` of the acting user, or None for anonymous
                       events.
        resource:      Resource type affected (e.g. ``"profile"``, ``"email"``).
        metadata:      Optional dict of additional context (serialized to JSON).
    """
    audit = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource=resource,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
        event_metadata=metadata or {},
    )
    db.session.add(audit)

@limiter.limit("10 per minute")
@app.post("/api/intake/presign")
def presign():
    """POST /api/intake/presign — Generate a presigned S3 PUT URL for resume upload.

    Step 1 of 2 in the intake flow.  The client sends the file's MIME type and
    size; the server validates both, generates a UUID-based object key, and
    returns a short-lived presigned PUT URL for direct browser-to-R2 upload.

    Body (JSON):
        mime (str): MIME type of the resume (must be in ALLOWED_MIME).
        size (int): File size in bytes (must be 0 < size <= 10 MB).

    Returns:
        200 {"submission_id", "object_key", "upload_url", "max_bytes"}
        400 on invalid mime or size
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "JSON body required"}), 400


    mime = (data.get("mime") or "").strip()
    size = int(data.get("size") or 0)

    if mime not in ALLOWED_MIME:
        return jsonify({"error": "Unsupported file type"}), 400
    if size <= 0 or size > MAX_BYTES:
        return jsonify({"error": "File too large (max 10MB)"}), 400

    submission_id = str(uuid.uuid4())
    ext = {
        "application/pdf": "pdf",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    }.get(mime, "bin")

    # Non-guessable object key
    object_key = f"intake/{submission_id}/resume.{ext}"

    s3 = get_s3_client()
    bucket = os.environ["S3_BUCKET_NAME"]

    # Presigned PUT URL for direct browser upload
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": bucket,
            "Key": object_key,
            "ContentType": mime,
        },
        ExpiresIn=10 * 60,  # 10 minutes
        HttpMethod="PUT",
    )

    return jsonify({
        "submission_id": submission_id,
        "object_key": object_key,
        "upload_url": url,
        "max_bytes": MAX_BYTES,
    })

@limiter.limit("20 per minute")
@app.post("/api/intake/finalize")
def finalize():
    """POST /api/intake/finalize — Commit an intake submission after resume upload.

    Step 2 of 2 in the intake flow.  The client provides personal details and
    the object key from the presign step.  The server:
      1. Validates all fields and verifies the uploaded object exists in R2.
      2. Inserts the row into ``intake_submissions``.
      3. Sends an internal notification email to info@solverah.com.

    Body (JSON):
        submission_id, object_key, mime, size (from presign response)
        first_name, last_name, email, state (required)
        phone, linkedin_url, portfolio_url, privacy_consent (optional/conditional)

    Returns:
        200 {"ok": true}
        400 on validation failure or S3 mismatch
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "JSON body required"}), 400


    submission_id = (data.get("submission_id") or "").strip()
    first_name = _normalize_whitespace((data.get("first_name") or "").strip())
    last_name = _normalize_whitespace((data.get("last_name") or "").strip())
    email = (data.get("email") or "").strip().lower()
    state = _normalize_whitespace((data.get("state") or "").strip())
    phone = _normalize_whitespace((data.get("phone") or "").strip())
    linkedin_url = (data.get("linkedin_url") or "").strip()
    portfolio_url = (data.get("portfolio_url") or "").strip()
    privacy_consent = data.get("privacy_consent") is True

    object_key = (data.get("object_key") or "").strip()
    mime = (data.get("mime") or "").strip()
    size = int(data.get("size") or 0)

    # Basic validation
    try:
        uuid.UUID(submission_id)
    except Exception:
        return jsonify({"error": "Invalid submission_id"}), 400

    if not object_key.startswith(f"intake/{submission_id}/"):
        return jsonify({"error": "Invalid object_key"}), 400
    if mime not in ALLOWED_MIME:
        return jsonify({"error": "Unsupported file type"}), 400
    if size <= 0 or size > MAX_BYTES:
        return jsonify({"error": "Invalid file size"}), 400
    
    if not email or len(email) > 254 or not _is_valid_email(email):
        return jsonify({"error": "Valid email is required"}), 400

    if not state or len(state) > 50:
        return jsonify({"error": "State is required"}), 400

    if not privacy_consent:
        return jsonify({"error": "Privacy consent is required"}), 400

    if not first_name or not last_name:
        return jsonify({"error": "First and last name are required"}), 400

    if len(first_name) > 120 or len(last_name) > 120:
        return jsonify({"error": "First or last name is too long"}), 400

    if phone and not _is_valid_phone(phone):
        return jsonify({"error": "Invalid phone format"}), 400

    if linkedin_url and not _is_valid_linkedin_url(linkedin_url):
        return jsonify({"error": "LinkedIn URL must be https://linkedin.com"}), 400

    if portfolio_url and not _is_valid_https_url(portfolio_url):
        return jsonify({"error": "Portfolio URL must be https://"}), 400

    if len(phone) > 50 or len(linkedin_url) > 400 or len(portfolio_url) > 400:
        return jsonify({"error": "One or more fields are too long"}), 400


    # HEAD the object to confirm it exists and matches metadata
    s3 = get_s3_client()
    bucket = os.environ["S3_BUCKET_NAME"]
    try:
        head = s3.head_object(Bucket=bucket, Key=object_key)
        actual_size = int(head.get("ContentLength", 0))
        actual_mime = head.get("ContentType", "")
        if actual_size != size:
            return jsonify({"error": "Uploaded file size mismatch"}), 400
        if actual_mime != mime:
            return jsonify({"error": "Uploaded file type mismatch"}), 400
    except Exception:
        return jsonify({"error": "Upload not found in storage"}), 400

    # Insert record
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intake_submissions
                    (id, first_name, last_name, email, state, phone, linkedin_url, portfolio_url,
                    resume_key, resume_mime, resume_size_bytes, status)
                    VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, 'uploaded')
                    """,
                    (
                        submission_id,
                        first_name,
                        last_name,
                        email,
                        state,
                        phone or None,
                        linkedin_url or None,
                        portfolio_url or None,
                        object_key,
                        mime,
                        size,
                    ),
                )

    finally:
        conn.close()

    # Send notification email to info@solverah.com
    try:
        from email_utils import send_intake_notification
        send_intake_notification(
            first_name=first_name,
            last_name=last_name,
            email=email,
            state=state,
            phone=phone,
            linkedin_url=linkedin_url,
            portfolio_url=portfolio_url,
            object_key=object_key,
            mime=mime,
            size=size,
        )
    except Exception as e:
        app.logger.error(f"Failed to send intake notification to info@solverah.com: {e}")
    return jsonify({"ok": True})


@limiter.limit("5 per minute")
@app.post("/api/intake/create-account")
def intake_create_account():
    """POST /api/intake/create-account — Register a new account from an intake submission.

    Looks up the intake record by submission_id, validates the chosen password,
    creates a ``User`` row with ``email_confirmed=False``, and sends a 6-digit
    OTP verification email.  The intake record's status is updated to
    ``"account_created"``.

    Body (JSON):
        submission_id (str): UUID from the intake finalize step.
        password      (str): Desired account password (must pass strength policy).
        role          (str): Must be ``"job-seeker"`` (only role supported here).

    Returns:
        201 {"message": "registered", "user": {...}}
        400 on validation failure or duplicate email
        404 if submission_id is not found
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    submission_id = (data.get("submission_id") or "").strip()
    password = data.get("password") or ""
    role = data.get("role") or "job-seeker"

    try:
        uuid.UUID(submission_id)
    except Exception:
        return jsonify({"error": "Invalid submission_id"}), 400

    if role != "job-seeker":
        return jsonify({"error": "Only job seeker accounts are supported"}), 400

    is_valid, validation_message = validate_password(password)
    if not is_valid:
        return jsonify({"error": validation_message}), 400

    intake = IntakeSubmission.query.filter_by(id=submission_id).first()
    if not intake:
        return jsonify({"error": "Submission not found"}), 404

    existing = User.query.filter_by(email=intake.email.lower()).first()
    if existing:
        return jsonify({"error": "User already exists"}), 400

    # Create user with confirmation token
    token = uuid.uuid4().hex
    hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
    full_name = f"{intake.first_name} {intake.last_name}".strip()
    profile_data = _build_profile_from_intake(intake)

    new_user = User(
        email=intake.email.lower(),
        password=hashed_pw,
        name=full_name,
        role=role,
        profile_data=profile_data,
        email_confirmed=False,
        confirmation_token=token,
        confirmation_sent_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.session.add(new_user)

    intake.status = "account_created"
    db.session.commit()

    # Send confirmation email (best-effort)
    try:
        send_confirmation_email(new_user.email, token)
    except Exception:
        log_audit_event(action="email_send_failed", actor_user_id=new_user.id, resource="email", metadata={})

    return jsonify({
        "message": "registered",
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "name": new_user.name,
            "role": new_user.role,
        },
    }), 201


@limiter.limit("5 per minute")
@app.post("/api/intake/sign-in")
def intake_sign_in():
    """POST /api/intake/sign-in — Sign in and attach an intake submission to an existing account.

    Used when the user already has an account and returns through the intake
    flow.  After successful authentication, the intake's parsed profile data is
    merged (intake values win on conflict) into the user's existing profile.
    The intake status is updated to ``"account_linked"``.

    Body (JSON):
        submission_id, email, password

    Returns:
        200 {"message": "signed in", "csrfToken", "user": {...}} + JWT cookie
        400 if email doesn't match the submission
        401 on wrong password
        403 if email is not yet confirmed
        404 if submission or user not found
        423 if account is locked
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    submission_id = (data.get("submission_id") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    try:
        uuid.UUID(submission_id)
    except Exception:
        return jsonify({"error": "Invalid submission_id"}), 400

    if not email or not _is_valid_email(email):
        return jsonify({"error": "Valid email is required"}), 400

    intake = IntakeSubmission.query.filter_by(id=submission_id).first()
    if not intake:
        return jsonify({"error": "Submission not found"}), 404

    if intake.email.lower() != email:
        return jsonify({"error": "Email does not match submission"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Account not found"}), 404

    if user.locked_until and user.locked_until > datetime.datetime.now(datetime.timezone.utc):
        return jsonify({"error": "Account locked. Try again later."}), 423

    if not bcrypt.check_password_hash(user.password, password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
            user.locked_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                minutes=LOGIN_LOCKOUT_MINUTES
            )
            user.failed_login_attempts = 0
        db.session.commit()
        return jsonify({"error": "Invalid credentials"}), 401

    user.failed_login_attempts = 0
    user.locked_until = None

    if not getattr(user, "email_confirmed", False):
        return jsonify({"error": "Email not confirmed. Please confirm your email before signing in."}), 403

    intake_profile = _build_profile_from_intake(intake)
    existing_profile = user.profile_data or {}
    merged_profile = {**existing_profile, **intake_profile}
    user.profile_data = merged_profile

    full_name = f"{intake.first_name} {intake.last_name}".strip()
    if full_name:
        user.name = full_name

    intake.status = "account_linked"
    log_audit_event(
        action="intake_attach",
        actor_user_id=user.id,
        resource="intake",
        metadata={"submission_id": intake.id, "user_id": user.id},
    )
    db.session.commit()

    access_token = create_access_token(identity=user.email)
    resp = jsonify({
        "message": "signed in",
        "csrfToken": get_csrf_token(access_token),
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
    })
    set_access_cookies(resp, access_token)

    return resp


def default_profile(email: str = "", name: str = "", role: str = "job-seeker") -> dict:
    """Return a blank ``profile_data`` dict pre-populated with identity fields.

    Used when registering a new user or creating an account from an intake
    submission.  The recruiter role gets extra company-facing fields appended.

    Args:
        email: User's email address — pre-fills the ``email`` field.
        name:  Full name (``"First Last"``); split into firstName/lastName.
        role:  ``"job-seeker"`` or ``"recruiter"``.

    Returns:
        Profile dict ready to be stored in ``User.profile_data``.
    """
    first = name.split(" ")[0] if name else ""
    last = " ".join(name.split(" ")[1:]) if name else ""

    # Default job-seeker profile
    profile = {
        "firstName": first,
        "lastName": last,
        "email": email,
        "phone": "",
        "location": "",
        "primaryLocation": "",
        "secondaryLocations": [],
        "linkedinUrl": "",
        "summary": "",
        "experience": [],
        "education": [],
        "skills": [],
        "performanceReviews": [],
        "psychometricResults": {
            "leadership": {"score": None, "percentile": None, "completed": False},
            "problemSolving": {"score": None, "percentile": None, "completed": False},
            "communication": {"score": None, "percentile": None, "completed": False},
            "creativity": {"score": None, "percentile": None, "completed": False},
            "teamwork": {"score": None, "percentile": None, "completed": False},
        },
    }

    if role == "recruiter":
        profile.update({
            "company": "",
            "position": "",
            "hiringGoals": "",
            "openRoles": [],
        })

    return profile
  
ML_ENABLED = os.getenv("ML_ENABLED", "0") == "1"
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"



@limiter.limit("5 per minute")
@app.route("/api/login", methods=["POST"])
def login():
    """POST /api/login — Authenticate a user and issue a JWT cookie.

    Validates credentials, enforces account lockout after ``MAX_LOGIN_ATTEMPTS``
    consecutive failures, and requires email confirmation before granting access.
    On success, sets an HttpOnly JWT cookie and returns the CSRF token in the
    response body (so the frontend can attach it as ``X-CSRF-TOKEN`` on mutating
    requests).

    Body (JSON):
        email    (str): User's email address.
        password (str): Plaintext password.

    Returns:
        200 {"message", "csrfToken", "user": {...}} + JWT cookie
        401 on invalid credentials
        403 if email not confirmed
        423 if account is locked
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if user and user.locked_until and user.locked_until > datetime.datetime.now(datetime.timezone.utc):
        return jsonify({"error": "Account locked. Try again later."}), 423

    if not user or not bcrypt.check_password_hash(user.password, password):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                    minutes=LOGIN_LOCKOUT_MINUTES
                )
                user.failed_login_attempts = 0
            db.session.commit()
        return jsonify({"error": "Invalid credentials"}), 401

    # Reset failed attempts and clear lockout
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()

    # Require email confirmation
    if not getattr(user, "email_confirmed", False):
        return jsonify({"error": "Email not confirmed. Please check your inbox or use the resend option."}), 403

    access_token = create_access_token(identity=user.email)

    # Build JSON response
    resp = jsonify({
        "message": "login successful",
        "csrfToken": get_csrf_token(access_token),
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        }
    })

    # Attach JWT as HttpOnly cookie
    set_access_cookies(resp, access_token)

    return resp

@app.route("/api/logout", methods=["POST"])
def logout():
    """POST /api/logout — Clear the JWT cookie server-side.

    Flask-JWT-Extended's ``unset_jwt_cookies`` removes the access-token cookie
    from the response, effectively ending the session.

    Returns:
        200 {"message": "logout successful"}
    """
    resp = jsonify({"message": "logout successful"})
    unset_jwt_cookies(resp)
    return resp


@limiter.limit("5 per minute")
@app.route("/api/confirm-email", methods=["POST"])
def confirm_email():
    """POST /api/confirm-email — Verify the 6-digit OTP sent at registration.

    Checks that the code matches, hasn't expired (default 15 min window), and
    clears the token fields on success so the code cannot be reused.

    Body (JSON):
        email (str): User's email address.
        code  (str): 6-digit OTP received by email.

    Returns:
        200 {"message": "email confirmed"}
        400 on missing fields, invalid code, or expired code
    """
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    if not email or not code:
        return jsonify({"error": "email and code are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.confirmation_token:
        return jsonify({"error": "invalid code"}), 400

    # Check expiry (15 minutes for 6-digit codes)
    exp_minutes = int(os.environ.get("VERIFY_CODE_EXP_MINUTES", "15"))
    sent_at_utc = user.confirmation_sent_at.replace(tzinfo=datetime.timezone.utc) if user.confirmation_sent_at else None
    if not sent_at_utc or sent_at_utc + datetime.timedelta(minutes=exp_minutes) < datetime.datetime.now(datetime.timezone.utc):
        return jsonify({"error": "code expired"}), 400

    if user.confirmation_token != code:
        return jsonify({"error": "invalid code"}), 400

    user.email_confirmed = True
    user.confirmation_token = None
    user.confirmation_sent_at = None
    db.session.commit()

    return jsonify({"message": "email confirmed"}), 200


@limiter.limit("5 per minute")
@app.route("/api/resend-confirmation", methods=["POST"])
def resend_confirmation():
    """POST /api/resend-confirmation — Issue a fresh OTP for unconfirmed accounts.

    Regenerates and re-sends the 6-digit verification code.  Rate-limited to
    5 per minute to prevent abuse.  Fails silently if the email is already
    confirmed to avoid leaking account existence.

    Body (JSON):
        email (str): Email address of the unconfirmed account.

    Returns:
        200 {"message": "confirmation_sent"}
        400 if already confirmed or invalid email
        404 if no account found
        500 on email delivery failure
    """
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email or not _is_valid_email(email):
        return jsonify({"error": "Valid email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Account not found"}), 404

    if getattr(user, "email_confirmed", False):
        return jsonify({"error": "Email already confirmed"}), 400

    code = str(random.randint(100000, 999999))
    user.confirmation_token = code
    user.confirmation_sent_at = datetime.datetime.now(datetime.timezone.utc)
    db.session.commit()

    try:
        send_confirmation_email(user.email, code)
    except Exception as e:
        log_audit_event(action="email_send_failed", actor_user_id=user.id, resource="email", metadata={"error": str(e)})
        app.logger.error(f"resend_confirmation email failed for {user.email}: {e}")
        return jsonify({"error": "Failed to send email", "detail": str(e)}), 500

    return jsonify({"message": "confirmation_sent"}), 200


from email_utils import send_confirmation_email


@limiter.limit("5 per minute")
@app.route("/api/register", methods=["POST"])
def register():
    """POST /api/register — Create a new user account.

    Creates the user with ``email_confirmed=False`` and sends a 6-digit OTP.
    The user must confirm their email before they can log in.  Profile data is
    pre-seeded with a blank default profile appropriate for the given role.

    Body (JSON):
        email    (str): Must be unique.
        password (str): Must pass the strength policy in validators.py.
        name     (str): Full name (optional but recommended).
        role     (str): ``"job-seeker"`` or ``"recruiter"``.

    Returns:
        201 {"message": "registered", "user": {...}}
        400 on invalid password or duplicate email
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = data.get("name")
    role = data.get("role", "job-seeker")

    is_valid, validation_message = validate_password(password)
    if not is_valid:
        return jsonify({"error": validation_message}), 400

    #Check user exsistence off of email
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User already exists"}), 400

    hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
    profile_data = default_profile(email=email, name=name, role=role)


    # Create user with 6-digit verification code
    code = str(random.randint(100000, 999999))
    new_user = User(
        email=email,
        password=hashed_pw,
        name=data.get("name"),
        role=data.get("role"),
        profile_data=profile_data,
        email_confirmed=False,
        confirmation_token=code,
        confirmation_sent_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.session.add(new_user)
    db.session.commit()

    # Send verification code email (best-effort; failures shouldn't break registration)
    try:
        send_confirmation_email(new_user.email, code)
    except Exception as e:
        app.logger.error(f"register email send failed for {new_user.email}: {e}")
        log_audit_event(action="email_send_failed", actor_user_id=new_user.id, resource="email", metadata={"error": str(e)})
        db.session.commit()

    return jsonify({"message": "registered", "user": {
        "id": new_user.id,
        "email": new_user.email,
        "name": new_user.name,
        "role": new_user.role
    }}), 201





@app.route("/api/profile", methods=["GET", "POST"])
@jwt_required()
def profile():
    """GET|POST /api/profile — Read or update the authenticated user's profile.

    GET:
        Returns the full profile including ``profileData`` and the current CSRF
        token.  Also writes a ``read`` audit log entry.

    POST:
        Merges incoming ``profileData`` keys into the existing profile (unknown
        keys are stripped by ``clean_profile_data``).  Quiz results are merged
        at the sub-key level so existing quiz entries are preserved.  Diffs
        against the stored parser snapshot to record ``ResumeParseCorrection``
        rows for any experience/education/skills the user edits after a resume
        upload.

    Returns (GET):
        200 {"id", "email", "name", "role", "profileData", "csrfToken"}
    Returns (POST):
        200 {"message", "profileData"}
        404 if the JWT identity no longer maps to a user
    """
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if request.method == "GET":
        log_audit_event(
            action="read",
            actor_user_id=user.id,
            resource="profile",
            metadata={"target_user_id": user.id},
        )
        db.session.commit()
        return jsonify({
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "profileData": user.profile_data or {},
            "csrfToken": get_jwt().get("csrf"),
        })

    # Handle profile update (POST)
    data = request.get_json()
    raw_profile_data = data.get("profileData", {})

    # Clean incoming keys
    profile_data = clean_profile_data(raw_profile_data)

    # Merge incoming profile_data with existing profile_data (preserve other fields)
    existing = user.profile_data or {}
    # shallow merge for top-level; quizzes/results should be a dedicated key
    merged = {**existing, **profile_data}

    # If there are quiz results, merge those specially and compute a lightweight summary
    incoming_quiz = profile_data.get("quizResults")
    existing_quiz = existing.get("quizResults") if isinstance(existing, dict) else None

    if incoming_quiz:
        merged_quiz = {}
        if existing_quiz and isinstance(existing_quiz, dict):
            merged_quiz.update(existing_quiz)
        # overwrite/insert incoming quiz entries
        merged_quiz.update(incoming_quiz if isinstance(incoming_quiz, dict) else {})
        merged["quizResults"] = merged_quiz

        # simple summary computation: counts and average selected option index per quiz
        def compute_stats(ans):
            counts = {}
            total = 0
            n = 0

            def walk(v):
                nonlocal total, n
                if isinstance(v, dict):
                    for item in v.values():
                        walk(item)
                elif isinstance(v, list):
                    for item in v:
                        walk(item)
                elif isinstance(v, int):
                    counts[str(v)] = counts.get(str(v), 0) + 1
                    total += v
                    n += 1

            walk(ans)
            avg = (total / n) if n > 0 else None
            return {"counts": counts, "avgIndex": avg, "n": n}

        summary = {}
        for qkey, qval in merged.get("quizResults", {}).items():
            try:
                summary[qkey] = compute_stats(qval)
            except Exception:
                summary[qkey] = {"counts": {}, "avgIndex": None, "n": 0}

        merged["_quizSummary"] = summary

    # Diff against the parser snapshot for experience/education/skills.
    # Any field the user changed from what the parser produced is recorded in
    # resume_parse_correction for training-data analysis.
    _TRACKED_RESUME_FIELDS = ("experience", "education", "skills")
    snapshot = existing.get("_parsedResumeSnapshot")
    if snapshot and isinstance(snapshot, dict):
        resume_key = snapshot.get("resumeKey")
        if resume_key:
            for field in _TRACKED_RESUME_FIELDS:
                if field not in profile_data:
                    continue
                new_val = profile_data[field]
                parsed_val = snapshot.get(field)
                if new_val != parsed_val:
                    correction = ResumeParseCorrection.query.filter_by(
                        user_id=user.id,
                        resume_key=resume_key,
                        field=field,
                    ).first()
                    if correction:
                        correction.corrected_value = new_val
                        correction.updated_at = datetime.datetime.utcnow()
                    else:
                        correction = ResumeParseCorrection(
                            user_id=user.id,
                            resume_key=resume_key,
                            field=field,
                            parsed_value=parsed_val,
                            corrected_value=new_val,
                        )
                        db.session.add(correction)

    user.profile_data = merged
    log_audit_event(
        action="update",
        actor_user_id=user.id,
        resource="profile",
        metadata={"updated_fields": sorted(profile_data.keys()), "target_user_id": user.id},
    )
    db.session.commit()

    return jsonify({
        "message": "Profile updated successfully",
        "profileData": user.profile_data
    })


@limiter.limit("10 per minute")
@app.post("/api/quiz-insights")
@jwt_required()
def quiz_insights():
    """POST /api/quiz-insights — Generate and persist AI career insights (authenticated).

    Validates and normalizes the quiz answers, calls OpenAI (gpt-4o-mini by
    default) with a structured prompt, coerces the response to a canonical
    schema, and persists the insights into ``profile_data.quizInsights``.

    Body (JSON):
        quizGroup (str):  Logical group key (e.g. ``"careerQuizzes"``).
        quizzes   (list): Each entry: ``{key, title, items: [{question, selected}]}``.

    Returns:
        200 {"quizGroup", "overallInsight", "insights": [...]}
        400 on missing/invalid input
        500 on OpenAI failure or malformed model response
    """
    data = request.get_json(silent=True) or {}
    quiz_group = (data.get("quizGroup") or "").strip()
    quizzes = data.get("quizzes") or []

    if not quiz_group or not isinstance(quizzes, list) or not quizzes:
        return jsonify({"error": "quizGroup and quizzes are required"}), 400

    normalized_quizzes = []
    for quiz in quizzes:
        if not isinstance(quiz, dict):
            continue
        key = (quiz.get("key") or "").strip()
        title = (quiz.get("title") or "").strip()
        items = quiz.get("items") or []
        if not key or not title or not isinstance(items, list) or not items:
            continue
        normalized_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            question = (item.get("question") or "").strip()
            selected = (item.get("selected") or "").strip()
            if question and selected:
                normalized_items.append({"question": question, "selected": selected})
        if normalized_items:
            normalized_quizzes.append({"key": key, "title": title, "items": normalized_items})

    if not normalized_quizzes:
        return jsonify({"error": "No valid quiz answers provided"}), 400

    try:
        client = _get_openai_client()
        model = os.environ.get("OPENAI_QUIZ_MODEL", "gpt-4o-mini")
        messages = _build_quiz_insight_prompt(quiz_group, normalized_quizzes)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        insight_payload = json.loads(content)
    except Exception as exc:
        app.logger.exception("Quiz insight generation failed")
        return jsonify({"error": f"Unable to generate insight: {type(exc).__name__}: {exc}"}), 500

    normalized_payload = _coerce_insight_payload(insight_payload, quiz_group, normalized_quizzes)
    insights = normalized_payload.get("insights") if isinstance(normalized_payload, dict) else None
    overall_insight = (
        normalized_payload.get("overallInsight") if isinstance(normalized_payload, dict) else None
    )

    if not isinstance(insights, list):
        return jsonify({"error": "Malformed insight response"}), 500

    # Persist to user profile
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    profile = dict(user.profile_data or {})
    quiz_insights = profile.get("quizInsights")
    if not isinstance(quiz_insights, dict):
        quiz_insights = {}
    else:
        quiz_insights = dict(quiz_insights)

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if quiz_group == "careerQuizzes":
        group_store = quiz_insights.get("careerQuizzes")
        if not isinstance(group_store, dict):
            group_store = {}
        else:
            group_store = dict(group_store)
        if overall_insight and isinstance(overall_insight, dict):
            group_store["_overallInsight"] = overall_insight
        group_store["_generatedAt"] = timestamp
        group_store["_model"] = model
        for insight in insights:
            if not isinstance(insight, dict):
                continue
            key = insight.get("key")
            if not key:
                continue
            store = {
                "title": insight.get("title"),
                "summary": insight.get("summary"),
                "keyTakeaways": insight.get("keyTakeaways"),
                "combinedMeaning": insight.get("combinedMeaning"),
                "nextSteps": insight.get("nextSteps"),
                "generatedAt": timestamp,
                "model": model,
            }
            group_store[key] = store
        quiz_insights["careerQuizzes"] = group_store
    else:
        first = insights[0] if insights else {}
        quiz_insights[quiz_group] = {
            "title": first.get("title"),
            "summary": first.get("summary"),
            "keyTakeaways": first.get("keyTakeaways"),
            "combinedMeaning": first.get("combinedMeaning"),
            "nextSteps": first.get("nextSteps"),
            "overallInsight": overall_insight,
            "generatedAt": timestamp,
            "model": model,
        }

    profile["quizInsights"] = quiz_insights
    user.profile_data = profile
    db.session.commit()

    return jsonify({
        "quizGroup": quiz_group,
        "overallInsight": overall_insight,
        "insights": insights,
    })


@limiter.limit("1 per day")
@app.post("/api/quiz-insights-guest")
def quiz_insights_guest():
    """POST /api/quiz-insights-guest — Generate AI insights for unauthenticated preview.

    Same logic as ``/api/quiz-insights`` but requires no JWT.  Hard-limited to
    1 request per day per IP to reduce OpenAI spend.  Insights are NOT persisted
    to any user profile.

    Body (JSON): Same schema as quiz_insights.

    Returns:
        200 {"quizGroup", "overallSummary", "insights": [...]}
        400/500 as per quiz_insights
    """
    data = request.get_json(silent=True) or {}
    quiz_group = (data.get("quizGroup") or "").strip()
    quizzes = data.get("quizzes") or []

    if not quiz_group or not isinstance(quizzes, list) or not quizzes:
        return jsonify({"error": "quizGroup and quizzes are required"}), 400

    normalized_quizzes = []
    for quiz in quizzes:
        if not isinstance(quiz, dict):
            continue
        key = (quiz.get("key") or "").strip()
        title = (quiz.get("title") or "").strip()
        items = quiz.get("items") or []
        if not key or not title or not isinstance(items, list) or not items:
            continue
        normalized_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            question = (item.get("question") or "").strip()
            selected = (item.get("selected") or "").strip()
            if question and selected:
                normalized_items.append({"question": question, "selected": selected})
        if normalized_items:
            normalized_quizzes.append({"key": key, "title": title, "items": normalized_items})

    if not normalized_quizzes:
        return jsonify({"error": "No valid quiz answers provided"}), 400

    try:
        client = _get_openai_client()
        model = os.environ.get("OPENAI_QUIZ_MODEL", "gpt-4o-mini")
        messages = _build_quiz_insight_prompt(quiz_group, normalized_quizzes)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        insight_payload = json.loads(content)
    except Exception as exc:
        app.logger.exception("Quiz insight generation failed")
        return jsonify({"error": f"Unable to generate insight: {type(exc).__name__}: {exc}"}), 500

    normalized_payload = _coerce_insight_payload(insight_payload, quiz_group, normalized_quizzes)
    insights = normalized_payload.get("insights") if isinstance(normalized_payload, dict) else None
    overall_summary = (
        normalized_payload.get("overallSummary") if isinstance(normalized_payload, dict) else None
    )

    if not isinstance(insights, list):
        return jsonify({"error": "Malformed insight response"}), 500

    return jsonify({
        "quizGroup": quiz_group,
        "overallSummary": overall_summary,
        "insights": insights,
    })

@app.route("/api/profile/resume-url", methods=["GET"])
@jwt_required()
def get_profile_resume_url():
    """GET /api/profile/resume-url — Get a presigned download URL for the user's resume.

    Generates a short-lived (10-minute) presigned GET URL for the resume stored
    at the ``resumeKey`` in the user's profile.  The URL is returned to the
    frontend so the browser can download or display the file without exposing
    permanent storage credentials.

    Returns:
        200 {"url": "<presigned URL>"}
        404 if user not found or no resume on file
        500 if the presigned URL cannot be generated
    """
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    profile = user.profile_data or {}
    resume_key = profile.get("resumeKey")
    if not resume_key:
        return jsonify({"error": "No resume on file"}), 404

    s3 = get_s3_client()
    bucket = os.environ["S3_BUCKET_NAME"]
    try:
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": bucket,
                "Key": resume_key,
            },
            ExpiresIn=10 * 60,
        )
    except Exception:
        return jsonify({"error": "Unable to generate resume URL"}), 500

    return jsonify({"url": url})



@app.post("/api/profile/resume/presign")
@jwt_required()
def profile_resume_presign():
    """POST /api/profile/resume/presign — Presign a PUT URL for authenticated resume upload.

    Scopes the S3 object key to ``profile/{user_id}/{uuid}/resume.{ext}``
    so that one user cannot overwrite another's file.  Step 1 of 2.

    Body (JSON):
        mime (str): Resume MIME type.
        size (int): File size in bytes.

    Returns:
        200 {"object_key", "upload_url", "max_bytes"}
        400 on invalid mime or size
        404 if user not found
    """
    data = request.get_json(silent=True) or {}
    mime = (data.get("mime") or "").strip()
    size = int(data.get("size") or 0)

    if mime not in ALLOWED_MIME:
        return jsonify({"error": "Unsupported file type"}), 400
    if size <= 0 or size > MAX_BYTES:
        return jsonify({"error": "File too large (max 10MB)"}), 400

    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    ext = {
        "application/pdf": "pdf",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    }.get(mime, "bin")

    object_key = f"profile/{user.id}/{uuid.uuid4()}/resume.{ext}"

    s3 = get_s3_client()
    bucket = os.environ["S3_BUCKET_NAME"]
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": bucket,
            "Key": object_key,
            "ContentType": mime,
        },
        ExpiresIn=10 * 60,
        HttpMethod="PUT",
    )

    return jsonify({
        "object_key": object_key,
        "upload_url": url,
        "max_bytes": MAX_BYTES,
    })


@app.post("/api/profile/resume/finalize")
@jwt_required()
def profile_resume_finalize():
    """POST /api/profile/resume/finalize — Parse the uploaded resume and update profile.

    Verifies the object key belongs to the requesting user, downloads the
    resume from R2, runs the rule-based parser, and merges the parsed fields
    (experience, education, skills) into the user's profile.  Also stores a
    ``_parsedResumeSnapshot`` so subsequent edits can be diffed against the
    parser's original output (see ``ResumeParseCorrection``).

    Body (JSON):
        object_key (str): S3 key from the presign step.
        mime       (str): MIME type.
        size       (int): File size in bytes.
        name       (str): Original filename for display (optional).

    Returns:
        200 {"message": "Resume processed", "profileData": {...}}
        400 on invalid inputs or key ownership mismatch
        404 if user not found
    """
    data = request.get_json(silent=True) or {}
    object_key = (data.get("object_key") or "").strip()
    mime = (data.get("mime") or "").strip()
    size = int(data.get("size") or 0)
    name = (data.get("name") or "").strip()

    if mime not in ALLOWED_MIME:
        return jsonify({"error": "Unsupported file type"}), 400
    if size <= 0 or size > MAX_BYTES:
        return jsonify({"error": "Invalid file size"}), 400

    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if not object_key.startswith(f"profile/{user.id}/"):
        return jsonify({"error": "Invalid object_key"}), 400

    profile_updates = _build_profile_from_resume_key(
        resume_key=object_key,
        resume_mime=mime,
        resume_size_bytes=size,
        resume_name=name or None,
    )

    existing = user.profile_data or {}
    merged = {**existing, **profile_updates}

    # Store a snapshot of what the parser produced so we can later diff against
    # any edits the user makes — used to build parser improvement training data.
    merged["_parsedResumeSnapshot"] = {
        "resumeKey": object_key,
        "parsedAt": datetime.datetime.utcnow().isoformat(),
        "experience": profile_updates.get("experience", []),
        "education": profile_updates.get("education", []),
        "skills": profile_updates.get("skills", []),
    }

    user.profile_data = merged
    db.session.commit()

    return jsonify({
        "message": "Resume processed",
        "profileData": user.profile_data,
    })


@app.route("/api/recommendations", methods=["POST"])
@jwt_required()
def generate_recommendations():
    """POST /api/recommendations — Run the ML pipeline and persist new job recommendations.

    Accepts a ``profilePipeline`` payload (array of {section, content}), collapses
    it into a single text blob, runs the SentenceTransformer similarity scorer
    against the jobs dataset, and stores the top-20 scored results in
    ``JobRecommendation``.

    Gated by:
        DEMO_MODE  — Returns empty list immediately if set.
        ML_ENABLED — Returns 503 if the ML module is not loaded.

    Body (JSON):
        profilePipeline (str): JSON-encoded list of {section, content} dicts.

    Returns:
        200 {"recommendations": [{job_id, score}]}
        400 if profilePipeline is missing or malformed
        503 if ML pipeline is disabled
    """
    if DEMO_MODE:
        return jsonify({"recommendations": []}), 200


    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first_or_404()

    data = request.get_json() or {}
    profile_pipeline_str = data.get("profilePipeline")
    if not profile_pipeline_str:
        return jsonify({"error": "profilePipeline is required"}), 400

    try:
        # pipeline is an array of {section, content}
        pipeline = json.loads(profile_pipeline_str)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON in profilePipeline"}), 400

    # Collapse sections into one text blob for the model
    # (You can tweak this format as you like.)
    if isinstance(pipeline, list):
        profile_text = "\n\n".join(
            f"{sec.get('section', '')}:\n{sec.get('content', '')}"
            for sec in pipeline
        )
    else:
        # fallback: treat the whole thing as raw text
        profile_text = str(pipeline)

    # Use your SentenceTransformer pipeline

    #remove lines in between when demo is done
    if not ML_ENABLED:
        return jsonify({"error": "Recommendations disabled for demo"}), 503
    
    from LLM.profile2model import sorted_mlscores
    #till here
    
    scores = sorted_mlscores(profile_text)  # returns list of (job_id, score, job_text)

    # Keep only the top N
    TOP_N = 20
    top_scores = scores[:TOP_N]

    # Optionally clear old recommendations for this user
    JobRecommendation.query.filter_by(user_id=user.id).delete()

    # Insert new ones
    for job_id, score, _job_text in top_scores:
        rec = JobRecommendation(user_id=user.id, job_id=job_id, score=score)
        db.session.add(rec)

    db.session.commit()

    # Also return them for immediate use on the frontend
    return jsonify({
        "recommendations": [
            {"job_id": job_id, "score": score}
            for job_id, score, _ in top_scores
        ]
    })


@app.route("/api/recommendations", methods=["GET"])
@jwt_required()
def get_recommendations():
    """GET /api/recommendations — Fetch persisted job recommendations for the user.

    Loads the user's ``JobRecommendation`` rows, joins them with the jobs CSV,
    and returns full job objects ordered by score descending.

    Returns:
        200 {"recommendations": [{ID, Title, Company, score, ...}]}
        200 {"recommendations": []} in DEMO_MODE
    """
    if DEMO_MODE:
        return jsonify({"recommendations": []}), 200


    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first_or_404()

    # Get this user's recommendations ordered by score
    recs = (
        JobRecommendation.query
        .filter_by(user_id=user.id)
        .order_by(JobRecommendation.score.desc())
        .all()
    )

    if not recs:
        return jsonify({"recommendations": []})

    # Load the jobs CSV and index by ID
    
    #removes these lines when demo is done
    from LLM.profile2model import jobs_path
    jobs_df = pd.read_csv(jobs_path)
    #till here

    jobs_df = pd.read_csv(jobs_path)
    jobs_by_id = {
        int(row["ID"]): row
        for _, row in jobs_df.iterrows()
        if "ID" in row
    }

    results = []
    for rec in recs:
        row = jobs_by_id.get(rec.job_id)
        if row is None:
            continue

        # Build a job object matching what Feed.tsx currently uses :contentReference[oaicite:7]{index=7}
        job_obj = {
            "ID": rec.job_id,
            "Title": row.get("Title", ""),
            "Company": row.get("Company", ""),
            "Location": row.get("Location", ""),
            "EmploymentType": row.get("EmploymentType", ""),
            "DatePosted": row.get("DatePosted", ""),
            "Remote": row.get("Remote", ""),
            "RoleDescription": row.get("RoleDescription", ""),
            "Experience": row.get("Experience", ""),
            "Link": row.get("Link", ""),
            "score": rec.score,
        }
        results.append(job_obj)

    return jsonify({"recommendations": results})



@app.route("/api/dashboard-data", methods=["GET"])
@jwt_required()
def get_dashboard_data():
    """GET /api/dashboard-data — Return summary stats for the job-seeker dashboard.

    Computes profile completion percentage, job-match count, and application
    count from live data.  Also returns static placeholder recommendations and
    recent activity until those features are fully wired up.

    Returns:
        200 {"profileCompletion", "jobMatches", "applications",
             "recentActivity", "recommendations", "hasIntakeSubmission"}
    """
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first_or_404()

    profile = user.profile_data or {}

    # Example: compute dynamic stats from their data
    profile_completion = 0
    fields = ["firstName", "lastName", "email", "summary", "skills", "experience", "education"]
    filled = sum(1 for f in fields if profile.get(f))
    profile_completion = int((filled / len(fields)) * 100)

    # Count jobs from recommendations
    job_matches = JobRecommendation.query.filter_by(user_id=user.id).count()

    # You can extend this later with live data (applications, views, etc.)
    applications = len(profile.get("applications", [])) if "applications" in profile else 0

    # Simple example recent activity & recommendations
    recent_activity = [
        {"type": "assessment", "text": "Complete your leadership assessment", "time": "1 day ago", "icon": "Brain"}
    ]

    recommendations = [
        {"title": "Complete Psychometric Assessment", "description": "Boost visibility", "action": "Take Assessment", "priority": "high", "href": "/job-seeker/profile#assessments"},
        {"title": "Add Recent Experience", "description": "Update your experience section", "action": "Update Profile", "priority": "medium", "href": "/job-seeker/profile#experience"},
    ]

    has_intake = IntakeSubmission.query.filter_by(email=current_email).first() is not None

    return jsonify({
        "profileCompletion": f"{profile_completion}%",
        "jobMatches": job_matches,
        "applications": applications,
        "recentActivity": recent_activity,
        "recommendations": recommendations,
        "hasIntakeSubmission": has_intake,
    })



@limiter.limit("5 per minute")
@app.post("/api/intake/link-account")
@jwt_required()
def intake_link_account():
    """Submit the intake form for an already-authenticated user and merge into their profile."""
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first_or_404()

    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    submission_id = (data.get("submission_id") or "").strip()
    first_name = _normalize_whitespace((data.get("first_name") or "").strip())
    last_name = _normalize_whitespace((data.get("last_name") or "").strip())
    state = _normalize_whitespace((data.get("state") or "").strip())
    phone = _normalize_whitespace((data.get("phone") or "").strip())
    linkedin_url = (data.get("linkedin_url") or "").strip()
    portfolio_url = (data.get("portfolio_url") or "").strip()
    privacy_consent = data.get("privacy_consent") is True
    info_opt_in = data.get("info_opt_in") is True

    object_key = (data.get("object_key") or "").strip()
    mime = (data.get("mime") or "").strip()
    size = int(data.get("size") or 0)

    try:
        uuid.UUID(submission_id)
    except Exception:
        return jsonify({"error": "Invalid submission_id"}), 400

    if not object_key.startswith(f"intake/{submission_id}/"):
        return jsonify({"error": "Invalid object_key"}), 400
    if mime not in ALLOWED_MIME:
        return jsonify({"error": "Unsupported file type"}), 400
    if size <= 0 or size > MAX_BYTES:
        return jsonify({"error": "Invalid file size"}), 400
    if not state or len(state) > 50:
        return jsonify({"error": "State is required"}), 400
    if not privacy_consent:
        return jsonify({"error": "Privacy consent is required"}), 400
    if not first_name or not last_name:
        return jsonify({"error": "First and last name are required"}), 400
    if len(first_name) > 120 or len(last_name) > 120:
        return jsonify({"error": "Name is too long"}), 400
    if phone and not _is_valid_phone(phone):
        return jsonify({"error": "Invalid phone format"}), 400
    if linkedin_url and not _is_valid_linkedin_url(linkedin_url):
        return jsonify({"error": "LinkedIn URL must be https://linkedin.com"}), 400
    if portfolio_url and not _is_valid_https_url(portfolio_url):
        return jsonify({"error": "Portfolio URL must be https://"}), 400
    if len(phone) > 50 or len(linkedin_url) > 400 or len(portfolio_url) > 400:
        return jsonify({"error": "One or more fields are too long"}), 400

    # Confirm resume was uploaded to S3
    s3 = get_s3_client()
    bucket = os.environ["S3_BUCKET_NAME"]
    try:
        head = s3.head_object(Bucket=bucket, Key=object_key)
        actual_size = int(head.get("ContentLength", 0))
        actual_mime = head.get("ContentType", "")
        if actual_size != size:
            return jsonify({"error": "Uploaded file size mismatch"}), 400
        if actual_mime != mime:
            return jsonify({"error": "Uploaded file type mismatch"}), 400
    except Exception:
        return jsonify({"error": "Upload not found in storage"}), 400

    # Insert intake record linked to the user's email with account_linked status
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intake_submissions
                    (id, first_name, last_name, email, state, phone, linkedin_url, portfolio_url,
                    resume_key, resume_mime, resume_size_bytes, status)
                    VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, 'account_linked')
                    """,
                    (
                        submission_id,
                        first_name,
                        last_name,
                        current_email,
                        state,
                        phone or None,
                        linkedin_url or None,
                        portfolio_url or None,
                        object_key,
                        mime,
                        size,
                    ),
                )
    finally:
        conn.close()

    # Build and merge profile data
    intake = IntakeSubmission.query.filter_by(id=submission_id).first()
    if intake:
        intake_profile = _build_profile_from_intake(intake)
        existing_profile = user.profile_data or {}
        user.profile_data = {**existing_profile, **intake_profile}
        full_name = f"{first_name} {last_name}".strip()
        if full_name:
            user.name = full_name
        db.session.commit()

    log_audit_event(
        action="intake_link_account",
        actor_email=current_email,
        target_email=current_email,
        detail=f"submission_id={submission_id}",
    )

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)
