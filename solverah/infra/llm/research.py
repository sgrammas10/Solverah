"""One CompanyLens web-research call on Anthropic, with web search and web fetch.

This module runs the call and reports what came back. It does not write the
prompt and does not parse the research: the CompanyLens pipeline
(``solverah/services/company_research/``) owns both. What it returns:

* the text Claude wrote (``final_text`` is the answer after the last tool call),
* the citations and source URLs the API reported,
* the token and search counts, per model, so the caller can record ``cost_usd``
  (:func:`estimate_research_cost_usd` does the arithmetic).

**Contract: company name and public URLs only.** The prompt and system text
must not carry anything that identifies a Solverah user. See
:func:`solverah.infra.llm.get_research_client`.

**No verbatim quote leaves the pipeline.** ``ResearchCitation.cited_text`` is
up to 150 characters copied from a third-party page. It is internal evidence
for scoring and audit. It must never reach a route or a page (GAP-14,
``Solverah_IP/compliance/AI_GOVERNANCE_AND_CLAIMS.md``).

Background jobs only: one call streams for minutes while searches and fetches
run on Anthropic's side. Never call this from a request handler.

Mechanics, per the Anthropic docs as of 2026-10-13:

* Tools ``web_search_20260318`` and ``web_fetch_20260318`` (dynamic filtering:
  Claude filters results in a sandbox before they reach its context; that code
  execution is free with these tools). Web search costs $10 per 1,000 searches
  plus tokens; web fetch costs tokens only. Search results always carry
  citations; fetch citations are turned on here. No beta header is required for
  either tool. ``SOLVERAH_RESEARCH_SEARCH_TOOL`` / ``SOLVERAH_RESEARCH_FETCH_TOOL``
  override the tool ``type`` strings per call (:func:`web_search_tool_type`,
  :func:`web_fetch_tool_type`), so a later docs drift is a config change.
* The server-side tool loop can stop with ``pause_turn``. The paused assistant
  content is sent back unchanged and the turn resumes, up to
  ``MAX_CONTINUATIONS`` times.
* ``fallbacks: "default"`` (beta ``server-side-fallback-2026-07-01``) re-runs a
  request that the model's safety classifiers decline on Anthropic's
  recommended substitute, inside the same call. Usage is then split per model.
* A ``char_location`` citation (a passage of a fetched page) carries no URL --
  only ``document_index`` and ``document_title``. ``document_index`` counts
  successfully fetched documents in the order they appear in the turn (verified
  against the live web-fetch-tool docs, 2026-10-13); :func:`_citations` resolves
  it to the fetched URL. The fetched document's own title also overrides
  ``ResearchSource.title`` when a URL was first seen under a different title
  from search (see :class:`ResearchSource`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from solverah.infra import llm

__all__ = [
    "DEFAULT_MAX_FETCHES",
    "DEFAULT_MAX_FETCH_CONTENT_TOKENS",
    "DEFAULT_MAX_SEARCHES",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_WEB_FETCH_TOOL_TYPE",
    "DEFAULT_WEB_SEARCH_TOOL_TYPE",
    "FALLBACK_BETA",
    "MAX_CONTINUATIONS",
    "RESEARCH_PRICES_USD_PER_MTOK",
    "ResearchCallError",
    "ResearchCitation",
    "ResearchIncomplete",
    "ResearchProviderError",
    "ResearchRefused",
    "ResearchResult",
    "ResearchSource",
    "ResearchUsage",
    "TokenUsage",
    "WEB_FETCH_TOOL_TYPE",
    "WEB_SEARCH_TOOL_TYPE",
    "WEB_SEARCH_USD_PER_SEARCH",
    "estimate_research_cost_usd",
    "run_research_call",
    "web_fetch_tool_type",
    "web_search_tool_type",
]

#: Verified against the live docs at platform.claude.com/docs/en/agents-and-tools/
#: tool-use/web-search-tool and .../web-fetch-tool (read 2026-10-13): both
#: ``_20260318`` variants exist, are each tool's latest version, carry dynamic
#: filtering, and need no beta header. ``SOLVERAH_RESEARCH_SEARCH_TOOL`` /
#: ``SOLVERAH_RESEARCH_FETCH_TOOL`` override these per call (read at call time,
#: like :func:`solverah.infra.llm.default_research_model`), so a future docs
#: drift is a config change, not a code change.
DEFAULT_WEB_SEARCH_TOOL_TYPE = "web_search_20260318"
DEFAULT_WEB_FETCH_TOOL_TYPE = "web_fetch_20260318"
#: Back-compat aliases -- the verified defaults, not necessarily what one call
#: actually sent; use :func:`web_search_tool_type` / :func:`web_fetch_tool_type`
#: to see the override in effect.
WEB_SEARCH_TOOL_TYPE = DEFAULT_WEB_SEARCH_TOOL_TYPE
WEB_FETCH_TOOL_TYPE = DEFAULT_WEB_FETCH_TOOL_TYPE
FALLBACK_BETA = "server-side-fallback-2026-07-01"

#: Output ceiling for one research turn. On Claude Opus 5 thinking is on by
#: default and ``max_tokens`` caps thinking *plus* the answer, so this is
#: generous. The call streams (``DEFAULT_MAX_TOKENS`` this large would
#: otherwise risk an HTTP timeout), so a large ceiling cannot trip one.
DEFAULT_MAX_TOKENS = 64_000
#: Per-request caps on the server tools. 10 searches is about $0.10.
DEFAULT_MAX_SEARCHES = 10
DEFAULT_MAX_FETCHES = 10
#: Truncation point for one fetched page. Fetched text is billed as input
#: tokens, and a long careers page or 10-K would otherwise dominate the cost.
DEFAULT_MAX_FETCH_CONTENT_TOKENS = 25_000
#: ``pause_turn`` resumptions before the call gives up.
MAX_CONTINUATIONS = 5

#: USD per million tokens, from platform.claude.com/docs/en/about-claude/pricing
#: (read 2026-10-13). ``claude-opus-4-8`` is here because it is where
#: ``fallbacks: "default"`` sends cyber-category refusals. Global routing (no
#: ``inference_geo``); a US-only geo would be 1.1x.
RESEARCH_PRICES_USD_PER_MTOK: Mapping[str, Mapping[str, float]] = {
    "claude-opus-5": {
        "input": 5.00, "output": 25.00, "cache_write_5m": 6.25, "cache_read": 0.50,
    },
    "claude-opus-4-8": {
        "input": 5.00, "output": 25.00, "cache_write_5m": 6.25, "cache_read": 0.50,
    },
}
WEB_SEARCH_USD_PER_SEARCH = 10.00 / 1000


# ── Result types ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TokenUsage:
    """Billed tokens for one model."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_creation_input_tokens + other.cache_creation_input_tokens,
            self.cache_read_input_tokens + other.cache_read_input_tokens,
        )


