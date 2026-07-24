"""Инструменты каталога предметов (props)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ..prop_catalog import (
    PropCatalogStore,
    catalog_path,
    ensure_layout,
    inbox_dir,
    library_root,
    sort_inbox_and_catalog,
)
from .base import AgentContext, Tool, ToolResult


def _store(ctx: AgentContext) -> PropCatalogStore:
    return PropCatalogStore(catalog_path(ctx.config))


class PropCatalogScanTool(Tool):
    name = "prop_catalog_scan"
    description = (
        "Сканировать папку на FBX/blend/obj и добавить в каталог предметов "
        "(для GUI-разметки: вес, сидеть, поднять…)"
    )
    parameters = {
        "folder": "путь к папке",
        "recursive": "искать в подпапках (по умолчанию true)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        folder = args.get("folder", "")
        if not folder:
            return ToolResult(False, "Укажи folder")
        store = _store(ctx)
        try:
            n, seen = scan_folder(
                Path(folder),
                store,
                recursive=str(args.get("recursive", "true")).lower() not in ("0", "false", "no"),
                blender_exe=ctx.config.blender_exe,
            )
        except OSError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(
            True,
            f"Добавлено новых: {n}, уже были: {seen}.\n"
            f"Каталог: {store.path}\n\n{store.render_summary()}\n\n"
            "Открой GUI: кнопка «Разметить предметы».",
        )


class PropCatalogListTool(Tool):
    name = "prop_catalog_list"
    description = "Показать каталог предметов: что размечено и что ждёт очереди"
    parameters = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        store = _store(ctx)
        lines = [store.render_summary(), ""]
        for e in store.reviewed()[:30]:
            w = f", {e.weight_kg} кг" if e.weight_kg else ""
            acts = ", ".join(e.interactions) if e.interactions else "—"
            mesh = f" / {e.mesh_name}" if e.mesh_name else ""
            role = f" [{e.role}]" if e.role else ""
            lines.append(f"  ✓ {e.guess_display_name()}{mesh}{role} [{e.category}]{w} — {acts}")
        return ToolResult(True, "\n".join(lines))


class PropOrganizeDownloadsTool(Tool):
    name = "prop_organize_downloads"
    description = (
        "Разобрать Inbox (U:\\Anabarra\\Inbox): blend/fbx/папки → U:\\Anabarra\\Library. "
        "Не лезет на C:\\Downloads и не сканирует Desktop Mascot. dry_run=1 — только план."
    )
    parameters = {
        "dry_run": "1 = не перемещать, только показать план",
        "inbox": "путь к Inbox (опционально, по умолчанию U:\\Anabarra\\Inbox)",
        "downloads": "устаревший алиас для inbox",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        inbox_raw = args.get("inbox") or args.get("downloads") or str(inbox_dir(ctx.config))
        lib = library_root(ctx.config)
        dry = str(args.get("dry_run", "1")).lower() in ("1", "true", "yes")
        store = _store(ctx)
        try:
            ensure_layout(ctx.config)
            lines, new_cat = sort_inbox_and_catalog(
                Path(inbox_raw),
                lib,
                store,
                dry_run=dry,
                blender_exe=ctx.config.blender_exe,
            )
        except OSError as exc:
            return ToolResult(False, str(exc))
        head = "План (dry-run):" if dry else "Перемещено из Inbox:"
        body = "\n".join(lines[:50])
        if len(lines) > 50:
            body += f"\n… ещё {len(lines) - 50} файлов"
        extra = "" if dry else f"\n\nВ каталог добавлено 3D: {new_cat}"
        return ToolResult(
            True,
            f"{head}\nInbox: {inbox_raw}\nБиблиотека: {lib}\n\n{body}{extra}",
        )
