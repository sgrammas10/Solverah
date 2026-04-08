"""
SQLAlchemy models for the application.

This module defines the database schema used by the Flask backend, including:

- User: Authentication/authorization data and a flexible JSON profile payload.
- JobRecommendation: Stores per-user job recommendations with a score and timestamp.
- AuditLog: Security and activity logging for traceability and monitoring.
- IntakeSubmission: Pre-launch / intake form submissions with resume upload metadata.

Notes:
- JSON columns use the SQLite dialect JSON type for compatibility in local/dev.
- `created_at` fields default to the database server timestamp via `db.func.now()`.
"""

from sqlalchemy import JSON
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class JobRecommendation(db.Model):
    """Represents a scored job recommendation generated for a specific user."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    job_id = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User", backref="recommendations")


class User(db.Model):
    """Application user record, including auth credentials and profile metadata."""

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(120))
    role = db.Column(db.String(50))
    profile_data = db.Column(JSON, default=dict)

    # Email confirmation fields
    email_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    confirmation_token = db.Column(db.String(64), nullable=True, index=True)
    confirmation_sent_at = db.Column(db.DateTime, nullable=True)

    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)


class AuditLog(db.Model):
    """Tracks user/system actions for auditing, security monitoring, and debugging."""

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    resource = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(300))
    event_metadata = db.Column("metadata", JSON, default=dict)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    actor = db.relationship("User", backref="audit_logs")


class ResumeParseCorrection(db.Model):
    """Tracks user corrections to parser-extracted resume fields for training data improvement.

    One record per (user, resume, field). When the user edits experience/education/skills after
    a resume upload and saves, the delta between what the parser produced and what the user
    actually wanted is captured here so the parser can be improved over time.
    """

    __tablename__ = "resume_parse_correction"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    resume_key = db.Column(db.String(500), nullable=False)
    field = db.Column(db.String(50), nullable=False)  # "experience", "education", or "skills"
    parsed_value = db.Column(JSON, nullable=True)   # what the parser originally produced
    corrected_value = db.Column(JSON, nullable=True)  # what the user ultimately saved
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    user = db.relationship("User", backref="resume_corrections")

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "resume_key", "field",
            name="uq_correction_user_resume_field",
        ),
    )


class Company(db.Model):
    """Stores a company profile with culture dimensions for scoring against user preferences.

    The full CompanyProfile is serialized into `profile_json`. The 8 culture
    dimensions are also promoted to indexed columns so the scoring query can
    filter/rank companies without deserializing the blob.
    """

    __tablename__ = "company"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    slug = db.Column(db.String(200), nullable=False, unique=True, index=True)
    profile_json = db.Column(JSON, nullable=False)  # full CompanyProfile dict

    # Culture narratives
    culture_narrative_company = db.Column(db.Text)
    culture_narrative_employees = db.Column(db.Text)

    # Culture dimensions — categorical
    work_environment = db.Column(db.String(200))
    pace = db.Column(db.String(100))
    pace_float = db.Column(db.Float)

    # Culture dimensions — numeric (0.0–1.0)
    empathy = db.Column(db.Float)
    creative_drive = db.Column(db.Float)
    adaptability = db.Column(db.Float)
    futuristic = db.Column(db.Float)
    harmony = db.Column(db.Float)
    data_orientation = db.Column(db.Float)

    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)


class IntakeSubmission(db.Model):
    """Stores pre-launch intake submissions and associated resume upload metadata."""

    __tablename__ = "intake_submissions"

    id = db.Column(db.String(36), primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    state = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(50))
    linkedin_url = db.Column(db.String(400))
    portfolio_url = db.Column(db.String(400))
    resume_key = db.Column(db.String(500), nullable=False)
    resume_mime = db.Column(db.String(100), nullable=False)
    resume_size_bytes = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), nullable=False, default="uploaded")
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
