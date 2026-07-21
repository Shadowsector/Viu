"""Viu Creature Wardrobe — наборы одежды, genital visibility."""
bl_info = {
    "name": "Viu Creature Wardrobe",
    "author": "Viu",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Viu",
    "description": "Наборы одежды: Casual/Fitness/Swimsuit… + внешность (кожа/волосы)",
    "category": "Animation",
}

import importlib.util
import json
import sys
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

_SESSION: dict = {}
_STATE = {"root": None, "objects": [], "import_colls": []}
_GENITAL_ITEMS = [("none", "нет половых органов", "")]
_SKIN_ITEMS = [("default", "как в файле", "")]
_HAIR_ITEMS = [("default", "как в файле", "")]
_SLOT = "VIU_WardrobeSlot"
_ROOT = "VIU_WARDROBE_ROOT"

_OUTFIT_TYPE_ITEMS = [
    ("casual", "Casual", ""),
    ("fitness", "Fitness", ""),
    ("swimsuit", "Swimsuit", ""),
    ("pajama", "Pajama", ""),
    ("undies", "Undies", ""),
    ("lingerie", "Lingerie", ""),
    ("half_nude", "Half-nude", ""),
    ("nude", "Nude", ""),
]
_OUTFIT_LABEL = {k: v for k, v, _ in _OUTFIT_TYPE_ITEMS}
_OUTFIT_VARIANT_ITEMS = [("01", "1", ""), ("02", "2", ""), ("03", "3", "")]


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


def _outfit_set_id(type_id: str, variant: str) -> str:
    v = (variant or "01").strip()
    if v.isdigit() and len(v) == 1:
        v = f"0{v}"
    if v not in ("01", "02", "03"):
        v = "01"
    return f"{type_id}_{v}"


def _clear():
    S.clear_collection_slot(
        _SLOT,
        _ROOT,
        tracked_objects=_STATE.get("objects"),
        root=_STATE.get("root"),
        import_collections=_STATE.get("import_colls"),
    )
    _STATE["root"] = None
    _STATE["objects"] = []
    _STATE["import_colls"] = []


def _load_entry(entry: dict) -> str:
    _clear()
    path = Path(str(entry.get("path") or ""))
    if not path.is_file():
        return f"Нет prepared: {path}"
    slot = S.ensure_collection(_SLOT)
    imported, import_colls = S.import_asset(path, target_coll=slot)
    root = S.wrap_root(imported, root_name=_ROOT, target_coll=slot)
    S.hide_rig_viewport(imported)
    _STATE["root"] = root
    _STATE["objects"] = imported
    _STATE["import_colls"] = import_colls
    meshes = [o for o in imported if o.type == "MESH" and not S.skip_mesh(o.name)]
    return f"Wardrobe: {entry.get('name')} ({len(meshes)} мешей)"


def _sync_props_from_entry(context, entry: dict) -> None:
    props = context.scene.viu_creature_wardrobe
    gp = str(entry.get("genital_profile") or "none")
    valid_gp = {i[0] for i in _GENITAL_ITEMS}
    props.genital_profile = gp if gp in valid_gp else "none"
    st = str(entry.get("skin_tone") or "default")
    valid_st = {i[0] for i in _SKIN_ITEMS}
    props.skin_tone = st if st in valid_st else "default"
    hc = str(entry.get("hair_color") or "default")
    valid_hc = {i[0] for i in _HAIR_ITEMS}
    props.hair_color = hc if hc in valid_hc else "default"


def _apply_appearance(context) -> tuple[int, int]:
    props = context.scene.viu_creature_wardrobe
    return S.apply_creature_appearance(
        _STATE.get("objects") or [],
        skin_tone=props.skin_tone or "default",
        hair_color=props.hair_color or "default",
    )


def _mesh_objects():
    return [o for o in (_STATE.get("objects") or []) if o.type == "MESH" and not S.skip_mesh(o.name)]


def _categorized_meshes():
    clothing, body, other = [], [], []
    for obj in _mesh_objects():
        if S.is_clothing_mesh(obj.name):
            clothing.append(obj)
        elif S.is_body_mesh_name(obj.name):
            body.append(obj)
        else:
            other.append(obj)
    return clothing, body, other


