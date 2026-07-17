"""Проверки здоровья внешних сервисов для статус-бара GUI."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List


def ollama_available(base_url: str = "http://localhost:11434/v1") -> bool:
    """Ollama отвечает на /api/tags."""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    url = f"{root}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        return isinstance(data.get("models"), list)
    except (OSError, json.JSONDecodeError, urllib.error.URLError):
        return False


def ollama_models(base_url: str = "http://localhost:11434/v1") -> List[str]:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    url = f"{root}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        models = data.get("models") or []
        return [m.get("name", "") for m in models if m.get("name")]
    except (OSError, json.JSONDecodeError, urllib.error.URLError):
        return []
