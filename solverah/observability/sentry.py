"""Sentry error tracking, gated on ``SENTRY_DSN``.

Production errors are invisible today -- no tracker on either tier, 14 days of
un-aggregated Render logs as the entire forensic record (PROD_READINESS_2026-09
finding 4).  This module is the API half of the fix.

The gate is the configuration, not this module: ``create_app()`` calls
:func:`init_sentry` only when ``settings.sentry_dsn`` is set, so an environment
without the variable (CI sets five, none of them this one) never imports a
behaviour change.  A DSN that is set but malformed never reaches here at all --
``solverah.config`` rejects it with the other fatal validation problems, so the
SDK cannot throw its own error mid-boot.

Deliberate choices, in the order an auditor would ask about them:

* **Errors only.** ``traces_sample_rate`` is 0; tracing is a later decision
  with its own quota maths.  The ``before_send_transaction`` hook drops the
  ``/healthz``/``/readyz`` probes anyway, so if someone later turns tracing on,
  probes firing every few seconds cannot eat the quota.
* **No PII by default, and none by accident.** ``send_default_pii=False``,
  request bodies are never attached (``max_request_body_size="never"``, and
  :func:`_scrub_event` drops any body a future SDK attaches regardless), and
  every user-shaped field is scrubbed with the *same* key-substring rule the
  structured-logging formatter applies -- one redaction policy, defined once in
  ``solverah.observability.logging``, not a second list that can drift.
* **Release tagging reuses the config's release string** -- the same value
  ``/healthz`` echoes -- rather than introducing a second source of version
  truth.

Under Scenario A (no broker) Celery tasks run inline in the request, and their
exceptions are captured too: the SDK's Celery integration hooks the task
tracer, which eager execution also goes through, so ``task_eager_propagates=
False`` swallowing the exception from the *caller* does not hide it from
Sentry.  ``tests/test_sentry.py`` proves that path with the SDK's function
transport.
"""

from __future__ import annotations

from typing import Any, Optional

import sentry_sdk

from solverah.config import Settings
from solverah.observability.logging import redact

__all__ = ["init_sentry"]

#: Transaction names the Flask integration can produce for the probes --
#: ``transaction_style`` decides between endpoint and URL naming, and this
#: module should not care which one a future config picks.
_PROBE_TRANSACTIONS = frozenset(
    {"/healthz", "/readyz", "health.healthz", "health.readyz"}
)
_PROBE_PATHS = ("/healthz", "/readyz")


def init_sentry(settings: Settings, transport: Optional[Any] = None) -> None:
    """Initialise the Sentry SDK from validated *settings*.

    Args:
        settings: Validated settings with ``sentry_dsn`` set -- the caller
            checks, so an unset DSN cannot half-initialise the SDK.
        transport: Test seam.  ``tests/test_sentry.py`` passes a capturing
            function here so assertions run against real captured events with
            no network; production passes nothing.
    """
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        release=settings.release,
        environment=settings.env,
        send_default_pii=False,
        traces_sample_rate=0.0,
        max_request_body_size="never",
        before_send=_scrub_event,
        before_send_transaction=_drop_probe_transaction,
        transport=transport,
    )


def _scrub_event(event: dict, hint: dict) -> dict:
    """Apply the logging module's redaction rules to an outgoing error event.

    Each user-data subtree is scrubbed independently rather than the whole
    event at once: ``redact()`` bounds recursion depth, and a stack trace
    nested under the event root would hit that bound and be truncated.
    """
    request = event.get("request")
    if isinstance(request, dict):
        # Request bodies are never attached, whatever a future SDK default says.
        request.pop("data", None)
        for key in ("headers", "cookies", "env"):
            if isinstance(request.get(key), (dict, list)):
                request[key] = redact(request[key])

    for key in ("extra", "user", "contexts"):
        if isinstance(event.get(key), dict):
            event[key] = redact(event[key])

    breadcrumbs = event.get("breadcrumbs")
    values = breadcrumbs.get("values") if isinstance(breadcrumbs, dict) else breadcrumbs
    if isinstance(values, list):
        for crumb in values:
            if isinstance(crumb, dict) and isinstance(crumb.get("data"), dict):
                crumb["data"] = redact(crumb["data"])

    # Local variables in stack frames are where a `password` argument actually
    # lives when an auth handler raises.
    for exc in (event.get("exception") or {}).get("values") or []:
        for frame in (exc.get("stacktrace") or {}).get("frames") or []:
            if isinstance(frame, dict) and isinstance(frame.get("vars"), dict):
                frame["vars"] = redact(frame["vars"])

    return event


def _drop_probe_transaction(event: dict, hint: dict) -> Optional[dict]:
    """Drop health-probe transactions; they fire every few seconds."""
    name = event.get("transaction") or ""
    request = event.get("request")
    url = (request.get("url") or "") if isinstance(request, dict) else ""
    if name in _PROBE_TRANSACTIONS or url.split("?", 1)[0].endswith(_PROBE_PATHS):
        return None
    return event
