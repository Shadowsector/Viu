"""Инструменты: архив Desktop Mascot + provenance (без bulk-скана)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..asset_archive.inventory import (
    describe_archive_brief,
    inventory_archive_top,
    inventory_pack,
    stage_pack_to_inbox,
)
from ..asset_archive.provenance import ProvenanceEntry, license_ok_for_anabarra_build
from ..asset_archive.store import ProvenanceStore, provenance_path
from ..machine_bind import require_personal_machine
from .base import AgentContext, Tool, ToolResult


def _gate_personal(ctx: AgentContext, args: Dict[str, Any]) -> ToolResult | None:
    """Личный гейт. force=1 — только осознанный обход (тесты/отладка)."""
    if str(args.get("force") or "").strip() in ("1", "true", "yes"):
        return None
    ok, msg = require_personal_machine(ctx.config, auto_ensure=True)
    if ok:
        return None
    return ToolResult(
        ok=False,
        content=(
            f"Личная привязка машины не совпала: {msg}\n"
            "После смены железа/путей: python -m viu machine rebind\n"
            "или tool machine_bind action=rebind"
        ),
    )


class AssetArchiveInventoryTool(Tool):
    name = "asset_archive_inventory"
    description = (
        "Показать верхний уровень U:\\Desktop Mascot (категории Women/Clothes/…). "
        "Без рекурсивного скана. pack_dir=… — инвентарь одного пака."
    )
    parameters = {
        "pack_dir": "опционально: путь к одному паку для рекурсивного учёта",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        blocked = _gate_personal(ctx, args)
        if blocked:
            return blocked
        pack = str(args.get("pack_dir") or "").strip()
        if pack:
            inv = inventory_pack(Path(pack))
            return ToolResult(
                ok=bool(inv.get("exists")),
                content=json.dumps(inv, ensure_ascii=False, indent=2),
            )
        inv = inventory_archive_top(ctx.config)
        text = describe_archive_brief(ctx.config) + "\n\n" + json.dumps(
            inv, ensure_ascii=False, indent=2
        )
        return ToolResult(ok=True, content=text)


class AssetArchiveStageTool(Tool):
    name = "asset_archive_stage"
    description = (
        "Скопировать один пак/файл из Desktop Mascot в Inbox "
        "(category=Women|Animations|Props|…)."
    )
    parameters = {
        "source": "путь к паку или файлу в архиве",
        "category": "Women|Animations|Clothes|Props|…",
        "dest_name": "опционально: имя в Inbox",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        blocked = _gate_personal(ctx, args)
        if blocked:
            return blocked
        source = str(args.get("source") or args.get("path") or "").strip()
        if not source:
            return ToolResult(ok=False, content="нужен source= путь к паку")
        category = str(args.get("category") or "Women").strip()
        dest_name = str(args.get("dest_name") or "").strip()
        ok, msg, dest = stage_pack_to_inbox(
            ctx.config, Path(source), category=category, dest_name=dest_name
        )
        return ToolResult(ok=ok, content=msg if not ok else f"{msg}\n{dest}")


class AssetProvenanceTool(Tool):
    name = "asset_provenance"
    description = (
        "Каталог provenance: action=show|ensure_pilots|add. "
        "Для add: id, title, source, license, url, author, mascot_category."
    )
    parameters = {
        "action": "show | ensure_pilots | add",
        "id": "для add",
        "title": "для add",
        "source": "smutbase|mine|patreon|other",
        "license": "CC0 / CC BY / CC BY-ND / mine",
        "url": "ссылка на страницу ассета",
        "author": "автор",
        "mascot_category": "Women|Animations|…",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        action = str(args.get("action") or "show").strip().lower()
        if action in ("ensure_pilots", "seed", "init", "add"):
            blocked = _gate_personal(ctx, args)
            if blocked:
                return blocked
        store = ProvenanceStore(provenance_path(ctx.config))
        if action in ("ensure_pilots", "seed", "init"):
            n = store.ensure_pilots()
            return ToolResult(
                ok=True,
                content=f"пилотов добавлено: {n}\n{store.render_summary()}",
            )
        if action == "add":
            entry_id = str(args.get("id") or "").strip()
            title = str(args.get("title") or entry_id).strip()
            license_text = str(args.get("license") or "").strip()
            if not entry_id:
                return ToolResult(ok=False, content="нужен id=")
            ok_lic, lic_msg = license_ok_for_anabarra_build(license_text or "mine")
            entry = ProvenanceEntry(
                id=entry_id,
                title=title or entry_id,
                source=str(args.get("source") or "other"),
                author=str(args.get("author") or ""),
                license=license_text,
                url=str(args.get("url") or ""),
                local_path=str(args.get("local_path") or ""),
                mascot_category=str(args.get("mascot_category") or ""),
                notes=str(args.get("notes") or lic_msg),
            )
            store.upsert(entry)
            flag = "ok" if ok_lic else "внимание"
            return ToolResult(
                ok=True,
                content=f"сохранено [{flag}]: {entry.id} — {lic_msg}\n{store.render_summary()}",
            )
        store.ensure_pilots()
        return ToolResult(ok=True, content=store.render_summary())
