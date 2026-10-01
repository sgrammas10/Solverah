"""E-4: `environment_reports` rows -> causal-model training rows.

`causal_graph/v1_model/assemble_training_data.assemble_environment_training_data`
is the DB->model glue BUILD_PLAN §5 asks for. These tests are pure data: no
PyTensor compile, no `pm.sample`, no fit. They exist to prove the JOIN is right,
because everything downstream inherits it silently if it is not.

Rows are produced through the real routes -- the shuffled, token-based `core`
form and `POST /me/environment-report` -- rather than hand-built, for the reason
`test_situation_report_api.py` gives: the pin and the re-derivation
(`assessment_form.score_stored_choices`) are the machinery under test, and a
hand-built score dict would step straight over both.

THE ONE THAT MATTERS
--------------------
`test_core_retake_does_not_move_the_person_side` is A-5's load-bearing lesson
carried into the model lane. The person-side score table is upserted in place
per (user, dimension, scoring key version), so reading it for a pinned sitting
returns a plausible six-dimension dict that describes the WRONG sitting after
any retake. That test asserts the assembled person side stays put while
`assessment_store.get_dimension_scores` -- the obvious thing to have read --
moves.

A NOTE ON HOW THAT TABLE IS NAMED HERE
---------------------------------------
Never by its real name, in prose or anywhere else. `test_employer_visibility.py`
(D-01) walks every .py file in the repo and matches the two person-side table
names inside string constants as well as identifiers -- docstrings included --
because raw SQL and `__tablename__` strings would otherwise slip past an
import-based check. This file is not on that allowlist and does not want to be:
it reaches person-side data only through `assessment_store`, which is exactly
what the rule asks for, and a file whose only offence is a docstring should be
reworded rather than granted an exemption that would then cover real access too.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path

import pytest
import yaml

from model import ENV_DIMENSIONS
from work_pulse import situation_items

_V1_MODEL = Path(__file__).resolve().parents[1] / "causal_graph" / "v1_model"
if str(_V1_MODEL) not in sys.path:
    sys.path.insert(0, str(_V1_MODEL))

import assemble_training_data as atd  # noqa: E402

_SCHEMA_SQL = _V1_MODEL / "schema.sql"
_MODEL_CONFIG = _V1_MODEL / "solverah_model_config.yaml"


def _cfg() -> dict:
    """The REAL `solverah_model_config.yaml`, not a stub. It is the documented
    single source of truth for which dimensions and confounders exist, and a
    test that supplied its own would stop noticing when the two disagree."""
    return yaml.safe_load(_MODEL_CONFIG.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    # Read at call time in assessment_store.respondent_id_for_user, with no
    # default by design (D-05). Deliberately not in tests/conftest.py --
    # test_assessment_form.py proves the no-default rule by deleting it.
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


def _noop(*_args, **_kwargs):
    return None


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _register_and_login(client, monkeypatch, email, password="Strongpass1!"):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": email, "password": password, "name": "E4 User",
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
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["csrfToken"]


def _set_career_status(client, csrf, status):
    resp = client.patch(
        "/api/v1/me/career-status",
        json={"status": status},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200, resp.get_json()


#: Every `core` item offers two options whose positions are balanced against the
#: underlying pole, so answering "first option" throughout lands every dimension
#: dead on 0.5 -- and so does "second option" throughout. A retake therefore
#: needs a different answer PATTERN, not a different fixed index, to score
#: differently. Both patterns are `test_situation_report_api.py`'s, verified
#: there against a real form (uniform -> flat 0.5; varied -> a real spread).
_UNIFORM = lambda i: 0  # noqa: E731
_VARIED = lambda i: 1 if i % 3 == 0 else 0  # noqa: E731

#: What `_UNIFORM` scores, by hand: a balanced two-option item contributes one
#: pole at each position, so the mean over four items is the midpoint exactly.
_UNIFORM_PERSON_SCORE = 0.5


def _complete_core(client, csrf, pattern=_UNIFORM):
    form = client.get("/api/v1/assessments/core/form")
    assert form.status_code == 200
    responses = {}
    index = 0
    for block in form.get_json()["blocks"]:
        for item in block["items"]:
            choice = pattern(index) % len(item["options"])
            responses[item["token"]] = item["options"][choice]["key"]
            index += 1
    resp = client.post(
        "/api/v1/assessments/core/submissions",
        json={"responses": responses},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200, resp.get_json()


#: One pole per dimension item, chosen so every dimension lands on a DIFFERENT,
#: hand-checkable number -- a uniform environment would let a transposed
#: dimension pass unnoticed.
#:
#:   POLE_VALUES:  low .1 · leaning_low .3 · mixed .5 · leaning_high .7 · high .9
#:   score_environment: the mean of that dimension's two items.
_ENV_PLAN = {
    "env-autonomy-1": "high",           # (0.9 + 0.9) / 2
    "env-autonomy-2": "high",
    "env-pace-1": "low",                # (0.1 + 0.1) / 2
    "env-pace-2": "low",
    "env-collaboration-1": "leaning_high",   # (0.7 + 0.3) / 2
    "env-collaboration-2": "leaning_low",
    "env-feedback-1": "mixed",          # (0.5 + 0.5) / 2
    "env-feedback-2": "mixed",
    "env-innovation-1": "high",         # (0.9 + 0.3) / 2
    "env-innovation-2": "leaning_low",
    "env-decision-1": "low",            # (0.1 + 0.7) / 2
    "env-decision-2": "leaning_high",
}

_EXPECTED_ENV = {
    "autonomy": 0.9,
    "pace": 0.1,
    "collaboration": 0.5,
    "feedback": 0.5,
    "innovation": 0.6,
    "decision": 0.4,
}


def _answers_from_plan(plan=None):
    """{item_id: option_key} for all twelve dimension items.

    Resolves each planned POLE to that item's option key rather than a position:
    A-1 balances anchor order within every dimension (one item ascending, one
    descending), so a positional answer means different things on the two items
    and the hand arithmetic above would be wrong.
    """
    plan = _ENV_PLAN if plan is None else plan
    answers = {}
    for item in situation_items.ENVIRONMENT_ITEMS:
        pole = plan[item["item_id"]]
        answers[item["item_id"]] = next(
            o["key"] for o in item["options"] if o["pole"] == pole
        )
    return answers


def _post_env(
    client,
    csrf,
    *,
    plan=None,
    stage_size=4,
    comp=2,
    experienced=5,
    employer_name=None,
    industry=None,
):
    payload = {
        "answers": _answers_from_plan(plan),
        "stage_size": stage_size,
        "comp": comp,
        "industry": industry,
        "experienced": experienced,
    }
    if employer_name is not None:
        payload["employer_name"] = employer_name
    return client.post(
        "/api/v1/me/environment-report",
        json=payload,
        headers={"X-CSRF-TOKEN": csrf},
    )


def _assemble(**kwargs):
    """Run the real assembler over the app database.

    A fresh `Connection` rather than the ORM session: this is the shape an
    offline fit run has, and it is what proves the function needs no Flask
    application context of its own beyond one to reach the engine.
    """
    from app import app
    from model import db

    with app.app_context():
        with db.engine.connect() as conn:
            return atd.assemble_environment_training_data(conn, _cfg(), **kwargs)


def _person_scores_from_the_store(email):
    """What the person-side score table currently holds, read through the
    sanctioned doorway. It is the thing a pinned read must NOT be built on;
    used here only to prove that it and the assembled person side diverge."""
    import assessment_store
    from app import app
    from model import User

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        return assessment_store.get_dimension_scores(user.id)


# ---------------------------------------------------------------------------
# The seeded end-to-end row
# ---------------------------------------------------------------------------


def test_one_report_becomes_one_row_with_hand_computed_values(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, "e4_row@example.com")
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf, _UNIFORM)
    assert _post_env(
        client, csrf, stage_size=4, comp=2, experienced=5, employer_name="  Acme Co  "
    ).status_code == 200

    result = _assemble()

    assert result.dropped == []
    assert len(result.rows) == 1
    assert result.outcome_type == "experienced"

    # --- env side: A-3's scores, as stored, unrescaled ---------------------
    for dimension, expected in _EXPECTED_ENV.items():
        assert result.env[dimension][0] == pytest.approx(expected), dimension

    # --- person side: the pinned sitting, re-derived -----------------------
    for dimension in ENV_DIMENSIONS:
        assert result.person[dimension][0] == pytest.approx(_UNIFORM_PERSON_SCORE)
    # With no retake yet, the stored table happens to agree. That agreement is
    # what test_core_retake_does_not_move_the_person_side destroys on purpose.
    assert _person_scores_from_the_store("e4_row@example.com") == pytest.approx(
        {d: _UNIFORM_PERSON_SCORE for d in ENV_DIMENSIONS}
    )

    # --- confounders: RAW 1..5, not standardized ---------------------------
    # 4 and 2, not (4-3)/1.5 and (2-3)/1.0. build_model.preprocess_conf owns the
    # standardizing; doing it here would apply it twice at fit time.
    assert result.conf["stage_size"][0] == 4.0
    assert result.conf["comp"][0] == 2.0
    assert not result.conf_missing["stage_size"][0]
    assert not result.conf_missing["comp"][0]

    # `industry` is asked since 2026-10-01 but optional; this row answered
    # "not sure" (NULL), so the column carries an explicit None with its mask
    # set -- never a silent omission, and never a guessed level.
    assert result.unsupplied_confounders == ()
    assert result.conf["industry"][0] is None
    assert bool(result.conf_missing["industry"][0]) is True

    # --- outcome: the ordinal 1..5, as an integer --------------------------
    assert result.outcome[0] == 5
    assert result.outcome.dtype.kind == "i"

    # --- provenance --------------------------------------------------------
    row = result.rows[0]
    assert row.capture_path == atd.CAPTURE_PATH == "self_report_environment"
    assert row.outcome_source == atd.OUTCOME_SOURCE == "environment_report"
    assert row.pin_source == atd.PIN_FIRST_CORE
    assert row.career_status == "employed"
    assert row.env_form_version == situation_items.FORM_VERSION
    assert row.report_ordinal == 1
    assert row.report_count_for_user == 1
    assert row.employer_name_normalized == "acme co"  # pre-normalized by A-5
    assert row.person_submission_id and len(row.person_submission_id) == 32
    assert row.person_form_version
    assert row.person_scoring_key_version


# ---------------------------------------------------------------------------
# industry: unmasked when answered, masked exactly as before when NULL
# ---------------------------------------------------------------------------


def _match_core():
    import match_core  # causal_graph/v1_model is on sys.path (see the import above)

    return match_core


def test_an_answered_industry_is_unmasked_at_its_own_level(client, monkeypatch):
    """PRODUCT_DECISIONS.md §2, 2026-10-01. A row that names its industry
    carries the RAW level key (preprocess_conf owns the indexing), its mask is
    clear, and after preprocessing it indexes its own level with
    `industry__present` = 1 -- while a NULL row beside it stays masked at the
    placeholder with `industry__present` = 0."""
    for email, industry in (
        ("e4_ind_health@example.com", "healthcare"),
        ("e4_ind_null@example.com", None),
        ("e4_ind_retail@example.com", "retail"),
    ):
        csrf = _register_and_login(client, monkeypatch, email)
        _set_career_status(client, csrf, "employed")
        _complete_core(client, csrf)
        assert _post_env(client, csrf, industry=industry).status_code == 200

    result = _assemble()
    assert result.dropped == []
    assert len(result.rows) == 3
    assert result.unsupplied_confounders == ()

    assert list(result.conf["industry"]) == ["healthcare", None, "retail"]
    assert result.conf_missing["industry"].tolist() == [False, True, False]

    cfg = _cfg()
    levels = next(c for c in cfg["confounders"] if c["key"] == "industry")["levels"]
    out = _match_core().preprocess_conf(result.conf, cfg, conf_missing=result.conf_missing)
    assert out["industry"].tolist() == [levels.index("healthcare"), 0, levels.index("retail")]
    assert out["industry__present"].tolist() == [1.0, 0.0, 1.0]


def test_a_null_industry_row_is_bit_identical_to_the_never_asked_path(client, monkeypatch):
    """The masked path must not move. Assemble the same NULL-industry rows
    twice: once as the code is, once with `industry` taken back out of
    ENVIRONMENT_CONFOUNDER_COLUMNS (the pre-2026-10-01 'never asked' path).
    Every array, raw and preprocessed, must be byte-for-byte the same. Only
    `unsupplied_confounders` may differ, because the instrument now asks it."""
    import numpy as np

    for email in ("e4_bit_a@example.com", "e4_bit_b@example.com"):
        csrf = _register_and_login(client, monkeypatch, email)
        _set_career_status(client, csrf, "employed")
        _complete_core(client, csrf)
        assert _post_env(client, csrf, industry=None).status_code == 200

    now = _assemble()
    old_columns = {k: v for k, v in atd.ENVIRONMENT_CONFOUNDER_COLUMNS.items() if k != "industry"}
    monkeypatch.setattr(atd, "ENVIRONMENT_CONFOUNDER_COLUMNS", old_columns)
    before = _assemble()

    assert now.unsupplied_confounders == ()
    assert before.unsupplied_confounders == ("industry",)

    def _same(a, b):
        assert a.dtype == b.dtype and a.shape == b.shape
        if a.dtype == object:
            assert list(a) == list(b)
        else:
            assert a.tobytes() == b.tobytes()

    for group in ("person", "env", "conf", "conf_missing"):
        assert list(getattr(now, group)) == list(getattr(before, group)), group
        for key in getattr(now, group):
            _same(getattr(now, group)[key], getattr(before, group)[key])
    _same(now.outcome, before.outcome)

    cfg = _cfg()
    pre_now = _match_core().preprocess_conf(now.conf, cfg, conf_missing=now.conf_missing)
    pre_before = _match_core().preprocess_conf(before.conf, cfg, conf_missing=before.conf_missing)
    assert list(pre_now) == list(pre_before)
    for key in pre_now:
        _same(np.asarray(pre_now[key]), np.asarray(pre_before[key]))
    assert pre_now["industry__present"].tolist() == [0.0, 0.0]


def test_every_unsuppliable_funnel_field_is_an_explicit_null(client, monkeypatch):
    """BUILD_PLAN §5: "funnel/collider fields carried per the handoff (capture
    how each pair entered the data)". Nothing selected this pair, so every
    selection field is NULL -- and NULL is the finding, not a gap."""
    csrf = _register_and_login(client, monkeypatch, "e4_funnel@example.com")
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    assert _post_env(client, csrf).status_code == 200

    row = _assemble().rows[0]
    for field_name in atd.UNSUPPLIED_FUNNEL_FIELDS:
        assert getattr(row, field_name) is None, field_name
    # `funnel_actions` is None rather than [] on purpose: an empty list claims
    # "we watched the funnel and nothing happened", which is a different fact.
    assert row.funnel_actions is None
    assert row.match_formed is None


def test_capture_notes_cover_every_row_field():
    """The inventory is data, not prose, so a field added to the row without a
    capture note fails here instead of shipping undocumented."""
    field_names = {f.name for f in dataclasses.fields(atd.EnvironmentTrainingRow)}
    assert field_names == set(atd.FUNNEL_FIELD_CAPTURE_NOTES)
    assert set(atd.UNSUPPLIED_FUNNEL_FIELDS) <= field_names

    defaults = {
        f.name: f.default for f in dataclasses.fields(atd.EnvironmentTrainingRow)
    }
    for name in atd.UNSUPPLIED_FUNNEL_FIELDS:
        assert defaults[name] is None, name


# ---------------------------------------------------------------------------
# comp: the "not sure" ruling, carried
# ---------------------------------------------------------------------------


def test_comp_not_sure_is_carried_as_null_and_not_imputed(client, monkeypatch):
    """PRODUCT_DECISIONS.md §2 (2026-09-10): "not sure" stores a real absence
    rather than a guessed 1..5. Whether the fit excludes the term or models the
    missingness is the model config's call, and it can only make that call if
    the row arrives honest about it."""
    csrf = _register_and_login(client, monkeypatch, "e4_comp@example.com")
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    assert _post_env(client, csrf, comp=None).status_code == 200

    result = _assemble()

    # Carried, not dropped: a missing confounder is not a missing row.
    assert result.dropped == []
    assert len(result.rows) == 1

    import numpy as np

    assert np.isnan(result.conf["comp"][0])
    assert bool(result.conf_missing["comp"][0]) is True

    # Specifically NOT the config's `scale.mean` for comp, which is what a
    # well-meaning imputation would reach for.
    comp_scale = next(
        c for c in _cfg()["confounders"] if c["key"] == "comp"
    )["scale"]["mean"]
    assert comp_scale == 3.0
    assert result.conf["comp"][0] != comp_scale

    # The rest of the row is untouched by the NULL.
    assert result.conf["stage_size"][0] == 4.0
    assert result.outcome[0] == 5


# ---------------------------------------------------------------------------
# The pin
# ---------------------------------------------------------------------------


def test_core_retake_does_not_move_the_person_side(client, monkeypatch):
    """⚑5's default pin is the FIRST completed core sitting, and a retake is not
    a recalibration. The person-side score table is upserted in place, so it
    moves; the training row must not."""
    email = "e4_retake@example.com"
    csrf = _register_and_login(client, monkeypatch, email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf, _UNIFORM)
    assert _post_env(client, csrf).status_code == 200

    before = _assemble()
    first_submission_id = before.rows[0].person_submission_id

    _complete_core(client, csrf, _VARIED)  # a retake, with no recalibrate

    stored_now = _person_scores_from_the_store(email)
    assert stored_now != pytest.approx({d: _UNIFORM_PERSON_SCORE for d in ENV_DIMENSIONS}), (
        "the retake did not actually change the stored scores, so this test "
        "would pass for the wrong reason"
    )

    after = _assemble()
    assert len(after.rows) == 1
    assert after.rows[0].person_submission_id == first_submission_id
    assert after.rows[0].pin_source == atd.PIN_FIRST_CORE
    for dimension in ENV_DIMENSIONS:
        assert after.person[dimension][0] == pytest.approx(_UNIFORM_PERSON_SCORE)
        assert after.person[dimension][0] == pytest.approx(before.person[dimension][0])

    # The whole point, said out loud: reading the obvious table would have
    # produced a different, wrong, entirely plausible row.
    assert any(
        after.person[d][0] != pytest.approx(stored_now[d]) for d in ENV_DIMENSIONS
    )


def test_explicit_recalibrate_moves_the_person_side(client, monkeypatch):
    """The override half of ⚑5: an explicit re-pin is the ONE thing that moves
    the sealed person side, and the assembled row follows it."""
    email = "e4_repin@example.com"
    csrf = _register_and_login(client, monkeypatch, email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf, _UNIFORM)
    assert _post_env(client, csrf).status_code == 200
    _complete_core(client, csrf, _VARIED)

    before = _assemble()

    resp = client.post(
        "/api/v1/me/situation-report/recalibrate",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["recalibrated"] is True

    after = _assemble()
    assert len(after.rows) == 1
    assert after.rows[0].pin_source == atd.PIN_EXPLICIT
    assert after.rows[0].person_submission_id != before.rows[0].person_submission_id

    stored_now = _person_scores_from_the_store(email)
    for dimension in ENV_DIMENSIONS:
        assert after.person[dimension][0] == pytest.approx(stored_now[dimension])

    # The environment side did not move -- only the pin did.
    for dimension, expected in _EXPECTED_ENV.items():
        assert after.env[dimension][0] == pytest.approx(expected)


def test_pin_resolution_agrees_with_the_situation_report_service(client, monkeypatch):
    """The tripwire for the one thing this module restates rather than calls.

    `_resolve_pinned_submissions` is SQL in the model lane;
    `situation_report_service._pinned_submission_id` is the app's own resolver.
    Two descriptions of one rule drift, so assert the agreement instead of
    documenting it -- across all three states the rule has.
    """
    from app import app
    from model import User, db
    from solverah.services import situation_report_service

    # (a) no core at all, (b) core + retake, no override, (c) explicit re-pin.
    csrf_a = _register_and_login(client, monkeypatch, "e4_pin_a@example.com")
    _set_career_status(client, csrf_a, "employed")
    assert _post_env(client, csrf_a).status_code == 200

    csrf_b = _register_and_login(client, monkeypatch, "e4_pin_b@example.com")
    _set_career_status(client, csrf_b, "employed")
    _complete_core(client, csrf_b, _UNIFORM)
    _complete_core(client, csrf_b, _VARIED)
    assert _post_env(client, csrf_b).status_code == 200

    csrf_c = _register_and_login(client, monkeypatch, "e4_pin_c@example.com")
    _set_career_status(client, csrf_c, "employed")
    _complete_core(client, csrf_c, _UNIFORM)
    _complete_core(client, csrf_c, _VARIED)
    assert _post_env(client, csrf_c).status_code == 200
    assert client.post(
        "/api/v1/me/situation-report/recalibrate", headers={"X-CSRF-TOKEN": csrf_c}
    ).status_code == 200

    emails = [
        "e4_pin_a@example.com",
        "e4_pin_b@example.com",
        "e4_pin_c@example.com",
    ]
    with app.app_context():
        user_ids = [User.query.filter_by(email=e).first().id for e in emails]
        expected = {
            uid: situation_report_service._pinned_submission_id(uid) for uid in user_ids
        }
        with db.engine.connect() as conn:
            resolved = atd._resolve_pinned_submissions(conn, user_ids)

    assert {uid: value[0] for uid, value in resolved.items()} == {
        uid: sid for uid, sid in expected.items() if sid is not None
    }
    # The state the service returns None for is the state with no row here.
    assert [uid for uid, sid in expected.items() if sid is None] == [user_ids[0]]
    assert user_ids[0] not in resolved
    assert resolved[user_ids[1]][1] == atd.PIN_FIRST_CORE
    assert resolved[user_ids[2]][1] == atd.PIN_EXPLICIT


# ---------------------------------------------------------------------------
# What produces no row, and why
# ---------------------------------------------------------------------------


def test_core_without_an_environment_report_produces_no_row(client, monkeypatch):
    """A person side alone is not a training pair. No row, and no drop either --
    there was never a candidate to exclude."""
    csrf = _register_and_login(client, monkeypatch, "e4_core_only@example.com")
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)

    result = _assemble()

    assert result.rows == []
    assert result.dropped == []
    assert len(result.outcome) == 0
    # Shape survives emptiness: a consumer can still ask which columns exist.
    assert list(result.env) == list(ENV_DIMENSIONS)
    assert list(result.person) == list(ENV_DIMENSIONS)
    assert set(result.conf) == {"stage_size", "comp", "industry"}
    assert result.outcome.dtype.kind == "i"


def test_environment_report_without_core_is_dropped_with_a_named_reason(
    client, monkeypatch
):
    """A-5 serves this as the `needs_core` state: a real, complete environment
    report with no person side to pair it against. Recorded as a drop, not
    quietly absent -- a shrinking N nobody can account for is the bug this
    project's handoffs keep catching after the fact."""
    csrf = _register_and_login(client, monkeypatch, "e4_no_core@example.com")
    _set_career_status(client, csrf, "employed")
    assert _post_env(client, csrf).status_code == 200

    result = _assemble()

    assert result.rows == []
    assert len(result.dropped) == 1
    assert result.dropped[0]["reason"] == ["no_pinned_core_sitting"]
    assert result.dropped[0]["environment_report_id"] is not None


