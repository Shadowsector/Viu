"""Экспорт персонажа FBX для Unity / Cascadeur — без WGT, без user addons."""

from __future__ import annotations

import json
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List

_MARK_BEGIN = "<<<VIU_EXPORT_JSON_BEGIN>>>"
_MARK_END = "<<<VIU_EXPORT_JSON_END>>>"

# --factory-startup: не грузить DAZ Importer / Viu Bridge (Den: Blender «мигнул и quit»).
EXPORT_SCRIPT = f'''
import bpy, json, sys, traceback

def emit(payload):
    print("{_MARK_BEGIN}" + json.dumps(payload, ensure_ascii=False) + "{_MARK_END}")

try:
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError("Нужен путь выхода после --")
    out_path = argv[argv.index("--") + 1]

    hidden = 0
    for obj in bpy.data.objects:
        name = obj.name
        if name.startswith("WGT") or name in ("Circle", "Sphere"):
            try:
                obj.hide_set(True)
                obj.hide_viewport = True
            except Exception:
                pass
            hidden += 1

    for col in bpy.data.collections:
        try:
            col.hide_viewport = False
        except Exception:
            pass

    scene = bpy.context.scene
    view_layer = bpy.context.view_layer

    def _unhide_lc(lc):
        try:
            lc.exclude = False
            lc.hide_viewport = False
        except Exception:
            pass
        try:
            lc.collection.hide_viewport = False
        except Exception:
            pass
        for ch in lc.children:
            _unhide_lc(ch)

    _unhide_lc(view_layer.layer_collection)

    skipped = []
    for obj in list(bpy.data.objects):
        if obj.type not in ("MESH", "ARMATURE"):
            continue
        if getattr(obj, "library", None):
            continue
        if obj.name in view_layer.objects:
            continue
        try:
            scene.collection.objects.link(obj)
        except RuntimeError:
            pass

    bpy.ops.object.select_all(action="DESELECT")
    active_arm = None
    selected = []
    for obj in list(view_layer.objects):
        if obj.type not in ("MESH", "ARMATURE"):
            continue
        try:
            if obj.hide_viewport or obj.hide_get():
                obj.hide_set(False)
                obj.hide_viewport = False
        except Exception:
            pass
        try:
            obj.select_set(True)
        except RuntimeError as exc:
            skipped.append(f"{{obj.name}}: {{exc}}")
            continue
        selected.append(obj.name)
        if obj.type == "ARMATURE" and active_arm is None:
            active_arm = obj

    if active_arm is None:
        for obj in list(view_layer.objects):
            if obj.type == "ARMATURE":
                try:
                    obj.select_set(True)
                except RuntimeError:
                    continue
                active_arm = obj
                if obj.name not in selected:
                    selected.append(obj.name)
                break

    if not selected:
        raise RuntimeError(
            "Нет MESH/ARMATURE для экспорта. "
            + (f"Пропуск: {{skipped[:5]}}" if skipped else "Сцена пуста или всё скрыто.")
        )

    if active_arm:
        bpy.context.view_layer.objects.active = active_arm
    else:
        bpy.context.view_layer.objects.active = bpy.data.objects[selected[0]]

    bpy.ops.export_scene.fbx(
        filepath=out_path,
        use_selection=True,
        object_types={{"ARMATURE", "MESH"}},
        use_mesh_modifiers=True,
        bake_anim=False,
        add_leaf_bones=False,
        mesh_smooth_type="FACE",
        apply_scale_options="FBX_SCALE_ALL",
    )

    emit({{
        "ok": True,
        "output": out_path,
        "selected": selected,
        "skipped": skipped,
        "hidden_widgets": hidden,
    }})
except Exception as exc:
    emit({{
        "ok": False,
        "error": str(exc),
        "traceback": traceback.format_exc()[-2000:],
    }})
    raise SystemExit(2)
'''


def build_export_command(blender_exe: str, blend_file: str, script_path: str, output_fbx: str) -> List[str]:
    return [
        blender_exe,
        "--background",
        "--factory-startup",
        blend_file,
        "--python",
        script_path,
        "--python-exit-code",
        "2",
        "--",
        output_fbx,
    ]


def _tail(text: str, limit: int = 2000) -> str:
    text = (text or "").strip()
    return text[-limit:] if len(text) > limit else text


def parse_export_output(stdout: str) -> Dict[str, Any]:
    start = stdout.find(_MARK_BEGIN)
    end = stdout.find(_MARK_END)
    if start == -1 or end == -1:
        raise RuntimeError(f"Маркер экспорта не найден.\n{_tail(stdout)}")
    data = json.loads(stdout[start + len(_MARK_BEGIN) : end])
    if not data.get("ok", True):
        err = data.get("error", "unknown")
        tb = data.get("traceback", "")
        raise RuntimeError(f"Blender export: {err}\n{tb}")
    return data


def export_shanya_fbx(
    blend_file: str,
    output_fbx: str | None = None,
    blender_exe: str = "blender",
    timeout: float = 300.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    blend = Path(blend_file).resolve()
    if not blend.is_file():
        raise FileNotFoundError(f"Blend не найден: {blend_file}")

    out = Path(output_fbx).resolve() if output_fbx else blend.with_suffix(".fbx")
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(EXPORT_SCRIPT)
        script_path = f.name

    try:
        cmd = build_export_command(blender_exe, str(blend), script_path, str(out))
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0 and _MARK_BEGIN not in proc.stdout:
            raise RuntimeError(
                f"Blender завершился с кодом {proc.returncode}.\n{_tail(combined)}"
            )
        parse_export_output(proc.stdout or combined)
        if not out.is_file():
            raise RuntimeError(f"FBX не создан: {out}\n{_tail(combined)}")
        return out
    finally:
        try:
            Path(script_path).unlink()
        except OSError:
            pass
