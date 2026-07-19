"""Viu Creature Prep — подготовка моделей из Inbox (очистка, текстуры, A-pose, blend)."""
bl_info = {
    "name": "Viu Creature Prep",
    "author": "Viu",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Viu",
    "description": "Подготовка существ: очистка, Bursting Head, текстуры, save blend",
    "category": "Animation",
}

import importlib.util
import json
import sys
import traceback
from pathlib import Path

import bpy
from bpy.props import StringProperty

_SESSION: dict = {}
_STATE = {"root": None, "objects": []}

_SLOT = "VIU_PrepSlot"
_ROOT = "VIU_PREP_ROOT"


def _load_shared():
    p = Path(__file__).resolve().parent / "viu_creature_blender_shared.py"
    name = "viu_creature_blender_shared"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(p))
    if spec is None or spec.loader is None:
        raise RuntimeError("shared missing: " + str(p))
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
    idx = max(0, min(idx, len(q) - 1))
    return q[idx]


def _feedback_path() -> Path:
    return Path(str(_SESSION.get("feedback_path") or ""))


def _clear():
    S.clear_collection_slot(_SLOT, _ROOT)
    _STATE["root"] = None
    _STATE["objects"] = []


def _load_entry(entry: dict) -> str:
    _clear()
    src = Path(str(entry.get("path") or ""))
    if not src.is_file():
        return f"Нет файла: {src}"
    slot = S.ensure_collection(_SLOT)
    imported = S.import_asset(src, target_coll=slot)
    root = S.wrap_root(imported, root_name=_ROOT, target_coll=slot)
    S.hide_helpers(imported)
    _STATE["root"] = root
    _STATE["objects"] = imported
    body = [o for o in imported if o.type == "MESH" and not o.hide_get()]
    if not body:
        return f"Загружено: {entry.get('name')} — ⚠ тела не видно (только WGT/риг?)"
    return f"Загружено: {entry.get('name')} ({len(body)} мешей)"


class VIU_OT_PrepPrev(bpy.types.Operator):
    bl_idname = "viu.prep_prev"
    bl_label = "Предыдущее"

    def execute(self, context):
        q = _SESSION.get("queue") or []
        if not q:
            return {"CANCELLED"}
        _SESSION["index"] = (int(_SESSION.get("index") or 0) - 1) % len(q)
        _load_entry(_current_entry())
        return {"FINISHED"}


class VIU_OT_PrepNext(bpy.types.Operator):
    bl_idname = "viu.prep_next"
    bl_label = "Следующее"

    def execute(self, context):
        q = _SESSION.get("queue") or []
        if not q:
            return {"CANCELLED"}
        _SESSION["index"] = (int(_SESSION.get("index") or 0) + 1) % len(q)
        _load_entry(_current_entry())
        return {"FINISHED"}


class VIU_OT_PrepReload(bpy.types.Operator):
    bl_idname = "viu.prep_reload"
    bl_label = "Перезагрузить"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        self.report({"INFO"}, _load_entry(entry))
        return {"FINISHED"}


class VIU_OT_PrepHideIk(bpy.types.Operator):
    bl_idname = "viu.prep_hide_ik"
    bl_label = "Спрятать IK / WGT"

    def execute(self, context):
        S.hide_helpers(_STATE.get("objects") or [])
        self.report({"INFO"}, "IK / WGT скрыты")
        return {"FINISHED"}


class VIU_OT_PrepShowBody(bpy.types.Operator):
    bl_idname = "viu.prep_show_body"
    bl_label = "Показать меши тела"

    def execute(self, context):
        shown = 0
        for obj in _STATE.get("objects") or []:
            if obj.type != "MESH" or S.is_wgt_name(obj.name):
                continue
            obj.hide_set(False)
            obj.hide_render = False
            shown += 1
        self.report({"INFO"}, f"Показано мешей: {shown}")
        return {"FINISHED"}


class VIU_OT_PrepBurstingHead(bpy.types.Operator):
    bl_idname = "viu.prep_bursting_head"
    bl_label = "Bursting Head Repair"

    def execute(self, context):
        objs = _STATE.get("objects") or []
        bones, drivers, msg = S.repair_bursting_head(objs)
        self.report({"INFO" if bones else "WARNING"}, f"Bursting Head: {msg}")
        return {"FINISHED"}


class VIU_OT_PrepCheckTextures(bpy.types.Operator):
    bl_idname = "viu.prep_check_textures"
    bl_label = "Проверить текстуры"

    def execute(self, context):
        ok, missing, lines = S.check_textures(_STATE.get("objects") or [])
        props = context.scene.viu_creature_prep
        if lines:
            props.texture_report = "\n".join(lines)
        else:
            props.texture_report = f"OK: {ok} текстур"
        self.report(
            {"INFO" if missing == 0 else "WARNING"},
            f"Текстуры OK={ok}, missing={missing}",
        )
        return {"FINISHED"}


