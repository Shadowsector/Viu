"""Хранение animation_catalog.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .models import DEFAULT_WISHES, STATUS_IMPORTED, STATUS_LINKED, STATUS_WISHED, AnimationWish


class AnimationCatalogStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._items: Dict[str, AnimationWish] = {}

    def load(self) -> "AnimationCatalogStore":
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for raw in data.get("wishes") or []:
                    w = AnimationWish.from_dict(raw)
                    self._items[w.id] = w
            except (json.JSONDecodeError, OSError, TypeError, KeyError):
                self._items = {}
        if not self._items:
            self.seed_defaults()
        return self

    def seed_defaults(self) -> None:
        self._items = {w.id: w for w in DEFAULT_WISHES}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        wishes = sorted(self._items.values(), key=lambda w: (w.wave, w.category, w.slug))
        payload = {
            "version": 1,
            "comment": "Каталог анимаций Шани — описания для Viu и матчинг FBX",
            "wishes": [w.to_dict() for w in wishes],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def all_wishes(self) -> List[AnimationWish]:
        return sorted(self._items.values(), key=lambda w: (w.wave, w.category, w.slug))

    def by_category(self, category: str) -> List[AnimationWish]:
        return [w for w in self.all_wishes() if w.category == category]

    def missing(self) -> List[AnimationWish]:
        return [w for w in self.all_wishes() if w.status == STATUS_WISHED]

    def get(self, wish_id: str) -> Optional[AnimationWish]:
        return self._items.get(wish_id)

    def get_by_slug(self, slug: str) -> Optional[AnimationWish]:
        from .models import wish_id

        return self._items.get(wish_id(slug))

    def upsert(self, wish: AnimationWish) -> None:
        self._items[wish.id] = wish

    def mark_imported(self, slug: str, clip_file: str, *, linked: bool = False) -> Optional[AnimationWish]:
        w = self.get_by_slug(slug)
        if w is None:
            return None
        w.clip_file = clip_file
        w.status = STATUS_LINKED if linked else STATUS_IMPORTED
        self._items[w.id] = w
        return w

    def summary_text(self) -> str:
        total = len(self._items)
        missing = len(self.missing())
        imported = sum(1 for w in self._items.values() if w.status != STATUS_WISHED)
        lines = [
            f"Каталог анимаций: {total} записей.",
            f"Импортировано/связано: {imported}. Не хватает: {missing}.",
        ]
        if missing:
            lines.append("\nПриоритет (wave 1, нет клипа):")
            for w in self.missing():
                if w.wave != 1:
                    continue
                lines.append(f"  • [{w.category}] {w.title_ru} — {w.slug}")
        return "\n".join(lines)
