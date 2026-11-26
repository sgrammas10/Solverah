"""``PATCH /me/onboarding`` -- the first-run "What brings you here?" answers.

The dashboard's first-run dialog writes a career moment, sometimes a career
status, and optionally a sentence in the user's own words. What is pinned here:

* each moment that implies a status writes that status, overwriting the stored
  one; the two that do not leave it alone or take an explicit one;
* every refusal is a 400 and writes nothing;
* own words are trimmed, capped at 1000 characters, and blank stores NULL;
* both answers ride the profile document, so ``GET /me/profile`` and
  ``GET /me/export`` carry them, and account deletion erases them;
* the dashboard document always carries ``careerMoment`` (null until answered),
  which is what the dialog opens on;
* the migration adds and removes the columns and the CHECK cleanly.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from solverah.domain import profile as domain
from solverah.schemas.profile import DashboardResponse, OnboardingResponse

EMAIL = "onboarding@example.com"
PASSWORD = "Strongpass1!"
URL = "/api/v1/me/onboarding"
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations" / "versions" / "20261124_profile_onboarding.py"
)


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns its CSRF token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Onboarding User",
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


def _patch(client, csrf, body):
    return client.patch(URL, json=body, headers={"X-CSRF-TOKEN": csrf})


def _stored_row():
    from app import app
    from model import Profile, User, db

    with app.app_context():
        user_id = User.query.filter_by(email=EMAIL).one().id
        row = db.session.get(Profile, user_id)
        return None if row is None else {
            "career_moment": row.career_moment,
            "own_words": row.own_words,
            "career_status": row.career_status,
        }


def _profile(client):
    return client.get("/api/v1/me/profile").get_json()["profile"]


# ── Happy paths ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "moment,status",
    [
        ("off_at_work", "employed"),
        ("stay_or_go", "employed"),
        ("between_jobs", "between_jobs"),
        ("first_job", "first_job"),
    ],
)
def test_a_status_implying_moment_writes_the_status(client, auth, moment, status):
    resp = _patch(client, auth, {"career_moment": moment})

    assert resp.status_code == 200, resp.get_json()
    body = OnboardingResponse.model_validate(resp.get_json())
    assert body.career_moment == moment
    assert body.career_status == status
    assert body.own_words is None
    assert _stored_row()["career_moment"] == moment
    assert _stored_row()["career_status"] == status


def test_an_implied_status_overwrites_the_stored_one(client, auth):
    """The moment is the user's latest statement about themselves."""
    client.patch(
        "/api/v1/me/career-status", json={"status": "first_job"}, headers={"X-CSRF-TOKEN": auth}
    )

    resp = _patch(client, auth, {"career_moment": "off_at_work"})

    assert resp.status_code == 200
    assert _profile(client)["career_status"] == "employed"


@pytest.mark.parametrize("moment", ["job_hunting", "curious"])
@pytest.mark.parametrize("status", ["employed", "between_jobs", "first_job"])
def test_a_follow_up_moment_takes_an_explicit_status(client, auth, moment, status):
    resp = _patch(client, auth, {"career_moment": moment, "career_status": status})

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json() == {"career_moment": moment, "career_status": status, "own_words": None}


def test_a_follow_up_moment_alone_keeps_the_stored_status(client, auth):
    client.patch(
        "/api/v1/me/career-status", json={"status": "between_jobs"}, headers={"X-CSRF-TOKEN": auth}
    )

    resp = _patch(client, auth, {"career_moment": "curious"})

    assert resp.status_code == 200
    assert resp.get_json()["career_status"] == "between_jobs"


def test_own_words_are_trimmed_and_kept_verbatim(client, auth):
    words = "  My manager rewrites my work at 11pm.\nI don't know if that's normal.  "

    resp = _patch(client, auth, {"own_words": words})

    assert resp.status_code == 200
    assert resp.get_json()["own_words"] == words.strip()
    assert _stored_row()["own_words"] == words.strip()


def test_exactly_the_cap_is_accepted_and_trimming_happens_first(client, auth):
    words = " " * 5 + "x" * domain.OWN_WORDS_MAX_CHARS + " " * 5

    resp = _patch(client, auth, {"own_words": words})

    assert resp.status_code == 200
    assert len(_stored_row()["own_words"]) == domain.OWN_WORDS_MAX_CHARS


