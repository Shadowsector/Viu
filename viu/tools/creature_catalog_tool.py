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
from ..creature_catalog.auto_size import auto_apply_size_guesses
from ..creature_catalog.lineup import run_creature_lineup
from ..creature_catalog.models import ALL_SIZE_IDS, CONTACT_MODES, GENITAL_PROFILES, LOCOMOTION
from ..creature_catalog.studio import open_creature_studio, sync_studio_feedback
from ..creature_catalog.prep import open_creature_prep, sync_prep_feedback
from ..creature_catalog.wardrobe import open_creature_wardrobe, sync_wardrobe_feedback
from .base import AgentContext, Tool, ToolResult


class CreatureCatalogScanTool(Tool):
    name = "creature_catalog_scan"
    description = (
        "Сканировать Lab/Creatures/Inbox → creature_catalog.json. "
        "Потом авторазметка уверенных имён. Основной UX — кнопка «Разметить существ»."
    )
    parameters: dict = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        _a, _t, msg = scan_creatures_inbox(ctx.config)
        ensure_girl_sockets_doc(ctx.config)
        store = CreatureCatalogStore(creature_catalog_path(ctx.config)).load()
        auto_n, auto_lines = auto_apply_size_guesses(store)
        auto_block = ""
        if auto_n:
            auto_block = (
                f"\nАвто по имени: +{auto_n}\n" + "\n".join(auto_lines[:25])
            )
            if auto_n > 25:
                auto_block += f"\n  … +{auto_n - 25}"
        pending = len(store.pending())
        hint = (
            "\n\nДальше: в окне Вью слева кнопка «Разметить существ» "
            f"(кнопки размеров, без команд). Ещё ждут разметки: {pending}."
        )
        return ToolResult(
            True,
            msg + auto_block + hint + "\n\n" + list_size_classes_text(),
        )


class CreatureCatalogAutoSizeTool(Tool):
    name = "creature_catalog_auto_size"
    description = (
        "Автопроставить size_class там, где по имени файла ровно одна догадка "
        "(goblin→small, wolf→quad_med…). Остальное — GUI «Разметить существ»."
    )
    parameters: dict = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        store = CreatureCatalogStore(creature_catalog_path(ctx.config)).load()
        n, lines = auto_apply_size_guesses(store)
        pending = len(store.pending())
        if n == 0:
            return ToolResult(
                True,
                f"Авто: 0 (нет уверенных имён). Ждут GUI: {pending}.\n"
                "Открой «Разметить существ» в боковой панели.",
            )
        return ToolResult(
            True,
            f"Авто: +{n}. Ещё ждут: {pending}.\n" + "\n".join(lines[:40]),
        )


class CreatureCatalogShowTool(Tool):
    name = "creature_catalog_show"
    description = (
        "Показать каталог существ / классы роста / сокеты девушек. "
        "mode=summary|pending|classes|sockets|all|bipeds"
    )
    parameters = {"mode": "summary | pending | classes | sockets | all | bipeds"}

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
        if mode in ("bipeds", "biped"):
            from ..creature_catalog.biped_canon import build_queue_items, format_biped_list

            return ToolResult(True, format_biped_list(build_queue_items(store)))
        if mode == "all":
            lines = [e.render_line() + f"  id={e.id}" for e in store.all()]
            return ToolResult(
                True,
                store.summary_text() + "\n\n" + ("\n".join(lines) or "(пусто)"),
            )
        return ToolResult(True, store.summary_text() + f"\nСокеты: {sock_path}")


