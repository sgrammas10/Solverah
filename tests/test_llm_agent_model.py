"""The agent chat's default Groq model and its env override.

Regression: the default was ``llama-3.1-8b-instant``, which Groq retired, so
every agent turn in prod came back 422 "Model ... not found on Groq." with no
way to change the model short of a deploy.
"""

from solverah.infra import llm

RETIRED = "llama-3.1-8b-instant"


def test_default_is_not_the_retired_model(monkeypatch):
    monkeypatch.delenv("SOLVERAH_AGENT_MODEL", raising=False)
    assert llm.default_agent_model() != RETIRED
    assert llm.default_agent_model() == "openai/gpt-oss-20b"


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("SOLVERAH_AGENT_MODEL", "  some/other-model  ")
    assert llm.default_agent_model() == "some/other-model"


def test_blank_env_override_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("SOLVERAH_AGENT_MODEL", "   ")
    assert llm.default_agent_model() == llm.DEFAULT_AGENT_MODEL
