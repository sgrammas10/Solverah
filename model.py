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
from sqlalchemy.orm import deferred
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

    __table_args__ = (
        # The dashboard's count, the export's list and the deletion's DELETE all
        # filter on user_id alone; before 20260928_ledger_indexes each one scanned
        # the table.
        db.Index("ix_job_recommendation_user_id", "user_id"),
    )


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
    #: Not read since Phase 2a; kept one release so a rollback is a redeploy.
    #: The drop is the next release's migration.
    #:
    #: Deferred, so a user load no longer carries the whole pre-2a document. The
    #: one writer left, the deletion tombstone (`account_repository.tombstone_user`),
    #: assigns it without reading it; anything that does read it pays one SELECT
    #: at that moment.
    profile_data = deferred(db.Column(JSON, default=dict))

    # Email confirmation.
    #
    # `confirmation_token` and `confirmation_sent_at` are absent from Part 4.2,
    # which assumes a separate token store alongside `user_sessions`. The
    # sessions table exists as of S3 (2026-09-03) and holds *refresh* tokens
    # only -- it is not the general token store Part 4.2 draws, and one-time
    # email codes have a different shape, a different lifetime, and no rotation
    # chain. Both columns are still live behind `POST /auth/email/verify`, so
    # they stay here rather than being folded into a table that does not model
    # them; deleting a live column because the target diagram does not draw it
    # is deleting a feature by omission.
    #
    # `confirmation_token` has no index (dropped by 20260928_ledger_indexes). No
    # query filters on it: every reader finds the user by email first and then
    # compares the token in Python.
    email_confirmed_at = db.Column(db.DateTime(timezone=True))
    confirmation_token = db.Column(db.String(64), nullable=True)
    confirmation_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Password reset via OTP. Carried forward for the same reason.
    reset_token = db.Column(db.String(64), nullable=True)
    reset_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)

    #: Declared by Part 4.2 and still not maintained. `user_sessions` exists as
    #: of S3, and its `issued_at` answers the same question without a second
    #: write on the login path -- `SELECT max(issued_at) FROM user_sessions
    #: WHERE user_id = ?`. That is the argument that left this column alone in
    #: Phase 2c, and building the sessions table strengthens it rather than
    #: retiring it.
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


class UserSession(db.Model):
    """One refresh token: the row that makes a session revocable.

    Part 4.2 declared this table and nothing built it, which is audit finding
    1.1 (HIGH): `POST /auth/logout` cleared the cookie and the access JWT stayed
    valid for the rest of its hour, so a stolen cookie survived the victim
    logging out and no operator action short of rotating `JWT_SECRET_KEY`
    fleet-wide revoked it.  A bare JWT is self-validating, which is exactly the
    property that makes it unrevocable -- there is nothing for a logout to
    change.  A row is.

    **The token is never here.**  `token_hash` is the SHA-256 of a value that
    exists in one place, the user's cookie; see `domain.auth.hash_refresh_token`
    for why the digest is SHA-256 rather than bcrypt.

    **A family is a login.**  Every rotation carries `family_id` forward, so the
    chain minted by one sign-in shares one id however many times it rotates.
    That is what makes reuse detection possible: a token presented after it was
    retired means the chain leaked, and the whole family dies rather than the
    one row -- the attacker's copy and the victim's copy are indistinguishable
    once both have been seen, so leaving either alive leaves the attacker in.

    **Rows outlive their tokens on purpose.**  A retired row is not deleted; it
    keeps `retired_at` and `retired_reason`, which is what turns the table into
    an audit trail -- "this session ended because the user logged out", not
    "this session is gone".  `flask retention run` deletes them once they are
    past `refresh_tokens.PURGE_DAYS`, which is the 30-days-past-expiry row in
    the Part 4.8 retention table.

    **`user_agent` and `ip` are deliberately not built**, though Part 4.2 draws
    them.  They are per-request identifying data, and the feature that would
    read them -- a device list, "sign out everywhere else" -- does not exist.
    The same audit that raised finding 1.1 raised #18 and #7 against exactly
    this shape: identifying columns retained past any reader.  They arrive with
    the screen that shows them.
    """

    __tablename__ = "user_sessions"

    id = db.Column(db.BigInteger, db.Identity(always=True), primary_key=True)

    #: Every descendant of one sign-in shares this. Rotation carries it
    #: forward; reuse detection revokes on it.
    family_id = db.Column(
        UUID(as_uuid=True), nullable=False, server_default=db.text("uuidv7()")
    )
    #: Named explicitly, unlike most foreign keys in this file, so the schema
    #: `db.create_all()` builds and the schema the migration builds carry the
    #: same constraint names. Unnamed, SQLAlchemy leaves it to Postgres and the
    #: test database ends up with `user_sessions_user_id_fkey` while production
    #: has `fk_user_sessions_user` -- a divergence that is invisible until
    #: something addresses a constraint by name.
    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_sessions_user"),
        nullable=False,
    )

    #: Hex SHA-256 of the opaque token. Unique, because it is the lookup key.
    token_hash = db.Column(db.Text, nullable=False)

    #: The row this one replaced, and the row that replaced this one. Two
    #: columns rather than one because both directions are read: the parent
    #: gives the audit chain, and the successor is what tells a stampede's
    #: second request that rotation already happened and which row it landed on.
    parent_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "user_sessions.id", ondelete="SET NULL", name="fk_user_sessions_parent"
        ),
    )
    successor_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "user_sessions.id", ondelete="SET NULL", name="fk_user_sessions_successor"
        ),
    )

    issued_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now()
    )
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)

    #: When this token stopped being usable, and why. Both or neither -- a death
    #: with no cause is an audit row that cannot answer the question it exists
    #: for, and the check constraint refuses it.
    retired_at = db.Column(db.DateTime(timezone=True))
    retired_reason = db.Column(db.Text)

    __table_args__ = (
        db.Index("uq_user_sessions_token_hash", "token_hash", unique=True),
        db.Index("ix_user_sessions_family", "family_id"),
        db.Index("ix_user_sessions_user_issued", "user_id", db.text("issued_at DESC")),
        # The two self-references, for their `ON DELETE SET NULL` actions: every
        # row the retention purge deletes makes Postgres look up the rows whose
        # parent or successor it was. Plain and NON-UNIQUE on purpose --
        # `refresh_tokens.rotate` inserts the successor before it claims the
        # parent, and that order is deadlock-free only while no unique index
        # covers these columns.
        db.Index("ix_user_sessions_parent", "parent_id"),
        db.Index("ix_user_sessions_successor", "successor_id"),
        # The retention pass reads exactly these two halves, and they are
        # disjoint: live rows by `expires_at`, dead rows by `retired_at`. One
        # index over both would make each scan the other's rows, and in steady
        # state the dead half is almost all of them.
        db.Index(
            "ix_user_sessions_live",
            "expires_at",
            postgresql_where=db.text("retired_at IS NULL"),
        ),
        db.Index(
            "ix_user_sessions_retired",
            "retired_at",
            postgresql_where=db.text("retired_at IS NOT NULL"),
        ),
        db.CheckConstraint(
            "(retired_at IS NULL AND retired_reason IS NULL) OR "
            "(retired_at IS NOT NULL AND retired_reason IS NOT NULL)",
            name="ck_user_sessions_retirement_complete",
        ),
        db.CheckConstraint(
            "retired_reason IS NULL OR retired_reason IN "
            "('rotated', 'logged_out', 'reused', 'expired')",
            name="ck_user_sessions_retired_reason",
        ),
    )


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
    # No index=True: the unique constraint is the index. The chain also built a
    # plain ix_company_slug beside it, dropped by 20260928_ledger_indexes.
    slug = db.Column(db.String(200), nullable=False, unique=True)
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

    __table_args__ = (
        # The one spelling of "this address" on this table. The account export
        # and deletion, the dashboard's intake banner and the retention sweep all
        # compare through `email_key` below, and this index is built on that
        # same expression. `email` is stored as submitted (VARCHAR, not CITEXT),
        # so a lookup that compared the column directly could neither use this
        # index nor match an address that differs only in case.
        db.Index("ix_intake_submissions_email_lower", db.func.lower(email)),
        # Retention's age filter (`created_at < cutoff`).
        db.Index("ix_intake_submissions_created_at", "created_at"),
    )

    @hybrid_property
    def email_key(self) -> str:
        """The address as every lookup compares it: lower-cased."""
        return (self.email or "").lower()

    @email_key.inplace.expression
    @classmethod
    def _email_key_expression(cls):
        """``lower(email)`` -- the expression ``ix_intake_submissions_email_lower`` indexes."""
        return db.func.lower(cls.email)


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


