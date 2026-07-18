"""Хранение creature_catalog.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    STATUS_NEW,
    STATUS_SIZED,
    CreatureEntry,
    size_spec,
)


class CreatureCatalogStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._items: Dict[str, CreatureEntry] = {}

    def load(self) -> "CreatureCatalogStore":
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for raw in data.get("creatures") or []:
                    if isinstance(raw, dict):
                        e = CreatureEntry.from_dict(raw)
                        self._items[e.id] = e
            except (json.JSONDecodeError, OSError, TypeError):
                self._items = {}
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        items = sorted(self._items.values(), key=lambda e: (e.status, e.name.lower()))
        payload = {
            "version": 1,
            "comment": "Существа: size_class × locomotion → набор анимаций; рост варьируется в классе",
            "creatures": [e.to_dict() for e in items],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def all(self) -> List[CreatureEntry]:
        return list(self._items.values())

    def pending(self) -> List[CreatureEntry]:
        return [e for e in self._items.values() if not e.reviewed and e.status == STATUS_NEW]

    def by_status(self, status: str) -> List[CreatureEntry]:
        return [e for e in self._items.values() if e.status == status]

    def get(self, cid: str) -> Optional[CreatureEntry]:
        return self._items.get(cid)

    def get_by_slug(self, slug: str) -> Optional[CreatureEntry]:
        for e in self._items.values():
            if e.slug == slug:
                return e
        return None

    def upsert(self, entry: CreatureEntry) -> None:
        self._items[entry.id] = entry

    def set_size(
        self,
        cid: str,
        size_class: str,
        *,
        size_alt: Optional[List[str]] = None,
        locomotion: str = "",
        notes: str = "",
        target_m: Optional[float] = None,
    ) -> Optional[CreatureEntry]:
        e = self._items.get(cid)
        if e is None:
            return None
        spec = size_spec(size_class)
        if not spec:
            return None
        e.size_class = size_class
        if target_m is not None and float(target_m) > 0:
            e.target_height_m = float(target_m)
        else:
            e.target_height_m = float(spec["target_m"])
        if size_alt is not None:
            e.size_alt = list(size_alt)
        if locomotion:
            e.locomotion = locomotion
        if notes:
            e.notes = ((e.notes or "") + "\n" + notes).strip()
        e.status = STATUS_SIZED
        e.reviewed = True
        # сброс старого замера — линейка перемерит
        e.measured_height_m = 0.0
        e.scale_applied = 1.0
        e.photo_ok = False
        e.photo_notes = ""
        self._items[e.id] = e
        return e

    def mark_photo_ok(self, cid: str, *, ok: bool, notes: str = "") -> Optional[CreatureEntry]:
        e = self._items.get(cid)
        if e is None:
            return None
        e.photo_ok = bool(ok)
        if notes:
            e.photo_notes = notes.strip()
        elif ok:
            e.photo_notes = ""
        self._items[e.id] = e
        return e

    def needs_photos(self) -> List[CreatureEntry]:
        return [e for e in self.sized() if e.needs_photo_lineup()]

    def needs_photo_review(self) -> List[CreatureEntry]:
        return [e for e in self.sized() if e.needs_photo_review()]

    def sized(self) -> List[CreatureEntry]:
        return [e for e in self._items.values() if e.size_class and e.status != "skip"]

    def mark_skip(self, cid: str, reason: str = "") -> Optional[CreatureEntry]:
        from .models import STATUS_SKIP

        e = self._items.get(cid)
        if e is None:
            return None
        e.status = STATUS_SKIP
        e.reviewed = True
        if reason:
            e.notes = ((e.notes or "") + "\n" + reason).strip()
        self._items[e.id] = e
        return e

    def summary_text(self) -> str:
        total = len(self._items)
        pending = len(self.pending())
        sized = sum(1 for e in self._items.values() if e.size_class)
        need_photos = len(self.needs_photos())
        need_review = len(self.needs_photo_review())
        photo_ok = sum(1 for e in self._items.values() if e.photo_ok)
        lines = [
            f"Каталог существ: {total} шт., размечено size: {sized}, ждут разметки: {pending}.",
            f"Скрины: ок {photo_ok}, ждут съёмки {need_photos}, ждут проверки {need_review}.",
        ]
        by_bucket: Dict[str, int] = {}
        for e in self._items.values():
            if e.size_class:
                by_bucket[e.anim_bucket()] = by_bucket.get(e.anim_bucket(), 0) + 1
        if by_bucket:
            lines.append("Наборы анимаций (size×loco):")
            for k, n in sorted(by_bucket.items()):
                lines.append(f"  • {k}: {n}")
        if pending:
            lines.append("\nЖдут size_class:")
            for e in self.pending()[:15]:
                lines.append(f"  • {e.id[:8]}… {e.render_line()}")
            if pending > 15:
                lines.append(f"  … +{pending - 15}")
        return "\n".join(lines)
