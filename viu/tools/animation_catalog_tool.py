"""Инструменты каталога анимаций и разбор Inbox."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ..animation_catalog import (
    ANIMATION_CATEGORIES,
    AnimationCatalogStore,
    animation_catalog_path,
    match_fbx_to_wish,
)
from ..drop_router import accept_single_animation, route_inbox
from .base import AgentContext, Tool, ToolResult


class AnimationCatalogShowTool(Tool):
    name = "animation_catalog_show"
    description = (
        "Каталог анимаций Шани: категории, описания «когда/как/зачем», "
        "что уже импортировано и чего не хватает (wave 1)."
    )
    parameters = {
        "category": "фильтр категории (locomotion, adventure, …) или пусто = всё",
        "missing_only": "1 = только без клипа",
        "slug": "одна запись по slug (climb_up, sit_idle, …)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        store = AnimationCatalogStore(animation_catalog_path(ctx.config)).load()
        slug = str(args.get("slug", "")).strip()
        if slug:
            w = store.get_by_slug(slug)
            if not w:
                return ToolResult(False, f"Нет записи slug={slug}")
            return ToolResult(True, w.render_block())

        cat = str(args.get("category", "")).strip()
        missing = str(args.get("missing_only", "0")).lower() in ("1", "true", "yes")
        wishes = store.all_wishes()
        if cat:
            wishes = [w for w in wishes if w.category == cat]
        if missing:
            wishes = [w for w in wishes if w.status == "wished"]

        if not wishes:
            return ToolResult(True, store.summary_text() + "\n\n(пусто по фильтру)")

        lines = [store.summary_text(), ""]
        cur_cat = ""
        for w in wishes:
            if w.category != cur_cat:
                cur_cat = w.category
                label = ANIMATION_CATEGORIES.get(cur_cat, (cur_cat, ""))[0]
                lines.append(f"\n## {label} ({cur_cat})")
            status = "✓" if w.status != "wished" else "○"
            lines.append(f"{status} **{w.title_ru}** (`{w.slug}`, wave {w.wave})")
            lines.append(f"  Когда: {w.when_used}")
            lines.append(f"  Как: {w.looks_like}")
        return ToolResult(True, "\n".join(lines))


class AnimationCatalogMatchTool(Tool):
    name = "animation_catalog_match"
    description = "Сопоставить FBX-файл с записью каталога (по имени Mixamo)."
    parameters = {"file": "путь к .fbx"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        path = Path(str(args.get("file", ""))).expanduser()
        if not path.is_file():
            return ToolResult(False, f"Файл не найден: {path}")
        store = AnimationCatalogStore(animation_catalog_path(ctx.config)).load()
        wish, score, reason = match_fbx_to_wish(path, store)
        if not wish:
            return ToolResult(
                True,
                f"Не удалось сопоставить {path.name} ({reason}).\n"
                "Переименуй или добавь override в viu_clips.json.",
            )
        return ToolResult(
            True,
            f"Match {score:.0%}: {path.name}\n→ {wish.title_ru} ({wish.slug})\n"
            f"Категория: {wish.category}\n{reason}\n\n{wish.looks_like}",
        )


class AcceptAnimationInboxTool(Tool):
    name = "accept_animation_inbox"
    description = (
        "Один Mixamo FBX из Inbox → Unity Animations + очередь описания (scope, когда/как)."
    )
    parameters = {
        "copy_to_unity": "1 = копировать в Assets/…/Animations",
        "keep_inbox": "1 = не удалять из Inbox",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        copy = str(args.get("copy_to_unity", "1")).lower() not in ("0", "false", "no")
        keep = str(args.get("keep_inbox", "0")).lower() in ("1", "true", "yes")
        report = accept_single_animation(
            ctx.config,
            copy_to_unity=copy,
            remove_from_inbox=not keep,
        )
        body = report.format()
        if report.open_animation_review:
            body += "\n\n→ Открой «Очередь анимаций» или GUI откроет сам."
        return ToolResult(report.ok, body)


class RouteInboxTool(Tool):
    name = "route_inbox"
    description = (
        "Разобрать Inbox: blend, prop FBX, картинки. "
        "Анимации Mixamo — «accept_animation_inbox» (по одной)."
    )
    parameters = {
        "copy_to_unity": "1 = копировать анимации в Assets/…/Animations (по умолчанию 1)",
        "keep_inbox": "1 = копировать, не удалять из Inbox",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        copy = str(args.get("copy_to_unity", "1")).lower() not in ("0", "false", "no")
        keep = str(args.get("keep_inbox", "0")).lower() in ("1", "true", "yes")
        report = route_inbox(
            ctx.config,
            copy_to_unity=copy,
            remove_from_inbox=not keep,
        )
        return ToolResult(report.ok, report.format())