class ScorerRun(db.Model):
    """One run of the LLM company-culture extractor: what produced a set of scraped scores.

    Separate from ModelRun on purpose (S1-6, and the PROPOSED DDL argues it at length). The
    two version axes are unrelated: the scorer's moves when a vendor ships a model update,
    the Bayesian model's when priors or dimensions change. Fused into one table neither is
    independently queryable, so a "did the rubric change this, or did the model?" question
    -- the question the whole scorer sprint exists to answer -- could not be asked.

    This is what makes anchor wording a re-run rather than a rebuild: every scraped score
    points at the exact rubric text, packet build and pinned model snapshot behind it.
    """

    __tablename__ = "scorer_run"

    id = db.Column(db.BigInteger, primary_key=True)
    model = db.Column(db.Text, nullable=False)
    temperature = db.Column(db.Numeric, nullable=True)
    temperature_honored = db.Column(db.Boolean, nullable=False)
    reasoning_effort = db.Column(db.Text, nullable=True)
    rubric_version = db.Column(db.Text, nullable=False)
    packet_version = db.Column(db.Text, nullable=False)
    run_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    notes = db.Column(db.Text, nullable=True)


class CompanyDimensionScore(db.Model):
    """Per company per dimension, with SOURCE + CONFIDENCE -- the cold-start wedge.

    scraped/researched rows are guesses with low-ish confidence; a `declared` row (from the
    company itself, later) upgrades the same shape in place. `is_ground_truth` flags the
    companies the scraped model can be calibrated against. Culture goes stale, so every row
    is dated (`as_of`) and re-scoring inserts rather than overwrites.
    """

    __tablename__ = "company_dimension_score"

    id = db.Column(db.Integer, primary_key=True)
    # No index=True: uq_cscore_company_dim_source_asof below leads with company_id.
    # The separate one was dropped by 20260928_ledger_indexes.
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False)
    dimension_key = db.Column(db.String(32), nullable=False)
    score = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(16), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    is_ground_truth = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    as_of = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    # Which LLM run produced this row (S1-6). NULL for 'researched' (human) and 'declared'
    # (from the company) rows, which have no scorer run and never will.
    scorer_run_id = db.Column(
        db.BigInteger, db.ForeignKey("scorer_run.id"), nullable=True, index=True
    )

    __table_args__ = (
        # NULLS NOT DISTINCT is load-bearing, not a flourish. scorer_run_id joined this key
        # so one company can be scored twice on one day under two rubrics -- but Postgres
        # treats NULLs as distinct, so a PLAIN unique constraint over these five columns
        # would silently stop de-duplicating the rows that have no scorer run: two human
        # 'researched' rows for the same company/dimension/day would both insert where the
        # second is refused today. NULLS NOT DISTINCT keeps both halves. Requires PG15+;
        # this repo runs 18. Both halves are tested in tests/test_company_side_tables.py.
        db.UniqueConstraint(
            "company_id", "dimension_key", "source", "as_of", "scorer_run_id",
            name="uq_cscore_company_dim_source_asof",
            postgresql_nulls_not_distinct=True,
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
    scorer_run = db.relationship("ScorerRun", backref="dimension_scores")


class DimensionScoreCitation(db.Model):
    """The evidence quotes behind one company dimension score, and whether each verified.

    Nothing had anywhere to put a citation before this: nothing produced evidence quotes
    until the scorer pipeline (S1-1). `matched` / `matched_excerpt_id` / `source_tag` are
    the citation VERIFIER's output (S1-5), never the model's self-report -- provenance is
    computed downstream by matching each quote to the packet's addressable excerpts, whose
    source class is already deterministic, rather than trusted from the thing being checked.

    An UNMATCHED quote is stored, not discarded. A quote that fails to verify -- invented,
    or garbled past recognition -- is exactly the failure this table exists to make visible,
    and dropping it would leave the score looking better evidenced than it is. The CHECK
    below is the other half of that: an unverified quote carries no provenance, because it
    has none to report.

    Makes the 08-10 decision-3 measurement a real query (does a score above 0.7 have any
    non-company-authored source behind it?) instead of a rater's manual flag. See
    company_score_store.noncompany_support.
    """

    __tablename__ = "dimension_score_citation"

    id = db.Column(db.BigInteger, primary_key=True)
    # Integer rather than BigInteger: it references company_dimension_score.id, which the
    # applied 20260819 migration made INTEGER even though schema.sql had declared it
    # BIGSERIAL. Matching the column actually referenced beats matching the proposal.
    company_dimension_score_id = db.Column(
        db.Integer,
        db.ForeignKey("company_dimension_score.id", name="fk_citation_score"),
        nullable=False,
    )
    quote_text = db.Column(db.Text, nullable=False)
    matched = db.Column(db.Boolean, nullable=False)
    matched_excerpt_id = db.Column(db.Text, nullable=True)
    source_tag = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.CheckConstraint(
            "(matched AND matched_excerpt_id IS NOT NULL AND source_tag IS NOT NULL) "
            "OR (NOT matched AND matched_excerpt_id IS NULL AND source_tag IS NULL)",
            name="ck_citation_provenance_iff_matched",
        ),
        # Named explicitly rather than via index=True: the PROPOSED DDL and the migration
        # both call it ix_citation_score, and index=True would generate
        # ix_dimension_score_citation_company_dimension_score_id instead -- the exact
        # model-vs-migration drift this repo already has elsewhere and does not need more of.
        db.Index("ix_citation_score", "company_dimension_score_id"),
    )

    score = db.relationship("CompanyDimensionScore", backref="citations")


class CompanyConfounderValue(db.Model):
    """Confounder value per company. Generic value columns (num OR cat) so a new confounder
    is an INSERT, never a migration. Values are stored RAW/unscaled; the model standardizes
    via solverah_model_config.yaml. The loader is the only range guardrail -- deliberately,
    per schema.sql's design notes."""

    __tablename__ = "company_confounder_value"

    id = db.Column(db.Integer, primary_key=True)
    # No index=True: uq_conf_company_key_source_asof below leads with company_id.
    # The separate one was dropped by 20260928_ledger_indexes.
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False)
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
    # No index=True: uq_weight_run_name below leads with model_run_id. The separate
    # one was dropped by 20260928_ledger_indexes.
    model_run_id = db.Column(db.Integer, db.ForeignKey("model_run.id"), nullable=False)
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
# Environment side -- the Situation Report instrument (BUILD_PLAN A-2)
# ---------------------------------------------------------------------------
# A self-report about the user's OWN job, not a company profile: there is no `company`
# row behind it and no scraped/researched/declared source axis. That is the "inversion"
# BUILD_PLAN's E-4 names -- training pairs for the causal model come from what the user
# says about their own environment, keyed to their own user_id, the same key their
# `person_dimension_score` rows already carry. So `environment_dimension_score` is
# deliberately shaped like `person_dimension_score` (long-format rows, dimension_key a
# plain validated-in-code string, no registry table -- schema.sql principle 1 and the
# person-side precedent above) rather than like `company_dimension_score`: the join
# E-4's assemble_training_data needs is (user_id, dimension_key, score) on both sides,
# not a (company_id, source, as_of) resolution.
#
# APPEND-ONLY, D-16 tradition, and unlike `person_dimension_score`: every submission
# writes a brand-new `environment_reports` row and a brand-new set of
# `environment_dimension_score` rows. There is no "current" row per user to upsert --
# person-side scoring upserts per (user, dimension, scoring_key_version) because there
# is exactly one live score per key version, but here the history itself is the point:
# Pulse trends and future training rows both read the full sequence of a user's reports,
# not just the latest. Nothing in this module updates an existing row.
#
# D-15 pinning (⚑5 / PRODUCT_DECISIONS §2) is deliberately NOT implemented here. The
# Situation Report pins to a named person-side snapshot, not to an environment report --
# environment data is the side that is allowed to vary freely (PRODUCT_DECISIONS: "what
# does vary freely is the environment side ... nobody has a reason to game"). Storage
# that let one of these rows reference a person-side submission would put a pin where
# the product decision says there must not be one; A-5 does the pinning, elsewhere, over
# `person_dimension_score.submission_id`, which this table does not touch.
ENV_DIMENSIONS = ("autonomy", "pace", "collaboration", "feedback", "innovation", "decision")

