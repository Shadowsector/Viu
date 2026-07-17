"""Инструменты планирования многоэтапных задач."""

from __future__ import annotations

from typing import Any, Dict

from .base import AgentContext, Tool, ToolResult


class PlanCreateTool(Tool):
    name = "plan_create"
    description = "Создать план: цель и список шагов"
    parameters = {"goal": "цель", "steps": "список названий шагов"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        goal = args.get("goal", "")
        steps = args.get("steps", [])
        if isinstance(steps, str):
            steps = [s.strip() for s in steps.split("\n") if s.strip()]
        if not steps:
            return ToolResult(False, "Не указаны steps")
        plan = ctx.planner.create(goal, steps)
        return ToolResult(True, "План создан:\n" + plan.render())


class PlanUpdateTool(Tool):
    name = "plan_update"
    description = "Обновить статус/заметку шага плана"
    parameters = {
        "step_id": "номер шага",
        "status": "pending|in_progress|done|blocked",
        "note": "заметка (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        try:
            step_id = int(args.get("step_id"))
        except (TypeError, ValueError):
            return ToolResult(False, "step_id должен быть числом")
        status = args.get("status")
        note = args.get("note")
        try:
            ctx.planner.update_step(step_id, status=status, note=note)
        except (KeyError, ValueError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, "Обновлено:\n" + ctx.planner.plan.render())


class PlanShowTool(Tool):
    name = "plan_show"
    description = "Показать текущий план"
    parameters = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        return ToolResult(True, ctx.planner.plan.render())
