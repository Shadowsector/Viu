"""Lineup в Blender: Шаня + существа одного/нескольких классов для сравнения роста."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from ..config import Config
from .models import CreatureEntry, scale_factor_to_target
from .paths import creature_catalog_path, creatures_lineup_dir
from .store import CreatureCatalogStore

LINEUP_SCRIPT_NAME = "viu_creature_lineup.py"


def _shanya_candidates(config: Config) -> List[Path]:
    from ..anabarra_layout import library_root

    lib = library_root(config)
    cands: List[Path] = []
    for rel in (
        ("Lab", "Models", "CascadeurReady"),
        ("Lab", "Models", "Inbox"),
        ("Characters", "Shanya"),
        ("Blender", "Shanya"),
    ):
        d = lib.joinpath(*rel)
        if d.is_dir():
            for p in sorted(d.glob("*Shanya*.fbx")) + sorted(d.glob("*shanya*.fbx")):
                cands.append(p)
            for p in sorted(d.glob("*Shanya*.blend")) + sorted(d.glob("*Erisa*.fbx")):
                cands.append(p)
    # Unity character
    try:
        from ..anabarra_layout import unity_project_path

        u = unity_project_path(config) / "Assets" / "Characters" / "Shanya"
        if u.is_dir():
            cands.extend(sorted(u.rglob("*.fbx")))
    except Exception:
        pass
    # unique
    out: List[Path] = []
    seen = set()
    for p in cands:
        try:
            k = str(p.resolve())
        except OSError:
            k = str(p)
        if k not in seen and p.is_file():
            seen.add(k)
            out.append(p)
    return out


def resolve_shanya_path(config: Config, explicit: str = "") -> Optional[Path]:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    cands = _shanya_candidates(config)
    return cands[0] if cands else None


def build_lineup_job(
    config: Config,
    *,
    size_filter: Sequence[str] = (),
    shanya_path: str = "",
    spacing_m: float = 1.2,
) -> Tuple[bool, str, Path]:
    """Собрать JSON job + Python-скрипт для Blender --background / открыть вручную."""
    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    creatures = [e for e in store.all() if e.size_class]
    if size_filter:
        want = {s.strip() for s in size_filter if s.strip()}
        creatures = [
            e
            for e in creatures
            if e.size_class in want or any(a in want for a in e.size_alt)
        ]
    if not creatures:
        return False, "Нет существ с size_class. Сначала creature_catalog_set_size.", Path()

    shanya = resolve_shanya_path(config, shanya_path)
    out_dir = creatures_lineup_dir(config)
    job_path = out_dir / "lineup_job.json"
    script_path = out_dir / LINEUP_SCRIPT_NAME
    blend_out = out_dir / "creature_lineup.blend"

    entries = []
    for i, e in enumerate(creatures):
        target = e.target_height_m or 1.0
        measured = e.measured_height_m or 0.0
        # если рост ещё не измерен — скрипт измерит bounds и подгонит к target
        entries.append(
            {
                "id": e.id,
                "name": e.name,
                "path": e.path,
                "size_class": e.size_class,
                "target_height_m": target,
                "measured_height_m": measured,
                "index": i,
            }
        )

    job = {
        "shanya_path": str(shanya) if shanya else "",
        "shanya_target_m": 1.70,
        "spacing_m": spacing_m,
        "output_blend": str(blend_out),
        "creatures": entries,
    }
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    script_path.write_text(_LINEUP_BLENDER_SCRIPT, encoding="utf-8")

    hint = (
        f"Lineup job: {job_path}\n"
        f"Скрипт: {script_path}\n"
        f"Выход: {blend_out}\n"
        f"Существ: {len(entries)}; Шаня: {shanya or 'НЕ НАЙДЕНА — укажи shanya_path='}\n\n"
        "Запуск:\n"
        f'  blender --background --python "{script_path}" -- "{job_path}"\n'
        "или открой Blender → Scripting → Open скрипт → внизу путь к job → Run.\n"
        "В кадре: Шаня слева, существа в ряд по X, уже подогнанные к target_height класса."
    )
    return True, hint, job_path


# Исполняется внутри Blender (bpy).
# Политика: только импорт + scale корня + расстановка.
# НЕ apply modifiers, НЕ bake shape keys, НЕ трогать morphs ушей/хвостов/гениталий.
_LINEUP_BLENDER_SCRIPT = textwrap.dedent(
    r'''
"""Viu — lineup существ рядом с Шаней (сравнение роста).