#: `Profile.career_status`'s vocabulary (`backend/services/path_scoring.py`,
#: `path_narrative.py`), snapshotted at submission time because A-1's needs-forward
#: framing (BUILD_PLAN A-1) depends on which one was true the day the user described
#: their job, not on whatever the profile says later.
CAREER_STATUSES = ("employed", "between_jobs", "first_job")

#: `environment_reports.industry`'s vocabulary: the `industry` confounder's levels
#: in causal_graph/v1_model/solverah_model_config.yaml, which
#: `work_pulse.situation_items.INDUSTRY_LEVELS` restates. A tripwire test asserts all
#: three agree.
ENV_INDUSTRIES = ("tech", "finance", "healthcare", "retail", "other")

#: `environment_reports.subject`'s vocabulary (PRODUCT_DECISIONS.md §2, Sebastian,
#: 2026-10-01): which job a report describes. `current` is the user's current or most
#: recent job -- every row before that date, and the only kind the Situation Report
#: reads. `past` is the one job before that, filed at most once per user, after a
#: current report exists.
ENV_REPORT_SUBJECTS = ("current", "past")


class EnvironmentReport(db.Model):
    """One submission of the environment-side instrument. Append-only: id is not a person's
    "current" report, it is one dated observation, and a resubmission (Pulse event-triggered
    or otherwise) is always a new row, never an update to this one.

    `raw_answers` holds the payload as sent (item key -> choice), the same shape
    `assessment_submissions.answers` already uses for the app's other non-`core`
    instruments. A JSONB blob rather than a normalized per-item table on purpose: these
    items are not D-01-sensitive (A-1: "user describes a job, not themselves"), so none of
    the token-map/re-derivation machinery `assessment_response` exists for applies, and
    keeping the raw shape generic means A-1's item bank can land, and change, without a
    migration here -- this table was built before A-1's item keys existed.
    """

    __tablename__ = "environment_reports"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    # No index=True here: ix_environment_reports_user_submitted below already leads with
    # user_id, so a separate single-column index would be redundant (assessment_submissions
    # follows the same rule for the same reason).
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    submitted_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    raw_answers = db.Column(JSONB, nullable=False)
    # 1 (seed) .. 5 (enterprise) -- schema.sql's `stage_size` confounder, unscaled.
    stage_size = db.Column(db.SmallInteger, nullable=False)
    # 1..5 MARKET-RELATIVE pay posture, NOT dollars -- schema.sql's `comp` confounder,
    # redefined the same way on this side as on the company side. NULLable: the
    # environment instrument's "not sure" option (PRODUCT_DECISIONS.md §2,
    # "Environment-instrument rulings", 2026-09-10) stores a real "I don't know"
    # rather than forcing a guess -- Finding 6's measurement error is non-random,
    # so a forced 1..5 answer would under-report underpayment exactly where it
    # is worst.
    comp = db.Column(db.SmallInteger, nullable=True)
    # The model's categorical `industry` confounder, stored as the level key (ENV_INDUSTRIES),
    # the way schema.sql's `value_cat` carries it on the company side. NULLable twice over:
    # rows written before 2026-10-01 were never asked (version env-v1-...), and from then on
    # NULL is the "not sure / prefer not to say" option (PRODUCT_DECISIONS.md §2, 2026-10-01).
    industry = db.Column(db.Text, nullable=True)
    # "Overall, how well is this role working for you?" 1..5 -- the model's outcome node,
    # same ordinal shape as `outcome_experienced.working_scale`.
    experienced_outcome = db.Column(db.SmallInteger, nullable=False)
    #: The user's status WHEN THEY FILED. On a `subject='past'` row this is still the
    #: filer's status that day, not a description of the past job.
    career_status = db.Column(db.Text, nullable=False)
    #: Which job this row describes (ENV_REPORT_SUBJECTS). Every read that means "the
    #: user's job" -- the Situation Report, the dashboard -- filters on `current`.
    subject = db.Column(db.Text, nullable=False, server_default="current", default="current")
    #: ⚑6: optional, stored, displayed nowhere at launch -- the future company-aggregation
    #: lane's join key, not a launch feature. Pre-normalized (lowercased/trimmed) by the
    #: caller so a later aggregation query is a GROUP BY, not a fuzzy match.
    employer_name_normalized = db.Column(db.Text, nullable=True)
    #: Which item set produced `raw_answers` -- `assessment_response.form_version`'s role,
    #: under the name BUILD_PLAN §3.2 gives this column.
    version = db.Column(db.Text, nullable=False)

    __table_args__ = (
        db.CheckConstraint(
            "stage_size >= 1 AND stage_size <= 5", name="ck_envreport_stage_size_range"
        ),
        db.CheckConstraint(
            "comp IS NULL OR (comp >= 1 AND comp <= 5)", name="ck_envreport_comp_range"
        ),
        db.CheckConstraint(
            "industry IS NULL OR industry IN %s" % (ENV_INDUSTRIES,),
            name="ck_envreport_industry_vocab",
        ),
        db.CheckConstraint(
            "experienced_outcome >= 1 AND experienced_outcome <= 5",
            name="ck_envreport_experienced_outcome_range",
        ),
        db.CheckConstraint(
            "career_status IN %s" % (CAREER_STATUSES,),
            name="ck_envreport_career_status_vocab",
        ),
        db.CheckConstraint(
            "subject IN %s" % (ENV_REPORT_SUBJECTS,),
            name="ck_envreport_subject_vocab",
        ),
        db.CheckConstraint(
            "subject = 'current' OR career_status <> 'first_job'",
            name="ck_envreport_past_not_first_job",
        ),
        db.Index(
            "ix_environment_reports_user_submitted",
            "user_id",
            db.text("submitted_at DESC"),
        ),
    )

    user = db.relationship("User", backref="environment_reports")


class EnvironmentDimensionScore(db.Model):
    """Derived 0..1 score for one environment report on one dimension. Long-format, mirroring
    `person_dimension_score` so E-4's `assemble_training_data` reads both sides through the
    same shape -- a JOIN on `user_id`/`dimension_key`, not a translation layer.

    `user_id` is denormalized here rather than reached through `environment_report_id`
    alone: `person_dimension_score` is queried by `user_id` directly, and giving this table
    the same column lets a consumer write the identical query against either one.

    No uniqueness on `(user_id, dimension_key)` -- deliberately unlike
    `person_dimension_score`. Many historical reports per user must coexist, each
    contributing its own six rows; only `(environment_report_id, dimension_key)` needs to
    be unique, to stop one submission writing the same dimension twice.
    """

    __tablename__ = "environment_dimension_score"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    # No index=True: uq_edscore_report_dim below leads with environment_report_id.
    # The separate one was dropped by 20260928_ledger_indexes.
    environment_report_id = db.Column(
        db.BigInteger,
        db.ForeignKey("environment_reports.id"),
        nullable=False,
    )
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False, index=True)
    dimension_key = db.Column(db.String(32), nullable=False)
    score = db.Column(db.Float, nullable=False)
    scored_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "environment_report_id", "dimension_key", name="uq_edscore_report_dim"
        ),
        db.CheckConstraint("score >= 0 AND score <= 1", name="ck_edscore_score_range"),
    )

    environment_report = db.relationship("EnvironmentReport", backref="dimension_scores")
    user = db.relationship("User", backref="environment_dimension_scores")


# ---------------------------------------------------------------------------
# Manager Decoder: the observed-manager instrument's storage (BUILD_PLAN C-3)
# ---------------------------------------------------------------------------
# ⚑4 (PRODUCT_DECISIONS.md §2): one shared manager-profile store, built once here,
# consumed by two features -- the Decoder's playbook (`manager_match/decoder.py`) today,
# the Situation Report's manager section (workstream A) once it lands. Neither consumer
# gets its own copy; a table named for the Decoder specifically would have made the
# second consumer's landing look like a migration instead of a query.
#
# APPEND-ONLY, D-16 tradition, same shape as `EnvironmentReport`: `id` is not a person's
# "current" sitting, it is one dated observation, and a retake is always a new row.
# `manager_profile_store.latest_manager_profile` is what "current" means to every reader.


