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


# ── industry (PRODUCT_DECISIONS.md §2, 2026-10-01) ───────────────────────────


def _post_env_with(client, csrf, **extra):
    body = {"answers": _env_answers("mixed"), "stage_size": 3, "comp": 3, "experienced": 3}
    body.update(extra)
    return client.post(
        "/api/v1/me/environment-report", json=body, headers={"X-CSRF-TOKEN": csrf}
    )


def _stored_report(email):
    from app import app
    from model import User
    import environment_report_store
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        return environment_report_store.latest_environment_report(user.id)


def test_industry_is_stored_and_echoed(client, monkeypatch):
    email = "a5_industry@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    submit = _post_env_with(client, csrf, industry="finance")

    assert submit.status_code == 200
    assert submit.get_json()["industry"] == "finance"
    assert submit.get_json()["version"] == situation_items.FORM_VERSION
    stored = _stored_report(email)
    assert stored["industry"] == "finance"
    assert stored["version"] == situation_items.FORM_VERSION


@pytest.mark.parametrize("omit", [True, False], ids=["absent", "explicit-null"])
def test_industry_not_sure_stores_null(client, monkeypatch, omit):
    """An explicit null (the form's "not sure / prefer not to say") and an
    absent key both store NULL, the same way comp's "not sure" does."""
    email = "a5_industry_null_%s@example.com" % ("absent" if omit else "null")
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    submit = _post_env_with(client, csrf) if omit else _post_env_with(client, csrf, industry=None)

    assert submit.status_code == 200
    assert submit.get_json()["industry"] is None
    assert _stored_report(email)["industry"] is None


@pytest.mark.parametrize("bad", ["crypto", "Tech", 3])
def test_industry_outside_the_levels_is_rejected_and_nothing_is_stored(client, monkeypatch, bad):
    email = "a5_industry_bad_%s@example.com" % str(bad).lower()
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    res = _post_env_with(client, csrf, industry=bad)

    assert res.status_code in (400, 422)
    assert _stored_report(email) is None


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


# ── Past-job report (PRODUCT_DECISIONS.md §2, Sebastian, 2026-10-01) ─────────


def _submit_past(client, csrf, pole="high", **extra):
    body = {
        "answers": _env_answers(pole),
        "stage_size": 2,
        "comp": 2,
        "experienced": 2,
        "subject": "past",
    }
    body.update(extra)
    return client.post(
        "/api/v1/me/environment-report", json=body, headers={"X-CSRF-TOKEN": csrf}
    )


def _history(email):
    from app import app
    from model import User
    import environment_report_store

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        return environment_report_store.environment_report_history(user.id)


def test_current_submit_echoes_subject_current(client, monkeypatch):
    email = "past_current_echo@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    explicit = _post_env_with(client, csrf, subject="current")
    implicit = _submit_env(client, csrf)

    from solverah.schemas.situation_report import EnvironmentReportSubmitResponse

    for res in (explicit, implicit):
        assert res.status_code == 200, res.get_json()
        assert res.get_json()["subject"] == "current"
        EnvironmentReportSubmitResponse.model_validate(res.get_json())
    assert [h["subject"] for h in _history(email)] == ["current", "current"]


@pytest.mark.parametrize("status", ["employed", "between_jobs"])
def test_past_submit_is_stored_as_past_with_the_filers_status(client, monkeypatch, status):
    email = "past_happy_%s@example.com" % status
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, status)
    assert _submit_env(client, csrf).status_code == 200

    res = _submit_past(client, csrf, industry="retail")

    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["subject"] == "past"
    assert body["career_status"] == status
    assert body["industry"] == "retail"
    assert body["dimension_scores"] == {d: 0.9 for d in situation_items.DIMENSIONS}
    from solverah.schemas.situation_report import EnvironmentReportSubmitResponse

    EnvironmentReportSubmitResponse.model_validate(body)

    history = _history(email)
    assert [h["subject"] for h in history] == ["past", "current"]
    assert history[0]["career_status"] == status
    # The latest report is still the current one.
    assert _stored_report(email)["subject"] == "current"
    assert _stored_report(email)["stage_size"] == 3