@dataclass(frozen=True)
class ResearchUsage:
    """Everything one research call billed, across all its API requests.

    ``by_model`` has more than one key only when a fallback ran. The search
    and fetch counts are per call; only searches are billed per use.
    """

    by_model: Mapping[str, TokenUsage] = field(default_factory=dict)
    web_search_requests: int = 0
    web_fetch_requests: int = 0
    api_requests: int = 0

    @property
    def totals(self) -> TokenUsage:
        total = TokenUsage()
        for tokens in self.by_model.values():
            total = total + tokens
        return total


@dataclass(frozen=True)
class ResearchCitation:
    """One citation the API attached to Claude's text.

    ``kind`` is the API's citation type: ``web_search_result_location`` (has
    ``url``) or ``char_location`` (a passage of a fetched page: the API gives no
    ``url`` on this kind, only ``document_index`` and ``document_title``).

    **2026-10-13 fix:** ``url`` is now populated for ``char_location`` too, resolved
    through ``document_index`` against the fetched documents in conversation order
    (the API's own convention for this field -- same as citations on a directly
    attached PDF). Before this, ``url`` was always ``None`` on this kind and callers
    had to match ``title`` against ``ResearchSource.title`` instead, which broke
    when a page's search-listed title differed from its fetched document title (see
    ``solverah/services/company_research/research.py::_citations_for``). ``title``
    is still populated (``document_title``, falling back to the resolved document's
    own title) so existing title-matching callers keep working. ``document_index``
    is new: ``None`` for a ``web_search_result_location`` citation (it carries its
    URL directly), and the resolved index for ``char_location``.

    ``cited_text`` is verbatim third-party text -- internal only, see the module
    docstring.
    """

    kind: str
    cited_text: str
    url: Optional[str]
    title: Optional[str]
    document_index: Optional[int] = None


