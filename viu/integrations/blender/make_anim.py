"""Простые клипы в Blender (idle/wave/nod…) → Action на арматуре.

Не замена Cascadeur: грубый ключ в Blender, полировка потом в Cascadeur.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .export_shanya import build_export_command

_MARK_BEGIN = "<<<VIU_ANIM_JSON_BEGIN>>>"
_MARK_END = "<<<VIU_ANIM_JSON_END>>>"

ANIM_PRESETS = (
    "idle",
    "wave",
    "nod",
    "look_left",
    "look_right",
    "stretch",
)

# Имена костей: Mixamo / Blender / общий humanoid.
BONE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "hips": ("hips", "pelvis", "root", "hip", "mixamorig:hips", "bip001 pelvis"),
    "spine": ("spine", "spine1", "spine_01", "mixamorig:spine", "bip001 spine"),
    "chest": (
        "chest",
        "spine2",
        "spine3",
        "spine_02",
        "mixamorig:spine1",
        "mixamorig:spine2",
        "bip001 spine1",
    ),
    "neck": ("neck", "mixamorig:neck", "bip001 neck"),
    "head": ("head", "mixamorig:head", "bip001 head"),
    "shoulder_l": (
        "leftshoulder",
        "shoulder.l",
        "shoulder_l",
        "clavicle.l",
        "mixamorig:leftshoulder",
        "bip001 l clavicle",
    ),
    "upper_arm_l": (
        "leftarm",
        "upperarm.l",
        "upper_arm.l",
        "arm.l",
        "mixamorig:leftarm",
        "bip001 l upperarm",
    ),
    "forearm_l": (
        "leftforearm",
        "forearm.l",
        "lowerarm.l",
        "mixamorig:leftforearm",
        "bip001 l forearm",
    ),
    "hand_l": (
        "lefthand",
        "hand.l",
        "wrist.l",
        "mixamorig:lefthand",
        "bip001 l hand",
    ),
    "shoulder_r": (
        "rightshoulder",
        "shoulder.r",
        "shoulder_r",
        "clavicle.r",
        "mixamorig:rightshoulder",
        "bip001 r clavicle",
    ),
    "upper_arm_r": (
        "rightarm",
        "upperarm.r",
        "upper_arm.r",
        "arm.r",
        "mixamorig:rightarm",
        "bip001 r upperarm",
    ),
    "forearm_r": (
        "rightforearm",
        "forearm.r",
        "lowerarm.r",
        "mixamorig:rightforearm",
        "bip001 r forearm",
    ),
    "hand_r": (
        "righthand",
        "hand.r",
        "wrist.r",
        "mixamorig:righthand",
        "bip001 r hand",
    ),
}


def match_bone(bone_names: Sequence[str], *aliases: str) -> Optional[str]:
    """Найти кость по списку алиасов (точное имя без учёта регистра)."""
    by_low = {n.lower().replace(" ", ""): n for n in bone_names}
    for alias in aliases:
        key = alias.lower().replace(" ", "")
        if key in by_low:
            return by_low[key]
    # Частичное: alias в имени кости
    for alias in aliases:
        key = alias.lower().replace(" ", "").replace(":", "")
        for low, orig in by_low.items():
            compact = low.replace(":", "")
            if key and key in compact:
                return orig
    return None


def resolve_role_bones(bone_names: Sequence[str]) -> Dict[str, Optional[str]]:
    return {
        role: match_bone(bone_names, *aliases)
        for role, aliases in BONE_ALIASES.items()
    }


MAKE_ANIM_SCRIPT = f'''
import bpy, json, math, sys, traceback

def emit(payload):
    print("{_MARK_BEGIN}" + json.dumps(payload, ensure_ascii=False) + "{_MARK_END}")

BONE_ALIASES = {json.dumps(BONE_ALIASES, ensure_ascii=False)}

def match_bone(bone_names, *aliases):
    by_low = {{n.lower().replace(" ", ""): n for n in bone_names}}
    for alias in aliases:
        key = alias.lower().replace(" ", "")
        if key in by_low:
            return by_low[key]
    for alias in aliases:
        key = alias.lower().replace(" ", "").replace(":", "")
        for low, orig in by_low.items():
            if key and key in low.replace(":", ""):
                return orig
    return None

def pick_armature():
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE" and not getattr(o, "library", None)]
    if not arms:
        return None
    if len(arms) == 1:
        return arms[0]
    return max(arms, key=lambda a: len(a.data.bones))

def clear_pose(arm):
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)

def key_pose(arm, frame, bones):
    bpy.context.scene.frame_set(frame)
    for name in bones:
        pb = arm.pose.bones.get(name)
        if pb is None:
            continue
        pb.keyframe_insert(data_path="rotation_euler", frame=frame)
        pb.keyframe_insert(data_path="location", frame=frame)

try:
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError("Нужны args после --: preset [action_name] [out_blend]")
    args = argv[argv.index("--") + 1 :]
    preset = (args[0] if args else "idle").strip().lower()
    action_name = (args[1] if len(args) > 1 else f"viu_{{preset}}").strip() or f"viu_{{preset}}"
    out_blend = (args[2] if len(args) > 2 else "").strip()

    arm = pick_armature()
    if arm is None:
        raise RuntimeError("В сцене нет ARMATURE")

    names = [b.name for b in arm.data.bones]
    roles = {{role: match_bone(names, *aliases) for role, aliases in BONE_ALIASES.items()}}

    if arm.animation_data is None:
        arm.animation_data_create()
    action = bpy.data.actions.new(name=action_name)
    arm.animation_data.action = action

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    clear_pose(arm)

    used = []
    frames = 48
    fps = bpy.context.scene.render.fps or 24

    def set_rot(role, euler):
        name = roles.get(role)
        if not name:
            return
        pb = arm.pose.bones.get(name)
        if pb is None:
            return
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = euler
        used.append(name)

    if preset == "idle":
        frames = 48
        # лёгкое дыхание / покачивание
        for fr, amp in ((1, 0.0), (12, 1.0), (24, 0.0), (36, -1.0), (48, 0.0)):
            clear_pose(arm)
            a = 0.04 * amp
            set_rot("spine", (a, 0.0, 0.0))
            set_rot("chest", (a * 0.6, 0.0, 0.0))
            set_rot("head", (a * 0.4, 0.0, a * 0.3))
            key_pose(arm, fr, used or [n for n in roles.values() if n])
            used = list(dict.fromkeys(used))
    elif preset == "wave":
        frames = 36
        clear_pose(arm)
        key_pose(arm, 1, [n for n in roles.values() if n])
        clear_pose(arm)
        set_rot("shoulder_r", (0.0, 0.0, -0.4))
        set_rot("upper_arm_r", (0.0, 0.0, -1.6))
        set_rot("forearm_r", (0.0, -0.3, 0.0))
        key_pose(arm, 10, used)
        for fr, z in ((18, 0.5), (26, -0.5), (36, 0.0)):
            set_rot("forearm_r", (0.0, -0.3, z))
            set_rot("hand_r", (0.0, 0.0, z * 0.5))
            key_pose(arm, fr, used)
    elif preset == "nod":
        frames = 24
        clear_pose(arm)
        key_pose(arm, 1, [n for n in (roles.get("head"), roles.get("neck")) if n])
        set_rot("head", (0.35, 0.0, 0.0))
        set_rot("neck", (0.12, 0.0, 0.0))
        key_pose(arm, 10, used)
        clear_pose(arm)
        set_rot("head", (-0.05, 0.0, 0.0))
        key_pose(arm, 18, used)
        clear_pose(arm)
        key_pose(arm, 24, used)
    elif preset == "look_left":
        frames = 24
        clear_pose(arm)
        key_pose(arm, 1, [n for n in (roles.get("head"), roles.get("neck")) if n])
        set_rot("head", (0.0, 0.0, 0.55))
        set_rot("neck", (0.0, 0.0, 0.2))
        key_pose(arm, 12, used)
        clear_pose(arm)
        key_pose(arm, 24, used)
    elif preset == "look_right":
        frames = 24
        clear_pose(arm)
        key_pose(arm, 1, [n for n in (roles.get("head"), roles.get("neck")) if n])
        set_rot("head", (0.0, 0.0, -0.55))
        set_rot("neck", (0.0, 0.0, -0.2))
        key_pose(arm, 12, used)
        clear_pose(arm)
        key_pose(arm, 24, used)
    elif preset == "stretch":
        frames = 36
        clear_pose(arm)
        key_pose(arm, 1, [n for n in roles.values() if n])
        clear_pose(arm)
        set_rot("upper_arm_l", (0.0, 0.0, 1.5))
        set_rot("upper_arm_r", (0.0, 0.0, -1.5))
        set_rot("spine", (-0.15, 0.0, 0.0))
        set_rot("head", (-0.1, 0.0, 0.0))
        key_pose(arm, 18, used)
        clear_pose(arm)
        key_pose(arm, 36, used)
    else:
        raise RuntimeError(f"Неизвестный preset: {{preset}}. Доступны: idle,wave,nod,look_left,look_right,stretch")

    if not used:
        raise RuntimeError(
            "Не нашлись нужные кости для клипа. "
            f"Есть: {{names[:20]}}…"
        )

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = frames
    scene.frame_set(1)
    bpy.ops.object.mode_set(mode="OBJECT")

    saved = ""
    if out_blend:
        bpy.ops.wm.save_as_mainfile(filepath=out_blend)
        saved = out_blend

    emit({{
        "ok": True,
        "preset": preset,
        "action": action.name,
        "armature": arm.name,
        "frames": frames,
        "fps": fps,
        "bones_used": sorted(set(used)),
        "roles": {{k: v for k, v in roles.items() if v}},
        "saved_blend": saved,
    }})
except Exception as exc:
    emit({{
        "ok": False,
        "error": str(exc),
        "traceback": traceback.format_exc()[-2000:],
    }})
    raise SystemExit(2)
'''


def make_simple_anim(
    blend_file: str,
    *,
    preset: str = "idle",
    action_name: str = "",
    out_blend: str | None = None,
    blender_exe: str = "blender",
    timeout: float = 300.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[Path, Dict[str, Any]]:
    """Создать Action на арматуре в .blend; опционально сохранить копию."""
    blend = Path(blend_file).resolve()
    if not blend.is_file():
        raise FileNotFoundError(f"Blend не найден: {blend_file}")

    preset_n = (preset or "idle").strip().lower()
    if preset_n not in ANIM_PRESETS:
        raise ValueError(f"preset должен быть один из: {', '.join(ANIM_PRESETS)}")

    act = (action_name or f"viu_{preset_n}").strip()
    if out_blend:
        out = Path(out_blend).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        out = blend.with_name(f"{blend.stem}_viu_{preset_n}.blend")

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(MAKE_ANIM_SCRIPT)
        script_path = f.name

    try:
        cmd = [
            blender_exe,
            "--background",
            "--factory-startup",
            str(blend),
            "--python",
            script_path,
            "--python-exit-code",
            "2",
            "--",
            preset_n,
            act,
            str(out),
        ]
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0 and _MARK_BEGIN not in (proc.stdout or ""):
            raise RuntimeError(f"Blender exit {proc.returncode}.\n{combined.strip()[-2000:]}")
        # parse_export_output ищет другие маркеры — свой парсер
        start = (proc.stdout or combined).find(_MARK_BEGIN)
        end = (proc.stdout or combined).find(_MARK_END)
        if start == -1 or end == -1:
            raise RuntimeError(f"Маркер анимации не найден.\n{combined.strip()[-1500:]}")
        meta = json.loads((proc.stdout or combined)[start + len(_MARK_BEGIN) : end])
        if not meta.get("ok"):
            raise RuntimeError(meta.get("error") or "make_anim failed")
        if not out.is_file():
            # Blender мог сохранить, но путь другой — всё равно вернём out если meta ok
            saved = (meta.get("saved_blend") or "").strip()
            if saved and Path(saved).is_file():
                out = Path(saved)
            else:
                raise RuntimeError(f"Blend с анимацией не сохранён: {out}")
        return out, meta
    finally:
        try:
            Path(script_path).unlink()
        except OSError:
            pass