def test_past_submit_for_first_job_is_409_first_job_no_role(client, monkeypatch):
    email = "past_first_job@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "first_job")

    res = _submit_past(client, csrf)

    assert res.status_code == 409
    assert res.mimetype == "application/problem+json"
    assert res.get_json()["errors"][0]["code"] == "first_job_no_role"
    assert _history(email) == []


def test_past_submit_before_any_current_report_is_409_current_report_required(client, monkeypatch):
    email = "past_no_current@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    res = _submit_past(client, csrf)

    assert res.status_code == 409
    assert res.mimetype == "application/problem+json"
    assert res.get_json()["errors"][0] == {"field": "subject", "code": "current_report_required"}
    assert _history(email) == []


def test_second_past_submit_is_409_past_report_limit(client, monkeypatch):
    email = "past_limit@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    assert _submit_env(client, csrf).status_code == 200
    assert _submit_past(client, csrf).status_code == 200

    res = _submit_past(client, csrf, pole="low")

    assert res.status_code == 409
    assert res.mimetype == "application/problem+json"
    assert res.get_json()["errors"][0] == {"field": "subject", "code": "past_report_limit"}
    assert [h["subject"] for h in _history(email)] == ["past", "current"]
    # A current resubmission is still accepted after the past cap is reached.
    assert _submit_env(client, csrf).status_code == 200


@pytest.mark.parametrize("bad", ["previous", "Past", None, 1])
def test_bad_subject_is_422_and_nothing_is_stored(client, monkeypatch, bad):
    email = "past_bad_subject_%s@example.com" % str(bad).lower()
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    res = _post_env_with(client, csrf, subject=bad)

    assert res.status_code == 422
    assert _history(email) == []


def test_service_refuses_a_bad_subject_even_without_the_route_validator(client, monkeypatch):
    """The service reads the raw body; the route's schema is the first gate, this the second."""
    from app import app
    from model import User
    from solverah.services import situation_report_service as service

    email = "past_bad_subject_service@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        result = service.submit_environment_report(user, {"subject": "previous"})
    assert result.status == 400


# ── REGRESSION: a past report never changes the Situation Report ──────────────


def _report_without_flag(client):
    res = _get_report(client)
    assert res.status_code == 200
    body = res.get_json()
    flag = body.pop("past_job_report_filed")
    return body, flag


@pytest.mark.parametrize("status", ["employed", "between_jobs"])
def test_past_submit_leaves_the_situation_report_byte_identical_but_the_flag(
    client, monkeypatch, status
):
    email = "past_regression_%s@example.com" % status
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, status)
    _complete_core(client, csrf, pattern=_VARIED)
    _submit_env(client, csrf, pole="mixed")

    before_raw = _get_report(client).get_data()
    before, before_flag = _report_without_flag(client)
    assert before["state"] == "complete"
    assert before_flag is False

    # Deliberately a different pole everywhere, so a leak would move every dimension.
    assert _submit_past(client, csrf, pole="low").status_code == 200

    after_raw = _get_report(client).get_data()
    after, after_flag = _report_without_flag(client)
    assert after_flag is True
    assert after == before
    assert b'"past_job_report_filed":false' in before_raw
    assert after_raw == before_raw.replace(
        b'"past_job_report_filed":false', b'"past_job_report_filed":true'
    )


def test_past_job_report_filed_is_present_in_every_state(client, monkeypatch):
    email = "past_flag_states@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    body = _get_report(client).get_json()
    assert body["state"] == "needs_core" and body["past_job_report_filed"] is False

    _submit_env(client, csrf)
    _submit_past(client, csrf)
    body = _get_report(client).get_json()
    assert body["state"] == "needs_core" and body["past_job_report_filed"] is True
    # needs_core echoes the CURRENT report's scores (mixed), never the past one's (high).
    assert {d["env_score"] for d in body["environment"]["dimensions"]} == {0.5}

    from solverah.schemas.situation_report import SituationReportResponse

    SituationReportResponse.model_validate(body)


def test_past_job_report_filed_in_needs_environment_report_state(client, monkeypatch):
    email = "past_flag_needs_env@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)

    body = _get_report(client).get_json()
    assert body["state"] == "needs_environment_report"
    assert body["past_job_report_filed"] is False


