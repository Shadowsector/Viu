"""Спеки NSFW-прикрутки: 6 aim-сокетов + penis-кости + хелперы вагины.

Чистый Python (без bpy) — тесты и документация. Blender-операторы живут в
`_creature_blender_shared.py` и читают те же константы через копию
`viu_nsfw_attach.py` рядом с аддоном Studio.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# --- Bone aliases (AccuRIG / Mixamo / Unity Humanoid / Blender) ---

HIPS_ALIASES: Tuple[str, ...] = (
    "Hips",
    "hips",
    "Pelvis",
    "pelvis",
    "Hip",
    "hip",
    "mixamorig:Hips",
    "mixamorig_Hips",
    "Root_M",
    "root_m",
    "DEF-hips",
    "DEF_hips",
)

HEAD_ALIASES: Tuple[str, ...] = (
    "Head",
    "head",
    "mixamorig:Head",
    "mixamorig_Head",
    "Head_M",
    "head_m",
    "DEF-head",
    "DEF_head",
)

JAW_ALIASES: Tuple[str, ...] = (
    "Jaw",
    "jaw",
    "LowerJaw",
    "lowerjaw",
    "Jaw_M",
    "DEF-jaw",
)

CHEST_ALIASES: Tuple[str, ...] = (
    "Chest",
    "chest",
    "Spine2",
    "spine2",
    "spine_02",
    "Spine_02",
    "UpperChest",
    "upperchest",
    "Spine1",
    "spine1",
    "spine_01",
    "mixamorig:Spine2",
    "mixamorig:Spine1",
    "mixamorig_Spine2",
    "Chest_M",
    "DEF-spine.002",
    "DEF-chest",
)

HAND_L_ALIASES: Tuple[str, ...] = (
    "LeftHand",
    "lefthand",
    "Hand.L",
    "hand.L",
    "hand_l",
    "Hand_L",
    "Wrist_L",
    "wrist_l",
    "mixamorig:LeftHand",
    "mixamorig_LeftHand",
    "DEF-hand.L",
)

HAND_R_ALIASES: Tuple[str, ...] = (
    "RightHand",
    "righthand",
    "Hand.R",
    "hand.R",
    "hand_r",
    "Hand_R",
    "Wrist_R",
    "wrist_r",
    "mixamorig:RightHand",
    "mixamorig_RightHand",
    "DEF-hand.R",
)

PENIS_BONE_NAMES: Tuple[str, ...] = ("Penis_01", "Penis_02", "Penis_03")
VAGINA_HELPER_NAMES: Tuple[str, ...] = ("Vagina_L", "Vagina_R")

# Rest hide: pose scale ≈ 0 (не материал).
PENIS_HIDE_SCALE = 0.001

# Aim sockets: id → parent aliases + local offset (bone space, meters) + display size.
# Offset — стартовая раскладка; Ден двигает Empty в Studio.
SOCKET_SPECS: Tuple[Dict[str, object], ...] = (
    {
        "id": "socket_oral",
        "aliases": JAW_ALIASES + HEAD_ALIASES,
        "prefer": JAW_ALIASES,
        "offset": (0.0, -0.04, -0.02),
        "size": 0.025,
        "label_ru": "рот",
    },
    {
        "id": "socket_vaginal",
        "aliases": HIPS_ALIASES,
        "prefer": (),
        "offset": (0.0, -0.06, -0.03),
        "size": 0.03,
        "label_ru": "вагина",
    },
    {
        "id": "socket_anal",
        "aliases": HIPS_ALIASES,
        "prefer": (),
        "offset": (0.0, 0.05, -0.04),
        "size": 0.028,
        "label_ru": "анус",
    },
    {
        "id": "socket_hand_l",
        "aliases": HAND_L_ALIASES,
        "prefer": (),
        "offset": (0.0, -0.02, 0.0),
        "size": 0.022,
        "label_ru": "левая ладонь",
    },
    {
        "id": "socket_hand_r",
        "aliases": HAND_R_ALIASES,
        "prefer": (),
        "offset": (0.0, -0.02, 0.0),
        "size": 0.022,
        "label_ru": "правая ладонь",
    },
    {
        "id": "socket_cleavage",
        "aliases": CHEST_ALIASES,
        "prefer": (),
        "offset": (0.0, -0.05, 0.02),
        "size": 0.028,
        "label_ru": "меж грудей",
    },
)


def normalize_bone_key(name: str) -> str:
    s = (name or "").strip()
    low = s.lower()
    for prefix in ("mixamorig:", "mixamorig_", "rig:", "rig_"):
        if low.startswith(prefix):
            s = s[len(prefix) :]
            low = s.lower()
            break
    s = s.replace(":", "_").replace(".", "_").replace("-", "_")
    return s.lower()


def match_bone_name(
    bone_names: Iterable[str],
    aliases: Sequence[str],
    *,
    prefer: Sequence[str] = (),
) -> Optional[str]:
    """Вернуть реальное имя кости из арматуры по списку алиасов."""
    names = [n for n in bone_names if n]
    if not names:
        return None
    by_norm = {normalize_bone_key(n): n for n in names}

    def _hit(alias_list: Sequence[str]) -> Optional[str]:
        for alias in alias_list:
            key = normalize_bone_key(alias)
            if key in by_norm:
                return by_norm[key]
        # suffix / contains for DEF-hand.L style already normalized
        for alias in alias_list:
            key = normalize_bone_key(alias)
            for nk, original in by_norm.items():
                if nk.endswith("_" + key) or nk.endswith(key):
                    return original
        return None

    if prefer:
        hit = _hit(prefer)
        if hit:
            return hit
    return _hit(aliases)


def list_socket_ids() -> List[str]:
    return [str(s["id"]) for s in SOCKET_SPECS]


def socket_parent_plan(bone_names: Sequence[str]) -> Dict[str, Optional[str]]:
    """Для тестов/отчёта: socket_id → matched bone name (или None)."""
    out: Dict[str, Optional[str]] = {}
    for spec in SOCKET_SPECS:
        sid = str(spec["id"])
        aliases = tuple(spec.get("aliases") or ())  # type: ignore[arg-type]
        prefer = tuple(spec.get("prefer") or ())  # type: ignore[arg-type]
        out[sid] = match_bone_name(bone_names, aliases, prefer=prefer)
    return out
