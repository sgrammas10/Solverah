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

import datetime

from sqlalchemy import DDL, JSON
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.ext.hybrid import hybrid_property
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

#: Part 4.2's `user_role`, spelled the way the system already spells it.
#:
#: Part 4.2 writes these as `('job_seeker','recruiter','admin')`. The value
#: stored, transmitted and gated on today is `job-seeker`, and `src/App.tsx`
#: gates fifteen routes on `allowedRoles={["job-seeker"]}`, so an underscored
#: enum would make every protected route reject every user. The tidier SQL
#: spelling is a wire change and lands with the frontend, not with a rename.
USER_ROLES = ("job-seeker", "recruiter", "admin")

#: Part 4.2's `user_status`, unchanged. Nothing reads it yet; it is maintained at
#: the two transitions that already exist in code -- confirmation and tombstoning
#: -- so the column is true rather than permanently 'pending'.
USER_STATUSES = ("pending", "active", "suspended", "deleted")


class JobRecommendation(db.Model):
    """Represents a scored job recommendation generated for a specific user."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    job_id = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User", backref="recommendations")


class User(db.Model):
    """Application user record, including auth credentials and profile metadata.

    Part 4.2, as of Phase 2c. The table is `users`: `user` is a reserved word and
    was quoted in every generated statement (P1-8's first bullet).

    Two shapes here differ from what the API publishes, and both are adapted
    before anything reaches a response:

    * `email_confirmed_at` is an instant; the wire still publishes
      `email_confirmed` as a boolean. The derivation is the hybrid below rather
      than four edits in four serializers, because the same question is asked by
      callers that are not serializers -- the login gate in `auth_service`, the
      tombstone in `account_repository`. One derivation cannot disagree with
      itself.
    * `public_id` exists and is indexed, and appears in no response and no route.
      Part 4.1 intends it for URLs and payloads with integer ids never leaving the
      database, which is right and is a breaking change to every client, so it is
      its own phase. `tests/test_users_table.py` asserts it stays off the wire.
    """

    __tablename__ = "users"

    # `BY DEFAULT`, not Part 4.1's `ALWAYS`. `ALWAYS` rejects an explicit id
    # without `OVERRIDING SYSTEM VALUE`, and `tests/conftest.py::seed_user`
    # inserts one deliberately -- several tests assert behaviour about a specific
    # user id. `BY DEFAULT` keeps that fixture ORM-shaped and costs nothing in
    # production, where nothing supplies an id. The sequence is still the
    # database's, which is the part that mattered.
    id = db.Column(db.BigInteger, db.Identity(always=False), primary_key=True)
    public_id = db.Column(
        UUID(as_uuid=True), nullable=False, server_default=db.text("uuidv7()")
    )
    # CITEXT, so `find_by_email` is case-insensitive in the database rather than
    # by every caller remembering to lower-case first. Uniqueness is the partial
    # index in __table_args__, not a column constraint.
    #
    # Part 4.2 also declares `email_normalized` for dot/plus-folded dedupe. It is
    # deliberately absent: folding dots is correct for Gmail and wrong for most
    # other providers, so a global fold would reject `a.b@fastmail.com` as a
    # duplicate of `ab@fastmail.com`. Scoping the fold to the domains where it
    # holds is a product rule with a list to maintain, and it belongs with the
    # signup flow rather than with a rename.
    email = db.Column(CITEXT, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    name = db.Column(db.Text)
    role = db.Column(
        db.Enum(*USER_ROLES, name="user_role"),
        nullable=False,
        default="job-seeker",
        server_default="job-seeker",
    )
    status = db.Column(
        db.Enum(*USER_STATUSES, name="user_status"),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    #: Not read or written since Phase 2a; kept one release so a rollback is a
    #: redeploy. The drop is the next release's migration.
    profile_data = db.Column(JSON, default=dict)

    # Email confirmation.
    #
    # `confirmation_token` and `confirmation_sent_at` are absent from Part 4.2,
    # which assumes a separate token store alongside `user_sessions`. Neither
    # exists yet and both columns are live behind `POST /auth/email/verify`, so
    # they are carried forward rather than dropped -- deleting a live column
    # because the target diagram does not draw it is deleting a feature by
    # omission. They move when the token table lands.
    email_confirmed_at = db.Column(db.DateTime(timezone=True))
    confirmation_token = db.Column(db.String(64), nullable=True, index=True)
    confirmation_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Password reset via OTP. Carried forward for the same reason.
    reset_token = db.Column(db.String(64), nullable=True)
    reset_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)

    #: Declared by Part 4.2 and not yet maintained. The row that knows a login
    #: happened is `user_sessions`, which this phase does not create; writing it
    #: from the login handler would put a write on the login path for a column
    #: nothing reads.
    last_login_at = db.Column(db.DateTime(timezone=True))
    failed_login_count = db.Column(db.SmallInteger, nullable=False, default=0)
    # TIMESTAMPTZ, where this was `timestamp without time zone`. `domain.utcnow()`
    # is timezone-aware, so `locked_until > utcnow()` in the login path compared a
    # naive value against an aware one and raised TypeError the moment a lockout
    # was actually in force.
    locked_until = db.Column(db.DateTime(timezone=True))

    #: Part 4.1 rule 4. Enforced by `version_id_col` below, not decorative: every
    #: UPDATE carries `AND version = <the value read>` and a losing writer raises
    #: StaleDataError instead of silently overwriting.
    version = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    #: Never set by this phase. `account_repository.tombstone_user` still frees a
    #: deleted account's address by rewriting it, so the partial index below
    #: behaves exactly like the full unique constraint it replaces. Adopting
    #: soft-delete is a deletion-policy change, not a schema one.
    deleted_at = db.Column(db.DateTime(timezone=True))

    __mapper_args__ = {"version_id_col": version}

    __table_args__ = (
        db.Index("uq_users_public_id", "public_id", unique=True),
        db.Index(
            "uq_users_email",
            "email",
            unique=True,
            postgresql_where=db.text("deleted_at IS NULL"),
        ),
        db.Index(
            "ix_users_status",
            "status",
            postgresql_where=db.text("deleted_at IS NULL"),
        ),
    )

    @hybrid_property
    def email_confirmed(self) -> bool:
        """Whether this address has been verified.

        The storage is an instant and the wire is a boolean. Reading the boolean
        from the instant here, once, is what keeps `GET /me` and
        `GET /auth/session` byte-identical without four serializers each deriving
        it their own way.
        """
        return self.email_confirmed_at is not None

    @email_confirmed.inplace.setter
    def _email_confirmed_setter(self, value: bool) -> None:
        """Assigning True stamps the instant; assigning False clears it.

        Re-assigning True leaves an existing instant alone. `confirm_email` sets
        it once, but a caller that sets it twice means "this is confirmed", not
        "it was confirmed again just now", and overwriting would quietly move a
        recorded fact forward.
        """
        if value:
            if self.email_confirmed_at is None:
                self.email_confirmed_at = datetime.datetime.now(datetime.timezone.utc)
        else:
            self.email_confirmed_at = None

    @email_confirmed.inplace.expression
    @classmethod
    def _email_confirmed_expression(cls):
        """So `filter(User.email_confirmed)` means the same thing in SQL."""
        return cls.email_confirmed_at.isnot(None)


class UserIntake(db.Model):
    """Stores a user's career intake responses: statement selections, WPLL answers,
    and Work Pulse Lite answers. One row per user, upserted on each intake event.
    wpl_completed_at drives the post-login WPL prompt suppression logic."""

    __tablename__ = "user_intake"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True
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
    """Tracks user/system actions for auditing, security monitoring, and debugging.

    RANGE-partitioned on ``created_at`` (Phase 2, item 5).  This is the
    highest-volume table in the system -- ``GET /api/profile`` writes a row on
    every read, so session restore appends one per page load -- and it is the
    only one of the three partitioned tables with a live writer today
    (``solverah/services/audit.py``).  Partitioning is what lets old months be
    detached and dropped in constant time instead of scanned and deleted.

    The declaration lives *here* rather than only in the migration because
    ``tests/conftest.py`` builds its schema with ``db.create_all()`` and never
    runs the migration chain.  A partition scheme declared only in Alembic would
    be invisible to every test in the suite, which is the same as not having
    tested it.

    ``created_at`` joins the primary key because Postgres requires the partition
    key to be part of every unique constraint on a partitioned table -- the
    planner has to be able to prove uniqueness without reading the other
    partitions.  ``id`` therefore needs ``autoincrement=True`` stated outright:
    SQLAlchemy only infers a serial column for a *single*-column integer key and
    would otherwise hand this table a plain, non-defaulted ``id``.

    The foreign key to ``users`` stays.  Postgres has supported outgoing foreign
    keys from partitioned tables since 12, so there is nothing to trade away
    here; dropping it to decouple the table from identity storage is a separate
    decision with its own migration.
    """

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    resource = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(300))
    event_metadata = db.Column("metadata", JSON, default=dict)
    created_at = db.Column(
        db.DateTime, server_default=db.func.now(), nullable=False, primary_key=True
    )

    __table_args__ = {"postgresql_partition_by": "RANGE (created_at)"}

    actor = db.relationship("User", backref="audit_logs")


class ResumeParseCorrection(db.Model):
    """Tracks user corrections to parser-extracted resume fields for training data improvement.

    One record per (user, resume, field). When the user edits experience/education/skills after
    a resume upload and saves, the delta between what the parser produced and what the user
    actually wanted is captured here so the parser can be improved over time.
    """

    __tablename__ = "resume_parse_correction"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
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
# Assessments, unified (Part 4.4, Phase 2d)
# ---------------------------------------------------------------------------
# Five products used to be stored in four places: `user_intake.wpl_*` and
# `user_intake.wpll_*` for the two Work Pulse instruments, two keys inside the
# profile document for FocusType and ManagerMatch, and the two person-side tables
# below for the core assessment. `GET /assessments` had to read three of them to
# answer one question. These two tables are the one shape all five share.


#: The `{kind}` values `assessment_forms` and `assessment_submissions` accept.
#: The same five keys `solverah.services.assessment_service.ASSESSMENT_KINDS`
#: registers -- kept here as well because the check constraint needs a literal
#: and importing the service layer from `model` would invert the layering.
ASSESSMENT_KIND_KEYS = ("core", "work_pulse", "wpll", "focus_type", "manager_match")

#: `in_progress` is declared by Part 4.4 and is never written today: every
#: instrument arrives complete in one request. It stays in the constraint rather
#: than being trimmed to what is currently reachable, because partial saves are
#: the reason the column exists and narrowing it now would make adding them a
#: migration.
ASSESSMENT_STATUSES = ("in_progress", "complete", "scored")


class AssessmentForm(db.Model):
    """One published version of one instrument.

    What makes this more than a lookup table is the composite foreign key from
    `assessment_submissions (kind, form_version)`. A submission cannot name a
    version that was never registered, which is the property that stops the
    version string being free text that drifts per instrument.

    `definition` holds only what the *database* is the source of truth for. For
    `core` that is the item-file identity the server serves the form from; for
    the other four it is `{"source": "client"}`, because the questions genuinely
    ship in the client bundle and writing a copy here would create a second
    source of truth for something no server code reads. Moving them server-side
    is Phase 4 work, and the honest record until then is that they are not here.

    `published_at` is null for a version registered on first use rather than
    published deliberately -- see :meth:`register`.
    """

    __tablename__ = "assessment_forms"

    id = db.Column(db.BigInteger, db.Identity(always=True), primary_key=True)
    kind = db.Column(db.Text, nullable=False)
    version = db.Column(db.Text, nullable=False)
    definition = db.Column(JSONB, nullable=False, default=dict)
    published_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (
        db.UniqueConstraint("kind", "version", name="uq_assessment_forms_kind_version"),
        db.CheckConstraint(
            "kind IN %s" % (ASSESSMENT_KIND_KEYS,), name="ck_assessment_forms_kind"
        ),
    )

    @classmethod
    def register(cls, kind: str, version: str) -> None:
        """Record that (*kind*, *version*) exists, if it does not already.

        Called on the write path before a submission names a version, so the
        composite foreign key can be enforced without a deploy step between "the
        item file changed" and "someone submitted against it". Idempotent by
        `ON CONFLICT DO NOTHING` rather than by a SELECT, because two respondents
        can be the first to sit a new version at the same moment.

        A row created here has a null `published_at` and an empty `definition`.
        That is deliberate and readable: it says the version was observed, not
        that anyone published a definition for it. The five rows the Phase 2d
        migration seeds carry both.

        Does not commit -- the caller owns the transaction, as everywhere else on
        this write path.
        """
        from sqlalchemy.dialects.postgresql import insert as _pg_insert

        db.session.execute(
            _pg_insert(cls.__table__)
            .values(kind=kind, version=version, definition={})
            .on_conflict_do_nothing(index_elements=["kind", "version"])
        )


class AssessmentSubmission(db.Model):
    """One sitting of one instrument, for one user.

    RETAKE SEMANTICS DIFFER BY KIND, AND THE SCHEMA SAYS SO
    -------------------------------------------------------
    `uq_assessment_submissions_current` is a **partial** unique index over
    (user_id, kind) `WHERE kind <> 'core'`. The four non-core instruments have
    exactly one current sitting each and a retake updates it in place, which is
    what they did before this table existed -- `user_intake` is one row per user,
    and a profile-document key holds one value. Making that a constraint rather
    than a convention is what stops a concurrent double-submit leaving two rows
    that every later read has to choose between.

    `core` is excluded because its sittings are append-only: a retake writes a
    fresh set of `assessment_response` rows under a new id and the old sitting
    stays readable forever, which is what makes a score re-derivable when the
    scoring key changes.

    WHAT A `core` ROW DELIBERATELY DOES NOT HOLD (D-01)
    ---------------------------------------------------
    `result` and `answers` are both null for `core`, always, and a check
    constraint says so rather than a convention. Its answers live in
    `assessment_response` and its scores in `person_dimension_score`, reachable
    only through `assessment_store` -- and unifying the *submission* record was
    not licence to widen that doorway. A core row carries a kind, a version, a
    status and three timestamps, and there is nothing in it from which an
    employer-facing reader could learn an individual's answers or dimension
    scores. `tests/test_employer_visibility.py` guards the two tables; the null
    columns are what keep this one uninteresting to it.

    `answers` IS AN ADDITION TO PART 4.4, AND WHY
    ---------------------------------------------
    Part 4.4 has no answers column, because it puts raw per-item answers in
    `assessment_responses` -- a table partitioned by `answered_at`, which is
    Phase 2 item 5 and its own phase. The four non-core instruments still need
    their raw answers kept: the Work Pulse narrative prompt reads the claimed
    WPLL answers, `/me/export` returns both sets, and the culture-preference
    backfill re-derives from the Work Pulse answers. Until item 5 lands they live
    here, as the payload the client sent. The alternative -- decomposing them
    into `assessment_response` now -- would put four instruments' answers behind
    the D-01 doorway and force every one of those readers through it, which is
    the surface widening this phase is explicitly not allowed to do.
    """

    __tablename__ = "assessment_submissions"

    id = db.Column(db.BigInteger, db.Identity(always=True), primary_key=True)
    public_id = db.Column(
        UUID(as_uuid=True), nullable=False, server_default=db.text("uuidv7()")
    )
    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = db.Column(db.Text, nullable=False)
    form_version = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, default="in_progress")
    #: The instrument's payload, returned verbatim by
    #: `GET /me/assessments/{kind}/result`. Null for `core` (see the class
    #: docstring) and for `wpll`, which stores a claimed anonymous session and
    #: has no result endpoint.
    result = db.Column(JSONB)
    narrative = db.Column(db.Text)
    #: What the respondent sent. Null for `core`. See the class docstring.
    answers = db.Column(JSONB)
    started_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    completed_at = db.Column(db.DateTime(timezone=True))
    scored_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["kind", "form_version"],
            ["assessment_forms.kind", "assessment_forms.version"],
            name="fk_assessment_submissions_form",
        ),
        db.CheckConstraint(
            "kind IN %s" % (ASSESSMENT_KIND_KEYS,),
            name="ck_assessment_submissions_kind",
        ),
        db.CheckConstraint(
            "status IN %s" % (ASSESSMENT_STATUSES,),
            name="ck_assessment_submissions_status",
        ),
        db.CheckConstraint(
            "kind <> 'core' OR (result IS NULL AND answers IS NULL)",
            name="ck_assessment_submissions_core_carries_nothing",
        ),
        db.Index(
            "uq_assessment_submissions_current",
            "user_id",
            "kind",
            unique=True,
            postgresql_where=db.text("kind <> 'core'"),
        ),
        db.Index("ix_submissions_user", "user_id", "kind", db.text("completed_at DESC")),
    )

    user = db.relationship("User", backref="assessment_submissions")


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
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
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
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
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

    RANGE-partitioned on ``shown_at`` (Phase 2, item 5), which forces the primary key
    from ``id`` to ``(id, shown_at)``: Postgres will not accept a unique constraint on a
    partitioned table unless it contains the partition key.

    That widening is why three other tables carry a ``shown_at`` of their own.  A plain
    reference to ``id`` is no longer a reference to anything unique, so ``rec_action``,
    ``outcome_appeal`` and ``outcome_experienced`` each hold the parent's ``shown_at``
    beside its id and point at both.  Dropping those foreign keys would have been the
    smaller change and the wrong one -- all three feed the causal model, where a dangling
    recommendation reference is not an error anyone sees but training data that is quietly
    wrong.
    """

    __tablename__ = "match_recommendation"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False, index=True)
    model_run_id = db.Column(db.Integer, db.ForeignKey("model_run.id"), nullable=True)
    p_fit = db.Column(db.Float, nullable=True)
    p_fit_low = db.Column(db.Float, nullable=True)
    p_fit_high = db.Column(db.Float, nullable=True)
    rank = db.Column(db.Integer, nullable=True)
    is_exploration = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    channel = db.Column(db.String(16), nullable=False, default="onsite", server_default="onsite")
    shown_at = db.Column(
        db.DateTime, server_default=db.func.now(), nullable=False, primary_key=True
    )

    __table_args__ = (
        db.CheckConstraint("p_fit IS NULL OR (p_fit >= 0 AND p_fit <= 1)", name="ck_mrec_pfit_range"),
        db.CheckConstraint(
            "p_fit_low IS NULL OR (p_fit_low >= 0 AND p_fit_low <= 1)", name="ck_mrec_pfit_low_range"
        ),
        db.CheckConstraint(
            "p_fit_high IS NULL OR (p_fit_high >= 0 AND p_fit_high <= 1)", name="ck_mrec_pfit_high_range"
        ),
        db.CheckConstraint("channel IN ('onsite', 'email')", name="ck_mrec_channel_vocab"),
        {"postgresql_partition_by": "RANGE (shown_at)"},
    )

    user = db.relationship("User", backref="match_recommendations")
    company = db.relationship("Company", backref="match_recommendations")
    model_run = db.relationship("ModelRun", backref="recommendations")


