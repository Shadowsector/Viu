"""Провайдер для любого OpenAI-совместимого Chat Completions API.

Использует только стандартную библиотеку (urllib), чтобы не тянуть
зависимости. Подходит для OpenAI, локальных серверов (Ollama, LM Studio,
vLLM, LocalAI) и прочих совместимых эндпоинтов.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List

from .base import LLMProvider, Message


class OpenAICompatibleLLM(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def complete(self, messages: List[Message], *, temperature: float | None = None) -> str:
        if not self.api_key:
            raise RuntimeError(
                "Не задан VIU_API_KEY. Укажите ключ или используйте VIU_PROVIDER=mock."
            )
        url = f"{self.base_url}/chat/completions"
        temp = self.temperature if temperature is None else temperature
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - сетевой путь
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Ошибка LLM API {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - сетевой путь
            raise RuntimeError(f"Сетевая ошибка при обращении к LLM: {exc.reason}") from exc

        try:
            return body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:  # pragma: no cover - защита от кривого ответа
            raise RuntimeError(f"Неожиданный формат ответа LLM: {body}") from exc
