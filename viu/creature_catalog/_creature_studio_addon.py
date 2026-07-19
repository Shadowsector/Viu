"""Viu Creature Studio — панель в Blender для разметки существ по одному."""
bl_info = {
    "name": "Viu Creature Studio",
    "author": "Viu",
    "version": (0, 1, 3),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Viu",
    "description": "Шаня + одно существо: рост, очистка, скрины, эталон",
    "category": "Animation",
}

import json
import math
import re
import traceback
from pathlib import Path

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from mathutils import Vector

_SESSION: dict = {}
_STATE = {
    "creature_root": None,
    "creature_objects": [],
    "shanya_root": None,
    "shanya_objects": [],
    "body_mesh": "",
}

_SLOT_NAME = "VIU_CreatureSlot"
_SHANYA_COLL = "VIU_ShanyaRef"

_RIG_HIDE = (
    "ik", "pole", "ctrl", "control", "target", "widget", "wgt", "handle",
    "gizmo", "helper", "empties", "guide", "wire",
)


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (name or "").strip().lower())
    return re.sub(r"_+", "_", s).strip("_")[:64] or "creature"


def _current_entry() -> dict:
    q = _SESSION.get("queue") or []
    idx = int(_SESSION.get("index") or 0)
    if not q:
        return {}
    idx = max(0, min(idx, len(q) - 1))
    return q[idx]


def _write_feedback(entry: dict, **extra) -> None:
    path = Path(str(_SESSION.get("feedback_path") or ""))
    if not path.parent:
        return
    data = {"entries": []}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"entries": []}
    rows = {r.get("id"): r for r in data.get("entries") or [] if isinstance(r, dict)}
    row = dict(rows.get(entry.get("id"), entry))
    row.update(extra)
    row["id"] = entry.get("id")
    row["slug"] = entry.get("slug")
    rows[entry.get("id")] = row
    data["entries"] = list(rows.values())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clear_creature():
    """Убрать только текущее существо (Шаню не трогаем)."""
    root = _STATE.get("creature_root")
    if root and root.name in bpy.data.objects:
        try:
            bpy.data.objects.remove(root, do_unlink=True)
        except ReferenceError:
            pass
    coll = bpy.data.collections.get(_SLOT_NAME)
    if coll:
        for obj in list(coll.all_objects):
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except ReferenceError:
                pass
        if coll.name in bpy.data.collections:
            bpy.data.collections.remove(coll)
    for obj in list(bpy.data.objects):
        if obj.name.startswith("VIU_CREATURE_ROOT"):
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except ReferenceError:
                pass
    _STATE["creature_root"] = None
    _STATE["creature_objects"] = []
    _STATE["body_mesh"] = ""
    for block in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials):
        for b in list(block):
            if b.users == 0:
                try:
                    block.remove(b)
                except (AttributeError, ReferenceError):
                    pass


def _creature_slot():
    coll = bpy.data.collections.get(_SLOT_NAME)
    if coll is None:
        coll = bpy.data.collections.new(_SLOT_NAME)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _shanya_slot():
    coll = bpy.data.collections.get(_SHANYA_COLL)
    if coll is None:
        coll = bpy.data.collections.new(_SHANYA_COLL)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _link_objects_to_collection(objects, coll):
    for obj in objects:
        if obj is None:
            continue
        for uc in list(obj.users_collection):
            try:
                uc.objects.unlink(obj)
            except RuntimeError:
                pass
        if obj.name not in coll.objects:
            coll.objects.link(obj)


def _is_wgt_name(name: str) -> bool:
    """Custom bone shapes (WGT.Foot.L и т.п.) — не тело."""
    if not name:
        return False
    n = name.strip()
    if n.startswith("WGT.") or n.startswith("WGT-") or n.startswith("WGT_"):
        return True
    low = n.lower()
    return low.startswith("wgt.") or low.startswith("wgt-") or low.startswith("wgt_")


