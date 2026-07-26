"""Viu Creature Studio — разметка + Шаня + рост + эталон FBX."""
bl_info = {
    "name": "Viu Creature Studio",
    "author": "Viu",
    "version": (0, 3, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Viu",
    "description": "Разметка, рост vs Шаня, скрины, эталон FBX",
    "category": "Animation",
}

import importlib.util
import json
import math
import sys
import traceback
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty

_SESSION: dict = {}
_STATE = {
    "creature_root": None,
    "creature_objects": [],
    "creature_import_colls": [],
    "shanya_root": None,
    "shanya_objects": [],
    "shanya_status": "",
    "body_mesh": "",
}

_SLOT = "VIU_CreatureSlot"
_SHANYA_COLL = "VIU_ShanyaRef"
_ROOT = "VIU_CREATURE_ROOT"

_SIZE_ITEMS = [("", "— класс —", "")]
_LOCO_ITEMS = [("unknown", "— locomotion —", "")]
_GENITAL_ITEMS = [("none", "нет", "")]


def _load_shared():
    p = Path(__file__).resolve().parent / "viu_creature_blender_shared.py"
    name = "viu_creature_blender_shared"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(p))
    if spec is None or spec.loader is None:
        raise RuntimeError("shared missing")
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


def _clear_creature():
    S.clear_collection_slot(
        _SLOT,
        _ROOT,
        tracked_objects=_STATE.get("creature_objects"),
        root=_STATE.get("creature_root"),
        import_collections=_STATE.get("creature_import_colls"),
    )
    _STATE["creature_root"] = None
    _STATE["creature_objects"] = []
    _STATE["creature_import_colls"] = []
    _STATE["body_mesh"] = ""


def _alive(obj) -> bool:
    if obj is None:
        return False
    try:
        return obj.name in bpy.data.objects
    except ReferenceError:
        return False


def _resolve_creature():
    """Rebind root/objects after addon reload or lost _STATE refs."""
    root = _STATE.get("creature_root")
    if not _alive(root):
        root = bpy.data.objects.get(_ROOT)
    objs = []
    for o in _STATE.get("creature_objects") or []:
        if _alive(o):
            objs.append(o)
    if root is not None and not objs:
        objs = [o for o in S.gather_under_root(root) if o != root]
    _STATE["creature_root"] = root
    _STATE["creature_objects"] = objs
    return root, objs


def _place_creature(root, objects, x_offset: float, target_h: float, body_mesh: str = ""):
    bpy.context.view_layer.update()
    # Move FBX scale=10 (etc.) from armature/mesh up to the wrap empty first.
    S.normalize_uniform_scales_under_root(root)
    bpy.context.view_layer.update()
    h = S.height_of_objects(objects, body_mesh)
    if h > 1e-6 and target_h > 0:
        factor = S.height_fit_multiplier(h, target_h)
        root.scale = (
            float(root.scale[0]) * factor,
            float(root.scale[1]) * factor,
            float(root.scale[2]) * factor,
        )
        bpy.context.view_layer.update()
    root.location = (x_offset, 0.0, 0.0)
    root.rotation_euler = (0.0, 0.0, 0.0)
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objects:
        pts.extend(S.mesh_points(o, deps))
    if pts:
        mins, _ = S.aabb_pts(pts)
        root.location.z -= mins.z
    bpy.context.view_layer.update()


