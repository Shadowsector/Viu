"""Viu — lineup существ рядом с Шаней.

1) Импорт → всё на один ROOT empty
2) Рост = AABB evaluated mesh по Z
3) Scale только ROOT → проверка final ≈ target
4) Табличка: имя / цель / факт
"""
import json
import math
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector


def _argv_job():
    argv = sys.argv
    if "--" in argv:
        return Path(argv[argv.index("--") + 1])
    return Path(__file__).resolve().parent / "lineup_job.json"


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.curves):
        for b in list(block):
            if b.users == 0:
                block.remove(b)


def import_asset(path: Path):
    path = Path(path)
    before = set(bpy.data.objects)
    suf = path.suffix.lower()
    if suf == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path), global_scale=1.0)
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
    bpy.context.view_layer.update()
    return [o for o in bpy.data.objects if o not in before]


def _skip_mesh_name(name: str) -> bool:
    low = (name or "").lower()
    return any(
        k in low
        for k in (
            "collision",
            "col_",
            "_col",
            "hitbox",
            "proxy",
            "shadow",
            "trigger",
            "lod3",
            "lod4",
        )
    )


def mesh_aabb(objects):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mins = Vector((1e18, 1e18, 1e18))
    maxs = Vector((-1e18, -1e18, -1e18))
    any_v = False
    for obj in objects:
        if obj.type != "MESH":
            continue
        if _skip_mesh_name(obj.name):
            continue
        eval_obj = obj.evaluated_get(depsgraph)
        try:
            mesh = eval_obj.to_mesh()
        except RuntimeError:
            continue
        try:
            mw = eval_obj.matrix_world
            for v in mesh.vertices:
                w = mw @ v.co
                mins.x = min(mins.x, w.x)
                mins.y = min(mins.y, w.y)
                mins.z = min(mins.z, w.z)
                maxs.x = max(maxs.x, w.x)
                maxs.y = max(maxs.y, w.y)
                maxs.z = max(maxs.z, w.z)
                any_v = True
        finally:
            eval_obj.to_mesh_clear()
    if not any_v:
        for obj in objects:
            if obj.type != "MESH" or _skip_mesh_name(obj.name):
                continue
            for corner in obj.bound_box:
                w = obj.matrix_world @ Vector(corner)
                mins.x = min(mins.x, w.x)
                mins.y = min(mins.y, w.y)
                mins.z = min(mins.z, w.z)
                maxs.x = max(maxs.x, w.x)
                maxs.y = max(maxs.y, w.y)
                maxs.z = max(maxs.z, w.z)
                any_v = True
    if not any_v:
        return Vector((0, 0, 0)), Vector((0, 0, 1))
    return mins, maxs


def height_of(objects):
    mins, maxs = mesh_aabb(objects)
    return float(maxs.z - mins.z)


