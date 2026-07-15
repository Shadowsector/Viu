"""Инструменты каталога существ."""

from __future__ import annotations

from typing import Any, Dict, List

from ..creature_catalog import (
    CreatureCatalogStore,
    build_lineup_job,
    creature_catalog_path,
    ensure_girl_sockets_doc,
    list_size_classes_text,
    scan_creatures_inbox,
)
from ..creature_catalog.models import ALL_SIZE_IDS, LOCOMOTION
from .base import AgentContext, Tool, ToolResult


class CreatureCatalogScanTool(Tool):
    name = "creature_catalog_scan"
    description = (
        "Сканировать Lab/Creatures/Inbox (+ Lab/Models/Inbox) → creature_catalog.json. "
        "Новые модели без size_class; подсказки по имени в notes/tags."
    )
    parameters: dict = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        _a, _t, msg = scan_creatures_inbox(ctx.config)
        ensure_girl_sockets_doc(ctx.config)
        return ToolResult(True, msg + "\n\n" + list_size_classes_text())


class CreatureCatalogShowTool(Tool):
    name = "creature_catalog_show"
    description = (
        "Показать каталог существ / классы роста / сокеты девушек. "
        "mode=summary|pending|classes|sockets|all"
    )
    parameters = {"mode": "summary | pending | classes | sockets | all"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        mode = str(args.get("mode") or "summary").strip().lower()
        store = CreatureCatalogStore(creature_catalog_path(ctx.config)).load()
        sock_path = ensure_girl_sockets_doc(ctx.config)
        if mode == "classes":
            return ToolResult(True, list_size_classes_text())
        if mode == "sockets":
            return ToolResult(
                True,
                f"Сокеты девушек (файл {sock_path}):\n"
                + sock_path.read_text(encoding="utf-8"),
            )
        if mode == "pending":
            lines = [e.render_line() + f"  id={e.id}" for e in store.pending()]
            return ToolResult(True, "\n".join(lines) or "Очередь пуста.")
        if mode == "all":
            lines = [e.render_line() + f"  id={e.id}" for e in store.all()]
            return ToolResult(
                True,
                store.summary_text() + "\n\n" + ("\n".join(lines) or "(пусто)"),
            )
        return ToolResult(True, store.summary_text() + f"\nСокеты: {sock_path}")


class CreatureCatalogSetSizeTool(Tool):
    name = "creature_catalog_set_size"
    description = (
        "Проставить size_class существу. id= или slug=; size=mini|small|humanoid|large|huge|"
        "quad_mini|quad_med|quad_large; size_alt= через запятую (dual); "
        "locomotion=biped|quadruped|amorph|tentacle|mimic|flyer; nsfw=1."
    )
    parameters = {
        "id": "id записи",
        "slug": "slug если нет id",
        "size": "size_class",
        "size_alt": "доп. классы через запятую",
        "locomotion": "locomotion",
        "nsfw": "1 = nsfw_capable",
        "notes": "заметка",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        size = str(args.get("size") or "").strip()
        if size not in ALL_SIZE_IDS:
            return ToolResult(
                False,
                f"size= должен быть один из: {', '.join(ALL_SIZE_IDS)}\n"
                + list_size_classes_text(),
            )
        store = CreatureCatalogStore(creature_catalog_path(ctx.config)).load()
        cid = str(args.get("id") or "").strip()
        slug = str(args.get("slug") or "").strip()
        entry = store.get(cid) if cid else None
        if entry is None and slug:
            entry = store.get_by_slug(slug)
        if entry is None:
            # частичный id
            if cid:
                for e in store.all():
                    if e.id.startswith(cid) or cid in e.id:
                        entry = e
                        break
        if entry is None:
            return ToolResult(False, "Не найдена запись — creature_catalog_show mode=pending")

        alt_raw = str(args.get("size_alt") or "")
        size_alt = [p.strip() for p in alt_raw.split(",") if p.strip()]
        for a in size_alt:
            if a not in ALL_SIZE_IDS:
                return ToolResult(False, f"size_alt неизвестен: {a}")

        loco = str(args.get("locomotion") or "").strip()
        if loco and loco not in LOCOMOTION:
            return ToolResult(False, f"locomotion= один из {', '.join(LOCOMOTION)}")

        updated = store.set_size(
            entry.id,
            size,
            size_alt=size_alt or None,
            locomotion=loco,
            notes=str(args.get("notes") or ""),
        )
        if updated is None:
            return ToolResult(False, "Не удалось обновить")
        if str(args.get("nsfw") or "").strip() in ("1", "true", "yes"):
            updated.nsfw_capable = True
            store.upsert(updated)
        store.save()
        return ToolResult(
            True,
            f"OK: {updated.render_line()}\n"
            f"anim_bucket=`{updated.anim_bucket()}`\n"
            "Дальше: creature_lineup — сравнить рост с Шаней в Blender.",
        )


class CreatureLineupTool(Tool):
    name = "creature_lineup"
    description = (
        "Собрать Blender lineup: Шаня + существа с size_class в одном кадре для сравнения роста. "
        "size= фильтр классов через запятую; shanya_path= явный FBX/blend Шани."
    )
    parameters = {
        "size": "фильтр size_class через запятую (пусто = все размеченные)",
        "shanya_path": "путь к модели Шани",
        "spacing": "метры между фигурами (1.2)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        sizes = [p.strip() for p in str(args.get("size") or "").split(",") if p.strip()]
        try:
            spacing = float(args.get("spacing") or 1.2)
        except (TypeError, ValueError):
            spacing = 1.2
        ok, msg, _ = build_lineup_job(
            ctx.config,
            size_filter=sizes,
            shanya_path=str(args.get("shanya_path") or "").strip(),
            spacing_m=spacing,
        )
        return ToolResult(ok, msg)