def _import_asset(path: Path, *, for_shanya: bool = False, target_coll=None):
    path = Path(path)
    before = set(bpy.data.objects)
    before_colls = set(bpy.data.collections)
    suf = path.suffix.lower()
    if suf == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path), global_scale=1.0)
    elif suf == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif suf in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suf == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
            data_to.collections = list(data_from.collections)
            data_to.objects = list(data_from.objects)
        scene_coll = bpy.context.scene.collection
        for coll in bpy.data.collections:
            if coll in before_colls:
                continue
            try:
                scene_coll.children.link(coll)
            except RuntimeError:
                pass
        for obj in bpy.data.objects:
            if obj in before:
                continue
            if obj.users_collection:
                continue
            try:
                scene_coll.objects.link(obj)
            except RuntimeError:
                pass
    else:
        raise RuntimeError("unsupported: " + suf)
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in before]
    if for_shanya:
        wgt = [o for o in imported if _is_wgt_name(o.name)]
        for obj in wgt:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except ReferenceError:
                pass
        imported = [o for o in imported if o not in wgt]
        for obj in imported:
            if obj.type == "MESH":
                obj.hide_set(False)
                obj.hide_render = False
            elif obj.type == "ARMATURE":
                obj.hide_set(False)
                obj.data.display_type = "STICK"
    else:
        _post_import_visibility(imported)
    if target_coll is not None:
        _link_objects_to_collection(imported, target_coll)
    return imported


def _post_import_visibility(objects):
    """Спрятать WGT/empties, показать меши тела."""
    body = []
    for obj in objects:
        if _is_wgt_name(obj.name):
            obj.hide_set(True)
            try:
                obj.hide_viewport = True
            except AttributeError:
                pass
            obj.hide_render = True
            continue
        if obj.type == "MESH" and _skip_mesh(obj.name):
            obj.hide_set(True)
            obj.hide_render = True
            continue
        if obj.type == "MESH":
            obj.hide_set(False)
            try:
                obj.hide_viewport = False
            except AttributeError:
                pass
            obj.hide_render = False
            vc = len(obj.data.vertices) if obj.data else 0
            if vc > 32:
                body.append(obj)
        elif obj.type == "ARMATURE":
            obj.hide_set(False)
            obj.data.display_type = "STICK"
        elif obj.type == "EMPTY":
            obj.hide_set(True)
            obj.hide_render = True
    return body


