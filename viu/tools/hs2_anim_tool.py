"""Инструменты: анимации Honey Select 2 → Inbox / каталог."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ..integrations.hs2 import (
    export_clip_json,
    hs2_fbx_dump_dir,
    import_fbx_dump,
    resolve_hs2_root,
    retarget_first_dump,
    retarget_hs2_fbx,
    scan_abdata,
)
from .base import AgentContext, Tool, ToolResult


class Hs2AnimStatusTool(Tool):
    name = "hs2_anim_status"
    description = (
        "Пути HS2: корень игры, fbx_dump, есть ли UnityPy/риг. "
        "Перед выдиранием анимаций из Honey Select 2."
    )
    parameters: Dict[str, str] = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        hs2 = resolve_hs2_root(ctx.config)
        dump = hs2_fbx_dump_dir(ctx.config)
        lines = [
            "HS2 анимации",
            f"VIU_HS2_ROOT: {hs2 or '(не найден)'}",
            f"fbx_dump: {dump}",
            f"FBX в дампе: {len(list(dump.rglob('*.fbx')))}",
        ]
        try:
            from UnityPy import Environment  # noqa: F401

            lines.append("UnityPy: установлен")
        except ImportError:
            lines.append("UnityPy: нет — pip install UnityPy (скан abdata)")
        from ..integrations.hs2.paths import default_retarget_rig_path

        rig = default_retarget_rig_path(ctx.config)
        lines.append(f"Retarget rig: {rig or '(положи Library/HS2/Mixamo_XBot.fbx)'}")
        return ToolResult(True, "\n".join(lines))


class Hs2AnimScanTool(Tool):
    name = "hs2_anim_scan"
    description = (
        "Скан abdata HS2 → список AnimationClip (UnityPy). "
        "Кэш: Library/HS2/animation_scan.json"
    )
    parameters = {
        "max_bundles": "сколько bundle-файлов открыть (default 200)",
        "refresh": "1 = игнорировать кэш",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        refresh = str(args.get("refresh", "0")).lower() in ("1", "true", "yes")
        max_b = int(args.get("max_bundles") or 200)
        result = scan_abdata(ctx.config, max_bundles=max_b, use_cache=not refresh)
        return ToolResult(result.ok, result.format_brief(limit=50))


class Hs2AnimExportJsonTool(Tool):
    name = "hs2_anim_export_json"
    description = "Экспорт одного клипа из abdata в JSON (для отладки / будущий bake)."
    parameters = {"clip_name": "имя AnimationClip из hs2_anim_scan"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        name = str(args.get("clip_name", "")).strip()
        if not name:
            return ToolResult(False, "Нужен clip_name")
        ok, msg = export_clip_json(ctx.config, name)
        return ToolResult(ok, msg)


class Hs2AnimImportFbxTool(Tool):
    name = "hs2_anim_import_fbx"
    description = (
        "FBX из Library/HS2/fbx_dump (MeshExporter) → Inbox/animations "
        "с именами для animation_catalog."
    )
    parameters = {
        "source_dir": "путь к папке дампа или пусто = fbx_dump",
        "limit": "макс. файлов (default 20)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        src = str(args.get("source_dir", "")).strip()
        source = Path(src).expanduser() if src else None
        limit = int(args.get("limit") or 20)
        report = import_fbx_dump(ctx.config, source_dir=source, limit=limit)
        return ToolResult(report.ok, report.format())


class Hs2AnimRetargetTool(Tool):
    name = "hs2_anim_retarget"
    description = (
        "Blender: HS2 FBX → humanoid (Mixamo rig) → Inbox/animations. "
        "file=путь или пусто = первый в fbx_dump."
    )
    parameters = {"file": "путь к HS2 FBX с анимацией"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        raw = str(args.get("file", "")).strip()
        if raw:
            ok, msg = retarget_hs2_fbx(ctx.config, Path(raw))
        else:
            ok, msg = retarget_first_dump(ctx.config)
        return ToolResult(ok, msg)