@pytest.mark.parametrize("blank", ["", "   \n\t ", None])
def test_blank_own_words_store_null(client, auth, blank):
    _patch(client, auth, {"own_words": "Something first."})

    resp = _patch(client, auth, {"own_words": blank})

    assert resp.status_code == 200
    assert resp.get_json()["own_words"] is None
    assert _stored_row()["own_words"] is None
    assert "own_words" not in _profile(client)


def test_an_absent_key_leaves_the_stored_value_alone(client, auth):
    _patch(client, auth, {"career_moment": "stay_or_go", "own_words": "Thinking it over."})

    resp = _patch(client, auth, {"own_words": "Changed my mind."})

    assert resp.status_code == 200
    assert resp.get_json()["career_moment"] == "stay_or_go"
    assert _stored_row()["career_moment"] == "stay_or_go"


def test_a_status_write_drops_the_path_caches_like_career_status_does(client, auth, monkeypatch):
    """Same side effects as PATCH /me/career-status (F-8 box 6)."""
    calls = []
    monkeypatch.setattr(
        "solverah.services.path_cache.invalidate", lambda user_id: calls.append(("tier1", user_id))
    )
    monkeypatch.setattr(
        "solverah.repositories.path_fit_repository.invalidate",
        lambda user_id: calls.append(("tier2", user_id)),
    )

    _patch(client, auth, {"own_words": "Just words."})
    assert calls == []

    _patch(client, auth, {"career_moment": "between_jobs"})
    assert [kind for kind, _ in calls] == ["tier2", "tier1"]


# ── Refusals ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["retired", "", None, "Curious", "off at work"])
def test_an_unknown_moment_is_a_400(client, auth, bad):
    resp = _patch(client, auth, {"career_moment": bad, "own_words": "Should not land."})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "invalid_career_moment"}
    assert (_stored_row() or {}).get("own_words") is None


@pytest.mark.parametrize("bad", ["retired", "", None, "Employed"])
def test_an_unknown_status_is_a_400(client, auth, bad):
    resp = _patch(client, auth, {"career_moment": "job_hunting", "career_status": bad})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "invalid_status"}
    assert (_stored_row() or {}).get("career_moment") is None


def test_a_status_that_contradicts_the_moment_is_a_400(client, auth):
    resp = _patch(client, auth, {"career_moment": "first_job", "career_status": "employed"})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "status_conflicts_with_moment"}


def test_a_status_that_agrees_with_the_moment_is_fine(client, auth):
    resp = _patch(client, auth, {"career_moment": "first_job", "career_status": "first_job"})

    assert resp.status_code == 200


def test_over_length_own_words_are_a_400(client, auth):
    resp = _patch(client, auth, {"own_words": "x" * (domain.OWN_WORDS_MAX_CHARS + 1)})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "own_words_too_long"}
    assert (_stored_row() or {}).get("own_words") is None


def test_an_empty_body_is_a_400(client, auth):
    resp = _patch(client, auth, {})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "no_fields"}


def test_unauthenticated_is_a_401(client):
    resp = client.patch(URL, json={"career_moment": "curious"})

    assert resp.status_code == 401


def test_csrf_is_still_enforced(client, auth):
    resp = client.patch(URL, json={"career_moment": "curious"})

    assert resp.status_code == 401


def test_the_profile_patch_cannot_set_either_answer(client, auth):
    """Only the validated endpoint writes these; the profile PATCH strips them."""
    client.patch(
        "/api/v1/me/profile",
        json={"profile": {"career_moment": "retired", "own_words": "sneaky", "phone": "555"}},
        headers={"X-CSRF-TOKEN": auth},
    )

    profile = _profile(client)
    assert "career_moment" not in profile
    assert "own_words" not in profile


def test_a_profile_save_keeps_the_answers(client, auth):
    _patch(client, auth, {"career_moment": "curious", "own_words": "Keep me."})

    client.patch(
        "/api/v1/me/profile",
        json={"profile": {"summary": "Engineer."}},
        headers={"X-CSRF-TOKEN": auth},
    )

    profile = _profile(client)
    assert profile["career_moment"] == "curious"
    assert profile["own_words"] == "Keep me."


# ── Where the answers show up ───────────────────────────────────────────────


