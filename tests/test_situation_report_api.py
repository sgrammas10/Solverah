"""POST /me/environment-report, GET /me/situation-report,
POST /me/situation-report/recalibrate (BUILD_PLAN A-5).

Person-side sittings are completed through the real, shuffled, token-based `core`
form -- the same path a real respondent takes (`test_agent_api.py`'s pattern) --
rather than a hand-built result dict, so the pin/re-derivation machinery
(`assessment_form.score_stored_choices`, `assessment_store.dimension_scores_for_submission`)
is exercised end to end. Reading the resulting person-side scores back through
`assessment_store.get_dimension_scores` (the sanctioned doorway, D-01) is what lets a
test choose environment answers that land a dimension in a known bucket, deterministically.
"""

from __future__ import annotations

import pytest

from work_pulse import situation_items


@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="a5@example.com", password="Strongpass1!"):
    # Only email sending is stubbed. `log_audit_event` stays real -- the recalibrate
    # tests assert a real `AuditLog` row, and monkeypatching it here (as
    # test_manager_playbook_api.py does, for a suite that never checks it) would
    # silently swallow every audit write for the rest of the test, not just
    # registration's.
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": email, "password": password, "name": "A5 User",
            "role": "job-seeker", "terms_accepted": True,
        },
    )

    from app import app
    from model import User, db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def _set_career_status(client, csrf, status):
    resp = client.patch(
        "/api/v1/me/career-status",
        json={"status": status},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200, resp.get_json()


#: Every `core` item offers exactly two options, and their two positions are
#: balanced against the underlying pole per item (the same positional-key-balance
#: rule `manager_profile.py` and `situation_items.py` both document) -- so
#: consistently picking "the first option" for all 24 items lands every dimension
#: dead on 0.5, and so does consistently picking "the second". A retake needs a
#: genuinely different answer PATTERN, not just a different fixed index, to score
#: differently; `_UNIFORM`/`_VARIED` are two such patterns, empirically distinct
#: (verified against a real form: uniform -> flat 0.5 on all six dimensions,
#: varied -> {0.0, 0.25, 0.5, 0.75} spread).
_UNIFORM = lambda i: 0  # noqa: E731
_VARIED = lambda i: 1 if i % 3 == 0 else 0  # noqa: E731


def _complete_core(client, csrf, pattern=_UNIFORM):
    """Complete one `core` sitting through the real form, choosing each item's
    option by *pattern(running_item_index)* -- see `_UNIFORM`/`_VARIED` above."""
    form = client.get("/api/v1/assessments/core/form")
    assert form.status_code == 200
    responses = {}
    i = 0
    for block in form.get_json()["blocks"]:
        for item in block["items"]:
            idx = pattern(i) % len(item["options"])
            responses[item["token"]] = item["options"][idx]["key"]
            i += 1
    resp = client.post(
        "/api/v1/assessments/core/submissions",
        json={"responses": responses},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200, resp.get_json()
    return resp


def _person_scores(email):
    from app import app
    from model import User
    import assessment_store

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        return assessment_store.get_dimension_scores(user.id)


def _env_answers(pole="mixed"):
    """A valid {item_id: option_key} for all twelve environment items, every one
    of them landing on *pole* -- so `score_environment` returns *pole*'s POLE_VALUES
    number, uniformly, for every dimension."""
    answers = {}
    for item in situation_items.ENVIRONMENT_ITEMS:
        option = next(o for o in item["options"] if o["pole"] == pole)
        answers[item["item_id"]] = option["key"]
    return answers


def _submit_env(client, csrf, pole="mixed", stage_size=3, comp=3, experienced=3, employer_name=None):
    body = {
        "answers": _env_answers(pole),
        "stage_size": stage_size,
        "comp": comp,
        "experienced": experienced,
    }
    if employer_name is not None:
        body["employer_name"] = employer_name
    return client.post(
        "/api/v1/me/environment-report",
        json=body,
        headers={"X-CSRF-TOKEN": csrf},
    )


def _env_answers_by_dimension(poles: dict[str, str], default: str = "mixed") -> dict:
    """A valid {item_id: option_key} where each dimension lands on its own pole
    from *poles*, and every other dimension on *default* -- so a fixture can put
    the widest divergence on whichever dimension it wants, which `_env_answers`
    (one pole for all six) structurally cannot.
    """
    answers = {}
    for item in situation_items.ENVIRONMENT_ITEMS:
        pole = poles.get(item["dimension"], default)
        option = next(o for o in item["options"] if o["pole"] == pole)
        answers[item["item_id"]] = option["key"]
    return answers


def _submit_env_by_dimension(client, csrf, poles: dict[str, str]):
    return client.post(
        "/api/v1/me/environment-report",
        json={
            "answers": _env_answers_by_dimension(poles),
            "stage_size": 3,
            "comp": 3,
            "experienced": 3,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )


def _get_report(client):
    return client.get("/api/v1/me/situation-report")


def _walk(value):
    """Yield every (key, value) pair anywhere in a nested JSON structure."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


# ── State: neither core nor environment report ──────────────────────────────


def test_neither_core_nor_environment_report_is_needs_core_with_no_environment(client, monkeypatch):
    email = "a5_neither@example.com"
    _register_and_login(client, monkeypatch, email=email)

    res = _get_report(client)

    assert res.status_code == 200
    body = res.get_json()
    assert body["state"] == "needs_core"
    assert body["environment"] is None
    assert body["manager"] == {"has_profile": False}


# ── State: environment report alone, no core yet ────────────────────────────


def test_environment_alone_echoes_dimension_scores_with_no_gap(client, monkeypatch):
    email = "a5_env_only@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    submit = _submit_env(client, csrf, pole="high")
    assert submit.status_code == 200
    assert submit.get_json()["comp"] == 3

    res = _get_report(client)

    assert res.status_code == 200
    body = res.get_json()
    assert body["state"] == "needs_core"
    env = body["environment"]
    assert env["career_status"] == "employed"
    assert {d["dimension"] for d in env["dimensions"]} == set(situation_items.DIMENSIONS)
    for entry in env["dimensions"]:
        assert entry["env_score"] == pytest.approx(0.9)  # "high" pole
    # D-15: no bucket/gap/person data belongs in a report with no core sitting yet.
    for key, _value in _walk(body):
        assert "person" not in key.lower()
        assert "gap" not in key.lower()
        assert "bucket" not in key.lower()


# ── State: core alone, no environment report ────────────────────────────────


def test_core_alone_prompts_for_the_environment_report(client, monkeypatch):
    email = "a5_core_only@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _complete_core(client, csrf)

    res = _get_report(client)

    assert res.status_code == 200
    body = res.get_json()
    assert body["state"] == "needs_environment_report"
    assert body["can_submit_environment_report"] is True
    assert body["manager"] == {"has_profile": False}


# ── first_job: refused from the environment form, told apart in the prompt ──


def test_first_job_is_refused_from_submitting_an_environment_report(client, monkeypatch):
    email = "a5_first_job_submit@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "first_job")

    res = _submit_env(client, csrf)

    assert res.status_code == 409
    assert res.mimetype == "application/problem+json"
    assert res.get_json()["errors"][0]["code"] == "first_job_no_role"


def test_first_job_core_only_state_cannot_submit_environment_report(client, monkeypatch):
    email = "a5_first_job_core@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "first_job")
    _complete_core(client, csrf)

    res = _get_report(client)

    assert res.status_code == 200
    body = res.get_json()
    assert body["state"] == "needs_environment_report"
    assert body["can_submit_environment_report"] is False


# ── State: both -- the full report ───────────────────────────────────────────


def test_both_complete_state_has_ranked_dimensions_and_guidance(client, monkeypatch):
    email = "a5_both@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    _submit_env(client, csrf, pole="mixed")

    res = _get_report(client)

    assert res.status_code == 200
    body = res.get_json()
    assert body["state"] == "complete"
    assert body["career_status"] == "employed"
    assert body["needs_forward"] is False
    assert "guidance_notice" in body and body["guidance_notice"]
    assert body["manager"] == {"has_profile": False}

    seen_dims = {d["dimension"] for d in body["dimensions"]}
    assert seen_dims <= set(situation_items.DIMENSIONS)
    for entry in body["dimensions"]:
        assert entry["bucket"] in ("aligned", "notable", "straining")
        if entry["bucket"] == "aligned":
            assert entry["direction"] is None
            assert "aligned_note" in entry
        else:
            assert entry["direction"] in ("under", "over")
            assert "diagnosis" in entry and "text" in entry["diagnosis"]
            assert "registers" in entry


# ── Rank order, and the elicited weights behind it ───────────────────────────


def test_dimensions_reach_the_client_in_rank_order(client, monkeypatch):
    """The ranking has to survive the trip to the browser.

    `build_situation_report` computes a `rank` and then returns rows in fixed
    `DIMENSIONS` order; both frontends render the list in the order they
    receive it and neither sorts. So unless the service emits them ranked,
    every user sees autonomy first forever, whatever their answers say.

    The fixture deliberately puts the widest divergence on `decision`, the
    LAST dimension in `DIMENSIONS` -- a fixture whose rank order happens to
    match document order passes this vacuously.
    """
    email = "a5_rankorder@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)  # uniform pattern -> 0.5 on all six
    resp = _submit_env_by_dimension(
        client,
        csrf,
        # env 0.9 vs person 0.5 -> |gap| 0.40, straining
        # env 0.7 vs person 0.5 -> |gap| 0.20, notable
        {"decision": "high", "innovation": "leaning_high"},
    )
    assert resp.status_code == 200, resp.get_json()

    body = _get_report(client).get_json()
    assert body["state"] == "complete"

    order = [d["dimension"] for d in body["dimensions"]]
    ranks = [d["rank"] for d in body["dimensions"]]

    assert order[0] == "decision", (
        "the widest divergence did not lead the list; got %r" % (order,)
    )
    assert order[1] == "innovation", order
    assert all(a < b for a, b in zip(ranks, ranks[1:])), (
        "ranks are not strictly increasing down the payload: %r" % (ranks,)
    )


def test_service_ranks_on_the_live_elicited_weights() -> None:
    """The service must rank on what `causal_graph/v1_model/priors.yaml`
    actually says today, so a re-elicitation reaches the report by editing
    that file and nothing else.

    Compares against an independent read of the YAML rather than against the
    same loader the service uses -- otherwise both sides could drift together
    and the test would still pass. Means only: the `sd` records how sure the
    expert was and has no say in which mismatch is listed first.
    """
    import yaml

    from solverah.services.situation_report_service import _dimension_weights
    from work_pulse.situation import DIMENSIONS

    with open("causal_graph/v1_model/priors.yaml", encoding="ascii") as handle:
        priors = yaml.safe_load(handle)["dimensions"]

    weights = _dimension_weights()

    assert set(weights) == set(DIMENSIONS)
    for dim in DIMENSIONS:
        assert weights[dim]["mag"] == pytest.approx(priors[dim]["mag"]["mean"]), dim
        assert weights[dim]["dir"] == pytest.approx(priors[dim]["dir"]["mean"]), dim
        # The invariant `work_pulse.situation.dimension_cost` refuses to break:
        # a cheap direction can cancel the penalty but never outrun it.
        assert abs(weights[dim]["dir"]) <= abs(weights[dim]["mag"]), dim


# ── D-15 structural payload discipline ───────────────────────────────────────


def test_complete_report_never_carries_person_side_score_or_numeric_gap(client, monkeypatch):
    email = "a5_structural@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    _submit_env(client, csrf, pole="low")  # far from any plausible person score

    body = _get_report(client).get_json()
    assert body["state"] == "complete"

    person_scores = _person_scores(email)

    for key, value in _walk(body):
        assert "person" not in key.lower(), key
        assert "gap" not in key.lower(), key
        assert "magnitude" not in key.lower(), key
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            # No float anywhere in the payload may equal a real person-side score --
            # the only floats allowed are env_score echoes (0.1 here, "low" pole).
            for score in person_scores.values():
                if abs(value - score) < 1e-9:
                    assert value == pytest.approx(0.1), (
                        "a person-side score value leaked into the payload: %r" % value
                    )


# ── Needs-forward slicing (past-tense career_status) ─────────────────────────


def test_between_jobs_needs_forward_slicing_drops_aligned_and_suppresses_negotiate(
    client, monkeypatch
):
    from work_pulse import situation_content

    email = "a5_between_jobs@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "between_jobs")
    _complete_core(client, csrf)
    # "low" on every dimension all but guarantees every non-degenerate person score
    # lands >= NOTABLE away from it, so nothing should be aligned by chance.
    _submit_env(client, csrf, pole="low")

    body = _get_report(client).get_json()
    assert body["state"] == "complete"
    assert body["career_status"] == "between_jobs"
    assert body["needs_forward"] is True

    assert body["dimensions"], "expected at least one non-aligned dimension to assert on"
    for entry in body["dimensions"]:
        assert entry["bucket"] != "aligned"  # A-6b: aligned rows are dropped entirely
        assert "negotiate" not in entry["registers"]
        assert entry["decoder_crossref"] is None
        if "change_in_place" in entry["registers"]:
            assert set(entry["registers"]["change_in_place"]) == {"signal"}
        # The diagnosis text served is the needs_forward rendering, not current_role.
        direction_word = situation_content.direction_for_bucket(entry["bucket"], entry["direction"])
        expected = situation_content.DIAGNOSES[(entry["dimension"], direction_word)]["needs_forward"]
        assert entry["diagnosis"]["text"] == expected


# ── Retakes do not move the report; recalibrate does, and logs ──────────────


def test_core_retake_without_recalibrate_leaves_the_report_byte_identical(client, monkeypatch):
    email = "a5_retake@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)  # uniform -> flat 0.5 on every dimension
    _submit_env(client, csrf, pole="mixed")  # env 0.5 too: every dimension aligned

    before = _get_report(client).get_json()

    _complete_core(client, csrf, pattern=_VARIED)  # a real retake, genuinely different scores

    after = _get_report(client).get_json()

    assert before == after


def test_recalibrate_moves_the_report_and_logs_the_action(client, monkeypatch):
    email = "a5_recalibrate@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)  # uniform -> flat 0.5 on every dimension
    _submit_env(client, csrf, pole="mixed")  # env 0.5 too: every dimension aligned
    before = _get_report(client).get_json()
    assert all(d["bucket"] == "aligned" for d in before["dimensions"])

    _complete_core(client, csrf, pattern=_VARIED)  # {0, 0.25, 0.5, 0.75} spread
    unmoved = _get_report(client).get_json()
    assert unmoved == before

    recal = client.post(
        "/api/v1/me/situation-report/recalibrate", headers={"X-CSRF-TOKEN": csrf}
    )
    assert recal.status_code == 200
    assert recal.get_json()["recalibrated"] is True

    after = _get_report(client).get_json()
    assert after != before

    from app import app
    from model import AuditLog, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        rows = AuditLog.query.filter_by(
            actor_user_id=user.id, action="situation_report_recalibrate"
        ).count()
        assert rows == 1


def test_recalibrate_is_idempotent_when_already_pinned_to_latest(client, monkeypatch):
    email = "a5_recal_idempotent@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    _submit_env(client, csrf, pole="mixed")

    first = client.post(
        "/api/v1/me/situation-report/recalibrate", headers={"X-CSRF-TOKEN": csrf}
    )
    assert first.status_code == 200
    assert first.get_json()["recalibrated"] is False  # already pinned to the only sitting

    second = client.post(
        "/api/v1/me/situation-report/recalibrate", headers={"X-CSRF-TOKEN": csrf}
    )
    assert second.get_json()["recalibrated"] is False

    from app import app
    from model import AuditLog, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        rows = AuditLog.query.filter_by(
            actor_user_id=user.id, action="situation_report_recalibrate"
        ).count()
        assert rows == 0


def test_recalibrate_before_any_core_sitting_is_409(client, monkeypatch):
    email = "a5_recal_no_core@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)

    res = client.post(
        "/api/v1/me/situation-report/recalibrate", headers={"X-CSRF-TOKEN": csrf}
    )

    assert res.status_code == 409
    assert res.get_json()["errors"][0]["code"] == "no_core_sitting"


# ── comp's "not sure" NULL, round-tripped ────────────────────────────────────


def test_comp_not_sure_round_trips_as_null(client, monkeypatch):
    email = "a5_comp_null@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    submit = _submit_env(client, csrf, comp=None)

    assert submit.status_code == 200
    assert submit.get_json()["comp"] is None

    from app import app
    from model import User
    import environment_report_store
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        stored = environment_report_store.latest_environment_report(user.id)
        assert stored["comp"] is None


# ── Pulse-event resubmission prompt (BUILD_PLAN B-4) ─────────────────────────


def _log_pulse_event(client, csrf, event_type="new_manager", note=None):
    body = {"event_type": event_type}
    if note is not None:
        body["note"] = note
    resp = client.post(
        "/api/v1/me/pulse/events", json=body, headers={"X-CSRF-TOKEN": csrf}
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _backdate_latest_environment_report(email, minutes=60):
    """Push the latest environment report's `submitted_at` into the past, so a
    Pulse event logged afterward with the real clock is unambiguously newer --
    without this, two requests close enough together in a fast test run could
    land within the same timestamp precision and make the ordering a coin flip
    rather than a fact about the code under test."""
    import datetime as dt

    from app import app
    from model import EnvironmentReport, User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        report = (
            EnvironmentReport.query.filter_by(user_id=user.id)
            .order_by(EnvironmentReport.submitted_at.desc(), EnvironmentReport.id.desc())
            .first()
        )
        report.submitted_at = report.submitted_at - dt.timedelta(minutes=minutes)
        db.session.commit()


def _setup_complete_report(client, csrf, email):
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    _submit_env(client, csrf, pole="mixed")


def test_events_since_report_is_empty_with_nothing_logged(client, monkeypatch):
    email = "b4_no_events@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _setup_complete_report(client, csrf, email)

    body = _get_report(client).get_json()

    assert body["state"] == "complete"
    assert body["events_since_report"] == []


def test_events_since_report_excludes_events_logged_before_submission(client, monkeypatch):
    email = "b4_events_before@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    # Logged, then the environment report is submitted afterward -- this event
    # is history the report already accounts for, not a reason to resurface it.
    _log_pulse_event(client, csrf, event_type="new_manager")
    _submit_env(client, csrf, pole="mixed")

    body = _get_report(client).get_json()

    assert body["state"] == "complete"
    assert body["events_since_report"] == []


def test_events_since_report_includes_events_logged_after_submission(client, monkeypatch):
    email = "b4_events_after@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _setup_complete_report(client, csrf, email)
    _backdate_latest_environment_report(email)

    logged = _log_pulse_event(client, csrf, event_type="new_manager")

    body = _get_report(client).get_json()

    assert body["state"] == "complete"
    assert body["events_since_report"] == [
        {"type": "new_manager", "date": logged["at"]}
    ]


def test_events_since_report_orders_newest_first(client, monkeypatch):
    email = "b4_events_order@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _setup_complete_report(client, csrf, email)
    _backdate_latest_environment_report(email)

    first = _log_pulse_event(client, csrf, event_type="reorg")
    second = _log_pulse_event(client, csrf, event_type="new_manager")

    body = _get_report(client).get_json()

    assert body["events_since_report"] == [
        {"type": "new_manager", "date": second["at"]},
        {"type": "reorg", "date": first["at"]},
    ]


def test_events_since_report_never_carries_note_text(client, monkeypatch):
    email = "b4_no_note_leak@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _setup_complete_report(client, csrf, email)
    _backdate_latest_environment_report(email)

    secret_note = "a private detail only this user typed"
    _log_pulse_event(client, csrf, event_type="other", note=secret_note)

    resp = _get_report(client)
    body = resp.get_json()

    assert body["events_since_report"] == [
        {"type": "other", "date": body["events_since_report"][0]["date"]}
    ]
    assert set(body["events_since_report"][0]) == {"type", "date"}
    assert secret_note not in resp.get_data(as_text=True)


# ── Malformed answers ─────────────────────────────────────────────────────


def test_missing_environment_items_is_400(client, monkeypatch):
    email = "a5_missing_items@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    answers = _env_answers("mixed")
    del answers["env-autonomy-1"]

    res = client.post(
        "/api/v1/me/environment-report",
        json={"answers": answers, "stage_size": 3, "comp": 3, "experienced": 3},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert res.status_code == 400


def test_unknown_option_key_is_400(client, monkeypatch):
    email = "a5_bad_option@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    answers = _env_answers("mixed")
    answers["env-autonomy-1"] = "z"

    res = client.post(
        "/api/v1/me/environment-report",
        json={"answers": answers, "stage_size": 3, "comp": 3, "experienced": 3},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert res.status_code == 400


def test_out_of_range_stage_size_is_rejected(client, monkeypatch):
    email = "a5_bad_stage_size@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    res = client.post(
        "/api/v1/me/environment-report",
        json={"answers": _env_answers("mixed"), "stage_size": 9, "comp": 3, "experienced": 3},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert res.status_code in (400, 422)


# ── Auth ──────────────────────────────────────────────────────────────────


def test_environment_report_submit_unauthenticated(client):
    """A schema-valid body, so the 401 comes from `@jwt_required()` rather than
    from `enforce=True`'s body validation, which runs first (matches
    `assessments.py`'s `_sync_kind_or_410` precedent: refusal before auth)."""
    body = {
        "answers": _env_answers("mixed"), "stage_size": 3, "comp": 3, "experienced": 3,
    }
    res = client.post("/api/v1/me/environment-report", json=body)
    assert res.status_code == 401


def test_situation_report_get_unauthenticated(client):
    res = client.get("/api/v1/me/situation-report")
    assert res.status_code == 401


def test_recalibrate_unauthenticated(client):
    res = client.post("/api/v1/me/situation-report/recalibrate")
    assert res.status_code == 401


# ── Rate limit ────────────────────────────────────────────────────────────


def test_environment_report_submit_is_limited_to_five_per_minute(client, monkeypatch):
    """Matches `solverah/api/v1/assessments.py`'s `DEFAULT_SUBMISSION_LIMIT` shape."""
    from app import app
    from solverah.extensions import limiter

    email = "a5_rate_limit@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    limiter.reset()
    app.config["TESTING"] = False
    try:
        statuses = [_submit_env(client, csrf).status_code for _ in range(6)]
    finally:
        app.config["TESTING"] = True
        limiter.reset()

    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429
