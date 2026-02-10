from flask import Flask, jsonify, request
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
    set_access_cookies,
    unset_jwt_cookies,
)
from flask_talisman import Talisman

import os
import json
import uuid
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
    return " ".join(value.split())


def _is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(email))


def _is_valid_phone(phone: str) -> bool:
    return bool(PHONE_PATTERN.match(phone))


def _is_valid_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _is_valid_linkedin_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.netloc in LINKEDIN_ALLOWED_HOSTS

#from LLM.profile2model import sorted_mlscores

from flask_migrate import Migrate

from model import AuditLog, IntakeSubmission, JobRecommendation, User, db
from datetime import timedelta
import pandas as pd

#from LLM.profile2model import jobs_path

# from geo_utils import geocode_city, haversine_miles


app = Flask(__name__)
from security import init_rate_limiter
from validators import validate_password, clean_profile_data

from flask_cors import CORS


def _is_production():
    env_name = (
        os.environ.get("FLASK_ENV")
        or os.environ.get("APP_ENV")
        or os.environ.get("ENV")
        or ""
    )
    return env_name.lower() in {"production", "prod"}


def _parse_bool_env(value, default):
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
            "https://www.solverah.com"
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
app.config["JWT_COOKIE_CSRF_PROTECT"] = True  # Set to True to enable CSRF protection when done setting up
app.config["JWT_CSRF_METHODS"] = ["POST", "PUT", "PATCH", "DELETE"]
app.config["JWT_CSRF_HEADER_NAME"] = "X-CSRF-TOKEN"


db.init_app(app)
migrate = Migrate(app, db)


bcrypt = Bcrypt(app)
jwt = JWTManager(app)

limiter = init_rate_limiter(app)

MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))

# Helper function to get a new DB connection
def get_db_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)

# Helper function to get S3 client
def get_s3_client():
    # Cloudflare R2 is S3-compatible
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("S3_REGION", "auto"),
    )


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _get_openai_client():
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK not installed")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)


def _build_quiz_insight_prompt(quiz_group: str, quizzes: list[dict]) -> list[dict]:
    system = (
        "You are an expert career insights engine designed to analyze structured quiz responses "
        "and extract meaningful career-related patterns.\n\n"
        
        "PRIMARY OBJECTIVE:\n"
        "Synthesize answers across quizzes into high-signal insights that help a user better "
        "understand their work preferences, strengths, and potential career directions.\n\n"

        "STRICT RULES:\n"
        "- Output VALID JSON only. Do not include markdown, commentary, or extra text.\n"
        "- Do NOT invent traits, preferences, or experiences not supported by the input.\n"
        "- Do NOT provide medical, psychological, or legal advice.\n"
        "- Avoid generic career advice that could apply to anyone.\n"
        "- Focus on PATTERNS and INTERSECTIONS across answers rather than summarizing individual responses.\n"
        "- Maintain a professional, supportive, and non-judgmental tone.\n"
        "- Be concise but information-dense.\n"

        "INSIGHT QUALITY GUIDELINES:\n"
        "- Each insight should reveal something the user may not have explicitly recognized.\n"
        "- Prefer specificity over broad statements.\n"
        "- Recommendations must be practical and immediately actionable.\n"
    )
    user_payload = {
        "quiz_group": quiz_group,
        "quizzes": quizzes,
        "output_rules": {
            "tone": "clear, supportive, non-judgmental",
            "length": "short but meaningful",
            "key_takeaways_count": "3-5",
            "next_steps_count": "2-4",
        },
        "output_format": {
            "overallSummary": "string",
            "insights": [
                {
                    "key": "string",
                    "title": "string",
                    "summary": "string",
                    "keyTakeaways": ["string"],
                    "combinedMeaning": "string",
                    "nextSteps": ["string"],
                }
            ],
        },
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload)},
    ]


