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

    # Password reset via OTP
    reset_token = db.Column(db.String(64), nullable=True)
    reset_sent_at = db.Column(db.DateTime, nullable=True)

    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)


class UserIntake(db.Model):
    """Stores a user's career intake responses: statement selections, WPLL answers,
    and Work Pulse Lite answers. One row per user, upserted on each intake event.
    wpl_completed_at drives the post-login WPL prompt suppression logic."""

    __tablename__ = "user_intake"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True
    )
    # Screen 1: statement selections
    selected_statement_ids = db.Column(JSON, nullable=False, default=list)
    # Screen 2: WPLL answers [{question_id, option_id}]
    wpll_answers = db.Column(JSON, nullable=False, default=list)
    wpll_insight_text = db.Column(db.Text, nullable=True)
    wpll_completed_at = db.Column(db.DateTime, nullable=True)
    # Sprint 2: WPL (12Q) — null until Work Pulse Lite is completed
    wpl_answers = db.Column(JSON, nullable=True)
    wpl_narrative = db.Column(db.Text, nullable=True)
    wpl_result = db.Column(JSON, nullable=True)
    wpl_completed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    user = db.relationship("User", backref=db.backref("intake", uselist=False))


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
    # Natural key for dedupe across sources (schema.sql `company.domain`). Nullable because
    # existing rows predate it; unique so two rows can never silently be the same company.
    # Added 2026-08-19 (S-07): the research schema's company table was reconciled INTO this
    # one rather than created alongside it -- one company universe, same D-13 trade.
    domain = db.Column(db.String(255), nullable=True, unique=True)
    profile_json = db.Column(JSON, nullable=False)  # full CompanyProfile dict

    # Culture narratives
    culture_narrative_company = db.Column(db.Text)
    culture_narrative_employees = db.Column(db.Text)

    # Culture dimensions — categorical
    work_environment = db.Column(db.Text)
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


# ---------------------------------------------------------------------------
# Person side of the culture-fit instrument (causal_graph/v1_model)
# ---------------------------------------------------------------------------
# These two tables are the minimum subset of causal_graph/v1_model/schema.sql needed to
# persist a completed assessment. The rest of that file -- notably its own `company` table,
# which collides with `Company` above -- is deliberately NOT migrated here; reconciling the
# two schemas is its own piece of work (S-07).
#
# `person_id` in schema.sql is `user_id` here, referencing the application's User directly.
# schema.sql's separate `person` table buys an indirection whose only justification is a
# respondent who exists without an account, and the 2026-08-18 funnel decision rules that out:
# the respondent is a signed-up user self-profiling after account creation. Adding the
# indirection later is a migration; removing it later would be a data migration.


class AssessmentResponse(db.Model):
    """One raw answer to one person-side item. Append-only.

    Raw responses are never updated or deleted, because the scoring key can change and a
    stored score must stay re-derivable from what the respondent actually chose. A retake
    writes a fresh set of rows under a new `submission_id` rather than overwriting.

    `submission_id` has no counterpart in schema.sql and is an addition. Without it the only
    way to recover which 24 rows constitute one sitting is to group by
    (user_id, form_version, answered_at), which breaks on a retake inside the same second,
    on clock skew between workers, and on any future partial-save feature. A submission is a
    real entity; giving it an id is cheaper than inferring it forever.
    """

    __tablename__ = "assessment_response"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    submission_id = db.Column(db.String(36), nullable=False, index=True)
    item_id = db.Column(db.String(64), nullable=False)
    choice = db.Column(db.String(8), nullable=False)
    form_version = db.Column(db.String(64), nullable=False)
    answered_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        # One answer per item per submission. A duplicate would change mean_pole's
        # denominator, which is the same class of silent corruption resolve_responses
        # refuses at the token layer.
        db.UniqueConstraint("submission_id", "item_id", name="uq_response_submission_item"),
    )

    user = db.relationship("User", backref="assessment_responses")


class PersonDimensionScore(db.Model):
    """Derived 0..1 score for one person on one dimension, under one scoring key.

    NOT EMPLOYER-VISIBLE. D-01 commits that employers never see an individual's answers or
    six dimension scores; if an employer ever sees anything it is a match result. That
    commitment is enforced as a test rather than as a comment -- see S-02. This docstring is
    a signpost, not the control.

    `scoring_key_version` identifies the item file AND the scoring method together, because
    a score is only comparable to another score derived from both. Changing either produces
    a new key version and a new row rather than silently replacing the old value.
    """

    __tablename__ = "person_dimension_score"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    dimension_key = db.Column(db.String(32), nullable=False)
    score = db.Column(db.Float, nullable=False)
    # Internal consistency of the four items. Nullable because the confidence measure is not
    # built yet -- a placeholder 1.0 would be indistinguishable from a real high-confidence
    # result once stored, so the column stays honest about not knowing.
    confidence = db.Column(db.Float, nullable=True)
    scoring_key_version = db.Column(db.String(64), nullable=False)
    # Which sitting produced the current value. The score row is updated in place on a retake
    # under the same key version; this records which raw submission it came from.
    submission_id = db.Column(db.String(36), nullable=False)
    scored_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "dimension_key", "scoring_key_version",
            name="uq_pscore_person_dim_keyversion",
        ),
        db.CheckConstraint("score >= 0 AND score <= 1", name="ck_pscore_score_range"),
        db.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_pscore_confidence_range",
        ),
    )

    user = db.relationship("User", backref="dimension_scores")