def test_export_carries_subject_on_every_environment_report(client, monkeypatch):
    email = "past_export@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _submit_env(client, csrf)
    _submit_past(client, csrf)

    res = client.get("/api/v1/me/export")

    assert res.status_code == 200
    payload = res.get_json()
    assert [r["subject"] for r in payload["environment_reports"]] == ["past", "current"]
    from solverah.schemas.account import AccountExportResponse

    AccountExportResponse.model_validate(payload)


# -- F1 (audit 2026-10-02): a career-status change after filing reaches the user --


@pytest.mark.parametrize(
    "filed_as, now, flagged",
    [
        ("employed", "between_jobs", True),
        ("between_jobs", "employed", True),
        # first_job maps to the past tense, but it has no role to describe: the
        # form gates it and the submit 409s, so a banner would be a dead end
        # that could never clear. Not flagged.
        ("employed", "first_job", False),
    ],
)
def test_career_status_tense_change_after_filing_is_flagged(
    client, monkeypatch, filed_as, now, flagged
):
    """The report renders from the career_status snapshot, so a status change in
    either tense direction was invisible. The flag reaches the payload; the
    report itself is NOT re-sliced (banner-only, 2026-10-02)."""
    email = "f1_%s_to_%s@example.com" % (filed_as, now)
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, filed_as)
    _complete_core(client, csrf)
    assert _submit_env(client, csrf, pole="low").status_code == 200

    before = _get_report(client).get_json()
    assert before["career_status_changed"] is False

    _set_career_status(client, csrf, now)
    after = _get_report(client).get_json()

    assert after["state"] == "complete"
    assert after["career_status_changed"] is flagged
    # Banner only: the old report still renders from its own snapshot.
    assert after["career_status"] == filed_as
    assert after["needs_forward"] == before["needs_forward"]
    assert after["dimensions"] == before["dimensions"]


def test_resubmitting_after_a_career_status_change_clears_the_flag(client, monkeypatch):
    email = "f1_resubmit@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    assert _submit_env(client, csrf).status_code == 200
    _set_career_status(client, csrf, "between_jobs")
    assert _get_report(client).get_json()["career_status_changed"] is True

    assert _submit_env(client, csrf).status_code == 200

    body = _get_report(client).get_json()
    assert body["career_status_changed"] is False
    assert body["career_status"] == "between_jobs"
    assert body["needs_forward"] is True


# -- F2 (audit 2026-10-02): an unreadable pinned sitting is a state, not a 500 --


def test_pin_to_a_sitting_with_no_responses_is_needs_core_unreadable_not_500(
    client, monkeypatch
):
    email = "f2_unknown_pin@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    assert _submit_env(client, csrf).status_code == 200

    from app import app
    from model import User, db
    import situation_report_pin_store

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        situation_report_pin_store.set_pin(db, user.id, "0" * 32)
        db.session.commit()

    res = _get_report(client)

    assert res.status_code == 200, res.get_data()
    body = res.get_json()
    assert body["state"] == "needs_core"
    assert body["core_unreadable"] is True
    assert {d["env_score"] for d in body["environment"]["dimensions"]} == {0.5}
    from solverah.schemas.situation_report import SituationReportResponse

    SituationReportResponse.model_validate(body)


def test_scores_with_no_core_submission_row_is_needs_core_unreadable_not_500(
    client, monkeypatch
):
    """Person-side scores of the current instrument with no `core` submission row
    behind them, so the default pin resolves to None -- e.g. a sitting recorded
    before submission rows existed."""
    email = "f2_no_submission@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    assert _submit_env(client, csrf).status_code == 200

    from app import app
    from model import AssessmentSubmission, User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        AssessmentSubmission.query.filter_by(user_id=user.id, kind="core").delete()
        db.session.commit()

    res = _get_report(client)

    assert res.status_code == 200, res.get_data()
    body = res.get_json()
    assert body["state"] == "needs_core"
    assert body["core_unreadable"] is True


def test_plain_needs_core_carries_no_core_unreadable_flag(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="f2_plain@example.com")
    _set_career_status(client, csrf, "employed")
    body = _get_report(client).get_json()
    assert body["state"] == "needs_core" and "core_unreadable" not in body