class ManagerProfile(db.Model):
    """One sitting of the manager-profile instrument (`manager_match/manager_profile.py`),
    for one user, about their actual manager.

    `answers` STORES AUTHORED OPTION IDENTITY, NOT SCREEN POSITION
    -----------------------------------------------------------------
    Sebastian's 2026-09-10 storage ruling: `answers[i]["choice"]` is `"a"` or `"b"` exactly
    as `manager_match/manager_profile.py`'s `MANAGER_PROFILE_QUESTIONS` keys the option,
    never which side of the screen it rendered on. Presentation order is a free frontend
    choice forever precisely because storage never depends on it --
    `score_manager_profile`'s own validation already enforces this shape (`choice` must be
    `"a"` or `"b"`, looked up against the question's own `score_a`/`score_b`), so this
    column is a direct persistence of what the scorer already required, not a second
    encoding of it.

    `scoring_key` IS A COLUMN, NOT A JSONB FIELD, AND THAT IS THE POINT
    ---------------------------------------------------------------------
    `manager_match/score.py`'s `SCORING_KEY` -- and the mm-q11 episode it documents -- is
    why: a marker living inside an optional JSON blob can be silently absent from an old
    row, and absence becomes indistinguishable from "scored under some earlier, unmarked
    key". A NOT NULL column with no server default forces every write path to state it, so
    a caller that forgets fails loudly at insert instead of leaving a row ambiguous.
    """

    __tablename__ = "manager_profiles"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    # No index=True: ix_manager_profiles_user_created below already leads with user_id,
    # the same reasoning EnvironmentReport's user_id column gives for skipping one.
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    #: The respondent's raw sitting -- see the class docstring's authored-identity rule.
    answers = db.Column(JSONB, nullable=False)
    #: {"autonomy": .., "feedback_style": .., "relationship": .., "growth_focus": ..} --
    #: `score_manager_profile`'s own output, persisted unmodified.
    dimension_scores = db.Column(JSONB, nullable=False)
    #: Which scoring key produced `dimension_scores`. See the class docstring.
    scoring_key = db.Column(db.Text, nullable=False)
    #: Which item set produced `answers` -- `EnvironmentReport.version`'s role, under the
    #: same name.
    version = db.Column(db.Text, nullable=False)

    __table_args__ = (
        db.Index(
            "ix_manager_profiles_user_created",
            "user_id",
            db.text("created_at DESC"),
        ),
    )

    user = db.relationship("User", backref="manager_profiles")


# ---------------------------------------------------------------------------
# Situation Report: the D-15 pin (BUILD_PLAN A-4/A-5, ⚑5)
# ---------------------------------------------------------------------------
# PRODUCT_DECISIONS.md §2, "What a D-15-conforming Situation Report returns": each
# report reads through a NAMED person-side snapshot -- the first completed `core`
# sitting -- so a retake is not a watchable gradient. `PersonDimensionScore` upserts
# in place per (user, dimension, scoring_key_version) (see its own docstring), so it
# cannot hold that history itself; a retake would silently move every report that
# read through it.
#
# The default pin needs no row here at all: "the first completed core sitting" is
# `assessment_store.first_completed_core_submission_id`, a stable fact computed live
# from the append-only `assessment_submissions`/`assessment_response` rows (adding a
# LATER sitting never changes which one was first). This table exists only to hold
# the EXPLICIT override an Enterprise "recalibrate" action writes -- absence means
# "still pinned to the first sitting", not "unset".


class SituationReportPin(db.Model):
    """One user's explicit re-pin target, written only by
    `POST /me/situation-report/recalibrate`.

    Mutable, unlike `EnvironmentReport`/`ManagerProfile`'s append-only rows -- there is
    exactly one active override per user, and moving it is a deliberate, explicit
    action rather than a routine submission. The history of WHEN it moved lives in
    `AuditLog` (`solverah.services.audit.log_audit_event`, action
    `"situation_report_recalibrate"`), not in a second row here.

    `submission_id` names an `assessment_submissions.public_id.hex` for a
    `kind="core"` sitting. No foreign key: `PersonDimensionScore`/`AssessmentResponse`'s
    own `submission_id` columns are plain strings for the same reason -- `public_id`
    carries no unique index to reference, and reading through it stays behind
    `assessment_store` (D-01) rather than behind a joinable key another table could
    reach through.
    """

    __tablename__ = "situation_report_pins"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    user_id = db.Column(
        db.BigInteger, db.ForeignKey("users.id"), nullable=False, unique=True
    )
    submission_id = db.Column(db.String(36), nullable=False)
    pinned_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    user = db.relationship("User", backref=db.backref("situation_report_pin", uselist=False))


# ---------------------------------------------------------------------------
# The Pulse: recurring check-in storage (BUILD_PLAN B-1)
# ---------------------------------------------------------------------------
# `work_pulse/pulse_items.py` owns the item bank and the round-robin selection; these
# two tables hold only what a submission or an event says, unmodified -- the same
# division of labour as `EnvironmentReport`/`environment_report_store.py`. Both
# APPEND-ONLY (D-16 tradition): a check-in is one dated observation and an event is one
# dated fact, never an update to an earlier row -- history is the point, since B-3's
# trend view and E-4's training rows both read across it.
#
# D-7 (BUILD_PLAN, added 2026-09-10): "any table added later joins /me/export and the
# account-deletion flow the day it is created." `environment_reports` and
# `manager_profiles` predate that rule and are its tracked gap (BUILD_PLAN D-7); these
# two tables do not inherit it -- `solverah/services/account_service.py`'s
# `export_account_data` reaches `pulse_checkins`/`pulse_events` from the same commit
# that creates them, both exported unconditionally.
#
# D-7b (2026-09-11 ruling): the two tables do NOT share one deletion answer.
# `pulse_checkins` carries no free text -- every column is a validated 1..5 integer --
# so it rides the tombstone de-identified, same reconciliation as `environment_reports`
# above; `account_repository.delete_personal_rows` does not touch it. `pulse_events.note`
# is free text, and free text is never retained de-identified, so that table is destroyed
# on deletion, same as before.

#: `pulse_events.event_type`'s vocabulary -- BUILD_PLAN B-1. A plain CHECK-constrained
#: string, same convention as `CAREER_STATUSES` above: validated in code and in the
#: migration's own literal CHECK, not a DB enum type or a registry table.
PULSE_EVENT_TYPES = ("new_manager", "reorg", "remote_change", "role_change", "other")

#: `pulse_events.note`'s cap. "Short free text" (BUILD_PLAN B-1) -- long enough to name
#: what happened, short enough that a check-in stays a 60-second interaction rather than
#: growing a second form inside it.
PULSE_EVENT_NOTE_MAX_LENGTH = 280


class PulseCheckin(db.Model):
    """One completed Pulse check-in: the three round-robin dimension scores
    `work_pulse.pulse_items.dimensions_for_checkin` served plus the outcome item,
    always asked. `item_scores` holds exactly the dimensions that sequence served --
    never all five -- so a reader must not assume every key is present on every row;
    `pulse_store.pulse_checkin_history` is what turns a run of these into a per-dimension
    trend with gaps where a dimension wasn't asked that week.

    No derived-score column anywhere, unlike `EnvironmentReport`/`EnvironmentDimensionScore`:
    a Pulse answer already IS its own score (a plain 1..5), so there is nothing to
    compute between the answer and what B-3's chart reads.

    RETAINED, DE-IDENTIFIED, ON ACCOUNT DELETION (D-7b, 2026-09-11)
    -----------------------------------------------------------------
    No column on this table is free text, so `account_repository.delete_personal_rows`
    does not touch it -- it rides the tombstone exactly like `EnvironmentReport`.
    `PulseEvent` beside it makes the opposite call, because `note` is free text.
    """

    __tablename__ = "pulse_checkins"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    # No index=True: ix_pulse_checkins_user_taken below already leads with user_id, the
    # same reasoning EnvironmentReport's user_id column gives for skipping one.
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    taken_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    #: The round-robin sequence number this check-in was served under
    #: (`pulse_items.dimensions_for_checkin`'s second argument). Persisted rather than
    #: re-derived so `pulse_store.pulse_checkin_count`'s "how many has this user
    #: completed" and "what sequence did THIS row serve" never have to agree by
    #: recomputation -- the row states the fact it was written under.
    sequence = db.Column(db.Integer, nullable=False)
    #: {dimension_key: 1..5} for exactly the `pulse_items.ITEMS_PER_CHECKIN` dimensions
    #: that sequence served. Keys are `pulse_items.DIMENSIONS` members, validated in
    #: `pulse_store.write_pulse_checkin`, not by a DB-level JSONB schema check.
    item_scores = db.Column(JSONB, nullable=False)
    #: "This week, how well is work working for you?" -- `pulse_items.EXPERIENCED_ITEM`,
    #: asked every check-in, never round-robin.
    experienced = db.Column(db.SmallInteger, nullable=False)
    #: Which item set produced this row -- `EnvironmentReport.version`'s role, under the
    #: name this table's column uses (`pulse_items.FORM_VERSION`).
    version = db.Column(db.Text, nullable=False)

    __table_args__ = (
        db.CheckConstraint("sequence >= 0", name="ck_pulsecheckin_sequence_nonneg"),
        db.CheckConstraint(
            "experienced >= 1 AND experienced <= 5", name="ck_pulsecheckin_experienced_range"
        ),
        db.Index(
            "ix_pulse_checkins_user_taken",
            "user_id",
            db.text("taken_at DESC"),
        ),
    )

    user = db.relationship("User", backref="pulse_checkins")


