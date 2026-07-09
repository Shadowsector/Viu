"""Базовый интерфейс провайдера LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

# Сообщение в OpenAI-совместимом формате: {"role": ..., "content": ...}.
Message = Dict[str, str]


class LLMProvider(ABC):
    """Абстрактный провайдер языковой модели.

    Провайдер принимает список сообщений и возвращает текст ответа.
    Протокол «действий» агента (JSON) не зависит от конкретного провайдера,
    поэтому одна и та же логика работает и с реальным API, и с mock.
    """

    name: str = "base"

    @abstractmethod
    def complete(self, messages: List[Message], *, temperature: float | None = None) -> str:
        """Возвращает текстовый ответ модели на переданный диалог."""
        raise NotImplementedError