# -- F9 (audit 2026-10-02): two racing past submits file exactly one report --


def _someone_waits_on_a_lock(engine):
    import sqlalchemy as sa

    with engine.connect() as connection:
        return (
            connection.execute(
                sa.text(
                    # Joined through pg_stat_activity: a row-lock waiter waits on a
                    # `transactionid` lock, whose `database` column is NULL.
                    "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                    "WHERE NOT l.granted AND a.datname = current_database()"
                )
            ).scalar()
            > 0
        )


def test_two_interleaved_past_submits_file_exactly_one_past_report(client, monkeypatch):
    """`_check_past_report_allowed` takes a row lock on the user before counting.
    The first submit is held open after its INSERT, before its commit; the second
    then runs. Without the lock the second counts zero past reports (the first is
    uncommitted), writes, and the user ends with two. With it, the second waits
    at the lock, then counts the first and refuses with `past_report_limit`. The
    interleaving is driven, not raced: the first is released only once the second
    has finished or is seen waiting in `pg_locks`."""
    import threading
    import time

    import environment_report_store
    from app import app
    from model import User, db
    from solverah.errors import ConflictError
    from solverah.services import situation_report_service

    email = "f9_race@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    assert _submit_env(client, csrf).status_code == 200
    with app.app_context():
        user_id = User.query.filter_by(email=email).first().id
        engine = db.engine

    real_write = environment_report_store.write_environment_report
    first_wrote = threading.Event()
    release_first = threading.Event()

    def write_then_hold_the_first(*args, **kwargs):
        real_write(*args, **kwargs)
        if threading.current_thread().name == "first":
            first_wrote.set()
            release_first.wait(30)

    monkeypatch.setattr(
        environment_report_store, "write_environment_report", write_then_hold_the_first
    )

    payload = {
        "answers": _env_answers("high"),
        "stage_size": 2,
        "comp": 2,
        "experienced": 2,
        "subject": "past",
    }
    results, errors = {}, {}

    def submit():
        name = threading.current_thread().name
        try:
            with app.app_context():
                user = db.session.get(User, user_id)
                try:
                    results[name] = situation_report_service.submit_environment_report(
                        user, payload
                    )
                finally:
                    db.session.rollback()
                    db.session.remove()
        except Exception as exc:  # noqa: BLE001 -- asserted below
            errors[name] = exc

    first = threading.Thread(target=submit, name="first")
    second = threading.Thread(target=submit, name="second")
    first.start()
    try:
        assert first_wrote.wait(30), "the first past submit never reached its commit"
        second.start()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if "second" in results or "second" in errors or _someone_waits_on_a_lock(engine):
                break
            time.sleep(0.02)
    finally:
        release_first.set()
        first.join(30)
        if second.ident is not None:
            second.join(30)

    assert "first" not in errors, errors
    assert results["first"].status == 200
    assert isinstance(errors.get("second"), ConflictError), (results, errors)
    assert errors["second"].errors[0]["code"] == "past_report_limit"
    assert [h["subject"] for h in _history(email)] == ["past", "current"]


# -- The default pin under core retakes (2026-10-05) --------------------------
#
# With no explicit pin, the report reads the core sitting that was current when the
# user's FIRST current Environment Report was filed (the latest sitting at or before
# it, else the first one after it), falling forward past a default that can no
# longer be scored. `_UNIFORM` + a `mixed` environment is all-aligned; `_VARIED` is
# not, so "which sitting is the report built from" is visible in the buckets.


def _all_aligned(body):
    return body["state"] == "complete" and all(
        d["bucket"] == "aligned" for d in body["dimensions"]
    )


def _user_id(email):
    from app import app
    from model import User

    with app.app_context():
        return User.query.filter_by(email=email).first().id