class RecAction(db.Model):
    """Funnel events against a shown recommendation. 'A match formed' (hired+accepted) is the
    collider the outcome data is conditioned on; capturing the full funnel is what lets the
    model SEE that selection instead of being silently biased by it.

    RANGE-partitioned on ``acted_at`` (Phase 2, item 5) -- its own event time, not the
    parent's.  ``shown_at`` here is a copy of ``match_recommendation.shown_at``, carried so
    the foreign key can name the parent's full ``(id, shown_at)`` key; the two timestamps
    mean different things and are not interchangeable.

    Assigning ``rec_action.recommendation`` populates both columns, so ORM callers see no
    change.  Code that sets ``recommendation_id`` as a bare integer must now set
    ``shown_at`` alongside it, and the database rejects it if the pair does not exist.
    """

    __tablename__ = "rec_action"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    recommendation_id = db.Column(db.Integer, nullable=False, index=True)
    shown_at = db.Column(db.DateTime, nullable=False)
    action = db.Column(db.String(16), nullable=False)
    acted_at = db.Column(
        db.DateTime, server_default=db.func.now(), nullable=False, primary_key=True
    )

    __table_args__ = (
        db.CheckConstraint(
            "action IN ('viewed', 'saved', 'passed', 'applied', 'interviewed', "
            "'offered', 'hired', 'accepted', 'declined')",
            name="ck_raction_action_vocab",
        ),
        db.ForeignKeyConstraint(
            ["recommendation_id", "shown_at"],
            ["match_recommendation.id", "match_recommendation.shown_at"],
            name="fk_raction_recommendation",
        ),
        {"postgresql_partition_by": "RANGE (acted_at)"},
    )

    recommendation = db.relationship("MatchRecommendation", backref="actions")


