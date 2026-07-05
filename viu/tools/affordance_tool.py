"""Инструменты Вью для сокетов и совместимости предметов."""

from __future__ import annotations

from typing import Any, Dict

from ..integrations.affordances import (
    DEFAULT_LIBRARY,
    describe_compatibility,
    get_from_library,
    load_affordance,
)
from .base import AgentContext, Tool, ToolResult


class AffordanceShowTool(Tool):
    name = "affordance_show"
    description = "Показать сокеты и возможные действия объекта (из библиотеки или по описанию)"
    parameters = {"object": "имя из библиотеки или JSON-описание"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        value = args.get("object")
        if not value:
            names = ", ".join(DEFAULT_LIBRARY.keys())
            return ToolResult(True, f"В библиотеке есть: {names}. Укажите object.")
        try:
            aff = load_affordance(value)
        except ValueError as exc:
            return ToolResult(False, str(exc))
        lines = [f"Объект: {aff.name}  (теги: {', '.join(aff.tags) or 'нет'})", "Сокеты:"]
        for s in aff.sockets:
            lines.append(f"  - {s.name}: теги [{', '.join(s.tags)}] принимает [{', '.join(s.accepts)}]")
        if aff.interactions:
            lines.append(f"Действия: {', '.join(aff.interactions)}")
        return ToolResult(True, "\n".join(lines))


class AffordanceMatchTool(Tool):
    name = "affordance_match"
    description = (
        "Проверить совместимость двух объектов: какие сокеты стыкуются и что можно сделать. "
        "Полезно перед генерацией анимации взаимодействия"
    )
    parameters = {"a": "первый объект (имя/JSON)", "b": "второй объект (имя/JSON)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        a_val, b_val = args.get("a"), args.get("b")
        if not a_val or not b_val:
            return ToolResult(False, "Нужны a и b")
        try:
            a = load_affordance(a_val)
            b = load_affordance(b_val)
        except ValueError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, describe_compatibility(a, b))