def _persist_unscoreable_sitting(email):
    """A real `core` sitting row whose responses the CURRENT item file cannot score --
    a sitting from before an item-bank change -- under a superseded scoring key, so it
    also does not satisfy `has_completed_assessment`. Written through the one write
    path (`persist_submission`), not the tables. Returns its submission_id."""
    from app import app
    from model import db
    from assessment_form import ScoredSubmission
    from assessment_store import persist_submission

    dims = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
    sitting = ScoredSubmission(
        form_version="v2-2026-08-18",
        scoring_key_version="v1-superseded+mean_pole",
        scores={d: 0.5 for d in dims},
        choices={f"{d[:2]}{rung}v2": "A" for d in dims for rung in range(1, 5)},
        confidences={d: (None if d == "feedback" else 1.0) for d in dims},
    )
    user_id = _user_id(email)
    with app.app_context():
        submission_id = persist_submission(db, user_id, sitting)
        db.session.commit()
    return submission_id


def _resolved_pin(email):
    from app import app
    import assessment_store
    from solverah.services import situation_report_service

    user_id = _user_id(email)
    with app.app_context():
        return (
            situation_report_service._pinned_submission_id(user_id),
            [sid for sid, _ in assessment_store.completed_core_sittings(user_id)],
        )


def test_a_retake_before_filing_builds_the_report_from_the_newer_sitting(client, monkeypatch):
    """Regression: the default used to be the FIRST sitting, so a user who retook
    before ever filing got a report built from a sitting they had replaced."""
    email = "pin_retake_before@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)  # uniform: would be all-aligned
    _complete_core(client, csrf, pattern=_VARIED)
    assert _submit_env(client, csrf, pole="mixed").status_code == 200

    body = _get_report(client).get_json()
    assert body["state"] == "complete"
    assert not _all_aligned(body)

    pinned, sittings = _resolved_pin(email)
    assert len(sittings) == 2 and pinned == sittings[-1]

    # Already on the latest sitting, so Recalibrate has nothing to move. (Not compared
    # with a second user's report: the core form is shuffled per user, so one answer
    # pattern scores differently for two people.)
    recal = client.post(
        "/api/v1/me/situation-report/recalibrate", headers={"X-CSRF-TOKEN": csrf}
    )
    assert recal.get_json()["recalibrated"] is False
    assert _get_report(client).get_json() == body


def test_a_retake_after_filing_does_not_move_the_report_until_recalibrate(client, monkeypatch):
    email = "pin_retake_after@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    _complete_core(client, csrf, pattern=_VARIED)
    assert _submit_env(client, csrf, pole="mixed").status_code == 200
    filed = _get_report(client).get_json()
    assert not _all_aligned(filed)

    _complete_core(client, csrf)  # uniform again, after filing
    assert _get_report(client).get_json() == filed
    # Re-filing the Environment Report does not re-anchor the person side either.
    assert _submit_env(client, csrf, pole="mixed").status_code == 200
    assert _get_report(client).get_json()["dimensions"] == filed["dimensions"]
    pinned, sittings = _resolved_pin(email)
    assert len(sittings) == 3 and pinned == sittings[1]

    recal = client.post(
        "/api/v1/me/situation-report/recalibrate", headers={"X-CSRF-TOKEN": csrf}
    )
    assert recal.get_json()["recalibrated"] is True
    assert _all_aligned(_get_report(client).get_json())


def test_a_report_filed_before_any_core_sitting_pins_to_the_first_one_after_it(
    client, monkeypatch
):
    email = "pin_env_first@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    assert _submit_env(client, csrf, pole="mixed").status_code == 200
    _complete_core(client, csrf)  # the sitting that completed the report
    first = _get_report(client).get_json()
    assert _all_aligned(first)

    _complete_core(client, csrf, pattern=_VARIED)
    assert _get_report(client).get_json() == first


@pytest.mark.parametrize("env_first", [False, True], ids=["core-then-env", "env-then-core"])
def test_a_single_sitting_resolves_exactly_as_before(client, monkeypatch, env_first):
    """No change for one-sitting users: the default is the only sitting, i.e. what
    `first_completed_core_submission_id` (the old default) names."""
    from app import app
    import assessment_store

    email = f"pin_single_{int(env_first)}@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    if env_first:
        assert _submit_env(client, csrf, pole="mixed").status_code == 200
    _complete_core(client, csrf, pattern=_VARIED)
    if not env_first:
        assert _submit_env(client, csrf, pole="mixed").status_code == 200

    pinned, sittings = _resolved_pin(email)
    with app.app_context():
        assert pinned == assessment_store.first_completed_core_submission_id(_user_id(email))
    assert sittings == [pinned]
    assert _get_report(client).get_json()["state"] == "complete"