# ---------------------------------------------------------------------------
# Company side + match/funnel + model runs (causal_graph/v1_model/schema.sql, S-07)
# ---------------------------------------------------------------------------
# Migrated 2026-08-19, decided with Sebastian:
#   - schema.sql's `company` is reconciled INTO the existing Company above (one new
#     `domain` column) rather than created as a parallel table. Same trade as person->user
#     (D-13): research schema coupled to product schema, one universe of companies.
#   - No `dimension`/`confounder` registry tables. Keys are plain strings validated in
#     code, matching person_dimension_score. Adding a dimension stays zero-work; the DB
#     will not catch a typo'd key -- loaders are the guardrail, as on the person side.
#   - schema.sql's Postgres enums become String + CheckConstraint so the SQLite test
#     database enforces the same vocabulary the production database does.
#   - schema.sql's `recommendation` is renamed `match_recommendation`: the app already
#     has `job_recommendation` (JobRecommendation above) and two near-identical names for
#     different concepts is how someone joins the wrong table at 2am.

SCORE_SOURCES = ("scraped", "researched", "declared")
REC_CHANNELS = ("onsite", "email")
FUNNEL_ACTIONS = (
    "viewed", "saved", "passed", "applied", "interviewed",
    "offered", "hired", "accepted", "declined",
)


class CompanyDimensionScore(db.Model):
    """Per company per dimension, with SOURCE + CONFIDENCE -- the cold-start wedge.

    scraped/researched rows are guesses with low-ish confidence; a `declared` row (from the
    company itself, later) upgrades the same shape in place. `is_ground_truth` flags the
    companies the scraped model can be calibrated against. Culture goes stale, so every row
    is dated (`as_of`) and re-scoring inserts rather than overwrites.
    """

    __tablename__ = "company_dimension_score"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False, index=True)
    dimension_key = db.Column(db.String(32), nullable=False)
    score = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(16), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    is_ground_truth = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    as_of = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "company_id", "dimension_key", "source", "as_of",
            name="uq_cscore_company_dim_source_asof",
        ),
        db.CheckConstraint("score >= 0 AND score <= 1", name="ck_cscore_score_range"),
        db.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_cscore_confidence_range"
        ),
        db.CheckConstraint(
            "source IN ('scraped', 'researched', 'declared')", name="ck_cscore_source_vocab"
        ),
    )

    company = db.relationship("Company", backref="dimension_scores")


class CompanyConfounderValue(db.Model):
    """Confounder value per company. Generic value columns (num OR cat) so a new confounder
    is an INSERT, never a migration. Values are stored RAW/unscaled; the model standardizes
    via solverah_model_config.yaml. The loader is the only range guardrail -- deliberately,
    per schema.sql's design notes."""

    __tablename__ = "company_confounder_value"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False, index=True)
    confounder_key = db.Column(db.String(32), nullable=False)
    value_num = db.Column(db.Float, nullable=True)
    value_cat = db.Column(db.String(64), nullable=True)
    source = db.Column(db.String(16), nullable=False)
    confidence = db.Column(db.Float, nullable=True)
    as_of = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "company_id", "confounder_key", "source", "as_of",
            name="uq_conf_company_key_source_asof",
        ),
        db.CheckConstraint(
            "value_num IS NOT NULL OR value_cat IS NOT NULL", name="ck_conf_value_present"
        ),
        db.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_conf_confidence_range",
        ),
        db.CheckConstraint(
            "source IN ('scraped', 'researched', 'declared')", name="ck_conf_source_vocab"
        ),
    )

    company = db.relationship("Company", backref="confounder_values")


class ModelRun(db.Model):
    """One training run of the Bayesian model: reproducibility record + the version key
    every served prediction points back to."""

    __tablename__ = "model_run"

    id = db.Column(db.Integer, primary_key=True)
    model_version = db.Column(db.String(64), nullable=False)
    dimension_set_version = db.Column(db.String(64), nullable=False)
    priors_version = db.Column(db.String(64), nullable=False)
    n_rows = db.Column(db.Integer, nullable=True)
    trained_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    notes = db.Column(db.Text, nullable=True)


