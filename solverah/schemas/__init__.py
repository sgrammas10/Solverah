"""Pydantic v2 request and response models, one module per resource.

These describe the API's wire format.  In Phase 1a they are exactly that --
descriptive.  They are not enforced at runtime, because 1a's contract is that
request and response bodies do not change; a validator that rejected a body the
old handler accepted, or reshaped an error, would break that invisibly.

What keeps them from becoming fiction is the test suite: every resource's tests
push real responses from real handlers through the declared model, so a schema
that stops matching the handler fails a test rather than quietly shipping a
wrong OpenAPI document to whoever generates a client from it.

Conventions:

* ``model_config = ConfigDict(extra="allow")`` on response models that serialise
  the ``profile_data`` blob.  Until Phase 2 decomposes it, the exact key set is
  data-dependent, and a closed model would be a lie.  Models over fixed shapes
  are closed.
* Field names match the wire exactly, including the camelCase the frontend
  already reads.  Renaming them is Phase 1b's business, not the schema layer's.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "PROBLEM_RESPONSE_MODEL",
    "LegacyError",
    "ProblemDetailResponse",
    "ProblemDetailError",
    "SolverahModel",
    "OkResponse",
]


class SolverahModel(BaseModel):
    """Base for every schema in this package.

    ``extra="forbid"`` is the default because an undeclared key in a *request*
    is almost always a client bug or a renamed field, and because a closed model
    is what makes the generated client's types worth trusting.  Response models
    over the ``profile_data`` blob override it -- see the module docstring.
    """

    model_config = ConfigDict(extra="forbid")


class OkResponse(SolverahModel):
    """The bare acknowledgement several handlers return."""

    ok: bool = Field(description="Always true; the operation succeeded.")


class LegacyError(SolverahModel):
    """The pre-Phase-1 error body: ``{"error": "..."}``.

    Handlers return this from their own explicit failure branches, and Phase 1a
    keeps every one of them byte-for-byte.  It coexists with
    :class:`ProblemDetailResponse`, which is what the Phase 0 error handlers
    produce for anything a handler did not catch itself.

    The two shapes are why ``src/utils/apiError.ts`` reads both.  Phase 1b
    collapses them by moving handlers onto ``solverah.errors.ApiError``.
    """

    error: str = Field(description="Human-readable failure message.")


class ProblemDetailError(SolverahModel):
    """One field-level entry inside a problem document's ``errors`` array."""

    field: Optional[str] = Field(default=None, description="Offending field name.")
    code: Optional[str] = Field(default=None, description="Machine-readable reason.")

    model_config = ConfigDict(extra="allow")


class ProblemDetailResponse(SolverahModel):
    """RFC 9457 problem document, as emitted by ``solverah.errors``.

    Served with ``Content-Type: application/problem+json``.  This is the body
    for anything the handler did not answer itself: an unhandled exception, a
    404 on an unknown path, a 405, a 413 over ``MAX_CONTENT_LENGTH``, a 429 from
    the limiter.
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(description="URI identifying the error class.")
    title: str = Field(description="Short, stable summary of the problem type.")
    status: int = Field(description="HTTP status code, repeated in the body.")
    detail: Optional[str] = Field(default=None, description="Explanation of this occurrence.")
    instance: Optional[str] = Field(default=None, description="Path that produced it.")
    request_id: Optional[str] = Field(
        default=None,
        description="Correlation id, echoed as X-Request-Id. Quote it in bug reports.",
    )
    errors: List[ProblemDetailError] = Field(
        default_factory=list, description="Field-level detail, when applicable."
    )


#: Referenced by every operation's ``default`` response in the generated
#: document.  Aliased so ``solverah/openapi.py`` does not import a name that
#: reads like a schema it should be documenting per-route.
PROBLEM_RESPONSE_MODEL = ProblemDetailResponse


class ProfileDataModel(SolverahModel):
    """Base for models that carry part of the ``users.profile_data`` JSON blob.

    The blob is P0-1 in docs/ARCHITECTURE.md: a read-modify-write column with no
    schema, holding profile fields, quiz results, skills, proficiencies, culture
    preferences, and parser snapshots.  Its key set genuinely varies per user and
    per feature that has touched it, so these models declare the keys the API
    contract actually promises and allow the rest through rather than pretending
    to a completeness they cannot have.

    When Phase 2 decomposes the blob into columns, these are the models that
    tighten to ``extra="forbid"`` -- and because they sit at the API boundary,
    that decomposition does not have to reach the client.
    """

    model_config = ConfigDict(extra="allow")


def blob(description: str) -> Any:
    """Field helper for an opaque JSON sub-document inside ``profile_data``."""
    return Field(default_factory=dict, description=description)


AnyJson = Dict[str, Any]
