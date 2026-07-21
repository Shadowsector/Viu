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
        "Каталог анимаций Шани + граф переходов (enters_from/exits_to). "
        "mode=graph|holes — только дыры с рёбрами; slug= — одна запись; "
        "missing_only=1 — без клипа."
    )
    parameters = {
        "category": "фильтр категории (locomotion, adventure, …) или пусто = всё",
        "missing_only": "1 = только без клипа",
        "slug": "одна запись по slug (climb_up, sit_idle, …)",
        "mode": "пусто | graph | holes — снимок графа / приоритет дыр",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        store = AnimationCatalogStore(animation_catalog_path(ctx.config)).load()
        mode = str(args.get("mode") or "").strip().lower()
        if mode in ("graph", "holes", "дыры", "граф"):
            return ToolResult(True, store.graph_brief(max_holes=16))

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
            wishes = [w for w in wishes if w.status == "wished" and not (w.ref_video or w.clip_file)]

        if not wishes:
            return ToolResult(True, store.summary_text() + "\n\n(пусто по фильтру)")

        lines = [store.summary_text(), ""]
        cur_cat = ""
        for w in wishes:
            if w.category != cur_cat:
                cur_cat = w.category
                label = ANIMATION_CATEGORIES.get(cur_cat, (cur_cat, ""))[0]
                lines.append(f"\n## {label} ({cur_cat})")
            status = "✓" if (w.status != "wished" or w.ref_video or w.clip_file) else "○"
            lines.append(f"{status} **{w.title_ru}** (`{w.slug}`, wave {w.wave})")
            if w.enters_from or w.exits_to:
                lines.append(
                    f"  Граф: {w.enters_from or '—'} → `{w.slug}` → {w.exits_to or '—'}"
                )
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


class AnimationOssBootstrapTool(Tool):
    name = "animation_oss_bootstrap"
    description = (
        "Скачать CC0-пакеты Mesh2Motion (GLB/Blend) в Animations/OSS/ "
        "и создать реестр .viu/oss_animations.json."
    )
    parameters: Dict[str, Any] = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..animation_catalog.oss_library import bootstrap_sources, ensure_registry

        ensure_registry(ctx.config)
        n, lines = bootstrap_sources(ctx.config)
        body = f"Bootstrap: {n} файл(ов).\n" + "\n".join(lines)
        return ToolResult(n > 0, body)


class AnimationOssStatusTool(Tool):
    name = "animation_oss_status"
    description = "Дыры каталога vs локальные OSS FBX (Mesh2Motion)."
    parameters: Dict[str, Any] = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..animation_catalog.oss_library import ensure_registry, status_text

        ensure_registry(ctx.config)
        return ToolResult(True, status_text(ctx.config))


class AnimationOssFetchTool(Tool):
    name = "animation_oss_fetch"
    description = (
        "OSS FBX → Inbox (имя как Mixamo). slug= или auto=1; accept=1 — сразу принять Inbox."
    )
    parameters = {
        "slug": "slug каталога (walk, sit_idle, …)",
        "auto": "1 = первая дыра с готовым OSS-файлом",
        "accept": "1 = после копирования вызвать accept_animation_inbox",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..animation_catalog.oss_library import ensure_registry, fetch_auto, fetch_to_inbox

        ensure_registry(ctx.config)
        accept = str(args.get("accept", "0")).lower() in ("1", "true", "yes")
        slug = str(args.get("slug") or "").strip()
        auto = str(args.get("auto", "0")).lower() in ("1", "true", "yes")
        if auto:
            ok, msg = fetch_auto(ctx.config, accept=accept)
            return ToolResult(ok, msg)
        if not slug:
            return ToolResult(
                False,
                "Укажи slug=walk или auto=1. Статус: animation_oss_status",
            )
        ok, msg = fetch_to_inbox(ctx.config, slug, accept=accept)
        return ToolResult(ok, msg)


class AnimationOssPrepareTool(Tool):
    name = "animation_oss_prepare"
    description = "Скопировать готовые OSS FBX в Animations/OSS/_export с именами Mixamo."
    parameters = {"wave": "макс. wave каталога (по умолчанию 1)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..animation_catalog.oss_library import ensure_registry, prepare_exports

        ensure_registry(ctx.config)
        try:
            wave = int(args.get("wave") or 1)
        except (TypeError, ValueError):
            wave = 1
        n, lines = prepare_exports(ctx.config, wave=max(1, wave))
        return ToolResult(n > 0, "\n".join(lines))


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
