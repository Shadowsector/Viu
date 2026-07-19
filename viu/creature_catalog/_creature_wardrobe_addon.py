"""Viu Creature Wardrobe — наборы одежды, genital visibility."""
bl_info = {
    "name": "Viu Creature Wardrobe",
    "author": "Viu",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Viu",
    "description": "Наборы одежды: casual, swim, nsfw, bath",
    "category": "Animation",
}

import importlib.util
import json
import sys
from pathlib import Path

import bpy
from bpy.props import BoolProperty, CollectionProperty, StringProperty
from bpy.types import PropertyGroup

_SESSION: dict = {}
_STATE = {"root": None, "objects": []}
_SLOT = "VIU_WardrobeSlot"
_ROOT = "VIU_WARDROBE_ROOT"


def _load_shared():
    p = Path(__file__).resolve().parent / "viu_creature_blender_shared.py"
    name = "viu_creature_blender_shared"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(p))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load_shared()


def _current_entry() -> dict:
    q = _SESSION.get("queue") or []
    idx = int(_SESSION.get("index") or 0)
    if not q:
        return {}
    return q[max(0, min(idx, len(q) - 1))]


def _feedback_path() -> Path:
    return Path(str(_SESSION.get("feedback_path") or ""))


def _outfit_path(entry: dict) -> Path:
    return Path(str(entry.get("outfit_sets_path") or ""))


def _load_outfit_doc(entry: dict) -> dict:
    path = _outfit_path(entry)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    slug = str(entry.get("slug") or S.slugify(entry.get("name")))
    return {"slug": slug, "name": entry.get("name") or slug, "sets": []}


def _save_outfit_doc(entry: dict, data: dict) -> Path:
    path = _outfit_path(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _clear():
    S.clear_collection_slot(_SLOT, _ROOT)
    _STATE["root"] = None
    _STATE["objects"] = []


def _load_entry(entry: dict) -> str:
    _clear()
    path = Path(str(entry.get("path") or ""))
    if not path.is_file():
        return f"Нет prepared: {path}"
    slot = S.ensure_collection(_SLOT)
    imported = S.import_asset(path, target_coll=slot)
    root = S.wrap_root(imported, root_name=_ROOT, target_coll=slot)
    S.hide_helpers(imported)
    _STATE["root"] = root
    _STATE["objects"] = imported
    meshes = [o.name for o in imported if o.type == "MESH" and not S.is_wgt_name(o.name)]
    return f"Wardrobe: {entry.get('name')} ({len(meshes)} мешей)"


def _mesh_objects():
    return [o for o in (_STATE.get("objects") or []) if o.type == "MESH" and not S.is_wgt_name(o.name)]


class VIU_WardrobeMeshItem(PropertyGroup):
    name: StringProperty(name="Mesh")


class VIU_OT_WardrobePrev(bpy.types.Operator):
    bl_idname = "viu.wardrobe_prev"
    bl_label = "Предыдущее"

    def execute(self, context):
        q = _SESSION.get("queue") or []
        if not q:
            return {"CANCELLED"}
        _SESSION["index"] = (int(_SESSION.get("index") or 0) - 1) % len(q)
        _load_entry(_current_entry())
        return {"FINISHED"}


class VIU_OT_WardrobeNext(bpy.types.Operator):
    bl_idname = "viu.wardrobe_next"
    bl_label = "Следующее"

    def execute(self, context):
        q = _SESSION.get("queue") or []
        if not q:
            return {"CANCELLED"}
        _SESSION["index"] = (int(_SESSION.get("index") or 0) + 1) % len(q)
        _load_entry(_current_entry())
        return {"FINISHED"}


class VIU_OT_WardrobeToggleMesh(bpy.types.Operator):
    bl_idname = "viu.wardrobe_toggle_mesh"
    bl_label = "Переключить меш"
    mesh_name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.mesh_name)
        if obj and obj.type == "MESH":
            hide = not obj.hide_get()
            obj.hide_set(hide)
            obj.hide_render = hide
        warn = S.clothing_genital_clipping_warning(_STATE.get("objects") or [])
        context.scene.viu_creature_wardrobe.clip_warning = warn
        return {"FINISHED"}


