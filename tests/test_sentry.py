"""Sentry wiring: inline-task capture, PII scrubbing, probe-transaction dropping.

Nothing here touches the network.  Every test that needs a live SDK initialises
it through the same ``init_sentry()`` production uses, with the SDK's function
transport handing captured events to a plain list -- so what is asserted on is
the real event the SDK would have sent, filters and all.

The SDK is process-global; the ``captured`` fixture detaches the client on
teardown so no other test in the suite can accidentally report through it.
"""

import pytest
import sentry_sdk

from solverah.config import Settings
from solverah.observability.logging import REDACTED
from solverah.observability.sentry import (
    _drop_probe_transaction,
    _scrub_event,
    init_sentry,
)

DSN = "https://publickey123@o0000.ingest.sentry.io/1234"

_ENV = {
    "APP_ENV": "testing",
    "DATABASE_URL": "postgresql://u:p@localhost:5432/solverah",
    "JWT_SECRET_KEY": "x" * 40,
    "RELEASE": "test-release-abc123",
    "SENTRY_DSN": DSN,
}


class _CapturingTransport(sentry_sdk.Transport):
    """Collects outgoing error events in a list instead of sending them."""

    def __init__(self, events):
        super().__init__()
        self._events = events

    def capture_envelope(self, envelope):
        event = envelope.get_event()
        if event is not None:
            self._events.append(event)


@pytest.fixture()
def captured():
    """A live SDK whose outgoing events land in the returned list."""
    events = []
    init_sentry(Settings.from_env(_ENV), transport=_CapturingTransport(events))
    yield events
    sentry_sdk.get_global_scope().set_client(None)


# ── Capture ─────────────────────────────────────────────────────────────────


def test_exception_inside_an_inline_task_is_captured(captured):
    """The Scenario A regression this file exists for.

    Production has no broker, so Celery tasks run inline in the request -- and
    ``task_eager_propagates=False`` means the exception never reaches the
    caller: the request 200s, the EagerResult quietly records the failure, and
    without the SDK's Celery integration (which hooks the task tracer that
    eager execution also runs through) the error would be invisible everywhere.
    """
    from solverah.infra.queue import celery_app

    @celery_app.task(name="tests.sentry.boom")
    def boom():
        raise RuntimeError("boom inside an inline task")

    previous = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    try:
        result = boom.delay()
    finally:
        celery_app.conf.task_always_eager = previous

    # The caller saw no exception -- exactly the silence being guarded against.
    assert result.failed()

    sentry_sdk.flush()
    values = [
        value
        for event in captured
        for value in (event.get("exception") or {}).get("values") or []
    ]
    assert any(
        value.get("type") == "RuntimeError"
        and "inline task" in (value.get("value") or "")
        for value in values
    ), "the inline task's exception never reached Sentry"


def test_captured_events_carry_the_release_the_config_already_holds(captured):
    """Release tagging reuses settings.release -- the string /healthz echoes."""
    sentry_sdk.capture_exception(ValueError("tag me"))
    sentry_sdk.flush()

    assert captured, "no event captured"
    assert captured[-1]["release"] == "test-release-abc123"
    assert captured[-1]["environment"] == "testing"


# ── Scrubbing (mirrors solverah.observability.logging.redact) ───────────────


def test_before_send_applies_the_logging_redaction_rules():
    event = {
        "request": {
            "url": "https://api.solverah.com/api/v1/login",
            "data": {"password": "hunter2"},
            "headers": {
                "Cookie": "access_token=abc",
                "X-CSRF-TOKEN": "csrf-value",
                "Accept": "application/json",
            },
        },
        "extra": {"user_email": "person@example.test", "attempts": 3},
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": "boom",
                    "stacktrace": {
                        "frames": [
                            {"vars": {"reset_token": "abc123", "attempt": 1}}
                        ]
                    },
                }
            ]
        },
        "breadcrumbs": {
            "values": [{"data": {"api_key": "sk-live", "route": "/login"}}]
        },
    }

    out = _scrub_event(event, {})

    # Request bodies are never attached, full stop.
    assert "data" not in out["request"]
    assert out["request"]["headers"]["Cookie"] == REDACTED
    assert out["request"]["headers"]["X-CSRF-TOKEN"] == REDACTED
    assert out["request"]["headers"]["Accept"] == "application/json"
    assert out["extra"]["user_email"] == REDACTED
    assert out["extra"]["attempts"] == 3
    frame_vars = out["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]
    assert frame_vars["reset_token"] == REDACTED
    assert frame_vars["attempt"] == 1
    crumb = out["breadcrumbs"]["values"][0]["data"]
    assert crumb["api_key"] == REDACTED
    assert crumb["route"] == "/login"


# ── Probe transactions ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "transaction,url",
    [
        ("/healthz", "https://api.solverah.com/healthz"),
        ("/readyz", "https://api.solverah.com/readyz"),
        # Flask's default transaction_style names by endpoint, not URL.
        ("health.healthz", ""),
        ("health.readyz", ""),
    ],
)
def test_probe_transactions_are_dropped(transaction, url):
    """Probes fire every few seconds; sent as transactions they would eat the
    whole quota.  traces_sample_rate is 0 today, so this is the backstop for
    the day tracing is turned on."""
    event = {"type": "transaction", "transaction": transaction, "request": {"url": url}}

    assert _drop_probe_transaction(event, {}) is None


def test_ordinary_transactions_are_kept():
    event = {
        "type": "transaction",
        "transaction": "/api/v1/me",
        "request": {"url": "https://api.solverah.com/api/v1/me"},
    }

    assert _drop_probe_transaction(event, {}) is event
