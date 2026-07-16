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
        # Копии, иначе мутация store затирает DEFAULT_WISHES.
        self._items = {
            w.id: AnimationWish.from_dict(w.to_dict()) for w in DEFAULT_WISHES
        }

    def merge_defaults(self) -> int:
        """Добавить новые DEFAULT_WISHES; дописать пустой граф переходов с defaults."""
        added = 0
        for w in DEFAULT_WISHES:
            if w.id not in self._items:
                self._items[w.id] = AnimationWish.from_dict(w.to_dict())
                added += 1
                continue
            cur = self._items[w.id]
            # Не затираем кастомный граф — только если поля пустые.
            if not cur.enters_from and w.enters_from:
                cur.enters_from = list(w.enters_from)
            if not cur.exits_to and w.exits_to:
                cur.exits_to = list(w.exits_to)
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
        """Дыры для съёмки: wished и ещё без ref_video (Comfy keep закрывает дыру)."""
        return [
            w
            for w in self.all_wishes()
            if w.status == STATUS_WISHED and not (w.ref_video or w.clip_file)
        ]

    @staticmethod
    def is_filled(wish: AnimationWish) -> bool:
        """Дыра закрыта: есть ref_video / clip_file или статус уже не wished."""
        if wish.ref_video or wish.clip_file:
            return True
        return wish.status != STATUS_WISHED

    def sources_ready(self, wish: AnimationWish) -> bool:
        """Можно снимать приоритетно: нет enters_from или хотя бы один источник заполнен."""
        if not wish.enters_from:
            return True
        for src in wish.enters_from:
            sw = self.get_by_slug(src)
            if sw is None:
                continue
            if self.is_filled(sw):
                return True
        return False

    def blocking_sources(self, wish: AnimationWish) -> List[str]:
        """Slug'и enters_from, которые ещё дыры (для подсказки Вью)."""
        if not wish.enters_from:
            return []
        out: List[str] = []
        for src in wish.enters_from:
            sw = self.get_by_slug(src)
            if sw is not None and not self.is_filled(sw):
                out.append(src)
        return out

    def ordered_holes(self) -> List[AnimationWish]:
        """Приоритет съёмки: готовые enters_from → wave≤1 → transition → rest → loco.

        Среди transition сначала входы из idle (sit_down/lie_down), потом выходы.
        """
        holes = self.missing()
        if not holes:
            return []
        ready = [w for w in holes if self.sources_ready(w)]
        pool = ready or holes
        wave1 = [w for w in pool if w.wave <= 1]
        base = wave1 or pool
        non_idle = [w for w in base if w.slug != "idle"]
        pool2 = non_idle or base

        def _entry_key(w: AnimationWish) -> tuple:
            # 0 = из idle / без входа; 1 = остальные
            from_idle = (not w.enters_from) or ("idle" in w.enters_from)
            return (0 if from_idle else 1, w.slug)

        transitions = sorted(
            [w for w in pool2 if w.category == "transition"], key=_entry_key
        )
        rest = sorted([w for w in pool2 if w.category == "rest"], key=_entry_key)
        loco = sorted([w for w in pool2 if w.category == "locomotion"], key=_entry_key)
        other = sorted(
            [w for w in pool2 if w.category not in ("transition", "rest", "locomotion")],
            key=_entry_key,
        )
        return transitions or rest or loco or other or pool2

    def graph_brief(self, *, max_holes: int = 8) -> str:
        """Короткий снимок графа для reflect / heartbeat / tool."""
        missing = self.missing()
        ordered = self.ordered_holes()
        with_edges = sum(1 for w in self.all_wishes() if w.enters_from or w.exits_to)
        lines = [
            "Граф анимаций (модульные клипы + переходы, не «одна большая»):",
            f"Записей: {len(self._items)}, с рёбрами enters_from/exits_to: {with_edges}, "
            f"дыр без клипа/ref: {len(missing)}.",
            "Цепочки: idle→sit_down→sit_idle→stand_up→idle; "
            "idle→lie_down→sleep_idle→get_up→idle; idle↔walk↔run.",
        ]
        if not ordered:
            lines.append("Дыр нет — можно вариации / NSFW / wave 2+.")
            return "\n".join(lines)

        lines.append("Следующие дыры (приоритет съёмки Comfy):")
        for w in ordered[:max_holes]:
            edge = f"{w.enters_from or '—'} → `{w.slug}` → {w.exits_to or '—'}"
            if self.sources_ready(w):
                mark = "готово снимать"
            else:
                blocked = self.blocking_sources(w)
                mark = f"сначала закрой: {', '.join(blocked)}" if blocked else "ждёт вход"
            lines.append(
                f"  • [{w.category}/w{w.wave}] {w.title_ru} — {edge} ({mark})"
            )
        if len(ordered) > max_holes:
            lines.append(f"  … ещё {len(ordered) - max_holes}")
        lines.append(
            "В чате предлагай закрывать цепочки; comfy_mocap action=auto берёт верхнюю дыру."
        )
        return "\n".join(lines)

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
        lines.append("")
        lines.append(self.graph_brief(max_holes=6))
        return "\n".join(lines)
