"""Хранение interaction_catalog.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    DEFAULT_INTERACTIONS,
    STATUS_ASSEMBLED,
    STATUS_VERIFIED,
    STATUS_WISHED,
    InteractionWish,
)


class InteractionCatalogStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._items: Dict[str, InteractionWish] = {}

    def load(self) -> "InteractionCatalogStore":
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for raw in data.get("interactions") or []:
                    if isinstance(raw, dict):
                        w = InteractionWish.from_dict(raw)
                        self._items[w.id] = w
            except (json.JSONDecodeError, OSError, TypeError, KeyError):
                self._items = {}
        if not self._items:
            self.seed_defaults()
        else:
            self.merge_defaults()
        return self

    def seed_defaults(self) -> None:
        self._items = {
            w.id: InteractionWish.from_dict(w.to_dict()) for w in DEFAULT_INTERACTIONS
        }

    def merge_defaults(self) -> int:
        added = 0
        for w in DEFAULT_INTERACTIONS:
            if w.id not in self._items:
                self._items[w.id] = InteractionWish.from_dict(w.to_dict())
                added += 1
        return added

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        items = sorted(self._items.values(), key=lambda w: (w.wave, w.slug))
        payload = {
            "version": 1,
            "comment": "Совместные анимации — multi-actor; см. docs/INTERACTION_PIPELINE.md",
            "interactions": [w.to_dict() for w in items],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def all_wishes(self) -> List[InteractionWish]:
        return sorted(self._items.values(), key=lambda w: (w.wave, w.slug))

    def get(self, iid: str) -> Optional[InteractionWish]:
        return self._items.get(iid)

    def get_by_slug(self, slug: str) -> Optional[InteractionWish]:
        for w in self._items.values():
            if w.slug == slug:
                return w
        return None

    def missing(self) -> List[InteractionWish]:
        """Дыры: wished без master_ref и без assembly."""
        return [
            w
            for w in self.all_wishes()
            if w.status == STATUS_WISHED
            and not (w.master_ref or w.assembly_blend)
        ]

    def holes_for_wave(self, wave: int = 1) -> List[InteractionWish]:
        return [
            w
            for w in self.all_wishes()
            if w.wave == wave and w.status not in (STATUS_VERIFIED, STATUS_ASSEMBLED)
        ]

    def summary_text(self) -> str:
        total = len(self._items)
        done = sum(1 for w in self._items.values() if w.status in (STATUS_VERIFIED, STATUS_ASSEMBLED))
        holes = len(self.missing())
        return (
            f"Каталог совместных анимаций: {total} сцен, готово {done}, дыр {holes}. "
            f"Файл: {self.path}"
        )

    def graph_brief(self, max_holes: int = 8) -> str:
        lines = [self.summary_text(), ""]
        for w in self.all_wishes():
            if w.status in (STATUS_VERIFIED, STATUS_ASSEMBLED):
                continue
            flag = "○" if w.status == STATUS_WISHED else "…"
            lines.append(f"{flag} **{w.title_ru}** (`{w.slug}`, {w.status})")
            if w.enters_from or w.exits_to:
                lines.append(
                    f"  Граф: {w.enters_from or '—'} → `{w.slug}` → {w.exits_to or '—'}"
                )
            actors = ", ".join(f"{a.role}:{a.creature_slug}" for a in w.actors)
            if actors:
                lines.append(f"  Актёры: {actors}")
            if len([ln for ln in lines if ln.startswith("○") or ln.startswith("…")]) >= max_holes:
                break
        return "\n".join(lines)
