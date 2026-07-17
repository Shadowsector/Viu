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
            # оружие / пропы раздувают AABB (Alice + мечи → «факт 2м», тело 50см)
            "sword",
            "blade",
            "weapon",
            "knife",
            "dagger",
            "axe",
            "spear",
            "bow",
            "arrow",
            "gun",
            "rifle",
            "shield",
            "scabbard",
            "sheath",
            "prop",
            "accessory",
            "attach",
            "item",
            "fx_",
            "vfx",
            "particle",
            "wing_l",  # иногда отдельные крылья далеко — нет, крылья часть роста феи
        )
    )


def _mesh_has_armature(obj) -> bool:
    for mod in getattr(obj, "modifiers", []) or []:
        if getattr(mod, "type", "") == "ARMATURE":
            return True
    if obj.parent is not None and obj.parent.type == "ARMATURE":
        return True
    return False


def _mesh_world_points(obj, depsgraph):
    if obj.type != "MESH" or _skip_mesh_name(obj.name):
        return []
    eval_obj = obj.evaluated_get(depsgraph)
    try:
        mesh = eval_obj.to_mesh()
    except RuntimeError:
        return []
    pts = []
    try:
        mw = eval_obj.matrix_world
        for v in mesh.vertices:
            pts.append(mw @ v.co)
    finally:
        eval_obj.to_mesh_clear()
    return pts


def _aabb_from_points(pts):
    mins = Vector((1e18, 1e18, 1e18))
    maxs = Vector((-1e18, -1e18, -1e18))
    for w in pts:
        mins.x = min(mins.x, w.x)
        mins.y = min(mins.y, w.y)
        mins.z = min(mins.z, w.z)
        maxs.x = max(maxs.x, w.x)
        maxs.y = max(maxs.y, w.y)
        maxs.z = max(maxs.z, w.z)
    return mins, maxs


def _select_body_meshes(objects):
    """Меши тела: с арматурой и без имён оружия; иначе самый крупный mesh."""
    meshes = [o for o in objects if o.type == "MESH" and not _skip_mesh_name(o.name)]
    if not meshes:
        return []
    rigged = [o for o in meshes if _mesh_has_armature(o)]
    pool = rigged if rigged else meshes
    # отсечь мелкий хлам: оставить меши ≥ 15% от самого жирного по verts
    def vcount(o):
        try:
            return len(o.data.vertices)
        except Exception:
            return 0

    top = max(vcount(o) for o in pool) or 1
    body = [o for o in pool if vcount(o) >= top * 0.15]
    return body or pool