class PulseEvent(db.Model):
    """One logged life/work event a user attaches to their Pulse timeline (a manager
    change, a reorg, going remote, a role change, or an unlisted "other"). Purely a
    dated annotation -- B-4's wiring (`BUILD_PLAN` B-4) reads these to decide when an
    environment-report resubmission should be prompted, and B-3's trend view plots them
    on the same axis as check-ins. Nothing here scores anything.

    DESTROYED, NOT RETAINED, ON ACCOUNT DELETION (D-7b, 2026-09-11)
    -------------------------------------------------------------------
    `note` is free text, and free text is never retained de-identified --
    `account_repository.delete_personal_rows` destroys every row for the deleting
    user. `PulseCheckin` beside it makes the opposite call: none of its columns are
    free text, so it rides the tombstone instead.
    """

    __tablename__ = "pulse_events"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    # No index=True: ix_pulse_events_user_at below already leads with user_id.
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    event_type = db.Column(db.Text, nullable=False)
    #: Optional -- most event types are self-explanatory from `event_type` alone; `note`
    #: exists for the "other" case and for anyone who wants to add context to a named one.
    note = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "event_type IN %s" % (PULSE_EVENT_TYPES,), name="ck_pulseevent_type_vocab"
        ),
        db.CheckConstraint(
            "note IS NULL OR char_length(note) <= %d" % PULSE_EVENT_NOTE_MAX_LENGTH,
            name="ck_pulseevent_note_length",
        ),
        db.Index(
            "ix_pulse_events_user_at",
            "user_id",
            db.text("at DESC"),
        ),
    )

    user = db.relationship("User", backref="pulse_events")


# ---------------------------------------------------------------------------
# Condition experiments (BUILD_PLAN B-5)
# ---------------------------------------------------------------------------
# ⚑2 (PRODUCT_DECISIONS.md §2, "The Pulse ships thin"): the designated cut line,
# built after B-1..B-4 landed. One experiment is a user running a named two-week
# change against one of `work_pulse.situation_content.GUIDANCE_CELLS`'s twelve
# `change_in_place` cells; the readout reads Pulse `experienced` check-ins from
# before and after (`work_pulse.experiments.compute_readout`). `register` is
# always `"change_in_place"` today -- the other two registers (`negotiate`,
# `rarely_moves`) describe a conversation or a ceiling, neither of which a
# two-week window can measure -- but the column exists rather than a hard-coded
# literal so a later register that IS runnable would not need a migration to be
# experimented on.
#
# MUTABLE, unlike `EnvironmentReport`/`PulseCheckin`'s append-only rows -- a
# running experiment's `status` moves to `abandoned` (the user's choice) or to
# `completed` (its two weeks ran out) in place, the same shape
# `SituationReportPin` mutates rather than appending. NO free text anywhere on
# the row, so it rides the tombstone de-identified on account deletion exactly
# like `pulse_checkins` (D-7b) -- see `solverah/services/account_service.py`.


class Experiment(db.Model):
    """One user's attempt at a named change-in-place cell, over a fixed two-week
    window.

    ONE ACTIVE EXPERIMENT PER USER, ENFORCED AT THE DATABASE
    -----------------------------------------------------------------
    `uq_experiments_one_active_per_user` below is a partial unique index on
    `user_id` where `status = 'active'`, not merely a service-layer check
    (`solverah.services.experiment_service` checks first and answers a `409`, but
    the index is what makes a race lose rather than silently double-book). The
    rule is a methodological one, not a UI nicety: a two-week change is
    confounded by a second concurrent one, so only one may run at a time.

    `status` is `active` / `completed` / `abandoned`. A partial index cannot
    carry a time predicate, so an experiment past its `ends_at` must stop being
    `active` for the index to keep meaning "one RUNNING experiment": the
    service moves it to `completed` before every read or write
    (`experiment_store.close_ended_experiments`). Until 2026-10-02 there was
    no such status and an ended row blocked every later start.

    `ends_at` IS STORED, NOT COMPUTED
    -----------------------------------------------------------------
    `started_at + 14 days` at write time, not derived on read. A later change to
    the window length must not silently move the end date of an experiment
    already in flight.

    `dimension`/`direction` NAME A CELL, NOT A FREE CHOICE
    -----------------------------------------------------------------
    Both are validated (`solverah.services.experiment_service`) against
    `work_pulse.situation_content.GUIDANCE_CELLS` before a row is written: the
    pair must be a real `change_in_place` cell, one of the twelve the gap engine
    can actually diagnose. `direction` uses `work_pulse.situation`'s short
    vocabulary (`under`/`over`) -- the same one `SituationDimensionReport.direction`
    already puts on the wire -- rather than `situation_content`'s longer
    `under_supplied`/`over_supplied`, so the report page can start an experiment
    from the exact `{dimension, direction}` pair a `StrainDimensionEntry` already
    carries, with no re-encoding.
    """

    __tablename__ = "experiments"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    # No index=True: ix_experiments_user_created below already leads with user_id,
    # the same reasoning EnvironmentReport's user_id column gives for skipping one.
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    dimension = db.Column(db.Text, nullable=False)
    direction = db.Column(db.Text, nullable=False)
    #: Always `"change_in_place"` today -- see the section docstring.
    register = db.Column(db.Text, nullable=False)
    started_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    #: `started_at` + the two-week window, stored at write time -- see the class
    #: docstring's "ends_at is stored, not computed".
    ends_at = db.Column(db.DateTime(timezone=True), nullable=False)
    status = db.Column(db.Text, nullable=False, default="active")
    abandoned_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.CheckConstraint(
            "dimension IN %s" % (ENV_DIMENSIONS,), name="ck_experiment_dimension_vocab"
        ),
        db.CheckConstraint(
            "direction IN ('under', 'over')", name="ck_experiment_direction_vocab"
        ),
        db.CheckConstraint(
            "register = 'change_in_place'", name="ck_experiment_register_vocab"
        ),
        # `completed` since 20261002_experiment_completed: an experiment whose
        # `ends_at` has passed is moved here lazily by
        # `experiment_store.close_ended_experiments`, so it drops out of the
        # partial index below and stops blocking the next start.
        db.CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="ck_experiment_status_vocab",
        ),
        db.CheckConstraint(
            "(status = 'abandoned') = (abandoned_at IS NOT NULL)",
            name="ck_experiment_abandoned_at_matches_status",
        ),
        db.Index("ix_experiments_user_created", "user_id", db.text("created_at DESC")),
        db.Index(
            "uq_experiments_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=db.text("status = 'active'"),
        ),
    )

    user = db.relationship("User", backref="experiments")


# ---------------------------------------------------------------------------
# Path Intelligence Tier 2: the deep fit, stored per (user, occupation) -- F-5
# ---------------------------------------------------------------------------
# `backend/services/path_deep_fit.deep_fit` is the analysis; this table is where
# one result is kept so a second click on the same card costs nothing. Design
# doc PATH_INTELLIGENCE_REDESIGN.md §5 #2: "stored, invalidated on profile
# write, mirroring `path_cache`'s `invalidate` discipline".
#
# MUTABLE, one row per (user, occupation) -- `SituationReportPin`'s shape, not
# `EnvironmentReport`'s append-only one. A fit is a derived read-through cache
# with a durable home, not an observation worth a history: nothing downstream
# reads "what did this user's fit for 15-1252.00 look like last month", and
# keeping every recomputation would grow a row per click per profile edit.
#
# DESTROYED, NOT RETAINED, ON ACCOUNT DELETION (D-7b). `payload.matched_skills`
# is the user's own typed skill names and `gap_skills` is derived from them, so
# the row carries free text about a person -- and free text is never retained
# de-identified. `account_repository.delete_personal_rows` deletes it explicitly,
# because deletion tombstones the user row rather than removing it and the
# foreign key's cascade therefore never fires.