def test_first_job_users_have_no_environment_reports(client, monkeypatch):
    """Asserted rather than assumed (BUILD_PLAN A-1 Finding 7 / PRODUCT_DECISIONS
    §2, 2026-09-10): a never-employed user skips the form, so the route refuses.

    The second half proves the assembler does not depend on that refusal holding
    -- a `first_job` row written past it is dropped by name, because it may
    describe a job nobody ever had.
    """
    csrf = _register_and_login(client, monkeypatch, "e4_first_job@example.com")
    _set_career_status(client, csrf, "first_job")
    _complete_core(client, csrf)

    refused = _post_env(client, csrf)
    assert refused.status_code == 409, refused.get_json()
    assert refused.get_json()["errors"][0]["code"] == "first_job_no_role"
    assert _assemble().rows == []

    # Now write one anyway, straight through A-2's store, bypassing the route.
    from app import app
    from environment_report_store import write_environment_report
    from model import User, db
    from work_pulse import situation

    with app.app_context():
        user = User.query.filter_by(email="e4_first_job@example.com").first()
        write_environment_report(
            db,
            user.id,
            raw_answers=_answers_from_plan(),
            dimension_scores=situation.score_environment(
                _answers_from_plan(), situation_items.item_spec("first_job")
            ),
            stage_size=3,
            comp=3,
            experienced_outcome=4,
            career_status="first_job",
            version=situation_items.FORM_VERSION,
        )
        db.session.commit()

    result = _assemble()
    assert result.rows == []
    assert len(result.dropped) == 1
    assert result.dropped[0]["reason"] == ["career_status='first_job' is not trainable"]