@dataclass(frozen=True)
class ResearchSource:
    """A URL the call saw, deduplicated, in order of first appearance.

    ``fetched``: Claude read the full page with web fetch. ``cited``: a search
    citation names it. A search result that is neither was only listed.

    **2026-10-13 fix:** ``title`` used to keep whichever title was seen first --
    usually the search result's -- even after a fetch of the same URL returned the
    page's own (possibly different) document title. A ``char_location`` citation
    always carries the fetched title, so matching it against this field's stale
    search title silently failed and the item was dropped. Now a fetch's document
    title overrides ``title`` when present. ``search_title`` is new: the title the
    URL was first listed under by search, kept even after a fetch overrides
    ``title``, for a caller that wants to show or compare both.
    """

    url: str
    title: Optional[str]
    page_age: Optional[str]
    retrieved_at: Optional[str]
    fetched: bool
    cited: bool
    search_title: Optional[str] = None


@dataclass(frozen=True)
class ResearchResult:
    text: str
    """Every text block, in order, including narration between tool calls."""
    final_text: str
    """The text after the last tool call: the answer to parse."""
    citations: tuple
    sources: tuple
    model: str
    """The model requested."""
    served_model: str
    """The model that produced the final message. Differs after a fallback."""
    fell_back: bool
    stop_reason: str
    usage: ResearchUsage
    continuations: int


class ResearchCallError(RuntimeError):
    """A research call that spent money and did not finish.

    ``usage`` is what was billed before the failure: record it as the run's
    cost even though there is no result.
    """

    def __init__(self, message: str, usage: ResearchUsage):
        super().__init__(message)
        self.usage = usage


class ResearchRefused(ResearchCallError):
    """The model and its fallback both declined (``stop_reason: refusal``)."""

    def __init__(self, message: str, usage: ResearchUsage, category: Optional[str]):
        super().__init__(message, usage)
        self.category = category


class ResearchIncomplete(ResearchCallError):
    """The turn stopped before an answer: ``max_tokens``, or still paused
    after ``MAX_CONTINUATIONS`` resumptions. ``partial_text`` is what was
    written so far."""

    def __init__(self, message: str, usage: ResearchUsage, stop_reason: str, partial_text: str):
        super().__init__(message, usage)
        self.stop_reason = stop_reason
        self.partial_text = partial_text


class ResearchProviderError(ResearchCallError):
    """The API call itself failed after the SDK's own retries.

    ``retryable`` is True for rate limits, overload, 5xx, timeouts and
    connection errors -- worth a later job retry -- and False for a 4xx that
    will fail the same way again (bad request, auth, permission).
    """

    def __init__(self, message: str, usage: ResearchUsage, *, retryable: bool,
                 status_code: Optional[int]):
        super().__init__(message, usage)
        self.retryable = retryable
        self.status_code = status_code


# ── The call ────────────────────────────────────────────────────────────────


