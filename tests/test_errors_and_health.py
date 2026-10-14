"""Tests for the Problem Details error envelope and the health probes."""

import pytest
from flask import Flask

from solverah.api.health import create_health_blueprint
from solverah.errors import (
    ApiError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    register_error_handlers,
)
from solverah.observability.logging import install_request_logging


@pytest.fixture()
def app():
    application = Flask(__name__)
    application.config["MAX_CONTENT_LENGTH"] = 1024
    install_request_logging(application)
    register_error_handlers(application)

    @application.get("/ok")
    def ok():
        return {"ok": True}

    @application.get("/validation")
    def validation():
        raise ValidationError(
            "linkedin_url must be an HTTPS linkedin.com URL",
            errors=[{"field": "linkedin_url", "code": "invalid_url"}],
        )

    @application.get("/forbidden")
    def forbidden():
        raise AuthorizationError()

    @application.get("/conflict")
    def conflict():
        raise ConflictError("email already registered")

    @application.get("/missing")
    def missing():
        raise NotFoundError()

    @application.get("/limited")
    def limited():
        raise RateLimitError()

    @application.get("/boom")
    def boom():
        raise RuntimeError("password=hunter2 leaked from psycopg2 at db-prod-1:5432")

    @application.post("/echo")
    def echo():
        # MAX_CONTENT_LENGTH is enforced on read, not on receipt, so the 413
        # only fires for a handler that actually consumes the body -- which
        # every real endpoint does.
        from flask import request

        request.get_data()
        return {"ok": True}

    return application


@pytest.fixture()
def client(app):
    return app.test_client()


# ------------------------------------------------------------------ envelope
def test_successful_request_is_untouched(client):
    res = client.get("/ok")

    assert res.status_code == 200
    assert res.get_json() == {"ok": True}


def test_api_error_renders_problem_details(client):
    res = client.get("/validation")
    body = res.get_json()

    assert res.status_code == 422
    assert res.mimetype == "application/problem+json"
    assert body["type"] == "https://solverah.com/errors/validation"
    assert body["title"] == "Validation failed"
    assert body["status"] == 422
    assert body["instance"] == "/validation"
    assert body["errors"] == [{"field": "linkedin_url", "code": "invalid_url"}]


def test_problem_carries_the_request_id(client):
    res = client.get("/validation")

    assert res.get_json()["request_id"] == res.headers["X-Request-Id"]


@pytest.mark.parametrize(
    "path,status,code",
    [
        ("/validation", 422, "validation"),
        ("/forbidden", 403, "forbidden"),
        ("/conflict", 409, "conflict"),
        ("/missing", 404, "not_found"),
        ("/limited", 429, "rate_limited"),
    ],
)
def test_each_error_class_maps_to_its_status(client, path, status, code):
    res = client.get(path)

    assert res.status_code == status
    assert res.get_json()["type"].endswith("/" + code)


# ------------------------------------------------------- framework exceptions
def test_unknown_route_returns_json_not_html(client):
    """The frontend calls res.json() on every response; an HTML 404 surfaces in
    the UI as "Unexpected response from server" instead of the real error."""
    res = client.get("/no-such-route")

    assert res.status_code == 404
    assert res.mimetype == "application/problem+json"
    assert res.get_json()["status"] == 404


def test_wrong_method_returns_json(client):
    res = client.post("/ok")

    assert res.status_code == 405
    assert res.get_json()["type"].endswith("/method_not_allowed")


def test_oversized_body_returns_json_413(client):
    res = client.post("/echo", data="x" * 4096, content_type="application/json")

    assert res.status_code == 413
    assert res.get_json()["status"] == 413


# ------------------------------------------------------------- leak avoidance
def test_unhandled_exception_leaks_nothing(client):
    res = client.get("/boom")
    body = res.get_json()
    blob = repr(body)

    assert res.status_code == 500
    assert "hunter2" not in blob
    assert "psycopg2" not in blob
    assert "db-prod-1" not in blob
    assert "RuntimeError" not in blob
    # The id is the only handle the client gets, and it is enough to find the trace.
    assert body["request_id"] == res.headers["X-Request-Id"]


def test_server_side_http_exception_hides_its_description(app):
    """5xx descriptions can carry internal detail; only 4xx text is safe to echo."""
    from werkzeug.exceptions import ServiceUnavailable

    @app.get("/unavailable")
    def unavailable():
        raise ServiceUnavailable("upstream pgbouncer pool exhausted on db-prod-1")

    res = app.test_client().get("/unavailable")

    assert res.status_code == 503
    assert "pgbouncer" not in repr(res.get_json())


def test_custom_api_error_subclass_is_handled(app):
    class PaymentRequired(ApiError):
        status = 402
        title = "Payment required"
        code = "payment_required"

    @app.get("/pay")
    def pay():
        raise PaymentRequired("subscription lapsed")

    res = app.test_client().get("/pay")

    assert res.status_code == 402
    assert res.get_json()["detail"] == "subscription lapsed"


