"""Инструмент «Следующий шаг» — один клик для Дена."""

from __future__ import annotations

from typing import Any, Dict

from ..director import format_banner, plan_next_step
from .base import AgentContext, Tool, ToolResult


class RunNextStepTool(Tool):
    name = "run_next_step"
    description = "План и описание одного следующего шага (без выполнения — для GUI используй __next_step__)"
    parameters: Dict[str, str] = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        plan = plan_next_step(ctx.config)
        body = format_banner(plan)
        if plan.idle or not plan.tool:
            return ToolResult(True, body + "\n\n(Автодействие не требуется — смотри подсказку выше.)")
        return ToolResult(
            True,
            body + f"\n\nИнструмент: {plan.tool}\n(В GUI это делает кнопка «Следующий шаг».)",
        )
