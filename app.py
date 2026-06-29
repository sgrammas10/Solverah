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
  * AI Agent: Groq-backed chat endpoint (``/api/agent/chat``) with RAG
    context assembled from the user's profile and company profiles.

Key environment variables (required unless otherwise noted):
    DATABASE_URL        — PostgreSQL connection string.
    JWT_SECRET_KEY      — Secret key for signing JWTs.
    S3_ENDPOINT_URL     — Cloudflare R2 (or any S3-compatible) endpoint.
    S3_ACCESS_KEY_ID    — R2 access key.
    S3_SECRET_ACCESS_KEY — R2 secret key.
    S3_BUCKET_NAME      — Target bucket for resume uploads.
    OPENAI_API_KEY      — Required for quiz-insight generation.
    GROQ_API_KEY        — Required for AI agent chat (``/api/agent/chat``).
    RESEND_API_KEY      — Required for transactional emails.
    EMAIL_FROM          — Sender address (defaults to no-reply@solverah.com).
    FLASK_ENV / APP_ENV / ENV — Set to "production" to enable HTTPS-only cookies
                                and HSTS headers.
    MAX_LOGIN_ATTEMPTS  — Failed attempts before lockout (default 5).
    LOGIN_LOCKOUT_MINUTES — Lockout duration in minutes (default 15).
"""

from flask import Flask, jsonify, request, Response, stream_with_context
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
import time
import traceback
from pathlib import Path
from threading import Lock
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

_COMPANY_CULTURE_DIR = str(Path(__file__).resolve().parent / "company_culture_LLM")
if _COMPANY_CULTURE_DIR not in sys.path:
    sys.path.insert(0, _COMPANY_CULTURE_DIR)

_resume_cache: dict = {}          # resumeKey -> (text, expires_at)
_resume_cache_lock = Lock()
_RESUME_CACHE_TTL = 600           # 10 minutes — covers a full chat session

_path_suggestions_cache: dict[int, dict] = {}  # user_id -> response payload
_path_suggestions_cache_lock = Lock()


def _invalidate_path_suggestions_cache(user_id: int) -> None:
    with _path_suggestions_cache_lock:
        _path_suggestions_cache.pop(user_id, None)

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

from flask_migrate import Migrate

from model import AuditLog, Company, IntakeSubmission, JobRecommendation, ResumeParseCorrection, User, db
from datetime import timedelta
from score import culture_fit_score
from company import CultureValues
from store import all_companies

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


# Flask-CORS 5.x: pass resources as a path pattern and all options at the top level.
# Nesting options inside the resources dict (4.x style) silently produces no headers in 5.x.
CORS(
    app,
    resources=r"/api/*",
    origins=[
        r"http://localhost:\d+",
        r"http://127\.0\.0\.1:\d+",
        "https://solverah.vercel.app",
        "https://solverah.com",
        "https://www.solverah.com",
        "https://api.solverah.com",
    ],
    supports_credentials=True,
    allow_headers=["Content-Type", "X-CSRF-TOKEN"],
)

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


_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()


def _get_agent_client():
    """Return an OpenAI-compatible Groq client."""
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK not installed")
    if not _GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured")
    return OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=_GROQ_API_KEY,
        timeout=30.0,
        max_retries=1,
    )


def _default_agent_model() -> str:
    """Return the default Groq model name."""
    return "llama-3.1-8b-instant"


def _build_agent_context(user: User, resume_text: str = "") -> str:
    """Assemble a RAG system prompt from the user's profile and company data."""
    parts = [
        "You are Solverah AI, a career assistant. Use the context below to give "
        "personalized advice. Do not reveal raw context data verbatim."
    ]

    profile = user.profile_data or {}
    name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
    if name:
        parts.append(f"## User Profile\nName: {name}")
    else:
        parts.append("## User Profile")

    if summary := profile.get("summary"):
        parts.append(f"Summary: {summary}")

    if skills := profile.get("skills"):
        levels = profile.get("skill_levels") or {}
        formatted_skills = [
            f"{s} ({levels[s]})" if s in levels else str(s)
            for s in skills[:20]
        ]
        parts.append(f"Skills: {', '.join(formatted_skills)}")

    if experience := profile.get("experience"):
        exp_lines = [
            f"- {e.get('position', '')} at {e.get('company', '')}"
            for e in experience[:5]
            if e.get("position") or e.get("company")
        ]
        if exp_lines:
            parts.append("Experience:\n" + "\n".join(exp_lines))

    if education := profile.get("education"):
        edu_lines = [
            f"- {e.get('degree', '')} from {e.get('institution', '')}"
            for e in education[:3]
            if e.get("degree") or e.get("institution")
        ]
        if edu_lines:
            parts.append("Education:\n" + "\n".join(edu_lines))

    companies = Company.query.limit(10).all()
    if companies:
        company_lines = []
        for c in companies:
            line = c.name
            if c.work_environment:
                line += f": {c.work_environment}"
            if c.pace:
                line += f", pace={c.pace}"
            company_lines.append(f"- {line}")
        parts.append("## Companies in Network\n" + "\n".join(company_lines))

    # TODO: inject quiz results here once scoring is built
    parts.append("## Quiz Results\n[Not yet available — coming soon]")

    if resume_text:
        parts.append(f"## Resume\n{resume_text}")

    return "\n\n".join(parts)


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