def _ensure_shanya() -> str:
    root = _STATE.get("shanya_root")
    if root is not None:
        try:
            if root.name in bpy.data.objects:
                return f"Шаня уже в сцене ({root.name})"
        except ReferenceError:
            _STATE["shanya_root"] = None
            _STATE["shanya_objects"] = []

    path = Path(str(_SESSION.get("shanya_path") or ""))
    if not path.is_file():
        return f"⚠ Шаня: файл не найден — {path or '(путь пуст в session)'}"

    slot = S.ensure_collection(_SHANYA_COLL)
    S.reveal_collection(_SHANYA_COLL)
    try:
        imported, _ = S.import_asset(path, for_shanya=True, target_coll=slot)
    except Exception as exc:
        return f"⚠ Шаня: ошибка импорта {path.name}: {exc}"

    meshes = [o for o in imported if o.type == "MESH"]
    if not meshes:
        return f"⚠ Шаня: импорт пустой (0 мешей) из {path.name} — нужен FBX с телом"

    _STATE["shanya_objects"] = imported
    root = S.wrap_root(imported, root_name="VIU_SHANYA_ROOT", target_coll=slot)
    # Одежда иногда остаётся вне иерархии empty — дожимаем под root.
    under = set(S.gather_under_root(root))
    for o in imported:
        if o in under or o == root:
            continue
        try:
            mw = o.matrix_world.copy()
            o.parent = root
            o.matrix_world = mw
        except (ReferenceError, AttributeError):
            pass
    bpy.context.view_layer.update()
    target = float(_SESSION.get("shanya_target_m") or 1.70)
    h = S.height_of_objects(imported)
    if h > 1e-6:
        root.scale *= target / h
    root.location = (0.0, 0.0, 0.0)
    _STATE["shanya_root"] = root
    S.reveal_collection(_SHANYA_COLL)
    S.reveal_objects([root, *imported])
    return f"Шаня: {path.name} ({len(meshes)} мешей, h≈{target:.2f}m)"


def _show_shanya_now() -> str:
    """Recovery after a failed screenshot left Shanya excluded/hidden."""
    S.reveal_collection(_SHANYA_COLL)
    root = _STATE.get("shanya_root")
    if not _alive(root):
        root = bpy.data.objects.get("VIU_SHANYA_ROOT")
        _STATE["shanya_root"] = root
    objs = list(_STATE.get("shanya_objects") or [])
    live = []
    for o in objs:
        if _alive(o):
            live.append(o)
    if root is not None and not live:
        live = [o for o in S.gather_under_root(root) if o != root]
    if root is None and not live:
        return _ensure_shanya()
    S.reveal_objects(([root] if root is not None else []) + live)
    _STATE["shanya_objects"] = live
    return f"Шаня снова видима ({len(live)} obj)"


def _force_show_body_meshes(objects) -> list:
    """Unhide real body geo; keep only WGT/cs_/GZM_ hidden."""
    body = []
    for o in objects or []:
        if getattr(o, "type", "") != "MESH":
            continue
        if S.is_wgt_name(o.name) or S.is_control_shape_name(o.name) or S.is_gzm_name(o.name):
            continue
        S.safe_unhide_object(o)
        if S.mesh_vertex_count(o) > 32:
            body.append(o)
    return body


def _load_creature_from_path(path: Path, entry: dict):
    slot = S.ensure_collection(_SLOT)
    S.reveal_collection(_SLOT)
    S.reveal_collection(_SHANYA_COLL)
    imported, import_colls = S.import_asset(path, target_coll=slot)
    body_meshes = _force_show_body_meshes(imported)
    # Diffeomorphic face scale=0 can collapse the whole preview.
    try:
        S.repair_bursting_head(imported)
    except Exception:
        pass
    root = S.wrap_root(imported, root_name=_ROOT, target_coll=slot)
    # Hide only true helpers — not Shadow/Control body meshes.
    for o in imported:
        if S.is_wgt_name(o.name) or S.is_control_shape_name(o.name) or S.is_gzm_name(o.name):
            S.safe_hide_object_for_render(o)
        elif getattr(o, "type", "") in ("EMPTY", "CURVE"):
            S.safe_hide_object_for_render(o)
        elif getattr(o, "type", "") == "ARMATURE":
            try:
                o.data.display_type = "STICK"
            except (AttributeError, ReferenceError):
                pass
    body_meshes = _force_show_body_meshes(imported) or body_meshes
    target = float(entry.get("target_height_m") or 1.0)
    offset = float(_SESSION.get("creature_offset_m") or 1.35)
    props = bpy.context.scene.viu_creature_studio
    bm = ""
    if body_meshes:
        best = max(body_meshes, key=S.mesh_vertex_count)
        bm = best.name
        if props.body_mesh and props.body_mesh != "AUTO":
            bm = props.body_mesh
    _place_creature(root, imported, offset, target, bm)
    S.reveal_collection(_SLOT)
    S.safe_unhide_object(root)
    _force_show_body_meshes(imported)
    measured = S.height_of_objects(imported, bm)
    # If height-fit crushed the model, reset and place once more without absorb glitches.
    if body_meshes and measured < 0.05:
        root.scale = (1.0, 1.0, 1.0)
        bpy.context.view_layer.update()
        _place_creature(root, imported, offset, target, bm)
        measured = S.height_of_objects(imported, bm)
    return bm, root, imported, import_colls, measured, target


