"""Режиссёр Comfy MoCap: граф переходов → следующий кадр.

Away: сама идёт по дырам графа.
Дома: предлагает кадр (одобрение в Telegram) с альтернативами.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from ..animation_catalog import AnimationCatalogStore, animation_catalog_path
from ..animation_catalog.models import AnimationWish
from ..config import Config
from ..integrations.comfy.clip_review import ComfyClipStore, STATUS_KEPT, clip_review_path

# Базовые EN-шаблоны по slug — Wan лучше ест EN.
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

# Парафразы — чтобы повтор одного slug не был дословной копией
_SLUG_PARAPHRASE = {
    "idle": (
        "standing idle loop, quiet breath, tiny shoulder rolls, soft gaze drift",
        "neutral stand, micro weight transfer left-right, fingers relax, calm presence",
    ),
    "walk": (
        "steady walk cycle forward, relaxed arms, even footsteps, full body",
        "casual stroll forward, natural hip sway, arms swing opposite legs",
    ),
    "wave": (
        "friendly hello wave with right hand, smile energy, planted feet",
        "raise hand and wave once then twice, cheerful greeting, stand in place",
    ),
    "sit_down": (
        "from stand, lower onto invisible chair, knees bend, sit controlled",
        "take a seat motion: bend, touch invisible seat, settle upright",
    ),
    "sit_idle": (
        "sitting still on invisible chair, soft breath, tiny torso sway",
        "seated rest, hands on thighs, slight head tilt, quiet idle",
    ),
    "stand_up": (
        "rise from sit to stand, push lightly, straighten spine",
        "get up from chair pose to full standing, smooth continuous rise",
    ),
}


@dataclass
class MocapShotPlan:
    action: str
    catalog_slug: str
    reason: str
    enters_from: List[str] = field(default_factory=list)
    exits_to: List[str] = field(default_factory=list)
    title_ru: str = ""
    alternatives: List[str] = field(default_factory=list)
    looped: bool = False

    def summary_ru(self) -> str:
        kind = "цикл (looped)" if self.looped else "переход / one-shot"
        lines = [
            f"Снимаю «{self.title_ru or self.catalog_slug}»: {self.action}",
            f"Тип: {kind}. Почему: {self.reason}",
            "Ракурс: только ¾ · 3 разных дубля (seed + timing).",
            f"Граф: {self.enters_from or '—'} → `{self.catalog_slug}` → {self.exits_to or '—'}",
        ]
        if self.alternatives:
            lines.append("Ещё можно: " + ", ".join(self.alternatives[:4]))
        return "\n".join(lines)


def _recent_slugs(config: Config, *, limit: int = 12) -> Set[str]:
    store = ComfyClipStore(clip_review_path(config)).load()
    kept = [c for c in store.clips if c.status == STATUS_KEPT]
    kept.sort(key=lambda c: c.kept_at or c.created_at, reverse=True)
    out: Set[str] = set()
    for c in kept[:limit]:
        if c.catalog_slug:
            out.add(c.catalog_slug)
    return out


def _wish_filled(w: AnimationWish) -> bool:
    """Дыра закрыта, если есть ref_video или статус не wished."""
    return AnimationCatalogStore.is_filled(w)


def _wish_to_action(wish: AnimationWish, *, paraphrase_i: int = 0) -> str:
    if wish.slug in _SLUG_ACTION_EN:
        base = _SLUG_ACTION_EN[wish.slug]
        alts = _SLUG_PARAPHRASE.get(wish.slug) or ()
        if paraphrase_i > 0 and alts:
            base = alts[(paraphrase_i - 1) % len(alts)]
    else:
        words = wish.slug.replace("_", " ")
        hint = (wish.looks_like or "").strip()
        if hint and re.search(r"[A-Za-z]{3,}", hint):
            base = f"{words}, {hint}"
        else:
            base = f"{words}, full body character motion, clear limbs, loopable short clip"
    if wish_is_looped(wish):
        if "seamless loop" not in base.lower() and "loopable" not in base.lower():
            base = (
                f"{base}, seamless loop, matching first and last pose, "
                "continuous cycle, no freeze at end"
            )
    return base


def wish_is_looped(wish: AnimationWish) -> bool:
    """Цикл (idle/walk/sit_idle…) vs one-shot переход."""
    if getattr(wish, "looped", False):
        return True
    if wish.category == "transition":
        return False
    if wish.slug in (
        "idle",
        "sit_idle",
        "sleep_idle",
        "walk",
        "walk_back",
        "run",
        "sneak",
        "walk_proud",
    ):
        return True
    return "idle" in wish.slug


def _sources_ready(cat: AnimationCatalogStore, w: AnimationWish) -> bool:
    return cat.sources_ready(w)


def _graph_ordered_holes(
    cat: AnimationCatalogStore, holes: List[AnimationWish]
) -> List[AnimationWish]:
    """Сначала то, чьи enters_from уже сняты; потом wave; не idle если есть иное.

    holes уже отфильтрованы (например без recent) — не зовём ordered_holes() целиком.
    **idle не берём**, пока есть другие дыры wave≤1.
    """
    ready = [w for w in holes if _sources_ready(cat, w)]
    pool = ready or holes
    wave1 = [w for w in pool if w.wave <= 1]
    base = wave1 or pool
    # Жёстко: не idle, пока есть любая другая дыра wave 1
    other_w1 = [w for w in holes if w.wave <= 1 and w.slug != "idle"]
    if other_w1:
        base = [w for w in base if w.slug != "idle"] or base
    non_idle = [w for w in base if w.slug != "idle"]
    pool2 = non_idle or base

    def _entry_key(w: AnimationWish) -> tuple:
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


def invent_next_shot(config: Config) -> MocapShotPlan:
    """Следующий клип по каталогу и графу. Без LLM."""
    cat = AnimationCatalogStore(animation_catalog_path(config)).load()
    recent = _recent_slugs(config)
    # missing() уже без ref_video; плюс недавние kept
    holes = [w for w in cat.missing() if w.slug not in recent]
    ordered = _graph_ordered_holes(cat, holes) if holes else []

    alts: List[str] = []
    if len(ordered) > 1:
        alts = [f"{w.slug} ({w.title_ru})" for w in ordered[1:5]]

    if ordered:
        wish = ordered[0]
        # сколько раз уже снимали этот slug (для парафраза)
        kept_n = sum(
            1
            for c in ComfyClipStore(clip_review_path(config)).load().clips
            if c.status == STATUS_KEPT and c.catalog_slug == wish.slug
        )
        action = _wish_to_action(wish, paraphrase_i=kept_n)
        reason = (
            f"дыра в графе `{wish.slug}` (wave {wish.wave}, {wish.category}); "
            f"когда: {wish.when_used[:80]}"
        )
        if wish.enters_from:
            reason += f"; enters_from={wish.enters_from}"
        return MocapShotPlan(
            action=action,
            catalog_slug=wish.slug,
            reason=reason,
            enters_from=list(wish.enters_from),
            exits_to=list(wish.exits_to),
            title_ru=wish.title_ru,
            alternatives=alts,
            looped=wish_is_looped(wish),
        )

    # всё закрыто — вариация по графу (не тот же idle)
    all_w = [w for w in cat.all_wishes() if w.slug not in recent]
    if not all_w:
        all_w = cat.all_wishes()
    pick = next((w for w in all_w if w.slug != "idle"), all_w[0] if all_w else None)
    if pick is None:
        return MocapShotPlan(
            action=_SLUG_ACTION_EN["wave"],
            catalog_slug="wave",
            reason="каталог пуст — жест приветствия как разведка",
            title_ru="Машет рукой",
        )
    return MocapShotPlan(
        action=_wish_to_action(pick, paraphrase_i=1),
        catalog_slug=pick.slug,
        reason=f"дыр нет — вариация `{pick.slug}` для MoCap",
        enters_from=list(pick.enters_from),
        exits_to=list(pick.exits_to),
        title_ru=pick.title_ru,
        looped=wish_is_looped(pick),
    )


def invent_next_action(config: Config) -> str:
    return invent_next_shot(config).action


def invent_shot_choices(config: Config, *, limit: int = 5) -> List[MocapShotPlan]:
    """Несколько кандидатов — для предложения дома."""
    cat = AnimationCatalogStore(animation_catalog_path(config)).load()
    recent = _recent_slugs(config)
    holes = [w for w in cat.missing() if w.slug not in recent]
    ordered = _graph_ordered_holes(cat, holes) if holes else []
    out: List[MocapShotPlan] = []
    for w in ordered[:limit]:
        out.append(
            MocapShotPlan(
                action=_wish_to_action(w),
                catalog_slug=w.slug,
                reason=f"кандидат `{w.slug}`",
                enters_from=list(w.enters_from),
                exits_to=list(w.exits_to),
                title_ru=w.title_ru,
            )
        )
    return out
