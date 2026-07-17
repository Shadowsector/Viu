"""Экспорт prepared asset в Unity (FBX)."""

from __future__ import annotations

from typing import Any, Dict

from ..integrations.blender.export_pipeline import format_export_report, run_export_pipeline
from .base import AgentContext, Tool, ToolResult


class ExportUnityAssetTool(Tool):
    name = "export_unity_asset"
    description = (
        "Экспорт *_prepared.blend в FBX: Library/Props/fbx + Unity/Assets/Environment/. "
        "Для домиков, сараев, props после разметки."
    )
    parameters = {
        "blend_file": "путь к *_prepared.blend (пусто = последний в Processed)",
        "force": "1 = экспорт даже если FBX свежий",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        force = str(args.get("force", "0")).lower() in ("1", "true", "yes")
        blend = str(args.get("blend_file", "")).strip() or None
        result = run_export_pipeline(ctx.config, blend_file=blend, force=force)
        return ToolResult(result.ok, format_export_report(result))