def _load_creature_entry(entry: dict):
    _clear_creature()
    path = Path(str(entry.get("path") or ""))
    inbox = Path(str(entry.get("source_inbox") or ""))
    if not path.is_file():
        if inbox.is_file():
            path = inbox
        else:
            return f"Нет файла: {path}"
    try:
        bm, root, imported, import_colls, measured, target = _load_creature_from_path(path, entry)
    except Exception as exc:
        return f"Ошибка импорта {path.name}: {exc}"
    # prepared.blend пустой/сломан — пробуем исходник из Inbox (как в prep).
    if (not bm or measured < 0.05) and inbox.is_file() and inbox.resolve() != path.resolve():
        _clear_creature()
        try:
            bm, root, imported, import_colls, measured, target = _load_creature_from_path(inbox, entry)
            path = inbox
        except Exception:
            pass
    _STATE["creature_root"] = root
    _STATE["creature_objects"] = imported
    _STATE["creature_import_colls"] = import_colls
    _STATE["body_mesh"] = bm or ""
    mesh_n = sum(1 for o in imported if getattr(o, "type", "") == "MESH")
    if not bm:
        return (
            f"Загружено: {entry.get('name')} — ⚠ тела не видно "
            f"(MESH={mesh_n}, файл {path.name}). Жми «Показать меши тела»"
        )
    if measured < 0.05:
        return (
            f"Загружено: {entry.get('name')} — ⚠ рост≈{measured:.3f}m "
            f"(меш {bm}, {path.name}) — жми Показать меши + Применить рост"
        )
    return (
        f"Загружено: {entry.get('name')} "
        f"(меш: {bm}, h≈{measured:.2f}m → {target:.2f}m, {path.name})"
    )


def _setup_camera_for_shot(yaw_deg: float, objects):
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    # Prefer the chosen body mesh so clothing helpers don't pull the framing out.
    bm = _STATE.get("body_mesh") or ""
    if bm:
        obj = bpy.data.objects.get(bm)
        if obj is not None:
            pts.extend(S.mesh_points(obj, deps))
    if not pts:
        for o in objects:
            pts.extend(S.mesh_points(o, deps))
    if not pts:
        return None
    mins, maxs = S.aabb_pts(pts)
    # Чуть выше середины — полный рост в кадре, меньше пола/воздуха.
    center = (mins + maxs) * 0.5
    center = center.copy()
    center.z = mins.z + (maxs.z - mins.z) * 0.52
    height = max(maxs.z - mins.z, 0.2)
    span = max(maxs.x - mins.x, maxs.y - mins.y, height, 0.2)
    # Ближе к модели (было 2.2) — существо крупнее в кадре.
    dist = max(span * 1.15, height * 1.35, 0.4)
    rad = math.radians(yaw_deg)
    cam_data = bpy.data.cameras.new("VIU_StudioCam")
    cam_data.lens = 70.0
    cam_data.clip_start = 0.01
    cam_data.clip_end = max(dist * 6.0, height + 10.0)
    cam = bpy.data.objects.new("VIU_StudioCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (
        center.x + dist * math.sin(rad),
        center.y - dist * math.cos(rad),
        center.z + height * 0.02,
    )
    direction = center - cam.location
    if direction.length > 1e-6:
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