class PathFit(db.Model):
    """One user's Tier-2 deep fit for one O*NET occupation.

    TWO STALENESS MECHANISMS, AND BOTH ARE LOAD-BEARING
    ---------------------------------------------------
    `profile_fingerprint` is a digest of exactly the `UserProfile` fields the
    analysis reads (`solverah.repositories.path_fit_repository.fingerprint`). A
    stored row whose fingerprint no longer matches the profile is stale and is
    recomputed, whatever its age.

    That is belt to the braces of explicit invalidation, not a replacement for
    it. Every write that changes a scoring input calls
    `path_fit_repository.invalidate`, enumerated and tested exactly as
    `path_cache.invalidate`'s call sites are -- but `path_cache`'s own docstring
    records the weakness of that enumeration: "missing one of those calls does
    not fail loudly; it serves a stale suggestion". A fingerprint on a durable
    row turns that silent failure into a recomputation, which costs four cached
    O*NET calls and never a wrong answer.

    `computed_at` carries the third input neither mechanism covers: O*NET's own
    content, which changes quarterly and which no profile write invalidates.
    `path_fit_repository.MAX_AGE` bounds it. This is the one place a TTL is the
    right tool rather than "a second, weaker correctness mechanism next to a
    working one" (`path_cache`), because for that input there is no first one.
    """

    __tablename__ = "path_fits"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    # No index=True: uq_path_fits_user_occupation below leads with user_id, so a
    # second index on the same column would serve nothing -- the same reasoning
    # EnvironmentReport's user_id column gives.
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    #: O*NET-SOC, e.g. "15-1252.00". No foreign key: occupations live in the
    #: corpus artifact (a `.npy` in S3), not in this database.
    onet_code = db.Column(db.Text, nullable=False)
    #: `path_deep_fit.DeepFit.to_dict()`, stored whole. Not decomposed into
    #: columns: every consumer wants the entire panel and nothing queries into
    #: it, so columns would buy a migration per field added and nothing else.
    payload = db.Column(JSONB, nullable=False)
    #: See the class docstring. Hex sha256, so a fixed 64 characters.
    profile_fingerprint = db.Column(db.Text, nullable=False)
    computed_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "onet_code", name="uq_path_fits_user_occupation"
        ),
    )

    user = db.relationship("User", backref="path_fits")


# ---------------------------------------------------------------------------
# Path Intelligence: inline card feedback for `adjacent` -- F-6
# ---------------------------------------------------------------------------
# One row per judgement a user has made about one occupation on their shortlist.
# `backend/services/path_scoring` rebuilds the retrieval query from these rows on
# every request: a Rocchio rotation toward what they called interesting, and a
# cosine radius raised past what they called too similar (design doc §3.2).
#
# JUDGEMENTS, NOT VECTORS, AND THAT IS THE WHOLE DESIGN. The obvious alternative
# is to store the rotated query -- one 1536-float column, written once per tap.
# It is worse in four ways that all have the same root: a stored vector is
# derived data pretending to be a fact.
#
#   * It is tied to a corpus build. `flask corpus build` runs quarterly (F-8) and
#     re-embeds every role document; a query rotated toward the old vectors is
#     silently wrong against the new ones, and nothing would say so.
#   * It is tied to an embedding model. Changing it would need a backfill nobody
#     can compute, because the inputs were thrown away.
#   * It cannot be audited. "Why am I being shown this?" is answerable from three
#     rows of (code, verdict); it is not answerable from 1536 floats.
#   * Reset is a DELETE here and an arithmetic inverse there.
#
# What it costs instead is a handful of `corpus.vector_for` lookups and two
# vector means per request -- microseconds against a retrieval that is already a
# 1,016 x 1536 matrix product.
#
# MUTABLE, one row per (user, occupation), upserted on re-tap: the user changing
# their mind about a card is a correction, not a second opinion, and a history of
# taps has no reader. Same shape as `PathFit` above and `SituationReportPin`.
#
# DESTROYED, NOT RETAINED, ON ACCOUNT DELETION (D-7b) -- see
# `tests/test_export_delete_coverage.py`'s entry for the reasoning, which is the
# `pulse_checkins` one rather than the `pulse_events` one: no column here is free
# text. It is destroyed anyway because what the row records is a person's stated
# preference about their own career, and the closed vocabulary makes the *format*
# safe rather than the content.


class PathFeedback(db.Model):
    """One user's verdict on one suggested occupation (BUILD_PLAN F-6).

    `verdict` is a closed vocabulary, mirrored in
    `solverah.repositories.path_feedback_repository.VERDICTS`:

    ``too_similar``
        A radius signal. Everything at least this close to the user's own
        occupation is excluded from their next shortlist.
    ``interesting``
        A direction signal. The retrieval query rotates toward it.
    ``not_for_me``
        The directional negative Rocchio's third term needs. Distinct from
        ``too_similar``: "too close to what I already do" and "wrong direction
        entirely" are different sentences and move the query different ways.

    Not an enum column. The vocabulary is enforced by the repository and by the
    API schema, and a Postgres enum would make adding a fourth verdict a
    migration -- see `Experiment.status` for the same call made the same way.
    """

    __tablename__ = "path_feedback"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    # No index=True: uq_path_feedback_user_occupation below leads with user_id,
    # and every read here is "every judgement for this user" -- the same
    # reasoning PathFit's user_id column gives.
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    #: O*NET-SOC, e.g. "15-1252.00". No foreign key, for PathFit's reason:
    #: occupations live in the corpus artifact, not in this database.
    onet_code = db.Column(db.Text, nullable=False)
    verdict = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    #: Bumped on every re-tap, so "most recent judgement" is answerable without a
    #: second row. `created_at` stays the first time they said anything about
    #: this card, which is the only thing an audit needs that `updated_at` loses.
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "onet_code", name="uq_path_feedback_user_occupation"
        ),
    )

    user = db.relationship("User", backref="path_feedback")


# ---------------------------------------------------------------------------
# Path Intelligence: what should change about the user's OWN job -- W-4
# ---------------------------------------------------------------------------
# One row per thing the user has said should change about the occupation they
# hold today: a task of that occupation they want more or less of, or one of the
# measured work conditions. `backend/services/path_scoring` reads them back as a
# `Wants` and rotates its query with them (design doc §8.3), the same way it
# rebuilds the Rocchio query from `PathFeedback` above.
#
# "FINE" IS THE ABSENCE OF A ROW, and that is the whole storage design rather
# than a saving. Three of the panel's answers are *more*, *fine* and *less*, and
# the middle one is what most rows would be: the panel shows the occupation's
# national task list, so "I never do that" and "that part is fine" are both
# honestly answered by saying nothing (design doc §8.7). Storing a third verdict
# would mean a `fine` row and a missing row had to mean the same thing at every
# read, which is two representations of one state and a bug waiting for the read
# that forgets. Clearing an answer therefore DELETES the row.
#
# KEYED TO THE ANCHOR OCCUPATION, AND OLD ROWS GO INERT RATHER THAN BEING
# DELETED. `anchor_onet_code` is the occupation the question was asked about. A
# user who changes job resolves to a different anchor, and every row under the
# old one stops being read -- it is not a stale answer, it is a true answer to a
# question about a job they no longer hold. They are kept because going back is
# a real thing that happens (a contract ends, a secondment finishes) and because
# a delete on a job change would need a job-change hook that does not exist and
# could not be trusted to fire.
#
# `item_key` SURVIVES A SIDECAR REFRESH. For a task it is a short digest of the
# ORIGINAL O*NET statement (`path_wants_repository.item_key_for_task`), not its
# position in the panel and not its display label: the tasks sidecar is rebuilt
# quarterly with the corpus and the labels are rewritten by an offline LLM pass,
# so a positional key would silently re-point an answer at a different task and a
# label key would lose every answer on a relabel. For a condition it is the axis
# name, which is code rather than data.
#
# `item_text` IS THE ORIGINAL STATEMENT, NEVER THE DISPLAY LABEL. It is what
# reaches the embedder (design doc §8.7, F-7's measured metaphor hazard), and
# storing it means a tapped task still scores after the sidecar drops it.
#
# DESTROYED, NOT RETAINED, ON ACCOUNT DELETION (D-7b) -- `PathFeedback`'s
# reasoning exactly, and see `tests/test_export_delete_coverage.py` for why the
# spelling rule and the meaning rule point different ways here too.


