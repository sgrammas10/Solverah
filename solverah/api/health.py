"""Liveness and readiness endpoints.

The application currently exposes neither, which means:

  * A container orchestrator cannot tell a wedged process from a healthy one, so
    a hung worker keeps receiving traffic until a human notices.
  * A rolling deploy cannot know when a new instance is able to serve, so it
    either shifts traffic to an instance whose database pool is not warm, or it
    waits on a fixed sleep and hopes.

The two probes answer deliberately different questions:

``GET /healthz`` -- *is this process alive?*
    Touches nothing external.  Must stay fast and dependency-free: if it checked
    the database, a brief database blip would make every replica fail liveness
    at once and the orchestrator would restart the entire fleet, converting a
    recoverable dependency outage into a self-inflicted full outage.

``GET /readyz`` -- *can this process serve traffic right now?*
    Checks the dependencies a request actually needs.  A failure removes the
    instance from the load balancer without killing it, so it rejoins on its own
    when the dependency recovers.

Neither is rate limited (probes fire continuously), neither is logged as traffic
(see ``_QUIET_PATHS`` in ``solverah.observability.logging``), and neither
requires authentication -- but ``/readyz`` reports only booleans and durations,
never a driver message, since an unauthenticated endpoint that echoes a database
error discloses topology.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify

from ..observability.logging import get_logger

__all__ = ["create_health_blueprint"]

logger = get_logger("solverah.health")

# A probe that hangs is worse than one that fails: the orchestrator waits for its
# own timeout while the instance keeps taking traffic.  Bound each check.
DEFAULT_CHECK_TIMEOUT_MS = 2000


def create_health_blueprint(
    checks: Optional[Dict[str, Callable[[], None]]] = None,
    release: str = "dev",
    started_at: Optional[float] = None,
) -> Blueprint:
    """Build the health blueprint.

    Args:
        checks: Named readiness checks.  Each is a zero-argument callable that
            returns normally when healthy and raises when not.  Injected rather
            than imported so tests can supply a failing check without a database,
            and so this module depends on no particular extension.
        release: Deployed version string, echoed for deploy verification.
        started_at: Process start time (``time.time()``), for uptime reporting.

    Returns:
        A blueprint exposing ``/healthz`` and ``/readyz``.
    """
    checks = checks or {}
    boot_time = started_at if started_at is not None else time.time()
    bp = Blueprint("health", __name__)

    @bp.get("/healthz")
    def healthz():
        """Liveness: the process is up and the WSGI stack responds."""
        return jsonify(
            {
                "status": "ok",
                "release": release,
                "uptime_seconds": round(time.time() - boot_time, 1),
            }
        )

    @bp.get("/readyz")
    def readyz():
        """Readiness: every registered dependency check passes."""
        results: Dict[str, Any] = {}
        ready = True

        for name, check in checks.items():
            ok, duration_ms, failure = _run_check(check)
            results[name] = {"ok": ok, "duration_ms": duration_ms}
            if not ok:
                ready = False
                # Full reason to the log (with request_id), boolean to the wire.
                logger.warning(
                    "readiness_check_failed",
                    extra={"event": "readiness_check_failed", "check": name, "reason": failure},
                )

        body = {"status": "ready" if ready else "not_ready", "release": release, "checks": results}
        return jsonify(body), (200 if ready else 503)

    return bp


def _run_check(check: Callable[[], None]) -> Tuple[bool, float, Optional[str]]:
    """Run one readiness check, capturing outcome, duration, and failure reason."""
    start = time.perf_counter()
    try:
        check()
    except Exception as exc:  # noqa: BLE001 - any failure means "not ready"
        return False, round((time.perf_counter() - start) * 1000, 2), "%s: %s" % (
            type(exc).__name__,
            exc,
        )
    return True, round((time.perf_counter() - start) * 1000, 2), None


def database_check(db, timeout_ms: int = DEFAULT_CHECK_TIMEOUT_MS) -> Callable[[], None]:
    """Return a readiness check that issues ``SELECT 1`` against *db*.

    Args:
        db: The Flask-SQLAlchemy instance.
        timeout_ms: Advisory statement timeout.  Applied only on backends that
            support it; SQLite silently has no equivalent.

    Returns:
        A zero-argument callable suitable for :func:`create_health_blueprint`.
    """
    from sqlalchemy import text

    def _check() -> None:
        db.session.execute(text("SELECT 1"))
        # A read-only probe must not leave an open transaction behind: an idle
        # transaction holds a connection and blocks VACUUM on a busy primary.
        db.session.rollback()

    _check.__doc__ = "database connectivity (SELECT 1, %dms budget)" % timeout_ms
    return _check


def redis_check(client) -> Callable[[], None]:
    """Return a readiness check that PINGs a Redis client."""

    def _check() -> None:
        client.ping()

    return _check


def compose_checks(*pairs: Tuple[str, Callable[[], None]]) -> Dict[str, Callable[[], None]]:
    """Build the checks mapping from ``(name, callable)`` pairs, skipping ``None``."""
    out: Dict[str, Callable[[], None]] = {}
    skipped: List[str] = []
    for name, check in pairs:
        if check is None:
            skipped.append(name)
            continue
        out[name] = check
    if skipped:
        logger.info(
            "readiness_checks_skipped",
            extra={"event": "readiness_checks_skipped", "skipped": skipped},
        )
    return out