class OutcomeAppeal(db.Model):
    """APPEAL outcome: fast, abundant, biased toward appearance ("did this fit what you
    wanted?"). Kept in its own table, never conflated with experienced fit -- the two
    outcomes are separate on purpose (schema.sql design principle 4).

    Not partitioned; it carries ``shown_at`` only because its parent is (Phase 2, item 5)
    and the foreign key has to name ``match_recommendation``'s full ``(id, shown_at)`` key.

    The uniqueness stays on ``recommendation_id`` *alone*.  One appeal per recommendation
    is the rule, and widening the constraint to ``(recommendation_id, shown_at)`` would
    quietly retire it: two rows naming the same recommendation with different ``shown_at``
    values would both be accepted, and only one of them can be about a real event.
    """

    __tablename__ = "outcome_appeal"

    id = db.Column(db.Integer, primary_key=True)
    recommendation_id = db.Column(db.Integer, nullable=False, unique=True)
    shown_at = db.Column(db.DateTime, nullable=False)
    fit_yes = db.Column(db.Boolean, nullable=False)
    channel = db.Column(db.String(16), nullable=False)
    responded_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.CheckConstraint("channel IN ('onsite', 'email')", name="ck_oappeal_channel_vocab"),
        db.ForeignKeyConstraint(
            ["recommendation_id", "shown_at"],
            ["match_recommendation.id", "match_recommendation.shown_at"],
            name="fk_oappeal_recommendation",
        ),
    )

    recommendation = db.relationship("MatchRecommendation", backref=db.backref("appeal", uselist=False))


