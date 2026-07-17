"""Инструменты автопилота: дорожная карта и состояние проекта Анабарра."""

from __future__ import annotations

from typing import Any, Dict

from ..project_state import next_step, project_status
from ..roadmap import RoadmapStore
from .base import AgentContext, Tool, ToolResult


def _store(ctx: AgentContext) -> RoadmapStore:
    return RoadmapStore(ctx.config.data_dir / "roadmap.json")


class RoadmapShowTool(Tool):
    name = "roadmap_show"
    description = "Показать дорожную карту игры Анабарра и текущий фокус"
    parameters: Dict[str, str] = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        return ToolResult(True, _store(ctx).roadmap.render())


class RoadmapUpdateTool(Tool):
    name = "roadmap_update"
    description = (
        "Обновить веху дорожной карты: статус (pending/in_progress/done/blocked) и заметку"
    )
    parameters = {
        "id": "номер вехи",
        "status": "pending | in_progress | done | blocked",
        "note": "заметка (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        try:
            mid = int(args.get("id"))
        except (TypeError, ValueError):
            return ToolResult(False, "Укажи числовой id вехи")
        status = str(args.get("status", "")).strip()
        note = args.get("note")
        try:
            m = _store(ctx).set_status(mid, status, note)
        except (KeyError, ValueError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, f"Веха {m.id}: {m.title} → {m.status}")


class ProjectStatusTool(Tool):
    name = "project_status"
    description = (
        "Снимок проекта: дорожная карта, состояние папки анимаций Unity, "
        "и конкретный следующий шаг. С этого стоит начинать автопилот."
    )
    parameters: Dict[str, str] = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        return ToolResult(True, project_status(ctx.config))


class NextStepTool(Tool):
    name = "next_step"
    description = "Что делать прямо сейчас к текущей цели дорожной карты"
    parameters: Dict[str, str] = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        return ToolResult(True, next_step(ctx.config))
