"""Таймаут LLM / Ollama."""

from viu.config import Config
from viu.llm import build_provider
from viu.llm.openai_compatible import OpenAICompatibleLLM


def test_default_llm_timeout_is_long():
    c = Config(provider="openai", api_key="ollama", base_url="http://localhost:11434/v1")
    assert c.llm_timeout >= 1800
    p = build_provider(c)
    assert isinstance(p, OpenAICompatibleLLM)
    assert p.timeout >= 1800


def test_llm_timeout_from_env(monkeypatch):
    monkeypatch.setenv("VIU_LLM_TIMEOUT", "1800")
    c = Config(provider="openai", api_key="x")
    assert c.llm_timeout == 1800.0