def _render_shots(entry: dict) -> tuple[str, str, str]:
    slug = str(entry.get("slug") or S.slugify(entry.get("name")))
    out_dir = Path(str(_SESSION.get("processed_root") or "")) / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    front = out_dir / "front.png"
    three_quarter = out_dir / "three_quarter.png"
    side = out_dir / "side.png"
    scene = bpy.context.scene
    S.setup_shot_render(scene, res=1536)
    S.ensure_shot_lights()
    root, objs = _resolve_creature()
    if not objs:
        objs = list(_STATE.get("creature_objects") or [])
    S.hide_helpers(objs)
    creature_root = root or _STATE.get("creature_root")
    shanya_root = _STATE.get("shanya_root")
    if not _alive(shanya_root):
        shanya_root = bpy.data.objects.get("VIU_SHANYA_ROOT")
        _STATE["shanya_root"] = shanya_root
    # Весь root Шани (тело + одежда + риг), не только body-mesh.
    hidden: list = []
    try:
        hidden = S.isolate_creature_for_render(
            creature_root,
            extra_hide_roots=[shanya_root],
            extra_hide_collections=[_SHANYA_COLL],
        )
        for yaw, path in ((0.0, front), (45.0, three_quarter), (90.0, side)):
            cam = _setup_camera_for_shot(yaw, objs)
            if cam is None:
                continue
            scene.camera = cam
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            bpy.data.objects.remove(cam, do_unlink=True)
    finally:
        try:
            S.restore_render_visibility(hidden)
        finally:
            # Если isolate/restore споткнулись — вернуть и Шаню, и существо.
            S.reveal_collection(_SHANYA_COLL)
            S.reveal_collection(_SLOT)
            if shanya_root is not None:
                S.reveal_objects([shanya_root, *S.gather_under_root(shanya_root)])
            if creature_root is not None:
                S.reveal_objects([creature_root, *S.gather_under_root(creature_root)])
    return str(front), str(three_quarter), str(side)


def _sync_props_from_entry(entry: dict):
    props = bpy.context.scene.viu_creature_studio
    props.target_height_m = float(entry.get("target_height_m") or 1.0)
    props.photo_notes = str(entry.get("photo_notes") or "")
    sc = str(entry.get("size_class") or "")
    if sc:
        props.size_class = sc
    loco = str(entry.get("locomotion") or "unknown")
    if loco:
        props.locomotion = loco
    gp = str(entry.get("genital_profile") or "none")
    props.genital_profile = gp if gp in {i[0] for i in _GENITAL_ITEMS} else "none"
    modes = set(entry.get("contact_modes") or [])
    props.contact_oral = "oral" in modes
    props.contact_tentacle = "tentacle" in modes
    props.contact_hand = "hand" in modes


def _target_from_size(size_id: str) -> float:
    for row in _SESSION.get("size_classes") or []:
        if row.get("id") == size_id:
            return float(row.get("target_m") or 1.0)
    return 1.0


def _contact_modes_from_props(props) -> list:
    modes = []
    if props.contact_oral:
        modes.append("oral")
    if props.contact_tentacle:
        modes.append("tentacle")
    if props.contact_hand:
        modes.append("hand")
    return modes


def _markup_fields(props, entry: dict) -> dict:
    gp = props.genital_profile or entry.get("genital_profile") or "none"
    modes = _contact_modes_from_props(props)
    return {
        "size_class": props.size_class or entry.get("size_class"),
        "locomotion": props.locomotion or entry.get("locomotion"),
        "genital_profile": gp,
        "contact_modes": modes,
    }


class VIU_OT_StudioShowShanya(bpy.types.Operator):
    bl_idname = "viu.studio_show_shanya"
    bl_label = "Показать Шаню"

    def execute(self, context):
        msg = _show_shanya_now()
        _STATE["shanya_status"] = msg
        context.scene.viu_creature_studio.shanya_status = msg
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class VIU_OT_StudioReloadShanya(bpy.types.Operator):
    bl_idname = "viu.studio_reload_shanya"
    bl_label = "Перезагрузить Шаню"

    def execute(self, context):
        # Un-exclude first — otherwise remove/hide ops trip View Layer errors.
        S.reveal_collection(_SHANYA_COLL)
        coll = bpy.data.collections.get(_SHANYA_COLL)
        if coll:
            for obj in list(coll.all_objects):
                name = S._safe_object_name(obj) if hasattr(S, "_safe_object_name") else getattr(obj, "name", "")
                if name and name in bpy.data.objects:
                    try:
                        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
                    except (ReferenceError, RuntimeError):
                        pass
            try:
                bpy.data.collections.remove(coll)
            except ReferenceError:
                pass
        _STATE["shanya_root"] = None
        _STATE["shanya_objects"] = []
        msg = _ensure_shanya()
        _STATE["shanya_status"] = msg
        context.scene.viu_creature_studio.shanya_status = msg
        level = {"INFO"} if msg.startswith("Шаня:") else {"WARNING"}
        self.report(level, msg)
        return {"FINISHED"}


