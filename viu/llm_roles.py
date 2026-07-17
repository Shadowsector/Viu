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

# Чатовый NSFW-тег по умолчанию — обёртку не отключаем «молча».
_DEFAULT_REFLECT = "viu-cydonia"
_DEFAULT_WORK = "viu-qwen32"
_DEFAULT_CODE = "qwen2.5-coder:14b"


def _is_coder_tag(name: str) -> bool:
    low = (name or "").lower()
    return "coder" in low or low.endswith(":code")


def _is_viu_wrap(name: str) -> bool:
    return (name or "").strip().lower().startswith("viu-")


def resolve_model(config: Config, role: Role = "default") -> Optional[str]:
    """Явный тег роли или None (= смотри effective_model / config.model)."""
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


def effective_model(config: Config, role: Role = "default") -> str:
    """Реальный тег Ollama/API для запроса.

    Reflect/work без явной роли не падают на coder / голый VIU_MODEL —
    подставляем viu-обёртки. Code — наоборот, coder 14b.
    """
    resolved = resolve_model(config, role)
    if resolved:
        return resolved

    base = (config.model or "").strip()

    if role == "reflect":
        if _is_viu_wrap(base) and not _is_coder_tag(base):
            return base
        return _DEFAULT_REFLECT

    if role == "work":
        if _is_viu_wrap(base) and not _is_coder_tag(base):
            return base
        return _DEFAULT_WORK

    if role == "code":
        if base and _is_coder_tag(base):
            return base
        return (config.model_code or "").strip() or _DEFAULT_CODE

    return base or _DEFAULT_REFLECT


def model_label(config: Config, role: Role = "reflect") -> str:
    """Подпись для кнопки Дома: только тег модели (без дублей в статус-баре)."""
    return effective_model(config, role)


def needs_viu_wrap_hint(config: Config) -> bool:
    """True, если в .env reflect явно указан без viu-обёртки."""
    explicit = (config.model_reflect or "").strip()
    if not explicit:
        return False
    return not _is_viu_wrap(explicit)


def guess_work_role(task: str) -> Role:
    """Грубая эвристика: code vs work. Сюжетный чат сюда не попадает (это reflect)."""
    if _CODE_HINT_RE.search(task or ""):
        return "code"
    return "work"
