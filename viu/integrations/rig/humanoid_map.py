"""Сопоставление сложного рига с Unity Humanoid БЕЗ переименования костей.

Реальные модели часто на Rigify (кости DEF-/ORG-/MCH-/tweak/WGT-…). Такие
риги переименовывать нельзя — они сломаются. Правильный путь: не трогая имена,
построить **карту соответствия** «слот Unity Humanoid → реальная кость»,
опираясь на деформирующие кости (DEF-). Финально карта подтверждается в
настройке Avatar внутри Unity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from .standard import ALIAS_MAP, CANON_ORDER, REQUIRED, normalize

SPINE_SLOTS = ["Hips", "Spine", "Chest", "UpperChest", "Neck", "Head"]

# Куски имён, характерные для управляющих (не деформирующих) костей.
_CONTROL_SUBSTR = (
    "_ik", "_fk", "tweak", "_master", "_drv", "pole", "target",
    "parent", "roll", "widget", "heel", "_swing", "_spin",
)
_CONTROL_PREFIX = ("WGT-", "MCH-", "MCH_", "VIS_", "VIS-")


def detect_rig_type(bones: List[str]) -> str:
    has_def = any(b.startswith("DEF-") for b in bones)
    has_mch = any(b.startswith("MCH-") for b in bones)
    if has_def and has_mch:
        return "rigify"
    if any(b.lower().startswith("mixamorig") for b in bones):
        return "mixamo"
    return "generic"


def _is_control(name: str) -> bool:
    if name.startswith(_CONTROL_PREFIX):
        return True
    low = name.lower()
    return any(s in low for s in _CONTROL_SUBSTR)


def _spine_index(name: str) -> int:
    m = re.search(r"(\d+)$", normalize(name))
    return int(m.group(1)) if m else 0


@dataclass
class HumanoidMap:
    rig_type: str
    renaming_needed: bool
    mapping: Dict[str, str] = field(default_factory=dict)  # слот Unity -> реальная кость
    missing_required: List[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"Тип рига: {self.rig_type}"]
        if self.rig_type == "rigify":
            lines.append("Rigify-риг: кости НЕ переименовываем, а сопоставляем (карта для Unity).")
        found = len(self.mapping)
        lines.append(f"\nСопоставлено слотов Humanoid: {found} из {len(CANON_ORDER)}")
        for slot in CANON_ORDER:
            if slot in self.mapping:
                lines.append(f"  ✓ {slot:14s} → {self.mapping[slot]}")
        if self.missing_required:
            lines.append("\nНе удалось сопоставить обязательные:")
            for s in self.missing_required:
                lines.append(f"  ✗ {s}")
        return "\n".join(lines)


def map_to_humanoid(bones: List[str]) -> HumanoidMap:
    rig_type = detect_rig_type(bones)
    defs = [b for b in bones if b.startswith("DEF-")]
    base_pool = defs if defs else bones
    # Отбрасываем управляющие/вспомогательные кости (в т.ч. DEF-…tweak и пр.).
    pool = [b for b in base_pool if not _is_control(b)]

    mapping: Dict[str, str] = {}

    # Конечности/кисти/стопы/плечи — по псевдонимам (без спины).
    for b in pool:
        canon = ALIAS_MAP.get(normalize(b))
        if canon and canon not in SPINE_SLOTS and canon not in mapping:
            mapping[canon] = b

    # Цепочка позвоночника — только чистые сегменты spine / spine.NNN.
    spine_bones = sorted(
        [b for b in pool if re.fullmatch(r"spine\d*", normalize(b))], key=_spine_index
    )
    if spine_bones:
        mapping["Hips"] = spine_bones[0]
        if len(spine_bones) >= 2:
            mapping["Head"] = spine_bones[-1]
        if len(spine_bones) >= 3:
            mapping["Neck"] = spine_bones[-2]
        middle = spine_bones[1:-2] if len(spine_bones) >= 3 else []
        for slot, bone in zip(["Spine", "Chest", "UpperChest"], middle):
            mapping[slot] = bone

    missing = [s for s in CANON_ORDER if s in REQUIRED and s not in mapping]
    return HumanoidMap(
        rig_type=rig_type,
        renaming_needed=(rig_type == "generic"),
        mapping=mapping,
        missing_required=missing,
    )
