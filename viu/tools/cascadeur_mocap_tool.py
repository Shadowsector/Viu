"""Инструменты: Comfy kept → Cascadeur Reference / MoCap / Export clip."""

from __future__ import annotations

from typing import Any, Dict

from ..integrations.cascadeur.reference_mocap import (
    finalize_export_clip,
    mocap_status_text,
    prepare_import_reference,
)
from .base import AgentContext, Tool, ToolResult


class CascadeurImportReferenceTool(Tool):
    name = "cascadeur_import_reference"
    description = (
        "Подготовить kept Comfy-mp4 как Reference в Cascadeur: staging, pending JSON, "
        "Commands Viu.ImportReference + чеклист MoCap. "
        "clip_id= или path= к mp4; иначе последний kept. slug= имя клипа/FBX."
    )
    parameters = {
        "clip_id": "id из comfy_clips.json (опционально)",
        "path": "путь к mp4 (опционально)",
        "slug": "имя клипа → shanya_<slug>.fbx",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        ok, msg, _ = prepare_import_reference(
            ctx.config,
            clip_id=str(args.get("clip_id") or "").strip(),
            path=str(args.get("path") or "").strip(),
            slug=str(args.get("slug") or "").strip(),
        )
        return ToolResult(ok, msg)


class CascadeurMocapAssistTool(Tool):
    name = "cascadeur_mocap_assist"
    description = (
        "То же, что cascadeur_import_reference + краткий статус очереди MoCap. "
        "Кнопку MoCap в Cascadeur API не жмёт — даёт чеклист и деплоит команды."
    )
    parameters = {
        "clip_id": "опционально",
        "path": "опционально",
        "slug": "опционально",
        "status_only": "1 = только статус, без prepare",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        if str(args.get("status_only") or "").strip() in ("1", "true", "yes"):
            return ToolResult(True, mocap_status_text(ctx.config))
        ok, msg, _ = prepare_import_reference(
            ctx.config,
            clip_id=str(args.get("clip_id") or "").strip(),
            path=str(args.get("path") or "").strip(),
            slug=str(args.get("slug") or "").strip(),
        )
        status = mocap_status_text(ctx.config)
        return ToolResult(ok, msg + "\n\n---\n" + status)


class CascadeurExportClipTool(Tool):
    name = "cascadeur_export_clip"
    description = (
        "После MoCap: проверить FBX в Animations (shanya_<slug>.fbx), "
        "задеплоить Viu.ExportClip если файла ещё нет, "
        "зарегистрировать клип в animation_catalog. "
        "slug= или path= к уже экспортированному FBX."
    )
    parameters = {
        "slug": "slug клипа (из pending)",
        "path": "готовый FBX, если уже экспортировал вручную",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        ok, msg = finalize_export_clip(
            ctx.config,
            slug=str(args.get("slug") or "").strip(),
            fbx_path=str(args.get("path") or "").strip(),
        )
        return ToolResult(ok, msg)