def _draw_mesh_buttons(layout, objects, *, prefix: str = ""):
    for obj in objects:
        icon = "HIDE_OFF" if not obj.hide_get() else "HIDE_ON"
        label = (prefix + obj.name)[:36]
        op = layout.operator("viu.wardrobe_toggle_mesh", text=label, icon=icon)
        op.mesh_name = obj.name


class VIU_OT_WardrobePrev(bpy.types.Operator):
    bl_idname = "viu.wardrobe_prev"
    bl_label = "Предыдущее"

    def execute(self, context):
        q = _SESSION.get("queue") or []
        if not q:
            return {"CANCELLED"}
        idx = int(_SESSION.get("index") or 0)
        if idx <= 0:
            self.report({"INFO"}, "Уже первая модель")
            return {"FINISHED"}
        _SESSION["index"] = idx - 1
        _load_entry(_current_entry())
        _sync_props_from_entry(context, _current_entry())
        skin_n, hair_n = _apply_appearance(context)
        if skin_n or hair_n:
            self.report({"INFO"}, f"Внешность: кожа {skin_n}, волосы {hair_n}")
        return {"FINISHED"}


class VIU_OT_WardrobeNext(bpy.types.Operator):
    bl_idname = "viu.wardrobe_next"
    bl_label = "Следующее"

    def execute(self, context):
        q = _SESSION.get("queue") or []
        if not q:
            return {"CANCELLED"}
        idx = int(_SESSION.get("index") or 0)
        if idx >= len(q) - 1:
            self.report(
                {"INFO"},
                "Конец очереди. Синхр. wardrobe во Вью и открой снова для оставшихся.",
            )
            return {"FINISHED"}
        _SESSION["index"] = idx + 1
        _load_entry(_current_entry())
        _sync_props_from_entry(context, _current_entry())
        skin_n, hair_n = _apply_appearance(context)
        if skin_n or hair_n:
            self.report({"INFO"}, f"Внешность: кожа {skin_n}, волосы {hair_n}")
        return {"FINISHED"}


class VIU_OT_WardrobeHideRig(bpy.types.Operator):
    bl_idname = "viu.wardrobe_hide_rig"
    bl_label = "Спрятать риг / IK / cs_"

    def execute(self, context):
        S.hide_rig_viewport(_STATE.get("objects") or [])
        self.report({"INFO"}, "Риг и хелперы скрыты")
        return {"FINISHED"}


class VIU_OT_WardrobeToggleMesh(bpy.types.Operator):
    bl_idname = "viu.wardrobe_toggle_mesh"
    bl_label = "Переключить меш"
    mesh_name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.mesh_name)
        if obj and obj.type == "MESH":
            hide = not obj.hide_get()
            S.set_mesh_viewport_visible(obj, not hide)
        warn = S.clothing_genital_clipping_warning(_STATE.get("objects") or [])
        context.scene.viu_creature_wardrobe.clip_warning = warn
        return {"FINISHED"}


class VIU_OT_WardrobeBodyOnly(bpy.types.Operator):
    bl_idname = "viu.wardrobe_body_only"
    bl_label = "Только тело"

    def execute(self, context):
        for obj in _mesh_objects():
            if S.is_body_mesh_name(obj.name):
                S.set_mesh_viewport_visible(obj, True)
            else:
                S.set_mesh_viewport_visible(obj, False)
        S.set_genital_meshes_visible(_STATE.get("objects") or [], False)
        return {"FINISHED"}


class VIU_OT_WardrobeHideClothes(bpy.types.Operator):
    bl_idname = "viu.wardrobe_hide_clothes"
    bl_label = "Снять одежду"

    def execute(self, context):
        for obj in _mesh_objects():
            if S.is_clothing_mesh(obj.name):
                S.set_mesh_viewport_visible(obj, False)
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


class VIU_OT_WardrobeApplyAppearance(bpy.types.Operator):
    bl_idname = "viu.wardrobe_apply_appearance"
    bl_label = "Применить кожу и волосы"

    def execute(self, context):
        skin_n, hair_n = _apply_appearance(context)
        props = context.scene.viu_creature_wardrobe
        entry = _current_entry()
        if entry:
            _sync_feedback(entry, _load_outfit_doc(entry), S.mesh_visibility_snapshot(_STATE.get("objects") or []), props)
        self.report({"INFO"}, f"Кожа: {skin_n} меш(ей), волосы: {hair_n}")
        return {"FINISHED"}


