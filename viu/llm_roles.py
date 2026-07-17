"""Выбор модели Ollama/API по роли запроса (reflect / work / code)."""

from __future__ import annotations

import re
from typing import Literal, Optional

from .config import Config

Role = Literal["reflect", "work", "code", "default"]

_CODE_HINT_RE = re.compile(
    r"(?i)\b(код|скрипт|python|c#|unity\.cs|\.cs\b|баг|traceback|exception|"
    r"рефактор|compile|compiler|stack\s*trace)\b"
)


def resolve_model(config: Config, role: Role = "default") -> Optional[str]:
    """Имя модели для запроса или None (= провайдер использует config.model)."""
    if role == "reflect":
        m = (config.model_reflect or "").strip()
        return m or None
    if role == "work":
        m = (config.model_work or "").strip()
        return m or None
    if role == "code":
        m = (config.model_code or config.model_work or "").strip()
        return m or None
    return None


def guess_work_role(task: str) -> Role:
    """Грубая эвристика: code vs work. Сюжетный чат сюда не попадает (это reflect)."""
    if _CODE_HINT_RE.search(task or ""):
        return "code"
    return "work"