def _wrap_root(imported, name, root_name="VIU_CREATURE_ROOT", target_coll=None):
    root = bpy.data.objects.new(root_name, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.2
    coll = target_coll or bpy.context.collection
    coll.objects.link(root)
    imported_set = set(imported)
    for o in imported:
        if o.parent is None or o.parent not in imported_set:
            mw = o.matrix_world.copy()
            o.parent = root
            o.matrix_world = mw
    bpy.context.view_layer.update()
    return root


def _skip_mesh(name: str) -> bool:
    if _is_wgt_name(name):
        return True
    low = (name or "").lower()
    return any(k in low for k in _RIG_HIDE + ("collision", "weapon", "sword", "shadow", "lod3", "lod4"))


def _mesh_points(obj, depsgraph):
    if obj.type != "MESH" or _skip_mesh(obj.name):
        return []
    ev = obj.evaluated_get(depsgraph)
    try:
        mesh = ev.to_mesh()
    except RuntimeError:
        return []
    pts = []
    try:
        mw = ev.matrix_world
        for v in mesh.vertices:
            pts.append(mw @ v.co)
    finally:
        ev.to_mesh_clear()
    return pts


def _aabb_pts(pts):
    if not pts:
        return Vector((0, 0, 0)), Vector((0, 0, 1))
    mins = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    maxs = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mins, maxs


def _height_of_objects(objects, body_mesh: str = ""):
    deps = bpy.context.evaluated_depsgraph_get()
    if body_mesh:
        obj = bpy.data.objects.get(body_mesh)
        if obj:
            pts = _mesh_points(obj, deps)
            if pts:
                mins, maxs = _aabb_pts(pts)
                return float(maxs.z - mins.z)
    meshes = [o for o in objects if o.type == "MESH" and not _skip_mesh(o.name)]
    if not meshes:
        return 0.0
    best = max(meshes, key=lambda o: len(o.data.vertices) if o.data else 0)
    pts = _mesh_points(best, deps)
    if not pts:
        return 0.0
    mins, maxs = _aabb_pts(pts)
    return float(maxs.z - mins.z)


def _hide_helpers(objects):
    for obj in objects:
        if _is_wgt_name(obj.name):
            obj.hide_set(True)
            obj.hide_render = True
            continue
        low = (obj.name or "").lower()
        try:
            if obj.type == "EMPTY":
                obj.hide_set(True)
                obj.hide_render = True
            elif obj.type == "ARMATURE":
                obj.data.display_type = "STICK"
            elif obj.type == "MESH" and any(k in low for k in _RIG_HIDE):
                obj.hide_set(True)
                obj.hide_render = True
            elif obj.type == "CURVE":
                obj.hide_set(True)
                obj.hide_render = True
        except (AttributeError, ReferenceError):
            pass


def _place_creature(root, objects, x_offset: float, target_h: float, body_mesh: str = ""):
    bpy.context.view_layer.update()
    h = _height_of_objects(objects, body_mesh)
    if h > 1e-6 and target_h > 0:
        if h > 20 and target_h < 10:
            root.scale *= 0.01
            bpy.context.view_layer.update()
            h = _height_of_objects(objects, body_mesh)
        s = target_h / h
        root.scale *= s
        bpy.context.view_layer.update()
    # лицом в +Y как Шаня, рядом по X
    root.location = (x_offset, 0.0, 0.0)
    root.rotation_euler = (0.0, 0.0, 0.0)
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objects:
        pts.extend(_mesh_points(o, deps))
    if pts:
        mins, _ = _aabb_pts(pts)
        root.location.z -= mins.z
    bpy.context.view_layer.update()


def _ensure_shanya():
    if _STATE.get("shanya_root") and _STATE["shanya_root"].name in bpy.data.objects:
        return
    path = Path(str(_SESSION.get("shanya_path") or ""))
    if not path.is_file():
        return
    slot = _shanya_slot()
    imported = _import_asset(path, for_shanya=True, target_coll=slot)
    _STATE["shanya_objects"] = imported
    root = _wrap_root(imported, "Shanya", root_name="VIU_SHANYA_ROOT", target_coll=slot)
    target = float(_SESSION.get("shanya_target_m") or 1.70)
    h = _height_of_objects(imported)
    if h > 1e-6:
        root.scale *= target / h
    root.location = (0.0, 0.0, 0.0)
    _STATE["shanya_root"] = root
    for obj in imported:
        if _is_wgt_name(obj.name):
            obj.hide_set(True)
            obj.hide_render = True


def _mesh_enum_items(self, context):
    items = [("AUTO", "Авто (крупнейший меш)", "")]
    for o in _STATE.get("creature_objects") or []:
        if o.type == "MESH" and not _skip_mesh(o.name):
            vc = len(o.data.vertices) if o.data else 0
            items.append((o.name, f"{o.name} ({vc}v)", ""))
    return items


def _load_creature_entry(entry: dict):
    _clear_creature()
    path = Path(str(entry.get("path") or ""))
    if not path.is_file():
        return f"Нет файла: {path}"
    slot = _creature_slot()
    imported = _import_asset(path, for_shanya=False, target_coll=slot)
    root = _wrap_root(imported, entry.get("name") or "creature", target_coll=slot)
    _hide_helpers(imported)
    body_meshes = [o for o in imported if o.type == "MESH" and not o.hide_get()]
    target = float(entry.get("target_height_m") or 1.0)
    offset = float(_SESSION.get("creature_offset_m") or 1.35)
    body = _STATE.get("body_mesh") or "AUTO"
    bm = "" if body == "AUTO" else body
    _place_creature(root, imported, offset, target, bm)
    _STATE["creature_root"] = root
    _STATE["creature_objects"] = imported
    if body_meshes:
        best = max(body_meshes, key=lambda o: len(o.data.vertices) if o.data else 0)
        _STATE["body_mesh"] = best.name
    else:
        _STATE["body_mesh"] = ""
    if not body_meshes:
        return (
            f"Загружено: {entry.get('name')} — ⚠ только WGT/риг, тела не видно. "
            "Проверь .blend (коллекция Body) или положи FBX в Creatures/Inbox."
        )
    return f"Загружено: {entry.get('name')} (меш: {_STATE['body_mesh']})"


def _setup_camera_for_shot(yaw_deg: float, objects):
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objects:
        pts.extend(_mesh_points(o, deps))
    if not pts:
        return None
    mins, maxs = _aabb_pts(pts)
    center = (mins + maxs) * 0.5
    span = max(maxs.x - mins.x, maxs.y - mins.y, maxs.z - mins.z, 0.25)
    dist = max(span * 2.2, 1.0)
    rad = math.radians(yaw_deg)
    cam_data = bpy.data.cameras.new("VIU_StudioCam")
    cam = bpy.data.objects.new("VIU_StudioCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (
        center.x + dist * math.sin(rad),
        center.y - dist * math.cos(rad),
        center.z + span * 0.1,
    )
    direction = center - cam.location
    if direction.length > 1e-6:
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


def _render_shots(entry: dict) -> tuple[str, str]:
    slug = str(entry.get("slug") or _slugify(entry.get("name")))
    out_dir = Path(str(_SESSION.get("processed_root") or "")) / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    front = out_dir / "front.png"
    side = out_dir / "side.png"
    scene = bpy.context.scene
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.image_settings.file_format = "PNG"
    objs = list(_STATE.get("creature_objects") or [])
    # спрятать Шаню на время съёмки
    shanya = _STATE.get("shanya_root")
    shanya_hide = False
    if shanya:
        shanya_hide = shanya.hide_get()
        shanya.hide_set(True)
        shanya.hide_render = True
    try:
        for yaw, path in ((0.0, front), (90.0, side)):
            cam = _setup_camera_for_shot(yaw, objs)
            if cam is None:
                continue
            scene.camera = cam
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            bpy.data.objects.remove(cam, do_unlink=True)
    finally:
        if shanya:
            shanya.hide_set(shanya_hide)
            shanya.hide_render = False
    return str(front), str(side)


def _gather_creature_objects():
    root = _STATE.get("creature_root")
    if root is None:
        return []
    out = []

    def walk(o):
        out.append(o)
        for ch in o.children:
            walk(ch)

    walk(root)
    return out


def _save_creature_blend(filepath: Path) -> bool:
    objs = _gather_creature_objects()
    if not objs:
        return False
    filepath.parent.mkdir(parents=True, exist_ok=True)
    if filepath.is_file():
        filepath.unlink()
    bpy.data.libraries.write(str(filepath), objs, path_remap="RELATIVE", fake_user=True)
    return filepath.is_file()


class VIU_OT_StudioShowBody(bpy.types.Operator):
    bl_idname = "viu.studio_show_body"
    bl_label = "Показать меши тела"

    def execute(self, context):
        objs = _STATE.get("creature_objects") or []
        shown = 0
        for obj in objs:
            if obj.type != "MESH" or _is_wgt_name(obj.name):
                continue
            obj.hide_set(False)
            try:
                obj.hide_viewport = False
            except AttributeError:
                pass
            obj.hide_render = False
            shown += 1
        self.report({"INFO"}, f"Показано мешей: {shown}")
        return {"FINISHED"}


class VIU_OT_StudioPrev(bpy.types.Operator):
    bl_idname = "viu.studio_prev"
    bl_label = "Предыдущее"

    def execute(self, context):
        q = _SESSION.get("queue") or []
        if not q:
            return {"CANCELLED"}
        _SESSION["index"] = (int(_SESSION.get("index") or 0) - 1) % len(q)
        _load_creature_entry(_current_entry())
        return {"FINISHED"}


class VIU_OT_StudioNext(bpy.types.Operator):
    bl_idname = "viu.studio_next"
    bl_label = "Следующее"

    def execute(self, context):
        q = _SESSION.get("queue") or []
        if not q:
            return {"CANCELLED"}
        _SESSION["index"] = (int(_SESSION.get("index") or 0) + 1) % len(q)
        _load_creature_entry(_current_entry())
        return {"FINISHED"}


class VIU_OT_StudioReload(bpy.types.Operator):
    bl_idname = "viu.studio_reload"
    bl_label = "Перезагрузить"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        self.report({"INFO"}, _load_creature_entry(entry))
        return {"FINISHED"}


class VIU_OT_StudioHideIk(bpy.types.Operator):
    bl_idname = "viu.studio_hide_ik"
    bl_label = "Спрятать IK"

    def execute(self, context):
        _hide_helpers(_STATE.get("creature_objects") or [])
        self.report({"INFO"}, "IK / empties скрыты")
        return {"FINISHED"}


class VIU_OT_StudioApplyHeight(bpy.types.Operator):
    bl_idname = "viu.studio_apply_height"
    bl_label = "Применить рост"

    def execute(self, context):
        props = context.scene.viu_creature_studio
        entry = _current_entry()
        root = _STATE.get("creature_root")
        objs = _STATE.get("creature_objects") or []
        if not root or not entry:
            return {"CANCELLED"}
        target = float(props.target_height_m or entry.get("target_height_m") or 1.0)
        root.scale = (1.0, 1.0, 1.0)
        bpy.context.view_layer.update()
        bm = props.body_mesh if props.body_mesh and props.body_mesh != "AUTO" else (_STATE.get("body_mesh") or "")
        _place_creature(root, objs, float(_SESSION.get("creature_offset_m") or 1.35), target, bm)
        measured = _height_of_objects(objs, bm if bm else "")
        entry["target_height_m"] = target
        _write_feedback(entry, target_height_m=target, measured_height_m=measured)
        self.report({"INFO"}, f"Рост {measured:.2f}м → цель {target:.2f}м")
        return {"FINISHED"}


class VIU_OT_StudioScreenshot(bpy.types.Operator):
    bl_idname = "viu.studio_screenshot"
    bl_label = "Снять скрины"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        try:
            front, side = _render_shots(entry)
            measured = _height_of_objects(
                _STATE.get("creature_objects") or [],
                _STATE.get("body_mesh") or "",
            )
            _write_feedback(
                entry,
                photo_front=front,
                photo_side=side,
                photo_ok=False,
                measured_height_m=measured,
                target_height_m=float(entry.get("target_height_m") or 0),
            )
            self.report({"INFO"}, f"PNG: {front}")
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            traceback.print_exc()
            return {"CANCELLED"}
        return {"FINISHED"}


class VIU_OT_StudioSave(bpy.types.Operator):
    bl_idname = "viu.studio_save"
    bl_label = "Сохранить эталон"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        slug = str(entry.get("slug") or _slugify(entry.get("name")))
        out_dir = Path(str(_SESSION.get("processed_root") or "")) / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        ready = out_dir / f"{slug}_ready.blend"
        try:
            if not _save_creature_blend(ready):
                self.report({"ERROR"}, "Нет существа для сохранения")
                return {"CANCELLED"}
            measured = _height_of_objects(
                _STATE.get("creature_objects") or [],
                _STATE.get("body_mesh") or "",
            )
            _write_feedback(
                entry,
                prepared_path=str(ready),
                measured_height_m=measured,
                target_height_m=float(entry.get("target_height_m") or 0),
            )
            self.report({"INFO"}, f"Эталон (только {slug}): {ready.name}")
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class VIU_OT_StudioReportIssue(bpy.types.Operator):
    bl_idname = "viu.studio_report_issue"
    bl_label = "Заметка для Вью"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        note = (context.scene.viu_creature_studio.photo_notes or "").strip()
        if not note:
            self.report({"ERROR"}, "Напиши заметку выше")
            return {"CANCELLED"}
        slug = str(entry.get("slug") or _slugify(entry.get("name")))
        reports = Path(str(_SESSION.get("reports_dir") or ""))
        reports.mkdir(parents=True, exist_ok=True)
        viewport = reports / f"{slug}_viewport.png"
        scene = context.scene
        old_path = scene.render.filepath
        scene.render.filepath = str(viewport)
        try:
            bpy.ops.render.opengl(write_still=True)
        except Exception:
            viewport = Path("")
        scene.render.filepath = old_path
        mesh_names = [
            o.name
            for o in (_STATE.get("creature_objects") or [])
            if o.type == "MESH" and not o.hide_get()
        ]
        payload = {
            "slug": slug,
            "name": entry.get("name"),
            "source_path": entry.get("path"),
            "note": note,
            "viewport": str(viewport) if viewport else "",
            "visible_meshes": mesh_names,
        }
        report_file = reports / f"{slug}_issue.json"
        report_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _write_feedback(entry, issue_report=note, photo_notes=note, photo_ok=False)
        self.report({"INFO"}, f"Отчёт: {report_file.name}")
        return {"FINISHED"}


class VIU_OT_StudioPhotoOk(bpy.types.Operator):
    bl_idname = "viu.studio_photo_ok"
    bl_label = "Скрины ок"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        _write_feedback(entry, photo_ok=True, photo_notes="")
        self.report({"INFO"}, f"OK: {entry.get('name')}")
        return {"FINISHED"}


class VIU_OT_StudioPhotoBad(bpy.types.Operator):
    bl_idname = "viu.studio_photo_bad"
    bl_label = "Скрины плохие"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        note = context.scene.viu_creature_studio.photo_notes or "нужна правка"
        _write_feedback(entry, photo_ok=False, photo_notes=note)
        self.report({"INFO"}, "Отмечено — поправь и пересними")
        return {"FINISHED"}


class VIU_PT_CreatureStudio(bpy.types.Panel):
    bl_label = "Viu — студия существ"
    bl_idname = "VIU_PT_creature_studio"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Viu"

    def draw(self, context):
        layout = self.layout
        entry = _current_entry()
        q = _SESSION.get("queue") or []
        idx = int(_SESSION.get("index") or 0)
        if not entry:
            layout.label(text="Очередь пуста")
            return
        layout.label(text=f"{idx + 1}/{len(q)}: {entry.get('name')}", icon="OUTLINER_OB_ARMATURE")
        layout.label(text=f"slug: {entry.get('slug')}")
        layout.label(text=f"{entry.get('size_class')} / {entry.get('locomotion')}")
        col = layout.column(align=True)
        col.operator("viu.studio_prev", icon="TRIA_LEFT")
        col.operator("viu.studio_next", icon="TRIA_RIGHT")
        col.operator("viu.studio_reload", icon="FILE_REFRESH")
        layout.separator()
        layout.operator("viu.studio_hide_ik", icon="HIDE_ON")
        layout.operator("viu.studio_show_body", icon="MESH_DATA")
        props = context.scene.viu_creature_studio
        layout.prop(props, "target_height_m")
        layout.label(text=f"Меш: {props.body_mesh or 'AUTO'}")
        meshes = [o.name for o in (_STATE.get('creature_objects') or []) if o.type == 'MESH']
        if meshes:
            layout.label(text=", ".join(meshes[:4])[:60], icon="MESH_DATA")
        layout.operator("viu.studio_apply_height", icon="ARROW_LEFTRIGHT")
        layout.separator()
        layout.label(text="Save = только текущее существо", icon="INFO")
        layout.separator()
        layout.operator("viu.studio_screenshot", icon="RENDER_STILL")
        layout.operator("viu.studio_save", icon="EXPORT")
        layout.prop(props, "photo_notes")
        layout.operator("viu.studio_report_issue", icon="TEXT")
        row = layout.row(align=True)
        row.operator("viu.studio_photo_ok", icon="CHECKMARK")
        row.operator("viu.studio_photo_bad", icon="CANCEL")
        if entry.get("photo_front"):
            layout.label(text="front.png есть", icon="IMAGE_DATA")


class VIU_CreatureStudioProps(bpy.types.PropertyGroup):
    target_height_m: FloatProperty(name="Рост (м)", default=1.0, min=0.05, max=20.0)
    body_mesh: StringProperty(name="Меш роста", default="AUTO", description="AUTO или имя меша")
    photo_notes: StringProperty(name="Заметка", default="")


_CLASSES = (
    VIU_CreatureStudioProps,
    VIU_OT_StudioPrev,
    VIU_OT_StudioNext,
    VIU_OT_StudioReload,
    VIU_OT_StudioHideIk,
    VIU_OT_StudioShowBody,
    VIU_OT_StudioApplyHeight,
    VIU_OT_StudioScreenshot,
    VIU_OT_StudioSave,
    VIU_OT_StudioReportIssue,
    VIU_OT_StudioPhotoOk,
    VIU_OT_StudioPhotoBad,
    VIU_PT_CreatureStudio,
)


def load_session(session_path: str) -> None:
    global _SESSION
    path = Path(session_path)
    _SESSION = json.loads(path.read_text(encoding="utf-8"))
    # новая сцена
    bpy.ops.wm.read_homefile(use_empty=True)
    _ensure_shanya()
    entry = _current_entry()
    if entry:
        msg = _load_creature_entry(entry)
        print("VIU_STUDIO_LOAD", msg)
        props = bpy.context.scene.viu_creature_studio
        props.target_height_m = float(entry.get("target_height_m") or 1.0)
        props.photo_notes = str(entry.get("photo_notes") or "")


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.viu_creature_studio = bpy.props.PointerProperty(type=VIU_CreatureStudioProps)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.viu_creature_studio
