"""The devfit harness: the safety catch, the fitted-run writer, and the row path.

`causal_graph/v1_model/devfit/` is the local-only harness that seeds synthetic
people, fits the ordinal head against them, and prints a user's numbers. Only the
fitting step needs PyMC, and it lives in its own module for exactly that reason --
so everything in this file runs in the suite that actually runs in CI.

WHAT IS PINNED HERE, AND WHY EACH ONE

1. THE GUARD. `seed_synthetic --reset` deletes rows and `explain_user` prints
   numbers D-15 keeps off every payload, so a wrong database is the expensive
   mistake this package can make. The repo's own `.env` carries a Render-internal
   PRODUCTION `DATABASE_URL` and `app.py` calls `load_dotenv()`, which is not a
   hypothetical: it is a live footgun sitting in the working tree. The guard is
   tested against a URL shaped like that one.

2. `record_fitted_run`. The flat weight naming is a database interface: 20 rows,
   strict in both directions (D-07). A fit that wrote 19 or 21 would not fail at
   write time -- it would fail later, on every load, in the app.

3. THE ROW PATH, end to end, through the real store functions: draw a small
   cohort, write it, assemble it, and put it through the linear predictor. That is
   the thing the whole harness exists to make possible, and it is worth an
   assertion that does not need a fit to run.

This file writes through `assessment_store` and reads through the assembler, so
it stays off `tests/test_employer_visibility.py`'s allowlist by construction --
it never names the sealed person-side tables, in code or in prose.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

import match_scoring  # noqa: F401  -- puts causal_graph/v1_model on sys.path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from causal_graph.v1_model.devfit import guard  # noqa: E402
from causal_graph.v1_model.devfit import seed_synthetic  # noqa: E402

DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]

#: Shaped like the URL actually sitting in this repo's .env -- a Render-internal
#: hostname with no port and a database name that looks plausible.
PRODUCTION_SHAPED_URL = "postgresql://solverah:hunter2@dpg-abc123-a/solverah_prod"

LOCAL_OK = "postgresql://solverah:solverah@localhost:5433/solverah_modeldev"


@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    # Read at call time in assessment_store.respondent_id_for_user, with no default
    # by design (D-05). Deliberately NOT in tests/conftest.py: test_assessment_form.py
    # deletes the variable to prove the no-default rule, and a suite-wide default
    # would make that test unable to fail.
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


# ---------------------------------------------------------------------------
# 1. The guard
# ---------------------------------------------------------------------------

def test_a_local_model_dev_url_is_accepted_and_returned_unchanged():
    assert guard.assert_local_dev_database(LOCAL_OK, app_env="testing") == LOCAL_OK


@pytest.mark.parametrize("url", [
    "postgresql://solverah:solverah@127.0.0.1:5433/solverah_modeldev",
    "postgresql://solverah:solverah@localhost:5433/solverah_modeldev_b",
    "postgresql://u:p@localhost/solverah_modeldev?sslmode=disable",
])
def test_the_accepted_shapes(url):
    """127.0.0.1 as well as localhost; a suffixed database name; and a query
    string, which must not leak into the name comparison."""
    assert guard.assert_local_dev_database(url, app_env="testing")


def test_a_production_shaped_url_is_refused():
    with pytest.raises(guard.UnsafeDatabaseError) as exc:
        guard.assert_local_dev_database(PRODUCTION_SHAPED_URL, app_env="testing")
    assert "not local" in str(exc.value)


def test_right_host_wrong_database_name_is_refused():
    """A local host is not enough. Every other lane's database is on this same
    server and this same port."""
    with pytest.raises(guard.UnsafeDatabaseError) as exc:
        guard.assert_local_dev_database(
            "postgresql://solverah:solverah@localhost:5433/solverah_test",
            app_env="testing",
        )
    assert "solverah_modeldev" in str(exc.value)


def test_right_database_name_wrong_host_is_refused():
    """The name alone is not enough either -- a remote server could carry a
    database with this exact name."""
    with pytest.raises(guard.UnsafeDatabaseError) as exc:
        guard.assert_local_dev_database(
            "postgresql://u:p@db.example.com:5432/solverah_modeldev",
            app_env="testing",
        )
    assert "not local" in str(exc.value)


def test_app_env_production_is_refused_even_on_a_correct_url():
    with pytest.raises(guard.UnsafeDatabaseError) as exc:
        guard.assert_local_dev_database(LOCAL_OK, app_env="production")
    assert "production" in str(exc.value)


def test_credentials_that_look_like_a_local_host_do_not_fool_it():
    """`urlsplit().hostname` strips user:pass@, so the host here is the remote
    one. A substring check for 'localhost' would have passed this."""
    with pytest.raises(guard.UnsafeDatabaseError):
        guard.assert_local_dev_database(
            "postgresql://localhost:localhost@prod.example.com/solverah_modeldev",
            app_env="testing",
        )


@pytest.mark.parametrize("url", [
    "postgresql://solverah:x@localhost:5433/solverah_modeldev?host=prod.example.com",
    "postgresql://solverah:x@localhost:5433/solverah_modeldev?hostaddr=10.0.0.9",
    "postgresql://solverah:x@localhost:5433/solverah_modeldev?dbname=solverah_postgres",
    "postgresql://solverah:x@localhost:5433/solverah_modeldev?service=prod",
    "postgresql://solverah:x@localhost:5433/solverah_modeldev?HOST=prod.example.com",
    "postgresql://solverah:x@localhost:5433/solverah_modeldev?sslmode=disable&host=prod.example.com",
    "postgresql://solverah:x@/solverah_modeldev?host=prod.example.com",
])
def test_a_query_string_cannot_redirect_a_local_looking_url(url):
    """Oversight regression, 2026-09-21: every one of these was ACCEPTED. The
    driver merges the query string over the URL's own host and database, so the
    visible host and path said `localhost/solverah_modeldev` while the connection
    went wherever the query named."""
    with pytest.raises(guard.UnsafeDatabaseError):
        guard.assert_local_dev_database(url, app_env="testing")


def test_the_guard_agrees_with_what_the_driver_would_actually_dial():
    """The property the cases above are instances of, checked against SQLAlchemy
    itself rather than against this file's idea of it: for a URL the guard ACCEPTS,
    the driver's connect arguments name a local host and a model-dev database, and
    carry nothing else that routes a connection."""
    from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
    from sqlalchemy.engine import make_url

    for url in (LOCAL_OK, "postgresql://u:p@127.0.0.1/solverah_modeldev_b?sslmode=disable"):
        guard.assert_local_dev_database(url, app_env="testing")
        _, opts = PGDialect_psycopg2().create_connect_args(make_url(url))
        assert str(opts["host"]).lower() in ("localhost", "127.0.0.1")
        assert str(opts.get("dbname", opts.get("database"))).startswith("solverah_modeldev")
        assert not {"hostaddr", "service"} & set(opts)


def test_an_empty_host_is_refused():
    """`postgresql:///db` hands the host to libpq, which reads PGHOST -- so an
    empty host means 'wherever the environment points', not 'this machine'."""
    with pytest.raises(guard.UnsafeDatabaseError) as exc:
        guard.assert_local_dev_database("postgresql:///solverah_modeldev", app_env="testing")
    assert "not local" in str(exc.value)


def test_an_empty_or_missing_url_is_refused_rather_than_defaulted(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(guard.UnsafeDatabaseError) as exc:
        guard.require_database_url(None)
    assert "never falls back" in str(exc.value)


def test_require_database_url_reads_the_environment_but_still_guards(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DATABASE_URL", LOCAL_OK)
    assert guard.require_database_url(None) == LOCAL_OK

    monkeypatch.setenv("DATABASE_URL", PRODUCTION_SHAPED_URL)
    with pytest.raises(guard.UnsafeDatabaseError):
        guard.require_database_url(None)


def test_an_explicit_argument_beats_the_environment(monkeypatch):
    """--database-url wins, and is guarded on its own merits -- otherwise a safe
    environment variable would launder an unsafe flag."""
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DATABASE_URL", LOCAL_OK)
    with pytest.raises(guard.UnsafeDatabaseError):
        guard.require_database_url(PRODUCTION_SHAPED_URL)


# ---------------------------------------------------------------------------
# 2. record_fitted_run
# ---------------------------------------------------------------------------

def _posterior_shaped_weights(cfg, pri, *, shift=0.0):
    """Nested {mean, sd} weights in the shape a posterior arrives in: every leaf
    a plain float, the categorical confounder a per-level array."""
    from match_scoring import weights_from_priors

    weights = weights_from_priors(cfg, pri)
    weights["intercept"] = {"mean": weights["intercept"]["mean"] + shift, "sd": 0.21}
    for feats in weights["dimensions"].values():
        for feat, leaf in feats.items():
            feats[feat] = {"mean": leaf["mean"] + shift, "sd": 0.19}
    for key, leaf in weights["confounders"].items():
        if isinstance(leaf["mean"], np.ndarray):
            weights[key] = leaf
            weights["confounders"][key] = {
                "mean": leaf["mean"] + shift,
                "sd": np.full(leaf["mean"].shape, 0.93),
            }
        else:
            weights["confounders"][key] = {"mean": leaf["mean"] + shift, "sd": 0.17}
    return weights


def test_record_fitted_run_writes_one_run_and_exactly_twenty_weight_rows(client):
    from app import app
    from match_scoring import FITTED_MODEL_VERSION, load, record_fitted_run
    from model import ModelRun, WeightPosterior, db

    cfg, pri = load()
    with app.app_context():
        run = record_fitted_run(
            db, cfg, _posterior_shaped_weights(cfg, pri),
            n_rows=1200, notes='{"source": "devfit"}',
        )
        db.session.commit()

        assert run.model_version == FITTED_MODEL_VERSION
        assert run.n_rows == 1200
        assert run.dimension_set_version == ",".join(DIMS)
        assert run.priors_version.startswith("sha256:")

        rows = WeightPosterior.query.filter_by(model_run_id=run.id).all()
        # 1 intercept + 6 dims x 2 feats + stage_size + comp + 5 industry levels
        assert len(rows) == 20
        assert not any("cut" in row.weight_name for row in rows), (
            "the cutpoint spacings are not weight rows -- unflatten_weights is "
            "strict and would refuse every load of this run"
        )
        assert ModelRun.query.count() == 1


def test_a_fitted_run_round_trips_through_load_run_weights(client):
    """The flat naming is the interface a posterior is exported through. If the
    trip is not lossless the app serves different numbers than the fit produced."""
    from app import app
    from match_scoring import load, load_run_weights, record_fitted_run
    from model import db

    cfg, pri = load()
    written = _posterior_shaped_weights(cfg, pri, shift=0.37)
    with app.app_context():
        record_fitted_run(db, cfg, written, n_rows=500)
        db.session.commit()

        _run, read_back = load_run_weights(db, cfg=cfg)

    assert read_back["intercept"]["mean"] == pytest.approx(
        written["intercept"]["mean"], abs=0.0
    )
    for dim in DIMS:
        for feat in ("mag", "dir"):
            assert read_back["dimensions"][dim][feat] == pytest.approx(
                written["dimensions"][dim][feat], abs=0.0
            )
    np.testing.assert_array_equal(
        read_back["confounders"]["industry"]["mean"],
        written["confounders"]["industry"]["mean"],
    )
    np.testing.assert_array_equal(
        read_back["confounders"]["industry"]["sd"],
        written["confounders"]["industry"]["sd"],
    )


def test_every_fit_makes_a_new_run_and_the_newest_one_serves(client):
    """Never idempotent-merged. A second fit -- more rows, a different seed, a
    widened prior -- is a different posterior, and silently returning the first
    would make a re-fit look like it had happened when it had not."""
    from app import app
    from match_scoring import current_run, load, load_run_weights, record_fitted_run
    from model import ModelRun, db

    cfg, pri = load()
    with app.app_context():
        first = record_fitted_run(db, cfg, _posterior_shaped_weights(cfg, pri),
                                  n_rows=100, notes="first")
        db.session.commit()
        second = record_fitted_run(
            db, cfg, _posterior_shaped_weights(cfg, pri, shift=0.5),
            n_rows=1200, notes="second",
        )
        db.session.commit()

        assert second.id != first.id
        assert ModelRun.query.count() == 2
        assert current_run(db).id == second.id

        _run, served = load_run_weights(db)
        assert served["intercept"]["mean"] == pytest.approx(
            _posterior_shaped_weights(cfg, pri, shift=0.5)["intercept"]["mean"]
        )


def test_a_fitted_run_and_the_priors_run_coexist_and_the_fit_wins(client):
    """The priors run is seeded at launch and must not be deleted by a fit -- it
    is the audit trail of what was served before any data existed."""
    from app import app
    from match_scoring import (FITTED_MODEL_VERSION, PRIORS_MODEL_VERSION,
                               current_run, load, record_fitted_run,
                               seed_priors_model_run)
    from model import ModelRun, db

    cfg, pri = load()
    with app.app_context():
        seed_priors_model_run(db)
        db.session.commit()
        record_fitted_run(db, cfg, _posterior_shaped_weights(cfg, pri), n_rows=1200)
        db.session.commit()

        versions = [r.model_version for r in ModelRun.query.order_by(ModelRun.id).all()]
        assert versions == [PRIORS_MODEL_VERSION, FITTED_MODEL_VERSION]
        assert current_run(db).model_version == FITTED_MODEL_VERSION


# ---------------------------------------------------------------------------
# 3. The row path: draw -> store functions -> assembler -> linear predictor
# ---------------------------------------------------------------------------

COHORT_N = 12


def test_a_seeded_cohort_assembles_with_no_drops_and_every_z_finite(client):
    """The point of the harness, without the fit. Rows are drawn and written by
    the SAME code `seed_synthetic` uses -- not a second implementation that could
    drift from it -- then read back through the real assembler."""
    import assemble_training_data as atd
    import match_core
    from app import app
    from model import db

    cohort = seed_synthetic.SyntheticCohort()
    rng = np.random.default_rng(7)

    with app.app_context():
        for index in range(COHORT_N):
            cohort.write(
                db,
                "cohort-%03d%s" % (index, seed_synthetic.SYNTHETIC_EMAIL_DOMAIN),
                cohort.draw(rng),
            )
        db.session.commit()

        with db.engine.connect() as conn:
            result = atd.assemble_environment_training_data(conn, cohort.cfg)

    assert len(result.rows) == COHORT_N
    assert result.dropped == [], "unexplained drops: %r" % (result.dropped,)
    assert result.outcome_type == "experienced"
    assert set(result.outcome.tolist()) <= {1, 2, 3, 4, 5}

    # `industry` is never asked by the instrument, so every row is masked -- the
    # exact case match_core.preprocess_conf's categorical mask exists for.
    assert result.unsupplied_confounders == ("industry",)
    assert np.asarray(result.conf_missing["industry"]).all()

    conf = match_core.preprocess_conf(
        result.conf, cohort.cfg, conf_missing=result.conf_missing
    )
    assert conf["industry__present"].tolist() == [0.0] * COHORT_N

    z = np.asarray(match_core.outcome_logit(
        result.person, result.env, conf, cohort.cfg,
        match_core.point_weights(
            match_core.weights_from_priors(cohort.cfg, cohort.pri)
        ),
    ))
    assert z.shape == (COHORT_N,)
    assert np.isfinite(z).all()


def test_the_drawn_rows_carry_the_missing_comp_the_ruling_promised(client):
    """`comp` is nullable by a signed ruling ("not sure"). The seeder produces
    some, because a harness that never exercised the NULL path would not be
    testing the model that has to handle it."""
    cohort = seed_synthetic.SyntheticCohort(comp_unsure_rate=1.0)
    rng = np.random.default_rng(3)
    rows = [cohort.draw(rng) for _ in range(6)]
    assert all(row["comp"] is None for row in rows)

    never = seed_synthetic.SyntheticCohort(comp_unsure_rate=0.0)
    rows = [never.draw(rng) for _ in range(6)]
    assert all(isinstance(row["comp"], int) for row in rows)


def test_the_planted_truth_is_the_priors_with_two_deviations():
    """The fit is asked to move two weights a long way and leave sixteen alone.
    Pinned because a truth that quietly equalled the prior would make every
    'recovered' number meaningless."""
    from match_scoring import load, weights_from_priors

    cfg, pri = load()
    truth = seed_synthetic.true_weights(cfg, pri)
    prior = weights_from_priors(cfg, pri)

    assert truth["dimensions"]["autonomy"]["mag"] == -3.0
    assert truth["dimensions"]["pace"]["mag"] == -0.5
    # and they really are far from what the expert said
    assert abs(truth["dimensions"]["autonomy"]["mag"]
               - prior["dimensions"]["autonomy"]["mag"]["mean"]) > 2.0
    assert abs(truth["dimensions"]["pace"]["mag"]
               - prior["dimensions"]["pace"]["mag"]["mean"]) > 1.9

    for dim in DIMS:
        for feat in ("mag", "dir"):
            if (dim, feat) in (("autonomy", "mag"), ("pace", "mag")):
                continue
            assert truth["dimensions"][dim][feat] == pytest.approx(
                prior["dimensions"][dim][feat]["mean"]
            )


# ---------------------------------------------------------------------------
# 4. Marking, and the refusal that protects a database with real rows in it
# ---------------------------------------------------------------------------

def test_the_synthetic_domain_can_never_resolve():
    """`.invalid` is reserved by RFC 2606. One of these addresses cannot be
    mailed even by a mistake elsewhere in the system."""
    assert seed_synthetic.SYNTHETIC_EMAIL_DOMAIN.endswith(".invalid")
    assert seed_synthetic.SYNTHETIC_EMAIL_DOMAIN.startswith("@")


def test_seeding_is_refused_when_a_user_is_not_marked_synthetic(client, seed_user):
    """The guard checks the URL; this checks the contents. A correctly-named
    database can still hold something real."""
    from app import app
    from model import EnvironmentReport, User

    seed_user(4242)
    with app.app_context():
        with pytest.raises(SystemExit) as exc:
            seed_synthetic.assert_safe_to_seed(User, EnvironmentReport)
    assert "do not end in" in str(exc.value)


def test_seeding_is_refused_when_the_database_already_holds_a_cohort(client):
    """Two cohorts in one database would be fitted together while the truth file
    described only the newer one -- a wrong recovery number nothing downstream
    could detect."""
    from app import app
    from model import EnvironmentReport, User, db

    cohort = seed_synthetic.SyntheticCohort()
    rng = np.random.default_rng(11)
    with app.app_context():
        cohort.write(db, "a%s" % seed_synthetic.SYNTHETIC_EMAIL_DOMAIN,
                     cohort.draw(rng))
        db.session.commit()

        with pytest.raises(SystemExit) as exc:
            seed_synthetic.assert_safe_to_seed(User, EnvironmentReport)
    assert "already holds" in str(exc.value)


def test_an_all_synthetic_empty_database_is_allowed(client):
    from app import app
    from model import EnvironmentReport, User

    with app.app_context():
        seed_synthetic.assert_safe_to_seed(User, EnvironmentReport)   # no raise


def test_reset_removes_the_training_rows_and_leaves_the_sealed_sitting(client):
    """A reset deletes what the assembler reads. It deliberately does not reach
    the sealed core sitting: those rows survive even account deletion, by a
    decided reconciliation, and a dev convenience is not a reason to teach the
    codebase that the seal is optional."""
    import assemble_training_data as atd
    import assessment_store
    from app import app
    from model import EnvironmentReport, User, db

    cohort = seed_synthetic.SyntheticCohort()
    rng = np.random.default_rng(5)
    with app.app_context():
        user_ids = [
            cohort.write(db, "r%d%s" % (i, seed_synthetic.SYNTHETIC_EMAIL_DOMAIN),
                         cohort.draw(rng))
            for i in range(3)
        ]
        db.session.commit()

        assert EnvironmentReport.query.count() == 3
        removed = seed_synthetic._reset(db, User)
        assert removed == 3
        assert EnvironmentReport.query.count() == 0

        # No training rows left...
        with db.engine.connect() as conn:
            assert atd.assemble_environment_training_data(conn, cohort.cfg).rows == []

        # ...and the sitting is still readable through its own doorway.
        for user_id in user_ids:
            submission_id = assessment_store.first_completed_core_submission_id(user_id)
            assert submission_id is not None
            scores = assessment_store.dimension_scores_for_submission(submission_id)
            assert set(scores) == set(DIMS)


# ---------------------------------------------------------------------------
# 5. The diagnostic gate and --prior-sd-scale
#
# `run_fit` imports PyMC lazily, inside run(), so the pure helpers below are
# reachable from this suite. Which is where they belong: the gate is the thing
# standing between a badly-mixed posterior and what the app serves, and it should
# be checked by the tests that actually run in CI rather than only by the PyMC
# file nobody runs on a branch.
# ---------------------------------------------------------------------------

def test_the_gate_passes_a_healthy_run():
    from causal_graph.v1_model.devfit import run_fit

    assert run_fit.is_healthy(
        {"max_rhat": 1.004, "max_rhat_on": "p_fit", "divergences": 0}
    )


@pytest.mark.parametrize("diag, why", [
    ({"max_rhat": 1.05, "max_rhat_on": "x", "divergences": 0}, "at the ceiling"),
    ({"max_rhat": 1.31, "max_rhat_on": "x", "divergences": 0}, "above it"),
    ({"max_rhat": 1.001, "max_rhat_on": "x", "divergences": 1}, "one divergence"),
    ({"max_rhat": float("nan"), "max_rhat_on": "x", "divergences": 0}, "unavailable"),
])
def test_the_gate_refuses(diag, why):
    """The last case is the one that bit: with a single chain arviz returns NaN
    r_hat for every variable, and an earlier `np.nanmax` over all-NaN produced
    0.0 -- which passed `< 1.05`. 'Could not check' must read as 'not verified',
    never as 'fine'."""
    from causal_graph.v1_model.devfit import run_fit

    assert run_fit.is_healthy(diag) is False, why


def test_prior_sd_scale_widens_dimensions_only_and_copies():
    """The expert's file is never edited; only this run's in-memory copy is."""
    from causal_graph.v1_model.devfit import run_fit
    from match_scoring import load

    cfg, pri = load()
    before = float(pri["dimensions"]["pace"]["mag"]["sd"])
    scaled = run_fit.scaled_priors(pri, 3.0)

    for dim in DIMS:
        for feat in ("mag", "dir"):
            assert scaled["dimensions"][dim][feat]["sd"] == pytest.approx(
                pri["dimensions"][dim][feat]["sd"] * 3.0
            )
            assert scaled["dimensions"][dim][feat]["mean"] == pytest.approx(
                pri["dimensions"][dim][feat]["mean"]
            )
    assert scaled["intercept"] == pri["intercept"]
    assert scaled["confounders"] == pri["confounders"]
    assert scaled["cutpoints"] == pri["cutpoints"]
    assert float(pri["dimensions"]["pace"]["mag"]["sd"]) == before
    assert run_fit.scaled_priors(pri, 1.0) == pri


# ---------------------------------------------------------------------------
# 6. explain_user's weight conversion (the ranking seam, no database needed)
# ---------------------------------------------------------------------------

def test_explain_user_converts_weights_into_the_ranking_shape():
    """`work_pulse.situation.dimension_cost` refuses a weight whose |dir| exceeds
    |mag|, so the conversion has to preserve signs exactly -- not absolute values,
    not a rescaling."""
    from causal_graph.v1_model.devfit import explain_user
    from match_scoring import load, weights_from_priors

    cfg, pri = load()
    converted = explain_user.dimension_weights(weights_from_priors(cfg, pri))

    assert set(converted) == set(DIMS)
    for dim in DIMS:
        assert converted[dim]["mag"] == pytest.approx(
            pri["dimensions"][dim]["mag"]["mean"]
        )
        assert converted[dim]["dir"] == pytest.approx(
            pri["dimensions"][dim]["dir"]["mean"]
        )
        assert converted[dim]["mag"] < 0
        assert abs(converted[dim]["dir"]) <= abs(converted[dim]["mag"])


def test_the_converted_weights_actually_rank(client):
    """End of the seam: the conversion feeds work_pulse.situation, which is what
    orders a real Situation Report."""
    from causal_graph.v1_model.devfit import explain_user
    from match_scoring import load, weights_from_priors
    from work_pulse import situation

    cfg, pri = load()
    weights = explain_user.dimension_weights(weights_from_priors(cfg, pri))
    gaps = {dim: 0.3 for dim in DIMS}
    order = situation.rank_dimensions(gaps, weights)

    assert sorted(order) == sorted(DIMS)
    # Equal gaps, so the order is the weights' own -- not DIMENSIONS order.
    assert order != list(situation.DIMENSIONS)


# ---------------------------------------------------------------------------
# make_loginable -- one synthetic row becomes an account, and only that
# ---------------------------------------------------------------------------

def test_make_loginable_refuses_a_real_looking_email():
    from causal_graph.v1_model.devfit import make_loginable as ml

    for email in ("person@example.com", "", "x@synthetic.solverah.invalid.evil.com"):
        with pytest.raises(ml.NotSyntheticError):
            ml.assert_synthetic_email(email)


def test_a_synthetic_user_can_sign_in_only_after_make_loginable(client):
    """Through the real login route, not a mocked hasher: before, the seeded
    placeholder hash and unconfirmed email keep the row from being an account;
    after, the same credentials sign in."""
    from app import app
    from causal_graph.v1_model.devfit import make_loginable as ml
    from model import User, db
    from solverah.extensions import bcrypt

    email = "synth-99999" + seed_synthetic.SYNTHETIC_EMAIL_DOMAIN
    with app.app_context():
        db.session.add(User(email=email, password_hash=seed_synthetic.UNUSABLE_PASSWORD_HASH))
        db.session.commit()

    before = client.post("/api/v1/auth/login", json={"email": email, "password": "Devpass1!"})
    # 401, not 500: the seeded hash is valid bcrypt that nothing matches. A readable
    # placeholder here made the real route raise "Invalid salt" instead of refusing.
    assert before.status_code == 401, before.get_json()

    with app.app_context():
        user = User.query.filter(User.email == email).first()
        ml.make_loginable(db, user, "Devpass1!", bcrypt.generate_password_hash)
        db.session.commit()

    after = client.post("/api/v1/auth/login", json={"email": email, "password": "Devpass1!"})
    assert after.status_code == 200, after.get_json()


def test_make_loginable_will_not_touch_a_non_synthetic_row(client, seed_user):
    from app import app
    from causal_graph.v1_model.devfit import make_loginable as ml
    from model import User, db
    from solverah.extensions import bcrypt

    seed_user(1)
    with app.app_context():
        user = User.query.first()
        original = user.password_hash
        with pytest.raises(ml.NotSyntheticError):
            ml.make_loginable(db, user, "Devpass1!", bcrypt.generate_password_hash)
        assert user.password_hash == original
