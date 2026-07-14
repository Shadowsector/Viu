"""Прямые команды чата → инструмент без Ollama (lab_start, blender_export_*, …)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

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
_ARG_RE = re.compile(r"(\w+)=([\w.:\\/+_-]+)")


def parse_direct_tool_command(text: str, registry) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Если строка — имя инструмента + key=value, вернуть (name, args). Иначе None."""
    raw = (text or "").strip()
    if not raw:
        return None
    # Естественная речь (кириллица) — агент, не прямой tool.
    if re.search(r"[а-яА-ЯёЁ]", raw):
        return None
    m = _DIRECT_RE.match(raw)
    if not m:
        return None
    name = m.group(1).lower()
    if name in _AGENT_ONLY:
        return None
    if registry.get(name) is None:
        return None
    args: Dict[str, Any] = {}
    tail = (m.group(2) or "").strip()
    for key, val in _ARG_RE.findall(tail):
        args[key.lower()] = val
    if name.startswith("lab_") and "topic" not in args:
        args.setdefault("topic", "cascadeur")
    return name, args