def _coerce_insight_payload(payload: dict, quiz_group: str, fallback_quizzes: list[dict]) -> dict:
    if not isinstance(payload, dict):
        return {}
    insights = payload.get("insights")
    overall = payload.get("overallSummary") if isinstance(payload.get("overallSummary"), str) else None

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

    return {"overallSummary": overall, "insights": normalized}


def _extract_resume_text(file_path: Path, mime: str) -> str:
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


# Helper to log audit events
def log_audit_event(action, actor_user_id, resource, metadata=None):
    audit = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource=resource,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
        event_metadata=metadata or {},
    )
    db.session.add(audit)

# Endpoint to get presigned upload URL
@limiter.limit("10 per minute")
@app.post("/api/intake/presign")
def presign():
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

# Endpoint to finalize intake submission
@limiter.limit("20 per minute")
@app.post("/api/intake/finalize")
def finalize():
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

    return jsonify({"ok": True})


@limiter.limit("5 per minute")
@app.post("/api/intake/create-account")
def intake_create_account():
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
        confirmation_sent_at=datetime.datetime.utcnow(),
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

    if user.locked_until and user.locked_until > datetime.datetime.utcnow():
        return jsonify({"error": "Account locked. Try again later."}), 423

    if not bcrypt.check_password_hash(user.password, password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
            user.locked_until = datetime.datetime.utcnow() + datetime.timedelta(
                minutes=LOGIN_LOCKOUT_MINUTES
            )
            user.failed_login_attempts = 0
        db.session.commit()
        return jsonify({"error": "Invalid credentials"}), 401

    user.failed_login_attempts = 0
    user.locked_until = None

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
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
    })
    set_access_cookies(resp, access_token)

    return resp


#Helper function for inital setup of profile on registration
def default_profile(email="", name="", role="job-seeker"):
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
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if user and user.locked_until and user.locked_until > datetime.datetime.utcnow():
        return jsonify({"error": "Account locked. Try again later."}), 423

    if not user or not bcrypt.check_password_hash(user.password, password):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.datetime.utcnow() + datetime.timedelta(
                    minutes=LOGIN_LOCKOUT_MINUTES
                )
                user.failed_login_attempts = 0
            db.session.commit()
        return jsonify({"error": "Invalid credentials"}), 401

    # Reset failed attempts and clear lockout
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()

    # Require email confirmation; resend confirmation on login attempt
    if not getattr(user, "email_confirmed", False):
        token = uuid.uuid4().hex
        user.confirmation_token = token
        user.confirmation_sent_at = datetime.datetime.utcnow()
        db.session.commit()
        try:
            send_confirmation_email(user.email, token)
        except Exception:
            log_audit_event(
                action="email_send_failed",
                actor_user_id=user.id,
                resource="email",
                metadata={"context": "login_resend_confirmation"},
            )
            db.session.commit()
        return jsonify({"error": "Email not confirmed. Confirmation email resent."}), 403

    access_token = create_access_token(identity=user.email)

    # Build JSON response
    resp = jsonify({
        "message": "login successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        }
        # can omit "token" now, since it's in the cookie
    })

    # Attach JWT as HttpOnly cookie
    set_access_cookies(resp, access_token)

    return resp

@app.route("/api/logout", methods=["POST"])
def logout():
    resp = jsonify({"message": "logout successful"})
    unset_jwt_cookies(resp)
    return resp


