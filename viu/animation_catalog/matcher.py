"""Сопоставление FBX-файла с записью каталога."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from .models import AnimationWish
from .store import AnimationCatalogStore

# Сильные совпадения в имени файла
_SLUG_ALIASES = {
    "sitdown": "sit_down",
    "sittingdown": "sit_down",
    "sit_idle": "sit_idle",
    "sittingidle": "sit_idle",
    "sitting": "sit_idle",
    "standup": "stand_up",
    "gettingup": "stand_up",
    "liedown": "lie_down",
    "lyingdown": "lie_down",
    "sleeping": "sleep_idle",
    "sleepingidle": "sleep_idle",
    "pickup": "take",
    "pickingup": "take",
    "melee": "attack_claws",
    "climb": "climb_up",
    "climbing": "climb_up",
}


def _normalize_name(name: str) -> str:
    s = Path(name).stem.lower()
    s = re.sub(r"^x bot@", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def match_fbx_to_wish(
    fbx_path: Path,
    store: AnimationCatalogStore,
) -> Tuple[Optional[AnimationWish], float, str]:
    """Возвращает (wish, score 0-1, reason)."""
    norm = _normalize_name(fbx_path.name)
    if not norm:
        return None, 0.0, "пустое имя"

    # Прямой slug в имени
    for wish in store.all_wishes():
        if wish.slug.replace("_", "") in norm.replace("_", ""):
            return wish, 0.95, f"slug {wish.slug}"

    # Алиасы
    for key, slug in _SLUG_ALIASES.items():
        if key in norm.replace("_", ""):
            w = store.get_by_slug(slug)
            if w:
                return w, 0.85, f"alias {key}→{slug}"

    # Mixamo hints
    best: Optional[AnimationWish] = None
    best_score = 0.0
    best_hint = ""
    for wish in store.all_wishes():
        for hint in wish.mixamo_hints:
            h = _normalize_name(hint)
            if len(h) < 4:
                continue
            if h in norm or norm in h:
                score = 0.7 + min(len(h), 20) / 100.0
                if score > best_score:
                    best, best_score, best_hint = wish, score, hint

    if best and best_score >= 0.7:
        return best, best_score, f"hint «{best_hint}»"

    # Ключевые слова категории adventure/fight etc.
    keyword_map = [
        (r"walk", "walk"),
        (r"run", "run"),
        (r"idle", "idle"),
        (r"jump", "jump"),
        (r"yawn", "yawn"),
        (r"throw", "throw"),
    ]
    for pat, slug in keyword_map:
        if re.search(pat, norm):
            w = store.get_by_slug(slug)
            if w:
                return w, 0.65, f"keyword {pat}"

    return None, 0.0, "нет совпадения — добавь в viu_clips.json или уточни имя файла"


def suggest_rename_for_wish(wish: AnimationWish, original_name: str) -> str:
    """Как лучше назвать FBX для автосync."""
    base = wish.slug.replace("_", " ").title().replace(" ", "")
    return f"Shanya_{base}.fbx"