class VIU_OT_PrepClearPose(bpy.types.Operator):
    bl_idname = "viu.prep_clear_pose"
    bl_label = "Сбросить позу (rest)"

    def execute(self, context):
        n = S.clear_pose_transforms(_STATE.get("objects") or [])
        self.report({"INFO"}, f"Сброшено костей: {n}. A-pose — вручную.")
        return {"FINISHED"}


class VIU_OT_PrepSave(bpy.types.Operator):
    bl_idname = "viu.prep_save"
    bl_label = "Сохранить prepared.blend"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        slug = str(entry.get("slug") or S.slugify(entry.get("name")))
        out_dir = Path(str(_SESSION.get("prepared_root") or "")) / slug
        out = out_dir / f"{slug}_prepared.blend"
        objs = S.gather_under_root(_STATE.get("root"))
        try:
            if not S.save_objects_blend(out, objs):
                self.report({"ERROR"}, "Не удалось сохранить blend")
                return {"CANCELLED"}
            note = (context.scene.viu_creature_prep.prep_notes or "").strip()
            S.write_feedback_file(
                _feedback_path(),
                entry,
                prepared_path=str(out),
                prep_ok=True,
                prep_notes=note,
            )
            self.report({"INFO"}, f"Prepared: {out.name}")
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            traceback.print_exc()
            return {"CANCELLED"}
        return {"FINISHED"}


class VIU_OT_PrepReport(bpy.types.Operator):
    bl_idname = "viu.prep_report"
    bl_label = "Заметка для Вью"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        note = (context.scene.viu_creature_prep.prep_notes or "").strip()
        if not note:
            self.report({"ERROR"}, "Напиши заметку")
            return {"CANCELLED"}
        S.write_feedback_file(_feedback_path(), entry, prep_notes=note, prep_ok=False)
        self.report({"INFO"}, "Заметка записана")
        return {"FINISHED"}


class VIU_PT_CreaturePrep(bpy.types.Panel):
    bl_label = "Viu — подготовка"
    bl_idname = "VIU_PT_creature_prep"
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
        layout.label(text=f"{idx + 1}/{len(q)}: {entry.get('name')}")
        layout.label(text=f"slug: {entry.get('slug')}")
        col = layout.column(align=True)
        col.operator("viu.prep_prev", icon="TRIA_LEFT")
        col.operator("viu.prep_next", icon="TRIA_RIGHT")
        col.operator("viu.prep_reload", icon="FILE_REFRESH")
        layout.separator()
        layout.operator("viu.prep_hide_ik", icon="HIDE_ON")
        layout.operator("viu.prep_show_body", icon="MESH_DATA")
        layout.operator("viu.prep_bursting_head", icon="MODIFIER")
        layout.operator("viu.prep_check_textures", icon="TEXTURE")
        layout.operator("viu.prep_clear_pose", icon="ARMATURE_DATA")
        props = context.scene.viu_creature_prep
        if props.texture_report:
            layout.label(text=props.texture_report[:80])
        layout.prop(props, "prep_notes")
        layout.separator()
        layout.label(text="Save = только эта модель", icon="INFO")
        layout.operator("viu.prep_save", icon="EXPORT")
        layout.operator("viu.prep_report", icon="TEXT")


class VIU_CreaturePrepProps(bpy.types.PropertyGroup):
    prep_notes: StringProperty(name="Заметка", default="")
    texture_report: StringProperty(name="Текстуры", default="")


_CLASSES = (
    VIU_CreaturePrepProps,
    VIU_OT_PrepPrev,
    VIU_OT_PrepNext,
    VIU_OT_PrepReload,
    VIU_OT_PrepHideIk,
    VIU_OT_PrepShowBody,
    VIU_OT_PrepBurstingHead,
    VIU_OT_PrepCheckTextures,
    VIU_OT_PrepClearPose,
    VIU_OT_PrepSave,
    VIU_OT_PrepReport,
    VIU_PT_CreaturePrep,
)


def load_session(session_path: str) -> None:
    global _SESSION
    _SESSION = json.loads(Path(session_path).read_text(encoding="utf-8"))
    bpy.ops.wm.read_homefile(use_empty=True)
    entry = _current_entry()
    if entry:
        msg = _load_entry(entry)
        print("VIU_PREP_LOAD", msg)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.viu_creature_prep = bpy.props.PointerProperty(type=VIU_CreaturePrepProps)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.viu_creature_prep
