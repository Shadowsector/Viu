"""Инструменты каталога совместных анимаций."""

from __future__ import annotations

from typing import Any, Dict

from ..interaction_catalog import (
    InteractionCatalogStore,
    interaction_catalog_path,
)
from .base import AgentContext, Tool, ToolResult


class InteractionCatalogShowTool(Tool):
    name = "interaction_catalog_show"
    description = (
        "Каталог совместных анимаций (multi-actor). "
        "mode=holes|graph — дыры; slug= — одна сцена. "
        "См. docs/INTERACTION_PIPELINE.md"
    )
    parameters = {
        "slug": "одна сцена по slug (shanya_wolf_approach, …)",
        "mode": "пусто | holes | graph",
        "wave": "фильтр wave (1, 2, …)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        store = InteractionCatalogStore(interaction_catalog_path(ctx.config)).load()
        mode = str(args.get("mode") or "").strip().lower()
        if mode in ("holes", "graph", "дыры", "граф"):
            return ToolResult(True, store.graph_brief(max_holes=16))

        slug = str(args.get("slug", "")).strip()
        if slug:
            w = store.get_by_slug(slug)
            if not w:
                return ToolResult(False, f"Нет сцены slug={slug}")
            return ToolResult(True, w.render_block())

        wave_raw = str(args.get("wave") or "").strip()
        wishes = store.all_wishes()
        if wave_raw.isdigit():
            wave = int(wave_raw)
            wishes = [w for w in wishes if w.wave == wave]

        if not wishes:
            return ToolResult(True, store.summary_text() + "\n\n(пусто по фильтру)")

        lines = [store.summary_text(), ""]
        for w in wishes:
            flag = "✓" if w.status in ("verified", "assembled", "linked") else "○"
            lines.append(f"{flag} **{w.title_ru}** (`{w.slug}`, {w.status})")
            if w.enters_from or w.exits_to:
                lines.append(
                    f"  Граф: {w.enters_from or '—'} → `{w.slug}` → {w.exits_to or '—'}"
                )
            actors = ", ".join(f"{a.role}:{a.creature_slug}" for a in w.actors)
            if actors:
                lines.append(f"  Актёры: {actors}")
        return ToolResult(True, "\n".join(lines))