class WeightPosterior(db.Model):
    """Snapshot of the fitted posterior, one row per weight. Serves fast point predictions
    from `mean` without re-sampling; comparing across model_runs is the recovery curve, live."""

    __tablename__ = "weight_posterior"

    id = db.Column(db.Integer, primary_key=True)
    model_run_id = db.Column(db.Integer, db.ForeignKey("model_run.id"), nullable=False, index=True)
    weight_name = db.Column(db.String(64), nullable=False)
    mean = db.Column(db.Float, nullable=False)
    sd = db.Column(db.Float, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("model_run_id", "weight_name", name="uq_weight_run_name"),
    )

    model_run = db.relationship("ModelRun", backref="weight_posteriors")


class MatchRecommendation(db.Model):
    """One (user, company) surfaced by the match model: the prediction, its uncertainty band,
    and `is_exploration` so the feedback loop can be broken and analyzed off-policy later.

    schema.sql calls this table `recommendation`; renamed here because `job_recommendation`
    already exists and means something else. What was shown is recorded even when the user
    does nothing with it -- the selection effect (the collider) is only visible if the
    un-acted-on rows exist.
    """

    __tablename__ = "match_recommendation"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False, index=True)
    model_run_id = db.Column(db.Integer, db.ForeignKey("model_run.id"), nullable=True)
    p_fit = db.Column(db.Float, nullable=True)
    p_fit_low = db.Column(db.Float, nullable=True)
    p_fit_high = db.Column(db.Float, nullable=True)
    rank = db.Column(db.Integer, nullable=True)
    is_exploration = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    channel = db.Column(db.String(16), nullable=False, default="onsite", server_default="onsite")
    shown_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.CheckConstraint("p_fit IS NULL OR (p_fit >= 0 AND p_fit <= 1)", name="ck_mrec_pfit_range"),
        db.CheckConstraint(
            "p_fit_low IS NULL OR (p_fit_low >= 0 AND p_fit_low <= 1)", name="ck_mrec_pfit_low_range"
        ),
        db.CheckConstraint(
            "p_fit_high IS NULL OR (p_fit_high >= 0 AND p_fit_high <= 1)", name="ck_mrec_pfit_high_range"
        ),
        db.CheckConstraint("channel IN ('onsite', 'email')", name="ck_mrec_channel_vocab"),
    )

    user = db.relationship("User", backref="match_recommendations")
    company = db.relationship("Company", backref="match_recommendations")
    model_run = db.relationship("ModelRun", backref="recommendations")


class RecAction(db.Model):
    """Funnel events against a shown recommendation. 'A match formed' (hired+accepted) is the
    collider the outcome data is conditioned on; capturing the full funnel is what lets the
    model SEE that selection instead of being silently biased by it."""

    __tablename__ = "rec_action"

    id = db.Column(db.Integer, primary_key=True)
    recommendation_id = db.Column(
        db.Integer, db.ForeignKey("match_recommendation.id"), nullable=False, index=True
    )
    action = db.Column(db.String(16), nullable=False)
    acted_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.CheckConstraint(
            "action IN ('viewed', 'saved', 'passed', 'applied', 'interviewed', "
            "'offered', 'hired', 'accepted', 'declined')",
            name="ck_raction_action_vocab",
        ),
    )

    recommendation = db.relationship("MatchRecommendation", backref="actions")


class OutcomeAppeal(db.Model):
    """APPEAL outcome: fast, abundant, biased toward appearance ("did this fit what you
    wanted?"). Kept in its own table, never conflated with experienced fit -- the two
    outcomes are separate on purpose (schema.sql design principle 4)."""

    __tablename__ = "outcome_appeal"

    id = db.Column(db.Integer, primary_key=True)
    recommendation_id = db.Column(
        db.Integer, db.ForeignKey("match_recommendation.id"), nullable=False, unique=True
    )
    fit_yes = db.Column(db.Boolean, nullable=False)
    channel = db.Column(db.String(16), nullable=False)
    responded_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.CheckConstraint("channel IN ('onsite', 'email')", name="ck_oappeal_channel_vocab"),
    )

    recommendation = db.relationship("MatchRecommendation", backref=db.backref("appeal", uselist=False))


class OutcomeExperienced(db.Model):
    """EXPERIENCED outcome: slow, scarce, the TRUE label -- only exists for placements.

    `working_scale` is ordinal 1..5 (1=bad .. 5=great). The model outcome node trained on
    this is OrderedLogistic, NOT Bernoulli -- see S-06 before wiring it into build_model.
    """

    __tablename__ = "outcome_experienced"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False)
    recommendation_id = db.Column(
        db.Integer, db.ForeignKey("match_recommendation.id"), nullable=True
    )
    started_at = db.Column(db.Date, nullable=True)
    checkin_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    working_scale = db.Column(db.SmallInteger, nullable=False)
    source = db.Column(db.String(32), nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "working_scale >= 1 AND working_scale <= 5", name="ck_oexp_working_scale_range"
        ),
    )

    user = db.relationship("User", backref="experienced_outcomes")
    company = db.relationship("Company", backref="experienced_outcomes")
    recommendation = db.relationship("MatchRecommendation", backref="experienced_outcomes")
