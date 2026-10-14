"""Tests for /api/account/export and /api/account/delete (account_lifecycle.py).

Verifies the D-16 reconciliation decided 2026-08-20: deletion erases every
personal field but RETAINS assessment response rows de-identified via the
tombstoned user row. Each test is written to fail if its guarantee is removed
(operating-policy red rule 7).
"""

import pytest


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="lifecycle@example.com",
                        password="Strongpass1!"):

    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Lifecycle User",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        user_id = user.id

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"], user_id


def _seed_assessment_rows(user_id):
    """Plant a sitting so retention-after-deletion is actually testable.

    Written through assessment_store, not by constructing rows here. D-01 keeps the
    person-side tables off-limits outside that module (tests/test_employer_visibility.py),
    and a test that hand-builds the rows is also free to build ones the real write path
    cannot produce — which is how this file first missed the NOT NULL submission_id that
    persist_submission has always supplied.
    """
    from app import app
    from assessment_form import ScoredSubmission
    from assessment_store import persist_submission
    from model import db

    with app.app_context():
        persist_submission(db, user_id, ScoredSubmission(
            form_version="v2-2026-08-18",
            scoring_key_version="v2-2026-08-18+mean_pole",
            scores={"autonomy": 0.75},
            choices={"au1v2": "A"},
            confidences={"autonomy": 1.0},
        ))
        db.session.commit()


def _person_side(user_id):
    """What the person-side tables still hold, read through the sanctioned doorway."""
    from app import app
    from assessment_store import export_person_side

    with app.app_context():
        return export_person_side(user_id)


# ── BUILD_PLAN D-7: environment_reports, manager_profiles, situation_report_pins ──
#
# Seeded through their own stores, same reasoning as `_seed_assessment_rows` above:
# a test that hand-builds the rows is free to build ones the real write path cannot
# produce, and `_require_all_dimensions` in particular is a real constraint a
# hand-built row could silently violate.

def _seed_environment_report(user_id):
    from app import app
    from environment_report_store import write_environment_report
    from model import ENV_DIMENSIONS, db

    with app.app_context():
        write_environment_report(
            db, user_id,
            raw_answers={"env-autonomy-1": "mixed-a"},
            dimension_scores={dim: 0.5 for dim in ENV_DIMENSIONS},
            stage_size=3,
            comp=3,
            experienced_outcome=3,
            career_status="employed",
            version="v1-2026-09-10",
        )
        db.session.commit()


def _seed_manager_profile(user_id):
    from app import app
    from manager_profile_store import write_manager_profile
    from model import db

    with app.app_context():
        write_manager_profile(
            db, user_id,
            answers=[{"question_id": "mp-q1", "choice": "a"}],
            dimension_scores={
                "autonomy": 0.6, "feedback_style": 0.5,
                "relationship": 0.5, "growth_focus": 0.5,
            },
            scoring_key="v1-2026-09-10",
            version="v1-2026-09-10",
        )
        db.session.commit()


def _seed_situation_report_pin(user_id, submission_id="a" * 32):
    from app import app
    from model import db
    from situation_report_pin_store import set_pin

    with app.app_context():
        set_pin(db, user_id, submission_id)
        db.session.commit()


def _situation_side(user_id):
    """What the three D-7 tables hold for this user, read through their own stores."""
    from app import app
    from environment_report_store import environment_report_history
    from manager_profile_store import manager_profile_history
    from situation_report_pin_store import explicit_pin

    with app.app_context():
        return {
            "environment_reports": environment_report_history(user_id),
            "manager_profiles": manager_profile_history(user_id),
            "situation_report_pin": explicit_pin(user_id),
        }


# ── Export ───────────────────────────────────────────────────────────────────

def test_export_returns_all_identified_data(client, monkeypatch):
    csrf, user_id = _register_and_login(client, monkeypatch)
    _seed_assessment_rows(user_id)

    res = client.get("/api/v1/me/export")
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["account"]["email"] == "lifecycle@example.com"
    assert payload["assessment_answers"][0]["item_id"] == "au1v2"
    assert payload["dimension_scores"][0]["dimension"] == "autonomy"


def test_export_requires_auth(client):
    res = client.get("/api/v1/me/export")
    assert res.status_code == 401


def test_export_includes_environment_reports_manager_profiles_and_situation_pin(
    client, monkeypatch
):
    """BUILD_PLAN D-7: the three tables A-5/C-3 added join `/me/export`.

    Also proves the omission half in the same test: a bystander who never sat either
    instrument gets empty lists and a null pin, not another account's rows.
    """
    _, bystander_id = _register_and_login(
        client, monkeypatch, email="d7-bystander@example.com"
    )
    csrf, user_id = _register_and_login(client, monkeypatch, email="d7-export@example.com")
    _seed_environment_report(user_id)
    _seed_manager_profile(user_id)
    _seed_situation_report_pin(user_id)

    res = client.get("/api/v1/me/export")
    assert res.status_code == 200
    payload = res.get_json()

    assert len(payload["environment_reports"]) == 1
    env = payload["environment_reports"][0]
    assert env["career_status"] == "employed"
    assert env["dimension_scores"]["autonomy"] == 0.5
    assert env["raw_answers"] == {"env-autonomy-1": "mixed-a"}

    assert len(payload["manager_profiles"]) == 1
    mp = payload["manager_profiles"][0]
    assert mp["scoring_key"] == "v1-2026-09-10"
    assert mp["dimension_scores"]["autonomy"] == 0.6

    assert payload["situation_report_pin"]["submission_id"] == "a" * 32

    # The bystander logged in first and never sat either instrument -- their own
    # export must not echo the other account's rows.
    from app import app
    from model import User, db

    with app.app_context():
        bystander = db.session.get(User, bystander_id)
        bystander_email = bystander.email

    bystander_login = client.post(
        "/api/v1/auth/login",
        json={"email": bystander_email, "password": "Strongpass1!"},
    )
    assert bystander_login.status_code == 200

    bystander_export = client.get("/api/v1/me/export").get_json()
    assert bystander_export["environment_reports"] == []
    assert bystander_export["manager_profiles"] == []
    assert bystander_export["situation_report_pin"] is None