class VIU_OT_StudioPrev(bpy.types.Operator):
    bl_idname = "viu.studio_prev"
    bl_label = "Предыдущее"

    def execute(self, context):
        q = _SESSION.get("queue") or []
        if not q:
            return {"CANCELLED"}
        idx = int(_SESSION.get("index") or 0)
        if idx <= 0:
            self.report({"INFO"}, "Уже первое существо в очереди")
            return {"FINISHED"}
        _SESSION["index"] = idx - 1
        entry = _current_entry()
        _load_creature_entry(entry)
        _sync_props_from_entry(entry)
        return {"FINISHED"}


class VIU_OT_StudioNext(bpy.types.Operator):
    bl_idname = "viu.studio_next"
    bl_label = "Следующее"

    def execute(self, context):
        q = _SESSION.get("queue") or []
        if not q:
            return {"CANCELLED"}
        idx = int(_SESSION.get("index") or 0)
        if idx >= len(q) - 1:
            self.report(
                {"INFO"},
                "Конец очереди студии. Синхр. студии во Вью и открой снова для оставшихся.",
            )
            return {"FINISHED"}
        _SESSION["index"] = idx + 1
        entry = _current_entry()
        _load_creature_entry(entry)
        _sync_props_from_entry(entry)
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
        S.hide_helpers(_STATE.get("creature_objects") or [])
        return {"FINISHED"}


class VIU_OT_StudioBurstingHead(bpy.types.Operator):
    bl_idname = "viu.studio_bursting_head"
    bl_label = "Bursting Head Repair"

    def execute(self, context):
        _, _, msg = S.repair_bursting_head(_STATE.get("creature_objects") or [])
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class VIU_OT_StudioApplyMarkup(bpy.types.Operator):
    bl_idname = "viu.studio_apply_markup"
    bl_label = "Применить разметку"

    def execute(self, context):
        entry = _current_entry()
        props = context.scene.viu_creature_studio
        if not entry:
            return {"CANCELLED"}
        sc = props.size_class or ""
        loco = props.locomotion or "unknown"
        if not sc:
            self.report({"ERROR"}, "Выбери size_class")
            return {"CANCELLED"}
        target = float(props.target_height_m or _target_from_size(sc))
        entry["size_class"] = sc
        entry["locomotion"] = loco
        entry["target_height_m"] = target
        mark = _markup_fields(props, entry)
        entry.update(mark)
        S.write_feedback_file(
            _feedback_path(),
            entry,
            target_height_m=target,
            **mark,
        )
        legs = S.legs_hint(loco)
        anat = mark.get("genital_profile", "none")
        if mark.get("contact_modes"):
            anat += " +" + "+".join(mark["contact_modes"])
        self.report({"INFO"}, f"{sc} / {loco} ({legs}) | {anat}, рост {target:.2f}м")
        return {"FINISHED"}


class VIU_OT_StudioApplyHeight(bpy.types.Operator):
    bl_idname = "viu.studio_apply_height"
    bl_label = "Применить рост"

    def execute(self, context):
        props = context.scene.viu_creature_studio
        entry = _current_entry()
        if not entry:
            self.report({"ERROR"}, "Нет существа в очереди — запусти студию из Вью")
            return {"CANCELLED"}
        root, objs = _resolve_creature()
        if root is None:
            self.report(
                {"ERROR"},
                "Нет VIU_CREATURE_ROOT — жми «Перезагрузить» или снова открой студию из Вью",
            )
            return {"CANCELLED"}
        if not objs:
            self.report({"ERROR"}, "Под root нет объектов — перезагрузи существо")
            return {"CANCELLED"}
        target = float(props.target_height_m or entry.get("target_height_m") or 1.0)
        bm = props.body_mesh if props.body_mesh and props.body_mesh != "AUTO" else (_STATE.get("body_mesh") or "")
        before = S.height_of_objects(objs, bm if bm else "")
        pre_child = 1.0
        for o in objs:
            u = S.uniform_scale_value(o)
            if u is not None and u > pre_child:
                pre_child = u
        root.scale = (1.0, 1.0, 1.0)
        bpy.context.view_layer.update()
        _place_creature(root, objs, float(_SESSION.get("creature_offset_m") or 1.35), target, bm)
        measured = S.height_of_objects(objs, bm if bm else "")
        entry["target_height_m"] = target
        S.write_feedback_file(
            _feedback_path(),
            entry,
            target_height_m=target,
            measured_height_m=measured,
            **_markup_fields(props, entry),
        )
        root_s = float(root.scale[0])
        leftover = []
        for o in objs:
            u = S.uniform_scale_value(o)
            if u is not None and abs(u - 1.0) > 0.05:
                leftover.append(f"{o.name}={u:.3g}")
        warn = f" ⚠ residual {', '.join(leftover[:3])}" if leftover else ""
        abs_txt = f", был scale×{pre_child:.3g} на детях" if pre_child > 1.05 else ""
        self.report(
            {"INFO"},
            f"Рост {before:.2f}→{measured:.2f}м (цель {target:.2f}); "
            f"{_ROOT}.scale≈{root_s:.3g}{abs_txt}{warn}",
        )
        return {"FINISHED"}