def test_api_error_5xx_logs_an_error_without_a_traceback(app, caplog):
    """A raised ApiError is a decision, not a crash (2026-10-14).

    Until then every 5xx ``ApiError`` went through ``logger.exception``, so a
    feature that was deliberately switched off -- `research_disabled`, the
    default state of CompanyLens research -- wrote an ERROR line with a stack
    pointing at its own ``raise`` on every hit. 5xx stays ERROR (Sentry's
    default logging integration only turns ERROR into an event, so a real
    misconfiguration must keep alerting), 4xx stays INFO, neither carries
    ``exc_info``, and a subclass can lower its own level
    for a state that is expected in normal operation. The catch-all 500 handler
    for unexpected exceptions is untouched and keeps its traceback.
    """
    import logging

    class SwitchedOff(ApiError):
        status = 503
        title = "Switched off"
        code = "switched_off"

    class SwitchedOffQuietly(SwitchedOff):
        code = "switched_off_quietly"
        log_level = logging.INFO

    class NotFoundHere(ApiError):
        status = 404
        title = "Not found"
        code = "not_found_here"

    # Endpoint names are explicit: the shared `app` fixture already carries a
    # `missing` endpoint from another test in this module.
    @app.get("/log-level/off", endpoint="log_level_off")
    def _off():
        raise SwitchedOff("off")

    @app.get("/log-level/off-quietly", endpoint="log_level_off_quietly")
    def _off_quietly():
        raise SwitchedOffQuietly("off")

    @app.get("/log-level/missing", endpoint="log_level_missing")
    def _missing():
        raise NotFoundHere("missing")

    client = app.test_client()
    with caplog.at_level(logging.DEBUG, logger="solverah.errors"):
        assert client.get("/log-level/off").status_code == 503
        assert client.get("/log-level/off-quietly").status_code == 503
        assert client.get("/log-level/missing").status_code == 404

    records = {r.code: r for r in caplog.records if r.getMessage() == "api_error"}
    assert set(records) == {"switched_off", "switched_off_quietly", "not_found_here"}
    assert records["switched_off"].levelno == logging.ERROR
    assert records["switched_off_quietly"].levelno == logging.INFO
    assert records["not_found_here"].levelno == logging.INFO
    assert all(r.exc_info is None for r in records.values())


# ------------------------------------------------------------------- probes
def _health_app(checks, info=None):
    application = Flask(__name__)
    register_error_handlers(application)
    application.register_blueprint(
        create_health_blueprint(checks=checks, release="v1.2.3", info=info)
    )
    return application.test_client()


def test_healthz_is_ok_with_no_dependencies():
    """Liveness must not depend on anything external: a database blip would
    otherwise fail liveness on every replica and restart the whole fleet."""
    res = _health_app({}).get("/healthz")

    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"
    assert res.get_json()["release"] == "v1.2.3"


def test_healthz_ignores_a_broken_dependency():
    def broken():
        raise RuntimeError("database is down")

    res = _health_app({"database": broken}).get("/healthz")

    assert res.status_code == 200


def test_readyz_reports_ready_when_checks_pass():
    res = _health_app({"database": lambda: None}).get("/readyz")
    body = res.get_json()

    assert res.status_code == 200
    assert body["status"] == "ready"
    assert body["checks"]["database"]["ok"] is True
    assert isinstance(body["checks"]["database"]["duration_ms"], float)


def test_readyz_returns_503_when_a_check_fails():
    def broken():
        raise RuntimeError("could not connect")

    res = _health_app({"database": broken}).get("/readyz")

    assert res.status_code == 503
    assert res.get_json()["status"] == "not_ready"
    assert res.get_json()["checks"]["database"]["ok"] is False


def test_readyz_reports_every_check_not_just_the_first_failure():
    res = _health_app(
        {"database": lambda: None, "redis": _raise, "storage": lambda: None}
    ).get("/readyz")
    checks = res.get_json()["checks"]

    assert res.status_code == 503
    assert checks["database"]["ok"] is True
    assert checks["redis"]["ok"] is False
    assert checks["storage"]["ok"] is True


def test_readyz_does_not_disclose_the_failure_reason():
    """The probe is unauthenticated; echoing a driver error discloses topology."""
    def broken():
        raise RuntimeError("FATAL: password authentication failed for user 'solverah_prod'")

    res = _health_app({"database": broken}).get("/readyz")

    assert "password authentication" not in repr(res.get_json())
    assert "solverah_prod" not in repr(res.get_json())


def test_readyz_reports_informational_fields_in_the_payload():
    res = _health_app(
        {"database": lambda: None},
        info={"outbox": lambda: {"pending": 2, "parked": 1}},
    ).get("/readyz")
    body = res.get_json()

    assert res.status_code == 200
    assert body["status"] == "ready"
    assert body["outbox"] == {"pending": 2, "parked": 1}


def test_readyz_info_fields_never_flip_readiness():
    """A deep outbox means email is behind, not that the process cannot serve.

    The trap this guards: wiring the depth counter into `checks` instead of
    `info` would 503 the probe on a backlog, pulling every instance out of
    rotation at once over a condition that does not affect serving traffic.
    """
    res = _health_app(
        {"database": lambda: None},
        info={"outbox": lambda: {"pending": 10_000, "parked": 10_000}},
    ).get("/readyz")

    assert res.status_code == 200
    assert res.get_json()["status"] == "ready"


def test_readyz_survives_a_broken_info_provider():
    """Reporting must not break the probe: a raising provider is omitted, not fatal."""
    res = _health_app({"database": lambda: None}, info={"outbox": _raise}).get("/readyz")
    body = res.get_json()

    assert res.status_code == 200
    assert body["status"] == "ready"
    assert "outbox" not in body


def _raise():
    raise RuntimeError("redis unreachable")
