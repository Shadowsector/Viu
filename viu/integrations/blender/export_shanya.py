"""Экспорт Shanya_Erisa FBX для Unity — без WGT-виджетов."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List

_MARK_BEGIN = "<<<VIU_EXPORT_OK>>>"
_MARK_END = "<<<VIU_EXPORT_END>>>"

EXPORT_SCRIPT = f'''
import bpy
import sys

argv = sys.argv
if "--" not in argv:
    raise SystemExit("Нужен путь выхода после --")
out_path = argv[argv.index("--") + 1]

hidden = 0
for obj in bpy.data.objects:
    name = obj.name
    if name.startswith("WGT") or name in ("Circle", "Sphere"):
        obj.hide_set(True)
        try:
            obj.hide_viewport = True
        except Exception:
            pass
        hidden += 1

bpy.ops.object.select_all(action='DESELECT')
active_arm = None
for obj in bpy.data.objects:
    if obj.type not in ('MESH', 'ARMATURE'):
        continue
    if obj.hide_viewport or obj.hide_get():
        continue
    obj.select_set(True)
    if obj.type == 'ARMATURE':
        active_arm = obj

if active_arm is None:
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            active_arm = obj
            obj.select_set(True)
            break

if active_arm:
    bpy.context.view_layer.objects.active = active_arm

bpy.ops.export_scene.fbx(
    filepath=out_path,
    use_selection=True,
    object_types={{'ARMATURE', 'MESH'}},
    bake_anim=False,
    add_leaf_bones=False,
    mesh_smooth_type='FACE',
)

print("{_MARK_BEGIN}" + out_path + "{_MARK_END}")
print(f"[Viu] FBX export: {{out_path}}, hidden widgets: {{hidden}}")
'''


def build_export_command(blender_exe: str, blend_file: str, script_path: str, output_fbx: str) -> List[str]:
    return [
        blender_exe,
        "--background",
        blend_file,
        "--python",
        script_path,
        "--",
        output_fbx,
    ]


def export_shanya_fbx(
    blend_file: str,
    output_fbx: str | None = None,
    blender_exe: str = "blender",
    timeout: float = 180.0,
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
        if proc.returncode != 0:
            raise RuntimeError(
                f"Blender export code {proc.returncode}\nstderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
            )
        if _MARK_BEGIN not in proc.stdout:
            raise RuntimeError(f"Маркер экспорта не найден.\n{proc.stdout[-2000:]}")
        return out
    finally:
        try:
            Path(script_path).unlink()
        except OSError:
            pass