# ── Delete ───────────────────────────────────────────────────────────────────

def test_delete_requires_explicit_confirmation(client, monkeypatch):
    csrf, user_id = _register_and_login(client, monkeypatch)

    res = client.delete("/api/v1/me", json={},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 400

    from app import app
    from model import User, db

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.email == "lifecycle@example.com"  # untouched


def test_delete_tombstones_user_and_purges_pii(client, monkeypatch):
    csrf, user_id = _register_and_login(client, monkeypatch)
    _seed_assessment_rows(user_id)

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        user = db.session.get(User, user_id)
        # Personal fields gone
        assert user.email == f"deleted-{user_id}@tombstone.invalid"
        assert user.name is None
        # The profile document is the tombstone and nothing else, which also
        # means no experience, education, skill or resume rows survive -- the
        # write path rebuilds those from the document it is handed.
        assert set(profile_repository.load_document(user_id).keys()) == {"deleted_at"}
        assert user.confirmation_token is None
        assert user.reset_token is None
        # The old password can never verify again (not a bcrypt hash at all)
        assert user.password_hash.startswith("!deleted!")

    # THE decided reconciliation: research rows survive, de-identified
    surviving = _person_side(user_id)
    assert len(surviving["answers"]) == 1
    assert len(surviving["dimension_scores"]) == 1


def test_export_includes_pulse_checkins_and_events(client, monkeypatch):
    """BUILD_PLAN B-1's D-7 rule: pulse_checkins/pulse_events join /me/export the same
    commit that creates them, rather than waiting for the D-7 catch-up chunk
    `environment_reports`/`manager_profiles` still owe."""
    csrf, user_id = _register_and_login(client, monkeypatch)

    from app import app
    from model import db
    from pulse_store import write_pulse_checkin, write_pulse_event
    from work_pulse.pulse_items import dimensions_for_checkin

    with app.app_context():
        item_scores = {dim: 4 for dim in dimensions_for_checkin(user_id, 0)}
        write_pulse_checkin(
            db, user_id, sequence=0, item_scores=item_scores,
            experienced=3, version="pulse-v1-test",
        )
        write_pulse_event(db, user_id, event_type="reorg", note="team split in two")
        db.session.commit()

    res = client.get("/api/v1/me/export")
    assert res.status_code == 200
    payload = res.get_json()

    assert len(payload["pulse_checkins"]) == 1
    assert payload["pulse_checkins"][0]["item_scores"] == item_scores
    assert payload["pulse_checkins"][0]["experienced"] == 3

    assert len(payload["pulse_events"]) == 1
    assert payload["pulse_events"][0]["event_type"] == "reorg"
    assert payload["pulse_events"][0]["note"] == "team split in two"


def test_delete_retains_environment_reports_manager_profiles_and_situation_pin(
    client, monkeypatch
):
    """BUILD_PLAN D-7: the three tables ride the same tombstone reconciliation as the
    person-side rows above -- kept, de-identified via the now-scrubbed user row, never
    destroyed and never updated. A bystander's rows are untouched either way."""
    _, bystander_id = _register_and_login(
        client, monkeypatch, email="d7-delete-bystander@example.com"
    )
    _seed_environment_report(bystander_id)
    _seed_manager_profile(bystander_id)
    _seed_situation_report_pin(bystander_id, submission_id="b" * 32)

    csrf, user_id = _register_and_login(client, monkeypatch, email="d7-delete@example.com")
    _seed_environment_report(user_id)
    _seed_manager_profile(user_id)
    _seed_situation_report_pin(user_id, submission_id="a" * 32)

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    surviving = _situation_side(user_id)
    assert len(surviving["environment_reports"]) == 1
    assert surviving["environment_reports"][0]["dimension_scores"]["autonomy"] == 0.5
    assert len(surviving["manager_profiles"]) == 1
    assert surviving["manager_profiles"][0]["scoring_key"] == "v1-2026-09-10"
    assert surviving["situation_report_pin"]["submission_id"] == "a" * 32

    # The row now hangs off a tombstoned, de-identified user_id -- not deleted, not
    # reassigned, not touched.
    from app import app
    from model import User, db

    with app.app_context():
        deleted_user = db.session.get(User, user_id)
        assert deleted_user.email == f"deleted-{user_id}@tombstone.invalid"

    # Bystander untouched.
    bystander_side = _situation_side(bystander_id)
    assert len(bystander_side["environment_reports"]) == 1
    assert len(bystander_side["manager_profiles"]) == 1
    assert bystander_side["situation_report_pin"]["submission_id"] == "b" * 32


def test_delete_removes_dependent_personal_rows(client, monkeypatch):
    csrf, user_id = _register_and_login(client, monkeypatch)

    from app import app
    from model import JobRecommendation, UserIntake, db

    with app.app_context():
        db.session.add(JobRecommendation(user_id=user_id, job_id=1, score=0.9))
        db.session.add(UserIntake(user_id=user_id, selected_statement_ids=[],
                                  wpll_answers=[]))
        db.session.commit()

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    with app.app_context():
        assert JobRecommendation.query.filter_by(user_id=user_id).count() == 0
        assert UserIntake.query.filter_by(user_id=user_id).count() == 0


def test_delete_retains_pulse_checkins(client, monkeypatch):
    """D-7b ruling (2026-09-11): pulse_checkins rides the tombstone, de-identified,
    exactly like environment_reports -- no column on the row is free text, so it does
    not qualify for the "must be destroyed" class the way pulse_events does. A
    bystander's check-in is untouched either way."""
    _, bystander_id = _register_and_login(
        client, monkeypatch, email="d7b-pulse-bystander@example.com"
    )
    csrf, user_id = _register_and_login(client, monkeypatch, email="d7b-pulse@example.com")

    from app import app
    from model import PulseCheckin, db
    from pulse_store import write_pulse_checkin
    from work_pulse.pulse_items import dimensions_for_checkin

    with app.app_context():
        for uid in (bystander_id, user_id):
            item_scores = {dim: 4 for dim in dimensions_for_checkin(uid, 0)}
            write_pulse_checkin(
                db, uid, sequence=0, item_scores=item_scores,
                experienced=3, version="pulse-v1-test",
            )
        db.session.commit()

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    with app.app_context():
        # Not destroyed, not reassigned -- still hanging off the now-tombstoned
        # user_id, the same "nothing to do" reconciliation as environment_reports.
        surviving = PulseCheckin.query.filter_by(user_id=user_id).all()
        assert len(surviving) == 1
        assert surviving[0].experienced == 3

        from model import User
        deleted_user = db.session.get(User, user_id)
        assert deleted_user.email == f"deleted-{user_id}@tombstone.invalid"

        # Bystander untouched.
        assert PulseCheckin.query.filter_by(user_id=bystander_id).count() == 1


def test_delete_retains_experiments(client, monkeypatch):
    """BUILD_PLAN B-5's own D-7 wiring, applying the D-7b test fresh: dimension,
    direction, register and status are all closed vocabularies, so the row rides
    the tombstone de-identified exactly like pulse_checkins/environment_reports.
    A bystander's experiment is untouched either way."""
    _, bystander_id = _register_and_login(
        client, monkeypatch, email="b5-experiments-bystander@example.com"
    )
    csrf, user_id = _register_and_login(client, monkeypatch, email="b5-experiments@example.com")

    from app import app
    from experiment_store import start_experiment
    from model import Experiment, db

    with app.app_context():
        for uid in (bystander_id, user_id):
            start_experiment(db, uid, dimension="autonomy", direction="under")
        db.session.commit()

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    with app.app_context():
        # Not destroyed, not reassigned -- still hanging off the now-tombstoned
        # user_id, the same "nothing to do" reconciliation as pulse_checkins.
        surviving = Experiment.query.filter_by(user_id=user_id).all()
        assert len(surviving) == 1
        assert surviving[0].dimension == "autonomy"
        assert surviving[0].status == "active"

        from model import User
        deleted_user = db.session.get(User, user_id)
        assert deleted_user.email == f"deleted-{user_id}@tombstone.invalid"

        # Bystander untouched.
        assert Experiment.query.filter_by(user_id=bystander_id).count() == 1


def test_delete_removes_pulse_events(client, monkeypatch):
    """The other half of the D-7b split: pulse_events IS destroyed on deletion,
    never tombstoned or retained de-identified -- `note` is free text, and free text
    is never retained de-identified. Neither table is behind D-01's doorway the way
    the core assessment rows are."""
    csrf, user_id = _register_and_login(client, monkeypatch)

    from app import app
    from model import PulseEvent, db
    from pulse_store import write_pulse_event

    with app.app_context():
        write_pulse_event(db, user_id, event_type="reorg")
        db.session.commit()

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    with app.app_context():
        assert PulseEvent.query.filter_by(user_id=user_id).count() == 0


def test_deleted_account_cannot_login(client, monkeypatch):
    csrf, user_id = _register_and_login(client, monkeypatch)

    client.delete("/api/v1/me", json={"confirm": "DELETE"},
                headers={"X-CSRF-TOKEN": csrf})

    res = client.post("/api/v1/auth/login", json={
        "email": "lifecycle@example.com", "password": "Strongpass1!"})
    assert res.status_code in (400, 401, 404)


# ── The legacy blob (SECURITY_AUDIT_2026-09 4.1) ─────────────────────────────
#
# `users.profile_data` is the pre-Phase-2a copy of the profile document. Nothing
# reads or writes it any more, which is precisely how it went unscrubbed: the
# deletion path was rewritten around the tables that replaced it, and the column
# it was decomposed *from* was left holding everything. Every account created
# before Phase 2a still has one, so this is not a hypothetical row.
#
# These are destructive-path tests, so they assert the blast radius in both
# directions: the deleting user's blob is gone, and nobody else's is touched.

#: A stand-in for what a pre-decomposition account actually holds. Written
#: straight to the column because no code path writes it any more -- which is
#: the point.
_LEGACY_BLOB = {
    "firstName": "Legacy",
    "lastName": "User",
    "phone": "+1-555-0100",
    "linkedinUrl": "https://linkedin.com/in/legacy-user",
    "resumeText": "Legacy User -- Senior Widget Engineer at Acme, 2019-2024",
    "experience": [{"id": 1, "company": "Acme", "position": "Engineer"}],
}


def _seed_legacy_blob(user_id, blob=None):
    from app import app
    from model import User, db

    with app.app_context():
        user = db.session.get(User, user_id)
        user.profile_data = dict(blob if blob is not None else _LEGACY_BLOB)
        db.session.commit()


def _legacy_blob(user_id):
    from app import app
    from model import User, db

    with app.app_context():
        return db.session.get(User, user_id).profile_data


def test_delete_scrubs_the_legacy_profile_data_blob(client, monkeypatch):
    """Deletion empties `users.profile_data`, not just the tables that replaced it.

    Before this, a tombstoned pre-Phase-2a account kept its phone number,
    LinkedIn URL, parsed resume text and employment history verbatim in the row
    the response calls scrubbed.
    """
    csrf, user_id = _register_and_login(client, monkeypatch)
    _seed_legacy_blob(user_id)
    assert _legacy_blob(user_id)["phone"] == "+1-555-0100"  # the fixture took

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                        headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    assert _legacy_blob(user_id) == {}


def test_delete_scrubs_only_the_deleting_users_blob(client, monkeypatch):
    """The scrub is one row wide.

    A column-level UPDATE with a missing or wrong predicate would empty the
    legacy profile of every account in the table, and there is no undo for that
    -- so the bystander is asserted, not assumed.
    """
    _, bystander_id = _register_and_login(
        client, monkeypatch, email="bystander@example.com"
    )
    _seed_legacy_blob(bystander_id, {"firstName": "Bystander", "phone": "+1-555-0199"})

    # Logging in as the second account replaces the session cookie, so the
    # delete below is unambiguously the second user's.
    csrf, user_id = _register_and_login(client, monkeypatch)
    _seed_legacy_blob(user_id)

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                        headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    assert _legacy_blob(user_id) == {}
    assert _legacy_blob(bystander_id) == {
        "firstName": "Bystander",
        "phone": "+1-555-0199",
    }

    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        bystander = db.session.get(User, bystander_id)
        assert bystander.email == "bystander@example.com"
        assert bystander.status != "deleted"
        # The bystander's new-format profile is intact too: the scrub reaches
        # one column on one row and nothing downstream of it.
        assert "deleted_at" not in profile_repository.load_document(bystander_id)


def test_the_new_format_profile_tables_keep_their_existing_deletion_path(
    client, monkeypatch
):
    """Scrubbing the legacy column changed nothing about how Phase 2a rows die.

    They are still erased by rewriting the profile document -- one write path,
    so a field added to the profile later is erased without anyone remembering
    to come back. This asserts the child rows themselves, which the document
    assertion in `test_delete_tombstones_user_and_purges_pii` reaches only
    through `load_document`.
    """
    csrf, user_id = _register_and_login(client, monkeypatch)
    _seed_legacy_blob(user_id)

    from app import app
    from model import ProfileEducation, ProfileExperience, ProfileSkill, db
    from solverah.repositories import profile_repository

    with app.app_context():
        profile_repository.update_document(
            user_id,
            lambda existing: {
                **existing,
                "experience": [
                    {"id": 1, "company": "Acme", "position": "Engineer",
                     "startDate": "", "endDate": "2024", "description": ""}
                ],
                "education": [
                    {"id": 1, "institution": "State U", "degree": "BSc",
                     "startDate": "", "endDate": "", "gpa": "", "description": ""}
                ],
                "skills": ["widgets", "sprockets"],
            },
        )
        db.session.commit()

        assert ProfileExperience.query.filter_by(user_id=user_id).count() == 1
        assert ProfileEducation.query.filter_by(user_id=user_id).count() == 1
        assert ProfileSkill.query.filter_by(user_id=user_id).count() == 2

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                        headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    with app.app_context():
        assert ProfileExperience.query.filter_by(user_id=user_id).count() == 0
        assert ProfileEducation.query.filter_by(user_id=user_id).count() == 0
        assert ProfileSkill.query.filter_by(user_id=user_id).count() == 0
        assert set(profile_repository.load_document(user_id).keys()) == {"deleted_at"}


def test_the_blob_scrub_is_part_of_the_tombstone_not_a_later_write(
    client, monkeypatch
):
    """One unit of work, so there is no window in which the row is half-deleted.

    `tombstone_user` does not commit -- its caller owns the transaction -- and
    the scrub has to live inside that same boundary. A scrub committed
    separately is a scrub that a crash in between turns into a deleted account
    still holding a complete profile, which nothing would ever look at again to
    notice. Rolling back is what demonstrates it: if the two were in one
    transaction, undoing it undoes both.
    """
    _, user_id = _register_and_login(client, monkeypatch)
    _seed_legacy_blob(user_id)

    from app import app
    from model import User, db
    from solverah.repositories import account_repository

    with app.app_context():
        user = db.session.get(User, user_id)
        account_repository.tombstone_user(
            user,
            tombstone_domain="tombstone.invalid",
            now_iso="2026-09-03T00:00:00",
            dead_password="!deleted!",
        )

        # Uncommitted, and already both.
        assert user.profile_data == {}
        assert user.status == "deleted"

        db.session.rollback()

        restored = db.session.get(User, user_id)
        assert restored.status != "deleted"
        assert restored.profile_data["phone"] == "+1-555-0100"


# ── D-7b: export/delete gap closures (2026-09-11) ───────────────────────────
#
# tests/test_export_delete_coverage.py carried resume_parse_correction, resume_parse_jobs,
# scoring_jobs and (partially) assessment_submissions in ALLOWLIST as documented,
# unfixed gaps. Each test below is the regression that guard's now-COVERED entry for
# that table points at.


def test_export_includes_resume_parse_corrections(client, monkeypatch):
    """resume_parse_correction's corrected_value is what the user typed to fix a
    parser-extracted field -- the same class of content assessment_answers already
    gets an export for. Closes the gap the pre-D-7b ALLOWLIST entry flagged."""
    csrf, user_id = _register_and_login(client, monkeypatch, email="d7b-correction@example.com")

    from app import app
    from model import db
    from solverah.repositories import profile_repository

    with app.app_context():
        profile_repository.record_resume_corrections(
            user_id, "profile/%s/x/resume.pdf" % user_id,
            [("phone", "+1-000-0000", "+1-555-0100")],
        )
        db.session.commit()

    res = client.get("/api/v1/me/export")
    assert res.status_code == 200
    payload = res.get_json()

    assert len(payload["resume_parse_corrections"]) == 1
    correction = payload["resume_parse_corrections"][0]
    assert correction["resume_key"] == "profile/%s/x/resume.pdf" % user_id
    assert correction["field"] == "phone"
    assert correction["parsed_value"] == "+1-000-0000"
    assert correction["corrected_value"] == "+1-555-0100"


def test_delete_removes_resume_parse_corrections(client, monkeypatch):
    csrf, user_id = _register_and_login(
        client, monkeypatch, email="d7b-correction-delete@example.com"
    )

    from app import app
    from model import ResumeParseCorrection, db
    from solverah.repositories import profile_repository

    with app.app_context():
        profile_repository.record_resume_corrections(
            user_id, "profile/%s/x/resume.pdf" % user_id,
            [("phone", "+1-000-0000", "+1-555-0100")],
        )
        db.session.commit()

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    with app.app_context():
        assert ResumeParseCorrection.query.filter_by(user_id=user_id).count() == 0


def test_delete_removes_resume_parse_jobs(client, monkeypatch):
    """BUILD_PLAN D-7b, closing SECURITY_AUDIT_2026-09 #7's residual half: the row
    carries resume_name (often a person's own name) and object_key (a locator to
    personal resume bytes) and previously survived account deletion untouched --
    swept only by resume_jobs.purge_terminal's own 30-day TTL, whether or not the
    account behind it still exists."""
    csrf, user_id = _register_and_login(client, monkeypatch, email="d7b-parse-job@example.com")

    from app import app
    from model import ResumeParseJob, db

    with app.app_context():
        db.session.add(ResumeParseJob(
            user_id=user_id,
            object_key="profile/%s/x/resume.pdf" % user_id,
            mime="application/pdf",
            size_bytes=2048,
            resume_name="Lifecycle User Resume.pdf",
            status="succeeded",
        ))
        db.session.commit()

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    with app.app_context():
        assert ResumeParseJob.query.filter_by(user_id=user_id).count() == 0


def test_delete_removes_scoring_jobs(client, monkeypatch):
    """BUILD_PLAN D-7b: scoring_jobs holds a duplicate copy of personal content --
    payload (submitted answers, pre-terminal) or result (a scored narrative/archetype,
    post-terminal) -- that previously outlived account deletion for up to
    scoring_jobs.PURGE_DAYS, the same class of gap resume_parse_jobs closes above."""
    csrf, user_id = _register_and_login(client, monkeypatch, email="d7b-scoring-job@example.com")

    from app import app
    from model import ScoringJob, db

    with app.app_context():
        db.session.add(ScoringJob(
            user_id=user_id,
            job_type="assessment_scoring",
            kind="work_pulse",
            payload={},
            status="succeeded",
            result={"narrative": "a scored narrative about this person"},
        ))
        db.session.commit()

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                      headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    with app.app_context():
        assert ScoringJob.query.filter_by(user_id=user_id).count() == 0


#: The exact payload Scripts/capture_contract.py exercises for FocusType -- reused
#: rather than invented, so this test's shape is one already proven to score.
_FOCUS_TYPE_PAYLOAD = {
    "scene_1": ["big_project", "planning_doc", "urgent_client", "teammate_feedback",
                "emails", "admin_tasks"],
    "scene_2": {
        "now": ["email_client_important", "slack_mentioned"],
        "later": ["slack_teammate_question"],
        "ignore": ["email_newsletter", "calendar_meeting_invite", "task_new_ticket",
                   "task_planning_doc", "slack_team_channel", "email_system_report",
                   "calendar_team_lunch"],
    },
    "scene_3": {"deep_solo": 2.5, "planning": 0.5, "social": 0.5, "breaks": 0.25,
                "exploring": 0.25},
    "scene_4": {
        "now": ["deep_research"],
        "tomorrow": ["reply_teammate", "write_report_draft", "update_task_tracker",
                     "quick_call_unblock", "send_followup_email", "review_others_work",
                     "sketch_tomorrow_plan"],
        "avg_decision_time_ms": 500,
    },
    "scene_5": ["deep_work", "wind_down"],
}

_MM_ANSWERS = [{"question_id": "mm-q%d" % i, "choice": "a"} for i in range(1, 16)]


def _mock_openai_client(monkeypatch, narrative="A test narrative."):
    import json as json_module
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    llm_body = {
        "narrative": narrative,
        "what_to_look_for": ["one thing to ask about"],
        "red_flags": ["one flag to watch for"],
        "archetype_description": "A test archetype description.",
    }
    mock_choice = MagicMock()
    mock_choice.message.content = json_module.dumps(llm_body)
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: mock_client)


