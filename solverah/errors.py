"""RFC 9457 Problem Details error handling.

The application currently registers **zero** ``@app.errorhandler`` callbacks.
Two consequences follow:

  * An unhandled exception returns Werkzeug's default **HTML** 500 page to a
    client that sent ``Accept: application/json`` and is parsing JSON.  The
    frontend's ``fetchWithAuth`` calls ``res.json()``, gets a parse error, and
    reports "Unexpected response from server" instead of the real failure.
  * Error bodies differ across 38 handlers -- ``{"error": ...}`` in most,
    ``{"message": ...}`` in others -- so the client cannot render errors
    uniformly and has to guess which key to read.

This module gives every failure one shape, keyed to
`RFC 9457 <https://www.rfc-editor.org/rfc/rfc9457>`_::

    {
      "type":       "https://solverah.com/errors/validation",
      "title":      "Validation failed",
      "status":     422,
      "detail":     "linkedin_url must be an HTTPS linkedin.com URL",
      "instance":   "/api/v1/me/profile",
      "request_id": "4f3c...",
      "errors":     [{"field": "linkedin_url", "code": "invalid_url"}]
    }

Unexpected exceptions are logged with a traceback and answered with a generic
500 that carries only the ``request_id``.  Driver messages, SQL, and stack
frames never reach a client -- they are how an attacker maps a schema.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .observability.logging import current_request_id, get_logger

__all__ = [
    "ApiError",
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "GoneError",
    "NotFoundError",
    "ProblemDetail",
    "RateLimitError",
    "ValidationError",
    "register_error_handlers",
]

logger = get_logger("solverah.errors")

ERROR_BASE_URI = "https://solverah.com/errors"
PROBLEM_CONTENT_TYPE = "application/problem+json"


class ProblemDetail:
    """An RFC 9457 problem document."""

    def __init__(
        self,
        status: int,
        title: str,
        code: str,
        detail: Optional[str] = None,
        errors: Optional[List[Dict[str, Any]]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status = status
        self.title = title
        self.code = code
        self.detail = detail
        self.errors = errors or []
        self.extra = extra or {}

    def to_dict(self, instance: Optional[str] = None) -> Dict[str, Any]:
        """Serialise to the wire format, stamping in the current request id."""
        body: Dict[str, Any] = {
            "type": "%s/%s" % (ERROR_BASE_URI, self.code),
            "title": self.title,
            "status": self.status,
        }
        if self.detail:
            body["detail"] = self.detail
        if instance:
            body["instance"] = instance
        rid = current_request_id()
        if rid:
            body["request_id"] = rid
        if self.errors:
            body["errors"] = self.errors
        body.update(self.extra)
        return body


class ApiError(Exception):
    """Base for errors that map to a deliberate HTTP response.

    Raising one of these from a service says "this is a known, expected failure
    mode with a defined status" -- as opposed to an unexpected exception, which
    becomes a 500 and pages someone.
    """

    status = 500
    title = "Internal server error"
    code = "internal"

    def __init__(
        self,
        detail: Optional[str] = None,
        errors: Optional[List[Dict[str, Any]]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.errors = errors or []
        self.extra = extra or {}

    def to_problem(self) -> ProblemDetail:
        return ProblemDetail(
            status=self.status,
            title=self.title,
            code=self.code,
            detail=self.detail,
            errors=self.errors,
            extra=self.extra,
        )


class ValidationError(ApiError):
    """Request body or parameters failed validation."""

    status = 422
    title = "Validation failed"
    code = "validation"


class AuthenticationError(ApiError):
    """No valid credentials were presented."""

    status = 401
    title = "Authentication required"
    code = "unauthenticated"


class AuthorizationError(ApiError):
    """Credentials are valid but insufficient for this resource."""

    status = 403
    title = "Forbidden"
    code = "forbidden"


class NotFoundError(ApiError):
    """The resource does not exist, or is not visible to this principal.

    Deliberately indistinguishable from "exists but you may not see it": telling
    the two apart lets an attacker enumerate resources they cannot read.
    """

    status = 404
    title = "Not found"
    code = "not_found"


class ConflictError(ApiError):
    """The request conflicts with current state (duplicate, stale version)."""

    status = 409
    title = "Conflict"
    code = "conflict"


class GoneError(ApiError):
    """The operation existed and was deliberately removed.

    Distinct from :class:`NotFoundError` on purpose: a 404 for a route a client
    shipped against says "you never had this", which sends the caller hunting
    for a typo. 410 says "this was here and is not coming back" -- and the
    problem document is expected to carry where the work moved (Phase 3c uses
    ``extra`` for the replacement path).
    """

    status = 410
    title = "Gone"
    code = "gone"


class RateLimitError(ApiError):
    """The caller exceeded a rate limit."""

    status = 429
    title = "Too many requests"
    code = "rate_limited"


def register_error_handlers(app) -> None:
    """Attach Problem Details handlers to a Flask app.

    Registers, in order of specificity:
      * :class:`ApiError` and subclasses -> their declared status.
      * ``werkzeug.exceptions.HTTPException`` -> its status, JSON-ified.  This is
        what converts Flask's own 404/405/413/429 HTML pages into JSON.
      * ``Exception`` -> a logged 500 carrying only the request id.

    Safe to call on an app that also serves non-API routes: the handlers respond
    in JSON regardless, which is correct for an API-only service and explicit
    for anything else.
    """
    from flask import jsonify, request
    from werkzeug.exceptions import HTTPException

    def _respond(problem: ProblemDetail):
        response = jsonify(problem.to_dict(instance=request.path))
        response.status_code = problem.status
        response.mimetype = PROBLEM_CONTENT_TYPE
        return response

    @app.errorhandler(ApiError)
    def _handle_api_error(exc: ApiError):
        # 4xx is the client's problem and is expected traffic; 5xx is ours.
        if exc.status >= 500:
            logger.exception(
                "api_error", extra={"event": "api_error", "code": exc.code, "status": exc.status}
            )
        else:
            logger.info(
                "api_error",
                extra={"event": "api_error", "code": exc.code, "status": exc.status},
            )
        return _respond(exc.to_problem())

    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException):
        status = exc.code or 500
        problem = ProblemDetail(
            status=status,
            title=exc.name or "Error",
            code=_HTTP_CODE_SLUGS.get(status, "http_error"),
            # exc.description is framework text ("The requested URL was not
            # found..."), never attacker-controlled or internal.
            detail=exc.description if status < 500 else None,
        )
        if status >= 500:
            logger.exception("http_exception", extra={"event": "http_exception", "status": status})
        return _respond(problem)

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        # The traceback goes to the log, keyed by request_id.  The client gets
        # the id and nothing else -- no exception class, no message, no SQL.
        logger.exception(
            "unhandled_exception",
            extra={"event": "unhandled_exception", "exc_type": type(exc).__name__},
        )
        return _respond(
            ProblemDetail(
                status=500,
                title="Internal server error",
                code="internal",
                detail="An unexpected error occurred. Quote the request_id when reporting this.",
            )
        )


_HTTP_CODE_SLUGS = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation",
    429: "rate_limited",
    500: "internal",
    502: "upstream_error",
    503: "unavailable",
    504: "upstream_timeout",
}