class OutcomeExperienced(db.Model):
    """EXPERIENCED outcome: slow, scarce, the TRUE label -- only exists for placements.

    `working_scale` is ordinal 1..5 (1=bad .. 5=great). The model outcome node trained on
    this is OrderedLogistic, NOT Bernoulli -- see S-06 before wiring it into build_model.

    Not partitioned; ``shown_at`` is here for the same reason as on ``outcome_appeal``
    (Phase 2, item 5).  It is nullable because ``recommendation_id`` is: a placement can be
    recorded without a recommendation that led to it.  Both columns are NULL together, and
    a composite foreign key with any NULL member is not checked, which is what keeps that
    case legal while a *stated* recommendation still has to exist.
    """

    __tablename__ = "outcome_experienced"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False)
    recommendation_id = db.Column(db.Integer, nullable=True)
    shown_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.Date, nullable=True)
    checkin_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    working_scale = db.Column(db.SmallInteger, nullable=False)
    source = db.Column(db.String(32), nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "working_scale >= 1 AND working_scale <= 5", name="ck_oexp_working_scale_range"
        ),
        db.ForeignKeyConstraint(
            ["recommendation_id", "shown_at"],
            ["match_recommendation.id", "match_recommendation.shown_at"],
            name="fk_oexp_recommendation",
        ),
    )

    user = db.relationship("User", backref="experienced_outcomes")
    company = db.relationship("Company", backref="experienced_outcomes")
    recommendation = db.relationship("MatchRecommendation", backref="experienced_outcomes")