def mesh_aabb(objects):
    """AABB тела (без оружия). Если мечи далеко — в рост не входят."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    body = _select_body_meshes(objects)
    pts = []
    for obj in body:
        pts.extend(_mesh_world_points(obj, depsgraph))
    if not pts:
        # fallback: всё что не skip
        for obj in objects:
            pts.extend(_mesh_world_points(obj, depsgraph))
    if not pts:
        return Vector((0, 0, 0)), Vector((0, 0, 1))
    mins, maxs = _aabb_from_points(pts)
    # отсев выбросов по Z: вершины далеко от медианы XY тела (отлетевшие мечи)
    if len(pts) >= 32:
        cx = sorted(p.x for p in pts)[len(pts) // 2]
        cy = sorted(p.y for p in pts)[len(pts) // 2]
        span_xy = max(maxs.x - mins.x, maxs.y - mins.y, 0.01)
        radius = span_xy * 0.75
        core = [
            p
            for p in pts
            if (p.x - cx) * (p.x - cx) + (p.y - cy) * (p.y - cy) <= radius * radius
        ]
        if len(core) >= max(16, len(pts) // 10):
            mins, maxs = _aabb_from_points(core)
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


def _slugify_name(name: str) -> str:
    import re

    s = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (name or "").strip().lower())
    return re.sub(r"_+", "_", s).strip("_")[:64] or "creature"


def _set_render_engine(scene):
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = eng
            return eng
        except TypeError:
            continue
    return scene.render.engine


def _setup_render_settings(scene, *, res=768):
    _set_render_engine(scene)
    scene.render.resolution_x = int(res)
    scene.render.resolution_y = int(res)
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False


def _ensure_shot_lights():
    if bpy.data.objects.get("VIU_ShotSun"):
        return
    bpy.ops.object.light_add(type="SUN", location=(2.0, -3.0, 5.0))
    sun = bpy.context.active_object
    sun.name = "VIU_ShotSun"
    sun.data.energy = 2.5
    sun.rotation_euler = (math.radians(55), 0, math.radians(25))
    bpy.ops.object.light_add(type="AREA", location=(-2.5, 2.0, 2.0))
    fill = bpy.context.active_object
    fill.name = "VIU_ShotFill"
    fill.data.energy = 180.0
    fill.data.size = 4.0


def _aabb_center_span(objects):
    mins, maxs = mesh_aabb(objects)
    center = (mins + maxs) * 0.5
    span = max(maxs.x - mins.x, maxs.y - mins.y, maxs.z - mins.z, 0.25)
    return center, span, mins, maxs


def _make_shot_camera(objects, yaw_deg: float):
    """yaw 0 = фронт (−Y), 90 = профиль (+X)."""
    center, span, _mins, maxs = _aabb_center_span(objects)
    dist = max(span * 2.4, 1.2)
    rad = math.radians(float(yaw_deg))
    ox = center.x + dist * math.sin(rad)
    oy = center.y - dist * math.cos(rad)
    oz = center.z + span * 0.08
    cam_data = bpy.data.cameras.new("VIU_ShotCam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("VIU_ShotCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (ox, oy, oz)
    direction = center - cam.location
    if direction.length > 1e-6:
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start = 0.01
    cam.data.clip_end = max(dist * 4.0, maxs.z - _mins.z + 10.0)
    return cam


_hidden_restore = []


def _isolate_creature(root):
    global _hidden_restore
    _hidden_restore = []
    keep = set()

    def walk(obj):
        keep.add(obj)
        for ch in obj.children:
            walk(ch)

    walk(root)
    for obj in bpy.data.objects:
        if obj in keep:
            continue
        if obj.type in ("CAMERA", "LIGHT"):
            continue
        _hidden_restore.append((obj, obj.hide_render, obj.hide_viewport))
        obj.hide_render = True
        obj.hide_viewport = True


def _restore_visibility():
    global _hidden_restore
    for obj, hr, hv in _hidden_restore:
        try:
            obj.hide_render = hr
            obj.hide_viewport = hv
        except ReferenceError:
            pass
    _hidden_restore = []


def render_creature_shots(placed, processed_root: Path):
    """Изолированный front/side PNG на существо → Processed/<slug>/."""
    processed_root = Path(processed_root)
    if not placed or not str(processed_root).strip():
        return 0
    scene = bpy.context.scene
    _setup_render_settings(scene)
    _ensure_shot_lights()
    lineup_cam = bpy.data.objects.get("LineupCam")
    if lineup_cam:
        lineup_cam.hide_render = True
    n = 0
    for item in placed:
        root = item.get("root")
        imported = item.get("imported") or []
        entry = item.get("entry") or {}
        if root is None or not imported:
            continue
        slug = str(entry.get("slug") or "").strip() or _slugify_name(entry.get("name"))
        out_dir = processed_root / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        front_path = out_dir / "front.png"
        side_path = out_dir / "side.png"
        _isolate_creature(root)
        try:
            for yaw, path in ((0.0, front_path), (90.0, side_path)):
                cam = _make_shot_camera(imported, yaw)
                scene.camera = cam
                scene.render.filepath = str(path)
                bpy.ops.render.render(write_still=True)
                bpy.data.objects.remove(cam, do_unlink=True)
            row = {
                "id": entry.get("id"),
                "slug": slug,
                "front": str(front_path),
                "side": str(side_path),
            }
            print("VIU_LINEUP_PHOTO", json.dumps(row, ensure_ascii=False))
            n += 1
        except Exception as exc:
            print("VIU_LINEUP_PHOTO_FAIL", slug, exc)
            traceback.print_exc()
        finally:
            _restore_visibility()
    if lineup_cam:
        lineup_cam.hide_render = False
    return n


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
    return {"root": root, "imported": imported, "entry": entry}


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
    placed: list = []
    for size_id, group in sorted(by_class.items()):
        y = -(row_i + 1) * row_pitch
        add_text_label(f"— {size_id} —", (spacing, y + 1.2, 0.3), size=0.22)
        for col, entry in enumerate(group):
            x = (col + 1) * spacing
            max_x = max(max_x, x)
            try:
                result = place_creature(entry, x, y)
                if result:
                    placed.append(result)
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

    processed_root = (job.get("processed_root") or "").strip()
    if processed_root and placed:
        shot_n = render_creature_shots(placed, Path(processed_root))
        print("VIU_LINEUP_PHOTOS_DONE", shot_n)

    out = Path(job.get("output_blend") or (job_path.parent / "creature_lineup.blend"))
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print("VIU_LINEUP_OK", out)


if __name__ == "__main__":
    main()