class VIU_OT_WardrobeSaveAnatomy(bpy.types.Operator):
    bl_idname = "viu.wardrobe_save_anatomy"
    bl_label = "Сохранить анатомию / внешность"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        props = context.scene.viu_creature_wardrobe
        snap = S.mesh_visibility_snapshot(_STATE.get("objects") or [])
        data = _load_outfit_doc(entry)
        _sync_feedback(entry, data, snap, props)
        gp_label = next(
            (lbl for gid, lbl, _ in _GENITAL_ITEMS if gid == props.genital_profile),
            props.genital_profile,
        )
        self.report({"INFO"}, f"Сохранено: {gp_label}")
        return {"FINISHED"}


class VIU_OT_WardrobeHideGenital(bpy.types.Operator):
    bl_idname = "viu.wardrobe_hide_genital"
    bl_label = "Спрятать genital mesh"

    def execute(self, context):
        n = S.set_genital_meshes_visible(_STATE.get("objects") or [], False)
        context.scene.viu_creature_wardrobe.clip_warning = ""
        self.report({"INFO"}, f"Скрыто genital: {n}")
        return {"FINISHED"}


def _write_outfit_set(entry: dict, props, type_id: str, variant: str, snap: dict) -> str:
    set_id = _outfit_set_id(type_id, variant)
    label = _OUTFIT_LABEL.get(type_id, type_id)
    data = _load_outfit_doc(entry)
    rows = {s.get("id"): s for s in data.get("sets") or [] if isinstance(s, dict)}
    rows[set_id] = {
        "id": set_id,
        "label": label,
        "variant": variant,
        "outfit_type": type_id,
        "confirmed": bool(props.set_confirmed),
        "show_meshes": snap["show_meshes"],
        "hide_meshes": snap["hide_meshes"],
        "hide_genital_mesh": not snap["genital_mesh_visible"],
        "genital_mesh_visible": snap["genital_mesh_visible"],
        "clothing_visible": snap["clothing_visible"],
        "notes": (props.set_notes or "").strip(),
    }
    data["sets"] = sorted(rows.values(), key=lambda s: s.get("id") or "")
    _save_outfit_doc(entry, data)
    return set_id


def _sync_feedback(entry: dict, data: dict, snap: dict, props) -> None:
    gp = props.genital_profile or entry.get("genital_profile") or "none"
    if gp == "penis_planned":
        genital_rig = "pending"
    elif snap["genital_mesh_visible"]:
        genital_rig = "attached"
    elif any(S.is_genital_mesh(o.name) for o in _mesh_objects()):
        genital_rig = "pending"
    else:
        genital_rig = "none"
    confirmed_n = sum(1 for s in data.get("sets") or [] if isinstance(s, dict) and s.get("confirmed"))
    out = _outfit_path(entry)
    S.write_feedback_file(
        _feedback_path(),
        entry,
        outfit_sets_path=str(out),
        outfit_sets_confirmed=confirmed_n,
        genital_profile=gp,
        genital_rig=genital_rig,
        skin_tone=props.skin_tone or "default",
        hair_color=props.hair_color or "default",
        wardrobe_notes=props.set_notes or "",
    )


class VIU_OT_WardrobeSaveSet(bpy.types.Operator):
    bl_idname = "viu.wardrobe_save_set"
    bl_label = "Сохранить набор"

    def execute(self, context):
        entry = _current_entry()
        props = context.scene.viu_creature_wardrobe
        type_id = props.outfit_type or "casual"
        variant = props.outfit_variant or "01"
        snap = S.mesh_visibility_snapshot(_STATE.get("objects") or [])
        set_id = _write_outfit_set(entry, props, type_id, variant, snap)
        data = _load_outfit_doc(entry)
        _sync_feedback(entry, data, snap, props)
        label = _OUTFIT_LABEL.get(type_id, type_id)
        self.report({"INFO"}, f"Сохранено {label} {int(variant)} → {set_id}")
        return {"FINISHED"}