def test_every_report_a_user_wrote_becomes_a_row_and_is_numbered(client, monkeypatch):
    """`environment_reports` is append-only and its history is the point (A-2's
    module docstring names E-4 for this). Repeated reports are not independent
    observations, so the ordinal rides along instead of the history being thrown
    away to avoid the problem."""
    csrf = _register_and_login(client, monkeypatch, "e4_history@example.com")
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf, _UNIFORM)

    assert _post_env(client, csrf, experienced=2).status_code == 200
    flipped = {item_id: "mixed" for item_id in _ENV_PLAN}
    assert _post_env(client, csrf, plan=flipped, experienced=4).status_code == 200

    result = _assemble()

    assert len(result.rows) == 2
    assert [r.report_ordinal for r in result.rows] == [1, 2]
    assert [r.report_count_for_user for r in result.rows] == [2, 2]
    assert list(result.outcome) == [2, 4]

    # Both rows read the same sealed person side; only the env side varies.
    assert len({r.person_submission_id for r in result.rows}) == 1
    for dimension in ENV_DIMENSIONS:
        assert result.person[dimension][0] == pytest.approx(result.person[dimension][1])
    assert result.env["autonomy"][0] == pytest.approx(0.9)
    assert result.env["autonomy"][1] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Past-job reports (PRODUCT_DECISIONS.md §2, 2026-10-01): report_subject and
