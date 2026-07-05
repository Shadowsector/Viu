"""Инструмент уточнения у пользователя — останавливает цикл агента."""

from __future__ import annotations

from typing import Any, Dict

from .base import AgentContext, Tool, ToolResult


class AskUserTool(Tool):
    name = "ask_user"
    description = (
        "Задать пользователю уточняющий вопрос и остановиться. "
        "Используй, если без ответа нельзя продолжать (путь, версия, выбор варианта)."
    )
    parameters = {"question": "вопрос пользователю"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        q = str(args.get("question", "")).strip()
        if not q:
            return ToolResult(False, "Не указан question")
        return ToolResult(True, q)