class VIU_OT_WardrobeSaveBare(bpy.types.Operator):
    bl_idname = "viu.wardrobe_save_bare"
    bl_label = "Без одежды: Casual 1 + Nude 1"

    def execute(self, context):
        entry = _current_entry()
        props = context.scene.viu_creature_wardrobe
        snap = S.mesh_visibility_snapshot(_STATE.get("objects") or [])
        ids = []
        for type_id in ("casual", "nude"):
            ids.append(_write_outfit_set(entry, props, type_id, "01", snap))
        data = _load_outfit_doc(entry)
        _sync_feedback(entry, data, snap, props)
        self.report({"INFO"}, f"Сохранено для существа без одежды: {', '.join(ids)}")
        return {"FINISHED"}


class VIU_OT_WardrobeLoadSet(bpy.types.Operator):
    bl_idname = "viu.wardrobe_load_set"
    bl_label = "Загрузить набор"
    set_id: StringProperty(default="")

    def execute(self, context):
        entry = _current_entry()
        set_id = (self.set_id or context.scene.viu_creature_wardrobe.outfit_type_variant_id()).strip()
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
        props = context.scene.viu_creature_wardrobe
        type_id = str(row.get("outfit_type") or "")
        variant = str(row.get("variant") or "")
        if type_id:
            props.outfit_type = type_id
        if variant:
            props.outfit_variant = variant
        props.clip_warning = S.clothing_genital_clipping_warning(_STATE.get("objects") or [])
        self.report({"INFO"}, f"Загружен {row.get('label')} ({set_id})")
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
        layout.operator("viu.wardrobe_hide_rig", icon="HIDE_ON")
        layout.operator("viu.wardrobe_body_only", icon="ARMATURE_DATA")
        layout.operator("viu.wardrobe_hide_clothes", icon="HIDE_ON")
        props = context.scene.viu_creature_wardrobe
        box = layout.box()
        box.label(text="Внешность и анатомия:", icon="USER")
        box.prop(props, "skin_tone", text="Кожа")
        box.prop(props, "hair_color", text="Волосы")
        row = box.row(align=True)
        row.operator("viu.wardrobe_apply_appearance", icon="BRUSH_DATA")
        box.prop(props, "genital_profile", text="Гениталии")
        box.operator("viu.wardrobe_save_anatomy", icon="EXPORT")
        row = layout.row(align=True)
        row.operator("viu.wardrobe_show_genital", icon="HIDE_OFF")
        row.operator("viu.wardrobe_hide_genital", icon="HIDE_ON")
        if props.clip_warning:
            layout.label(text=props.clip_warning, icon="ERROR")

        clothing, body, other = _categorized_meshes()
        layout.separator()
        box = layout.box()
        box.label(text=f"Одежда ({len(clothing)}) — клик вкл/выкл:", icon="MOD_CLOTH")
        col = box.column(align=True)
        _draw_mesh_buttons(col, clothing)

        if body:
            box = layout.box()
            box.label(text=f"Тело ({len(body)}):", icon="OUTLINER_OB_MESH")
            col = box.column(align=True)
            _draw_mesh_buttons(col, body)

        if other:
            box = layout.box()
            box.label(text=f"Прочее ({len(other)}):", icon="MESH_DATA")
            col = box.column(align=True)
            _draw_mesh_buttons(col, other)

        layout.separator()
        saved = _load_outfit_doc(entry).get("sets") or []
        if saved:
            layout.label(text="Сохранённые наборы:", icon="FILE_TICK")
            for row in saved[:12]:
                if not isinstance(row, dict):
                    continue
                r = layout.row(align=True)
                mark = "✓" if row.get("confirmed") else "·"
                r.label(text=f"{mark} {row.get('label', '?')} {row.get('variant', '')[:2]}")
                op = r.operator("viu.wardrobe_load_set", text="", icon="IMPORT")
                op.set_id = str(row.get("id") or "")

        layout.separator()
        row = layout.row(align=True)
        row.prop(props, "outfit_type", text="")
        row.prop(props, "outfit_variant", text="")
        type_id = props.outfit_type or "casual"
        variant = props.outfit_variant or "01"
        label = _OUTFIT_LABEL.get(type_id, type_id)
        layout.label(text=f"→ {label} · вариант {int(variant)}  ({_outfit_set_id(type_id, variant)})")
        layout.prop(props, "set_notes")
        layout.prop(props, "set_confirmed")
        layout.operator("viu.wardrobe_save_bare", icon="OUTLINER_OB_MESH")
        layout.operator("viu.wardrobe_save_set", text=f"Сохранить {label} {int(variant)}", icon="EXPORT")