def test_an_unreadable_default_falls_forward_to_the_next_readable_sitting(client, monkeypatch):
    """Regression: a first sitting the current item file cannot score used to leave
    the report `core_unreadable` even after a readable retake. An unseen default
    protects nothing, so it falls forward -- and stays put once it has."""
    email = "pin_fall_forward@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    old = _persist_unscoreable_sitting(email)
    assert _submit_env(client, csrf, pole="mixed").status_code == 200  # anchors on `old`
    assert _get_report(client).get_json()["state"] == "needs_core"

    _complete_core(client, csrf, pattern=_VARIED)
    body = _get_report(client).get_json()
    assert body["state"] == "complete", body
    assert "core_unreadable" not in body
    assert not _all_aligned(body)
    pinned, sittings = _resolved_pin(email)
    assert sittings[0] == old and pinned == sittings[1]

    _complete_core(client, csrf)  # a later retake does not drag it further
    assert _get_report(client).get_json() == body


def test_an_explicit_pin_to_an_unreadable_sitting_still_gates(client, monkeypatch):
    """Fall-forward is for the default only: a pin the user chose is never second-
    guessed, and Recalibrate is its exit."""
    email = "pin_explicit_unreadable@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    old = _persist_unscoreable_sitting(email)
    _complete_core(client, csrf, pattern=_VARIED)
    assert _submit_env(client, csrf, pole="mixed").status_code == 200
    assert _get_report(client).get_json()["state"] == "complete"

    from app import app
    from model import db
    import situation_report_pin_store

    with app.app_context():
        situation_report_pin_store.set_pin(db, _user_id(email), old)
        db.session.commit()

    body = _get_report(client).get_json()
    assert body["state"] == "needs_core"
    assert body["core_unreadable"] is True

    recal = client.post(
        "/api/v1/me/situation-report/recalibrate", headers={"X-CSRF-TOKEN": csrf}
    )
    assert recal.get_json()["recalibrated"] is True
    assert _get_report(client).get_json()["state"] == "complete"


# ── Tolerance and must-haves (PRODUCT_DECISIONS.md §2, "The six-trait match
# model", 2026-10-13). Gap convention in the report: gap = env - person. ─────


