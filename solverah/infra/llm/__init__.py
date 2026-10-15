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

CompanyLens (decided 2026-10-13, ``docs/PRODUCT_DECISIONS.md`` §2) adds two
more, both for **background jobs only** -- never a request handler:

* **Anthropic** for company research (``get_research_client``; the call itself
  is :func:`solverah.infra.llm.research.run_research_call`). Web search and web
  fetch run server-side, so one call can take minutes. Contract: the prompt
  carries a company name and public URLs only -- never user PII.
* **OpenAI** for per-item scoring (``get_scorer_client``) on the pinned
  snapshot ``causal_graph/scorer_pipeline.py`` validated.

Both raise :class:`LLMProviderUnavailable` when the SDK or the key is missing,
the way a missing corpus raises ``CorpusUnavailable`` -- one typed failure the
service maps to a 503. Keys and model ids are read per call, never at import.
"""

from __future__ import annotations

import os

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - the SDK is a hard dependency in practice
    OpenAI = None

__all__ = [
    "AGENT_MAX_COMPLETION_TOKENS",
    "DEFAULT_AGENT_MODEL",
    "DEFAULT_RESEARCH_MODEL",
    "DEFAULT_SCORER_MODEL",
    "LLMProviderUnavailable",
    "QUIZ_INSIGHT_MAX_COMPLETION_TOKENS",
    "RESEARCH_CLIENT_CONNECT_TIMEOUT_SECONDS",
    "RESEARCH_CLIENT_MAX_RETRIES",
    "RESEARCH_CLIENT_TIMEOUT_SECONDS",
    "SCORER_CLIENT_MAX_RETRIES",
    "SCORER_CLIENT_TIMEOUT_SECONDS",
    "default_agent_model",
    "default_research_model",
    "default_scorer_model",
    "get_agent_client",
    "get_openai_client",
    "get_research_client",
    "get_scorer_client",
    "groq_api_key",
]

#: Groq's small, fast model. Chosen for latency: the agent streams, so
#: time-to-first-token matters more than depth. Was ``llama-3.1-8b-instant``
#: until Groq retired it and every chat turn came back 422 "model not found";
#: ``SOLVERAH_AGENT_MODEL`` now swaps the model without a deploy.
DEFAULT_AGENT_MODEL = "openai/gpt-oss-20b"

#: Output ceiling for one agent chat turn (2026-10-02 audit #5: there was none,
#: so one turn's cost was bounded only by the model's own limit). On gpt-oss
#: this budget includes the reasoning tokens, which ``reasoning_effort="low"``
#: keeps to a few hundred -- 1,500 leaves room for a long, list-heavy answer.
AGENT_MAX_COMPLETION_TOKENS = 1500

#: Output ceiling for one quiz-insight call. Six quizzes at ~300 tokens each plus
#: the cross-quiz synthesis is under 2,500; a truncated JSON body fails to parse
#: and is answered as a generic 500, so this errs high rather than tight.
QUIZ_INSIGHT_MAX_COMPLETION_TOKENS = 4000

#: CompanyLens research model. ``claude-opus-5-5`` (Claude Opus 5.5) is the exact,
#: fixed model id (Anthropic's current ids carry no date suffix; this is not an
#: alias). Sebastian ruled 2026-10-14 to replace ``claude-opus-5`` with it ($4 /
#: $20 per MTok). ``SOLVERAH_RESEARCH_MODEL`` overrides it per call. Any other
#: model is a cost decision for Sebastian first, and
#: ``research.RESEARCH_PRICES_USD_PER_MTOK`` needs its row or cost estimates come
#: back ``None``.
DEFAULT_RESEARCH_MODEL = "claude-opus-5-5"

#: CompanyLens scoring model: the dated snapshot ``causal_graph/scorer_pipeline.py``
#: validated the v3.1 anchors on. Pinned, never an alias -- an alias would move
#: the scorer under the validation without anyone deciding it.
DEFAULT_SCORER_MODEL = "gpt-5.5-2026-04-23"

#: A research call streams, so the read timeout is the longest silence allowed
#: between two stream events, not the length of the whole call (which can run
#: for minutes while searches and fetches execute server-side). 10 s to connect.
RESEARCH_CLIENT_TIMEOUT_SECONDS = 600.0
RESEARCH_CLIENT_CONNECT_TIMEOUT_SECONDS = 10.0
#: The SDK retries connection errors, 408, 409, 429 and 5xx with backoff. On a
#: stream a retry only happens before the first byte, so a retry never re-bills
#: a half-finished research turn.
RESEARCH_CLIENT_MAX_RETRIES = 2

#: The scorer is a reasoning model answering under a strict JSON schema. The
#: validated pipeline ran on the SDK's default 600 s with five retries of its
#: own; ``get_openai_client``'s 60 s is sized for gpt-4o-mini on the request
#: path and would time out reasoning calls, so the scorer gets its own client.
SCORER_CLIENT_TIMEOUT_SECONDS = 300.0
SCORER_CLIENT_MAX_RETRIES = 3


class LLMProviderUnavailable(RuntimeError):
    """The provider SDK is not installed, or its API key is not set.

    The one typed failure the CompanyLens clients raise before any network call,
    so a service catches one exception and answers a 503 -- the same shape as
    ``CorpusUnavailable`` for a missing O*NET corpus. A ``RuntimeError`` so code
    that already catches the older clients' failures still catches this one.
    """


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
    """The Groq model every chat turn uses.

    The server alone picks it (2026-10-02 audit #5): a ``model`` sent by the
    client is ignored, because letting a browser name the model let anyone
    pick the most expensive one Groq serves on Solverah's key.

    ``SOLVERAH_AGENT_MODEL`` wins when set (read per call, like the key), so the
    next provider retirement is an env change rather than a code change.
    """
    return os.environ.get("SOLVERAH_AGENT_MODEL", "").strip() or DEFAULT_AGENT_MODEL


def default_research_model() -> str:
    """The Anthropic model a CompanyLens research call uses.

    ``SOLVERAH_RESEARCH_MODEL`` wins when set (read per call). Give it an exact
    model id from Anthropic's model list, never a family name.
    """
    return os.environ.get("SOLVERAH_RESEARCH_MODEL", "").strip() or DEFAULT_RESEARCH_MODEL


def default_scorer_model() -> str:
    """The OpenAI model a CompanyLens scoring call uses.

    ``SOLVERAH_SCORER_MODEL`` wins when set (read per call). A different
    snapshot than the validated one needs the anchors re-validated first.
    """
    return os.environ.get("SOLVERAH_SCORER_MODEL", "").strip() or DEFAULT_SCORER_MODEL


def get_research_client():
    """Return an ``anthropic.Anthropic`` client for CompanyLens research.

    **Contract: company name and public URLs only.** Nothing that identifies a
    Solverah user -- no name, email, resume text, assessment answer or user id --
    may go into a request made with this client. Anthropic is registered as a
    vendor for public employer research only
    (``Solverah_IP/compliance/VENDOR_REGISTER.md``).

    ``ANTHROPIC_API_KEY`` is read at call time and passed explicitly, so the SDK
    never falls back to an ``ant auth login`` profile on a developer machine.

    Raises:
        LLMProviderUnavailable: the ``anthropic`` package is not installed, or
            ``ANTHROPIC_API_KEY`` is unset or blank.
    """
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - pinned in requirements.txt
        raise LLMProviderUnavailable("Anthropic SDK not installed") from exc
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        raise LLMProviderUnavailable("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(
        api_key=api_key,
        timeout=anthropic.Timeout(
            RESEARCH_CLIENT_TIMEOUT_SECONDS,
            connect=RESEARCH_CLIENT_CONNECT_TIMEOUT_SECONDS,
        ),
        max_retries=RESEARCH_CLIENT_MAX_RETRIES,
    )


def get_scorer_client():
    """Return an OpenAI client for CompanyLens per-item scoring.

    Same key as :func:`get_openai_client`, a longer timeout (see
    ``SCORER_CLIENT_TIMEOUT_SECONDS``). Use it with :func:`default_scorer_model`.

    Raises:
        LLMProviderUnavailable: the ``openai`` package is not installed, or
            ``OPENAI_API_KEY`` is unset or blank.
    """
    if OpenAI is None:
        raise LLMProviderUnavailable("OpenAI SDK not installed")
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise LLMProviderUnavailable("OPENAI_API_KEY is not set")
    return OpenAI(
        api_key=api_key,
        timeout=SCORER_CLIENT_TIMEOUT_SECONDS,
        max_retries=SCORER_CLIENT_MAX_RETRIES,
    )
