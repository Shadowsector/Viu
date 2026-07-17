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

# Выбор в GUI (runtime.json → reflect_model). id → подсказка в combobox.
REFLECT_MODEL_CHOICES: tuple[tuple[str, str], ...] = (
    ("viu-cydonia", "чат / ERP"),
    ("viu-command-r", "GDD / квесты"),
    ("viu-magnum", "лит. NSFW"),
    ("viu-qwen32", "общая 32B"),
)

REFLECT_MODEL_IDS: tuple[str, ...] = tuple(c[0] for c in REFLECT_MODEL_CHOICES)


def _is_coder_tag(name: str) -> bool:
    low = (name or "").lower()
    return "coder" in low or low.endswith(":code")


def _is_viu_wrap(name: str) -> bool:
    return (name or "").strip().lower().startswith("viu-")


def _runtime_reflect_override(config: Config) -> str:
    from .runtime_settings import get_reflect_model_override

    return get_reflect_model_override(config)


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
    Для reflect сначала смотрим runtime.json (выбор в GUI).
    """
    if role == "reflect":
        rt = _runtime_reflect_override(config)
        if rt:
            return rt

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


def reflect_combo_labels() -> list[str]:
    """Подписи для Combobox: viu-cydonia · чат."""
    return [f"{mid} · {hint}" for mid, hint in REFLECT_MODEL_CHOICES]


def reflect_model_from_combo(label: str) -> str:
    """id из строки combobox или голый id."""
    raw = (label or "").strip()
    if not raw:
        return ""
    if " · " in raw:
        return raw.split(" · ", 1)[0].strip()
    return raw.split()[0].strip()


def set_reflect_model(config: Config, model_id: str) -> None:
    from .runtime_settings import set_reflect_model_override

    set_reflect_model_override(config, model_id)


def model_label(config: Config, role: Role = "reflect") -> str:
    """Подпись reflect-модели (кнопка / Telegram /status)."""
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
