"""Прямые команды чата → инструмент без Ollama (lab_start, blender_export_*, …)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Инструменты, которые всегда через агента (не one-shot).
_AGENT_ONLY = frozenset(
    {
        "ask_user",
        "improve_prompt",
        "add_tool",
        "self_inspect",
        "web_search",
        "web_fetch",
        "run_shell",
        "memory_write",
        "memory_search",
        "plan_create",
        "plan_update",
        "plan_show",
    }
)

_DIRECT_RE = re.compile(
    r"^([a-z][a-z0-9_]*(?:_[a-z0-9_]*)*)(?:\s+(.+))?$",
    re.IGNORECASE,
)
_ARG_RE = re.compile(r"(\w+)=([^\s]+)")

# Русские ярлыки → tool (без Ollama).
_RU_ALIASES: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "сканируй существ": ("creature_catalog_scan", {}),
    "скан существ": ("creature_catalog_scan", {}),
    "сканировать существ": ("creature_catalog_scan", {}),
    "авто размер существ": ("creature_catalog_auto_size", {}),
    "авторазметка существ": ("creature_catalog_auto_size", {}),
    "каталог существ": ("creature_catalog_show", {"mode": "summary"}),
    "очередь существ": ("creature_catalog_show", {"mode": "pending"}),
    "линейка существ": ("creature_lineup", {}),
    "lineup существ": ("creature_lineup", {}),
    "blocking сцены": ("interaction_blocking", {}),
    "сцена blocking": ("interaction_blocking", {}),
    "master ref сцены": ("interaction_master_draft", {}),
    "master ref": ("interaction_master_draft", {}),
    "совместные анимации": ("interaction_catalog_show", {"mode": "holes"}),
    "промпт comfy": ("comfy_prompt", {}),
    "покажи промпт": ("comfy_prompt", {}),
    "что за промпт": ("comfy_prompt", {}),
    "wan промпт": ("comfy_prompt", {}),
    "статус comfy": ("comfy_status", {}),
    "статус comfi": ("comfy_status", {}),
    "comfy статус": ("comfy_status", {}),
    "что делает comfy": ("comfy_status", {}),
    "диагностика comfy": ("comfy_diag", {}),
    "диагностика комфи": ("comfy_diag", {}),
    "comfy diag": ("comfy_diag", {}),
    "comfy_diag": ("comfy_diag", {}),
    "почему не генерит": ("comfy_diag", {}),
    "почему не снимает": ("comfy_diag", {}),
    "lab статус": ("lab_status", {"topic": "comfy"}),
    "статус lab": ("lab_status", {"topic": "comfy"}),
    "запусти comfy": ("comfy_ensure", {}),
    "подними comfy": ("comfy_ensure", {}),
    "comfy ensure": ("comfy_ensure", {}),
    "перезапусти comfy": ("comfy_ensure", {"restart": "1"}),
    "рестарт comfy": ("comfy_ensure", {"restart": "1"}),
    "фокус nsfw": ("comfy_focus", {"focus": "nsfw"}),
    "фокус сарай": ("comfy_focus", {"focus": "barn"}),
    "comfy фокус nsfw": ("comfy_focus", {"focus": "nsfw"}),
    "очисти очередь comfy": ("comfy_queue_clear", {"force": "1"}),
    "сброс очереди comfy": ("comfy_queue_clear", {"force": "1"}),
    "comfy queue clear": ("comfy_queue_clear", {"force": "1"}),
    "почини reactor": ("comfy_reactor_fix", {}),
    "comfy reactor fix": ("comfy_reactor_fix", {}),
}


def _parse_args(tail: str) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    for key, val in _ARG_RE.findall(tail or ""):
        args[key.lower()] = val
    return args


def _longest_tool_prefix(token: str, names: List[str]) -> Optional[str]:
    """Найти самое длинное имя инструмента, с которого начинается token.

    Ловит опечатки вроде creature_catalog_scancreature_catalog_scan (имя дважды).
    """
    low = (token or "").lower()
    best: Optional[str] = None
    for name in names:
        if low == name or low.startswith(name):
            if best is None or len(name) > len(best):
                best = name
    return best


def parse_direct_tool_command(text: str, registry) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Если строка — имя инструмента + key=value, вернуть (name, args). Иначе None."""
    raw = (text or "").strip()
    if not raw:
        return None

    # Русские ярлыки (целиком или начало строки).
    low_full = re.sub(r"\s+", " ", raw.lower())
    for phrase, (tool, base_args) in _RU_ALIASES.items():
        if low_full == phrase or low_full.startswith(phrase + " "):
            if registry.get(tool) is None:
                return None
            args = dict(base_args)
            rest = raw[len(phrase) :].strip()
            args.update(_parse_args(rest))
            return tool, args

    # Естественная речь (кириллица) — агент, не прямой tool.
    if re.search(r"[а-яА-ЯёЁ]", raw):
        return None

    names = sorted(
        (n for n in registry.names() if n not in _AGENT_ONLY),
        key=len,
        reverse=True,
    )

    m = _DIRECT_RE.match(raw)
    if m:
        name = m.group(1).lower()
        tail = (m.group(2) or "").strip()
        if name not in _AGENT_ONLY and registry.get(name) is not None:
            args = _parse_args(tail)
            if name.startswith("lab_") and "topic" not in args:
                args.setdefault("topic", "cascadeur")
            return name, args
        # Имя склеилось / с хвостом: creature_catalog_scancreature_…
        matched = _longest_tool_prefix(name, names)
        if matched is not None:
            remainder = name[len(matched) :] + ((" " + tail) if tail else "")
            args = _parse_args(remainder.strip())
            # хвост без = — мусор от двойного ввода, игнор
            if matched.startswith("lab_") and "topic" not in args:
                args.setdefault("topic", "cascadeur")
            return matched, args

    # Первое «слово» без пробелов — снова longest prefix
    first = raw.split(None, 1)[0].lower()
    matched = _longest_tool_prefix(first, names)
    if matched is not None:
        rest = raw[len(first) :].strip()
        # если first длиннее имени — остаток имени отбросить
        args = _parse_args(rest)
        if matched.startswith("lab_") and "topic" not in args:
            args.setdefault("topic", "cascadeur")
        return matched, args

    return None


def looks_like_missing_creature_tool(text: str) -> bool:
    """Строка про существ, но инструмента в реестре ещё нет (старая сборка)."""
    raw = (text or "").strip().lower()
    if not raw:
        return False
    if raw.startswith("creature_catalog") or raw.startswith("creature_lineup"):
        return True
    return any(raw.startswith(p) or raw == p for p in _RU_ALIASES) or raw in (
        "разметить существ",
        "разметка существ",
        "размечай существ",
    )