Только импорт + scale корня + расстановка.
Не apply modifiers / не bake shape keys — morphs (уши, хвосты, гениталии) сохраняем.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _argv_job():
    argv = sys.argv
    if "--" in argv:
        return Path(argv[argv.index("--") + 1])
    # fallback: рядом со скриптом
    return Path(__file__).resolve().parent / "lineup_job.json"


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials):
        for b in list(block):
            if b.users == 0:
                block.remove(b)


def import_asset(path: Path):
    path = Path(path)
    before = set(bpy.data.objects)
    suf = path.suffix.lower()
    if suf == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suf == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif suf in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suf == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
            data_to.objects = list(data_from.objects)
        for obj in data_to.objects:
            if obj is not None:
                bpy.context.collection.objects.link(obj)
    else:
        raise RuntimeError("unsupported: " + suf)
    return [o for o in bpy.data.objects if o not in before]


def world_bounds(objects):
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    any_mesh = False
    for obj in objects:
        if obj.type != "MESH":
            continue
        any_mesh = True
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, w.x); mins.y = min(mins.y, w.y); mins.z = min(mins.z, w.z)
            maxs.x = max(maxs.x, w.x); maxs.y = max(maxs.y, w.y); maxs.z = max(maxs.z, w.z)
    if not any_mesh:
        return Vector((0, 0, 0)), Vector((0, 0, 1))
    return mins, maxs


def height_of(objects):
    mins, maxs = world_bounds(objects)
    return float(maxs.z - mins.z)


def place_group(objects, x, ground_z=0.0):
    mins, maxs = world_bounds(objects)
    # центр по X/Y, ноги на ground
    cx = (mins.x + maxs.x) * 0.5
    cy = (mins.y + maxs.y) * 0.5
    dz = ground_z - mins.z
    dx = x - cx
    dy = 0.0 - cy
    for obj in objects:
        if obj.parent:
            continue
        obj.location.x += dx
        obj.location.y += dy
        obj.location.z += dz
    bpy.context.view_layer.update()


def scale_roots(objects, factor):
    for obj in objects:
        if obj.parent:
            continue
        obj.scale *= factor
    bpy.context.view_layer.update()


def label_empty(name, location):
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.location = location
    bpy.context.collection.objects.link(empty)
    return empty


def main():
    job_path = _argv_job()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    clear_scene()

    spacing = float(job.get("spacing_m") or 1.2)
    x = 0.0

    shanya_path = (job.get("shanya_path") or "").strip()
    if shanya_path and Path(shanya_path).is_file():
        objs = import_asset(Path(shanya_path))
        h = height_of(objs)
        target = float(job.get("shanya_target_m") or 1.70)
        if h > 1e-4:
            scale_roots(objs, target / h)
        place_group(objs, x)
        label_empty("LABEL_Shanya", (x, -0.5, target + 0.1))
        x += spacing
    else:
        label_empty("MISSING_Shanya", (0, 0, 1.7))
        x += spacing

    for entry in job.get("creatures") or []:
        p = Path(entry["path"])
        if not p.is_file():
            label_empty("MISSING_" + entry.get("name", "?"), (x, 0, 1))
            x += spacing
            continue
        objs = import_asset(p)
        h = height_of(objs)
        target = float(entry.get("target_height_m") or 1.0)
        if h > 1e-4:
            scale_roots(objs, target / h)
        place_group(objs, x)
        label_empty(
            "LABEL_" + str(entry.get("size_class") or "") + "_" + str(entry.get("name") or "")[:24],
            (x, -0.5, target + 0.1),
        )
        x += spacing

    # камера анфас
    cam_data = bpy.data.cameras.new("LineupCam")
    cam = bpy.data.objects.new("LineupCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (x * 0.5 - spacing * 0.5, -max(4.0, x * 0.55), 1.6)
    cam.rotation_euler = (math.radians(85), 0, 0)
    bpy.context.scene.camera = cam

    out = Path(job.get("output_blend") or (job_path.parent / "creature_lineup.blend"))
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print("VIU_LINEUP_OK", out)


if __name__ == "__main__":
    main()
'''
).lstrip()
