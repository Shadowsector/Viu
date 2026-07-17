"""Инструмент: подготовить asset из Inbox для Unity."""

from __future__ import annotations

from typing import Any, Dict

from ..integrations.blender.prepare_asset import (
    format_prepare_report,
    run_inbox_prepare_pipeline,
)
from ..prop_catalog import PropCatalogStore, catalog_path
from .base import AgentContext, Tool, ToolResult


class PrepareUnityAssetTool(Tool):
    name = "prepare_unity_asset"
    description = (
        "Принять asset для Unity: .blend из Inbox (или явный путь), восстановить textures, "
        "relink+pack, скрыть фон, сохранить в Processed, открыть Blender."
    )
    parameters = {
        "blend_file": "путь к .blend (опционально; иначе только Inbox)",
        "open_blender": "1 = открыть Blender после подготовки (по умолчанию 1)",
        "allow_library_fallback": "1 = если Inbox пуст, взять последний .blend из Library (агент)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        open_blender = str(args.get("open_blender", "1")).lower() not in ("0", "false", "no")
        allow_lib = str(args.get("allow_library_fallback", "0")).lower() in ("1", "true", "yes")
        store = PropCatalogStore(catalog_path(ctx.config))
        try:
            report = run_inbox_prepare_pipeline(
                ctx.config,
                blend_file=args.get("blend_file") or "",
                open_blender=open_blender,
                catalog_store=store,
                allow_library_fallback=allow_lib,
            )
        except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, format_prepare_report(report))