# ---------------------------------------------------------------------------
# Phase 2a -- profile_data, decomposed (docs/ARCHITECTURE.md Part 4.3)
# ---------------------------------------------------------------------------
#
# `User.profile_data` above is no longer read or written by anything. It is kept
# for one release so a rollback is a redeploy rather than a restore
# (docs/RUNBOOK_DATABASE_ROLLBACK.md); the column is dropped in the next one.
#
# These tables are Postgres-only and deliberately so. `DEFAULT uuidv7()`, JSONB,
# `TEXT[]`, identity columns and the trigram index are what Part 4 specifies, and
# Render runs Postgres 18.3 where all five work. See docs/ARCHITECTURE.md Phase 2
# for why the SQLite CI job was retired rather than these being watered down.


def _updated_at_trigger(table_name: str) -> str:
    """DDL keeping ``updated_at`` current without the application's help.

    Part 4.1 principle 5. It is not stylistic: the profile write path issues a
    Core UPDATE built column-by-column from an optimistic-lock comparison, and
    any column that write forgets is a column that silently stops being
    maintained. A trigger cannot be forgotten.
    """
    return """
    CREATE OR REPLACE FUNCTION solverah_set_updated_at() RETURNS trigger AS $BODY$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $BODY$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_%(table)s_updated_at ON %(table)s;
    CREATE TRIGGER trg_%(table)s_updated_at
        BEFORE UPDATE ON %(table)s
        FOR EACH ROW EXECUTE FUNCTION solverah_set_updated_at();
    """ % {"table": table_name}


