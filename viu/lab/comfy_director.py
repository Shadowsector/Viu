"""Режиссёр Comfy MoCap: Вью сама выбирает, что снять.

Не хардкодим idle stand — смотрим каталог анимаций, граф переходов,
недавно снятое, и собираем filmable action на английском для Wan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from ..animation_catalog import AnimationCatalogStore, animation_catalog_path
from ..animation_catalog.models import AnimationWish, STATUS_WISHED
from ..config import Config
from ..integrations.comfy.clip_review import ComfyClipStore, STATUS_KEPT, clip_review_path

# Английские шаблоны по slug — Wan лучше ест EN.
_SLUG_ACTION_EN = {
    "idle": (
        "idle stand, subtle breathing, soft weight shift, "
        "small head turn, slight finger micro-movements, natural idle loop"
    ),
    "walk": "walking forward at a calm pace, natural arm swing, full body gait cycle",
    "run": "running forward, athletic stride, arms pumping, full body visible",
    "sit_down": "sitting down from standing onto an invisible seat, controlled motion",
    "sit_idle": "seated idle on invisible chair, subtle breathing, small posture shifts",
    "stand_up": "standing up from a seated pose to full standing, smooth rise",
    "lie_down": "lying down onto the back from standing or sitting, onto invisible floor",
    "sleep_idle": (
        "lying on the back asleep, subtle breathing, small restless shifts, "
        "gentle head movement, sleep-idle loop"
    ),
    "get_up": "getting up from lying on the back to standing, push with arms",
    "wave": "standing wave hello with one hand, friendly gesture, feet planted",
    "climb_up": "climbing upward, reaching hands and stepping feet, vertical effort",
    "jump": "standing jump up and land, knees bend, arms assist",
    "fall": "falling backward or sideways from stand, loss of balance",
    "pickup": "bending to pick up a small object from the floor, then stand again",
    "lean": "leaning against invisible wall, one shoulder/hip contact, relaxed",
}


@dataclass
class MocapShotPlan:
    action: str
    catalog_slug: str
    reason: str
    enters_from: List[str] = field(default_factory=list)
    exits_to: List[str] = field(default_factory=list)
    title_ru: str = ""

    def summary_ru(self) -> str:
        return (
            f"Снимаю «{self.title_ru or self.catalog_slug}»: {self.action}\n"
            f"Почему: {self.reason}"
        )


def _recent_slugs(config: Config, *, limit: int = 12) -> Set[str]:
    store = ComfyClipStore(clip_review_path(config)).load()
    kept = [c for c in store.clips if c.status == STATUS_KEPT]
    kept.sort(key=lambda c: c.kept_at or c.created_at, reverse=True)
    out: Set[str] = set()
    for c in kept[:limit]:
        if c.catalog_slug:
            out.add(c.catalog_slug)
        # также slug из action
        s = re.sub(r"[^a-z0-9_\-]+", "_", (c.action or "").lower())[:40]
        if s:
            out.add(s.strip("_"))
    return out


def _wish_to_action(wish: AnimationWish) -> str:
    if wish.slug in _SLUG_ACTION_EN:
        return _SLUG_ACTION_EN[wish.slug]
    # fallback: slug + краткий EN из looks_like если латиница, иначе slug words
    words = wish.slug.replace("_", " ")
    hint = (wish.looks_like or "").strip()
    if hint and re.search(r"[A-Za-z]{3,}", hint):
        return f"{words}, {hint}"
    return f"{words}, full body character motion, clear limbs, loopable short clip"


def invent_next_shot(config: Config) -> MocapShotPlan:
    """Выбрать следующий клип для съёмки. Без LLM — по каталогу и графу."""
    cat = AnimationCatalogStore(animation_catalog_path(config)).load()
    recent = _recent_slugs(config)
    missing = [w for w in cat.missing() if w.slug not in recent]

    # 1) волна 1 без недавних повторов
    wave1 = [w for w in missing if w.wave <= 1]
    # не залипать на idle, если есть другие дыры
    non_idle = [w for w in wave1 if w.slug != "idle"]
    pool = non_idle or wave1 or missing

    # 2) приоритет transition, у которых enters_from уже «закрыты» (есть ref или imported)
    def _ready_sources(w: AnimationWish) -> bool:
        if not w.enters_from:
            return True
        for src in w.enters_from:
            sw = cat.get_by_slug(src)
            if sw is None:
                continue
            if sw.status != STATUS_WISHED or sw.ref_video or sw.clip_file:
                return True
        return False

    transitions = [w for w in pool if w.category == "transition" and _ready_sources(w)]
    rest = [w for w in pool if w.category == "rest"]
    loco = [w for w in pool if w.category == "locomotion"]
    ordered = transitions or rest or loco or pool

    if ordered:
        wish = ordered[0]
        action = _wish_to_action(wish)
        reason = (
            f"в каталоге нет клипа `{wish.slug}` (wave {wish.wave}, {wish.category}); "
            f"когда: {wish.when_used[:80]}"
        )
        return MocapShotPlan(
            action=action,
            catalog_slug=wish.slug,
            reason=reason,
            enters_from=list(wish.enters_from),
            exits_to=list(wish.exits_to),
            title_ru=wish.title_ru,
        )

    # 3) всё закрыто — вариация поверх имеющихся (не тот же idle)
    all_w = [w for w in cat.all_wishes() if w.slug not in recent]
    if not all_w:
        all_w = cat.all_wishes()
    pick = next((w for w in all_w if w.slug != "idle"), all_w[0] if all_w else None)
    if pick is None:
        return MocapShotPlan(
            action=_SLUG_ACTION_EN["wave"],
            catalog_slug="wave",
            reason="каталог пуст — сниму жест приветствия как разведку",
            title_ru="Машет рукой",
        )
    return MocapShotPlan(
        action=_wish_to_action(pick) + ", alternate take, slightly different timing",
        catalog_slug=pick.slug,
        reason=f"дыр нет — вариация `{pick.slug}` для MoCap",
        enters_from=list(pick.enters_from),
        exits_to=list(pick.exits_to),
        title_ru=pick.title_ru,
    )


def invent_next_action(config: Config) -> str:
    """Только строка action (для lab/tools)."""
    return invent_next_shot(config).action
