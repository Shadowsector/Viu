"""Определение единого стандартного скелета (совместим с Unity Humanoid).

Названия костей — на латинице в стиле Unity («Hips», «LeftUpperArm» и т.д.),
чтобы модель без переделок подхватывалась Unity. Для каждой кости хранится
набор «псевдонимов» — как её называют в популярных ригах (Mixamo, Rigify,
разные L/R-конвенции, транслитерация с русского), чтобы Вью узнавала кость,
как бы она ни была названа в модели.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

# Префиксы, которые встречаются в названиях костей и не несут смысла.
_PREFIXES = (
    "mixamorig:", "mixamorig1:", "mixamorig::", "rig:",
    "def-", "def_", "org-", "org_", "mch-", "mch_",
    "ctrl-", "ctrl_", "tgt-", "tgt_", "b_",
)


def normalize(name: str) -> str:
    """Приводит имя кости к каноническому виду для сравнения.

    lowercase, срезает известные префиксы, убирает все не-буквенно-цифровые
    символы (пробелы, точки, подчёркивания, двоеточия).
    """
    s = (name or "").strip().lower()
    for p in _PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    # Встроенный ORG в метаригах: L_ORG_thigh, ORG_upper_arm_L
    s = re.sub(r"_?org_?", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return re.sub(r"[^a-z0-9]", "", s)


# Маркеры стороны в псевдонимах (нормализованные).
_SIDE_MARKERS = {"L": ("left", "l"), "R": ("right", "r")}


def _gen_aliases(synonyms: List[str], side: Optional[str]) -> Set[str]:
    """Из синонимов и стороны собирает набор нормализованных псевдонимов."""
    out: Set[str] = set()
    for syn in synonyms:
        s = normalize(syn)
        if not s:
            continue
        if side is None:
            out.add(s)
        else:
            for m in _SIDE_MARKERS[side]:
                out.add(m + s)  # напр. leftupperarm, lupperarm
                out.add(s + m)  # напр. upperarml, upperarmleft
    return out


@dataclass
class Bone:
    name: str            # каноническое имя (оно же для Unity)
    required: bool       # обязательна ли для Unity Humanoid
    parent: Optional[str]
    aliases: Set[str] = field(default_factory=set)


# Центральные кости (без стороны).
_CORE = [
    # name, required, parent, synonyms
    ("Hips", True, None, ["hips", "hip", "pelvis", "root", "cog", "taz", "torso"]),
    ("Spine", True, "Hips", ["spine", "spine0", "spine01", "lowerback", "pozvon", "pozvonochnik", "abdomenlower", "abdomenupper"]),
    ("Chest", False, "Spine", ["chest", "spine1", "spine001", "upperback", "grud", "chestlower", "chestupper"]),
    ("UpperChest", False, "Chest", ["upperchest", "spine2", "spine002"]),
    ("Neck", False, "UpperChest", ["neck", "sheya", "sheia", "neck01", "neck02"]),
    ("Head", True, "Neck", ["head", "golova"]),
]

# Парные кости (левая/правая). base, required, parent_base, synonyms.
# parent_base из числа центральных не получает сторону.
_CENTRAL_NAMES = {"Hips", "Spine", "Chest", "UpperChest", "Neck", "Head"}
_SIDED = [
    ("Shoulder", False, "UpperChest", ["shoulder", "clavicle", "collar", "klyuchica", "plecho"]),
    ("UpperArm", True, "Shoulder", ["upperarm", "arm", "ruka", "oberarm"]),
    ("LowerArm", True, "UpperArm", ["lowerarm", "forearm", "predplechie"]),
    ("Hand", True, "LowerArm", ["hand", "wrist", "kist", "ladon"]),
    ("UpperLeg", True, "Hips", ["upperleg", "upleg", "thigh", "bedro"]),
    ("LowerLeg", True, "UpperLeg", ["lowerleg", "leg", "shin", "calf", "golen", "orgshin"]),
    ("Foot", True, "LowerLeg", ["foot", "ankle", "stopa"]),
    ("Toes", False, "Foot", ["toe", "toes", "toebase", "paltsy"]),
]


def _build_bones() -> List[Bone]:
    bones: List[Bone] = []
    for name, required, parent, syn in _CORE:
        bones.append(Bone(name=name, required=required, parent=parent, aliases=_gen_aliases(syn, None) | {normalize(name)}))
    for base, required, parent_base, syn in _SIDED:
        for side, prefix in (("L", "Left"), ("R", "Right")):
            name = f"{prefix}{base}"
            parent = parent_base if parent_base in _CENTRAL_NAMES else f"{prefix}{parent_base}"
            aliases = _gen_aliases(syn, side) | {normalize(name)}
            bones.append(Bone(name=name, required=required, parent=parent, aliases=aliases))
    return bones


BONES: List[Bone] = _build_bones()
CANON_ORDER: List[str] = [b.name for b in BONES]
REQUIRED: Set[str] = {b.name for b in BONES if b.required}


def _build_alias_map() -> Dict[str, str]:
    """Нормализованный псевдоним -> каноническое имя (первое совпадение выигрывает)."""
    amap: Dict[str, str] = {}
    for b in BONES:
        for a in b.aliases:
            amap.setdefault(a, b.name)
    return amap


ALIAS_MAP: Dict[str, str] = _build_alias_map()

# Быстрый доступ к кости по имени.
BONE_BY_NAME: Dict[str, Bone] = {b.name: b for b in BONES}


def standard_summary() -> str:
    """Человекочитаемое описание стандартного скелета."""
    lines = ["Стандартный скелет (Unity Humanoid). ✱ — обязательные:"]
    for b in BONES:
        mark = "✱" if b.required else " "
        parent = f" ← {b.parent}" if b.parent else ""
        lines.append(f"  {mark} {b.name}{parent}")
    return "\n".join(lines)