class VIU_OT_WardrobeBodyOnly(bpy.types.Operator):
    bl_idname = "viu.wardrobe_body_only"
    bl_label = "Только тело"

    def execute(self, context):
        for obj in _mesh_objects():
            if S.is_body_mesh_name(obj.name):
                obj.hide_set(False)
                obj.hide_render = False
            else:
                obj.hide_set(True)
                obj.hide_render = True
        S.set_genital_meshes_visible(_STATE.get("objects") or [], False)
        return {"FINISHED"}


class VIU_OT_WardrobeHideClothes(bpy.types.Operator):
    bl_idname = "viu.wardrobe_hide_clothes"
    bl_label = "Снять одежду"

    def execute(self, context):
        for obj in _mesh_objects():
            if S.is_clothing_mesh(obj.name):
                obj.hide_set(True)
                obj.hide_render = True
        return {"FINISHED"}


class VIU_OT_WardrobeShowGenital(bpy.types.Operator):
    bl_idname = "viu.wardrobe_show_genital"
    bl_label = "Показать genital mesh"

    def execute(self, context):
        n = S.set_genital_meshes_visible(_STATE.get("objects") or [], True)
        warn = S.clothing_genital_clipping_warning(_STATE.get("objects") or [])
        context.scene.viu_creature_wardrobe.clip_warning = warn
        self.report({"INFO"}, f"Genital mesh: {n}")
        return {"FINISHED"}


class VIU_OT_WardrobeHideGenital(bpy.types.Operator):
    bl_idname = "viu.wardrobe_hide_genital"
    bl_label = "Спрятать genital mesh"

    def execute(self, context):
        n = S.set_genital_meshes_visible(_STATE.get("objects") or [], False)
        context.scene.viu_creature_wardrobe.clip_warning = ""
        self.report({"INFO"}, f"Скрыто genital: {n}")
        return {"FINISHED"}


class VIU_OT_WardrobeSaveSet(bpy.types.Operator):
    bl_idname = "viu.wardrobe_save_set"
    bl_label = "Сохранить набор"

    def execute(self, context):
        entry = _current_entry()
        props = context.scene.viu_creature_wardrobe
        set_id = (props.set_id or "").strip()
        if not set_id:
            self.report({"ERROR"}, "Укажи id набора (casual_01, swim_01…)")
            return {"CANCELLED"}
        snap = S.mesh_visibility_snapshot(_STATE.get("objects") or [])
        data = _load_outfit_doc(entry)
        rows = {s.get("id"): s for s in data.get("sets") or [] if isinstance(s, dict)}
        rows[set_id] = {
            "id": set_id,
            "label": (props.set_label or set_id).strip(),
            "confirmed": bool(props.set_confirmed),
            "show_meshes": snap["show_meshes"],
            "hide_meshes": snap["hide_meshes"],
            "hide_genital_mesh": not snap["genital_mesh_visible"],
            "genital_mesh_visible": snap["genital_mesh_visible"],
            "clothing_visible": snap["clothing_visible"],
            "notes": (props.set_notes or "").strip(),
        }
        data["sets"] = sorted(rows.values(), key=lambda s: s.get("id") or "")
        out = _save_outfit_doc(entry, data)
        genital_rig = "attached" if snap["genital_mesh_visible"] else (
            "pending" if any(S.is_genital_mesh(o.name) for o in _mesh_objects()) else "none"
        )
        confirmed_n = sum(1 for s in data["sets"] if s.get("confirmed"))
        S.write_feedback_file(
            _feedback_path(),
            entry,
            outfit_sets_path=str(out),
            outfit_sets_confirmed=confirmed_n,
            genital_rig=genital_rig,
            wardrobe_notes=props.set_notes or "",
        )
        self.report({"INFO"}, f"Набор {set_id} → {out.name}")
        return {"FINISHED"}