class CreatureBipedCanonTool(Tool):
    name = "creature_biped_canon"
    description = (
        "Пачка biped → канон Humanoid (AccuRIG). "
        "action=list|queue|ingest|mark_genital|guide. "
        "mark_genital — всем biped penis/futa + pending (спрятан scale~0). "
        "girls=1 — только vagina/futa / girl-имена. "
        "Простая инструкция: docs/BIPED_RERIG_SIMPLE.md или action=guide."
    )
    parameters = {
        "action": "list | queue | ingest | mark_genital | guide",
        "girls": "1 = только девки (genital/имя)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..creature_catalog.biped_canon import run_biped_canon_action

        action = str(args.get("action") or "list").strip()
        girls = str(args.get("girls") or "").lower() in ("1", "true", "yes", "devki")
        ok, msg = run_biped_canon_action(
            ctx.config, action=action, girls_only=girls
        )
        return ToolResult(ok, msg)


class CreatureCatalogSetSizeTool(Tool):
    name = "creature_catalog_set_size"
    description = (
        "Проставить size_class существу. id= или slug=; size=mini|small|humanoid|large|huge|"
        "quad_mini|quad_med|quad_large; size_alt= через запятую (dual); "
        "locomotion=biped|quadruped|amorph|tentacle|mimic|flyer; "
        "genital=none|penis|vagina|futa; contact=oral,tentacle,hand (через запятую)."
    )
    parameters = {
        "id": "id записи",
        "slug": "slug если нет id",
        "size": "size_class",
        "size_alt": "доп. классы через запятую",
        "locomotion": "locomotion",
        "genital": "genital_profile: none|penis|vagina|futa",
        "contact": "contact_modes: oral,tentacle,hand",
        "notes": "заметка",
        "height": "точный рост в метрах (иначе из класса)",
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

        target_m = None
        h_raw = str(args.get("height") or args.get("target_m") or "").strip().replace(",", ".")
        if h_raw:
            try:
                target_m = float(h_raw)
            except ValueError:
                return ToolResult(False, "height= число в метрах, например 0.7")

        updated = store.set_size(
            entry.id,
            size,
            size_alt=size_alt or None,
            locomotion=loco,
            notes=str(args.get("notes") or ""),
            target_m=target_m,
        )
        if updated is None:
            return ToolResult(False, "Не удалось обновить")
        genital = str(args.get("genital") or args.get("genital_profile") or "").strip()
        contact_raw = str(args.get("contact") or args.get("contact_modes") or "").strip()
        if genital:
            if genital not in GENITAL_PROFILES:
                return ToolResult(
                    False,
                    f"genital= один из: {', '.join(GENITAL_PROFILES)}",
                )
        modes: List[str] = []
        if contact_raw:
            modes = [p.strip() for p in contact_raw.split(",") if p.strip()]
            bad = [m for m in modes if m not in CONTACT_MODES]
            if bad:
                return ToolResult(
                    False,
                    f"contact= oral,tentacle,hand — неизвестно: {', '.join(bad)}",
                )
        if genital or contact_raw:
            updated.set_anatomy(
                genital_profile=genital or updated.genital_profile,
                contact_modes=modes if contact_raw else None,
            )
        store.upsert(updated)
        store.save()
        return ToolResult(
            True,
            f"OK: {updated.render_line()}\n"
            f"anim_bucket=`{updated.anim_bucket()}`\n"
            f"анатомия: {updated.anatomy_summary()}\n"
            "Дальше: подготовка → студия существ.",
        )


class CreatureDescribeTool(Tool):
    name = "creature_describe"
    description = (
        "Описать существо по скрину (Ollama VL / llava): EN-промпт + RU для анимации. "
        "Пишет appearance_* в creature_catalog.json. "
        "query=имя/slug/id; image=путь к PNG (иначе photo_front или Processed/<slug>/front.png)."
    )
    parameters = {
        "query": "имя, slug или id существа",
        "image": "опционально путь к PNG скрина",
        "mark_ready": "1 (по умолчанию) → status=ready если есть size_class",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..creature_catalog.describe import describe_creature

        query = str(args.get("query") or args.get("name") or "").strip()
        if not query:
            return ToolResult(False, "Нужен query= имя/slug существа.")
        image = str(args.get("image") or args.get("path") or "").strip()
        mark = str(args.get("mark_ready") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        ok, msg = describe_creature(
            ctx.config, query, image=image, mark_ready=mark
        )
        return ToolResult(ok, msg)


class CreatureLineupTool(Tool):
    name = "creature_lineup"
    description = (
        "Линейка существ: Вью сама запускает Blender, собирает .blend рядом с Шаней, "
        "front/side PNG в Processed/. По умолчанию только без одобренных скринов. "
        "slug= один или несколько; need_photos=0 — весь каталог; open=0 не открывать."
    )
    parameters = {
        "size": "фильтр size_class через запятую (пусто = все размеченные)",
        "slug": "slug или имя (через запятую) — только эти существа",
        "need_photos": "1 только ждут съёмки/проверки (по умолчанию), 0 весь каталог",
        "shanya_path": "путь к модели Шани",
        "spacing": "метры между фигурами (1.2)",
        "open": "1 открыть .blend/папку (по умолчанию), 0 — нет",
        "split": "1 всегда по классам, 0 одна сцена, пусто — авто если много",
        "all": "1 все файлы без дедупа fbx+blend",
        "prepare_only": "1 только подготовить job, не запускать Blender",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        sizes = [p.strip() for p in str(args.get("size") or "").split(",") if p.strip()]
        slug_filter = [
            p.strip()
            for p in str(args.get("slug") or args.get("slugs") or "").split(",")
            if p.strip()
        ]
        need_raw = str(args.get("need_photos") or "1").strip().lower()
        need_photos_only = need_raw not in ("0", "false", "no", "all")
        try:
            spacing = float(args.get("spacing") or 1.2)
        except (TypeError, ValueError):
            spacing = 1.2

        if str(args.get("prepare_only") or "").strip() in ("1", "true", "yes"):
            ok, msg, path = build_lineup_job(
                ctx.config,
                size_filter=sizes,
                slug_filter=slug_filter,
                need_photos_only=need_photos_only,
                shanya_path=str(args.get("shanya_path") or "").strip(),
                spacing_m=spacing,
            )
            return ToolResult(ok, msg if path else msg)

        split_raw = str(args.get("split") or "").strip().lower()
        split: bool | None
        if split_raw in ("1", "true", "yes"):
            split = True
        elif split_raw in ("0", "false", "no"):
            split = False
        else:
            split = None

        open_result = str(args.get("open") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        all_files = str(args.get("all") or "").strip().lower() in ("1", "true", "yes")

        ok, msg = run_creature_lineup(
            ctx.config,
            size_filter=sizes,
            slug_filter=slug_filter,
            need_photos_only=need_photos_only,
            shanya_path=str(args.get("shanya_path") or "").strip(),
            spacing_m=spacing,
            split=split,
            all_files=all_files,
            open_result=open_result,
        )
        return ToolResult(ok, msg)


class CreatureWardrobeOpenTool(Tool):
    name = "creature_wardrobe_open"
    description = "Blender Wardrobe: наборы одежды, genital visibility. Нужен prepared.blend."
    parameters = {"slug": "один slug/имя"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        slug_filter = [p.strip() for p in str(args.get("slug") or "").split(",") if p.strip()]
        ok, msg = open_creature_wardrobe(ctx.config, slug_filter=slug_filter)
        return ToolResult(ok, msg)


class CreatureWardrobeSyncTool(Tool):
    name = "creature_wardrobe_sync"
    description = "Считать wardrobe_feedback → outfit_sets.json, genital_rig в каталог."

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        n, msg = sync_wardrobe_feedback(ctx.config)
        return ToolResult(n > 0, msg)


class CreaturePrepOpenTool(Tool):
    name = "creature_prep_open"
    description = (
        "Blender — подготовка моделей (шаг 1): очистка, Bursting Head, текстуры, prepared.blend."
    )
    parameters = {
        "slug": "один slug/имя",
        "all": "1 все из Inbox, 0 только без prepared (по умолчанию)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        slug_filter = [p.strip() for p in str(args.get("slug") or "").split(",") if p.strip()]
        only_unprepared = str(args.get("all") or "").strip().lower() not in ("1", "true", "yes", "all")
        ok, msg = open_creature_prep(ctx.config, slug_filter=slug_filter, only_unprepared=only_unprepared)
        return ToolResult(ok, msg)


class CreaturePrepSyncTool(Tool):
    name = "creature_prep_sync"
    description = "Считать prep_feedback.json → prepared_path, prep_ok в каталог."

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        n, msg = sync_prep_feedback(ctx.config)
        return ToolResult(n > 0, msg)


class CreatureStudioOpenTool(Tool):
    name = "creature_studio_open"
    description = (
        "Blender-студия (шаг 2): разметка + Шаня + рост + скрины + эталон FBX. "
        "Нужен prepared.blend. slug= один; all=1 вся очередь."
    )
    parameters = {
        "slug": "один slug/имя (пусто = очередь без photo_ok)",
        "all": "1 все размеченные, 0 только без одобренных скринов (по умолчанию)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        slug_filter = [
            p.strip()
            for p in str(args.get("slug") or "").split(",")
            if p.strip()
        ]
        only_unapproved = str(args.get("all") or "").strip().lower() not in (
            "1",
            "true",
            "yes",
            "all",
        )
        ok, msg = open_creature_studio(
            ctx.config,
            slug_filter=slug_filter,
            only_unapproved=only_unapproved,
        )
        return ToolResult(ok, msg)


class CreatureStudioSyncTool(Tool):
    name = "creature_studio_sync"
    description = (
        "Считать studio_feedback.json → разметка, рост, скрины, photo_ok, эталон FBX."
    )
    parameters: dict = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        n, msg = sync_studio_feedback(ctx.config)
        return ToolResult(n > 0, msg)


class CreaturePipelineNotesTool(Tool):
    name = "creature_pipeline_notes"
    description = "Показать заметки [prep]/[wardrobe]/[studio] из creature_catalog.json."

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        store = CreatureCatalogStore(creature_catalog_path(ctx.config)).load()
        text = store.pipeline_notes_text()
        return ToolResult(True, text)


class CreatureCatalogMergeTool(Tool):
    name = "creature_catalog_merge"
    description = "Слить дубли каталога с одним slug (Dennis дважды и т.п.)."

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        store = CreatureCatalogStore(creature_catalog_path(ctx.config)).load()
        removed, merged = store.merge_duplicate_slugs()
        if removed:
            store.save()
        return ToolResult(
            True,
            f"Каталог: удалено дублей {removed}, объединено заметок {merged}.",
        )


__all__ = [
    "CreatureCatalogScanTool",
    "CreatureCatalogShowTool",
    "CreatureBipedCanonTool",
    "CreatureCatalogSetSizeTool",
    "CreatureCatalogAutoSizeTool",
    "CreatureDescribeTool",
    "CreatureLineupTool",
    "CreatureWardrobeOpenTool",
    "CreatureWardrobeSyncTool",
    "CreaturePrepOpenTool",
    "CreaturePrepSyncTool",
    "CreatureStudioOpenTool",
    "CreatureStudioSyncTool",
    "CreaturePipelineNotesTool",
    "CreatureCatalogMergeTool",
]
