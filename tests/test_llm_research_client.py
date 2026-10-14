"""The CompanyLens LLM clients: Anthropic research and the OpenAI scorer.

No test here reaches the network. The research helper is driven through a fake
client whose ``beta.messages.stream`` returns real SDK message objects (parsed
with ``BetaMessage.model_validate``), so the shapes under test are the SDK's,
not hand-rolled dicts. CI sets no ``ANTHROPIC_API_KEY`` or ``OPENAI_API_KEY``;
the tests that need one set it with monkeypatch, and the missing-key tests
clear it explicitly.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaMessage

from solverah.infra import llm
from solverah.infra.llm import research

# ── Fakes ───────────────────────────────────────────────────────────────────


class _FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


class _FakeClient:
    """Stands in for ``anthropic.Anthropic`` at the client boundary."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **request):
        self.requests.append(copy.deepcopy(request))
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _FakeStream(item)


def _message(content, *, stop_reason="end_turn", model="claude-opus-5", usage=None,
             stop_details=None):
    return BetaMessage.model_validate({
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "stop_details": stop_details,
        "usage": usage or {"input_tokens": 1000, "output_tokens": 200},
    })


SEARCH_USE = {"type": "server_tool_use", "id": "srvtoolu_s1", "name": "web_search",
              "input": {"query": "Acme Corp engineering culture"}}
SEARCH_RESULT = {
    "type": "web_search_tool_result", "tool_use_id": "srvtoolu_s1",
    "content": [
        {"type": "web_search_result", "url": "https://acme.example/careers",
         "title": "Careers at Acme", "encrypted_content": "ENC-1", "page_age": "May 1, 2026"},
        {"type": "web_search_result", "url": "https://news.example/acme",
         "title": "Acme reorganises", "encrypted_content": "ENC-2", "page_age": None},
    ],
}
FETCH_USE = {"type": "server_tool_use", "id": "srvtoolu_f1", "name": "web_fetch",
             "input": {"url": "https://acme.example/careers"}}
FETCH_RESULT = {
    "type": "web_fetch_tool_result", "tool_use_id": "srvtoolu_f1",
    "content": {
        "type": "web_fetch_result", "url": "https://acme.example/careers",
        "retrieved_at": "2026-10-13T09:00:00Z",
        "content": {"type": "document", "title": "Careers at Acme",
                    "source": {"type": "text", "media_type": "text/plain", "data": "We ship fast."},
                    "citations": {"enabled": True}},
    },
}
NARRATION = {"type": "text", "text": "Let me look that up. "}
ANSWER = [
    {"type": "text", "text": "Acme ships weekly", "citations": [
        {"type": "web_search_result_location", "url": "https://acme.example/careers",
         "title": "Careers at Acme", "encrypted_index": "EI-1", "cited_text": "We ship weekly"},
    ]},
    {"type": "text", "text": " and says so.", "citations": [
        {"type": "char_location", "document_index": 0, "document_title": "Careers at Acme",
         "start_char_index": 0, "end_char_index": 13, "cited_text": "We ship fast."},
    ]},
]
FULL_TURN = [NARRATION, SEARCH_USE, SEARCH_RESULT, FETCH_USE, FETCH_RESULT, *ANSWER]


# ── Client accessors ────────────────────────────────────────────────────────


def test_research_client_without_key_raises_typed_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(llm.LLMProviderUnavailable, match="ANTHROPIC_API_KEY"):
        llm.get_research_client()


def test_research_client_blank_key_is_missing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    with pytest.raises(llm.LLMProviderUnavailable):
        llm.get_research_client()


def test_typed_error_is_still_a_runtime_error():
    assert issubclass(llm.LLMProviderUnavailable, RuntimeError)


