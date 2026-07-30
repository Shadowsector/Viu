"""Библиотека базовых поз + blend между ними (Blender-first).

Поверх make_anim: Вью мыслит «старт → финиш», не dual-mocap.
Cascadeur — optional polish после export.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...config import Config
from .make_anim import (
    ANIM_PRESETS,
    MOTION_PRESETS,
    POSE_HOLD_PRESETS,
    make_simple_anim,
)

_CHAR_ALIASES = {
    "shanya": ("shanya", "шаня", "шанька", "shania"),
    "viu": ("viu", "вью", "вьюшка"),
}


def list_poses() -> Dict[str, Tuple[str, ...]]:
    return {
        "holds": POSE_HOLD_PRESETS,
        "motion": MOTION_PRESETS,
        "all": ANIM_PRESETS,
    }


def normalize_character(name: str) -> str:
    low = (name or "").strip().lower()
    for canon, al in _CHAR_ALIASES.items():
        if low in al or any(a in low for a in al):
            return canon
    return low or "shanya"


def resolve_character_blend(
    config: Config, character: str = "shanya", explicit: str = ""
) -> Optional[Path]:
    """Найти .blend рига персонажа (Шаня и т.п.)."""
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return p.resolve()
    char = normalize_character(character)
    roots: List[Path] = []
    try:
        lib = Path(config.library_root or "")
        if lib.is_dir():
            roots.extend(
                [
                    lib / "Lab" / "Models" / "CascadeurReady",
                    lib / "Lab" / "Models",
                    lib / "Lab" / "Anims" / "BlenderOut",
                    lib / "Blender",
                ]
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        roots.append(Path(config.data_dir) / "blender")
    except Exception:  # noqa: BLE001
        pass

    needles = {
        "shanya": ("shanya", "шаня", "shania"),
        "viu": ("viu", "вью"),
    }.get(char, (char,))

    candidates: List[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*.blend"):
            name = p.name.lower()
            if any(n in name for n in needles) and "viu_" not in name:
                candidates.append(p)
    if not candidates:
        return None
    # предпочесть *rig* / короче путь
    candidates.sort(
        key=lambda p: (
            0 if "rig" in p.stem.lower() else 1,
            0 if "canon" in p.stem.lower() else 1,
            len(str(p)),
        )
    )
    return candidates[0].resolve()


def pose_character(
    config: Config,
    character: str,
    pose: str,
    *,
    blend_file: str = "",
    action_name: str = "",
    out_blend: str | None = None,
    blender_exe: str = "blender",
) -> Tuple[Path, Dict[str, Any]]:
    """Поставить персонажа в позу-hold / motion-preset (один Action)."""
    pose_n = (pose or "").strip().lower()
    if pose_n not in ANIM_PRESETS:
        raise ValueError(f"pose: {', '.join(ANIM_PRESETS)}")
    src = resolve_character_blend(config, character, explicit=blend_file)
    if src is None:
        raise FileNotFoundError(
            f"Не нашла .blend для «{character}». "
            "Укажи blend_file= или положи *Shanya*.blend в Lab/Models/."
        )
    return make_simple_anim(
        str(src),
        preset=pose_n,
        action_name=action_name or f"viu_{normalize_character(character)}_{pose_n}",
        out_blend=out_blend,
        blender_exe=blender_exe,
    )


def blend_to(
    config: Config,
    character: str,
    to_pose: str,
    *,
    from_pose: str = "stand",
    frames: int = 12,
    blend_file: str = "",
    action_name: str = "",
    out_blend: str | None = None,
    blender_exe: str = "blender",
) -> Tuple[Path, Dict[str, Any]]:
    """Переход from_pose → to_pose за N кадров (грубый ключ в Blender)."""
    to_n = (to_pose or "").strip().lower()
    from_n = (from_pose or "stand").strip().lower()
    if to_n not in ANIM_PRESETS:
        raise ValueError(f"to_pose: {', '.join(ANIM_PRESETS)}")
    if from_n not in ANIM_PRESETS:
        raise ValueError(f"from_pose: {', '.join(ANIM_PRESETS)}")
    src = resolve_character_blend(config, character, explicit=blend_file)
    if src is None:
        raise FileNotFoundError(
            f"Не нашла .blend для «{character}». Укажи blend_file=."
        )
    char = normalize_character(character)
    act = action_name or f"viu_{char}_{from_n}_to_{to_n}"
    return make_simple_anim(
        str(src),
        preset=to_n,
        from_preset=from_n,
        blend_frames=max(4, int(frames)),
        action_name=act,
        out_blend=out_blend,
        blender_exe=blender_exe,
    )


def format_pose_help() -> str:
    holds = ", ".join(POSE_HOLD_PRESETS)
    motion = ", ".join(MOTION_PRESETS)
    return (
        "Blender-first позы (канон Humanoid):\n"
        f"holds: {holds}\n"
        f"motion: {motion}\n"
        "Tools: blender_pose_character · blender_blend_to · blender_make_anim\n"
        "Дальше: blender_export_cascadeur_anim / blender_anim_to_cascadeur (polish)."
    )
