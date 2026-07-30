"""Простые клипы в Blender: позы-hold + motion + blend_to.

Не замена Cascadeur: грубый ключ в Blender, полировка потом в Cascadeur.
Кости — Unity Humanoid / Mixamo aliases (ноги включены).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

POSE_HOLD_PRESETS = (
    "stand",
    "sit",
    "kneel",
    "all_fours",
    "lie",
)

MOTION_PRESETS = (
    "idle",
    "wave",
    "nod",
    "look_left",
    "look_right",
    "stretch",
)

ANIM_PRESETS = POSE_HOLD_PRESETS + MOTION_PRESETS

# Роли → алиасы (Unity Humanoid + Mixamo + L/R).
BONE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "hips": ("Hips", "hips", "pelvis", "root", "hip", "mixamorig:Hips", "Bip001 Pelvis"),
    "spine": ("Spine", "spine", "spine1", "spine_01", "mixamorig:Spine", "Bip001 Spine"),
    "chest": (
        "Chest",
        "UpperChest",
        "chest",
        "spine2",
        "spine3",
        "Spine1",
        "Spine2",
        "mixamorig:Spine1",
        "mixamorig:Spine2",
        "Bip001 Spine1",
    ),
    "neck": ("Neck", "neck", "mixamorig:Neck", "Bip001 Neck"),
    "head": ("Head", "head", "mixamorig:Head", "Bip001 Head"),
    "shoulder_l": (
        "LeftShoulder",
        "leftshoulder",
        "shoulder.L",
        "shoulder_l",
        "clavicle.L",
        "mixamorig:LeftShoulder",
        "Bip001 L Clavicle",
    ),
    "upper_arm_l": (
        "LeftUpperArm",
        "leftarm",
        "upperarm.L",
        "upper_arm.L",
        "arm.L",
        "mixamorig:LeftArm",
        "Bip001 L UpperArm",
    ),
    "forearm_l": (
        "LeftLowerArm",
        "leftforearm",
        "forearm.L",
        "lowerarm.L",
        "mixamorig:LeftForeArm",
        "Bip001 L Forearm",
    ),
    "hand_l": (
        "LeftHand",
        "lefthand",
        "hand.L",
        "wrist.L",
        "mixamorig:LeftHand",
        "Bip001 L Hand",
    ),
    "shoulder_r": (
        "RightShoulder",
        "rightshoulder",
        "shoulder.R",
        "shoulder_r",
        "clavicle.R",
        "mixamorig:RightShoulder",
        "Bip001 R Clavicle",
    ),
    "upper_arm_r": (
        "RightUpperArm",
        "rightarm",
        "upperarm.R",
        "upper_arm.R",
        "arm.R",
        "mixamorig:RightArm",
        "Bip001 R UpperArm",
    ),
    "forearm_r": (
        "RightLowerArm",
        "rightforearm",
        "forearm.R",
        "lowerarm.R",
        "mixamorig:RightForeArm",
        "Bip001 R Forearm",
    ),
    "hand_r": (
        "RightHand",
        "righthand",
        "hand.R",
        "wrist.R",
        "mixamorig:RightHand",
        "Bip001 R Hand",
    ),
    "thigh_l": (
        "LeftUpperLeg",
        "leftupleg",
        "thigh.L",
        "upperleg.L",
        "upleg.L",
        "mixamorig:LeftUpLeg",
        "Bip001 L Thigh",
    ),
    "shin_l": (
        "LeftLowerLeg",
        "leftleg",
        "shin.L",
        "lowerleg.L",
        "calf.L",
        "mixamorig:LeftLeg",
        "Bip001 L Calf",
    ),
    "foot_l": (
        "LeftFoot",
        "leftfoot",
        "foot.L",
        "ankle.L",
        "mixamorig:LeftFoot",
        "Bip001 L Foot",
    ),
    "thigh_r": (
        "RightUpperLeg",
        "rightupleg",
        "thigh.R",
        "upperleg.R",
        "upleg.R",
        "mixamorig:RightUpLeg",
        "Bip001 R Thigh",
    ),
    "shin_r": (
        "RightLowerLeg",
        "rightleg",
        "shin.R",
        "lowerleg.R",
        "calf.R",
        "mixamorig:RightLeg",
        "Bip001 R Calf",
    ),
    "foot_r": (
        "RightFoot",
        "rightfoot",
        "foot.R",
        "ankle.R",
        "mixamorig:RightFoot",
        "Bip001 R Foot",
    ),
}


def match_bone(bone_names: Sequence[str], *aliases: str) -> Optional[str]:
    """Найти кость по списку алиасов (точное имя без учёта регистра)."""
    by_low = {n.lower().replace(" ", ""): n for n in bone_names}
    for alias in aliases:
        key = alias.lower().replace(" ", "")
        if key in by_low:
            return by_low[key]
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


# Позы-hold: role → Euler XYZ (радианы), грубо под Humanoid Y-up / Z-forward.
# Не анатомия — стартовая библиотека для blend_to.
_POSE_HOLD_EULERS: Dict[str, Dict[str, Tuple[float, float, float]]] = {
    "stand": {},
    "sit": {
        "thigh_l": (1.1, 0.0, 0.0),
        "thigh_r": (1.1, 0.0, 0.0),
        "shin_l": (1.2, 0.0, 0.0),
        "shin_r": (1.2, 0.0, 0.0),
        "spine": (0.15, 0.0, 0.0),
        "chest": (0.05, 0.0, 0.0),
    },
    "kneel": {
        "thigh_l": (1.4, 0.0, 0.15),
        "thigh_r": (1.4, 0.0, -0.15),
        "shin_l": (2.0, 0.0, 0.0),
        "shin_r": (2.0, 0.0, 0.0),
        "spine": (0.1, 0.0, 0.0),
        "foot_l": (-0.4, 0.0, 0.0),
        "foot_r": (-0.4, 0.0, 0.0),
    },
    "all_fours": {
        "spine": (0.9, 0.0, 0.0),
        "chest": (0.35, 0.0, 0.0),
        "neck": (-0.4, 0.0, 0.0),
        "head": (-0.2, 0.0, 0.0),
        "thigh_l": (1.3, 0.0, 0.2),
        "thigh_r": (1.3, 0.0, -0.2),
        "shin_l": (1.0, 0.0, 0.0),
        "shin_r": (1.0, 0.0, 0.0),
        "upper_arm_l": (1.2, 0.0, 0.5),
        "upper_arm_r": (1.2, 0.0, -0.5),
        "forearm_l": (0.4, 0.0, 0.0),
        "forearm_r": (0.4, 0.0, 0.0),
    },
    "lie": {
        "spine": (1.4, 0.0, 0.0),
        "chest": (0.2, 0.0, 0.0),
        "thigh_l": (0.3, 0.0, 0.25),
        "thigh_r": (0.3, 0.0, -0.25),
        "shin_l": (0.4, 0.0, 0.0),
        "shin_r": (0.4, 0.0, 0.0),
        "upper_arm_l": (0.5, 0.0, 0.8),
        "upper_arm_r": (0.5, 0.0, -0.8),
    },
}


_MARK_BEGIN = "<<<VIU_ANIM_JSON_BEGIN>>>"
_MARK_END = "<<<VIU_ANIM_JSON_END>>>"

MAKE_ANIM_SCRIPT = f'''
import bpy, json, math, sys, traceback

def emit(payload):
    print("{_MARK_BEGIN}" + json.dumps(payload, ensure_ascii=False) + "{_MARK_END}")

BONE_ALIASES = {json.dumps(BONE_ALIASES, ensure_ascii=False)}
POSE_HOLDS = {json.dumps(_POSE_HOLD_EULERS, ensure_ascii=False)}
POSE_HOLD_NAMES = {json.dumps(list(POSE_HOLD_PRESETS), ensure_ascii=False)}
MOTION_NAMES = {json.dumps(list(MOTION_PRESETS), ensure_ascii=False)}

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
        raise RuntimeError("Нужны args после --: preset [action] [out] [from_preset] [blend_frames]")
    args = argv[argv.index("--") + 1 :]
    preset = (args[0] if args else "idle").strip().lower()
    action_name = (args[1] if len(args) > 1 else f"viu_{{preset}}").strip() or f"viu_{{preset}}"
    out_blend = (args[2] if len(args) > 2 else "").strip()
    from_preset = (args[3] if len(args) > 3 else "").strip().lower()
    try:
        blend_frames = int(args[4]) if len(args) > 4 and str(args[4]).strip() else 0
    except ValueError:
        blend_frames = 0

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
    mode = "motion"

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

    def apply_hold(hold_name):
        clear_pose(arm)
        for role, euler in (POSE_HOLDS.get(hold_name) or {{}}).items():
            set_rot(role, tuple(euler))
        return [n for n in roles.values() if n]

    def bake_hold(hold_name, frame):
        bones = apply_hold(hold_name)
        key_pose(arm, frame, bones or used)
        return bones

    # --- blend_to: from_preset → preset ---
    if from_preset:
        if from_preset not in POSE_HOLD_NAMES and from_preset not in MOTION_NAMES:
            raise RuntimeError(f"from_preset неизвестен: {{from_preset}}")
        if preset not in POSE_HOLD_NAMES and preset not in MOTION_NAMES:
            raise RuntimeError(f"preset неизвестен: {{preset}}")
        mode = "blend"
        frames = max(4, int(blend_frames) or 12)
        # from
        if from_preset in POSE_HOLD_NAMES:
            bake_hold(from_preset, 1)
        else:
            clear_pose(arm)
            key_pose(arm, 1, [n for n in roles.values() if n])
        used = list(dict.fromkeys(used))
        # to
        if preset in POSE_HOLD_NAMES:
            bake_hold(preset, frames)
        else:
            # motion target: roughly mid-pose of simple clips
            clear_pose(arm)
            if preset == "wave":
                set_rot("shoulder_r", (0.0, 0.0, -0.4))
                set_rot("upper_arm_r", (0.0, 0.0, -1.6))
                set_rot("forearm_r", (0.0, -0.3, 0.0))
            elif preset == "nod":
                set_rot("head", (0.35, 0.0, 0.0))
                set_rot("neck", (0.12, 0.0, 0.0))
            elif preset in ("look_left",):
                set_rot("head", (0.0, 0.0, 0.55))
                set_rot("neck", (0.0, 0.0, 0.2))
            elif preset == "look_right":
                set_rot("head", (0.0, 0.0, -0.55))
                set_rot("neck", (0.0, 0.0, -0.2))
            elif preset == "stretch":
                set_rot("upper_arm_l", (0.0, 0.0, 1.5))
                set_rot("upper_arm_r", (0.0, 0.0, -1.5))
                set_rot("spine", (-0.15, 0.0, 0.0))
            key_pose(arm, frames, used or [n for n in roles.values() if n])
        used = list(dict.fromkeys(used))
    elif preset in POSE_HOLD_NAMES:
        mode = "hold"
        frames = max(8, int(blend_frames) or 24)
        bake_hold(preset, 1)
        bake_hold(preset, frames)
        used = list(dict.fromkeys(used))
    elif preset == "idle":
        frames = 48
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
        raise RuntimeError(
            f"Неизвестный preset: {{preset}}. "
            f"holds={{POSE_HOLD_NAMES}}, motion={{MOTION_NAMES}}"
        )

    if not used and preset not in ("stand",):
        # stand = rest pose — ключи на все найденные кости
        used = [n for n in roles.values() if n]
        if used:
            clear_pose(arm)
            key_pose(arm, 1, used)
            key_pose(arm, frames, used)

    if not used:
        raise RuntimeError(
            "Не нашлись нужные кости для клипа. "
            f"Есть: {{names[:24]}}…"
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
        "from_preset": from_preset or "",
        "mode": mode,
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
    from_preset: str = "",
    blend_frames: int = 0,
    blender_exe: str = "blender",
    timeout: float = 300.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[Path, Dict[str, Any]]:
    """Создать Action на арматуре в .blend; опционально blend from→to."""
    blend = Path(blend_file).resolve()
    if not blend.is_file():
        raise FileNotFoundError(f"Blend не найден: {blend_file}")

    preset_n = (preset or "idle").strip().lower()
    if preset_n not in ANIM_PRESETS:
        raise ValueError(f"preset должен быть один из: {', '.join(ANIM_PRESETS)}")

    from_n = (from_preset or "").strip().lower()
    if from_n and from_n not in ANIM_PRESETS:
        raise ValueError(f"from_preset: {', '.join(ANIM_PRESETS)}")

    act = (action_name or f"viu_{preset_n}").strip()
    if from_n:
        act = (action_name or f"viu_{from_n}_to_{preset_n}").strip()
    if out_blend:
        out = Path(out_blend).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        suffix = f"{from_n}_to_{preset_n}" if from_n else preset_n
        out = blend.with_name(f"{blend.stem}_viu_{suffix}.blend")

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
            from_n,
            str(int(blend_frames) if blend_frames else (12 if from_n else 0)),
        ]
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0 and _MARK_BEGIN not in (proc.stdout or ""):
            raise RuntimeError(f"Blender exit {proc.returncode}.\n{combined.strip()[-2000:]}")
        start = (proc.stdout or combined).find(_MARK_BEGIN)
        end = (proc.stdout or combined).find(_MARK_END)
        if start == -1 or end == -1:
            raise RuntimeError(f"Маркер анимации не найден.\n{combined.strip()[-1500:]}")
        meta = json.loads((proc.stdout or combined)[start + len(_MARK_BEGIN) : end])
        if not meta.get("ok"):
            raise RuntimeError(meta.get("error") or "make_anim failed")
        if not out.is_file():
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