def test_export_includes_focus_type_and_manager_match_answers(client, monkeypatch):
    """BUILD_PLAN D-7b. The scored `result` for both kinds already reached export
    before this chunk -- nested at profile.focus_type_result/profile.manager_match_result
    via profile_repository.load_document -- so this test locks that prior behaviour in
    too, rather than asserting only the raw `answers` this chunk actually adds."""
    csrf, user_id = _register_and_login(client, monkeypatch, email="d7b-ft-mm@example.com")

    ft_res = client.post(
        "/api/v1/assessments/focus_type/submissions",
        json=_FOCUS_TYPE_PAYLOAD,
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert ft_res.status_code == 200

    _mock_openai_client(monkeypatch)
    queued = client.post(
        "/api/v1/assessments/manager_match/scoring-jobs",
        json={"answers": _MM_ANSWERS},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert queued.status_code == 202
    poll = client.get(
        "/api/v1/assessments/manager_match/scoring-jobs/%s" % queued.get_json()["job_id"]
    )
    assert poll.get_json()["status"] == "succeeded"

    res = client.get("/api/v1/me/export")
    assert res.status_code == 200
    payload = res.get_json()

    # The gap this chunk closes: the raw answers, absent from export before now.
    assert payload["focus_type_answers"] == _FOCUS_TYPE_PAYLOAD
    assert payload["manager_match_answers"] == _MM_ANSWERS

    # The behaviour this chunk did NOT need to add, locked in so it cannot regress
    # unnoticed: the scored result, nested in the profile document.
    assert payload["profile"]["manager_match_result"]["narrative"] == "A test narrative."
    assert "archetype" in payload["profile"]["focus_type_result"]


def test_export_omits_focus_type_and_manager_match_answers_when_never_sat(client, monkeypatch):
    """The omission half: a bystander who never sat either instrument gets null, not
    another account's answers or a KeyError."""
    csrf, user_id = _register_and_login(client, monkeypatch, email="d7b-ft-mm-bystander@example.com")

    res = client.get("/api/v1/me/export")
    assert res.status_code == 200
    payload = res.get_json()

    assert payload["focus_type_answers"] is None
    assert payload["manager_match_answers"] is None


# ── C1 trait preferences and C3 pasted job postings ─────────────────────────
#
# The two tables answer the D-7b question from opposite sides. The trait-preference
# sittings hold no free text (step counts, a boolean, a closed trait key) and sit
# behind D-01's doorway with no `ondelete`, so they are RETAINED de-identified under
# the tombstone like the core assessment's rows. A pasted posting is the user's own
# free text, so it is DESTROYED, with everything the pipeline derived from it.

def _seed_trait_preferences(user_id, under, over, must=()):
    """One sitting, through the D-01 doorway's write path."""
    from app import app
    from assessment_store import save_trait_preferences
    from model import db
    from solverah.domain.trait_preferences import TRAIT_KEYS, TraitPreference

    with app.app_context():
        sitting = save_trait_preferences(db, user_id, {
            key: TraitPreference(
                dimension_key=key, under_steps=under, over_steps=over,
                must_have=key in must, answered=True,
            )
            for key in TRAIT_KEYS
        })
        db.session.commit()
        return sitting


def _seed_scored_posting(user_id, slug, text="We move fast and break things."):
    """A pasted posting with the whole derived chain under it: one evidence item, its
    score, and a posting-private trait record linked to that score. Every write goes
    through company_evidence_store, the only door to those tables. Returns the
    posting id and the private record id."""
    from app import app
    from company_evidence_store import (
        EvidenceItemInput,
        ItemScoreInput,
        TraitRecordInput,
        create_job_posting,
        write_item_scores,
        write_items,
        write_trait_records,
    )
    from model import Company, EvidenceItemScore, ScorerRun, db

    with app.app_context():
        company = Company(name=slug.title(), slug=slug, profile_json={})
        scorer = ScorerRun(
            model="test-model", temperature=0, temperature_honored=True,
            rubric_version="v3.1", packet_version="v4.11",
        )
        db.session.add_all([company, scorer])
        db.session.commit()

        posting = create_job_posting(
            db, user_id, posting_text=text, title="Staff Engineer", company_id=company.id
        )
        (item_id,) = write_items(
            db, company.id,
            # Positional on purpose: the third field is the scorer's internal copy, a
            # name tests/test_company_evidence_internal.py keeps out of this file.
            [EvidenceItemInput(
                "role", "user_pasted_posting", text, "The posting describes a fast pace.",
                scope_label="Staff Engineer",
            )],
            job_posting_id=posting.id,
        )
        write_item_scores(db, [ItemScoreInput(item_id, "pace", score=0.9)], scorer_run_id=scorer.id)
        score_id = EvidenceItemScore.query.filter_by(evidence_item_id=item_id).one().id
        (record_id,) = write_trait_records(
            db, company.id,
            [TraitRecordInput(
                "pace", "role", "known", estimate=0.9, scope_label="Staff Engineer",
                score_ids=[score_id], job_posting_id=posting.id,
            )],
            aggregation_version="agg-test",
        )
        return posting.id, record_id


def _posting_trace(posting_id, record_id):
    """How many rows of each derived kind still hang off one posting."""
    from app import app
    from model import (
        CompanyEvidenceItem,
        CompanyTraitRecord,
        CompanyTraitRecordEvidence,
        EvidenceItemScore,
        JobPostingSubmission,
        db,
    )

    with app.app_context():
        item_ids = [
            i for (i,) in db.session.query(CompanyEvidenceItem.id).filter_by(job_posting_id=posting_id)
        ]
        return {
            "posting": JobPostingSubmission.query.filter_by(id=posting_id).count(),
            "items": len(item_ids),
            "scores": EvidenceItemScore.query.filter(
                EvidenceItemScore.evidence_item_id.in_(item_ids or [-1])
            ).count(),
            "records": CompanyTraitRecord.query.filter_by(job_posting_id=posting_id).count(),
            "links": CompanyTraitRecordEvidence.query.filter_by(trait_record_id=record_id).count(),
        }


def test_export_includes_trait_preferences_and_job_postings(client, monkeypatch):
    """Every trait sitting, oldest first; every pasted posting, newest first, with the
    text the user pasted. A bystander's paste is not in it."""
    _, bystander_id = _register_and_login(client, monkeypatch, email="c3-export-bystander@example.com")
    _seed_scored_posting(bystander_id, "bystander-co", text="Not yours.")

    _, user_id = _register_and_login(client, monkeypatch, email="c3-export@example.com")
    first = _seed_trait_preferences(user_id, under=0, over=0, must=("pace",))
    second = _seed_trait_preferences(user_id, under=2, over=1)

    from app import app
    from company_evidence_store import create_job_posting
    from model import db

    with app.app_context():
        older = create_job_posting(db, user_id, posting_text="We move fast.")
        newer = create_job_posting(db, user_id, posting_text="Calm, steady team.", title="PM")

    res = client.get("/api/v1/me/export")
    assert res.status_code == 200
    payload = res.get_json()

    prefs = payload["trait_preferences"]
    assert len(prefs) == 12
    assert [p["sitting_id"] for p in prefs] == [first] * 6 + [second] * 6
    assert {(p["under_steps"], p["over_steps"]) for p in prefs[:6]} == {(0, 0)}
    assert [p["dimension"] for p in prefs[:6] if p["must_have"]] == ["pace"]
    assert {(p["under_steps"], p["over_steps"]) for p in prefs[6:]} == {(2, 1)}

    postings = payload["job_postings"]
    assert [p["id"] for p in postings] == [newer.id, older.id]
    assert [p["posting_text"] for p in postings] == ["Calm, steady team.", "We move fast."]
    assert postings[0]["title"] == "PM" and postings[0]["status"] == "pending"
    assert postings[0]["created_at"]
    assert "Not yours." not in res.get_data(as_text=True)
    # The user's own paste and its bookkeeping -- nothing the pipeline derived from it.
    assert set(postings[0]) == {"id", "company_id", "title", "posting_text", "status", "created_at"}


def test_export_carries_empty_lists_when_neither_table_has_rows(client, monkeypatch):
    _register_and_login(client, monkeypatch, email="c3-export-empty@example.com")

    payload = client.get("/api/v1/me/export").get_json()
    assert payload["trait_preferences"] == []
    assert payload["job_postings"] == []


def test_delete_retains_trait_preferences_behind_the_tombstone(client, monkeypatch):
    """The core assessment's reconciliation, applied to C1: no free text and no
    `ondelete`, so the sittings survive, de-identified, on the tombstoned user id."""
    csrf, user_id = _register_and_login(client, monkeypatch, email="c1-delete@example.com")
    _seed_trait_preferences(user_id, under=1, over=2, must=("pace", "autonomy"))

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                        headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    surviving = _person_side(user_id)["trait_preferences"]
    assert len(surviving) == 6
    assert {(p["under_steps"], p["over_steps"]) for p in surviving} == {(1, 2)}

    from app import app
    from model import User, db

    with app.app_context():
        assert db.session.get(User, user_id).email == f"deleted-{user_id}@tombstone.invalid"


def test_delete_destroys_job_postings_and_everything_derived_from_them(client, monkeypatch):
    """D-7b: the paste is free text, so it is destroyed, and so is every row the
    pipeline derived from it. A bystander's posting chain is untouched."""
    _, bystander_id = _register_and_login(client, monkeypatch, email="c3-delete-bystander@example.com")
    bystander_posting, bystander_record = _seed_scored_posting(bystander_id, "bystander-co")

    csrf, user_id = _register_and_login(client, monkeypatch, email="c3-delete@example.com")
    posting_id, record_id = _seed_scored_posting(user_id, "user-co")
    assert _posting_trace(posting_id, record_id) == {
        "posting": 1, "items": 1, "scores": 1, "records": 1, "links": 1,
    }

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                        headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    assert _posting_trace(posting_id, record_id) == {
        "posting": 0, "items": 0, "scores": 0, "records": 0, "links": 0,
    }
    from app import app
    from model import JobPostingSubmission

    with app.app_context():
        assert JobPostingSubmission.query.filter_by(user_id=user_id).count() == 0

    assert _posting_trace(bystander_posting, bystander_record) == {
        "posting": 1, "items": 1, "scores": 1, "records": 1, "links": 1,
    }


def test_posting_destruction_waits_for_the_deletions_own_commit(client, monkeypatch):
    """`delete_personal_rows` does not commit, and the posting store's per-call commit
    must not sneak one in: if the deletion fails before its commit, the account is
    still live and so are its postings. Fails if the store is called with the real
    session, whose commit would land the posting deletes on their own."""
    _, user_id = _register_and_login(client, monkeypatch, email="c3-atomic@example.com")
    posting_id, record_id = _seed_scored_posting(user_id, "atomic-co")

    from app import app
    from model import db
    from solverah.repositories import account_repository

    with app.app_context():
        account_repository.delete_personal_rows(user_id, [])
        db.session.rollback()

    assert _posting_trace(posting_id, record_id) == {
        "posting": 1, "items": 1, "scores": 1, "records": 1, "links": 1,
    }

    with app.app_context():
        account_repository.delete_personal_rows(user_id, [])
        db.session.commit()

    assert _posting_trace(posting_id, record_id)["posting"] == 0


# ── C6: "I took this job" links ──────────────────────────────────────────────


def _seed_company_link(user_id, slug, started_on, ended_on=None):
    """A company and one link to it, through company_evidence_store's own write.
    Returns the link id."""
    from app import app
    from company_evidence_store import create_company_link
    from model import Company, UserCompanyLink, db

    with app.app_context():
        company = Company.query.filter_by(slug=slug).first()
        if company is None:
            company = Company(name=slug.title(), slug=slug, profile_json={})
            db.session.add(company)
            db.session.commit()
        link = create_company_link(db, user_id, company_id=company.id, started_on=started_on)
        if ended_on is not None:
            # The store has no "end a link" write yet; the column is the user's own
            # date, so setting it here builds nothing the real path could not.
            db.session.get(UserCompanyLink, link.id).ended_on = ended_on
            db.session.commit()
        return link.id


def _seed_pulse_checkin(user_id):
    """One check-in through pulse_store's write, which attaches the active link."""
    from app import app
    from model import db
    from pulse_store import write_pulse_checkin
    from work_pulse.pulse_items import dimensions_for_checkin

    with app.app_context():
        checkin_id = write_pulse_checkin(
            db, user_id, sequence=0,
            item_scores={dim: 4 for dim in dimensions_for_checkin(user_id, 0)},
            experienced=3, version="pulse-v1-test",
        )
        db.session.commit()
        return checkin_id


def test_export_includes_company_links(client, monkeypatch):
    """Every link the user made, newest start first, with the dates they gave. A
    bystander's link is not in it, and the check-in filed under the active link
    carries its id -- validated against the published schema, which forbids keys it
    does not declare."""
    import datetime

    from solverah.schemas.account import AccountExportResponse

    today = datetime.date.today()
    _, bystander_id = _register_and_login(client, monkeypatch, email="c6-export-bystander@example.com")
    bystander_link = _seed_company_link(bystander_id, "c6-bystander-co", today)

    _, user_id = _register_and_login(client, monkeypatch, email="c6-export@example.com")
    older = _seed_company_link(
        user_id, "c6-old-co", today - datetime.timedelta(days=400),
        ended_on=today - datetime.timedelta(days=30),
    )
    newer = _seed_company_link(user_id, "c6-new-co", today - datetime.timedelta(days=10))
    checkin_id = _seed_pulse_checkin(user_id)

    res = client.get("/api/v1/me/export")
    assert res.status_code == 200
    payload = res.get_json()
    AccountExportResponse.model_validate(payload)

    links = payload["company_links"]
    assert [link["id"] for link in links] == [newer, older]
    assert links[0]["started_on"] == (today - datetime.timedelta(days=10)).isoformat()
    assert links[0]["ended_on"] is None
    assert links[1]["ended_on"] == (today - datetime.timedelta(days=30)).isoformat()
    assert links[0]["created_at"]
    assert set(links[0]) == {"id", "company_id", "started_on", "ended_on", "created_at"}
    assert bystander_link not in {link["id"] for link in links}

    (checkin,) = payload["pulse_checkins"]
    assert checkin["id"] == checkin_id
    assert checkin["company_link_id"] == newer


def test_export_carries_an_empty_company_links_list(client, monkeypatch):
    _register_and_login(client, monkeypatch, email="c6-export-empty@example.com")

    payload = client.get("/api/v1/me/export").get_json()
    assert payload["company_links"] == []


def test_delete_retains_company_links_and_the_checkins_keep_their_anchor(client, monkeypatch):
    """C6 rides the tombstone, the precedent `environment_reports.employer_name_normalized`
    sets for an employer identity tied to a person: no free text, and a research reader
    (the check-ins tied to the CompanyLens read). The links survive on the tombstoned
    user id, the check-ins keep pointing at them, and a bystander is untouched. Fails if
    deletion destroys the links -- the check-ins' `company_link_id` would go NULL."""
    import datetime

    today = datetime.date.today()
    _, bystander_id = _register_and_login(client, monkeypatch, email="c6-delete-bystander@example.com")
    bystander_link = _seed_company_link(bystander_id, "c6-del-bystander-co", today)
    bystander_checkin = _seed_pulse_checkin(bystander_id)

    csrf, user_id = _register_and_login(client, monkeypatch, email="c6-delete@example.com")
    link_id = _seed_company_link(user_id, "c6-del-co", today - datetime.timedelta(days=5))
    checkin_id = _seed_pulse_checkin(user_id)

    res = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                        headers={"X-CSRF-TOKEN": csrf})
    assert res.status_code == 200

    from app import app
    from model import PulseCheckin, User, UserCompanyLink, db

    with app.app_context():
        assert db.session.get(User, user_id).email == f"deleted-{user_id}@tombstone.invalid"

        surviving = UserCompanyLink.query.filter_by(user_id=user_id).all()
        assert [row.id for row in surviving] == [link_id]
        assert surviving[0].started_on == today - datetime.timedelta(days=5)
        assert db.session.get(PulseCheckin, checkin_id).company_link_id == link_id

        assert [row.id for row in UserCompanyLink.query.filter_by(user_id=bystander_id)] == [
            bystander_link
        ]
        assert db.session.get(PulseCheckin, bystander_checkin).company_link_id == bystander_link
