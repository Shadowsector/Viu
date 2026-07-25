"""Чеклист эталонных поз для I2V (что снимать в HS2).

idle stand — 2–3 ракурса: фронт, ¾, профиль.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ...config import Config


@dataclass(frozen=True)
class SeedPoseNeed:
    """Один эталон, который стоит иметь в библиотеке."""

    id: str
    slug: str  # catalog_slug анимации (или группа)
    title_ru: str
    priority: int  # 1 = сначала, 2 = потом
    variant: str = "start"  # start | end | mid | front | three_quarter | profile
    hs2_hint: str = ""
    graph: str = ""


# Порядок = рекомендуемый порядок съёмки в HS2.
SEED_POSE_NEEDS: Tuple[SeedPoseNeed, ...] = (
    # --- idle × 3 ---
    SeedPoseNeed(
        "idle_front",
        "idle",
        "Стойка idle — фронт",
        1,
        "front",
        "Полный рост, руки вдоль тела, взгляд в камеру, белый фон.",
        "Ходьба",
    ),
    SeedPoseNeed(
        "idle_tq",
        "idle",
        "Стойка idle — ¾",
        1,
        "three_quarter",
        "Тот же idle, корпус чуть вбок (как Wan ¾). Главный эталон для T2V/I2V.",
        "Ходьба",
    ),
    SeedPoseNeed(
        "idle_profile",
        "idle",
        "Стойка idle — профиль",
        1,
        "profile",
        "Боком, полный рост — для walk/run переходов.",
        "Ходьба",
    ),
    # --- locomotion ---
    SeedPoseNeed(
        "walk_mid",
        "walk",
        "Шаг (середина цикла)",
        1,
        "mid",
        "Одна нога впереди, руки в противофазе, профиль или ¾.",
        "Ходьба",
    ),
    SeedPoseNeed(
        "walk_back_mid",
        "walk_back",
        "Шаг назад",
        2,
        "mid",
        "Отступает, корпус чуть наклонён к камере.",
        "Ходьба",
    ),
    SeedPoseNeed(
        "run_mid",
        "run",
        "Бег (середина)",
        2,
        "mid",
        "Шире шаг, наклон вперёд.",
        "Ходьба",
    ),
    # --- сесть ---
    SeedPoseNeed(
        "sit_down_start",
        "sit_down",
        "Садится — старт (стоя у кровати/стула)",
        1,
        "start",
        "Стоит перед краем, руки чуть для баланса — начало перехода.",
        "Сесть",
    ),
    SeedPoseNeed(
        "sit_idle",
        "sit_idle",
        "Сидит (цикл)",
        1,
        "mid",
        "Уже сидит, полный рост / ¾, спокойно.",
        "Сесть",
    ),
    SeedPoseNeed(
        "stand_up_end",
        "stand_up",
        "Встала из сидя — конец",
        2,
        "end",
        "Только что выпрямилась из sit → почти idle.",
        "Сесть",
    ),
    # --- спать ---
    SeedPoseNeed(
        "lie_down_start",
        "lie_down",
        "Ложится — старт",
        1,
        "start",
        "Стоит у кровати, начинает опускаться / садиться на край.",
        "Лечь спать",
    ),
    SeedPoseNeed(
        "sleep_idle",
        "sleep_idle",
        "Лежит / спит",
        1,
        "mid",
        "На спине или боку, полный кадр тела, белый/простой фон.",
        "Лечь спать",
    ),
    SeedPoseNeed(
        "get_up_end",
        "get_up",
        "Встала с лежания — конец",
        2,
        "end",
        "Почти стойка после подъёма с кровати.",
        "Лечь спать",
    ),
    # --- залезть ---
    SeedPoseNeed(
        "climb_start",
        "climb_up",
        "Залезть — старт (хват)",
        1,
        "start",
        "Руки на уступе/стволе, нога ищет опору — начало цикла.",
        "Залезть",
    ),
    SeedPoseNeed(
        "climb_mid",
        "climb_up",
        "Залезть — середина",
        2,
        "mid",
        "Подтянулась, вторая нога на уступе.",
        "Залезть",
    ),
    # --- жесты / быт ---
    SeedPoseNeed(
        "wave",
        "wave",
        "Машет рукой",
        1,
        "mid",
        "Стоя, рука на уровне головы.",
        "Жесты",
    ),
    SeedPoseNeed(
        "look_around",
        "look_around",
        "Оглядывается",
        1,
        "mid",
        "Стоя, голова/плечи в сторону.",
        "Осмотр сарая",
    ),
    SeedPoseNeed(
        "lean",
        "lean",
        "Облокачивается",
        2,
        "mid",
        "Опёрлась бедром/локтем о край стола/стены.",
        "Осмотр сарая",
    ),
    SeedPoseNeed(
        "look_window",
        "look_window",
        "Смотрит в окно",
        2,
        "mid",
        "Стоя у «окна», взгляд в сторону.",
        "Осмотр сарая",
    ),
    SeedPoseNeed(
        "take",
        "take",
        "Берёт предмет",
        1,
        "mid",
        "Наклон / рука к предмету на уровне пояса.",
        "Взять / есть / пить",
    ),
    SeedPoseNeed(
        "eat",
        "eat",
        "Ест",
        2,
        "mid",
        "Стоя или сидя, рука у рта.",
        "Взять / есть / пить",
    ),
    SeedPoseNeed(
        "drink",
        "drink",
        "Пьёт",
        2,
        "mid",
        "Чашка/бутылка у губ.",
        "Взять / есть / пить",
    ),
    SeedPoseNeed(
        "touch_self",
        "touch_self",
        "Touch self (сидя)",
        1,
        "mid",
        "Сидя на краю кровати — для NSFW MoCap; полный рост, не face closeup.",
        "Интим",
    ),
    SeedPoseNeed(
        "jump_mid",
        "jump",
        "Прыжок (в воздухе / присед)",
        2,
        "mid",
        "Либо присед перед отрывом, либо короткая фаза в воздухе.",
        "Прыжок / падение",
    ),
    SeedPoseNeed(
        "fall_mid",
        "fall",
        "Падение / приземление",
        2,
        "mid",
        "Потеря баланса или squat absorb.",
        "Прыжок / падение",
    ),
)


def pose_needs(*, priority_max: int = 2) -> List[SeedPoseNeed]:
    return [p for p in SEED_POSE_NEEDS if p.priority <= priority_max]


def format_pose_checklist_text(
    config: Optional[Config] = None,
    *,
    priority_max: int = 2,
) -> str:
    """Человекочитаемый список: что снять в HS2 + покрытие библиотеки."""
    covered = _coverage_map(config) if config is not None else {}
    lines = [
        "Эталоны для I2V — сними в HS2 (полный рост, простой фон), потом «Из Inbox (HS2)»:",
        "",
    ]
    current_graph = ""
    for p in pose_needs(priority_max=priority_max):
        if p.graph != current_graph:
            current_graph = p.graph
            lines.append(f"▸ {current_graph}")
        mark = "✓" if covered.get(p.id) else ("·" if p.priority == 1 else "○")
        pri = "P1" if p.priority == 1 else "P2"
        lines.append(f"  {mark} [{pri}] {p.title_ru}  (`{p.slug}` / {p.variant})")
        if p.hs2_hint:
            lines.append(f"      {p.hs2_hint}")
    lines.append("")
    lines.append(
        "Idle: лучше 3 кадра (фронт, ¾, профиль). "
        "¾ — основной start для Wan; остальные — запас под walk/переходы."
    )
    lines.append("✓ = уже есть ready-эталон в библиотеке на этот slug/вариант.")
    return "\n".join(lines)


def _entry_ready(e: object) -> bool:
    status = str(getattr(e, "status", "") or "")
    source = str(getattr(e, "source", "") or "")
    return status == "ready" or source == "refined"


def _coverage_map(config: Config) -> Dict[str, bool]:
    from .seed_library import load_library, load_slug_seeds

    lib = load_library(config)
    by_slug: Dict[str, List] = {}
    for e in lib:
        slug = (getattr(e, "slug", "") or "").strip()
        if slug:
            by_slug.setdefault(slug, []).append(e)

    mapping = load_slug_seeds(config)
    out: Dict[str, bool] = {}
    for p in SEED_POSE_NEEDS:
        ok = False
        slot = mapping.get(p.slug) or {}
        if p.variant in ("start", "front", "three_quarter", "mid") and slot.get("start"):
            ok = True
        if p.variant == "end" and slot.get("end"):
            ok = True
        ready_for_slug = [e for e in (by_slug.get(p.slug) or []) if _entry_ready(e)]
        for e in ready_for_slug:
            blob = f"{e.id} {e.title} {' '.join(e.tags)}".lower()
            tokens = (
                p.variant,
                p.variant.replace("_", " "),
                p.id,
                p.id.replace("_", " "),
                "¾" if p.variant == "three_quarter" else "",
                "3/4" if p.variant == "three_quarter" else "",
                "фронт" if p.variant == "front" else "",
                "профиль" if p.variant == "profile" else "",
            )
            if any(t and t.lower() in blob for t in tokens):
                ok = True
                break
        # Один ready на slug закрывает mid/start, если вариантов не несколько.
        if not ok and ready_for_slug and p.variant in ("mid", "start"):
            # Для idle требуем явное совпадение variant (их три).
            if p.slug != "idle":
                ok = True
        out[p.id] = ok
    return out


def checklist_rows(config: Config, *, priority_max: int = 2) -> List[Tuple[SeedPoseNeed, bool]]:
    covered = _coverage_map(config)
    return [(p, bool(covered.get(p.id))) for p in pose_needs(priority_max=priority_max)]
