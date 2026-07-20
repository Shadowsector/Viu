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
from ..integrations.comfy.naming import max_clips_per_action, slug_at_quota

# Цикл «временный дом / сарай»: пол, стул, стол, кровать, осмотр.
BARN_SHED_CYCLE: tuple[str, ...] = (
    "walk",
    "sit_down",
    "sit_idle",
    "stand_up",
    "lie_down",
    "sleep_idle",
    "get_up",
    "lean",
    "look_around",
    "look_window",
    "take",
    "eat",
    "drink",
    "touch_self",
)

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
    "lean": "leaning against invisible wall or table edge, relaxed weight shift, one elbow on surface",
    "look_around": "standing, turning head left and right, examining surroundings, curious gaze",
    "look_window": "standing at window, looking outside, hand on frame optional, thoughtful pause",
    "take": "bending to pick up object from floor or table, then standing with item in hand",
    "eat": "standing or sitting, bringing food to mouth, chewing, holding plate or apple",
    "drink": "raising cup or bottle to lips, small sip, lowering hand",
    "touch_self": (
        "private solo moment, seated or lying, slow self-touch, intimate breathing, "
        "shy closed eyes, loopable subtle motion"
    ),
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
    stop_cycle: bool = False

    def summary_ru(self) -> str:
        if self.stop_cycle:
            return f"⏸ Comfy MoCap: {self.reason}"
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


def _filter_quota(config: Config, wishes: List[AnimationWish]) -> List[AnimationWish]:
    return [w for w in wishes if not slug_at_quota(config, w.slug)]


def _barn_cycle_enabled() -> bool:
    import os

    return os.environ.get("VIU_COMFY_BARN_CYCLE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def barn_cycle_status(config: Config) -> str:
    """Сводка по лимиту 10 клипов на действие в цикле сарая."""
    lines = [f"Цикл сарая/дом (лимит {max_clips_per_action()} kept на действие):"]
    for slug in BARN_SHED_CYCLE:
        n = kept_count_for_slug(config, slug)
        mark = "✓" if n >= max_clips_per_action() else "…"
        lines.append(f"  {mark} {slug}: {n}/{max_clips_per_action()}")
    pending = pending_review_count(config)
    if pending:
        lines.append(f"На оценку (кандидаты): {pending}")
    return "\n".join(lines)


def kept_count_for_slug(config: Config, slug: str) -> int:
    from ..integrations.comfy.naming import kept_count_for_slug as _n

    return _n(config, slug)


def pending_review_count(config: Config) -> int:
    store = ComfyClipStore(clip_review_path(config)).load()
    return sum(1 for c in store.clips if c.status == "candidate")


def action_for_slug(
    config: Config,
    slug: str,
    *,
    paraphrase_i: int = 0,
) -> str:
    """EN-промпт по catalog_slug (не оставлять stale idle stand при lie_down)."""
    from ..integrations.comfy.clip_review import normalize_catalog_slug

    slug = normalize_catalog_slug(slug)
    if not slug:
        return _SLUG_ACTION_EN.get("idle", "idle stand")
    cat = AnimationCatalogStore(animation_catalog_path(config)).load()
    wish = cat.get_by_slug(slug)
    if wish is not None:
        return _wish_to_action(wish, paraphrase_i=paraphrase_i)
    if slug in _SLUG_ACTION_EN:
        return _SLUG_ACTION_EN[slug]
    return slug.replace("_", " ")


def sync_session_shot_from_slug(config: Config, session) -> str:
    """Подтянуть action/граф из catalog_slug. Возвращает итоговый action."""
    from ..integrations.comfy.clip_review import normalize_catalog_slug

    slug = normalize_catalog_slug(str(session.meta.get("catalog_slug") or ""))
    if not slug:
        return str(session.meta.get("approved_action") or session.meta.get("action") or "")
    kept_n = kept_count_for_slug(config, slug)
    action = action_for_slug(config, slug, paraphrase_i=kept_n)
    cat = AnimationCatalogStore(animation_catalog_path(config)).load()
    wish = cat.get_by_slug(slug)
    session.meta["catalog_slug"] = slug
    session.meta["action"] = action
    session.meta["approved_action"] = action
    session.meta["looped"] = wish_is_looped(wish) if wish else bool(session.meta.get("looped"))
    if wish:
        if wish.enters_from:
            session.meta["enters_from"] = list(wish.enters_from)
        if wish.exits_to:
            session.meta["exits_to"] = list(wish.exits_to)
    return action


def invent_next_shot(config: Config, *, barn_cycle: Optional[bool] = None) -> MocapShotPlan:
    """Следующий клип по каталогу и графу. Без LLM."""
    from ..integrations.comfy.scene_choice import (
        format_scene_choice_message,
        is_paused_for_scene_choice,
        load_scene_state,
        get_focus_slugs,
    )

    if is_paused_for_scene_choice(config):
        st = load_scene_state(config)
        return MocapShotPlan(
            action="",
            catalog_slug="",
            reason=format_scene_choice_message(st),
            stop_cycle=True,
            title_ru=st.completed_title,
        )

    use_barn = _barn_cycle_enabled() if barn_cycle is None else barn_cycle
    cat = AnimationCatalogStore(animation_catalog_path(config)).load()
    recent = _recent_slugs(config)
    # missing() уже без ref_video; плюс недавние kept
    holes = [w for w in cat.missing() if w.slug not in recent]
    holes = _filter_quota(config, holes)
    focus = get_focus_slugs(config)
    if focus:
        holes = [w for w in holes if w.slug in focus] or holes
    if use_barn:
        barn_holes = [w for w in holes if w.slug in BARN_SHED_CYCLE]
        if barn_holes:
            holes = barn_holes
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

    # всё закрыто — вариация, но не idle и не сверх лимита
    all_w = [w for w in cat.all_wishes() if w.slug not in recent]
    all_w = _filter_quota(config, all_w)
    if use_barn:
        barn_all = [w for w in all_w if w.slug in BARN_SHED_CYCLE]
        if barn_all:
            all_w = barn_all
    idle_w = cat.get_by_slug("idle")
    if idle_w and _wish_filled(idle_w):
        all_w = [w for w in all_w if w.slug != "idle"]
    if not all_w:
        reason = (
            f"все действия цикла сарая набрали по {max_clips_per_action()} kept-клипов "
            f"(или дыры закрыты). {barn_cycle_status(config)}"
        )
        return MocapShotPlan(
            action="",
            catalog_slug="",
            reason=reason,
            stop_cycle=True,
        )
    pick = next((w for w in all_w if w.slug != "idle"), all_w[0] if all_w else None)
    if pick is None:
        return MocapShotPlan(
            action="",
            catalog_slug="",
            reason="каталог пуст",
            stop_cycle=True,
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