def _put_trait_preferences(client, csrf, steps=None, must=()):
    """PUT /me/trait-preferences (C1's route): every trait at 0/0 unless *steps*
    names it as (under_steps, over_steps)."""
    from work_pulse.situation import DIMENSIONS

    steps = steps or {}
    resp = client.put(
        "/api/v1/me/trait-preferences",
        json={
            "traits": [
                {
                    "dimension_key": dim,
                    "under_steps": steps.get(dim, (0, 0))[0],
                    "over_steps": steps.get(dim, (0, 0))[1],
                    "must_have": dim in must,
                }
                for dim in DIMENSIONS
            ]
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200, resp.get_json()


def _complete_with_every_gap_over_by_point_four(client, monkeypatch, email):
    """Core answered uniformly (every person score 0.5) and every environment
    item at the `high` pole (0.9): six gaps of +0.4, all OVER, all straining
    under today's thresholds."""
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    assert set(_person_scores(email).values()) == {0.5}, "fixture precondition"
    assert _submit_env(client, csrf, pole="high").status_code == 200
    return csrf


def test_unanswered_tolerance_leaves_the_report_as_it_was(client, monkeypatch):
    """No tolerance sitting: today's buckets, and every new flag false."""
    csrf = _complete_with_every_gap_over_by_point_four(client, monkeypatch, "c4_unanswered@example.com")
    del csrf

    body = _get_report(client).get_json()

    assert body["state"] == "complete"
    assert body["tolerance_applied"] is False
    assert [d["bucket"] for d in body["dimensions"]] == ["straining"] * 6
    assert all(d["must_have"] is False for d in body["dimensions"])
    assert all(d["within_tolerance"] is False for d in body["dimensions"])


def test_unanswered_report_is_byte_identical_to_one_built_without_the_tolerance_read(
    client, monkeypatch
):
    """The service's tolerance read changes nothing for a user who never
    answered: the same response as a run where the read is replaced by a
    hard-coded "unanswered"."""
    from solverah.domain.trait_preferences import unanswered_preferences

    email = "c4_unanswered_bytes@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf, pattern=_VARIED)
    _submit_env_by_dimension(client, csrf, {"autonomy": "high", "pace": "low", "decision": "leaning_low"})

    live = _get_report(client)
    with monkeypatch.context() as patched:
        patched.setattr(
            "assessment_store.get_trait_preferences",
            lambda _db, _user_id: unanswered_preferences(),
        )
        forced = _get_report(client)

    assert live.status_code == forced.status_code == 200
    assert live.get_data() == forced.get_data()


def test_a_two_step_over_tolerance_puts_a_point_four_gap_in_aligned(client, monkeypatch):
    csrf = _complete_with_every_gap_over_by_point_four(client, monkeypatch, "c4_zone@example.com")
    # Two steps MORE pace is fine (over zone 0.5); two steps LESS autonomy is
    # fine, which says nothing about an OVER gap (over zone stays 0.15).
    _put_trait_preferences(client, csrf, steps={"pace": (0, 2), "autonomy": (2, 0)})

    body = _get_report(client).get_json()
    by_dim = {d["dimension"]: d for d in body["dimensions"]}

    assert body["tolerance_applied"] is True
    assert by_dim["pace"]["bucket"] == "aligned"
    assert by_dim["pace"]["direction"] is None
    assert by_dim["pace"]["within_tolerance"] is True
    assert "aligned_note" in by_dim["pace"]
    assert by_dim["autonomy"]["bucket"] == "straining"
    assert by_dim["autonomy"]["within_tolerance"] is False
    # The aligned row sorts below every straining one.
    assert body["dimensions"][-1]["dimension"] == "pace"


def test_a_must_have_ranks_first_within_its_tier(client, monkeypatch):
    csrf = _complete_with_every_gap_over_by_point_four(client, monkeypatch, "c4_must@example.com")

    before = [d["dimension"] for d in _get_report(client).get_json()["dimensions"]]
    last = before[-1]
    _put_trait_preferences(client, csrf, must=(last,))

    body = _get_report(client).get_json()
    after = [d["dimension"] for d in body["dimensions"]]

    assert after[0] == last
    assert after[1:] == [d for d in before if d != last]
    assert [d["rank"] for d in body["dimensions"]] == list(range(6))
    assert [d["must_have"] for d in body["dimensions"]] == [True] + [False] * 5


def test_tolerance_report_still_carries_no_person_side_number(client, monkeypatch):
    """D-15 holds with tolerance on: the new fields are booleans, nothing else."""
    csrf = _complete_with_every_gap_over_by_point_four(client, monkeypatch, "c4_d15@example.com")
    _put_trait_preferences(client, csrf, steps={"pace": (0, 2)}, must=("feedback",))

    body = _get_report(client).get_json()

    for key, value in _walk(body):
        assert "person" not in key.lower()
        assert "gap" not in key.lower()
        assert "zone" not in key.lower()
        # `under_steps` / `over_steps` (the stated tolerance) never echo back.
        # Bare `steps` is the change_in_place register's guidance list.
        assert "_steps" not in key.lower()
    for dim in body["dimensions"]:
        assert isinstance(dim["must_have"], bool)
        assert isinstance(dim["within_tolerance"], bool)


def test_needs_forward_report_with_tolerance_still_drops_aligned_rows(client, monkeypatch):
    email = "c4_needs_forward@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "between_jobs")
    _complete_core(client, csrf)
    assert _submit_env(client, csrf, pole="high").status_code == 200
    _put_trait_preferences(client, csrf, steps={"pace": (0, 2)}, must=("decision",))

    body = _get_report(client).get_json()

    assert body["needs_forward"] is True
    dims = [d["dimension"] for d in body["dimensions"]]
    assert "pace" not in dims
    assert dims[0] == "decision"
    assert body["dimensions"][0]["must_have"] is True


# ── The five optional exploratory outcomes (PRODUCT_DECISIONS.md §2, 2026-10-13) ──

_OUTCOMES = {
    "satisfaction": 4,
    "performance": 5,
    "engagement": 2,
    "sustainability": 1,
    "retention_intention": 3,
}


def test_outcomes_are_stored_raw_and_echoed(client, monkeypatch):
    email = "c4_outcomes@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    submit = _post_env_with(client, csrf, **_OUTCOMES)

    assert submit.status_code == 200, submit.get_json()
    body = submit.get_json()
    assert body["version"] == "env-v3-2026-10-13"
    for item_id, value in _OUTCOMES.items():
        assert body[item_id] == value
    stored = _stored_report(email)
    for item_id, column in situation_items.OUTCOME_COLUMNS.items():
        assert stored[column] == _OUTCOMES[item_id], column
    assert stored["experienced_outcome"] == 3


def test_outcomes_are_optional_absent_and_null_both_store_null(client, monkeypatch):
    email = "c4_outcomes_skipped@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    submit = _post_env_with(client, csrf, satisfaction=None, engagement=5)

    assert submit.status_code == 200, submit.get_json()
    body = submit.get_json()
    assert body["satisfaction"] is None
    assert body["performance"] is None  # absent
    assert body["engagement"] == 5
    stored = _stored_report(email)
    assert stored["outcome_satisfaction"] is None
    assert stored["outcome_performance"] is None
    assert stored["outcome_engagement"] == 5


@pytest.mark.parametrize("bad", [0, 6, "3", True])
def test_out_of_range_outcome_is_rejected_and_nothing_is_stored(client, monkeypatch, bad):
    email = "c4_outcomes_bad_%s@example.com" % str(bad).lower()
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")

    res = _post_env_with(client, csrf, sustainability=bad)

    assert res.status_code in (400, 422)
    assert _stored_report(email) is None


@pytest.mark.parametrize("bad", [0, 6, "3", True, 2.0])
def test_service_refuses_a_bad_outcome_even_without_the_route_validator(client, monkeypatch, bad):
    """The service reads the raw body; the route's schema is the first gate, this the second."""
    from app import app
    from model import User
    from solverah.services import situation_report_service as service

    email = "c4_outcomes_service_%s@example.com" % str(bad).lower().replace(".", "_")
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    body = {
        "answers": _env_answers("mixed"), "stage_size": 3, "comp": 3, "experienced": 3,
        "retention_intention": bad,
    }
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        result = service.submit_environment_report(user, body)
    assert result.status == 400
    assert "retention_intention" in result.body["error"]
    assert _stored_report(email) is None


def test_outcomes_on_a_past_tense_report_are_stored(client, monkeypatch):
    """A between_jobs user's current report renders past tense; the stored
    outcomes do not depend on tense."""
    email = "c4_outcomes_between@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "between_jobs")

    submit = _post_env_with(client, csrf, **_OUTCOMES)

    assert submit.status_code == 200, submit.get_json()
    stored = _stored_report(email)
    assert stored["career_status"] == "between_jobs"
    assert stored["outcome_retention_intention"] == 3


def test_outcomes_on_a_past_job_report_are_stored_on_that_row(client, monkeypatch):
    email = "c4_outcomes_past@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    assert _post_env_with(client, csrf).status_code == 200

    res = _submit_past(client, csrf, satisfaction=2, sustainability=5)

    assert res.status_code == 200, res.get_json()
    past = next(r for r in _history(email) if r["subject"] == "past")
    current = next(r for r in _history(email) if r["subject"] == "current")
    assert past["outcome_satisfaction"] == 2
    assert past["outcome_sustainability"] == 5
    assert past["outcome_performance"] is None
    assert current["outcome_satisfaction"] is None


def test_outcomes_never_change_the_situation_report(client, monkeypatch):
    """Exploratory only: re-filing the same description with outcome answers
    leaves the report byte-identical. (One user, not two: the core form is
    shuffled per user, so reports are never compared across users.)"""
    email = "c4_outcomes_report@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf, pattern=_VARIED)
    assert _post_env_with(client, csrf).status_code == 200
    without = _get_report(client).get_data()

    assert _post_env_with(client, csrf, satisfaction=1, engagement=1, retention_intention=5).status_code == 200
    with_outcomes = _get_report(client).get_data()

    assert with_outcomes == without
