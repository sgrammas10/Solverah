"""Phase 2c: the `users` table, and the four things it must not have changed.

The phase moved storage without moving the wire, so most of the evidence for it
is negative -- what does *not* appear in a response, what a rename did *not*
break. Those are the assertions that would otherwise be made by nobody.

`Scripts/verify_contract.py` is the other half: it diffs the actual bytes of
`GET /me`, `GET /auth/session` and `GET /me/profile` against a baseline recorded
before the change. This file covers what a byte diff cannot see -- the shape of
the schema underneath, and the failure modes that need two sessions or a
hand-assigned id to provoke.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

REPO_ROOT = Path(__file__).resolve().parents[1]

EMAIL = "users-table@example.com"
PASSWORD = "Strongpass1!"


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns its CSRF token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Users Table",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


# ── The rename ──────────────────────────────────────────────────────────────


def test_the_table_is_named_users():
    from model import User

    assert User.__tablename__ == "users"


def test_no_live_code_still_quotes_the_reserved_word():
    """P1-8's first bullet, asserted rather than remembered.

    `migrations/versions/` is excluded on purpose. Those files describe the schema
    as it was at their revision, and the 2c migration has to say
    `ALTER TABLE "user" RENAME TO users` to do its job. Rewriting history to make
    a grep pass would make every one of them a lie about the database it ran on.
    """
    # `"user"` appears constantly as an LLM message role, so matching the bare
    # string finds nothing useful. These are the shapes that mean *the table*.
    offenders = []
    pattern = re.compile(
        r'(?:FROM|JOIN|INTO|UPDATE|TABLE|EXISTS)\s+"user"|ForeignKey\(\s*"user\.'
    )
    for path in REPO_ROOT.rglob("*.py"):
        parts = path.parts
        if "migrations" in parts or "node_modules" in parts or "_to_delete" in parts:
            continue
        # This file quotes the reserved word when explaining why it is looking
        # for it. A scanner cannot be its own subject.
        if path == Path(__file__):
            continue
        text_ = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text_.splitlines(), 1):
            if pattern.search(line):
                offenders.append("%s:%d: %s" % (path.relative_to(REPO_ROOT), number, line.strip()))

    assert offenders == [], "quoted `user` table references remain:\n" + "\n".join(offenders)


def test_every_foreign_key_followed_the_rename(client):
    """Postgres carries FKs through a rename. Phase 2a added four; verify all of them."""
    from app import app
    from model import db

    with app.app_context():
        rows = db.session.execute(
            text(
                """
                SELECT DISTINCT cl.relname
                FROM pg_constraint c
                JOIN pg_class cl ON cl.oid = c.conrelid
                JOIN pg_class ref ON ref.oid = c.confrelid
                WHERE c.contype = 'f' AND ref.relname = 'users'
                """
            )
        ).scalars().all()

    children = set(rows)
    # The four Phase 2a added, which are the ones the rename could most easily
    # have orphaned because they were created pointing at `user.id`.
    assert {"profiles", "profile_experiences", "profile_educations", "profile_skills",
            "resumes"} <= children
    # And the ones that predate it.
    assert {"user_intake", "audit_log", "job_recommendation"} <= children


def test_the_rename_left_nothing_carrying_the_old_name(client):
    """A rename moves the table and nothing else.

    The sequence, the primary key, and the confirmation-token index all kept
    `user_` until they were renamed or replaced explicitly. A survivor is an
    object named after a table that no longer exists.

    That last sentence is the assertion, and it did not used to be. The check
    was a prefix allowlist -- anything not starting `users` or `user_intake` was
    a straggler -- which read as the same rule and is not: it flags any NEW
    table whose name happens to begin with `user_`, and S3's `user_sessions`
    (Part 4.2's spelling, never renamed from anything) is the first one to
    arrive and be wrongly accused. Deriving the allowlist from the tables that
    actually exist says what is meant, needs no maintenance, and is strictly
    stricter: `user_pkey` fails it because there is no `user` table, which is
    exactly the leftover being hunted.
    """
    from app import app
    from model import db

    with app.app_context():
        names = db.session.execute(
            text(
                """
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('i', 'S')
                  AND c.relname LIKE 'user%'
                """
            )
        ).scalars().all()
        tables = db.session.execute(
            text(
                """
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                  AND c.relname LIKE 'user%'
                """
            )
        ).scalars().all()

    assert "users" in tables, "the users table is missing; this guard proves nothing"
    stragglers = [
        n for n in names if not any(n == t or n.startswith(t + "_") for t in tables)
    ]
    assert stragglers == [], "objects named after a table that no longer exists: %s" % stragglers


# ── id: BIGINT, identity, still an integer on the wire ──────────────────────


def test_id_is_a_bigint_identity_column(client):
    from app import app
    from model import db

    with app.app_context():
        row = db.session.execute(
            text(
                """
                SELECT data_type, is_identity, identity_generation
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'id'
                """
            )
        ).one()

    assert row.data_type == "bigint"
    assert row.is_identity == "YES"
    # `ALWAYS` would reject seed_user's explicit ids without OVERRIDING SYSTEM VALUE.
    assert row.identity_generation == "BY DEFAULT"


def test_an_explicit_id_is_still_accepted_and_does_not_collide(client, seed_user):
    """`seed_user` inserts hand-assigned ids; the next generated id must clear them."""
    from app import app
    from model import User, db

    seed_user(41, 42)

    with app.app_context():
        fresh = User(email="generated@example.test", password_hash="not-a-real-hash")
        db.session.add(fresh)
        db.session.commit()
        assert fresh.id > 42


def test_the_id_on_the_wire_is_still_the_integer(client, auth):
    from app import app
    from model import User

    with app.app_context():
        expected = User.query.filter_by(email=EMAIL).first().id

    assert client.get("/api/v1/me").get_json()["id"] == expected
    assert client.get("/api/v1/auth/session").get_json()["user"]["id"] == expected


# ── public_id: on every row, in no response ─────────────────────────────────


def test_public_id_is_populated_on_every_row(client, auth, seed_user):
    from app import app
    from model import User

    seed_user(7)

    with app.app_context():
        users = User.query.all()
        assert len(users) >= 2
        ids = [u.public_id for u in users]

    assert all(pid is not None for pid in ids)
    assert len(set(ids)) == len(ids)


def test_public_id_appears_in_no_response(client, auth):
    """Part 4.1 intends public_id for URLs and payloads. That is a later phase.

    Shipping it early is not harmless: a client that starts reading it has been
    handed a contract nobody agreed to, and the phase that flips the wire then
    has two shapes to support instead of one.
    """
    from app import app
    from model import User

    with app.app_context():
        public_id = str(User.query.filter_by(email=EMAIL).first().public_id)

    for path in (
        "/api/v1/me",
        "/api/v1/auth/session",
        "/api/v1/me/profile",
        "/api/v1/me/dashboard",
        "/api/v1/me/export",
    ):
        body = client.get(path).get_data(as_text=True)
        assert public_id not in body, "public_id leaked into %s" % path
        assert "public_id" not in body, "the key public_id leaked into %s" % path


# ── email_confirmed: an instant underneath, a boolean on the wire ───────────


def test_email_confirmed_is_published_as_a_boolean(client, auth):
    for body in (
        client.get("/api/v1/me").get_json(),
        client.get("/api/v1/auth/session").get_json()["flags"],
    ):
        assert body["email_confirmed"] is True

    assert "email_confirmed_at" not in client.get("/api/v1/me").get_json()


def test_the_boolean_is_derived_from_the_instant(client, auth):
    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        assert user.email_confirmed_at is not None
        user.email_confirmed = False
        db.session.commit()
        assert user.email_confirmed_at is None

    assert client.get("/api/v1/me").get_json()["email_confirmed"] is False


def test_confirming_twice_does_not_move_the_recorded_instant(client, auth):
    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        first = user.email_confirmed_at
        user.email_confirmed = True
        db.session.commit()
        assert user.email_confirmed_at == first


def test_the_expression_form_filters_in_sql(client, auth):
    """`filter(User.email_confirmed)` has to mean the same thing as the property."""
    from app import app
    from model import User

    with app.app_context():
        assert User.query.filter(User.email_confirmed).count() == 1
        assert User.query.filter(~User.email_confirmed).count() == 0


# ── citext, enums, status ───────────────────────────────────────────────────


def test_email_lookup_is_case_insensitive(client, auth):
    from app import app
    from model import User

    with app.app_context():
        assert User.query.filter_by(email=EMAIL.upper()).first() is not None


def test_the_role_enum_uses_the_hyphenated_spelling(client):
    """`src/App.tsx` gates fifteen routes on `allowedRoles={["job-seeker"]}`.

    An underscored enum value would make every one of them reject every user.
    """
    from app import app
    from model import db

    with app.app_context():
        labels = db.session.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'user_role' "
                "ORDER BY e.enumsortorder"
            )
        ).scalars().all()

    assert labels == ["job-seeker", "recruiter", "admin"]


def test_role_is_still_the_hyphenated_string_on_the_wire(client, auth):
    assert client.get("/api/v1/me").get_json()["role"] == "job-seeker"


def test_status_follows_confirmation(client, monkeypatch):
    from app import app
    from model import User, db

    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    client.post(
        "/api/v1/auth/register",
        json={"email": "status@example.com", "password": PASSWORD, "name": "S",
              "role": "job-seeker", "terms_accepted": True},
    )

    with app.app_context():
        user = User.query.filter_by(email="status@example.com").first()
        assert user.status == "pending"
        code = user.confirmation_token

    client.post(
        "/api/v1/auth/email/verify",
        json={"email": "status@example.com", "code": code},
    )

    with app.app_context():
        assert User.query.filter_by(email="status@example.com").first().status == "active"


def test_status_does_not_reach_any_response(client, auth):
    for path in ("/api/v1/me", "/api/v1/auth/session", "/api/v1/me/export"):
        assert "status" not in client.get(path).get_json()


# ── version: optimistic locking, enforced ───────────────────────────────────


def test_a_stale_version_update_raises(client, auth):
    """Part 4.1 rule 4. Without `version_id_col` the column is decoration.

    Two sessions read the same row, both write. The second carries the version it
    read, no row matches, and SQLAlchemy raises rather than reporting a silent
    zero-row update as success.
    """
    from app import app
    from model import User, db

    with app.app_context():
        user_id = User.query.filter_by(email=EMAIL).first().id

        first = Session(db.engine)
        second = Session(db.engine)
        try:
            a = first.get(User, user_id)
            b = second.get(User, user_id)
            assert a.version == b.version

            a.name = "won the race"
            first.commit()

            b.name = "lost the race"
            with pytest.raises(StaleDataError):
                second.commit()
        finally:
            first.close()
            second.close()

    with app.app_context():
        assert db.session.get(User, user_id).name == "won the race"


def test_version_advances_on_every_write(client, auth):
    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        before = user.version
        user.name = "Renamed"
        db.session.commit()
        assert user.version == before + 1


def test_version_does_not_reach_any_response(client, auth):
    body = client.get("/api/v1/me").get_data(as_text=True)
    assert "version" not in body


# ── updated_at is the database's job ────────────────────────────────────────


def test_updated_at_moves_without_the_application_touching_it(client, auth):
    """P1-8's fourth bullet, for this table.

    `server_default=now()` alone never fires on UPDATE, which makes `updated_at`
    a second `created_at`. The write below sets `name` and nothing else.
    """
    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        created, before = user.created_at, user.updated_at

        user.name = "Trigger Me"
        db.session.commit()
        db.session.refresh(user)

        assert user.updated_at > before
        assert user.created_at == created


# ── the indexes Part 4.2 declares ───────────────────────────────────────────


def test_the_email_unique_index_is_partial_on_deleted_at(client):
    from app import app
    from model import db

    with app.app_context():
        definition = db.session.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_users_email'")
        ).scalar_one()

    assert "UNIQUE" in definition
    assert "deleted_at IS NULL" in definition


def test_deletion_still_frees_the_address_by_rewriting_it(client, auth):
    """The tombstone, not the partial predicate, is what frees the email today.

    `deleted_at` stays NULL, so `uq_users_email` behaves exactly like the full
    unique constraint it replaced. This asserts the deletion contract did not
    quietly change underneath the index.
    """
    from app import app
    from model import User, db

    client.delete("/api/v1/me", json={"confirm": "DELETE"}, headers={"X-CSRF-TOKEN": auth})

    with app.app_context():
        assert User.query.filter_by(email=EMAIL).first() is None
        tombstoned = User.query.filter(User.email.like("deleted-%")).first()
        assert tombstoned is not None
        assert tombstoned.deleted_at is None
        assert tombstoned.status == "deleted"


def test_public_id_is_uniquely_indexed(client):
    from app import app
    from model import db

    with app.app_context():
        indexes = {ix["name"] for ix in inspect(db.engine).get_indexes("users")}

    assert "uq_users_public_id" in indexes
    assert "ix_users_status" in indexes
