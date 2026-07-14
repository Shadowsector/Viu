"""Ракурсы камеры для тройной генерации под Cascadeur MoCap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class CameraAngle:
    id: str
    label_ru: str
    prompt_en: str


DEFAULT_ANGLES: Tuple[CameraAngle, ...] = (
    CameraAngle(
        "side",
        "сбоку",
        "side view, camera on the character's left, "
        "full body visible head to toe, profile silhouette clear, limbs readable",
    ),
    CameraAngle(
        "three_quarter",
        "три четверти",
        "three-quarter view, camera 45 degrees off front, "
        "full body visible head to toe, limbs unoccluded",
    ),
    CameraAngle(
        "front",
        "анфас",
        "front view, camera facing the character, "
        "full body visible head to toe, face and torso evenly lit, symmetric stance readable",
    ),
)


def default_angles() -> List[CameraAngle]:
    return list(DEFAULT_ANGLES)