def wrap_root(imported, name):
    root = bpy.data.objects.new("ROOT_" + (name or "x")[:48], None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.25
    bpy.context.collection.objects.link(root)
    imported_set = set(imported)
    tops = [o for o in imported if o.parent is None or o.parent not in imported_set]
    for o in tops:
        mw = o.matrix_world.copy()
        o.parent = root
        o.matrix_world = mw
    bpy.context.view_layer.update()
    return root


def place_root(root, objects, x, y=0.0, ground_z=0.0):
    bpy.context.view_layer.update()
    mins, maxs = mesh_aabb(objects)
    cx = (mins.x + maxs.x) * 0.5
    cy = (mins.y + maxs.y) * 0.5
    root.location.x += x - cx
    root.location.y += y - cy
    root.location.z += ground_z - mins.z
    bpy.context.view_layer.update()


def scale_root_to_target(root, objects, target):
    bpy.context.view_layer.update()
    h = height_of(objects)
    if h <= 1e-6 or target <= 0:
        return 1.0, h, h
    if h > 20 and target < 10:
        root.scale *= 0.01
        bpy.context.view_layer.update()
        h = height_of(objects)
    elif h > 5 and target < 5 and (h / target) > 8:
        root.scale *= 0.01
        bpy.context.view_layer.update()
        h = height_of(objects)
    elif h < 0.02 and target >= 0.15:
        root.scale *= 100.0
        bpy.context.view_layer.update()
        h = height_of(objects)
    s = target / h if h > 1e-6 else 1.0
    root.scale *= s
    bpy.context.view_layer.update()
    h_final = height_of(objects)
    if h_final > 1e-6 and abs(h_final - target) / target > 0.03:
        root.scale *= target / h_final
        bpy.context.view_layer.update()
        h_final = height_of(objects)
    return s, h, h_final


def add_text_label(text, location, *, size=0.18):
    curve = bpy.data.curves.new(name="lbl", type="FONT")
    curve.body = text
    curve.size = size
    curve.align_x = "CENTER"
    obj = bpy.data.objects.new(text.split("\n")[0][:40], curve)
    obj.location = location
    obj.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.collection.objects.link(obj)
    return obj


def place_creature(entry, x, y):
    p = Path(entry["path"])
    name = str(entry.get("name") or "?")
    target = float(entry.get("target_height_m") or 1.0)
    if not p.is_file():
        add_text_label("MISSING\n" + name[:40], (x, y - 0.6, 0.5))
        return None
    imported = import_asset(p)
    root = wrap_root(imported, name)
    scale, h_before, h_final = scale_root_to_target(root, imported, target)
    place_root(root, imported, x, y=y, ground_z=0.0)
    ok = h_final > 1e-6 and abs(h_final - target) / max(target, 1e-6) <= 0.08
    tag = "OK" if ok else "FAIL"
    label = (
        f"{name[:28]}\n"
        f"цель {target:.2f}м\n"
        f"факт {h_final:.2f}м [{tag}]"
    )
    add_text_label(label, (x, y - 0.85, 0.05), size=0.14)
    row = {
        "id": entry.get("id"),
        "name": name,
        "measured_m": round(h_before, 4),
        "final_m": round(h_final, 4),
        "target_m": target,
        "scale": round(scale, 6),
        "ok": ok,
    }
    print("VIU_LINEUP_ROW", json.dumps(row, ensure_ascii=False))
    if not ok:
        print("VIU_LINEUP_HEIGHT_FAIL", name, f"final={h_final:.3f}", f"target={target:.3f}")
    return root


def main():
    job_path = _argv_job()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    clear_scene()

    spacing = float(job.get("spacing_m") or 2.8)
    row_pitch = float(job.get("row_pitch_m") or 4.0)

    x = 0.0
    shanya_path = (job.get("shanya_path") or "").strip()
    if shanya_path and Path(shanya_path).is_file():
        try:
            imported = import_asset(Path(shanya_path))
            root = wrap_root(imported, "Shanya")
            target = float(job.get("shanya_target_m") or 1.70)
            scale_root_to_target(root, imported, target)
            place_root(root, imported, x, y=0.0)
            add_text_label(f"Шаня\nцель {target:.2f}м", (x, -0.85, 0.05), size=0.16)
        except Exception as exc:
            print("VIU_LINEUP_WARN shanya", exc)
            traceback.print_exc()
            add_text_label("MISSING Shanya", (0, -0.6, 0.5))
    else:
        add_text_label("MISSING Shanya", (0, -0.6, 0.5))

    creatures = list(job.get("creatures") or [])
    by_class = {}
    for entry in creatures:
        by_class.setdefault(str(entry.get("size_class") or "unset"), []).append(entry)

    max_x = spacing
    row_i = 0
    for size_id, group in sorted(by_class.items()):
        y = -(row_i + 1) * row_pitch
        add_text_label(f"— {size_id} —", (spacing, y + 1.2, 0.3), size=0.22)
        for col, entry in enumerate(group):
            x = (col + 1) * spacing
            max_x = max(max_x, x)
            try:
                place_creature(entry, x, y)
            except Exception as exc:
                print("VIU_LINEUP_WARN", entry.get("name"), exc)
                traceback.print_exc()
                add_text_label(
                    "FAIL\n" + str(entry.get("name") or "?")[:40], (x, y - 0.6, 0.5)
                )
        row_i += 1

    cam_data = bpy.data.cameras.new("LineupCam")
    cam = bpy.data.objects.new("LineupCam", cam_data)
    bpy.context.collection.objects.link(cam)
    depth = max(6.0, (row_i + 1) * row_pitch * 0.7 + 4.0)
    cam.location = (max_x * 0.45, -depth, 2.2)
    cam.rotation_euler = (math.radians(72), 0, 0)
    bpy.context.scene.camera = cam

    out = Path(job.get("output_blend") or (job_path.parent / "creature_lineup.blend"))
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print("VIU_LINEUP_OK", out)


if __name__ == "__main__":
    main()