def _build_wp_narrative_prompt(
    answers: list[dict],
    wpll_answers: list[dict] | None = None,
    selected_statement_ids: list[str] | None = None,
) -> list[dict]:
    """Construct system + user messages for the Work Pulse narrative OpenAI call.

    Resolves each answer's question_id / option_id to human-readable text so the
    model receives meaningful context rather than opaque identifiers.

    Args:
        answers:                 12 WP answers, each {question_id, option_id}.
        wpll_answers:            Optional 5 earlier WPLL answers for richer context.
        selected_statement_ids:  Optional intake statement IDs for richer context.

    Returns:
        Two-element list of OpenAI chat message dicts (system, user).
    """
    # Inline question registry: id -> (dimension, question_text, {suffix -> option_text})
    _Q: dict[str, tuple[str, str, dict[str, str]]] = {
        "wp-q1": ("Fragmentation", "When you're pulled off a task mid-way through, how long does it typically take you to rebuild your focus?", {
            "a": "A few minutes — I pick back up pretty quickly",
            "b": "10–20 minutes — it takes real effort to re-orient",
            "c": "30+ minutes — I often never quite get back into flow",
            "d": "I've mostly stopped expecting deep focus — it rarely happens",
        }),
        "wp-q2": ("Sustainability", "After a tough stretch — a demanding week, a big push — how do you typically recover?", {
            "a": "A good night's sleep or a weekend usually restores me",
            "b": "It takes a few lighter days before I feel like myself",
            "c": "I struggle to fully recover before the next demand hits",
            "d": "I don't really recover — I just keep pushing through",
        }),
        "wp-q3": ("Environmental Friction", "How much of your workday feels like it exists to support other people's processes rather than your own actual work?", {
            "a": "Not much — most of my time is on real output",
            "b": "Some — maybe 20–30% feels like overhead",
            "c": "A lot — I feel like I work for the calendar, not my work",
            "d": "Almost all of it — I can barely find time to do the work itself",
        }),
        "wp-q4": ("Recognition Friction", "When your contribution feeds into a team outcome, how often does your specific role in that result get acknowledged?", {
            "a": "Usually — people know what I brought to it",
            "b": "Sometimes — depends on who's paying attention",
            "c": "Rarely — team results tend to flatten individual contributions",
            "d": "Almost never — I feel largely invisible in group work",
        }),
        "wp-q5": ("Work Pace", "How often do you find yourself working urgently toward a deadline that, in retrospect, wasn't actually urgent?", {
            "a": "Rarely — urgency in my environment is usually real",
            "b": "Sometimes — maybe once or twice a month",
            "c": "Regularly — manufactured urgency is part of the culture",
            "d": "Constantly — everything is treated as high priority",
        }),
        "wp-q6": ("Autonomy", "When you're given a clear goal, how much say do you have in how you actually get there?", {
            "a": "Full autonomy — I define the approach and execute it",
            "b": "Significant input — my preferences shape the method",
            "c": "Limited — I work within a fairly defined playbook",
            "d": "Very little — the process is usually dictated to me",
        }),
        "wp-q7": ("Autonomy", "How much control do you have over when and where you do your most focused work?", {
            "a": "A lot — I structure my day around how I work best",
            "b": "Some — I have flexibility but within real constraints",
            "c": "Not much — my schedule is largely set by others",
            "d": "None — I have no real say in my work structure",
        }),
        "wp-q8": ("Collaboration Style", "When it comes to doing your best work, you tend to…", {
            "a": "Work alone for most of it, then share when it's ready",
            "b": "Collaborate closely throughout — input at every stage",
            "c": "Start solo, then bring others in at key decision points",
            "d": "Think out loud with others — real-time collaboration is where I do my best thinking",
        }),
        "wp-q9": ("Feedback Orientation", "When someone gives you critical feedback on your work, your first instinct is…", {
            "a": "To listen and adapt — I find it genuinely useful",
            "b": "To understand their perspective before deciding what to do with it",
            "c": "To evaluate whether the source is credible before I weight it",
            "d": "To feel it first, then process it over time",
        }),
        "wp-q10": ("Role Clarity", "How clearly do you understand what success looks like in your current role?", {
            "a": "Very clearly — I know exactly what good looks like",
            "b": "Mostly — there are a few areas that feel ambiguous",
            "c": "Not very — success seems to shift depending on who's asking",
            "d": "Not at all — I'm often uncertain whether I'm doing well",
        }),
        "wp-q11": ("Growth Alignment", "How closely does your day-to-day work align with the skills or direction you actually want to grow in?", {
            "a": "Closely — I'm building the things I care about",
            "b": "Partially — some of it tracks, some of it doesn't",
            "c": "Not much — I'm developing skills I don't particularly want",
            "d": "Barely — my growth is almost entirely incidental",
        }),
        "wp-q12": ("Growth Alignment", "When you picture yourself two years from now, does your current work feel like it's moving you there?", {
            "a": "Yes — I can draw a clear line from here to there",
            "b": "Somewhat — I can see a path but it's indirect",
            "c": "Not really — I'm not sure this trajectory leads where I want",
            "d": "No — I feel like I'm moving in a different or unclear direction",
        }),
    }

    formatted_answers = []
    for ans in answers:
        q_id = ans.get("question_id", "")
        o_id = ans.get("option_id", "")
        if q_id not in _Q:
            continue
        dimension, question_text, option_map = _Q[q_id]
        suffix = o_id.split("-")[-1]  # "wp-q1-b" → "b"
        option_text = option_map.get(suffix, o_id)
        formatted_answers.append({
            "dimension": dimension,
            "question": question_text,
            "selected": option_text,
        })

    system = (
        "You are a work psychology analyst. Your task is to read a person's responses to a "
        "12-question Work Pulse assessment and produce a personalised, evidence-based narrative "
        "about how they work.\n\n"

        "STRICT OUTPUT RULES:\n"
        "- Return VALID JSON only. No markdown, no commentary, no extra keys.\n"
        "- The response MUST contain exactly these four keys: narrative, emerging_signals, archetype, archetype_description.\n"
        "- narrative: A multi-paragraph string (3–4 paragraphs). Write in second person ('you'). "
        "Tone: warm, direct, and specific — never generic. Each paragraph should illuminate a "
        "different aspect of how this person works. Separate paragraphs with \\n\\n.\n"
        "- emerging_signals: A list of 2–4 objects, each with 'title' (a short named pattern, "
        "3–6 words) and 'description' (1–2 sentences explaining what the signal means for this "
        "person). Ground each signal in specific answer patterns.\n"
        "- archetype: A 2–5 word label capturing this person's dominant work style, e.g. "
        "'Structured Deep Thinker' or 'Collaborative Momentum Builder'. Be specific, not generic.\n"
        "- archetype_description: A 2–3 sentence explanation of what this archetype means in "
        "practice — how this person naturally creates momentum, what environments tend to suit "
        "them, and where friction commonly emerges for someone with this pattern. Write in second "
        "person. Do not repeat the archetype label verbatim.\n\n"

        "QUALITY GUIDELINES:\n"
        "- Do not invent traits not supported by the answers.\n"
        "- Avoid hollow phrases like 'you thrive in dynamic environments'.\n"
        "- Where two dimensions interact (e.g. low autonomy + high fragmentation), name that tension.\n"
        "- The narrative should feel like it was written by someone who actually read every answer.\n"
        "- Do not provide medical, psychological, or legal advice.\n"
    )

    user_payload: dict = {"work_pulse_answers": formatted_answers}

    if wpll_answers:
        user_payload["earlier_work_pulse_lite_signals"] = wpll_answers

    if selected_statement_ids:
        user_payload["intake_statements_selected"] = selected_statement_ids

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload)},
    ]


