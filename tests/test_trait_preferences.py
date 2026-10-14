"""Per-trait tolerance and must-have (six-trait match model, 2026-10-13).

Three layers, one file:

* the pure rules and the flat-zone arithmetic in ``solverah.domain.trait_preferences``;
* the D-01 doorway, ``assessment_store.get_trait_preferences`` / ``save_trait_preferences``
  (latest sitting wins, earlier sittings kept, unanswered is never a default);
* ``GET`` / ``PUT /api/v1/me/trait-preferences`` (auth, the 400s, the round trip).

The table itself is never named here: tests/test_employer_visibility.py scans every
file's identifiers and string literals for it, and a test is not on its allowlist.
"""

from __future__ import annotations

import pytest

from solverah.domain.trait_preferences import (
    ALIGNED_FLOOR,
    MAX_MUST_HAVES,
    TRAIT_KEYS,
    TraitPreference,
    TraitPreferenceError,
    flat_zones,
    must_have_keys,
    parse_trait_preferences,
    unanswered_preferences,
    validate_trait_preferences,
)

PASSWORD = "Strongpass1!"
URL = "/api/v1/me/trait-preferences"


# The form-token secret has no default by design (D-05) and is set per file, never in
# conftest.py: test_assessment_form.py deletes it to prove the no-default rule holds.
@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


def _answered(under=1, over=1, must=()):
    return {
        key: TraitPreference(
            dimension_key=key,
            under_steps=under,
            over_steps=over,
            must_have=key in must,
            answered=True,
        )
        for key in TRAIT_KEYS
    }


def _body(under=1, over=1, must=()):
    return {
        "traits": [
            {"dimension_key": key, "under_steps": under, "over_steps": over,
             "must_have": key in must}
            for key in TRAIT_KEYS
        ]
    }


# ── The vocabulary agrees with the rest of the product ─────────────────────


def test_trait_keys_match_the_situation_report_dimensions():
    from work_pulse.situation import DIMENSIONS

    assert TRAIT_KEYS == DIMENSIONS


def test_the_floor_is_the_situation_reports_aligned_band():
    from work_pulse.situation import ALIGNED_THRESHOLDS

    assert set(ALIGNED_THRESHOLDS.values()) == {ALIGNED_FLOOR}


def test_the_model_check_constraint_uses_the_same_six_keys():
    from model import TRAIT_PREFERENCE_DIMENSIONS

    assert TRAIT_PREFERENCE_DIMENSIONS == TRAIT_KEYS


# ── flat_zones ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "steps, zone", [(0, 0.15), (1, 0.25), (2, 0.5)]
)
def test_flat_zone_is_steps_times_a_quarter_floored_at_the_aligned_band(steps, zone):
    zones = flat_zones(_answered(under=steps, over=steps))

    assert zones == {key: (zone, zone) for key in TRAIT_KEYS}


def test_flat_zones_keep_the_two_directions_apart():
    prefs = _answered(under=0, over=2)

    assert flat_zones(prefs)["pace"] == (0.15, 0.5)


def test_unanswered_user_has_no_zones_so_callers_take_todays_path():
    assert flat_zones(unanswered_preferences()) is None


def test_flat_zones_refuse_a_partial_set_rather_than_guess():
    prefs = _answered()
    del prefs["pace"]

    with pytest.raises(ValueError):
        flat_zones(prefs)


def test_flat_zones_refuse_answered_and_unanswered_mixed():
    prefs = _answered()
    prefs["pace"] = unanswered_preferences()["pace"]

    with pytest.raises(ValueError):
        flat_zones(prefs)


def test_must_have_keys():
    assert must_have_keys(_answered(must=("pace", "feedback"))) == {"pace", "feedback"}
    assert must_have_keys(unanswered_preferences()) == frozenset()


# ── The rules ──────────────────────────────────────────────────────────────


def _codes(exc_info):
    return {e["code"] for e in exc_info.value.errors}


def test_a_complete_sitting_validates():
    validate_trait_preferences(_answered(under=0, over=2, must=("pace", "decision")))


def test_three_must_haves_are_refused():
    with pytest.raises(TraitPreferenceError) as exc_info:
        validate_trait_preferences(_answered(must=("pace", "decision", "autonomy")))

    assert _codes(exc_info) == {"too_many_must_haves"}
    assert MAX_MUST_HAVES == 2


@pytest.mark.parametrize("bad", [-1, 3, None, True, "1", 1.0])
def test_steps_outside_zero_to_two_are_refused(bad):
    raw = _body()["traits"]
    raw[0]["over_steps"] = bad

    with pytest.raises(TraitPreferenceError) as exc_info:
        parse_trait_preferences(raw)

    assert _codes(exc_info) == {"steps_out_of_range"}


def test_a_missing_trait_is_refused():
    raw = _body()["traits"][:-1]

    with pytest.raises(TraitPreferenceError) as exc_info:
        parse_trait_preferences(raw)

    assert _codes(exc_info) == {"missing_trait"}


def test_an_unknown_or_repeated_trait_is_refused():
    raw = _body()["traits"]
    raw.append(dict(raw[0]))
    with pytest.raises(TraitPreferenceError) as exc_info:
        parse_trait_preferences(raw)
    assert _codes(exc_info) == {"duplicate_trait"}

    raw = _body()["traits"]
    raw[0]["dimension_key"] = "salary"
    with pytest.raises(TraitPreferenceError) as exc_info:
        parse_trait_preferences(raw)
    assert "unknown_trait" in _codes(exc_info)


def test_must_have_must_be_a_real_boolean():
    raw = _body()["traits"]
    raw[0]["must_have"] = 1

    with pytest.raises(TraitPreferenceError) as exc_info:
        parse_trait_preferences(raw)

    assert _codes(exc_info) == {"invalid_type"}


