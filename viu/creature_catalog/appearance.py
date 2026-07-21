"""Пресеты внешности существа: тон кожи и цвет волос (Wardrobe / каталог)."""

from __future__ import annotations

from typing import Dict, Tuple

# id → (R, G, B) множитель к исходному Base Color материала
SKIN_TONE_IDS = (
    "default",
    "fair",
    "light",
    "medium",
    "tan",
    "olive",
    "dark",
)

SKIN_TONE_LABELS: Dict[str, str] = {
    "default": "как в файле",
    "fair": "светлая",
    "light": "светло-бежевая",
    "medium": "средняя",
    "tan": "загорелая",
    "olive": "оливковая",
    "dark": "тёмная",
}

SKIN_TONE_RGB: Dict[str, Tuple[float, float, float]] = {
    "default": (1.0, 1.0, 1.0),
    "fair": (1.08, 0.94, 0.90),
    "light": (1.02, 0.88, 0.78),
    "medium": (0.92, 0.76, 0.62),
    "tan": (0.85, 0.68, 0.52),
    "olive": (0.78, 0.72, 0.55),
    "dark": (0.55, 0.42, 0.34),
}

HAIR_COLOR_IDS = (
    "default",
    "black",
    "dark_brown",
    "brown",
    "blonde",
    "auburn",
    "silver",
    "fantasy_blue",
)

HAIR_COLOR_LABELS: Dict[str, str] = {
    "default": "как в файле",
    "black": "чёрные",
    "dark_brown": "тёмно-каштан",
    "brown": "каштан",
    "blonde": "блонд",
    "auburn": "рыжие",
    "silver": "серебро",
    "fantasy_blue": "фэнтези синие",
}

HAIR_COLOR_RGB: Dict[str, Tuple[float, float, float]] = {
    "default": (1.0, 1.0, 1.0),
    "black": (0.12, 0.10, 0.09),
    "dark_brown": (0.28, 0.18, 0.12),
    "brown": (0.42, 0.26, 0.16),
    "blonde": (0.78, 0.62, 0.32),
    "auburn": (0.62, 0.22, 0.10),
    "silver": (0.72, 0.72, 0.78),
    "fantasy_blue": (0.22, 0.38, 0.85),
}


def normalize_skin_tone(value: str) -> str:
    v = (value or "default").strip()
    return v if v in SKIN_TONE_IDS else "default"


def normalize_hair_color(value: str) -> str:
    v = (value or "default").strip()
    return v if v in HAIR_COLOR_IDS else "default"