def run_research_call(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    effort: Optional[str] = None,
    max_searches: int = DEFAULT_MAX_SEARCHES,
    max_fetches: int = DEFAULT_MAX_FETCHES,
    max_fetch_content_tokens: int = DEFAULT_MAX_FETCH_CONTENT_TOKENS,
    blocked_domains: Sequence[str] = (),
    client: Any = None,
) -> ResearchResult:
    """Run one research turn with web search and web fetch enabled.

    Args:
        prompt: the user message. Company name and public URLs only.
        system: optional system prompt. Same rule.
        model: defaults to :func:`solverah.infra.llm.default_research_model`.
        max_tokens: output ceiling per request (thinking plus answer).
        effort: ``"low"`` .. ``"max"``; ``None`` leaves the API default
            (``high`` on Claude Opus 5).
        max_searches / max_fetches: per-request caps on each server tool.
        max_fetch_content_tokens: truncation point for one fetched page.
        blocked_domains: bare hostnames neither tool may use (e.g. a review
            site awaiting attorney review). Empty means no filter.
        client: an ``anthropic.Anthropic``; defaults to
            :func:`solverah.infra.llm.get_research_client`. Tests pass a fake.

    Raises:
        LLMProviderUnavailable: no SDK or no ``ANTHROPIC_API_KEY`` (nothing spent).
        ResearchRefused / ResearchIncomplete / ResearchProviderError: the call
            started and failed; each carries the ``usage`` billed so far.
    """
    model = model or llm.default_research_model()
    if client is None:
        client = llm.get_research_client()

    tools = _tools(max_searches, max_fetches, max_fetch_content_tokens, blocked_domains)
    request: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "tools": tools,
        "betas": [FALLBACK_BETA],
        "fallbacks": "default",
    }
    if system:
        request["system"] = system
    if effort:
        request["output_config"] = {"effort": effort}

    usage = _UsageAccumulator(model)
    content: list = []  # the assistant turn so far, as API dicts
    served_model = model
    stop_reason = ""
    continuations = 0

    while True:
        messages = [{"role": "user", "content": prompt}]
        if content:
            messages.append({"role": "assistant", "content": _echoable(content)})
        message = _stream_once(client, dict(request, messages=messages), usage)
        usage.add(message)
        content.extend(message.get("content") or [])
        served_model = message.get("model") or served_model
        stop_reason = message.get("stop_reason") or ""
        if stop_reason != "pause_turn":
            break
        if continuations >= MAX_CONTINUATIONS:
            raise ResearchIncomplete(
                "research turn still paused after %d continuations" % continuations,
                usage.freeze(), "pause_turn", _all_text(content),
            )
        continuations += 1

    if stop_reason == "refusal":
        details = message.get("stop_details") or {}
        raise ResearchRefused(
            "research request declined (category=%s)" % details.get("category"),
            usage.freeze(), details.get("category"),
        )
    if stop_reason == "max_tokens":
        raise ResearchIncomplete(
            "research turn hit max_tokens=%d" % max_tokens,
            usage.freeze(), stop_reason, _all_text(content),
        )

    fetched_documents = _fetched_documents(content)
    return ResearchResult(
        text=_all_text(content),
        final_text=_final_text(content),
        citations=tuple(_citations(content, fetched_documents)),
        sources=tuple(_sources(content)),
        model=model,
        served_model=served_model,
        fell_back=usage.fell_back or served_model != model,
        stop_reason=stop_reason,
        usage=usage.freeze(),
        continuations=continuations,
    )


def estimate_research_cost_usd(usage: ResearchUsage) -> Optional[float]:
    """Dollar cost of a research call at list price, or ``None`` when a model
    in ``usage.by_model`` has no row in ``RESEARCH_PRICES_USD_PER_MTOK``.

    ``None`` rather than a guess, so a model swap that forgot the price table
    shows up as a missing cost instead of a wrong one. Cache writes are priced
    at the 5-minute rate (this module sets no cache TTL).
    """
    total = usage.web_search_requests * WEB_SEARCH_USD_PER_SEARCH
    for model_id, tokens in usage.by_model.items():
        prices = RESEARCH_PRICES_USD_PER_MTOK.get(model_id)
        if prices is None:
            return None
        total += (
            tokens.input_tokens * prices["input"]
            + tokens.output_tokens * prices["output"]
            + tokens.cache_creation_input_tokens * prices["cache_write_5m"]
            + tokens.cache_read_input_tokens * prices["cache_read"]
        ) / 1_000_000
    return round(total, 6)


# ── Internals ───────────────────────────────────────────────────────────────


