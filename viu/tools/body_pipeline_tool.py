"""Чеклист тела Шани — простые шаги."""

from __future__ import annotations

from typing import Any, Dict

from ..body_pipeline import mark_step_done, render_checklist, set_step
from .base import AgentContext, Tool, ToolResult


class BodyPipelineTool(Tool):
    name = "body_pipeline"
    description = (
        "Чеклист тела Шани простыми словами: status | done | set. "
        "Не Comfy/Cascadeur — только Inbox → Blender → Rigify → Unity."
    )
    parameters = {
        "action": "status | done | set",
        "step": "для set или done: stage_pack|open_blender|shrinkwrap|rigify|export_fbx|unity_humanoid",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        action = str(args.get("action") or "status").strip().lower()
        if action in ("status", "show", ""):
            return ToolResult(ok=True, content=render_checklist(ctx.config))
        if action in ("done", "next", "complete"):
            step = str(args.get("step") or "").strip() or None
            _, msg = mark_step_done(ctx.config, step)
            return ToolResult(
                ok=True,
                content=f"{msg}\n\n{render_checklist(ctx.config)}",
            )
        if action == "set":
            step = str(args.get("step") or "").strip()
            if not step:
                return ToolResult(ok=False, content="нужен step=")
            ok, msg = set_step(ctx.config, step)
            return ToolResult(
                ok=ok,
                content=f"{msg}\n\n{render_checklist(ctx.config)}" if ok else msg,
            )
        return ToolResult(ok=False, content="action: status|done|set")
