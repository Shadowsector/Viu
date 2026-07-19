"""Viu Creature Studio — панель в Blender для разметки существ по одному."""
bl_info = {
    "name": "Viu Creature Studio",
    "author": "Viu",
    "version": (0, 1, 0),
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
    "body_mesh": "",
}

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
    for key in ("creature_root",):
        obj = _STATE.get(key)
        if obj and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for obj in list(_STATE.get("creature_objects") or []):
        try:
            if obj and obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        except ReferenceError:
            pass
    _STATE["creature_root"] = None
    _STATE["creature_objects"] = []
    _STATE["body_mesh"] = ""


def _import_asset(path: Path):
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


def _wrap_root(imported, name):
    root = bpy.data.objects.new("VIU_CREATURE_ROOT", None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.2
    bpy.context.collection.objects.link(root)
    imported_set = set(imported)
    for o in imported:
        if o.parent is None or o.parent not in imported_set:
            mw = o.matrix_world.copy()
            o.parent = root
            o.matrix_world = mw
    bpy.context.view_layer.update()
    return root


def _skip_mesh(name: str) -> bool:
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
    path = str(_SESSION.get("shanya_path") or "")
    if not path or not Path(path).is_file():
        return
    imported = _import_asset(Path(path))
    root = _wrap_root(imported, "Shanya")
    root.name = "VIU_SHANYA_ROOT"
    target = float(_SESSION.get("shanya_target_m") or 1.70)
    h = _height_of_objects(imported)
    if h > 1e-6:
        root.scale *= target / h
    root.location = (0.0, 0.0, 0.0)
    _STATE["shanya_root"] = root
    _hide_helpers(imported)


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
    imported = _import_asset(path)
    root = _wrap_root(imported, entry.get("name") or "creature")
    _hide_helpers(imported)
    target = float(entry.get("target_height_m") or 1.0)
    offset = float(_SESSION.get("creature_offset_m") or 1.35)
    body = _STATE.get("body_mesh") or "AUTO"
    bm = "" if body == "AUTO" else body
    _place_creature(root, imported, offset, target, bm)
    _STATE["creature_root"] = root
    _STATE["creature_objects"] = imported
    # авто body mesh
    meshes = [o for o in imported if o.type == "MESH" and not _skip_mesh(o.name)]
    if meshes:
        best = max(meshes, key=lambda o: len(o.data.vertices) if o.data else 0)
        _STATE["body_mesh"] = best.name
    return f"Загружено: {entry.get('name')}"


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
            bpy.ops.wm.save_as_mainfile(filepath=str(ready), copy=True)
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
            self.report({"INFO"}, f"Эталон: {ready.name}")
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
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
        props = context.scene.viu_creature_studio
        layout.prop(props, "target_height_m")
        layout.label(text=f"Меш: {props.body_mesh or 'AUTO'}")
        meshes = [o.name for o in (_STATE.get('creature_objects') or []) if o.type == 'MESH']
        if meshes:
            layout.label(text=", ".join(meshes[:4])[:60], icon="MESH_DATA")
        layout.operator("viu.studio_apply_height", icon="ARROW_LEFTRIGHT")
        layout.separator()
        layout.operator("viu.studio_screenshot", icon="RENDER_STILL")
        layout.operator("viu.studio_save", icon="EXPORT")
        layout.prop(props, "photo_notes")
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
    VIU_OT_StudioApplyHeight,
    VIU_OT_StudioScreenshot,
    VIU_OT_StudioSave,
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