def web_search_tool_type() -> str:
    """The web search tool ``type`` string this call uses.

    ``SOLVERAH_RESEARCH_SEARCH_TOOL`` wins when set (read per call, like
    :func:`solverah.infra.llm.default_research_model`), so a docs drift on
    deploy day is a config change, not a code change.
    """
    return os.environ.get("SOLVERAH_RESEARCH_SEARCH_TOOL", "").strip() or DEFAULT_WEB_SEARCH_TOOL_TYPE


def web_fetch_tool_type() -> str:
    """The web fetch tool ``type`` string this call uses.

    ``SOLVERAH_RESEARCH_FETCH_TOOL`` wins when set (read per call).
    """
    return os.environ.get("SOLVERAH_RESEARCH_FETCH_TOOL", "").strip() or DEFAULT_WEB_FETCH_TOOL_TYPE


def _tools(max_searches: int, max_fetches: int, max_fetch_content_tokens: int,
           blocked_domains: Sequence[str]) -> list:
    search: dict = {"type": web_search_tool_type(), "name": "web_search", "max_uses": max_searches}
    fetch: dict = {
        "type": web_fetch_tool_type(),
        "name": "web_fetch",
        "max_uses": max_fetches,
        "max_content_tokens": max_fetch_content_tokens,
        "citations": {"enabled": True},
    }
    if blocked_domains:
        search["blocked_domains"] = list(blocked_domains)
        fetch["blocked_domains"] = list(blocked_domains)
    return [search, fetch]


def _stream_once(client: Any, request: dict, usage: "_UsageAccumulator") -> dict:
    """One streamed request; the final message as an API dict."""
    import anthropic

    try:
        with client.beta.messages.stream(**request) as stream:
            message = stream.get_final_message()
    except anthropic.APIStatusError as exc:
        status = exc.status_code
        retryable = status in (408, 409, 429) or status >= 500
        raise ResearchProviderError(
            "research call failed: HTTP %s" % status, usage.freeze(),
            retryable=retryable, status_code=status,
        ) from exc
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
        raise ResearchProviderError(
            "research call failed: %s" % type(exc).__name__, usage.freeze(),
            retryable=True, status_code=None,
        ) from exc
    return message.to_dict() if hasattr(message, "to_dict") else dict(message)


class _UsageAccumulator:
    def __init__(self, requested_model: str):
        self._requested = requested_model
        self._by_model: dict = {}
        self._searches = 0
        self._fetches = 0
        self._requests = 0
        self.fell_back = False

    def add(self, message: Mapping) -> None:
        self._requests += 1
        usage = message.get("usage") or {}
        iterations = usage.get("iterations") or []
        if any(entry.get("type") == "fallback_message" for entry in iterations):
            # Top-level usage covers only the attempt that produced the
            # message; per-attempt billing lives in the iterations.
            self.fell_back = True
            for entry in iterations:
                self._credit(entry.get("model") or self._requested, entry)
        else:
            self._credit(message.get("model") or self._requested, usage)
        server = usage.get("server_tool_use") or {}
        self._searches += int(server.get("web_search_requests") or 0)
        self._fetches += int(server.get("web_fetch_requests") or 0)

    def _credit(self, model_id: str, counts: Mapping) -> None:
        tokens = TokenUsage(
            int(counts.get("input_tokens") or 0),
            int(counts.get("output_tokens") or 0),
            int(counts.get("cache_creation_input_tokens") or 0),
            int(counts.get("cache_read_input_tokens") or 0),
        )
        self._by_model[model_id] = self._by_model.get(model_id, TokenUsage()) + tokens

    def freeze(self) -> ResearchUsage:
        return ResearchUsage(
            by_model=dict(self._by_model),
            web_search_requests=self._searches,
            web_fetch_requests=self._fetches,
            api_requests=self._requests,
        )


#: Blocks that are not the model's prose. The answer is the text after the
#: last of these. ``fallback`` is not one: a mid-stream fallback continues the
#: same partial text on the substitute model.
_PROSE_TYPES = {"text", "thinking", "redacted_thinking", "fallback"}