class VIU_OT_WardrobeLoadSet(bpy.types.Operator):
    bl_idname = "viu.wardrobe_load_set"
    bl_label = "Загрузить набор"

    def execute(self, context):
        entry = _current_entry()
        set_id = (context.scene.viu_creature_wardrobe.set_id or "").strip()
        data = _load_outfit_doc(entry)
        row = next((s for s in data.get("sets") or [] if s.get("id") == set_id), None)
        if not row:
            self.report({"ERROR"}, f"Нет набора {set_id}")
            return {"CANCELLED"}
        S.apply_mesh_visibility(
            _STATE.get("objects") or [],
            row.get("show_meshes") or [],
            row.get("hide_meshes") or [],
        )
        if row.get("hide_genital_mesh"):
            S.set_genital_meshes_visible(_STATE.get("objects") or [], False)
        context.scene.viu_creature_wardrobe.clip_warning = S.clothing_genital_clipping_warning(
            _STATE.get("objects") or []
        )
        self.report({"INFO"}, f"Загружен {set_id}")
        return {"FINISHED"}


class VIU_PT_CreatureWardrobe(bpy.types.Panel):
    bl_label = "Viu — wardrobe"
    bl_idname = "VIU_PT_creature_wardrobe"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Viu"

    def draw(self, context):
        layout = self.layout
        entry = _current_entry()
        if not entry:
            layout.label(text="Очередь пуста")
            return
        q = _SESSION.get("queue") or []
        idx = int(_SESSION.get("index") or 0)
        layout.label(text=f"{idx + 1}/{len(q)}: {entry.get('name')}")
        col = layout.column(align=True)
        col.operator("viu.wardrobe_prev", icon="TRIA_LEFT")
        col.operator("viu.wardrobe_next", icon="TRIA_RIGHT")
        layout.separator()
        layout.operator("viu.wardrobe_body_only", icon="ARMATURE_DATA")
        layout.operator("viu.wardrobe_hide_clothes", icon="HIDE_ON")
        row = layout.row(align=True)
        row.operator("viu.wardrobe_show_genital", icon="HIDE_OFF")
        row.operator("viu.wardrobe_hide_genital", icon="HIDE_ON")
        props = context.scene.viu_creature_wardrobe
        if props.clip_warning:
            layout.label(text=props.clip_warning, icon="ERROR")
        layout.separator()
        layout.label(text="Меши (клик — видимость):")
        meshes = _mesh_objects()[:16]
        for obj in meshes:
            icon = "HIDE_OFF" if not obj.hide_get() else "HIDE_ON"
            op = layout.operator("viu.wardrobe_toggle_mesh", text=obj.name[:28], icon=icon)
            op.mesh_name = obj.name
        if len(_mesh_objects()) > 16:
            layout.label(text=f"… +{len(_mesh_objects()) - 16} мешей")
        layout.separator()
        layout.prop(props, "set_id")
        layout.prop(props, "set_label")
        layout.prop(props, "set_notes")
        layout.prop(props, "set_confirmed")
        layout.operator("viu.wardrobe_save_set", icon="EXPORT")
        layout.operator("viu.wardrobe_load_set", icon="IMPORT")


class VIU_CreatureWardrobeProps(bpy.types.PropertyGroup):
    set_id: StringProperty(name="ID набора", default="casual_01")
    set_label: StringProperty(name="Название", default="Casual")
    set_notes: StringProperty(name="Заметка", default="")
    set_confirmed: BoolProperty(name="Подтверждён ✓", default=False)
    clip_warning: StringProperty(name="", default="")


_CLASSES = (
    VIU_WardrobeMeshItem,
    VIU_CreatureWardrobeProps,
    VIU_OT_WardrobePrev,
    VIU_OT_WardrobeNext,
    VIU_OT_WardrobeToggleMesh,
    VIU_OT_WardrobeBodyOnly,
    VIU_OT_WardrobeHideClothes,
    VIU_OT_WardrobeShowGenital,
    VIU_OT_WardrobeHideGenital,
    VIU_OT_WardrobeSaveSet,
    VIU_OT_WardrobeLoadSet,
    VIU_PT_CreatureWardrobe,
)


def load_session(session_path: str) -> None:
    global _SESSION
    _SESSION = json.loads(Path(session_path).read_text(encoding="utf-8"))
    bpy.ops.wm.read_homefile(use_empty=True)
    entry = _current_entry()
    if entry:
        print("VIU_WARDROBE_LOAD", _load_entry(entry))


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.viu_creature_wardrobe = bpy.props.PointerProperty(type=VIU_CreatureWardrobeProps)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.viu_creature_wardrobe
