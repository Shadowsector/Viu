"""Взаимодействия с предметами — две «шкалы»: Props и Shell (геометрия).

Props: мебель, инструменты — вес, взять, открыть…
Shell: стены, деревья, крыша — без веса; climb / встать / спать на поверхности.

«Сидеть задом» убрали из разметки — это выбор анимации, не свойство стула.
NSFW-usable — только ручная галочка (авто по диаметру цилиндра — позже, в Blender).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# --- Props (интерактивные предметы) ---
INTERACTION_CHOICES_PROPS: List[tuple[str, str]] = [
    ("sit", "Сидеть"),
    ("sleep", "Лечь / спать"),
    ("lean_on", "Опереться"),
    ("stand_on", "Встать на"),
    ("grab", "Взять"),
    ("throw", "Кинуть"),
    ("pocket", "В карман / рюкзак"),
    ("move", "Толкать / тянуть"),
    ("open", "Открыть / закрыть"),
    ("eat", "Есть"),
    ("read", "Читать"),
]

# --- Shell (геометрия: дом, дерево, крыша) — без веса и grab ---
INTERACTION_CHOICES_SHELL: List[tuple[str, str]] = [
    ("stand_on", "Можно встать (крыша, пень, ветка)"),
    ("sit", "Можно сидеть"),
    ("sleep", "Можно лечь / спать"),
    ("lean_on", "Можно опереться"),
]

PROP_FLAG_CHOICES: List[tuple[str, str]] = [
    ("can_stack", "Stackable / в сундук"),
    ("nsfw_usable", "NSFW-usable (вручную)"),
]

SHELL_FLAG_CHOICES: List[tuple[str, str]] = [
    ("can_climb", "Можно залезть (лазable)"),
]

# Обратная совместимость + экспорт в affordances.
INTERACTION_CHOICES: List[tuple[str, str]] = INTERACTION_CHOICES_PROPS

_LEGACY_INTERACTION_MAP: Dict[str, str] = {
    "push": "move",
    "pull": "move",
    "close": "open",
    "sit_reversed": "sit",
}


def normalize_interactions(raw: List[str]) -> List[str]:
    """Старые push/pull/close/sit_reversed → новая схема."""
    out: List[str] = []
    for key in raw or []:
        mapped = _LEGACY_INTERACTION_MAP.get(key, key)
        if mapped and mapped not in out:
            out.append(mapped)
    return out


def default_shell_interactions(mesh_name: str, collection: str) -> List[str]:
    """Подсказки для деревьев / крыш без ручной разметки."""
    name = (mesh_name or "").lower()
    col = (collection or "").lower()
    if any(k in name for k in ("pine", "tree", "brome", "foliage", "spruce", "oak")):
        return ["stand_on"]
    if col in ("landscape", "environment", "building", "buildings"):
        return []
    return []


def default_shell_flags(mesh_name: str, collection: str) -> Dict[str, bool]:
    name = (mesh_name or "").lower()
    flags = {"can_climb": False}
    if any(k in name for k in ("pine", "tree", "brome", "foliage", "spruce", "oak", "ladder")):
        flags["can_climb"] = True
    if "roof" in name or "beam" in name:
        flags["can_climb"] = True
    return flags