class PathWant(db.Model):
    """One thing this user says should change about their own occupation (W-4).

    ``kind`` is a closed vocabulary of two, mirrored in
    ``solverah.repositories.path_wants_repository.KINDS``:

    ``task``
        ``item_key`` is a digest of ``item_text``, and ``item_text`` is one of
        the anchor occupation's O*NET task statements, byte-exact.
    ``condition``
        ``item_key`` is an axis of ``occupation_conditions.AXES`` and
        ``item_text`` is empty -- an axis is a name in code, so there is no
        original text to preserve.

    ``verdict`` is ``more`` or ``less``. There is no ``fine``: see the section
    comment above for why the absence of a row is the third answer rather than a
    third value.

    Not enum columns, for the reason `PathFeedback` and `Experiment` give: the
    panel's vocabulary is a product question that is still moving, and a Postgres
    enum would make a fifth axis a migration.
    """

    __tablename__ = "path_wants"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    # No index=True: uq_path_wants_user_anchor_item below leads with user_id and
    # then anchor_onet_code, which is exactly the "every answer this user has
    # about this job" read -- the same reasoning PathFit's user_id column gives.
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    #: The occupation the question was about. O*NET-SOC, e.g. "15-1252.00". No
    #: foreign key, for PathFit's reason: occupations live in the corpus
    #: artifact, not in this database.
    anchor_onet_code = db.Column(db.Text, nullable=False)
    kind = db.Column(db.Text, nullable=False)
    item_key = db.Column(db.Text, nullable=False)
    #: The original O*NET statement for a task; empty for a condition.
    item_text = db.Column(db.Text, nullable=False, default="")
    verdict = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    #: Bumped when the user changes their mind about this item. `created_at`
    #: stays the first time they answered it, for PathFeedback's reason.
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "anchor_onet_code",
            "kind",
            "item_key",
            name="uq_path_wants_user_anchor_item",
        ),
    )

    user = db.relationship("User", backref="path_wants")


# ---------------------------------------------------------------------------
# Path Intelligence: the narrator's sentences, stored -- W-16
# ---------------------------------------------------------------------------
# One row per (user, occupation, fingerprint): the `why_text` and tags the
# narrator (`backend/services/path_narrative`) wrote for one card, filed under a
# digest of exactly what the prompt fed the model about that card and that
# person (`path_narrative.narrative_fingerprint`).
#
# WHY A TABLE. Until W-16 the only copy lived in `path_cache` -- per worker and
# lost on every deploy -- so a re-score after a wants save or a tap paid the
# narrator again for sentences it had already written, and the text changed
# under the reader on every save. The panel answers and the taps reorder the
# list but are not narrator inputs, so the sentence for a card is a function of
# the fingerprint alone and is worth keeping.
#
# THE FINGERPRINT IS THE CORRECTNESS, NOT AN INVALIDATION LIST. Nothing calls an
# `invalidate` here: a profile edit that changes a narrator input changes the
# fingerprint, and the old row simply stops being asked for. Old rows are bounded
# by `path_narrative_repository.MAX_AGE` on read and removed by its purge --
# `path_fits`' 30-day rule, for its reason (the model and O*NET's titles move
# under a stored sentence with no profile write to say so).
#
# APPEND-ONLY IN PRACTICE, KEYED BY FINGERPRINT. Unlike `path_fits`, a new
# fingerprint is a new row rather than an overwrite: going back to an earlier
# profile (re-adding a skill) finds its sentences again.
#
# DESTROYED ON ACCOUNT DELETION (D-7b). `why_text` is model-written prose ABOUT
# the person ("uses your Python and SQL"), and free text about a person is never
# retained de-identified. `account_repository.delete_personal_rows` deletes it
# explicitly: deletion tombstones the user row, so the cascade below never fires
# on that path. It is there for a hard delete.


class PathNarrative(db.Model):
    """The narrator's sentence and tags for one card, for one set of inputs (W-16)."""

    __tablename__ = "path_narratives"

    id = db.Column(db.BigInteger, autoincrement=True, primary_key=True)
    # No index=True: uq_path_narratives_user_code_fp leads with user_id, and
    # every read is "these codes for this user" -- PathFit's reasoning.
    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE", name="fk_pathnarrative_user"),
        nullable=False,
    )
    #: O*NET-SOC. No foreign key, for PathFit's reason: occupations live in the
    #: corpus artifact, not in this database.
    onet_code = db.Column(db.Text, nullable=False)
    #: Hex sha256 of the narrator's inputs for this card. See the section comment.
    fingerprint = db.Column(db.Text, nullable=False)
    #: Already scrubbed of grades (W-13) before it is written, and never a
    #: fallback sentence: only prose the narrator wrote is stored.
    why_text = db.Column(db.Text, nullable=False)
    profile_dimensions = db.Column(
        JSONB, nullable=False, server_default=db.text("'[]'::jsonb")
    )
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "onet_code",
            "fingerprint",
            name="uq_path_narratives_user_code_fp",
        ),
    )

    user = db.relationship(
        "User", backref=db.backref("path_narratives", passive_deletes=True)
    )


# ---------------------------------------------------------------------------
# Phase 2a -- profile_data, decomposed (docs/ARCHITECTURE.md Part 4.3)
# ---------------------------------------------------------------------------
#
# `User.profile_data` above is no longer read, and is written only by the deletion
# tombstone (`account_repository.tombstone_user` empties it). It is kept
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


# ---------------------------------------------------------------------------
# Platform tables (Part 4.7, Phase 3)
# ---------------------------------------------------------------------------


class Outbox(db.Model):
    """Domain events and emails that commit with the business write.

    Part 4.7, verbatim: the columns here are the ones that section declares and
    nothing else. It is the fix for "the email send failed so the request 500'd"
    -- registration used to create the account, commit it, then call Resend
    inline, so a provider blip turned a successful registration into either a
    500 or a silently missing verification code depending on which caller you
    landed in.

    The mechanism is one property: the row is inserted into the *caller's*
    transaction and never committed by itself, so "the account exists" and "the
    email is owed" become the same commit. Either both happened or neither did.
    A worker publishes afterwards (``solverah/services/outbox.py``), and if the
    worker never runs, the row is still there.

    NOT partitioned, unlike `audit_log`, `match_recommendation` and `rec_action`.
    Those three are append-only and unbounded, and partitioning is what lets a
    month be dropped in constant time. This table is a *queue*: rows are written,
    published within seconds, and swept once published. Its steady-state size is
    the backlog, not the history, so range partitions would be empty overhead --
    and a partitioned table would force `created_at` into the primary key, which
    would in turn make the by-id claim in `publish` a partition scan.

    `attempts` is incremented on every publish try, successful or not. It is the
    only failure state the table carries, which is deliberate: a `last_error`
    column would put provider text -- an address, a bounce reason -- in a second
    place, and the logs already carry it beside the row id. `drain` stops
    retrying a row once `attempts` reaches its ceiling, so a permanently bad
    payload parks rather than spinning.

    Payloads hold what the send needs, which for the two OTP topics is an address
    and a code. Neither is new exposure -- `users.confirmation_token` already
    stores the same code in plaintext -- but it does mean this table holds PII,
    and `purge_published` is what bounds how long.
    """

    __tablename__ = "outbox"

    id = db.Column(db.BigInteger, db.Identity(always=True), primary_key=True)
    topic = db.Column(db.Text, nullable=False)
    payload = db.Column(JSONB, nullable=False, default=dict)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    published_at = db.Column(db.DateTime(timezone=True))
    attempts = db.Column(db.SmallInteger, nullable=False, server_default=db.text("0"))

    __table_args__ = (
        # Partial, on the unpublished rows only. The drain query is
        # `WHERE published_at IS NULL ORDER BY created_at`, and the whole point
        # is that its cost tracks the backlog rather than the table: a published
        # row is not in this index at all.
        db.Index(
            "ix_outbox_unpublished",
            "created_at",
            postgresql_where=db.text("published_at IS NULL"),
        ),
        # The other half, for `purge_published`: `WHERE published_at IS NOT NULL
        # AND published_at < cutoff`. Partial on the purge's own first predicate,
        # so the two indexes split the table between them rather than overlap.
        db.Index(
            "ix_outbox_published",
            "published_at",
            postgresql_where=db.text("published_at IS NOT NULL"),
        ),
    )


