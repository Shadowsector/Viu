"""Подсказки: имена HS2 / Illusion → slug каталога Шани."""

from __future__ import annotations

import re
from typing import Optional

# Нормализованное подстрока в имени клипа → animation_catalog slug
_HINTS: tuple[tuple[str, str], ...] = (
    ("idle", "idle"),
    ("loop_idle", "idle"),
    ("walk", "walk"),
    ("run", "run"),
    ("sneak", "sneak"),
    ("sit", "sit_idle"),
    ("sit_idle", "sit_idle"),
    ("sitdown", "sit_down"),
    ("sit_down", "sit_down"),
    ("standup", "stand_up"),
    ("stand_up", "stand_up"),
    ("lie", "lie_down"),
    ("sleep", "sleep_idle"),
    ("yawn", "yawn"),
    ("stretch", "stretch"),
    ("jump", "jump"),
    ("fall", "fall"),
    ("climb", "climb_up"),
    ("attack", "attack_claws"),
    ("throw", "throw"),
    ("take", "take"),
    ("pickup", "take"),
    ("eat", "eat"),
    ("drink", "drink"),
    ("dance", "dance"),
    ("greet", "greeting"),
    ("wave", "greeting"),
    ("hit", "hit_react"),
    ("knock", "knock"),
    ("peek", "look_window"),
    ("window", "look_window"),
    ("shower", "shower"),
    ("bath", "bath"),
    ("cook", "cook"),
    ("stumble", "stumble"),
    ("walkback", "walk_back"),
    ("backward", "walk_back"),
    ("groom", "groom"),
    ("scout", "scout"),
    ("hide", "hide_peek"),
)


def _norm(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def suggest_catalog_slug(clip_name: str) -> Optional[str]:
    """Эвристика slug для animation_catalog по имени HS2-клипа."""
    n = _norm(clip_name)
    if not n:
        return None
    best_slug: Optional[str] = None
    best_len = 0
    for key, slug in _HINTS:
        kn = _norm(key)
        if kn in n and len(kn) >= best_len:
            best_slug = slug
            best_len = len(kn)
    return best_slug
