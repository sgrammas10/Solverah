from sqlalchemy.dialects.sqlite import JSON
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class JobRecommendation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    job_id = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User", backref="recommendations")

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(120))
    role = db.Column(db.String(50))
    profile_data = db.Column(JSON, default=dict)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)

class IntakeSubmission(db.Model):
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
