"""The ``/api/v1/me`` resources Phase 1b split out of ``GET|POST /profile``.

Three things are being checked, and only the first is about the new paths.

1. The split preserves behaviour. Identity and profile come back through two
   resources with the same values the god-endpoint returned in one document.
2. The split *removes* something specific: ``GET /me`` writes no audit row.
   That is the P0-3 fix, and asserting the absence is the only way it stays
   fixed -- a future refactor that reintroduces the write would otherwise pass
   every other test in the suite.
3. Addressing resumes by id closes the hole the object-key API had to defend
   against by hand. One user cannot name another's key, because there is no key
   to name.
"""

import pytest

from solverah.schemas.account import AccountExportResponse
from solverah.schemas.profile import (
    CareerStatusResponse,
    DashboardResponse,
    IdentityResponse,
    ProfileDocument,
    SkillsResponse,
)

EMAIL = "me-api@example.com"
PASSWORD = "Strongpass1!"


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns its CSRF token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Me User",
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


def _audit_count(action, resource):
    from app import app
    from model import AuditLog

    with app.app_context():
        return AuditLog.query.filter_by(action=action, resource=resource).count()


# ── Identity ────────────────────────────────────────────────────────────────


def test_get_me_returns_identity_and_validates(client, auth):
    resp = client.get("/api/v1/me")

    assert resp.status_code == 200
    body = resp.get_json()
    IdentityResponse.model_validate(body)
    assert body["email"] == EMAIL
    assert body["email_confirmed"] is True


def test_get_me_does_not_ship_the_profile_blob(client, auth):
    """The whole point of the split. Shipping it here would undo it."""
    body = client.get("/api/v1/me").get_json()

    assert "profileData" not in body
    assert "profile" not in body


def test_get_me_writes_no_audit_row(client, auth):
    """P0-3: the read on the boot path used to commit a write. This asserts it stopped.

    `GET /profile` logged a `read` on `profile` every time the SPA restored a
    session -- the highest-volume table in the system, written synchronously on
    the hottest endpoint, for data the shell does not render.
    """
    before = _audit_count("read", "profile")

    client.get("/api/v1/me")
    client.get("/api/v1/me")

    assert _audit_count("read", "profile") == before


def test_patch_me_updates_the_name(client, auth):
    resp = client.patch(
        "/api/v1/me", json={"name": "Renamed User"}, headers={"X-CSRF-TOKEN": auth}
    )

    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Renamed User"
    assert client.get("/api/v1/me").get_json()["name"] == "Renamed User"