# Email confirmation endpoints
@limiter.limit("5 per minute")
@app.route("/api/confirm-email", methods=["POST"])
def confirm_email():
    data = request.get_json() or {}
    token = (data.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token required"}), 400

    user = User.query.filter_by(confirmation_token=token).first()
    if not user:
        return jsonify({"error": "invalid token"}), 404

    # Check expiry
    exp_hours = int(os.environ.get("CONFIRM_TOKEN_EXP_HOURS", "48"))
    if not user.confirmation_sent_at or user.confirmation_sent_at + datetime.timedelta(hours=exp_hours) < datetime.datetime.utcnow():
        return jsonify({"error": "token expired"}), 400

    user.email_confirmed = True
    user.confirmation_token = None
    user.confirmation_sent_at = None
    db.session.commit()

    return jsonify({"message": "email confirmed"}), 200


@limiter.limit("5 per minute")
@app.route("/api/resend-confirmation", methods=["POST"])
def resend_confirmation():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email or not _is_valid_email(email):
        return jsonify({"error": "Valid email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Account not found"}), 404

    if getattr(user, "email_confirmed", False):
        return jsonify({"error": "Email already confirmed"}), 400

    token = uuid.uuid4().hex
    user.confirmation_token = token
    user.confirmation_sent_at = datetime.datetime.utcnow()
    db.session.commit()

    try:
        send_confirmation_email(user.email, token)
    except Exception:
        log_audit_event(action="email_send_failed", actor_user_id=user.id, resource="email", metadata={})
        return jsonify({"error": "Failed to send email"}), 500

    return jsonify({"message": "confirmation_sent"}), 200


#Registering new user
from email_utils import send_confirmation_email

@limiter.limit("5 per minute")
@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
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


    # Create user with confirmation token
    token = uuid.uuid4().hex
    new_user = User(
        email=email,
        password=hashed_pw,
        name=data.get("name"),
        role=data.get("role"),
        profile_data=profile_data,
        email_confirmed=False,
        confirmation_token=token,
        confirmation_sent_at=datetime.datetime.utcnow(),
    )
    db.session.add(new_user)
    db.session.commit()

    # Send confirmation email (best-effort; failures shouldn't break registration)
    try:
        send_confirmation_email(new_user.email, token)
    except Exception:
        # Log in audit but don't expose details to user
        log_audit_event(action="email_send_failed", actor_user_id=new_user.id, resource="email", metadata={})

    return jsonify({"message": "registered", "user": {
        "id": new_user.id,
        "email": new_user.email,
        "name": new_user.name,
        "role": new_user.role
    }}), 201





#For viewing profile info, requires JWT auth
@app.route("/api/profile", methods=["GET", "POST"])
@jwt_required()
def profile():
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
            "profileData": user.profile_data or {}
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
        if not is_production:
            return jsonify({"error": f"Unable to generate insight: {exc}"}), 500
        return jsonify({"error": "Unable to generate insight"}), 500

    normalized_payload = _coerce_insight_payload(insight_payload, quiz_group, normalized_quizzes)
    insights = normalized_payload.get("insights") if isinstance(normalized_payload, dict) else None
    overall_summary = (
        normalized_payload.get("overallSummary") if isinstance(normalized_payload, dict) else None
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

    timestamp = datetime.datetime.utcnow().isoformat()

    if quiz_group == "careerQuizzes":
        group_store = quiz_insights.get("careerQuizzes")
        if not isinstance(group_store, dict):
            group_store = {}
        else:
            group_store = dict(group_store)
        if overall_summary:
            group_store["_overallSummary"] = overall_summary
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
            "overallSummary": overall_summary,
            "generatedAt": timestamp,
            "model": model,
        }

    profile["quizInsights"] = quiz_insights
    user.profile_data = profile
    db.session.commit()

    return jsonify({
        "quizGroup": quiz_group,
        "overallSummary": overall_summary,
        "insights": insights,
    })


@app.route("/api/profile/resume-url", methods=["GET"])
@jwt_required()
def get_profile_resume_url():
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



@app.route("/api/recommendations", methods=["POST"])
@jwt_required()
def generate_recommendations():
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

    return jsonify({
        "profileCompletion": f"{profile_completion}%",
        "jobMatches": job_matches,
        "applications": applications,
        "recentActivity": recent_activity,
        "recommendations": recommendations
    })



if __name__ == "__main__":
    app.run(debug=True)