class VIU_OT_StudioScreenshot(bpy.types.Operator):
    bl_idname = "viu.studio_screenshot"
    bl_label = "Снять скрины"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            return {"CANCELLED"}
        try:
            front, three_quarter, side = _render_shots(entry)
            measured = S.height_of_objects(_STATE.get("creature_objects") or [], _STATE.get("body_mesh") or "")
            props = context.scene.viu_creature_studio
            S.write_feedback_file(
                _feedback_path(),
                entry,
                photo_front=front,
                photo_three_quarter=three_quarter,
                photo_side=side,
                photo_ok=False,
                measured_height_m=measured,
                target_height_m=float(entry.get("target_height_m") or 0),
                **_markup_fields(props, entry),
            )
            self.report({"INFO"}, f"PNG: front + ¾ + side → {Path(front).parent.name}")
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            traceback.print_exc()
            return {"CANCELLED"}
        return {"FINISHED"}


class VIU_OT_StudioShowBody(bpy.types.Operator):
    bl_idname = "viu.studio_show_body"
    bl_label = "Показать меши тела"

    def execute(self, context):
        root, objs = _resolve_creature()
        S.reveal_collection(_SLOT)
        body = _force_show_body_meshes(objs)
        if root is not None:
            S.safe_unhide_object(root)
        if not body:
            self.report({"WARNING"}, "Нет MESH у существа — перезагрузи из Вью")
            return {"CANCELLED"}
        if body:
            best = max(body, key=S.mesh_vertex_count)
            _STATE["body_mesh"] = best.name
        self.report({"INFO"}, f"Показано MESH: {len(body)} (осн. {_STATE.get('body_mesh')})")
        return {"FINISHED"}


class VIU_OT_StudioSaveFbx(bpy.types.Operator):
    bl_idname = "viu.studio_save"
    bl_label = "Сохранить эталон FBX"

    def execute(self, context):
        entry = _current_entry()
        if not entry:
            self.report({"ERROR"}, "Нет существа в очереди")
            return {"CANCELLED"}
        props = context.scene.viu_creature_studio
        if not (props.size_class or entry.get("size_class")):
            self.report({"ERROR"}, "Сначала разметка (класс + locomotion)")
            return {"CANCELLED"}
        root, objs = _resolve_creature()
        if root is None:
            self.report({"ERROR"}, "Нет VIU_CREATURE_ROOT — перезагрузи существо")
            return {"CANCELLED"}
        export_objs = S.gather_under_root(root)
        # На всякий случай выкинуть всё под Шанёй, если вдруг попало в иерархию.
        shanya = _STATE.get("shanya_root") or bpy.data.objects.get("VIU_SHANYA_ROOT")
        if shanya is not None:
            ban = set(S.gather_under_root(shanya))
            export_objs = [o for o in export_objs if o not in ban]
        if not export_objs:
            self.report({"ERROR"}, "Под root нет объектов существа")
            return {"CANCELLED"}
        slug = str(entry.get("slug") or S.slugify(entry.get("name")))
        out_dir = Path(str(_SESSION.get("processed_root") or "")) / slug
        fbx = out_dir / f"{slug}_ready.fbx"
        try:
            tex_n = S.materialize_textures_beside_fbx(out_dir)
            ok, msg = S.export_creature_fbx(fbx, export_objs)
            if not ok:
                self.report({"ERROR"}, msg)
                return {"CANCELLED"}
            measured = S.height_of_objects(objs, _STATE.get("body_mesh") or "")
            rows = S.audit_textures(export_objs)
            manifest = S.write_texture_manifest(
                out_dir,
                stage="processed",
                images=rows,
                packed_in_blend=False,
                source_inbox=str(entry.get("prepared_path") or entry.get("path") or ""),
            )
            S.write_feedback_file(
                _feedback_path(),
                entry,
                ready_fbx_path=str(fbx),
                texture_manifest_path=str(manifest),
                measured_height_m=measured,
                target_height_m=float(entry.get("target_height_m") or props.target_height_m or 0),
                **_markup_fields(props, entry),
            )
            self.report(
                {"INFO"},
                f"Эталон FBX: {fbx.name} (без Шани); textures≈{tex_n}; manifest OK",
            )
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
            self.report({"ERROR"}, "Напиши заметку")
            return {"CANCELLED"}
        slug = str(entry.get("slug") or S.slugify(entry.get("name")))
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
        S.write_feedback_file(_feedback_path(), entry, issue_report=note, photo_notes=note, photo_ok=False)
        self.report({"INFO"}, "Отчёт записан")
        return {"FINISHED"}


