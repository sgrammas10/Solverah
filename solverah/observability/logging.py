"""Structured logging with request correlation and PII redaction.

The current app logs unstructured strings through ``app.logger`` at 18 call
sites and has no request identifier at all, so two interleaved requests in a
multi-worker deploy cannot be told apart in a log aggregator.

This module gives every request an id, threads it through logs and responses,
and emits one machine-parseable access line per request:

    {"ts":"2026-08-22T14:03:11.482Z","level":"info","event":"http_request",
     "request_id":"01JX8T3Q...","method":"GET","path":"/api/v1/me",
     "status":200,"duration_ms":47,"user_id":8123,...}

The ``request_id`` is echoed on the response as ``X-Request-Id`` and is the
value stamped into ``audit_events.request_id``, so a support ticket quoting one
id resolves to the exact log line, audit row, and trace.

No third-party dependency: this is stdlib ``logging`` with a custom formatter,
so it works in the current deployment without adding a package.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

__all__ = [
    "REDACTED",
    "current_request_id",
    "get_logger",
    "init_logging",
    "install_request_logging",
    "new_request_id",
    "set_request_context",
]

REDACTED = "[redacted]"

# ContextVars, not thread-locals: they are correct under gthread/gevent workers
# and survive into asyncio if the app ever moves to an ASGI server.
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_user_id: ContextVar[Optional[int]] = ContextVar("log_user_id", default=None)

# Keys whose values must never reach a log sink, matched case-insensitively as
# substrings so `user_email`, `X-CSRF-TOKEN`, and `refresh_token` are all caught.
_SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "email",
    "phone",
    "resume_text",
    "ssn",
)

# LogRecord attributes that are not caller-supplied `extra` fields.
_RESERVED_RECORD_ATTRS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "taskName", "thread", "threadName",
    }
)


def new_request_id() -> str:
    """Return a fresh request id (hex, no dashes — cheaper to grep and index)."""
    return uuid.uuid4().hex


def current_request_id() -> Optional[str]:
    """Return the id of the request being handled, or None outside a request."""
    return _request_id.get()


def set_request_context(request_id: Optional[str] = None, user_id: Optional[int] = None) -> str:
    """Bind correlation values for the current context.

    Args:
        request_id: Id to bind.  Generated when omitted.
        user_id: Authenticated user id, once known.  Callers may set this later
            in the request (after JWT verification) than the id.

    Returns:
        The bound request id.
    """
    rid = request_id or new_request_id()
    _request_id.set(rid)
    if user_id is not None:
        _user_id.set(user_id)
    return rid


def redact(value: Any, _depth: int = 0) -> Any:
    """Recursively replace sensitive values in *value* with :data:`REDACTED`.

    Applied to every structured field before it is serialised, so redaction is a
    property of the logger rather than something each of 18 call sites has to
    remember.  Depth is bounded to keep a cyclic or deeply nested payload from
    turning a log call into a stack overflow.
    """
    if _depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            key_l = str(k).lower()
            if any(part in key_l for part in _SENSITIVE_KEY_PARTS):
                out[str(k)] = REDACTED
            else:
                out[str(k)] = redact(v, _depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v, _depth + 1) for v in value[:50]]
    return value


class JsonFormatter(logging.Formatter):
    """Render a :class:`logging.LogRecord` as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + ".%03dZ" % record.msecs,
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        rid = _request_id.get()
        if rid:
            payload["request_id"] = rid
        uid = _user_id.get()
        if uid is not None:
            payload["user_id"] = uid

        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS or key.startswith("_"):
                continue
            if key in payload:
                continue
            payload[key] = redact(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # default=str so an unexpected type degrades to its repr instead of
        # raising inside the logging call and losing the event entirely.
        return json.dumps(payload, default=str, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        rid = _request_id.get()
        prefix = "[%s] " % rid[:8] if rid else ""
        base = "%s%-7s %s: %s" % (
            prefix,
            record.levelname,
            record.name,
            record.getMessage(),
        )
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _RESERVED_RECORD_ATTRS and not k.startswith("_")
        }
        if extras:
            base += "  " + " ".join(
                "%s=%s" % (k, redact(v)) for k, v in sorted(extras.items())
            )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def init_logging(level: str = "INFO", fmt: str = "json", service: str = "api",
                 release: str = "dev") -> None:
    """Configure root logging for the process.

    Replaces any existing root handlers so gunicorn's default handlers do not
    produce a second, unstructured copy of every line.

    Args:
        level: Standard logging level name.
        fmt: ``"json"`` for production, ``"console"`` for local development.
        service: Service name stamped on every record.
        release: Deployed version, so a log line identifies the code that wrote it.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else ConsoleFormatter())
    handler.addFilter(_ServiceFilter(service=service, release=release))
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for noisy in _THIRD_PARTY_NOISE:
        logging.getLogger(noisy).setLevel(logging.WARNING)


# Third-party loggers pinned to WARNING regardless of the app's level.
#
# At DEBUG these emit per-socket chatter that says nothing the access log does
# not, and drowns application events. httpx/httpcore additionally log during
# interpreter shutdown (openai's client closes its transport from __del__), by
# which point the stdout handler's stream is closed -- which surfaces as a
# "ValueError: I/O operation on closed file" traceback after the test summary.
_THIRD_PARTY_NOISE = (
    "werkzeug",
    "botocore",
    "boto3",
    "urllib3",
    "s3transfer",
    "httpx",
    "httpcore",
    "openai",
    "asyncio",
)


class _ServiceFilter(logging.Filter):
    """Stamp static service identity onto every record."""

    def __init__(self, service: str, release: str) -> None:
        super().__init__()
        self.service = service
        self.release = release

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self.service
        record.version = self.release
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger.  Thin wrapper, present so call sites import one name."""
    return logging.getLogger(name)


# --------------------------------------------------------------------------- Flask
def install_request_logging(app, header: str = "X-Request-Id") -> None:
    """Attach request-id propagation and access logging to a Flask app.

    Behaviour:
      * An inbound ``X-Request-Id`` is adopted when it looks safe, so a trace
        started at the edge (Cloudflare, load balancer) stays joined up.  It is
        length- and charset-checked first: the value lands in logs and in
        ``audit_events``, and an unbounded attacker-controlled string there is a
        log-injection and storage-bloat vector.
      * Every response carries the id back, so a user reporting an error can
        quote something an engineer can search.
      * One ``http_request`` line per request with status and duration.

    Args:
        app: The Flask application.
        header: Request/response header carrying the correlation id.
    """
    from flask import g, request

    access_log = logging.getLogger("solverah.access")

    @app.before_request
    def _begin_request():  # pragma: no cover - exercised via the test client
        inbound = request.headers.get(header, "")
        rid = inbound if _is_safe_request_id(inbound) else new_request_id()
        set_request_context(request_id=rid)
        g._request_started_at = time.perf_counter()

    @app.after_request
    def _end_request(response):  # pragma: no cover - exercised via the test client
        rid = current_request_id()
        if rid:
            response.headers[header] = rid

        started = getattr(g, "_request_started_at", None)
        duration_ms = round((time.perf_counter() - started) * 1000, 2) if started else None

        # Health probes fire every few seconds; logging them buries real traffic.
        if request.path not in _QUIET_PATHS:
            access_log.info(
                "%s %s %s",
                request.method,
                request.path,
                response.status_code,
                extra={
                    "event": "http_request",
                    "method": request.method,
                    "path": request.path,
                    "route": request.url_rule.rule if request.url_rule else None,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "remote_addr": request.remote_addr,
                },
            )
        return response

    @app.teardown_request
    def _clear_request(_exc=None):  # pragma: no cover
        _request_id.set(None)
        _user_id.set(None)


_QUIET_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})

_REQUEST_ID_MAX_LEN = 128
_REQUEST_ID_ALLOWED = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)


def _is_safe_request_id(value: str) -> bool:
    """Return True if an inbound correlation id is safe to adopt and store."""
    if not value or len(value) > _REQUEST_ID_MAX_LEN:
        return False
    return all(ch in _REQUEST_ID_ALLOWED for ch in value)


def bind_user(user_id: Optional[int]) -> None:
    """Attach the authenticated user id to the current logging context."""
    _user_id.set(user_id)


# Re-exported for callers that want the process id without importing os.
PROCESS_ID = os.getpid()
