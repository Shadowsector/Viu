"""Ракурсы камеры для тройной генерации под Cascadeur MoCap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class CameraAngle:
    id: str
    label_ru: str
    prompt_en: str


# Три вида — вертикальный кадр, фигура на весь рост.
DEFAULT_ANGLES: Tuple[CameraAngle, ...] = (
    CameraAngle(
        "side",
        "сбоку",
        "vertical portrait framing, side view, camera on the character's left, "
        "full body fills the frame head to toe, profile silhouette clear",
    ),
    CameraAngle(
        "three_quarter",
        "три четверти",
        "vertical portrait framing, three-quarter view, camera 45 degrees off front, "
        "full body fills the frame head to toe, limbs unoccluded",
    ),
    CameraAngle(
        "front",
        "анфас",
        "vertical portrait framing, front view, camera facing the character, "
        "full body fills the frame head to toe, symmetric stance readable",
    ),
)


def default_angles() -> List[CameraAngle]:
    return list(DEFAULT_ANGLES)