# current_report_ordinal
# ---------------------------------------------------------------------------


def _write_past_report(email, *, plan=None, experienced=3, career_status="employed"):
    """A `subject='past'` row, written straight through A-2's store. The route's
    own eligibility rules are the service's business and tested there; this
    file only needs the row to exist, so it does not depend on the route."""
    from app import app
    from environment_report_store import write_environment_report
    from model import User, db
    from work_pulse import situation

    answers = _answers_from_plan(plan)
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        report_id = write_environment_report(
            db,
            user.id,
            raw_answers=answers,
            dimension_scores=situation.score_environment(
                answers, situation_items.item_spec(career_status)
            ),
            stage_size=2,
            comp=3,
            experienced_outcome=experienced,
            career_status=career_status,
            version=situation_items.FORM_VERSION,
            subject="past",
        )
        db.session.commit()
    return report_id


def test_subject_vocabulary_agrees_with_the_model():
    """Restated so the model lane needs no app on sys.path; this is the tripwire."""
    from model import ENV_REPORT_SUBJECTS

    assert atd.ENVIRONMENT_REPORT_SUBJECTS == tuple(ENV_REPORT_SUBJECTS)
    assert atd.SUBJECT_CURRENT == "current"
    assert atd.SUBJECT_PAST == "past"


