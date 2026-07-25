"""Контракт верхнего уровня U:\\Desktop Mascot — категории, не автоскан."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

# Как на диске Дена (Total Commander, 2026-07).
MASCOT_TOP_CATEGORIES: Tuple[str, ...] = (
    "Animations",
    "Clothes",
    "Cocks",
    "Monsters",
    "NS Animations",
    "Props",
    "Toys",
    "Women",
)

# Куда класть один пак из архива → U:\\Anabarra\\Inbox\\...
MASCOT_CATEGORY_TO_INBOX: Dict[str, str] = {
    "Animations": "animations",
    "NS Animations": "animations",
    "Clothes": "creatures",
    "Cocks": "creatures",
    "Monsters": "creatures",
    "Women": "creatures",
    "Props": "",  # корень Inbox — паки домиков/пропов
    "Toys": "creatures",
}


def classify_mascot_category(name: str) -> str | None:
    """Вернуть каноническое имя категории или None."""
    raw = (name or "").strip()
    if not raw:
        return None
    lower = raw.lower().replace("_", " ").replace("-", " ")
    for cat in MASCOT_TOP_CATEGORIES:
        if cat.lower() == lower:
            return cat
    aliases = {
        "nsfw animations": "NS Animations",
        "ns_animations": "NS Animations",
        "woman": "Women",
        "animation": "Animations",
        "prop": "Props",
        "monster": "Monsters",
        "cloth": "Clothes",
        "clothing": "Clothes",
    }
    return aliases.get(lower)


def expected_mascot_layout(archive_root: Path) -> Dict[str, Path]:
    """Ожидаемые пути категорий (могут ещё не существовать на диске)."""
    root = Path(archive_root)
    return {cat: root / cat for cat in MASCOT_TOP_CATEGORIES}


def missing_mascot_categories(archive_root: Path) -> List[str]:
    """Какие канонические папки отсутствуют (только top-level exists check)."""
    root = Path(archive_root)
    if not root.is_dir():
        return list(MASCOT_TOP_CATEGORIES)
    missing: List[str] = []
    for cat in MASCOT_TOP_CATEGORIES:
        if not (root / cat).is_dir():
            missing.append(cat)
    return missing


def inbox_subdir_for_category(category: str) -> str | None:
    cat = classify_mascot_category(category) or category
    if cat not in MASCOT_CATEGORY_TO_INBOX:
        return None
    return MASCOT_CATEGORY_TO_INBOX[cat]
