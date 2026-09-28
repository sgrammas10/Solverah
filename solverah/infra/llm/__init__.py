"""LLM provider clients.

Two providers, two purposes:

* **OpenAI** (``gpt-4o-mini`` by default) for the structured, JSON-mode calls --
  quiz insights and the three assessment narratives.  60-second timeout, two
  retries.
* **Groq** for the streaming agent chat.  It speaks the OpenAI wire protocol, so
  the same SDK works against a different ``base_url``.  30-second timeout, one
  retry, because a chat that is going to stream should fail fast rather than sit.

Both were module-level functions in ``app.py``, which meant the only way to give
a test a fake client was to patch a name on a 4,000-line module. They are the
substitution seam now: patch ``solverah.infra.llm.get_openai_client`` once and
every caller sees it.

Every call through these clients is **synchronous and on the request path**
(P0-6). ``gunicorn.conf.py`` carries a 120-second timeout to accommodate them,
which means one slow provider response occupies a whole sync worker for up to
two minutes and a provider slowdown becomes an outage. Phase 3 moves them to the
``llm`` queue; the agent stays inline but streams.
"""

from __future__ import annotations

import os

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - the SDK is a hard dependency in practice
    OpenAI = None

__all__ = [
    "DEFAULT_AGENT_MODEL",
    "default_agent_model",
    "get_agent_client",
    "get_openai_client",
    "groq_api_key",
]

#: Groq's small, fast model. Chosen for latency: the agent streams, so
#: time-to-first-token matters more than depth. Was ``llama-3.1-8b-instant``
#: until Groq retired it and every chat turn came back 422 "model not found";
#: ``SOLVERAH_AGENT_MODEL`` now swaps the model without a deploy.
DEFAULT_AGENT_MODEL = "openai/gpt-oss-20b"


def get_openai_client():
    """Build and return an OpenAI client with standard retry/timeout settings.

    Uses a 60-second timeout and 2 automatic retries to handle transient
    API errors without hanging the request indefinitely.

    Raises:
        RuntimeError: If the ``openai`` package is not installed or
                      OPENAI_API_KEY is missing from the environment.
    """
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK not installed")
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key, timeout=60.0, max_retries=2)


def groq_api_key() -> str:
    """The Groq key, read per call.

    Read at call time rather than at import, unlike the module-level
    ``_GROQ_API_KEY`` this replaces: a module-level read meant that setting the
    variable after import -- which is exactly what a test does -- had no effect.
    """
    return os.environ.get("GROQ_API_KEY", "").strip()


def get_agent_client():
    """Return an OpenAI-compatible Groq client."""
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK not installed")
    if not groq_api_key():
        raise RuntimeError("GROQ_API_KEY is not configured")
    return OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=groq_api_key(),
        timeout=30.0,
        max_retries=1,
    )


def default_agent_model() -> str:
    """The Groq model a chat turn uses when the client names none.

    ``SOLVERAH_AGENT_MODEL`` wins when set (read per call, like the key), so the
    next provider retirement is an env change rather than a code change.
    """
    return os.environ.get("SOLVERAH_AGENT_MODEL", "").strip() or DEFAULT_AGENT_MODEL