def _genital_enum_items(self, context):
    return _GENITAL_ITEMS


def _skin_enum_items(self, context):
    return _SKIN_ITEMS


def _hair_enum_items(self, context):
    return _HAIR_ITEMS


class VIU_CreatureWardrobeProps(bpy.types.PropertyGroup):
    outfit_type: EnumProperty(
        name="Тип",
        items=_OUTFIT_TYPE_ITEMS,
        default="casual",
    )
    outfit_variant: EnumProperty(
        name="Вариант",
        items=_OUTFIT_VARIANT_ITEMS,
        default="01",
    )
    set_notes: StringProperty(name="Заметка", default="")
    set_confirmed: BoolProperty(name="Подтверждён ✓", default=True)
    clip_warning: StringProperty(name="", default="")
    skin_tone: EnumProperty(name="Тон кожи", items=_skin_enum_items, default=0)
    hair_color: EnumProperty(name="Цвет волос", items=_hair_enum_items, default=0)
    genital_profile: EnumProperty(name="Гениталии", items=_genital_enum_items, default=0)

    def outfit_type_variant_id(self) -> str:
        return _outfit_set_id(self.outfit_type or "casual", self.outfit_variant or "01")


_CLASSES = (
    VIU_CreatureWardrobeProps,
    VIU_OT_WardrobePrev,
    VIU_OT_WardrobeNext,
    VIU_OT_WardrobeHideRig,
    VIU_OT_WardrobeToggleMesh,
    VIU_OT_WardrobeBodyOnly,
    VIU_OT_WardrobeHideClothes,
    VIU_OT_WardrobeShowGenital,
    VIU_OT_WardrobeApplyAppearance,
    VIU_OT_WardrobeSaveAnatomy,
    VIU_OT_WardrobeHideGenital,
    VIU_OT_WardrobeSaveBare,
    VIU_OT_WardrobeSaveSet,
    VIU_OT_WardrobeLoadSet,
    VIU_PT_CreatureWardrobe,
)


def load_session(session_path: str) -> None:
    global _SESSION, _GENITAL_ITEMS, _SKIN_ITEMS, _HAIR_ITEMS
    _SESSION = json.loads(Path(session_path).read_text(encoding="utf-8"))
    _GENITAL_ITEMS = []
    for row in _SESSION.get("genital_profiles") or []:
        gid = row.get("id") or "none"
        _GENITAL_ITEMS.append((gid, row.get("label") or gid, ""))
    if not _GENITAL_ITEMS:
        _GENITAL_ITEMS = [("none", "нет половых органов", "")]
    _SKIN_ITEMS = []
    for row in _SESSION.get("skin_tones") or []:
        sid = row.get("id") or "default"
        _SKIN_ITEMS.append((sid, row.get("label") or sid, ""))
    if not _SKIN_ITEMS:
        _SKIN_ITEMS = [("default", "как в файле", "")]
    _HAIR_ITEMS = []
    for row in _SESSION.get("hair_colors") or []:
        hid = row.get("id") or "default"
        _HAIR_ITEMS.append((hid, row.get("label") or hid, ""))
    if not _HAIR_ITEMS:
        _HAIR_ITEMS = [("default", "как в файле", "")]
    bpy.ops.wm.read_homefile(use_empty=True)
    entry = _current_entry()
    if entry:
        print("VIU_WARDROBE_LOAD", _load_entry(entry))
        if bpy.context.scene.viu_creature_wardrobe:
            _sync_props_from_entry(bpy.context, entry)
            skin_n, hair_n = _apply_appearance(bpy.context)
            print("VIU_WARDROBE_APPEARANCE", f"skin={skin_n} hair={hair_n}")


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.viu_creature_wardrobe = bpy.props.PointerProperty(type=VIU_CreatureWardrobeProps)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.viu_creature_wardrobe