def _build_mm_narrative_prompt(
    answers: list[dict],
    archetype: str,
    dimension_scores: dict[str, float],
) -> list[dict]:
    """Construct system + user messages for the ManagerMatch narrative OpenAI call.

    Maps each answer's question_id to human-readable option text so the model
    sees real sentences rather than IDs.

    Args:
        answers:          15 ManagerMatch answers, each {question_id, choice}.
        archetype:        The classified archetype string.
        dimension_scores: Four dimension floats from score_manager_match.

    Returns:
        Two-element list of OpenAI chat message dicts (system, user).
    """
    from manager_match.questions import QUESTIONS

    q_lookup = {q["question_id"]: q for q in QUESTIONS}

    formatted_answers = []
    for ans in answers:
        q_id = ans.get("question_id", "")
        choice = ans.get("choice", "")
        q = q_lookup.get(q_id)
        if not q:
            continue
        option_text = q["option_a_text"] if choice == "a" else q["option_b_text"]
        formatted_answers.append({
            "question_id": q_id,
            "dimension": q["dimension"],
            "selected": option_text,
        })

    system = (
        "You are Solverah's ManagerMatch engine. Based on a user's forced-choice "
        "assessment responses, generate a personalised management style analysis. "
        "Write in second person (\"you\"). Be specific — never generic. Reference "
        "patterns from their actual answers. Return a JSON object with exactly these "
        "four keys: narrative (2–3 paragraphs describing the user's management "
        "preferences and why they work that way — do not open with the archetype "
        "name), what_to_look_for (list of 3–4 concrete strings the user can probe "
        "for in interviews), red_flags (list of 2–3 management behaviours that will "
        "create friction for this person), archetype_description (2 sentences — what "
        "this archetype means in practice for this user)."
    )

    user_payload = {
        "archetype": archetype,
        "dimension_scores": {
            f"{k} (0.0–1.0)": round(v, 3) for k, v in dimension_scores.items()
        },
        "answers": formatted_answers,
    }

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload)},
    ]


def _build_wpll_insight_prompt(answers: list[dict]) -> tuple[str, str]:
    """Construct system + user messages for the Work Pulse Lite Lite insight call.

    Resolves each answer's question_id / option_id to human-readable text so the
    model receives meaningful context rather than opaque identifiers.

    Args:
        answers: Up to 5 WPLL answers, each {question_id, option_id}.

    Returns:
        (system_message, user_message) tuple of strings.
    """
    from work_pulse.insight_engine import WP_QUESTIONS

    formatted = []
    for ans in answers:
        q_id = ans.get("question_id", "")
        o_id = ans.get("option_id", "")
        q_data = WP_QUESTIONS.get(q_id)
        if not q_data:
            continue
        suffix = o_id.split("-")[-1]  # "wpll-q1-c" → "c"
        option_text = q_data["options"].get(suffix, o_id)
        formatted.append({
            "dimension": q_data["dimension"],
            "question": q_data["text"],
            "selected": option_text,
        })

    system = (
        "You are a work psychology analyst. A person just completed a 5-question "
        "assessment about how they work. Generate a brief, personal insight based on "
        "their responses.\n\n"
        "STRICT OUTPUT RULES:\n"
        "- Return VALID JSON only. No markdown, no commentary, no extra text.\n"
        "- The response must contain exactly one key: insight_text.\n"
        "- insight_text: 2–3 sentences, written in second person ('you'). "
        "Tone: warm, direct, and specific — no generic filler, no bullet points. "
        "Name the specific patterns visible in their answers.\n\n"
        "QUALITY GUIDELINES:\n"
        "- Do not invent traits not supported by the answers.\n"
        "- Avoid hollow phrases like 'you thrive in dynamic environments'.\n"
        "- The insight should feel like it was written by someone who actually read "
        "every answer — not a template.\n"
        "- Do not provide medical, psychological, or legal advice.\n"
    )

    user = json.dumps({"answers": formatted})
    return system, user


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


def _fetch_resume_text(profile_data: dict) -> str:
    """Fetch and extract resume text from S3 for use in agent context.

    Result is cached in-process for _RESUME_CACHE_TTL seconds so repeated
    calls within a chat session hit memory instead of S3. Cache key is the
    resumeKey (unique per upload), so a new upload automatically bypasses
    the old entry.

    Returns "" on any failure so callers always get a safe string.
    """
    resume_key = profile_data.get("resumeKey")
    mime = (profile_data.get("uploadedResume") or {}).get("type", "")
    if not resume_key or not mime:
        return ""

    with _resume_cache_lock:
        cached = _resume_cache.get(resume_key)
        if cached and time.monotonic() < cached[1]:
            return cached[0]

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

        text = _extract_resume_text(temp_path, mime)[:6000]
        with _resume_cache_lock:
            _resume_cache[resume_key] = (text, time.monotonic() + _RESUME_CACHE_TTL)
        return text
    except Exception:
        return ""
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


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


def default_profile(email: str = "", name: str = "") -> dict:
    """Return a blank ``profile_data`` dict pre-populated with identity fields.

    Used when registering a new user or creating an account from an intake
    submission.

    Args:
        email: User's email address — pre-fills the ``email`` field.
        name:  Full name (``"First Last"``); split into firstName/lastName.

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
        "certifications": [],
        "skills": [],
        "skill_levels": {},
        "performanceReviews": [],
        "psychometricResults": {
            "leadership": {"score": None, "percentile": None, "completed": False},
            "problemSolving": {"score": None, "percentile": None, "completed": False},
            "communication": {"score": None, "percentile": None, "completed": False},
            "creativity": {"score": None, "percentile": None, "completed": False},
            "teamwork": {"score": None, "percentile": None, "completed": False},
        },
    }

    return profile
  
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
            "profileData": user.profile_data or {},
            "wpl_completed": bool(user.intake and user.intake.wpl_completed_at),
            "wpll_completed": bool(user.intake and user.intake.wpll_completed_at),
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


from email_utils import send_confirmation_email, send_password_reset_email


@limiter.limit("3 per minute")
@app.route("/api/request-password-reset", methods=["POST"])
def request_password_reset():
    """POST /api/request-password-reset — Send a 6-digit OTP for passwordless login.

    Body (JSON):
        email (str): The user's email address.

    Returns:
        200 {"message": "reset_sent"} on success
        404 if no confirmed account found for that email
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    user = User.query.filter_by(email=email).first()
    if not user or not getattr(user, "email_confirmed", False):
        return jsonify({"error": "No account found with that email address."}), 404

    code = str(random.randint(100000, 999999))
    user.reset_token = code
    user.reset_sent_at = datetime.datetime.now(datetime.timezone.utc)
    db.session.commit()
    try:
        send_password_reset_email(user.email, code)
    except Exception as e:
        log_audit_event(action="email_send_failed", actor_user_id=user.id, resource="email", metadata={"error": str(e)})
        app.logger.error(f"request_password_reset email failed for {user.email}: {e}")
        return jsonify({"error": "Failed to send email. Please try again."}), 500

    return jsonify({"message": "reset_sent"}), 200


