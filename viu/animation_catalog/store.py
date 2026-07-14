"""Хранение animation_catalog.json + очередь pending review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    DEFAULT_WISHES,
    STATUS_IMPORTED,
    STATUS_LINKED,
    STATUS_WISHED,
    AnimationImportReview,
    AnimationWish,
)


class AnimationCatalogStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._items: Dict[str, AnimationWish] = {}
        self._pending: Dict[str, AnimationImportReview] = {}

    def load(self) -> "AnimationCatalogStore":
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for raw in data.get("wishes") or []:
                    w = AnimationWish.from_dict(raw)
                    self._items[w.id] = w
                for raw in data.get("pending_reviews") or []:
                    p = AnimationImportReview.from_dict(raw)
                    self._pending[p.id] = p
            except (json.JSONDecodeError, OSError, TypeError, KeyError):
                self._items = {}
                self._pending = {}
        if not self._items:
            self.seed_defaults()
        else:
            self.merge_defaults()
        return self

    def seed_defaults(self) -> None:
        self._items = {w.id: w for w in DEFAULT_WISHES}

    def merge_defaults(self) -> int:
        """Добавить новые DEFAULT_WISHES, не затирая статусы/файлы существующих."""
        added = 0
        for w in DEFAULT_WISHES:
            if w.id not in self._items:
                self._items[w.id] = w
                added += 1
        return added

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        wishes = sorted(self._items.values(), key=lambda w: (w.wave, w.category, w.slug))
        pending = sorted(
            self._pending.values(),
            key=lambda p: (p.reviewed, p.original_name),
        )
        payload = {
            "version": 2,
            "comment": "Каталог анимаций — описания, scope, очередь review",
            "wishes": [w.to_dict() for w in wishes],
            "pending_reviews": [p.to_dict() for p in pending if not p.reviewed],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def all_wishes(self) -> List[AnimationWish]:
        return sorted(self._items.values(), key=lambda w: (w.wave, w.category, w.slug))

    def by_category(self, category: str) -> List[AnimationWish]:
        return [w for w in self.all_wishes() if w.category == category]

    def missing(self) -> List[AnimationWish]:
        return [w for w in self.all_wishes() if w.status == STATUS_WISHED]

    def pending_reviews(self) -> List[AnimationImportReview]:
        return [p for p in self._pending.values() if not p.reviewed]

    def get(self, wish_id: str) -> Optional[AnimationWish]:
        return self._items.get(wish_id)

    def get_by_slug(self, slug: str) -> Optional[AnimationWish]:
        from .models import wish_id

        return self._items.get(wish_id(slug))

    def get_pending(self, pending_id: str) -> Optional[AnimationImportReview]:
        return self._pending.get(pending_id)

    def upsert(self, wish: AnimationWish) -> None:
        self._items[wish.id] = wish

    def upsert_pending(self, review: AnimationImportReview) -> None:
        self._pending[review.id] = review

    def confirm_pending(self, review: AnimationImportReview) -> AnimationWish:
        """Сохранить review → обновить wish в каталоге."""
        review.reviewed = True
        self._pending[review.id] = review

        wish = self.get_by_slug(review.suggested_slug)
        if wish is None:
            wish = AnimationWish(
                slug=review.suggested_slug or review.original_name,
                category=review.category,
                title_ru=review.suggested_title or review.original_name,
                when_used=review.when_used,
                looks_like=review.looks_like,
                purpose=review.purpose,
                animator_state=review.animator_state,
                clip_file=Path(review.clip_file).name,
                scope=review.scope,
                reviewed=True,
                status=STATUS_IMPORTED,
                notes=review.notes,
            )
        else:
            if review.when_used.strip():
                wish.when_used = review.when_used
            if review.looks_like.strip():
                wish.looks_like = review.looks_like
            if review.purpose.strip():
                wish.purpose = review.purpose
            wish.clip_file = Path(review.clip_file).name
            wish.scope = review.scope
            wish.reviewed = True
            wish.status = STATUS_IMPORTED
            if review.notes.strip():
                wish.notes = review.notes
            if review.animator_state.strip():
                wish.animator_state = review.animator_state

        self._items[wish.id] = wish
        return wish

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
        pending = len(self.pending_reviews())
        lines = [
            f"Каталог анимаций: {total} записей.",
            f"Импортировано/связано: {imported}. Не хватает: {missing}.",
        ]
        if pending:
            lines.append(f"Ожидают описания: {pending} — «Принять анимацию» или «Очередь анимаций».")
        if missing:
            lines.append("\nПриоритет (wave 1, нет клипа):")
            for w in self.missing():
                if w.wave != 1:
                    continue
                lines.append(f"  • [{w.category}] {w.title_ru} — {w.slug}")
        return "\n".join(lines)