class Profile(db.Model):
    """One row per user: the promoted scalar profile fields, plus the remainder.

    `extra` is the open-ended remainder and is still a JSON document, so it still
    has P0-1's read-modify-write shape. `version` is what makes that safe: every
    write is a compare-and-swap against the value it read, and a writer that
    loses re-reads and re-merges rather than overwriting. Decomposition alone
    would not have fixed the lost update -- see tests/test_profile_concurrency.py.
    """

    __tablename__ = "profiles"

    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    headline = db.Column(db.Text)
    summary = db.Column(db.Text)
    location_state = db.Column(db.Text)
    location_city = db.Column(db.Text)
    phone = db.Column(db.Text)
    linkedin_url = db.Column(db.Text)
    portfolio_url = db.Column(db.Text)
    career_status = db.Column(db.Text)
    #: 0-100, maintained by the service on every write. The dashboard still
    #: computes its percentage from the assembled document rather than reading
    #: this, so the two cannot disagree on the request path; the column exists so
    #: "how many profiles are more than 80% complete" is a query rather than a
    #: full scan of a JSON column. tests/test_profile_decomposition.py asserts
    #: the two agree.
    completeness = db.Column(db.SmallInteger, nullable=False, default=0)
    extra = db.Column(JSONB, nullable=False, default=dict)
    version = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    user = db.relationship("User", backref=db.backref("profile", uselist=False))


