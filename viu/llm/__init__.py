"""Слой провайдеров LLM для Вью."""

from .base import LLMProvider, Message
from .mock import MockLLM
from .openai_compatible import OpenAICompatibleLLM

__all__ = ["LLMProvider", "Message", "MockLLM", "OpenAICompatibleLLM", "build_provider"]


def build_provider(config):
    """Фабрика провайдера по конфигурации."""
    provider = (config.provider or "mock").lower()
    if provider == "mock":
        return MockLLM()
    if provider in ("openai", "openai_compatible", "openai-compatible"):
        return OpenAICompatibleLLM(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            temperature=config.temperature,
        )
    raise ValueError(f"Неизвестный провайдер LLM: {config.provider!r}")