def test_patch_me_will_not_change_the_role(client, auth):
    """Role is a privilege boundary; an account must not grant itself one."""
    client.patch(
        "/api/v1/me",
        json={"name": "Still A Seeker", "role": "employer"},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert client.get("/api/v1/me").get_json()["role"] == "job-seeker"


def test_patch_me_will_not_change_the_email(client, auth):
    """Changing an address without re-verifying it is an account-takeover primitive."""
    client.patch(
        "/api/v1/me",
        json={"name": "Same Person", "email": "attacker@example.com"},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert client.get("/api/v1/me").get_json()["email"] == EMAIL


def test_me_requires_authentication(client):
    assert client.get("/api/v1/me").status_code == 401


# ── Profile ─────────────────────────────────────────────────────────────────


def test_get_my_profile_returns_the_envelope(client, auth):
    resp = client.get("/api/v1/me/profile")

    assert resp.status_code == 200
    ProfileDocument.model_validate(resp.get_json())


def test_patch_my_profile_merges_rather_than_replaces(client, auth):
    client.patch(
        "/api/v1/me/profile",
        json={"profile": {"phone": "555-0100"}},
        headers={"X-CSRF-TOKEN": auth},
    )
    resp = client.patch(
        "/api/v1/me/profile",
        json={"profile": {"location": "Austin, TX"}},
        headers={"X-CSRF-TOKEN": auth},
    )

    profile = resp.get_json()["profile"]
    assert profile["phone"] == "555-0100"
    assert profile["location"] == "Austin, TX"


def test_reading_the_profile_still_records_an_audit_event(client, auth):
    """Unlike GET /me. A personal-data document read is worth recording."""
    before = _audit_count("read", "profile")

    client.get("/api/v1/me/profile")

    assert _audit_count("read", "profile") == before + 1


def test_patch_my_profile_rejects_a_missing_profile_key(client, auth):
    """`enforce=True`: the declared body is checked before the handler runs."""
    resp = client.patch("/api/v1/me/profile", json={}, headers={"X-CSRF-TOKEN": auth})

    assert resp.status_code == 422
    assert resp.mimetype == "application/problem+json"
    assert resp.get_json()["errors"][0]["field"] == "profile"


# ── Career status and skills ────────────────────────────────────────────────


def test_patch_career_status(client, auth):
    resp = client.patch(
        "/api/v1/me/career-status",
        json={"status": "employed"},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 200
    CareerStatusResponse.model_validate(resp.get_json())


@pytest.mark.parametrize("bad", ["retired", "", None, 3, "Employed"])
def test_patch_my_profile_rejects_an_unknown_career_status(client, auth, bad):
    """Audit 2026-10-02 item 13: PATCH /me/career-status validated the status and
    the profile PATCH, which writes the same column, did not. A 400, and nothing
    else in the same request is written either."""
    resp = client.patch(
        "/api/v1/me/profile",
        json={"profile": {"career_status": bad, "phone": "555-0199"}},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_status"
    profile = client.get("/api/v1/me/profile").get_json()["profile"]
    assert profile.get("phone") != "555-0199"
    assert "career_status" not in profile


def test_patch_my_profile_accepts_each_known_career_status(client, auth):
    for status in ("employed", "between_jobs", "first_job"):
        resp = client.patch(
            "/api/v1/me/profile",
            json={"profile": {"career_status": status}},
            headers={"X-CSRF-TOKEN": auth},
        )
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["profile"]["career_status"] == status


def test_an_in_between_proficiency_reads_back_instead_of_500ing(client, auth):
    """Audit 2026-10-02 item 12: profile_skills.proficiency allows 1-5, the read
    mapped only 1/3/5, and a 2 or a 4 raised KeyError inside GET /me/profile.
    An in-between score reads as the named level below it."""
    client.put(
        "/api/v1/me/skills",
        json={"skills": [{"name": "Python", "proficiency": "advanced"},
                         {"name": "SQL", "proficiency": "intermediate"}]},
        headers={"X-CSRF-TOKEN": auth},
    )
    from app import app
    from model import ProfileSkill, User, db

    with app.app_context():
        user_id = User.query.filter_by(email=EMAIL).first().id
        rows = ProfileSkill.query.filter_by(user_id=user_id).all()
        assert {row.label for row in rows} == {"Python", "SQL"}
        for row in rows:
            row.proficiency = 4 if row.label == "Python" else 2
        db.session.commit()

    resp = client.get("/api/v1/me/profile")

    assert resp.status_code == 200
    ProfileDocument.model_validate(resp.get_json())
    assert resp.get_json()["profile"]["skill_levels"] == {
        "Python": "intermediate",
        "SQL": "beginner",
    }


def test_put_then_get_skills_round_trips(client, auth):
    """GET /me/skills is new: the endpoint it replaces was write-only."""
    put = client.put(
        "/api/v1/me/skills",
        json={"skills": [{"name": "Python", "proficiency": "advanced"}]},
        headers={"X-CSRF-TOKEN": auth},
    )
    assert put.status_code == 200

    resp = client.get("/api/v1/me/skills")

    assert resp.status_code == 200
    body = resp.get_json()
    SkillsResponse.model_validate(body)
    assert body["skill_levels"]["Python"] == "advanced"
    assert body["skills_proficiency_confirmed"] is True


def test_skills_before_any_rating_is_an_empty_map_not_a_404(client, auth):
    body = client.get("/api/v1/me/skills").get_json()

    assert body["skill_levels"] == {}
    assert body["skills_proficiency_confirmed"] is False


def test_put_skills_rejects_an_unknown_proficiency(client, auth):
    resp = client.put(
        "/api/v1/me/skills",
        json={"skills": [{"name": "Python", "proficiency": "wizard"}]},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 400


# ── Dashboard and export ────────────────────────────────────────────────────


def test_dashboard_matches_its_schema(client, auth):
    resp = client.get("/api/v1/me/dashboard")

    assert resp.status_code == 200
    DashboardResponse.model_validate(resp.get_json())


def test_export_matches_its_schema(client, auth):
    resp = client.get("/api/v1/me/export")

    assert resp.status_code == 200
    body = resp.get_json()
    AccountExportResponse.model_validate(body)
    assert body["account"]["email"] == EMAIL


def test_delete_me_requires_the_confirmation_string(client, auth):
    resp = client.delete(
        "/api/v1/me", json={"confirm": "yes"}, headers={"X-CSRF-TOKEN": auth}
    )

    assert resp.status_code == 400


def test_delete_me_erases_the_account(client, auth):
    resp = client.delete(
        "/api/v1/me", json={"confirm": "DELETE"}, headers={"X-CSRF-TOKEN": auth}
    )

    assert resp.status_code == 200
    assert client.get("/api/v1/me").status_code == 401


def test_delete_me_still_enforces_csrf(client, auth):
    """The new path must not be a way around the protection the old one had."""
    resp = client.delete("/api/v1/me", json={"confirm": "DELETE"})

    assert resp.status_code == 401


# ── Resumes: addressed by id, not by object key ─────────────────────────────


PDF = "application/pdf"


@pytest.fixture()
def storage(monkeypatch):
    """Stub the presign step so no network or credentials are needed."""
    monkeypatch.setattr(
        "solverah.services.resume_service.presign_upload",
        lambda key, mime, size: "https://example.invalid/put/%s" % key,
    )


def test_resume_ticket_returns_an_id_and_never_the_object_key(client, auth, storage):
    """The key is the thing the superseded API had to defend; now it is not exposed."""
    resp = client.post(
        "/api/v1/me/resumes",
        json={"mime": PDF, "size": 1024},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["resume_id"]
    assert "object_key" not in body


def test_resume_ticket_rejects_an_unsupported_type(client, auth, storage):
    resp = client.post(
        "/api/v1/me/resumes",
        json={"mime": "image/png", "size": 1024},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 400


def test_resume_ticket_rejects_an_oversized_file(client, auth, storage):
    resp = client.post(
        "/api/v1/me/resumes",
        json={"mime": PDF, "size": 999_999_999},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 400


def test_resume_ticket_enforces_its_schema(client, auth, storage):
    resp = client.post(
        "/api/v1/me/resumes", json={"mime": PDF}, headers={"X-CSRF-TOKEN": auth}
    )

    assert resp.status_code == 422
    assert [e["field"] for e in resp.get_json()["errors"]] == ["size"]


def test_a_resume_id_can_only_ever_address_the_callers_own_prefix(client, auth):
    """The authorisation property the id scheme buys.

    The endpoint this replaces took a caller-supplied object_key and checked it
    began with `profile/{your-id}/`. Get that check wrong and a caller parses
    someone else's resume into their own profile. Here the key is rebuilt from
    the JWT identity, so an id belonging to another user resolves under *this*
    user's prefix -- which does not exist -- rather than reaching theirs.
    """
    from app import app
    from model import User
    from solverah.services import profile_service

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        key = profile_service.resolve_resume_key(user, "some-other-users-id", mime=PDF)

        assert key.startswith("profile/%s/" % user.id)


def test_a_resume_id_containing_a_path_separator_is_refused(client, auth):
    """Otherwise `../` or an absolute key would escape the user's prefix."""
    from app import app
    from model import User
    from solverah.services import profile_service

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()

        assert profile_service.resolve_resume_key(user, "../../etc", mime=PDF) is None


def test_download_url_is_404_when_there_is_no_resume(client, auth):
    resp = client.get("/api/v1/me/resumes/current/download-url")

    assert resp.status_code == 404


def test_complete_is_a_routing_404_because_the_route_is_gone(client, auth):
    """``POST /me/resumes/{id}/complete`` was deleted in Phase 3c.

    This test used to read the 404 as "an id that names nothing"; there is no
    longer a handler for any id to reach. Resume parsing goes through
    ``POST /me/resumes/{id}/parse-jobs`` (pinned in ``test_resume_parse_jobs.py``),
    and this asserts the deletion stays deleted: any request at this path gets
    the router's problem+json not-found.
    """
    resp = client.post(
        "/api/v1/me/resumes/current/complete",
        json={"mime": PDF, "size": 1024},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 404
    assert resp.mimetype == "application/problem+json"
    assert resp.get_json()["type"].endswith("/not_found")
