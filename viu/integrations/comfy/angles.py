"""Ракурсы / дубли для Comfy MoCap.

С 2026-07: для MoCap достаточно **три четверти**.
«Тройка» = три **разных дубля** одного действия (разный seed + вариация промпта),
а не side/front/¾.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class CameraAngle:
    id: str
    label_ru: str
    prompt_en: str


THREE_QUARTER = CameraAngle(
    "three_quarter",
    "три четверти",
    "three-quarter view, full body",
)

# Устаревшие ракурсы — оставлены для ручного comfy_mocap angle=… и старых клипов.
LEGACY_ANGLES: Tuple[CameraAngle, ...] = (
    CameraAngle(
        "side",
        "сбоку",
        "side view, camera on the character's left, "
        "full body visible head to toe, profile silhouette clear, limbs readable",
    ),
    THREE_QUARTER,
    CameraAngle(
        "front",
        "анфас",
        "front view, camera facing the character, "
        "full body visible head to toe, face and torso evenly lit, symmetric stance readable",
    ),
)

# Пять дублей ¾ для MoCap (AFK и lab).
MOCAP_TAKE_COUNT = 5

MOCAP_TAKES: Tuple[CameraAngle, ...] = (
    CameraAngle(
        "take_a",
        "дубль A (¾)",
        THREE_QUARTER.prompt_en,
    ),
    CameraAngle(
        "take_b",
        "дубль B (¾)",
        THREE_QUARTER.prompt_en,
    ),
    CameraAngle(
        "take_c",
        "дубль C (¾)",
        THREE_QUARTER.prompt_en,
    ),
    CameraAngle(
        "take_d",
        "дубль D (¾)",
        THREE_QUARTER.prompt_en,
    ),
    CameraAngle(
        "take_e",
        "дубль E (¾)",
        THREE_QUARTER.prompt_en,
    ),
)

# DEFAULT_ANGLES = дубли MoCap (не три камеры)
DEFAULT_ANGLES: Tuple[CameraAngle, ...] = MOCAP_TAKES

# Away / авто-выбор: средний дубль
AWAY_AUTO_TAKE_ID = "take_b"


def default_angles() -> List[CameraAngle]:
    """Углы/дубли для генерации MoCap."""
    return list(MOCAP_TAKES)


def mocap_take_count() -> int:
    return len(MOCAP_TAKES)


def legacy_angles() -> List[CameraAngle]:
    return list(LEGACY_ANGLES)


def angle_by_id(angle_id: str) -> CameraAngle | None:
    aid = (angle_id or "").strip().lower()
    for a in list(MOCAP_TAKES) + list(LEGACY_ANGLES):
        if a.id == aid:
            return a
    return None
