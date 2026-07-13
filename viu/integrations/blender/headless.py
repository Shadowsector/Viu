"""Чтение сведений о .blend-файле через фоновый запуск Blender.

Когда живой Blender с мостом не запущен, Вью может узнать всё о файле,
запустив Blender «без окна» (--background) с dumper-скриптом, который
печатает JSON-описание сцены между маркерами.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List

_MARK_BEGIN = "<<<VIU_BLEND_JSON_BEGIN>>>"
_MARK_END = "<<<VIU_BLEND_JSON_END>>>"

# Скрипт исполняется ВНУТРИ Blender (там доступен bpy). Печатает JSON
# с описанием объектов, мешей, арматур (костей), блендшейпов и материалов.
DUMPER_SCRIPT = f'''
import bpy, json, sys, traceback

def emit(payload):
    print("{_MARK_BEGIN}" + json.dumps(payload, ensure_ascii=False) + "{_MARK_END}")

try:
    def _obj_info(o):
        cols = [c.name for c in o.users_collection]
        info = {{"name": o.name, "type": o.type, "collections": cols}}
        data = o.data
        if o.type == "MESH" and data is not None:
            info["vertices"] = len(data.vertices)
            info["polygons"] = len(data.polygons)
            shape_keys = []
            if getattr(data, "shape_keys", None):
                shape_keys = [kb.name for kb in data.shape_keys.key_blocks]
            info["shape_keys"] = shape_keys
            info["materials"] = [m.name for m in data.materials if m]
            info["modifiers"] = [m.name for m in o.modifiers]
        if o.type == "ARMATURE" and data is not None:
            info["bones"] = [b.name for b in data.bones]
        return info

    scene = {{
        "objects": [_obj_info(o) for o in bpy.data.objects],
        "meshes": [m.name for m in bpy.data.meshes],
        "armatures": [a.name for a in bpy.data.armatures],
        "materials": [m.name for m in bpy.data.materials],
        "actions": [a.name for a in bpy.data.actions],
    }}
    emit({{"ok": True, "scene": scene}})
except Exception as exc:
    emit({{"ok": False, "error": str(exc), "traceback": traceback.format_exc()[-1500:]}})
    raise SystemExit(2)
'''


def build_dump_command(blender_exe: str, blend_file: str, script_path: str) -> List[str]:
    """Команда запуска Blender в фоне (--factory-startup: без DAZ/Viu Bridge)."""
    return [
        blender_exe,
        "--background",
        "--factory-startup",
        blend_file,
        "--python",
        script_path,
        "--python-exit-code",
        "2",
    ]


def parse_dump_output(stdout: str) -> Dict[str, Any]:
    """Извлекает JSON между маркерами из вывода Blender."""
    start = stdout.find(_MARK_BEGIN)
    end = stdout.find(_MARK_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("Не найден JSON в выводе Blender (маркеры отсутствуют).")
    chunk = stdout[start + len(_MARK_BEGIN) : end]
    payload = json.loads(chunk)
    if isinstance(payload, dict) and payload.get("ok") is False:
        err = payload.get("error", "unknown")
        tb = payload.get("traceback", "")
        raise ValueError(f"Blender dump: {err}\n{tb}")
    if isinstance(payload, dict) and "scene" in payload:
        return payload["scene"]
    return payload


def dump_blend_info(
    blend_file: str,
    blender_exe: str = "blender",
    timeout: float = 120.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Dict[str, Any]:
    """Возвращает описание .blend-файла (объекты, кости, блендшейпы, материалы).

    `runner` вынесен параметром, чтобы логику можно было протестировать без Blender.
    """
    if not Path(blend_file).exists():
        raise FileNotFoundError(f"Файл не найден: {blend_file}")

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(DUMPER_SCRIPT)
        script_path = f.name

    try:
        cmd = build_dump_command(blender_exe, blend_file, script_path)
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Blender завершился с кодом {proc.returncode}. stderr:\n{proc.stderr}"
            )
        return parse_dump_output(proc.stdout)
    finally:
        try:
            Path(script_path).unlink()
        except OSError:
            pass
