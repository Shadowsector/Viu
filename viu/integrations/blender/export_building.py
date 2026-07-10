"""Экспорт prepared .blend (домики, props) → FBX для Unity."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List

_MARK_BEGIN = "<<<VIU_EXPORT_JSON_BEGIN>>>"
_MARK_END = "<<<VIU_EXPORT_JSON_END>>>"

# Статичные меши: видимые MESH, без armature-анимации.
EXPORT_BUILDING_SCRIPT = f'''
import bpy
import json
import sys

argv = sys.argv
if "--" not in argv:
    raise SystemExit("Нужен путь выхода после --")
out_path = argv[argv.index("--") + 1]

SKIP_PREFIX = ("WGT",)
SKIP_TYPES = {{"CAMERA", "LIGHT", "SPEAKER"}}

exported = []
skipped = []

for obj in list(bpy.data.objects):
    if obj.type in SKIP_TYPES:
        skipped.append(obj.name)
        continue
    if obj.type != "MESH":
        continue
    if obj.hide_viewport or obj.hide_get():
        skipped.append(obj.name)
        continue
    if any(obj.name.startswith(p) for p in SKIP_PREFIX):
        skipped.append(obj.name)
        continue
    obj.select_set(True)
    exported.append(obj.name)

if not exported:
    raise SystemExit("Нет видимых MESH для экспорта")

bpy.context.view_layer.objects.active = bpy.data.objects[exported[0]]

bpy.ops.export_scene.fbx(
    filepath=out_path,
    use_selection=True,
    object_types={{"MESH"}},
    use_mesh_modifiers=True,
    mesh_smooth_type="FACE",
    apply_scale_options="FBX_SCALE_ALL",
    bake_anim=False,
    add_leaf_bones=False,
    path_mode="COPY",
    embed_textures=True,
)

report = {{"output": out_path, "meshes": exported, "skipped": skipped}}
print("{_MARK_BEGIN}" + json.dumps(report, ensure_ascii=False) + "{_MARK_END}")
'''


def build_export_command(
    blender_exe: str,
    blend_file: str,
    script_path: str,
    output_fbx: str,
) -> List[str]:
    return [
        blender_exe,
        "--background",
        blend_file,
        "--python",
        script_path,
        "--",
        output_fbx,
    ]


def parse_export_json(stdout: str) -> Dict[str, Any]:
    start = stdout.find(_MARK_BEGIN)
    end = stdout.find(_MARK_END)
    if start == -1 or end == -1:
        raise RuntimeError(f"Маркер экспорта не найден.\n{stdout[-2000:]}")
    return json.loads(stdout[start + len(_MARK_BEGIN) : end])


def export_building_fbx(
    blend_file: str,
    output_fbx: str,
    *,
    blender_exe: str = "blender",
    timeout: float = 300.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Dict[str, Any]:
    blend = Path(blend_file).resolve()
    if not blend.is_file():
        raise FileNotFoundError(f"Blend не найден: {blend_file}")

    out = Path(output_fbx).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(EXPORT_BUILDING_SCRIPT)
        script_path = f.name

    try:
        cmd = build_export_command(blender_exe, str(blend), script_path, str(out))
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Blender export code {proc.returncode}\nstderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
            )
        report = parse_export_json(proc.stdout)
        if not out.is_file():
            raise RuntimeError(f"FBX не создан: {out}")
        report["output"] = str(out)
        return report
    finally:
        try:
            Path(script_path).unlink()
        except OSError:
            pass


def slugify_pack_name(name: str) -> str:
    """Old Stables → Old_Stables"""
    s = re.sub(r"[^\w\s-]", "", name.strip(), flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "asset"


def pack_name_from_prepared(prepared: Path) -> str:
    stem = prepared.stem
    if stem.lower().endswith("_prepared"):
        stem = stem[: -len("_prepared")]
    parent = prepared.parent.name
    if parent.lower() not in ("processed", "blender", "inbox"):
        return parent
    return stem