def _echoable(content: list) -> list:
    """The paused turn as it must be sent back on a continuation.

    Unchanged, except after a mid-output fallback: blocks before the last
    ``fallback`` block that the substitute model cannot take (thinking, client
    tool calls, and server tool calls whose result never arrived) are omitted,
    per the API's echo rule. Without a fallback this is ``content`` as-is.
    """
    last_fallback = max(
        (i for i, block in enumerate(content) if block.get("type") == "fallback"),
        default=-1,
    )
    if last_fallback < 0:
        return content
    answered = {block.get("tool_use_id") for block in content if block.get("tool_use_id")}
    kept = []
    for i, block in enumerate(content):
        kind = block.get("type")
        if i < last_fallback:
            if kind in ("thinking", "redacted_thinking", "tool_use"):
                continue
            if kind == "server_tool_use" and block.get("id") not in answered:
                continue
        kept.append(block)
    return kept


def _all_text(content: list) -> str:
    return "".join(block.get("text") or "" for block in content if block.get("type") == "text")


def _final_text(content: list) -> str:
    last_tool = max(
        (i for i, block in enumerate(content) if block.get("type") not in _PROSE_TYPES),
        default=-1,
    )
    return _all_text(content[last_tool + 1:])


def _fetched_documents(content: list) -> list:
    """Successfully fetched documents, in the order they appear in the turn.

    A ``char_location`` citation's ``document_index`` counts positions in this
    list (the API's convention for document citations in general: the same
    indexing a directly attached PDF's citations use). An errored
    ``web_fetch_tool_result`` (``content.type == "web_fetch_tool_result_error"``)
    never becomes a citable document, so it is not counted here.
    """
    docs = []
    for block in content:
        if block.get("type") != "web_fetch_tool_result":
            continue
        result = block.get("content")
        if isinstance(result, dict) and result.get("type") == "web_fetch_result":
            document = result.get("content") or {}
            docs.append({"url": result.get("url"), "title": document.get("title")})
    return docs


def _citations(content: list, fetched_documents: Sequence[Mapping[str, Any]]) -> list:
    out = []
    for block in content:
        if block.get("type") != "text":
            continue
        for cite in block.get("citations") or []:
            kind = cite.get("type") or ""
            url = cite.get("url")
            title = cite.get("title") or cite.get("document_title")
            document_index = cite.get("document_index")
            if kind == "char_location" and url is None and isinstance(document_index, int) \
                    and 0 <= document_index < len(fetched_documents):
                document = fetched_documents[document_index]
                url = document.get("url")
                title = title or document.get("title")
            out.append(ResearchCitation(
                kind=kind, cited_text=cite.get("cited_text") or "",
                url=url, title=title, document_index=document_index,
            ))
    return out


def _sources(content: list) -> list:
    found: dict = {}

    def entry_for(url: str) -> dict:
        return found.setdefault(url, {
            "url": url, "title": None, "page_age": None, "retrieved_at": None,
            "fetched": False, "cited": False, "search_title": None,
        })

    def note(url: Optional[str], **attrs: Any) -> None:
        if not url:
            return
        entry = entry_for(url)
        for key, value in attrs.items():
            if value and not entry[key]:
                entry[key] = value

    for block in content:
        kind = block.get("type")
        result = block.get("content")
        if kind == "web_search_tool_result" and isinstance(result, list):
            for hit in result:
                note(hit.get("url"), title=hit.get("title"), search_title=hit.get("title"),
                     page_age=hit.get("page_age"))
        elif kind == "web_fetch_tool_result" and isinstance(result, dict) \
                and result.get("type") == "web_fetch_result":
            url = result.get("url")
            if url:
                entry = entry_for(url)
                entry["fetched"] = True
                if result.get("retrieved_at") and not entry["retrieved_at"]:
                    entry["retrieved_at"] = result.get("retrieved_at")
                document = result.get("content") or {}
                doc_title = document.get("title")
                if doc_title:
                    # The fetched document's own title wins over whatever title
                    # (typically search's) was recorded first -- see the class
                    # docstring. search_title is left as whatever note() already
                    # captured from a search hit, if any.
                    entry["title"] = doc_title
        elif kind == "text":
            for cite in block.get("citations") or []:
                note(cite.get("url"), title=cite.get("title"), cited=True)

    return [ResearchSource(**entry) for entry in found.values()]