class ProfileExperience(db.Model):
    """One role from the profile's ``experience`` array.

    `extra` holds the entry keys with no column: the frontend's list `id`, and
    any date the user typed as free text ("2020 - 2022", "Present"). Part 4.3
    does not list it; without it the only entries that could become rows would be
    the ones whose dates happen to be ISO, which is almost none of them, and the
    decomposition would decompose nothing.
    """

    __tablename__ = "profile_experiences"

    id = db.Column(db.BigInteger, db.Identity(always=True), primary_key=True)
    public_id = db.Column(
        UUID(as_uuid=True), nullable=False, server_default=db.text("uuidv7()")
    )
    user_id = db.Column(
        db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company_name = db.Column(db.Text, nullable=False)
    title = db.Column(db.Text, nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_current = db.Column(db.Boolean, nullable=False, default=False)
    description = db.Column(db.Text)
    source = db.Column(db.Text, nullable=False, default="user")
    ordinal = db.Column(db.SmallInteger, nullable=False, default=0)
    extra = db.Column(JSONB, nullable=False, default=dict)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.Index("ix_experiences_user", "user_id", "ordinal"),
        db.Index("uq_experiences_public_id", "public_id", unique=True),
    )


class ProfileEducation(db.Model):
    """One entry from the profile's ``education`` array.

    Same shape as ProfileExperience, and `extra` is here for the same reason --
    plus ``gpa``, which the parser emits and Part 4.3 has no column for.
    """

    __tablename__ = "profile_educations"

    id = db.Column(db.BigInteger, db.Identity(always=True), primary_key=True)
    public_id = db.Column(
        UUID(as_uuid=True), nullable=False, server_default=db.text("uuidv7()")
    )
    user_id = db.Column(
        db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    institution = db.Column(db.Text, nullable=False)
    degree = db.Column(db.Text)
    field_of_study = db.Column("field", db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    source = db.Column(db.Text, nullable=False, default="user")
    ordinal = db.Column(db.SmallInteger, nullable=False, default=0)
    extra = db.Column(JSONB, nullable=False, default=dict)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.Index("ix_educations_user", "user_id", "ordinal"),
        db.Index("uq_educations_public_id", "public_id", unique=True),
    )


class Skill(db.Model):
    """The canonical skill dimension. One row per `solverah.domain.skills.slugify`.

    `label` is first-writer-wins: whoever creates the row names it, and every
    later spelling that slugifies the same way is appended to `aliases`. That
    keeps what people actually typed without letting capitalisation fork the
    dimension, and gives the trigram index below something real to search.
    """

    __tablename__ = "skills"

    id = db.Column(db.BigInteger, db.Identity(always=True), primary_key=True)
    slug = db.Column(db.Text, nullable=False, unique=True)
    label = db.Column(db.Text, nullable=False)
    onet_element_id = db.Column(db.Text)
    aliases = db.Column(ARRAY(db.Text), nullable=False, server_default=db.text("'{}'"))

    __table_args__ = (
        db.Index(
            "ix_skills_trgm",
            "label",
            postgresql_using="gin",
            postgresql_ops={"label": "gin_trgm_ops"},
        ),
    )


class ProfileSkill(db.Model):
    """One skill claimed by one user.

    `label` is the raw text *this* user wrote, which is not the same thing as
    `Skill.label`: two users can type "Python" and "python" and must each get
    their own spelling back. `ordinal` is the position in the document's
    ``skills`` array, and NULL means the skill was rated but never listed --
    a state the blob could represent, so one the rows have to.
    """

    __tablename__ = "profile_skills"

    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id = db.Column(db.BigInteger, db.ForeignKey("skills.id"), primary_key=True)
    label = db.Column(db.Text, nullable=False)
    proficiency = db.Column(db.SmallInteger)
    ordinal = db.Column(db.SmallInteger)
    years = db.Column(db.Numeric(4, 1))
    source = db.Column(db.Text, nullable=False, default="user")
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.Index("ix_profile_skills_skill", "skill_id"),
        db.CheckConstraint(
            "proficiency IS NULL OR (proficiency >= 1 AND proficiency <= 5)",
            name="ck_profile_skills_proficiency_range",
        ),
    )

    skill = db.relationship("Skill")


class Resume(db.Model):
    """The resume object on a user's profile.

    One row per user today, because the blob held exactly one ``resumeKey`` and
    `retention_cleanup` deletes object-storage keys no row references. Keeping
    superseded uploads here would quietly stop them from ever being swept, which
    is a retention change rather than a storage change. The index is on
    (user_id, created_at DESC) so history is a data change when it arrives.
    """

    __tablename__ = "resumes"

    id = db.Column(db.BigInteger, db.Identity(always=True), primary_key=True)
    public_id = db.Column(
        UUID(as_uuid=True), nullable=False, server_default=db.text("uuidv7()")
    )
    user_id = db.Column(
        db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    object_key = db.Column(db.Text, nullable=False)
    #: Nullable, unlike Part 4.3. A blob that recorded `resumeKey` without an
    #: `uploadedResume` sub-document has no MIME type to carry over, and NULL
    #: says that where an invented "application/octet-stream" would not.
    mime = db.Column(db.Text)
    #: 0 means "not recorded", for the same reason.
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.Text, nullable=False, default="stored")
    parser_version = db.Column(db.Text)
    parsed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.Index("ix_resumes_user", "user_id", db.text("created_at DESC")),
        db.Index("uq_resumes_public_id", "public_id", unique=True),
    )