class VIU_OT_StudioPhotoOk(bpy.types.Operator):
    bl_idname = "viu.studio_photo_ok"
    bl_label = "Скрины ок"

    def execute(self, context):
        entry = _current_entry()
        props = context.scene.viu_creature_studio
        if not entry:
            return {"CANCELLED"}
        S.write_feedback_file(
            _feedback_path(),
            entry,
            photo_ok=True,
            photo_notes="",
            **_markup_fields(props, entry),
        )
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
        S.write_feedback_file(_feedback_path(), entry, photo_ok=False, photo_notes=note)
        return {"FINISHED"}


def _size_enum_items(self, context):
    return _SIZE_ITEMS


def _loco_enum_items(self, context):
    return _LOCO_ITEMS


class VIU_PT_CreatureStudio(bpy.types.Panel):
    bl_label = "Viu — студия"
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
        layout.label(text=f"{idx + 1}/{len(q)}: {entry.get('name')}")
        box = layout.box()
        box.label(text="Порядок: разметка → рост vs Шаня → скрины → FBX")
        box.label(text="Потом во Вью: Синхр. студии")
        box.label(text="Рост смотри у VIU_CREATURE_ROOT, не у арматуры")
        props = context.scene.viu_creature_studio
        shanya_msg = props.shanya_status or _STATE.get("shanya_status") or ""
        if shanya_msg:
            icon = "CHECKMARK" if shanya_msg.startswith("Шаня:") else "ERROR"
            layout.label(text=shanya_msg[:72], icon=icon)
        row_sh = layout.row(align=True)
        row_sh.operator("viu.studio_show_shanya", icon="HIDE_OFF")
        row_sh.operator("viu.studio_reload_shanya", icon="FILE_REFRESH")
        col = layout.column(align=True)
        col.operator("viu.studio_prev", icon="TRIA_LEFT")
        col.operator("viu.studio_next", icon="TRIA_RIGHT")
        col.operator("viu.studio_reload", icon="FILE_REFRESH")
        layout.separator()
        layout.label(text="1. Разметка (класс / ноги / анатомия)", icon="OUTLINER_OB_ARMATURE")
        props = context.scene.viu_creature_studio
        layout.prop(props, "size_class", text="Класс")
        layout.prop(props, "locomotion", text="Locomotion")
        loco = props.locomotion or entry.get("locomotion") or ""
        layout.label(text=S.legs_hint(loco), icon="INFO")
        layout.prop(props, "genital_profile", text="Гениталии")
        row = layout.row(align=True)
        row.prop(props, "contact_oral", text="Рот")
        row.prop(props, "contact_tentacle", text="Щуп.")
        row.prop(props, "contact_hand", text="Руки")
        layout.label(text="Контакт — только если NSFW без гениталий")
        layout.label(text="(мимик/язык, щуп., лапы). Не всем biped")
        layout.operator("viu.studio_apply_markup", icon="CHECKMARK")
        layout.separator()
        layout.label(text="2. Рост (сравнить с Шаней слева)", icon="ARROW_LEFTRIGHT")
        layout.operator("viu.studio_hide_ik", icon="HIDE_ON")
        layout.operator("viu.studio_show_body", icon="HIDE_OFF")
        layout.operator("viu.studio_bursting_head", icon="MODIFIER")
        layout.prop(props, "target_height_m")
        layout.operator("viu.studio_apply_height", icon="ARROW_LEFTRIGHT")
        layout.separator()
        layout.label(text="3. Эталон FBX (только существо, +textures/)", icon="EXPORT")
        layout.operator("viu.studio_screenshot", icon="RENDER_STILL")
        layout.operator("viu.studio_save", icon="EXPORT")
        layout.prop(props, "photo_notes")
        row = layout.row(align=True)
        row.operator("viu.studio_photo_ok", icon="CHECKMARK")
        row.operator("viu.studio_photo_bad", icon="CANCEL")
        row2 = layout.row(align=True)
        row2.operator("viu.studio_report_issue", icon="TEXT")


