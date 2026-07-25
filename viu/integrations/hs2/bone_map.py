"""Соответствие костей HS2 (cf_J_*) → Mixamo humanoid."""

from __future__ import annotations

from typing import Dict

# Расширяется при реальных дампах; ключ — суффикс после cf_J_ (без префикса).
_HS2_SUFFIX_TO_MIXAMO: Dict[str, str] = {
    "Hips": "Hips",
    "Spine01": "Spine",
    "Spine02": "Spine1",
    "Spine03": "Spine2",
    "Neck": "Neck",
    "Head": "Head",
    "Shoulder_L": "LeftShoulder",
    "Shoulder_R": "RightShoulder",
    "UpperArm_L": "LeftArm",
    "UpperArm_R": "RightArm",
    "LowerArm_L": "LeftForeArm",
    "LowerArm_R": "RightForeArm",
    "Hand_L": "LeftHand",
    "Hand_R": "RightHand",
    "UpperLeg_L": "LeftUpLeg",
    "UpperLeg_R": "RightUpLeg",
    "LowerLeg_L": "LeftLeg",
    "LowerLeg_R": "RightLeg",
    "Foot_L": "LeftFoot",
    "Foot_R": "RightFoot",
    "Toes_L": "LeftToeBase",
    "Toes_R": "RightToeBase",
    # альтернативные имена в некоторых экспортёрах
    "L_Shoulder": "LeftShoulder",
    "R_Shoulder": "RightShoulder",
    "L_UpperArm": "LeftArm",
    "R_UpperArm": "RightArm",
    "L_LowerArm": "LeftForeArm",
    "R_LowerArm": "RightForeArm",
    "L_Hand": "LeftHand",
    "R_Hand": "RightHand",
    "L_UpperLeg": "LeftUpLeg",
    "R_UpperLeg": "RightUpLeg",
    "L_LowerLeg": "LeftLeg",
    "R_LowerLeg": "RightLeg",
    "L_Foot": "LeftFoot",
    "R_Foot": "RightFoot",
    "L_Toes": "LeftToeBase",
    "R_Toes": "RightToeBase",
}


def hs2_bone_to_mixamo(bone_name: str) -> str | None:
    """Имя кости из FBX/clip path → Mixamo bone или None."""
    name = bone_name.strip()
    if not name:
        return None
    if name in _HS2_SUFFIX_TO_MIXAMO:
        return _HS2_SUFFIX_TO_MIXAMO[name]
    for prefix in ("cf_J_", "cf_j_", "j_", "J_"):
        if name.startswith(prefix):
            suffix = name[len(prefix):]
            if suffix in _HS2_SUFFIX_TO_MIXAMO:
                return _HS2_SUFFIX_TO_MIXAMO[suffix]
    # последний сегмент пути Unity (Root/Hips/cf_J_Hips)
    tail = name.split("/")[-1]
    return hs2_bone_to_mixamo(tail)


def bone_map_dict() -> Dict[str, str]:
    """Полная карта cf_J_* → Mixamo для Blender JSON."""
    out: Dict[str, str] = {}
    for suffix, mixamo in _HS2_SUFFIX_TO_MIXAMO.items():
        out[f"cf_J_{suffix}"] = mixamo
        out[suffix] = mixamo
    return out