# `updated_at` is the database's job, not the application's (Part 4.1 rule 5).
# Attached per table rather than declared once because a trigger is DDL and has
# to be emitted after the table it fires on -- for `db.create_all()` in the tests
# and for the migration alike.
#
# `users` joins the list in Phase 2c. P1-8's fourth bullet is that several tables
# have an `updated_at` with only a `server_default`, which never fires on UPDATE
# and makes the column a second `created_at`. That is fixed here for this table;
# the remaining ones are named in P1-8 and are not this phase's.
for _triggered_table in (
    User.__table__,
    Profile.__table__,
    ProfileExperience.__table__,
    ProfileEducation.__table__,
    ProfileSkill.__table__,
):
    sa_event.listen(
        _triggered_table,
        "after_create",
        DDL(_updated_at_trigger(_triggered_table.name)).execute_if(dialect="postgresql"),
    )
del _triggered_table


#: The tables `db.create_all()` emits as partitioned parents, and the suffix their
#: catch-all partition gets. Derived from the models rather than restated, so a
#: fourth partitioned table cannot be added without one appearing here too.
PARTITIONED_TABLES = tuple(
    table
    for table in db.metadata.sorted_tables
    if table.dialect_options.get("postgresql", {}).get("partition_by")
)

DEFAULT_PARTITION_SUFFIX = "_default"

# A partitioned parent with no partitions accepts no rows. Every insert fails with
# "no partition of relation ... found for row", and `db.create_all()` creates only
# the parent -- so without this, the three tables above would be created and then
# reject everything written to them. `audit_log` alone is written on every
# authenticated request, which is the whole suite plus `Scripts/capture_contract.py`.
#
# One DEFAULT partition per table, not a month-by-month generator. DEFAULT accepts
# every timestamp, so there is no range to keep ahead of and no gap for a row to
# fall through -- including the far-future and far-past values tests use precisely
# because they are implausible. A generator would prove nothing extra here and
# would need maintaining as the clock moves.
#
# This is a schema-build concern, not a test fixture, which is why it lives beside
# the models instead of in `tests/conftest.py`: two callers build schemas from this
# metadata (the suite and the contract-capture script) and a step either of them
# can forget is a step that will be forgotten. Production never reaches this code
# -- its schema comes from `flask db upgrade`, and the migration creates real
# monthly partitions alongside a DEFAULT that catches the gaps.
#
# `after_create` for the same reason the `updated_at` triggers above use it: the
# partition is DDL that has to follow the table it attaches to.
for _partitioned_table in PARTITIONED_TABLES:
    sa_event.listen(
        _partitioned_table,
        "after_create",
        DDL(
            'CREATE TABLE IF NOT EXISTS "%s%s" PARTITION OF "%s" DEFAULT'
            % (_partitioned_table.name, DEFAULT_PARTITION_SUFFIX, _partitioned_table.name)
        ).execute_if(dialect="postgresql"),
    )
del _partitioned_table