def test_research_client_reads_key_at_call_time_and_sizes_for_long_calls(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    client = llm.get_research_client()

    assert isinstance(client, anthropic.Anthropic)
    assert client.api_key == "sk-ant-test-not-real"
    assert client.max_retries == llm.RESEARCH_CLIENT_MAX_RETRIES
    assert client.timeout.read == llm.RESEARCH_CLIENT_TIMEOUT_SECONDS
    assert client.timeout.connect == llm.RESEARCH_CLIENT_CONNECT_TIMEOUT_SECONDS


def test_research_model_default_override_and_blank(monkeypatch):
    monkeypatch.delenv("SOLVERAH_RESEARCH_MODEL", raising=False)
    assert llm.default_research_model() == "claude-opus-5"
    monkeypatch.setenv("SOLVERAH_RESEARCH_MODEL", "  claude-opus-4-8 ")
    assert llm.default_research_model() == "claude-opus-4-8"
    monkeypatch.setenv("SOLVERAH_RESEARCH_MODEL", "  ")
    assert llm.default_research_model() == llm.DEFAULT_RESEARCH_MODEL


def test_scorer_client_without_key_raises_typed_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(llm.LLMProviderUnavailable, match="OPENAI_API_KEY"):
        llm.get_scorer_client()


def test_scorer_client_has_its_own_longer_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    client = llm.get_scorer_client()

    assert client.timeout == llm.SCORER_CLIENT_TIMEOUT_SECONDS
    assert client.max_retries == llm.SCORER_CLIENT_MAX_RETRIES
    assert llm.get_openai_client().timeout == 60.0  # the request-path client is unchanged


def test_scorer_model_is_the_validated_snapshot_and_overridable(monkeypatch):
    monkeypatch.delenv("SOLVERAH_SCORER_MODEL", raising=False)
    assert llm.default_scorer_model() == "gpt-5.5-2026-04-23"
    monkeypatch.setenv("SOLVERAH_SCORER_MODEL", "gpt-5.5-2026-09-01")
    assert llm.default_scorer_model() == "gpt-5.5-2026-09-01"


# ── run_research_call ───────────────────────────────────────────────────────


def test_no_key_and_no_client_fails_before_any_request(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(llm.LLMProviderUnavailable):
        research.run_research_call("Research Acme Corp.")


def test_request_enables_both_web_tools_with_caps_and_fallback(monkeypatch):
    monkeypatch.delenv("SOLVERAH_RESEARCH_MODEL", raising=False)
    client = _FakeClient(_message(FULL_TURN))

    research.run_research_call(
        "Research Acme Corp.", system="You research employers.", effort="medium",
        max_searches=4, max_fetches=3, max_fetch_content_tokens=9000,
        blocked_domains=["reviews.example"], client=client,
    )

    (request,) = client.requests
    assert request["model"] == "claude-opus-5"
    assert request["system"] == "You research employers."
    assert request["output_config"] == {"effort": "medium"}
    assert request["fallbacks"] == "default"
    assert request["betas"] == [research.FALLBACK_BETA]
    assert request["messages"] == [{"role": "user", "content": "Research Acme Corp."}]
    search, fetch = request["tools"]
    assert search == {"type": "web_search_20260318", "name": "web_search", "max_uses": 4,
                      "blocked_domains": ["reviews.example"]}
    assert fetch == {"type": "web_fetch_20260318", "name": "web_fetch", "max_uses": 3,
                     "max_content_tokens": 9000, "citations": {"enabled": True},
                     "blocked_domains": ["reviews.example"]}


def test_default_tool_types_and_max_tokens():
    assert research.DEFAULT_WEB_SEARCH_TOOL_TYPE == "web_search_20260318"
    assert research.DEFAULT_WEB_FETCH_TOOL_TYPE == "web_fetch_20260318"
    assert research.DEFAULT_MAX_TOKENS == 64_000


def test_tool_types_are_overridable_by_env(monkeypatch):
    monkeypatch.delenv("SOLVERAH_RESEARCH_SEARCH_TOOL", raising=False)
    monkeypatch.delenv("SOLVERAH_RESEARCH_FETCH_TOOL", raising=False)
    assert research.web_search_tool_type() == research.DEFAULT_WEB_SEARCH_TOOL_TYPE
    assert research.web_fetch_tool_type() == research.DEFAULT_WEB_FETCH_TOOL_TYPE

    monkeypatch.setenv("SOLVERAH_RESEARCH_SEARCH_TOOL", "  web_search_20270101 ")
    monkeypatch.setenv("SOLVERAH_RESEARCH_FETCH_TOOL", "  web_fetch_20270101 ")
    assert research.web_search_tool_type() == "web_search_20270101"
    assert research.web_fetch_tool_type() == "web_fetch_20270101"

    client = _FakeClient(_message(FULL_TURN))
    research.run_research_call("Research Acme Corp.", client=client)
    search, fetch = client.requests[0]["tools"]
    assert search["type"] == "web_search_20270101"
    assert fetch["type"] == "web_fetch_20270101"


def test_optional_fields_are_omitted_when_not_given():
    client = _FakeClient(_message(FULL_TURN))
    research.run_research_call("Research Acme Corp.", client=client)

    (request,) = client.requests
    assert "system" not in request
    assert "output_config" not in request
    assert all("blocked_domains" not in tool for tool in request["tools"])


def test_happy_path_returns_text_citations_sources_and_usage():
    usage = {"input_tokens": 12_000, "output_tokens": 1_500,
             "server_tool_use": {"web_search_requests": 2, "web_fetch_requests": 1}}
    client = _FakeClient(_message(FULL_TURN, usage=usage))

    result = research.run_research_call("Research Acme Corp.", client=client)

    assert result.text == "Let me look that up. Acme ships weekly and says so."
    assert result.final_text == "Acme ships weekly and says so."
    assert result.stop_reason == "end_turn"
    assert result.served_model == result.model == "claude-opus-5"
    assert result.fell_back is False
    assert result.continuations == 0

    assert [(c.kind, c.url, c.title, c.document_index) for c in result.citations] == [
        ("web_search_result_location", "https://acme.example/careers", "Careers at Acme", None),
        ("char_location", "https://acme.example/careers", "Careers at Acme", 0),
    ]
    careers, news = result.sources
    assert careers == research.ResearchSource(
        url="https://acme.example/careers", title="Careers at Acme", page_age="May 1, 2026",
        retrieved_at="2026-10-13T09:00:00Z", fetched=True, cited=True,
        search_title="Careers at Acme")
    assert (news.url, news.fetched, news.cited) == ("https://news.example/acme", False, False)

    assert result.usage.by_model == {"claude-opus-5": research.TokenUsage(12_000, 1_500)}
    assert (result.usage.web_search_requests, result.usage.web_fetch_requests) == (2, 1)
    assert result.usage.api_requests == 1
    # 12k in at $5/M = 0.06, 1.5k out at $25/M = 0.0375, 2 searches at $0.01 = 0.02
    assert research.estimate_research_cost_usd(result.usage) == pytest.approx(0.1175)


def test_char_location_resolves_to_the_fetched_url_even_when_search_title_differs():
    """Regression for the bug matching-model's C5b found: search lists a page under
    one title, the fetch of that same URL returns a different document title, and
    the char_location citation (which carries only the fetched title) must still
    resolve to that URL -- by document_index, not by a title match that a title
    mismatch would silently fail."""
    search_use = {"type": "server_tool_use", "id": "srvtoolu_s9", "name": "web_search",
                  "input": {"query": "Acme Corp"}}
    search_result = {
        "type": "web_search_tool_result", "tool_use_id": "srvtoolu_s9",
        "content": [{"type": "web_search_result", "url": "https://acme.example/careers",
                     "title": "Acme Careers - Join Us", "encrypted_content": "ENC-1",
                     "page_age": None}],
    }
    fetch_use = {"type": "server_tool_use", "id": "srvtoolu_f9", "name": "web_fetch",
                 "input": {"url": "https://acme.example/careers"}}
    fetch_result = {
        "type": "web_fetch_tool_result", "tool_use_id": "srvtoolu_f9",
        "content": {
            "type": "web_fetch_result", "url": "https://acme.example/careers",
            "retrieved_at": "2026-10-13T09:00:00Z",
            "content": {"type": "document", "title": "Careers | Acme Corporation",
                        "source": {"type": "text", "media_type": "text/plain",
                                   "data": "We ship weekly."},
                        "citations": {"enabled": True}},
        },
    }
    answer = {"type": "text", "text": "They ship weekly.", "citations": [
        {"type": "char_location", "document_index": 0,
         "document_title": "Careers | Acme Corporation",
         "start_char_index": 0, "end_char_index": 15, "cited_text": "We ship weekly."},
    ]}
    client = _FakeClient(_message([search_use, search_result, fetch_use, fetch_result, answer]))

    result = research.run_research_call("Research Acme Corp.", client=client)

    (citation,) = result.citations
    assert citation.kind == "char_location"
    assert citation.url == "https://acme.example/careers"
    assert citation.title == "Careers | Acme Corporation"
    assert citation.document_index == 0

    (source,) = result.sources
    # The fetched document's own title wins over the search title it was first
    # seen under; search_title keeps the original for a caller that wants both.
    assert source.title == "Careers | Acme Corporation"
    assert source.search_title == "Acme Careers - Join Us"
    assert source.fetched is True


def test_pause_turn_resends_the_paused_content_unchanged_and_sums_usage():
    paused = _message([NARRATION, SEARCH_USE, SEARCH_RESULT], stop_reason="pause_turn",
                      usage={"input_tokens": 5_000, "output_tokens": 300,
                             "server_tool_use": {"web_search_requests": 1, "web_fetch_requests": 0}})
    finished = _message([FETCH_USE, FETCH_RESULT, *ANSWER],
                        usage={"input_tokens": 8_000, "output_tokens": 700,
                               "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 1}})
    client = _FakeClient(paused, finished)

    result = research.run_research_call("Research Acme Corp.", client=client)

    first, second = client.requests
    assert len(first["messages"]) == 1
    user, assistant = second["messages"]
    assert user == {"role": "user", "content": "Research Acme Corp."}
    assert assistant["role"] == "assistant"
    assert assistant["content"] == paused.to_dict()["content"]
    assert assistant["content"][2]["content"][0]["encrypted_content"] == "ENC-1"
    assert second["tools"] == first["tools"]

    assert result.continuations == 1
    assert result.final_text == "Acme ships weekly and says so."
    assert result.usage.totals == research.TokenUsage(13_000, 1_000)
    assert result.usage.api_requests == 2
    assert (result.usage.web_search_requests, result.usage.web_fetch_requests) == (1, 1)


def test_endless_pause_turn_gives_up_with_the_usage_spent():
    paused = [_message([NARRATION], stop_reason="pause_turn")
              for _ in range(research.MAX_CONTINUATIONS + 1)]
    client = _FakeClient(*paused)

    with pytest.raises(research.ResearchIncomplete) as caught:
        research.run_research_call("Research Acme Corp.", client=client)

    assert caught.value.stop_reason == "pause_turn"
    assert caught.value.usage.api_requests == research.MAX_CONTINUATIONS + 1
    assert caught.value.usage.totals.input_tokens == 1000 * (research.MAX_CONTINUATIONS + 1)


def test_max_tokens_is_incomplete_not_a_result():
    client = _FakeClient(_message([NARRATION, {"type": "text", "text": "Acme is"}],
                                  stop_reason="max_tokens"))

    with pytest.raises(research.ResearchIncomplete) as caught:
        research.run_research_call("Research Acme Corp.", client=client)

    assert caught.value.stop_reason == "max_tokens"
    assert caught.value.partial_text == "Let me look that up. Acme is"
    assert caught.value.usage.api_requests == 1


def test_refusal_after_fallback_raises_with_category_and_usage():
    client = _FakeClient(_message([], stop_reason="refusal",
                                  stop_details={"type": "refusal", "category": "cyber",
                                                "explanation": None}))

    with pytest.raises(research.ResearchRefused) as caught:
        research.run_research_call("Research Acme Corp.", client=client)

    assert caught.value.category == "cyber"
    assert caught.value.usage.api_requests == 1


def test_fallback_usage_is_split_per_model_from_the_iterations():
    usage = {
        "input_tokens": 9_000, "output_tokens": 800,
        "server_tool_use": {"web_search_requests": 1, "web_fetch_requests": 0},
        "iterations": [
            {"type": "message", "input_tokens": 2_000, "output_tokens": 100,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            {"type": "fallback_message", "model": "claude-opus-4-8", "input_tokens": 9_000,
             "output_tokens": 800, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        ],
    }
    fallback_block = {"type": "fallback", "from": {"model": "claude-opus-5"},
                      "to": {"model": "claude-opus-4-8"}, "trigger": {"type": "refusal"}}
    client = _FakeClient(_message([fallback_block, *ANSWER], model="claude-opus-4-8", usage=usage))

    result = research.run_research_call("Research Acme Corp.", client=client)

    assert result.fell_back is True
    assert result.served_model == "claude-opus-4-8"
    assert result.usage.by_model == {
        "claude-opus-5": research.TokenUsage(2_000, 100),
        "claude-opus-4-8": research.TokenUsage(9_000, 800),
    }
    assert result.final_text == "Acme ships weekly and says so."


def test_continuation_after_a_fallback_drops_what_the_substitute_cannot_take():
    thinking = {"type": "thinking", "thinking": "", "signature": "SIG"}
    unanswered = {"type": "server_tool_use", "id": "srvtoolu_lost", "name": "web_search",
                  "input": {"query": "x"}}
    fallback_block = {"type": "fallback", "from": {"model": "claude-opus-5"},
                      "to": {"model": "claude-opus-4-8"}, "trigger": {"type": "refusal"}}
    paused = _message([thinking, SEARCH_USE, SEARCH_RESULT, unanswered, NARRATION,
                       fallback_block, FETCH_USE], stop_reason="pause_turn",
                      model="claude-opus-4-8")
    client = _FakeClient(paused, _message([FETCH_RESULT, *ANSWER], model="claude-opus-4-8"))

    research.run_research_call("Research Acme Corp.", client=client)

    echoed = client.requests[1]["messages"][1]["content"]
    kinds = [(block["type"], block.get("id")) for block in echoed]
    assert ("thinking", None) not in kinds
    assert ("server_tool_use", "srvtoolu_lost") not in kinds
    assert ("server_tool_use", "srvtoolu_s1") in kinds  # answered, so kept
    assert ("server_tool_use", "srvtoolu_f1") in kinds  # after the boundary, kept as-is
    assert ("fallback", None) in kinds


def _status_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


@pytest.mark.parametrize("error, retryable, status", [
    (_status_error(anthropic.InternalServerError, 529), True, 529),
    (_status_error(anthropic.RateLimitError, 429), True, 429),
    (_status_error(anthropic.BadRequestError, 400), False, 400),
    (_status_error(anthropic.AuthenticationError, 401), False, 401),
])
def test_api_errors_become_one_typed_error_with_a_retry_hint(error, retryable, status):
    client = _FakeClient(error)

    with pytest.raises(research.ResearchProviderError) as caught:
        research.run_research_call("Research Acme Corp.", client=client)

    assert caught.value.retryable is retryable
    assert caught.value.status_code == status
    assert caught.value.usage.api_requests == 0


def test_connection_error_is_retryable():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    client = _FakeClient(anthropic.APIConnectionError(request=request))

    with pytest.raises(research.ResearchProviderError) as caught:
        research.run_research_call("Research Acme Corp.", client=client)

    assert caught.value.retryable is True
    assert caught.value.status_code is None


def test_failure_on_a_continuation_keeps_the_first_requests_usage():
    paused = _message([NARRATION], stop_reason="pause_turn")
    client = _FakeClient(paused, _status_error(anthropic.InternalServerError, 500))

    with pytest.raises(research.ResearchProviderError) as caught:
        research.run_research_call("Research Acme Corp.", client=client)

    assert caught.value.usage.api_requests == 1
    assert caught.value.usage.totals.input_tokens == 1000


def test_cost_is_none_for_a_model_with_no_price_row():
    usage = research.ResearchUsage(by_model={"claude-unpriced-9": research.TokenUsage(10, 10)})
    assert research.estimate_research_cost_usd(usage) is None


def test_cost_prices_cache_tokens_and_every_model():
    usage = research.ResearchUsage(
        by_model={
            "claude-opus-5": research.TokenUsage(1_000_000, 0, 1_000_000, 1_000_000),
            "claude-opus-4-8": research.TokenUsage(0, 1_000_000),
        },
        web_search_requests=100,
    )
    # 5 + 6.25 + 0.50 (opus-5) + 25 (opus-4-8 output) + 1.00 (100 searches)
    assert research.estimate_research_cost_usd(usage) == pytest.approx(37.75)