class ResumeParseJob(db.Model):
    """One resume parse taken off the request path (Phase 3, item 3).

    `POST /me/resumes/{id}/parse-jobs` inserts a row and answers 202 with its
    `public_id`; a worker on the `default` queue does the parse; `GET
    /me/resume-parse-jobs/{job_id}` reports what happened. The synchronous
    `POST /me/resumes/{id}/complete` is untouched and still works -- this is a
    contract addition, and the old path stays until the frontend moves.

    A table rather than Celery's result backend, and the difference matters
    twice. The result backend is Redis, so the status endpoint would answer 404
    for every job the moment Redis restarted -- for work that had actually
    succeeded. And a result backend is a transport detail with a TTL, not a
    record of what a user asked the product to do; `attempts`, the object key,
    and the failure reason are all things support needs after the TTL expires.

    Terminal states are `succeeded` and `failed`. `queued` and `running` are not
    terminal and a row can sit in either if a worker dies mid-parse, which is
    what `reap_stalled` in the maintenance sweep is for.
    """

    __tablename__ = "resume_parse_jobs"

    #: The four states a job can be in. Declared rather than left as free text so
    #: the status endpoint's schema and the worker agree on one vocabulary.
    STATUSES = ("queued", "running", "succeeded", "failed")

    id = db.Column(db.BigInteger, db.Identity(always=True), primary_key=True)
    #: The handle on the wire. The integer `id` is never published: it enumerates,
    #: and P1-8 already names that as a defect in the tables that do it.
    public_id = db.Column(
        UUID(as_uuid=True), nullable=False, server_default=db.text("uuidv7()")
    )
    user_id = db.Column(
        db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    object_key = db.Column(db.Text, nullable=False)
    mime = db.Column(db.Text, nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False, default=0)
    resume_name = db.Column(db.Text)
    status = db.Column(db.Text, nullable=False, default="queued")
    #: Present only on `failed`, and it is the message the client is shown. It is
    #: written from a caught exception, so it must never carry a storage path or a
    #: provider response -- `resume_tasks` maps to a fixed set of reasons.
    error = db.Column(db.Text)
    attempts = db.Column(db.SmallInteger, nullable=False, server_default=db.text("0"))
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.Index("uq_resume_parse_jobs_public_id", "public_id", unique=True),
        db.Index("ix_resume_parse_jobs_user", "user_id", db.text("created_at DESC")),
        db.Index(
            "ix_resume_parse_jobs_pending",
            "created_at",
            postgresql_where=db.text("status IN ('queued', 'running')"),
        ),
        # `purge_terminal`'s index, the same shape as `ix_scoring_jobs_terminal`
        # and for the same reason: pending and terminal rows are disjoint halves.
        db.Index(
            "ix_resume_parse_jobs_terminal",
            "created_at",
            postgresql_where=db.text("status IN ('succeeded', 'failed')"),
        ),
        db.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_resume_parse_jobs_status",
        ),
    )


class ScoringJob(db.Model):
    """Assessment scoring and path suggestions, taken off the request path (3b).

    The same `202 + job handle` shape `ResumeParseJob` carries for resume
    parsing, and deliberately the same state machine rather than a second one:
    `queued -> running -> succeeded | failed`, claimed by a conditional UPDATE,
    swept by `reap_stalled` when a worker dies holding one.

    **One table for two job types, and the reason is the mechanism rather than
    the payload.** `job_type` discriminates `assessment_scoring` from
    `path_suggestions`. Both are "a user's input, a provider call, a result",
    and splitting them would buy two copies of the claim, the reaper, the
    sweep and the purge -- four things that must not drift -- to separate two
    column sets that differ by one nullable `kind`.

    **A shared table is not a shared response.** A12 rejects a uniform result
    envelope for the five instruments, and nothing here reintroduces one:
    `result` is JSONB at rest, and `{kind}` in the path selects the response
    model the job endpoint publishes and validates against, exactly as it does
    on the synchronous submit. What is shared is where the row lives, not what
    the wire promises.

    **`user_id` is nullable for exactly one instrument.** `wpll` is the
    anonymous pre-launch teaser and has no account to attach to, so its job has
    no owner and the `public_id` is the only thing that can authorise a poll --
    a capability handle, and the check constraint below is what stops any other
    job type acquiring one by accident.

    **`payload` is nulled when the job reaches a terminal state.** It holds the
    submitted answers, which for the three instruments that persist are already
    in `assessment_submissions.answers`; keeping a second copy alive past the
    scoring is duplicate retention of assessment data for no reader. `result` is
    kept, because the poll is what serves it.
    """

    __tablename__ = "scoring_jobs"

    #: Same four states as `resume_parse_jobs`, and the same two are terminal.
    STATUSES = ("queued", "running", "succeeded", "failed")

    #: The two kinds of work on this table. `assessment_scoring` carries a
    #: `kind`; `path_suggestions` does not and must not.
    JOB_TYPES = ("assessment_scoring", "path_suggestions")

    id = db.Column(db.BigInteger, db.Identity(always=True), primary_key=True)
    #: The handle on the wire, and for `wpll` the only thing authorising a poll.
    public_id = db.Column(
        UUID(as_uuid=True), nullable=False, server_default=db.text("uuidv7()")
    )
    #: Null only for an anonymous `wpll` scoring -- see the check constraint.
    user_id = db.Column(
        db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    job_type = db.Column(db.Text, nullable=False)
    #: The assessment instrument, for `assessment_scoring` only.
    kind = db.Column(db.Text)
    #: The submitted body. Nulled on a terminal state; see the class docstring.
    payload = db.Column(
        JSONB, nullable=False, server_default=db.text("'{}'::jsonb")
    )
    #: What the poll serves. Shape is per-discriminator, not per-table.
    result = db.Column(JSONB)
    status = db.Column(db.Text, nullable=False, default="queued")
    #: Present only on `failed`, and shown to the client, so it is written from
    #: a fixed vocabulary rather than from a provider exception -- those carry
    #: model names, request ids and prompt fragments.
    error = db.Column(db.Text)
    attempts = db.Column(db.SmallInteger, nullable=False, server_default=db.text("0"))
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )

    __table_args__ = (
        db.Index("uq_scoring_jobs_public_id", "public_id", unique=True),
        db.Index("ix_scoring_jobs_user", "user_id", db.text("created_at DESC")),
        db.Index(
            "ix_scoring_jobs_pending",
            "created_at",
            postgresql_where=db.text("status IN ('queued', 'running')"),
        ),
        # The purge sweep's index. Separate from the pending one because the two
        # select disjoint halves of the table and a single index over
        # `created_at` would make each scan the other's rows.
        db.Index(
            "ix_scoring_jobs_terminal",
            "created_at",
            postgresql_where=db.text("status IN ('succeeded', 'failed')"),
        ),
        db.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_scoring_jobs_status",
        ),
        db.CheckConstraint(
            "job_type IN ('assessment_scoring', 'path_suggestions')",
            name="ck_scoring_jobs_type",
        ),
        # `kind` belongs to assessment scoring and to nothing else. Without this
        # a path-suggestion row could carry `kind='work_pulse'` and be served by
        # the assessment poll under that instrument's response model.
        db.CheckConstraint(
            "(job_type = 'assessment_scoring' AND kind IS NOT NULL) OR "
            "(job_type = 'path_suggestions' AND kind IS NULL)",
            name="ck_scoring_jobs_kind_matches_type",
        ),
        # Anonymity is granted to one instrument by name, in the schema, rather
        # than left to whichever handler happens to set `user_id`. `wpll` is the
        # pre-launch teaser; every other job belongs to an account, and an
        # ownerless row of any other type would be a poll nobody can be denied.
        db.CheckConstraint(
            "user_id IS NOT NULL OR "
            "(job_type = 'assessment_scoring' AND kind = 'wpll')",
            name="ck_scoring_jobs_owner_required",
        ),
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
    ResumeParseJob.__table__,
    ScoringJob.__table__,
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
