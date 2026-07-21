"""Blocking-сцена в Blender для совместных анимаций.

Импорт актёров (Шаня + существа из каталога), studio-камера, empties по sync_markers.
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
    return Path(__file__).resolve().parent / "blocking_job.json"


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
            "weapon",
            "sword",
            "prop",
            "shadow",
            "lod3",
            "lod4",
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
    meshes = [o for o in objects if o.type == "MESH" and not _skip_mesh_name(o.name)]
    if not meshes:
        return []
    rigged = [o for o in meshes if _mesh_has_armature(o)]
    pool = rigged if rigged else meshes

    def vcount(o):
        try:
            return len(o.data.vertices)
        except Exception:
            return 0

    top = max(vcount(o) for o in pool) or 1
    body = [o for o in pool if vcount(o) >= top * 0.15]
    return body or pool


def mesh_aabb(objects):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    body = _select_body_meshes(objects)
    pts = []
    for obj in body:
        pts.extend(_mesh_world_points(obj, depsgraph))
    if not pts:
        for obj in objects:
            pts.extend(_mesh_world_points(obj, depsgraph))
    if not pts:
        return Vector((0, 0, 0)), Vector((0, 0, 1))
    return _aabb_from_points(pts)


def height_of(objects):
    mins, maxs = mesh_aabb(objects)
    return float(maxs.z - mins.z)


def wrap_root(imported, name):
    root = bpy.data.objects.new("ROOT_" + (name or "x")[:40], None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.3
    bpy.context.collection.objects.link(root)
    imported_set = set(imported)
    tops = [o for o in imported if o.parent is None or o.parent not in imported_set]
    for o in tops:
        mw = o.matrix_world.copy()
        o.parent = root
        o.matrix_world = mw
    bpy.context.view_layer.update()
    return root


def place_root(root, objects, x, y=0.0, ground_z=0.0, yaw_deg=0.0):
    bpy.context.view_layer.update()
    mins, maxs = mesh_aabb(objects)
    cx = (mins.x + maxs.x) * 0.5
    cy = (mins.y + maxs.y) * 0.5
    root.location.x += x - cx
    root.location.y += y - cy
    root.location.z += ground_z - mins.z
    root.rotation_euler.z = math.radians(float(yaw_deg))
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
    s = target / h if h > 1e-6 else 1.0
    root.scale *= s
    bpy.context.view_layer.update()
    h_final = height_of(objects)
    if h_final > 1e-6 and abs(h_final - target) / target > 0.03:
        root.scale *= target / h_final
        bpy.context.view_layer.update()
        h_final = height_of(objects)
    return s, h, h_final


def _scene_bounds(objects):
    mins = Vector((1e18, 1e18, 1e18))
    maxs = Vector((-1e18, -1e18, -1e18))
    for obj in objects:
        if obj.type != "MESH":
            continue
        lo, hi = mesh_aabb([obj])
        mins.x = min(mins.x, lo.x)
        mins.y = min(mins.y, lo.y)
        mins.z = min(mins.z, lo.z)
        maxs.x = max(maxs.x, hi.x)
        maxs.y = max(maxs.y, hi.y)
        maxs.z = max(maxs.z, hi.z)
    if mins.x > maxs.x:
        return Vector((0, 0, 0)), 1.0
    center = (mins + maxs) * 0.5
    span = max(maxs.x - mins.x, maxs.y - mins.y, maxs.z - mins.z, 0.5)
    return center, span


def add_studio_floor(size=12.0):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "VIU_StudioFloor"
    mat = bpy.data.materials.new("VIU_StudioWhite")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.92, 0.92, 0.92, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.85
    floor.data.materials.append(mat)
    return floor


def add_marker_empty(marker: dict):
    frame = int(marker.get("frame") or 0)
    event = str(marker.get("event") or "mark")
    x = float(marker.get("x") or 0)
    y = float(marker.get("y") or 0)
    z = float(marker.get("z") or 0)
    empty = bpy.data.objects.new(f"MARKER_f{frame:03d}_{event}", None)
    empty.empty_display_type = "SPHERE"
    empty.empty_display_size = 0.12
    empty.location = (x, y, z)
    bpy.context.collection.objects.link(empty)
    note = str(marker.get("note") or "")
    if note:
        empty["viu_note"] = note
    empty["viu_frame"] = frame
    empty["viu_event"] = event
    return empty


def setup_studio_camera(choreo: dict, focus_objects):
    cam_type = str(choreo.get("camera_type") or "ortho_studio")
    dist = float(choreo.get("camera_distance_m") or 4.0)
    height = float(choreo.get("camera_height_m") or 1.8)
    center, span = _scene_bounds(focus_objects)

    cam_data = bpy.data.cameras.new("VIU_StudioCam")
    if "ortho" in cam_type.lower():
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = max(span * 2.2, 2.5)
    else:
        cam_data.type = "PERSP"
        cam_data.lens = 50.0
    cam = bpy.data.objects.new("VIU_StudioCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (center.x, center.y - dist, height)
    look = center + Vector((0, 0, span * 0.35))
    direction = look - cam.location
    if direction.length > 1e-6:
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def setup_lights():
    bpy.ops.object.light_add(type="SUN", location=(2, -3, 5))
    sun = bpy.context.active_object
    sun.name = "VIU_StudioSun"
    sun.data.energy = 2.8
    sun.rotation_euler = (math.radians(50), 0, math.radians(20))
    bpy.ops.object.light_add(type="AREA", location=(-2, 2, 2.5))
    fill = bpy.context.active_object
    fill.name = "VIU_StudioFill"
    fill.data.energy = 200.0
    fill.data.size = 5.0


def place_actor(actor: dict):
    path = Path(actor.get("path") or "")
    role = str(actor.get("role") or "actor")
    slug = str(actor.get("slug") or role)
    name = str(actor.get("name") or slug)
    target = float(actor.get("target_m") or 1.0)
    x = float(actor.get("x") or 0)
    y = float(actor.get("y") or 0)
    yaw = float(actor.get("yaw_deg") or 0)
    if not path.is_file():
        print("VIU_BLOCKING_WARN", json.dumps({"role": role, "slug": slug, "error": "missing"}))
        return None
    imported = import_asset(path)
    root = wrap_root(imported, slug[:32])
    scale, h_before, h_final = scale_root_to_target(root, imported, target)
    place_root(root, imported, x, y=y, ground_z=0.0, yaw_deg=yaw)
    root.name = f"ACTOR_{role}_{slug}"[:60]
    row = {
        "role": role,
        "slug": slug,
        "name": name,
        "measured_m": round(h_before, 4),
        "final_m": round(h_final, 4),
        "target_m": target,
        "x": x,
        "y": y,
        "yaw_deg": yaw,
    }
    print("VIU_BLOCKING_ACTOR", json.dumps(row, ensure_ascii=False))
    return {"root": root, "imported": imported, "row": row}


def main():
    job_path = _argv_job()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    clear_scene()

    scene = bpy.context.scene
    ch = job.get("choreography") or {}
    scene.render.fps = int(ch.get("fps") or 24)
    scene.frame_start = 1
    scene.frame_end = max(int(ch.get("duration_frames") or 72), 24)

    add_studio_floor()
    setup_lights()

    placed = []
    focus_meshes = []
    for actor in job.get("actors") or []:
        try:
            result = place_actor(actor)
            if result:
                placed.append(result)
                focus_meshes.extend(result["imported"])
        except Exception as exc:
            print("VIU_BLOCKING_WARN", actor.get("slug"), exc)
            traceback.print_exc()

    for marker in job.get("sync_markers") or []:
        add_marker_empty(marker)

    setup_studio_camera(ch, focus_meshes or list(bpy.data.objects))

    out = Path(job.get("output_blend") or (job_path.parent / "blocking.blend"))
    lock_path = Path(job.get("choreography_lock") or (job_path.parent / "choreography_lock.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "choreography": ch,
                "interaction_slug": job.get("interaction_slug"),
                "actors": [p["row"] for p in placed],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print("VIU_BLOCKING_OK", json.dumps({"blend": str(out), "lock": str(lock_path)}))


if __name__ == "__main__":
    main()
