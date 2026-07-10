"""Инструменты: домики (стены) и Cascadeur."""

from __future__ import annotations

from typing import Any, Dict

from ..building_workflow import building_status_text, parse_building_notes, read_sidecar_for_blend
from ..integrations.cascadeur import cascadeur_status
from .base import AgentContext, Tool, ToolResult


class BuildingWorkflowTool(Tool):
    name = "building_workflow"
    description = (
        "Где лежит prepared-сарай/домик, чеклист отрезания стены (open_wall из notes.txt). "
        "Не бери сырой blend из Mascot — только Processed."
    )
    parameters = {
        "name_hint": "часть имени, напр. stables или old (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        hint = str(args.get("name_hint", "")).strip()
        text = building_status_text(ctx.config, name_hint=hint)
        return ToolResult(True, text)


class CascadeurStatusTool(Tool):
    name = "cascadeur_status"
    description = (
        "Пути Cascadeur Inbox/Export, проверка VIU_CASCADEUR_EXE. "
        "FBX для правки анимаций перед Unity."
    )
    parameters: dict = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        ok, text = cascadeur_status(ctx.config)
        return ToolResult(ok, text)