# ── The store (D-01 doorway) ───────────────────────────────────────────────


def test_a_user_who_never_answered_gets_all_six_unanswered(client, seed_user):
    from app import app
    from assessment_store import get_trait_preferences
    from model import db

    seed_user(8101)
    with app.app_context():
        prefs = get_trait_preferences(db, 8101)

    assert set(prefs) == set(TRAIT_KEYS)
    for pref in prefs.values():
        assert pref.answered is False
        assert pref.under_steps is None and pref.over_steps is None
        assert pref.must_have is False
    assert flat_zones(prefs) is None


def test_latest_sitting_wins_and_earlier_sittings_are_kept(client, seed_user):
    from app import app
    from assessment_store import (
        export_person_side,
        get_trait_preferences,
        save_trait_preferences,
    )
    from model import db

    seed_user(8201, 8202)
    with app.app_context():
        first = save_trait_preferences(db, 8201, _answered(under=0, over=0, must=("pace",)))
        db.session.commit()
        second = save_trait_preferences(db, 8201, _answered(under=2, over=1, must=("decision",)))
        db.session.commit()
        save_trait_preferences(db, 8202, _answered(under=0, over=0))
        db.session.commit()

        prefs = get_trait_preferences(db, 8201)
        exported = export_person_side(8201)["trait_preferences"]

    assert first != second and len(second) == 32
    assert all(p.answered for p in prefs.values())
    assert {(p.under_steps, p.over_steps) for p in prefs.values()} == {(2, 1)}
    assert must_have_keys(prefs) == {"decision"}
    # Both sittings are still held, six rows each, oldest first.
    assert [row["sitting_id"] for row in exported] == [first] * 6 + [second] * 6
    assert {row["form_version"] for row in exported} == {"tp-v1-2026-10-13"}


def test_the_store_refuses_three_must_haves_without_writing(client, seed_user):
    from app import app
    from assessment_store import get_trait_preferences, save_trait_preferences
    from model import db

    seed_user(8301)
    with app.app_context():
        with pytest.raises(TraitPreferenceError):
            save_trait_preferences(
                db, 8301, _answered(must=("pace", "decision", "feedback"))
            )
        db.session.rollback()
        assert flat_zones(get_trait_preferences(db, 8301)) is None


# ── GET / PUT /me/trait-preferences ────────────────────────────────────────


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns its CSRF token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    email = "trait-prefs@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Trait User",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def _put(client, body, csrf):
    return client.put(URL, json=body, headers={"X-CSRF-TOKEN": csrf})


def test_get_requires_a_session(client):
    assert client.get(URL).status_code == 401


def test_put_requires_a_session(client):
    assert client.put(URL, json=_body()).status_code == 401


def test_put_requires_the_csrf_header(client, auth):
    resp = client.put(URL, json=_body())

    assert resp.status_code in (401, 403)


def test_get_for_a_fresh_account_is_unanswered(client, auth):
    from solverah.schemas.assessments import TraitPreferencesDocument

    resp = client.get(URL)

    assert resp.status_code == 200
    body = resp.get_json()
    TraitPreferencesDocument.model_validate(body)
    assert body["answered"] is False
    assert body["max_must_haves"] == 2
    assert [t["dimension_key"] for t in body["traits"]] == list(TRAIT_KEYS)
    assert all(
        t == {"dimension_key": t["dimension_key"], "under_steps": None,
              "over_steps": None, "must_have": False, "answered": False}
        for t in body["traits"]
    )


def test_put_saves_and_get_reads_it_back(client, auth):
    from solverah.schemas.assessments import TraitPreferencesDocument

    resp = _put(client, _body(under=0, over=2, must=("pace", "feedback")), auth)

    assert resp.status_code == 200
    saved = resp.get_json()
    TraitPreferencesDocument.model_validate(saved)
    assert saved["answered"] is True
    assert client.get(URL).get_json() == saved
    pace = next(t for t in saved["traits"] if t["dimension_key"] == "pace")
    assert pace == {"dimension_key": "pace", "under_steps": 0, "over_steps": 2,
                    "must_have": True, "answered": True}


def test_a_second_put_replaces_what_get_returns(client, auth):
    _put(client, _body(under=0, over=0, must=("pace",)), auth)
    _put(client, _body(under=2, over=2), auth)

    body = client.get(URL).get_json()

    assert {(t["under_steps"], t["over_steps"], t["must_have"]) for t in body["traits"]} == {
        (2, 2, False)
    }


def _problem_codes(resp):
    return {e["code"] for e in resp.get_json().get("errors", [])}


def test_three_must_haves_is_a_typed_400(client, auth):
    resp = _put(client, _body(must=("pace", "feedback", "decision")), auth)

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["type"].endswith("/invalid_trait_preferences")
    assert _problem_codes(resp) == {"too_many_must_haves"}
    # Nothing was written.
    assert client.get(URL).get_json()["answered"] is False


@pytest.mark.parametrize("bad", [3, -1])
def test_steps_out_of_range_is_a_typed_400(client, auth, bad):
    body = _body()
    body["traits"][2]["under_steps"] = bad

    resp = _put(client, body, auth)

    assert resp.status_code == 400
    assert _problem_codes(resp) == {"steps_out_of_range"}


def test_a_missing_trait_is_a_typed_400(client, auth):
    body = _body()
    body["traits"] = body["traits"][:5]

    resp = _put(client, body, auth)

    assert resp.status_code == 400
    assert _problem_codes(resp) == {"missing_trait"}


def test_a_body_that_does_not_match_the_schema_is_the_house_422(client, auth):
    resp = _put(client, {"traits": [{"dimension_key": "pace"}]}, auth)

    assert resp.status_code == 422
