"""Офлайн mock-провайдер.

Нужен по двум причинам:
1. Детерминированное тестирование всего цикла агента без сети и API-ключа.
2. Демонстрация работы (`python -m viu demo`) на любой машине.

Поддерживает два режима:
* «сценарий» — заранее заданный список ответов, отдаётся по очереди;
* «правила» — простой ответ по умолчанию, если сценарий исчерпан.
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional

from .base import LLMProvider, Message


class MockLLM(LLMProvider):
    name = "mock"

    def __init__(
        self,
        responses: Optional[List[str]] = None,
        responder: Optional[Callable[[List[Message]], str]] = None,
    ) -> None:
        # Копируем, чтобы не мутировать переданный список у вызывающего.
        self._responses = list(responses) if responses else []
        self._responder = responder

    def complete(
        self,
        messages: List[Message],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        del temperature, model
        if self._responses:
            return self._responses.pop(0)
        if self._responder is not None:
            return self._responder(messages)
        return self._default(messages)

    @staticmethod
    def _default(messages: List[Message]) -> str:
        """Ответ по умолчанию: завершить задачу с честной оговоркой.

        Возвращает валидный JSON согласно протоколу агента, чтобы цикл
        корректно завершился даже без настроенной модели.
        """
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        return json.dumps(
            {
                "thought": "Работаю в офлайн mock-режиме без реальной модели.",
                "final": (
                    "Это mock-ответ Вью. Задача получена: "
                    f"«{last_user[:200]}». Для полноценной работы задайте "
                    "VIU_PROVIDER=openai и VIU_API_KEY."
                ),
            },
            ensure_ascii=False,
        )