def _genital_enum_items(self, context):
    return _GENITAL_ITEMS


class VIU_CreatureStudioProps(bpy.types.PropertyGroup):
    target_height_m: FloatProperty(name="Рост (м)", default=1.0, min=0.05, max=20.0)
    body_mesh: StringProperty(name="Меш роста", default="AUTO")
    photo_notes: StringProperty(name="Заметка", default="")
    shanya_status: StringProperty(name="Шаня", default="")
    size_class: EnumProperty(name="Класс", items=_size_enum_items)
    locomotion: EnumProperty(name="Locomotion", items=_loco_enum_items)
    genital_profile: EnumProperty(name="Гениталии", items=_genital_enum_items, default=0)
    contact_oral: BoolProperty(name="Рот/язык", default=False)
    contact_tentacle: BoolProperty(name="Щупальца", default=False)
    contact_hand: BoolProperty(name="Руки/лапы", default=False)


_CLASSES = (
    VIU_CreatureStudioProps,
    VIU_OT_StudioShowShanya,
    VIU_OT_StudioReloadShanya,
    VIU_OT_StudioPrev,
    VIU_OT_StudioNext,
    VIU_OT_StudioReload,
    VIU_OT_StudioHideIk,
    VIU_OT_StudioShowBody,
    VIU_OT_StudioBurstingHead,
    VIU_OT_StudioApplyMarkup,
    VIU_OT_StudioApplyHeight,
    VIU_OT_StudioScreenshot,
    VIU_OT_StudioSaveFbx,
    VIU_OT_StudioReportIssue,
    VIU_OT_StudioPhotoOk,
    VIU_OT_StudioPhotoBad,
    VIU_PT_CreatureStudio,
)


def load_session(session_path: str) -> None:
    global _SESSION, _SIZE_ITEMS, _LOCO_ITEMS, _GENITAL_ITEMS
    _SESSION = json.loads(Path(session_path).read_text(encoding="utf-8"))
    _SIZE_ITEMS = [("", "— класс —", "")]
    for row in _SESSION.get("size_classes") or []:
        sid = row.get("id") or ""
        label = row.get("label") or sid
        _SIZE_ITEMS.append((sid, f"{sid} — {label}", ""))
    _LOCO_ITEMS = [("unknown", "— locomotion —", "")]
    for loco in _SESSION.get("locomotion_options") or []:
        _LOCO_ITEMS.append((loco, loco, S.legs_hint(loco)))
    _GENITAL_ITEMS = []
    for row in _SESSION.get("genital_profiles") or []:
        gid = row.get("id") or "none"
        _GENITAL_ITEMS.append((gid, row.get("label") or gid, ""))
    if not _GENITAL_ITEMS:
        _GENITAL_ITEMS = [("none", "нет", "")]
    bpy.ops.wm.read_homefile(use_empty=True)
    S.setup_shot_render(bpy.context.scene, res=1536)
    S.ensure_shot_lights()
    shanya_msg = _ensure_shanya()
    _STATE["shanya_status"] = shanya_msg
    print("VIU_STUDIO_SHANYA", shanya_msg)
    entry = _current_entry()
    if entry:
        msg = _load_creature_entry(entry)
        print("VIU_STUDIO_LOAD", msg)
        _sync_props_from_entry(entry)
        if bpy.context.scene.viu_creature_studio:
            bpy.context.scene.viu_creature_studio.shanya_status = shanya_msg


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.viu_creature_studio = bpy.props.PointerProperty(type=VIU_CreatureStudioProps)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.viu_creature_studio