def test_both_answers_are_in_the_profile_document_and_the_export(client, auth):
    _patch(client, auth, {"career_moment": "stay_or_go", "own_words": "Thinking about leaving."})

    profile = _profile(client)
    assert profile["career_moment"] == "stay_or_go"
    assert profile["own_words"] == "Thinking about leaving."

    export = client.get("/api/v1/me/export").get_json()
    assert export["profile"]["career_moment"] == "stay_or_go"
    assert export["profile"]["own_words"] == "Thinking about leaving."


def test_the_dashboard_sends_an_explicit_null_until_answered(client, auth):
    resp = client.get("/api/v1/me/dashboard")
    body = resp.get_json()

    assert "careerMoment" in body and body["careerMoment"] is None
    assert "careerStatus" in body and body["careerStatus"] is None
    DashboardResponse.model_validate(body)

    _patch(client, auth, {"career_moment": "job_hunting", "career_status": "employed"})

    body = client.get("/api/v1/me/dashboard").get_json()
    assert body["careerMoment"] == "job_hunting"
    assert body["careerStatus"] == "employed"


def test_account_deletion_erases_both_answers(client, auth):
    _patch(client, auth, {"career_moment": "off_at_work", "own_words": "Private thought."})

    resp = client.delete("/api/v1/me", json={"confirm": "DELETE"}, headers={"X-CSRF-TOKEN": auth})

    assert resp.status_code == 200
    from app import app
    from model import Profile, db

    with app.app_context():
        rows = db.session.execute(
            sa.select(Profile.own_words, Profile.career_moment)
        ).all()
        assert rows, "the tombstone keeps the profiles row"
        assert all(own_words is None and moment is None for own_words, moment in rows)
        leftover = db.session.execute(
            sa.text("SELECT count(*) FROM profiles WHERE extra::text LIKE '%Private thought%'")
        ).scalar()
        assert leftover == 0


# ── The column CHECK and the migration ──────────────────────────────────────


def test_the_check_refuses_a_moment_outside_the_vocabulary(client, seed_user):
    from app import app
    from model import Profile, db

    seed_user(1)
    with app.app_context():
        db.session.add(Profile(user_id=1, career_moment="retired"))
        with pytest.raises(sa.exc.IntegrityError):
            db.session.flush()
        db.session.rollback()


def test_the_check_and_the_domain_agree_on_the_vocabulary(client):
    from app import app
    from model import db

    with app.app_context():
        check = db.session.execute(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_profiles_career_moment'"
            )
        ).scalar()
    for moment in domain.CAREER_MOMENTS:
        assert "'%s'" % moment in check


def _load_migration(connection):
    spec = importlib.util.spec_from_file_location("_h_profile_onboarding", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(connection))
    return module


def _columns(db):
    return {
        name
        for (name,) in db.session.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'profiles'"
            )
        )
    }


def _has_check(db):
    return bool(
        db.session.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = 'ck_profiles_career_moment'")
        ).scalar()
    )


def test_the_migration_downgrades_and_upgrades_cleanly(client):
    """Transactional DDL: the round trip is rolled back so the fixture schema survives."""
    from app import app
    from model import db

    with app.app_context():
        module = _load_migration(db.session.connection())
        assert module.down_revision == "20261123_user_company_lookup"

        module.downgrade()
        assert not {"career_moment", "own_words"} & _columns(db)
        assert not _has_check(db)

        module.upgrade()
        assert {"career_moment", "own_words"} <= _columns(db)
        assert _has_check(db)
        db.session.rollback()


# ── The domain rule on its own ──────────────────────────────────────────────


def test_every_moment_maps_to_a_known_status_or_none():
    assert set(domain.CAREER_MOMENTS) == {
        "off_at_work", "stay_or_go", "job_hunting", "between_jobs", "first_job", "curious",
    }
    for implied in domain.CAREER_MOMENTS.values():
        assert implied is None or implied in domain.CAREER_STATUSES


@pytest.mark.parametrize("body", [None, [], "curious", {}])
def test_a_body_with_nothing_to_write_is_refused(body):
    problem, update = domain.validate_onboarding(body)

    assert problem == "no_fields"
    assert update.fields == {}


def test_non_string_own_words_are_refused():
    assert domain.validate_onboarding({"own_words": 3})[0] == "invalid_own_words"
