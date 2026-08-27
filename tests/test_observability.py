"""Tests for structured logging, request correlation, and PII redaction."""

import json
import logging

import pytest
from flask import Flask

from solverah.observability.logging import (
    REDACTED,
    ConsoleFormatter,
    JsonFormatter,
    _is_safe_request_id,
    current_request_id,
    install_request_logging,
    redact,
    set_request_context,
)


def _record(msg="hello", **extra):
    record = logging.LogRecord(
        name="solverah.test", level=logging.INFO, pathname=__file__,
        lineno=1, msg=msg, args=(), exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


# --------------------------------------------------------------------- format
def test_json_formatter_emits_one_parseable_line():
    out = JsonFormatter().format(_record("something happened", event="thing", count=3))
    parsed = json.loads(out)

    assert "\n" not in out
    assert parsed["message"] == "something happened"
    assert parsed["level"] == "info"
    assert parsed["event"] == "thing"
    assert parsed["count"] == 3
    assert parsed["ts"].endswith("Z")


def test_json_formatter_includes_request_context_when_bound():
    set_request_context(request_id="abc123", user_id=77)
    try:
        parsed = json.loads(JsonFormatter().format(_record()))
        assert parsed["request_id"] == "abc123"
        assert parsed["user_id"] == 77
    finally:
        set_request_context(request_id=None)


def test_json_formatter_survives_unserialisable_extra():
    """A bad value must degrade to its repr, never raise and lose the event."""
    class Opaque:
        def __repr__(self):
            return "<opaque>"

    parsed = json.loads(JsonFormatter().format(_record(thing=Opaque())))
    assert parsed["thing"] == "<opaque>"


def test_console_formatter_is_human_readable():
    out = ConsoleFormatter().format(_record("boot", event="startup"))
    assert "boot" in out
    assert "event=startup" in out


# --------------------------------------------------------------------- redact
@pytest.mark.parametrize(
    "key",
    ["password", "Password", "JWT_SECRET_KEY", "access_token", "Authorization",
     "Cookie", "api_key", "user_email", "phone_number", "resume_text"],
)
def test_sensitive_keys_are_redacted(key):
    assert redact({key: "sensitive"})[key] == REDACTED


def test_redaction_is_recursive():
    out = redact({"user": {"name": "Ada", "email": "ada@example.com"}})

    assert out["user"]["name"] == "Ada"
    assert out["user"]["email"] == REDACTED


def test_redaction_handles_lists_and_bounds_depth():
    assert redact({"items": [{"password": "x"}]})["items"][0]["password"] == REDACTED

    deep = current = {}
    for _ in range(20):
        current["next"] = {}
        current = current["next"]
    assert redact(deep) is not None   # bounded, does not recurse to overflow


def test_non_sensitive_values_pass_through():
    assert redact({"count": 3, "ok": True, "name": "solverah"}) == {
        "count": 3, "ok": True, "name": "solverah"
    }


# ------------------------------------------------------------- request id I/O
@pytest.mark.parametrize("value", ["abc-123", "01JX8T3Q4Y7ZK2M9", "a" * 128])
def test_safe_request_ids_are_adopted(value):
    assert _is_safe_request_id(value) is True


@pytest.mark.parametrize(
    "value",
    ["", "a" * 129, "has space", "new\nline", "semi;colon", "quote\"mark", "<script>"],
)
def test_unsafe_request_ids_are_rejected(value):
    """The id lands in logs and audit rows; unbounded attacker input there is
    a log-injection and storage-bloat vector."""
    assert _is_safe_request_id(value) is False


# ------------------------------------------------------------------ Flask glue
@pytest.fixture()
def app():
    application = Flask(__name__)
    install_request_logging(application)

    @application.get("/ping")
    def ping():
        return {"request_id": current_request_id()}

    return application


def test_response_carries_a_request_id(app):
    res = app.test_client().get("/ping")

    rid = res.headers["X-Request-Id"]
    assert rid
    assert res.get_json()["request_id"] == rid


def test_inbound_request_id_is_adopted(app):
    res = app.test_client().get("/ping", headers={"X-Request-Id": "edge-trace-1"})

    assert res.headers["X-Request-Id"] == "edge-trace-1"


def test_unsafe_inbound_request_id_is_replaced(app):
    # A newline cannot be pushed through the test client (Werkzeug rejects it at
    # the header layer), so the charset rule is exercised with characters that do
    # travel: spaces and angle brackets.
    hostile = "<script>alert(1)</script> and a space"
    res = app.test_client().get("/ping", headers={"X-Request-Id": hostile})

    assert res.headers["X-Request-Id"] != hostile
    assert res.headers["X-Request-Id"].isalnum()


def test_overlong_inbound_request_id_is_replaced(app):
    """An unbounded id would be stored on every audit row it touches."""
    res = app.test_client().get("/ping", headers={"X-Request-Id": "a" * 500})

    assert len(res.headers["X-Request-Id"]) == 32


def test_request_ids_are_unique_per_request(app):
    client = app.test_client()
    first = client.get("/ping").headers["X-Request-Id"]
    second = client.get("/ping").headers["X-Request-Id"]

    assert first != second


def test_context_is_cleared_between_requests(app):
    app.test_client().get("/ping")

    assert current_request_id() is None