def test_a_past_report_is_a_row_marked_past_with_no_current_ordinal(client, monkeypatch):
    """A past row assembles like any other -- same arrays, same pin -- and says
    what it is. It pairs with the SAME person-side sitting as the user's
    current row (the person side is measured now, the job ended earlier)."""
    email = "e4_past_one@example.com"
    csrf = _register_and_login(client, monkeypatch, email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    assert _post_env(client, csrf, experienced=5).status_code == 200
    past_id = _write_past_report(email, experienced=2)

    result = _assemble()

    assert result.dropped == []
    assert [r.report_subject for r in result.rows] == ["current", "past"]
    current, past = result.rows
    assert past.environment_report_id == past_id
    assert past.current_report_ordinal is None
    assert current.current_report_ordinal == 1
    assert list(result.outcome) == [5, 2]

    # Same pin, same person side -- by design, and the capture note says so.
    assert past.person_submission_id == current.person_submission_id
    for dimension in ENV_DIMENSIONS:
        assert result.person[dimension][1] == pytest.approx(result.person[dimension][0])

    # career_status is the filer's status at filing, carried as-is.
    assert past.career_status == "employed"
    # report_ordinal still counts every report the user wrote.
    assert [r.report_ordinal for r in result.rows] == [1, 2]
    assert [r.report_count_for_user for r in result.rows] == [2, 2]


def test_current_ordinals_ignore_an_interleaved_past_report(client, monkeypatch):
    """current, past, current, current (by submitted_at): the current rows are
    numbered 1, 2, 3 -- the past row in between takes no place among them."""
    email = "e4_past_interleave@example.com"
    csrf = _register_and_login(client, monkeypatch, email)
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    assert _post_env(client, csrf, experienced=1).status_code == 200
    _write_past_report(email, experienced=2)
    assert _post_env(client, csrf, experienced=3).status_code == 200
    assert _post_env(client, csrf, experienced=4).status_code == 200

    # A second user, so per-user numbering is exercised too.
    other = "e4_past_interleave_other@example.com"
    csrf_o = _register_and_login(client, monkeypatch, other)
    _set_career_status(client, csrf_o, "between_jobs")
    _complete_core(client, csrf_o)
    assert _post_env(client, csrf_o, experienced=5).status_code == 200

    result = _assemble()
    assert result.dropped == []

    from app import app
    from model import User

    with app.app_context():
        uid = User.query.filter_by(email=email).first().id

    mine = [(r, int(o)) for r, o in zip(result.rows, result.outcome) if r.user_id == uid]
    assert [o for _, o in mine] == [1, 2, 3, 4]  # submitted_at order
    assert [r.report_subject for r, _ in mine] == ["current", "past", "current", "current"]
    assert [r.current_report_ordinal for r, _ in mine] == [1, None, 2, 3]
    assert [r.report_ordinal for r, _ in mine] == [1, 2, 3, 4]

    theirs = [r for r in result.rows if r.user_id != uid]
    assert [(r.report_subject, r.current_report_ordinal) for r in theirs] == [("current", 1)]


def test_first_eligible_current_report_is_current_report_ordinal_one(client, monkeypatch):
    """The pre-registered primary sample is one line over the rows, and no past
    report -- even one filed right after the first current one -- lands in it."""
    import numpy as np

    for email, n_current, with_past in (
        ("e4_first_a@example.com", 2, True),
        ("e4_first_b@example.com", 1, False),
        ("e4_first_c@example.com", 3, True),
    ):
        csrf = _register_and_login(client, monkeypatch, email)
        _set_career_status(client, csrf, "employed")
        _complete_core(client, csrf)
        for i in range(n_current):
            assert _post_env(client, csrf, experienced=1 + i).status_code == 200
            if with_past and i == 0:
                _write_past_report(email, experienced=5)

    result = _assemble()
    assert result.dropped == []
    assert len(result.rows) == 2 + 1 + 3 + 2

    keep = np.array([r.current_report_ordinal == 1 for r in result.rows])
    primary = [r for r, k in zip(result.rows, keep) if k]

    assert len(primary) == 3
    assert len({r.user_id for r in primary}) == 3  # exactly one per user
    assert all(r.report_subject == "current" for r in primary)
    # Each is that user's EARLIEST current report (experienced = 1 by construction).
    assert result.outcome[keep].tolist() == [1, 1, 1]


def _same_array(a, b):
    import numpy as np

    a, b = np.asarray(a), np.asarray(b)
    assert a.dtype == b.dtype and a.shape == b.shape
    if a.dtype == object:
        assert list(a) == list(b)
    else:
        assert a.tobytes() == b.tobytes()


def _assert_same_result(new, old, *, ignore_fields=("report_subject", "current_report_ordinal")):
    """Every array (raw and after preprocess_conf) byte-identical; every row
    field identical except the named ones."""
    for group in ("person", "env", "conf", "conf_missing"):
        assert list(getattr(new, group)) == list(getattr(old, group)), group
        for key in getattr(new, group):
            _same_array(getattr(new, group)[key], getattr(old, group)[key])
    _same_array(new.outcome, old.outcome)
    assert new.dropped == old.dropped
    assert new.unsupplied_confounders == old.unsupplied_confounders
    assert new.outcome_type == old.outcome_type

    cfg = _cfg()
    pre_new = _match_core().preprocess_conf(new.conf, cfg, conf_missing=new.conf_missing)
    pre_old = _match_core().preprocess_conf(old.conf, cfg, conf_missing=old.conf_missing)
    assert list(pre_new) == list(pre_old)
    for key in pre_new:
        _same_array(pre_new[key], pre_old[key])

    assert len(new.rows) == len(old.rows)
    old_fields = [f.name for f in dataclasses.fields(old.rows[0])] if old.rows else []
    for new_row, old_row in zip(new.rows, old.rows):
        for name in old_fields:
            if name in ignore_fields:
                continue
            assert getattr(new_row, name) == getattr(old_row, name), name


def _seed_current_only_dataset(client, monkeypatch, prefix):
    """Several users, repeated reports, a NULL comp and a named industry -- the
    shapes the current path already handles."""
    for i, (status, industry, comp, n) in enumerate(
        (
            ("employed", None, 2, 2),
            ("between_jobs", "healthcare", None, 1),
            ("employed", "tech", 5, 3),
        )
    ):
        csrf = _register_and_login(client, monkeypatch, "%s_%d@example.com" % (prefix, i))
        _set_career_status(client, csrf, status)
        _complete_core(client, csrf, _UNIFORM if i % 2 == 0 else _VARIED)
        for k in range(n):
            assert _post_env(
                client, csrf, industry=industry, comp=comp, experienced=1 + (i + k) % 5
            ).status_code == 200
    # One env report with no core, so `dropped` is non-empty and compared too.
    csrf = _register_and_login(client, monkeypatch, "%s_nocore@example.com" % prefix)
    _set_career_status(client, csrf, "employed")
    assert _post_env(client, csrf).status_code == 200


#: The commit just before `report_subject` existed. The comparison below loads
#: the assembler AS IT WAS there and runs it on the same database.
_PRE_SUBJECT_COMMIT = "45de8b4"


def _load_pre_subject_assembler():
    import importlib.util
    import subprocess

    repo = Path(__file__).resolve().parents[1]
    try:
        source = subprocess.run(
            [
                "git", "-C", str(repo), "show",
                "%s:causal_graph/v1_model/assemble_training_data.py" % _PRE_SUBJECT_COMMIT,
            ],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    name = "_atd_pre_subject"
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(_V1_MODEL / "assemble_training_data.py")
    sys.modules[name] = module
    exec(compile(source, "<atd@%s>" % _PRE_SUBJECT_COMMIT, "exec"), module.__dict__)
    return module


def test_a_current_only_dataset_is_byte_identical_to_the_pre_subject_assembler(
    client, monkeypatch
):
    """The subject column must not move a current-only fit. Same database,
    assembled by today's code and by the code as it was at _PRE_SUBJECT_COMMIT:
    every array (raw and preprocessed), `dropped`, and every pre-existing row
    field identical. The only difference is the two new fields.

    Needs git history (a shallow CI checkout lacks the commit and skips);
    `test_past_rows_do_not_perturb_current_rows` below is the history-free
    guard of the same property."""
    old_atd = _load_pre_subject_assembler()
    if old_atd is None:
        pytest.skip("commit %s not in this checkout" % _PRE_SUBJECT_COMMIT)

    _seed_current_only_dataset(client, monkeypatch, "e4_bytes")

    new = _assemble()
    from app import app
    from model import db

    with app.app_context():
        with db.engine.connect() as conn:
            old = old_atd.assemble_environment_training_data(conn, _cfg())

    assert len(new.rows) == 6 and len(new.dropped) == 1
    _assert_same_result(new, old)
    old_names = {f.name for f in dataclasses.fields(old.rows[0])}
    new_names = {f.name for f in dataclasses.fields(new.rows[0])}
    assert new_names - old_names == {"report_subject", "current_report_ordinal"}
    assert old_names <= new_names

    # On current-only data the new fields are fully determined.
    assert all(r.report_subject == "current" for r in new.rows)
    assert [r.current_report_ordinal for r in new.rows] == [
        r.report_ordinal for r in new.rows
    ]


def test_past_rows_do_not_perturb_current_rows(client, monkeypatch):
    """History-free version of the byte-identity guard: add a past report for a
    user, and the current rows -- selected on report_subject -- carry the same
    arrays and fields they had before, current_report_ordinal included. Only
    report_ordinal / report_count_for_user may move, because they count both
    subjects by definition."""
    _seed_current_only_dataset(client, monkeypatch, "e4_perturb")
    before = _assemble()

    _write_past_report("e4_perturb_2@example.com", experienced=4)
    after = _assemble()

    assert len(after.rows) == len(before.rows) + 1
    keep = [i for i, r in enumerate(after.rows) if r.report_subject == "current"]
    assert len(keep) == len(before.rows)

    import numpy as np

    idx = np.asarray(keep, dtype=int)
    filtered = atd.EnvironmentAssembleResult(
        person={k: v[idx] for k, v in after.person.items()},
        env={k: v[idx] for k, v in after.env.items()},
        conf={k: v[idx] for k, v in after.conf.items()},
        conf_missing={k: v[idx] for k, v in after.conf_missing.items()},
        outcome=after.outcome[idx],
        rows=[after.rows[i] for i in keep],
        dropped=after.dropped,
        unsupplied_confounders=after.unsupplied_confounders,
    )
    _assert_same_result(
        filtered, before, ignore_fields=("report_ordinal", "report_count_for_user")
    )


# ---------------------------------------------------------------------------
# Naming and shape: assert the agreement, do not trust the comment
# ---------------------------------------------------------------------------


def test_confounder_columns_agree_with_the_instrument():
    """`ENVIRONMENT_CONFOUNDER_COLUMNS` restates
    `situation_items.CONTEXT_COLUMNS` so the model lane needs no app on
    sys.path. Restating is the risk; this is the tripwire."""
    context = dict(situation_items.CONTEXT_COLUMNS)
    outcome_column = context.pop("experienced")

    assert atd.ENVIRONMENT_CONFOUNDER_COLUMNS == context
    assert atd.ENVIRONMENT_OUTCOME_COLUMN == outcome_column


def test_dimension_keys_and_order_agree_everywhere(client, monkeypatch):
    """One list of six, spelled the same and ordered the same, in the model
    config, the ORM, the instrument and the assembled arrays."""
    cfg = _cfg()
    active = [d["key"] for d in cfg["dimensions"] if d.get("active")]

    assert tuple(active) == tuple(ENV_DIMENSIONS)
    assert tuple(active) == tuple(situation_items.DIMENSIONS)

    csrf = _register_and_login(client, monkeypatch, "e4_order@example.com")
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    assert _post_env(client, csrf).status_code == 200

    result = _assemble()
    assert list(result.person) == active
    assert list(result.env) == active
    assert list(result.conf) == [
        c["key"] for c in cfg["confounders"] if c.get("active") and c.get("measurable")
    ]
    assert list(result.conf_missing) == list(result.conf)


def test_row_values_honour_schema_sql_ranges(client, monkeypatch):
    """schema.sql is the long-format contract A-2's columns were aligned to.
    Its encodings are stated in a doc-comment the database does not enforce
    ("the loader ... and the workbook dropdowns are the only guardrail"), which
    makes the loader's agreement with it worth asserting rather than assuming.
    """
    schema = _SCHEMA_SQL.read_text(encoding="utf-8")

    # The confounder encoding block: parsed, not eyeballed.
    encoding = re.search(
        r"value_num encoding per continuous confounder.*?^-- +'industry'[^\n]*",
        schema,
        re.S | re.M,
    )
    assert encoding, "schema.sql no longer documents the value_num encodings"
    block = encoding.group(0)
    assert re.search(r"'stage_size'\s*:\s*integer 1\.\.5", block)
    assert re.search(r"'comp'\s*:\s*integer 1\.\.5", block)
    assert re.search(r"'industry'\s*:\s*categorical -> uses value_cat", block)
    for key in atd.ENVIRONMENT_CONFOUNDER_COLUMNS:
        assert "'%s'" % key in block

    # The outcome's own declared range, and its ordinal nature.
    assert re.search(
        r"working_scale\s+SMALLINT NOT NULL CHECK \(working_scale BETWEEN 1 AND 5\)",
        schema,
    )
    # Both sides' dimension scores are 0..1 on ONE scale -- the premise of a
    # signed gap meaning anything at all.
    assert re.search(r"score\s+NUMERIC\(4,3\) NOT NULL CHECK \(score BETWEEN 0 AND 1\)", schema)

    csrf = _register_and_login(client, monkeypatch, "e4_schema@example.com")
    _set_career_status(client, csrf, "employed")
    _complete_core(client, csrf)
    assert _post_env(client, csrf, stage_size=1, comp=5, experienced=1).status_code == 200

    result = _assemble()
    assert result.conf["stage_size"][0] == 1.0
    assert result.conf["comp"][0] == 5.0
    assert 1 <= result.outcome[0] <= 5
    for dimension in ENV_DIMENSIONS:
        assert 0.0 <= result.person[dimension][0] <= 1.0
        assert 0.0 <= result.env[dimension][0] <= 1.0
