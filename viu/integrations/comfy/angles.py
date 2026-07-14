"""Ракурсы камеры для тройной генерации под Cascadeur MoCap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class CameraAngle:
    id: str
    label_ru: str
    prompt_en: str


# Три вида на один промпт — потом сравним, какой лучше ест Cascadeur MoCap.
DEFAULT_ANGLES: Tuple[CameraAngle, ...] = (
    CameraAngle(
        "side",
        "сбоку",
        "side view, camera on the character's left, full body visible, profile silhouette clear",
    ),
    CameraAngle(
        "three_quarter",
        "три четверти",
        "three-quarter view, camera 45 degrees off front, full body visible, limbs unoccluded",
    ),
    CameraAngle(
        "front",
        "анфас",
        "front view, camera facing the character, full body visible, symmetric stance readable",
    ),
)


def default_angles() -> List[CameraAngle]:
    return list(DEFAULT_ANGLES)
