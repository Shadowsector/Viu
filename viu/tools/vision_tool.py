"""Инструменты для vision.md — общее направление проекта."""

from __future__ import annotations

from typing import Any, Dict

from ..vision import append_vision, read_vision
from .base import AgentContext, Tool, ToolResult


class VisionReadTool(Tool):
    name = "vision_read"
    description = "Прочитать vision.md — файл общего направления, идей и фокуса"
    parameters: Dict[str, str] = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        return ToolResult(True, read_vision(ctx.config))


class VisionAppendTool(Tool):
    name = "vision_append"
    description = "Добавить запись в vision.md (идея, сюжет, техника, решение Дена)"
    parameters = {
        "section": "заголовок блока, напр. «Сарай» или «Идея анимации»",
        "text": "что записать",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        section = str(args.get("section", "Заметка")).strip()
        text = str(args.get("text", "")).strip()
        if not text:
            return ToolResult(False, "Нужен text")
        msg = append_vision(ctx.config, section, text)
        return ToolResult(True, msg)
