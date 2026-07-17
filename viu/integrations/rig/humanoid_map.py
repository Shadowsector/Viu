"""Сопоставление сложного рига с Unity Humanoid БЕЗ переименования костей.

Реальные модели часто на Rigify (кости DEF-/ORG-/MCH-/tweak/WGT-…) или
метаригах (ORG_upper_arm_L, L_ORG_thigh). Такие риги переименовывать нельзя —
они сломаются. Правильный путь: не трогая имена, построить **карту соответствия**
«слот Unity Humanoid → реальная кость». Финально карта подтверждается в
настройке Avatar внутри Unity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .standard import ALIAS_MAP, CANON_ORDER, REQUIRED, normalize

SPINE_SLOTS = ["Hips", "Spine", "Chest", "UpperChest", "Neck", "Head"]

# Куски имён, характерные для управляющих (не деформирующих) костей.
_CONTROL_SUBSTR = (
    "_ik", "_fk", "tweak", "_master", "_drv", "pole", "target",
    "parent", "roll", "widget", "heel", "_swing", "_spin",
    "_ctl", "_mch", "blend",
)
_CONTROL_PREFIX = ("WGT-", "MCH-", "MCH_", "VIS_", "VIS-")

# Именованные сегменты позвоночника в метаригах (Fortnite/RedEyes и т.п.).
_NAMED_SPINE: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Hips", ("pelvis", "hips", "root", "torso")),
    ("Spine", ("abdomenlower", "abdomenupper", "spine")),
    ("Chest", ("chestlower", "chestupper", "chest")),
    ("UpperChest", ("upperchest", "spine2")),
    ("Neck", ("neck01", "neck02", "neck")),
    ("Head", ("head",)),
)


def detect_rig_type(bones: List[str]) -> str:
    has_def = any(b.startswith("DEF-") for b in bones)
    has_mch = any(b.startswith("MCH-") for b in bones)
    if has_def and has_mch:
        return "rigify"
    if any(b.lower().startswith("mixamorig") for b in bones):
        return "mixamo"
    has_org = any(re.search(r"(^|[_.-])org[_-]", b, re.I) for b in bones)
    ik_controls = sum(1 for b in bones if re.search(r"IK_BLEND|_CTL$|_MCH$", b))
    if has_org or (ik_controls >= 4 and len(bones) > 120):
        return "advanced"
    return "generic"


def is_complex_rig(bones: List[str]) -> bool:
    """True, если риг нельзя безопасно переименовывать — только карта для Unity."""
    rig_type = detect_rig_type(bones)
    if rig_type in ("rigify", "advanced"):
        return True
    return any(b.startswith("DEF-") for b in bones)


def _is_control(name: str) -> bool:
    if name.startswith(_CONTROL_PREFIX):
        return True
    low = name.lower()
    if any(s in low for s in _CONTROL_SUBSTR):
        return True
    # IK-контроллеры колена/локтя, не деформирующие кости.
    if re.fullmatch(r"[lr]_?(knee|elbow)", normalize(name)):
        return True
    return False


def _spine_index(name: str) -> int:
    m = re.search(r"(\d+)$", normalize(name))
    return int(m.group(1)) if m else 0


def _map_named_spine(pool: List[str], mapping: Dict[str, str]) -> None:
    """Дополняет карту позвоночника по типичным именам метаригов."""
    by_norm = {normalize(b): b for b in pool}
    for slot, keys in _NAMED_SPINE:
        if slot in mapping:
            continue
        for key in keys:
            if key in by_norm:
                mapping[slot] = by_norm[key]
                break


@dataclass
class HumanoidMap:
    rig_type: str
    renaming_needed: bool
    mapping: Dict[str, str] = field(default_factory=dict)  # слот Unity -> реальная кость
    missing_required: List[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"Тип рига: {self.rig_type}"]
        if self.rig_type in ("rigify", "advanced"):
            lines.append(
                "Сложный риг: кости НЕ переименовываем, а сопоставляем (карта для Unity)."
            )
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

    # Конечности/кисти/стопы/плечи — по псевдонимам (без позвоночника).
    for b in pool:
        canon = ALIAS_MAP.get(normalize(b))
        if canon and canon not in SPINE_SLOTS and canon not in mapping:
            mapping[canon] = b

    # Цепочка позвоночника — сегменты spine / spine.NNN (Rigify).
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

    _map_named_spine(pool, mapping)

    missing = [s for s in CANON_ORDER if s in REQUIRED and s not in mapping]
    return HumanoidMap(
        rig_type=rig_type,
        renaming_needed=not is_complex_rig(bones),
        mapping=mapping,
        missing_required=missing,
    )