@limiter.limit("5 per minute")
@app.route("/api/verify-password-reset", methods=["POST"])
def verify_password_reset():
    """POST /api/verify-password-reset — Validate OTP and issue a JWT (passwordless login).

    Validates the 6-digit OTP, clears it on success, and issues a JWT cookie
    plus CSRF token so the user is fully logged in without a password.

    Body (JSON):
        email (str): User's email address.
        code  (str): 6-digit OTP from the reset email.

    Returns:
        200 {"message", "csrfToken", "user": {...}} + JWT cookie
        400 on missing fields, invalid code, or expired code
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()

    if not email or not code:
        return jsonify({"error": "email and code are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.reset_token:
        return jsonify({"error": "invalid_or_expired_code"}), 400

    exp_minutes = int(os.environ.get("VERIFY_CODE_EXP_MINUTES", "15"))
    sent_at_utc = user.reset_sent_at.replace(tzinfo=datetime.timezone.utc) if user.reset_sent_at else None
    if not sent_at_utc or sent_at_utc + datetime.timedelta(minutes=exp_minutes) < datetime.datetime.now(datetime.timezone.utc):
        return jsonify({"error": "invalid_or_expired_code"}), 400

    if user.reset_token != code:
        return jsonify({"error": "invalid_or_expired_code"}), 400

    user.reset_token = None
    user.reset_sent_at = None
    db.session.commit()

    access_token = create_access_token(identity=user.email)
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
    set_access_cookies(resp, access_token)
    return resp


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
    Returns:
        201 {"message": "registered", "user": {...}}
        400 on invalid password or duplicate email
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = data.get("name")
    role = "job-seeker"

    is_valid, validation_message = validate_password(password)
    if not is_valid:
        return jsonify({"error": validation_message}), 400

    #Check user exsistence off of email
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User already exists"}), 400

    hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
    profile_data = default_profile(email=email, name=name)


    # Create user with 6-digit verification code
    code = str(random.randint(100000, 999999))
    new_user = User(
        email=email,
        password=hashed_pw,
        name=data.get("name"),
        role=role,
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
            "wpl_completed": bool(user.intake and user.intake.wpl_completed_at),
            "wpll_completed": bool(user.intake and user.intake.wpll_completed_at),
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
    if profile_data.keys() & {"experience", "skills", "skill_levels"}:
        _invalidate_path_suggestions_cache(user.id)

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

@app.route("/api/profile/career-status", methods=["PATCH"])
@jwt_required()
def set_career_status():
    """PATCH /api/profile/career-status — Directly set the user's career_status.

    Lets the frontend set career status with a single targeted request rather
    than a full profile save.  Used by the career-status onboarding modal so
    the user can pick a status without filling in experience entries.

    Request body:
        { "status": "employed" | "between_jobs" | "first_job" }

    Returns:
        200 {"career_status": str}
        400 {"error": "invalid_status"}
    """
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json() or {}
    status = data.get("status")

    valid = {"employed", "between_jobs", "first_job"}
    if status not in valid:
        return jsonify({"error": "invalid_status"}), 400

    profile_data = dict(user.profile_data or {})
    profile_data["career_status"] = status
    user.profile_data = profile_data
    db.session.commit()

    return jsonify({"career_status": status}), 200


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



@limiter.limit("10 per minute")
@app.route("/api/intake/save-to-account", methods=["POST"])
@jwt_required()
def intake_save_to_account():
    """POST /api/intake/save-to-account — Persist anonymous WPLL session data to
    the authenticated user's account.

    Called by the frontend immediately after login when sessionStorage contains
    intake data from the /start flow. Creates the user_intake row on first call;
    upserts on subsequent calls (preserves wpl_* fields if already set).

    Body (JSON):
        selected_statement_ids (list[str])
        wpll_answers           (list[{question_id: str, option_id: str}])
        wpll_insight_text      (str, optional)

    Returns:
        200 {"message": "Intake saved", "wpll_completed": bool}
        400 on validation failure
        404 if user not found
    """
    from model import UserIntake

    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    selected_ids = data.get("selected_statement_ids", [])
    wpll_answers = data.get("wpll_answers", [])
    wpll_insight_text = data.get("wpll_insight_text", "") or ""

    if not isinstance(selected_ids, list):
        return jsonify({"error": "selected_statement_ids must be a list"}), 400
    if not isinstance(wpll_answers, list):
        return jsonify({"error": "wpll_answers must be a list"}), 400
    if len(wpll_answers) > 5:
        return jsonify({"error": "wpll_answers must contain at most 5 items"}), 400

    now = datetime.datetime.now(datetime.timezone.utc)
    intake = UserIntake.query.filter_by(user_id=user.id).first()

    if intake is None:
        intake = UserIntake(
            user_id=user.id,
            selected_statement_ids=selected_ids,
            wpll_answers=wpll_answers,
            wpll_insight_text=wpll_insight_text or None,
            wpll_completed_at=now if wpll_answers else None,
        )
        db.session.add(intake)
    else:
        intake.selected_statement_ids = selected_ids
        intake.wpll_answers = wpll_answers
        intake.wpll_insight_text = wpll_insight_text or None
        # Only set wpll_completed_at on first save; preserve if already set.
        if wpll_answers and intake.wpll_completed_at is None:
            intake.wpll_completed_at = now
        # Never overwrite wpl_answers / wpl_narrative / wpl_completed_at here —
        # those are set by the Sprint 2 WPL submit endpoint.

    log_audit_event(
        action="create",
        actor_user_id=user.id,
        resource="user_intake",
        metadata={
            "statement_count": len(selected_ids),
            "answer_count": len(wpll_answers),
        },
    )
    db.session.commit()

    return jsonify({
        "message": "Intake saved",
        "wpll_completed": intake.wpll_completed_at is not None,
    }), 200


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
        actor_user_id=user.id,
        resource="intake",
        metadata={"submission_id": submission_id, "email": current_email},
    )

    return jsonify({"ok": True})


@limiter.limit("30 per minute")
@app.route("/api/recommendations", methods=["GET"])
@jwt_required()
def get_recommendations():
    """GET /api/recommendations — Return persisted job recommendations for the user.

    The ML pipeline that generated these has been replaced by the AI agent.
    Returns an empty list until a Groq-based recommendation flow is wired up.
    """
    return jsonify({"recommendations": []})


@limiter.limit("10 per minute")
@app.route("/api/recommendations", methods=["POST"])
@jwt_required()
def generate_recommendations():
    """POST /api/recommendations — Trigger job recommendation generation.

    Accepts a profilePipeline payload but is currently a no-op stub while the
    Groq-based recommendation flow is being built.
    """
    return jsonify({"recommendations": []})


@limiter.limit("30 per minute")
@app.route("/api/agent/chat", methods=["POST"])
@jwt_required()
def agent_chat():
    """POST /api/agent/chat — Stream a chat turn from Groq with RAG context.

    Assembles a system prompt from the authenticated user's profile and company
    data, prepends it to the supplied message history, and streams the response
    as Server-Sent Events so the UI can render tokens as they arrive.

    Body (JSON):
        messages (list): Full conversation history as [{role, content}, ...].
            Must contain at least one entry.
        model (str, optional): Groq model name. Defaults to "llama-3.1-8b-instant".

    Returns:
        200 text/event-stream  data: {"chunk": str} per token, then data: {"done": true, "model": str}
        400 if messages is missing or empty
        422 if requested model is not available on Groq
        503 if Groq is unreachable
    """
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first_or_404()

    data = request.get_json(silent=True) or {}
    messages = data.get("messages")
    if not messages or not isinstance(messages, list) or len(messages) == 0:
        return jsonify({"error": "messages must be a non-empty list"}), 400

    model = (data.get("model") or _default_agent_model()).strip()
    resume_text = _fetch_resume_text(user.profile_data or {})
    system_prompt = _build_agent_context(user, resume_text=resume_text)
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    try:
        client = _get_agent_client()
        stream = client.chat.completions.create(model=model, messages=full_messages, stream=True)
    except Exception as exc:
        app.logger.error("agent_chat error: %s: %s", type(exc).__name__, exc)
        exc_type = type(exc).__name__.lower()
        exc_str = str(exc).lower()
        if "not found" in exc_str or "notfounderror" in exc_type:
            return jsonify({"error": f"Model '{model}' not found on Groq."}), 422
        is_connection_err = any(kw in exc_str or kw in exc_type for kw in (
            "connection", "refused", "timeout", "unreachable", "apiconnection",
        ))
        if is_connection_err:
            return jsonify({"error": "AI service unavailable — Groq"}), 503
        return jsonify({"error": "Failed to generate response"}), 500

    def generate():
        try:
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield f"data: {json.dumps({'chunk': delta})}\n\n"
            yield f"data: {json.dumps({'done': True, 'model': model})}\n\n"
        except Exception as exc:
            app.logger.error("agent_chat stream error: %s: %s", type(exc).__name__, exc)
            yield f"data: {json.dumps({'error': 'Stream interrupted'})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/work-pulse/lite-lite/result", methods=["POST"])
def work_pulse_lite_lite_result():
    """POST /api/work-pulse/lite-lite/result — LLM-powered insight for the WPLL teaser.

    Anonymous endpoint — no auth required. Calls OpenAI to generate a personalised
    2–3 sentence insight from the 5 WPLL answers, then returns it alongside the
    fixed set of locked section titles shown on the result screen.  Falls back
    silently to the rules-based engine if the LLM call fails or returns a
    malformed response.

    Body (JSON):
        answers (list): 1–5 objects with ``question_id`` and ``option_id``.

    Returns:
        200 {"insight_text": str, "locked_sections": [str, str, str]}
        400 if answers is missing, empty, not a list, or contains more than 5 items
    """
    from work_pulse.insight_engine import generate_result, LOCKED_SECTION_TITLES

    data = request.get_json(silent=True) or {}
    answers = data.get("answers", [])

    if not isinstance(answers, list):
        return jsonify({"error": "answers must be a list"}), 400

    if len(answers) == 0:
        return jsonify({"error": "answers is required"}), 400

    if len(answers) > 5:
        return jsonify({"error": "Too many answers"}), 400

    insight_text = None
    try:
        system_msg, user_msg = _build_wpll_insight_prompt(answers)
        client = _get_openai_client()
        model = os.environ.get("OPENAI_WPLL_MODEL", "gpt-4o-mini")
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or ""
        parsed = json.loads(content)
        candidate = parsed.get("insight_text")
        if isinstance(candidate, str) and candidate.strip():
            insight_text = candidate
    except Exception:
        pass

    if insight_text is None:
        fallback = generate_result(answers)
        return jsonify(fallback), 200

    return jsonify({
        "insight_text": insight_text,
        "locked_sections": LOCKED_SECTION_TITLES,
    }), 200


@limiter.limit("5 per minute")
@app.post("/api/work-pulse/submit")
@jwt_required()
def work_pulse_submit():
    """POST /api/work-pulse/submit — Generate and persist a Work Pulse narrative (authenticated).

    Validates the 12 WP answers, calls OpenAI with a structured prompt that
    optionally incorporates earlier WPLL signals from the user's intake row,
    then persists the answers and narrative to ``user_intake``.

    Body (JSON):
        answers (list): Exactly 12 objects with ``question_id`` and ``option_id``.

    Returns:
        200 {"narrative": str, "emerging_signals": [...], "archetype": str}
        400 on missing or wrong-length answers
        401 if unauthenticated
        404 if user not found
        500 on OpenAI failure or malformed model response
    """
    from model import UserIntake

    data = request.get_json(silent=True) or {}
    answers = data.get("answers")

    if not isinstance(answers, list) or len(answers) != 12:
        return jsonify({"error": "answers must be a list of exactly 12 items"}), 400

    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Load or create the intake row — same upsert pattern as intake_save_to_account.
    # Flush immediately after the INSERT so a concurrent duplicate request raises
    # IntegrityError here rather than at commit (after the expensive LLM call).
    from sqlalchemy.exc import IntegrityError
    intake = UserIntake.query.filter_by(user_id=user.id).first()
    if intake is None:
        intake = UserIntake(user_id=user.id)
        db.session.add(intake)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            intake = UserIntake.query.filter_by(user_id=user.id).first()

    wpll_answers = intake.wpll_answers or None
    selected_statement_ids = intake.selected_statement_ids or None

    try:
        client = _get_openai_client()
        model = os.environ.get("OPENAI_WP_MODEL", "gpt-4o-mini")
        messages = _build_wp_narrative_prompt(
            answers,
            wpll_answers=wpll_answers,
            selected_statement_ids=selected_statement_ids,
        )
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
    except Exception:
        app.logger.exception("Work Pulse narrative generation failed")
        return jsonify({"error": "Unable to generate Work Pulse results"}), 500

    if not all(k in result for k in ("narrative", "emerging_signals", "archetype", "archetype_description")):
        return jsonify({"error": "Malformed response from model"}), 500

    now = datetime.datetime.now(datetime.timezone.utc)

    # Commit 1: persist answers and mark the user as WP-complete.
    # This must succeed before we attempt to store the narrative so that
    # wpl_completed_at is always written even if the wpl_result column is
    # missing (e.g. a pending migration) or the second commit fails for any
    # other reason.
    intake.wpl_answers = answers
    intake.wpl_completed_at = now

    from work_pulse.derive_preferences import derive_culture_preferences
    culture_prefs = derive_culture_preferences(answers)
    profile = dict(user.profile_data or {})
    profile["culture_preferences"] = culture_prefs
    user.profile_data = profile

    db.session.commit()

    # Commit 2: store the full narrative/result blob (best-effort).
    # If this fails (e.g. wpl_result column not yet migrated) the user is
    # still marked complete; they will see an error on the results page and
    # can retry narrative generation after running flask db upgrade.
    try:
        intake.wpl_narrative = result["narrative"]
        intake.wpl_result = result
        db.session.commit()
        _invalidate_path_suggestions_cache(user.id)
    except Exception:
        db.session.rollback()
        app.logger.exception("Work Pulse: failed to persist narrative/result blob")

    return jsonify(result)


@limiter.limit("5 per minute")
@app.post("/api/focus-type/submit")
@jwt_required()
def focus_type_submit():
    """POST /api/focus-type/submit — Score and persist a FocusType result (authenticated).

    Accepts the 5 scene payloads, runs deterministic scoring, and persists the
    archetype result to ``user.profile_data["focus_type_result"]``.

    Body (JSON):
        scene_1 (list): Card IDs in priority order.
        scene_2 (dict): {"now": [...], "later": [...], "ignore": [...]}.
        scene_3 (dict): {"deep_solo": float, "planning": float, "social": float,
                         "breaks": float, "exploring": float}.
        scene_4 (dict): {"now": [...], "tomorrow": [...], "avg_decision_time_ms": int}.
        scene_5 (list): Block IDs in timeline order.

    Returns:
        200 {"archetype": str, "dimension_scores": {...}, "recommendations": [...]}
        400 if any scene payload is missing
        401 if unauthenticated
        404 if user not found
    """
    from focus_type.score import score_focus_type

    data = request.get_json(silent=True) or {}
    missing = [f"scene_{i}" for i in range(1, 6) if f"scene_{i}" not in data]
    if missing:
        return jsonify({"error": f"Missing scene payloads: {', '.join(missing)}"}), 400

    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    result = score_focus_type(
        data["scene_1"],
        data["scene_2"],
        data["scene_3"],
        data["scene_4"],
        data["scene_5"],
    )

    profile = dict(user.profile_data or {})
    profile["focus_type_result"] = result
    user.profile_data = profile
    db.session.commit()
    _invalidate_path_suggestions_cache(user.id)

    return jsonify(result)


@app.get("/api/work-pulse/results")
@jwt_required()
def work_pulse_results_get():
    """GET /api/work-pulse/results — Retrieve persisted Work Pulse results for the current user.

    Returns the stored narrative, emerging signals, and archetype from the user's
    most recent Work Pulse submission. Used by the results page to rehydrate
    state in fresh browser sessions where sessionStorage has been cleared.

    Returns:
        200 {"narrative": str, "emerging_signals": [...], "archetype": str}
        404 if no completed WP results are available
        401 if unauthenticated
    """
    from model import UserIntake

    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    intake = UserIntake.query.filter_by(user_id=user.id).first()
    if not intake or not intake.wpl_completed_at:
        return jsonify({"error": "No Work Pulse results found"}), 404
    if not intake.wpl_result:
        # Answers saved but narrative blob missing (e.g. wpl_result column not yet
        # migrated). Tell the client to resubmit so narrative can be regenerated.
        return jsonify({"error": "Work Pulse results pending — please resubmit"}), 422

    return jsonify(intake.wpl_result)


@limiter.limit("5 per minute")
@app.post("/api/manager-match/submit")
@jwt_required()
def manager_match_submit():
    """POST /api/manager-match/submit — Score and persist a ManagerMatch result (authenticated).

    Validates 15 forced-choice answers, runs deterministic scoring, calls OpenAI
    to generate a personalised narrative, then persists the full result to
    ``user.profile_data["manager_match_result"]``.

    Body (JSON):
        answers (list): Exactly 15 objects with ``question_id`` and ``choice`` ("a"|"b").

    Returns:
        200 {"archetype": str, "dimension_scores": {...}, "narrative": str,
             "what_to_look_for": [...], "red_flags": [...], "archetype_description": str}
        400 on missing, wrong-length, or invalid answers
        401 if unauthenticated
        404 if user not found
        500 on OpenAI failure or malformed model response
    """
    from manager_match.score import score_manager_match

    data = request.get_json(silent=True) or {}
    answers = data.get("answers")

    if not isinstance(answers, list) or len(answers) != 15:
        return jsonify({"error": "answers must be a list of exactly 15 items"}), 400

    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        scoring = score_manager_match(answers)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        client = _get_openai_client()
        model = os.environ.get("OPENAI_WP_MODEL", "gpt-4o-mini")
        messages = _build_mm_narrative_prompt(
            answers, scoring["archetype"], scoring["dimension_scores"]
        )
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        llm_result = json.loads(content)
    except Exception:
        app.logger.exception("ManagerMatch narrative generation failed")
        return jsonify({"error": "Unable to generate ManagerMatch results"}), 500

    required_keys = ("narrative", "what_to_look_for", "red_flags", "archetype_description")
    if not all(k in llm_result for k in required_keys):
        return jsonify({"error": "Malformed response from model"}), 500

    result = {**scoring, **llm_result}

    profile = dict(user.profile_data or {})
    profile["manager_match_result"] = result
    user.profile_data = profile
    db.session.commit()
    _invalidate_path_suggestions_cache(user.id)

    return jsonify(result), 200


@app.get("/api/manager-match/results")
@jwt_required()
def manager_match_results_get():
    """GET /api/manager-match/results — Retrieve persisted ManagerMatch result for the current user.

    Returns:
        200 with the stored result dict
        404 if no result has been saved yet
        401 if unauthenticated
    """
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    result = (user.profile_data or {}).get("manager_match_result")
    if result is None:
        return jsonify({"error": "No ManagerMatch result found"}), 404

    return jsonify(result)


@app.get("/api/companies/<int:company_id>")
@jwt_required()
def company_detail(company_id: int):
    """GET /api/companies/<company_id> — Return a company's full profile.

    Returns:
        200 {"id", "name", "slug", "profile": {...full CompanyProfile dict...}}
        404 if the company does not exist
        401 if unauthenticated
    """
    company = Company.query.get(company_id)
    if company is None:
        return jsonify({"error": "Company not found"}), 404
    return jsonify({
        "id": company.id,
        "name": company.name,
        "slug": company.slug,
        "profile": company.profile_json,
    })


_DIM_LABELS: dict[str, str] = {
    "empathy": "empathy",
    "creative_drive": "creative drive",
    "adaptability": "adaptability",
    "futuristic": "future orientation",
    "harmony": "harmony",
    "data_orientation": "data orientation",
    "pace": "work pace",
    "work_environment": "work environment",
}


def _build_fit_summary(matching: list[str], mismatching: list[str]) -> str:
    match_str = " and ".join(_DIM_LABELS.get(d, d) for d in matching)
    mismatch_str = " and ".join(_DIM_LABELS.get(d, d) for d in mismatching)
    if mismatching:
        return f"Strong alignment on {match_str}; potential friction around {mismatch_str}."
    return f"Strong alignment on {match_str}."


@app.get("/api/company-lens/matches")
@jwt_required()
def company_lens_matches():
    """GET /api/company-lens/matches — Score all companies against the user's culture preferences.

    Query params:
        limit (int, default 5, min 1, max 50): Number of best/worst matches to return.

    Returns:
        200 {"best_fits": [...], "worst_fits": [...], "total_companies_scored": int, "limit": int}
        400 if culture_preferences have not been set (Work Pulse not completed)
        401 if unauthenticated
    """
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    profile = user.profile_data or {}
    user_prefs = profile.get("culture_preferences")
    if not user_prefs:
        # Backfill for users who completed WP before culture_preferences was stored.
        from model import UserIntake
        intake = UserIntake.query.filter_by(user_id=user.id).first()
        if intake and intake.wpl_answers:
            from work_pulse.derive_preferences import derive_culture_preferences
            user_prefs = derive_culture_preferences(intake.wpl_answers)
            profile = dict(profile)
            profile["culture_preferences"] = user_prefs
            user.profile_data = profile
            db.session.commit()
        else:
            return jsonify({"error": "Work Pulse not completed — culture preferences not found"}), 400

    try:
        limit = int(request.args.get("limit", 5))
    except (TypeError, ValueError):
        return jsonify({"error": "limit must be an integer"}), 400
    limit = max(1, min(50, limit))

    companies = all_companies()

    scored = []
    for company in companies:
        if company.pace is None:
            continue
        try:
            culture_values = CultureValues(
                work_environment=company.work_environment,
                pace=company.pace,
                empathy=company.empathy,
                creative_drive=company.creative_drive,
                adaptability=company.adaptability,
                futuristic=company.futuristic,
                harmony=company.harmony,
                data_orientation=company.data_orientation,
            )
            fit = culture_fit_score(culture_values, user_prefs)
        except Exception:
            app.logger.warning("Skipping company %s — invalid culture data", company.id)
            continue
        scored.append((company, fit))

    scored.sort(key=lambda x: x[1].total_score, reverse=True)
    total = len(scored)

    if total <= 2 * limit:
        mid = (total + 1) // 2
        best_rows = scored[:mid]
        worst_rows = scored[mid:]
    else:
        best_rows = scored[:limit]
        worst_rows = scored[-limit:][::-1]

    def _format_entry(company, fit):
        dim_scores = fit.dimension_scores
        sorted_dims = sorted(dim_scores.items(), key=lambda kv: kv[1], reverse=True)
        matching = [d for d, _ in sorted_dims[:2]]
        mismatching = [d for d, _ in sorted_dims[-2:]] if len(sorted_dims) >= 2 else []
        overview = (company.profile_json or {}).get("overview") or {}
        return {
            "id": company.id,
            "name": company.name,
            "slug": company.slug,
            "industry": overview.get("industry"),
            "fit_score": fit.total_score,
            "top_matching_dimensions": matching,
            "top_mismatching_dimensions": mismatching,
            "fit_summary": _build_fit_summary(matching, mismatching),
        }

    return jsonify({
        "best_fits": [_format_entry(c, r) for c, r in best_rows],
        "worst_fits": [_format_entry(c, r) for c, r in worst_rows],
        "total_companies_scored": total,
        "limit": limit,
    })


@app.post("/api/intelligence/path-preferences")
@jwt_required()
def save_path_preferences():
    """POST /api/intelligence/path-preferences — Save the user's career search preferences.

    Body: {"move_intent": str, "seniority_intent": str, "priority": str}

    Returns:
        200 {"message": "Preferences saved"}
        400 if any field has an invalid value or is missing
        401 if unauthenticated
        404 if user not found
    """
    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json() or {}
    move_intent = data.get("move_intent")
    seniority_intent = data.get("seniority_intent")
    priority = data.get("priority")

    valid_move = {"stay_in_field", "adjacent", "fresh_start"}
    valid_seniority = {"move_up", "stay_lateral", "open"}
    valid_priority = {"pay_title", "interesting_work", "work_life_balance", "learning_growth"}

    if move_intent not in valid_move:
        return jsonify({"error": "Invalid move_intent"}), 400
    if seniority_intent not in valid_seniority:
        return jsonify({"error": "Invalid seniority_intent"}), 400
    if priority not in valid_priority:
        return jsonify({"error": "Invalid priority"}), 400

    profile = dict(user.profile_data or {})
    profile["path_preferences"] = {
        "move_intent": move_intent,
        "seniority_intent": seniority_intent,
        "priority": priority,
    }
    user.profile_data = profile
    db.session.commit()

    _invalidate_path_suggestions_cache(user.id)
    return jsonify({"message": "Preferences saved"}), 200


@app.get("/api/intelligence/path-suggestions")
@jwt_required()
def path_suggestions():
    """GET /api/intelligence/path-suggestions — Score and narrate career path suggestions for the current user.

    Orchestrates path_scoring.score_paths and path_narrative.generate_narratives,
    caching the result per user.  The cache is invalidated when the user's
    WorkPulse results, experience entries, or ManagerMatch results are updated.

    Returns:
        200 {"suggestions": [...], "career_status": str, "generated_at": str}
        400 {"error": "career_status_not_set"} if career_status has not been saved
        401 if unauthenticated
        404 if user not found
        500 on scoring or narrative generation failure
    """
    from backend.services.path_scoring import UserProfile, UserSkill, score_paths
    from backend.services.path_narrative import (
        NarrativeGenerationError,
        UserContext,
        _get_openai_client,
        generate_narratives,
    )
    from backend.services.onet_client import OnetClient

    current_email = get_jwt_identity()
    user = User.query.filter_by(email=current_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    with _path_suggestions_cache_lock:
        cached = _path_suggestions_cache.get(user.id)
    if cached is not None:
        return jsonify(cached)

    profile = user.profile_data or {}
    career_status = profile.get("career_status")
    if not career_status:
        # Try to derive from experience before giving up.  If any entry has
        # endDate of "Present" or "Current" the user is employed — set it and
        # persist so future calls skip this derivation step entirely.
        experience = profile.get("experience") or []
        has_current = any(
            str(exp.get("endDate", "")).strip().lower() in ("present", "current")
            for exp in experience
            if isinstance(exp, dict)
        )
        if has_current:
            career_status = "employed"
            updated = dict(profile)
            updated["career_status"] = career_status
            user.profile_data = updated
            db.session.commit()
        else:
            return jsonify({"error": "career_status_not_set"}), 400

    skills_raw: list = profile.get("skills") or []
    skill_levels: dict = profile.get("skill_levels") or {}
    user_skills = [
        UserSkill(name=s, level=skill_levels.get(s, "beginner"))
        for s in skills_raw
        if isinstance(s, str)
    ]

    archetype = ""
    archetype_description = ""
    intake = user.intake
    if intake and intake.wpl_result and isinstance(intake.wpl_result, dict):
        archetype = intake.wpl_result.get("archetype", "")
        # The multi-sentence description embeds far more meaningfully than the
        # short label against O*NET work-activity language.
        archetype_description = intake.wpl_result.get("archetype_description", "")

    focus_type: str | None = None
    focus_type_result: dict = profile.get("focus_type_result") or {}
    if focus_type_result:
        # FocusType scoring produces no rich description — fall back to the label.
        focus_type = focus_type_result.get("archetype") or None

    manager_match_desc: str | None = None
    manager_match_result: dict = profile.get("manager_match_result") or {}
    if manager_match_result:
        # Prefer the LLM-generated description over the short archetype label.
        manager_match_desc = (
            manager_match_result.get("archetype_description")
            or manager_match_result.get("archetype")
            or None
        )

    work_style_tags: list[str] = []
    if intake and intake.wpl_result and isinstance(intake.wpl_result, dict):
        signals = intake.wpl_result.get("emerging_signals") or []
        # Use description sentences — they embed meaningfully against O*NET work
        # activities; short title labels ("Independent Worker") do not.
        work_style_tags = [
            s.get("description") or s.get("title", "")
            for s in signals
            if isinstance(s, dict) and (s.get("description") or s.get("title"))
        ]

    current_title: str | None = None
    experience: list = profile.get("experience") or []
    if experience and career_status != "first_job":
        first_exp = experience[0] if isinstance(experience[0], dict) else {}
        current_title = first_exp.get("position") or first_exp.get("title") or None

    path_preferences: dict = profile.get("path_preferences") or {}
    move_intent: str | None = path_preferences.get("move_intent")
    seniority_intent: str | None = path_preferences.get("seniority_intent")
    priority: str | None = path_preferences.get("priority")

    user_profile = UserProfile(
        current_title=current_title,
        career_status=career_status,
        skills=user_skills,
        archetype=archetype,
        archetype_description=archetype_description,
        move_intent=move_intent,
        seniority_intent=seniority_intent,
        priority=priority,
        focus_type=focus_type,
        manager_match=manager_match_desc,
        work_style_tags=work_style_tags,
    )

    try:
        onet_client = OnetClient()
        try:
            openai_client = _get_openai_client()
        except RuntimeError:
            openai_client = None
        scored = score_paths(user_profile, onet_client, openai_client)
    except Exception:
        app.logger.exception("Path scoring failed for user %s", user.id)
        return jsonify({"error": "Unable to score career paths"}), 500

    if not scored:
        # Profile is complete but O*NET returned nothing — treat as a
        # transient service issue rather than a profile problem.
        app.logger.warning("Empty scored list for user %s (title=%r, skills=%d)", user.id, current_title, len(user_skills))
        return jsonify({"error": "Unable to score career paths"}), 500

    manager_match_result: dict = profile.get("manager_match_result") or {}
    top_skills = [s for s in skills_raw[:5] if isinstance(s, str)]

    user_context = UserContext(
        archetype=archetype,
        management_preferences=manager_match_result,
        career_status=career_status,
        top_skills=top_skills,
        move_intent=move_intent,
        seniority_intent=seniority_intent,
        priority=priority,
    )

    try:
        suggestions = generate_narratives(scored, user_context)
    except NarrativeGenerationError:
        app.logger.exception("Path narrative generation failed for user %s", user.id)
        return jsonify({"error": "Unable to generate path narratives"}), 500

    score_map = {sp.onet_code: sp.score for sp in scored}

    payload = {
        "suggestions": [
            {
                "onet_code": s.onet_code,
                "title": s.title,
                "why_text": s.why_text,
                "profile_dimensions": s.profile_dimensions,
                "match_score": score_map.get(s.onet_code, 0.0),
            }
            for s in suggestions
        ],
        "career_status": career_status,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with _path_suggestions_cache_lock:
        _path_suggestions_cache[user.id] = payload

    return jsonify(payload)


if __name__ == "__main__":
    app.run(debug=True)
