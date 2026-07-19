"""Общие утилиты для Blender Prep / Studio (копируется в Lab/Creatures/)."""
from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import bpy
from mathutils import Vector

_RIG_HIDE = (
    "ik", "pole", "ctrl", "control", "target", "widget", "wgt", "handle",
    "gizmo", "helper", "empties", "guide", "wire",
)

_FACE_BONE_KEYS = (
    "face", "jaw", "lip", "brow", "cheek", "nose", "eye", "lid", "ear",
    "tongue", "teeth", "head", "mouth", "chin", "forehead", "temple",
)

_WIDGET_PREFIXES = ("WGT", "WGT-", "VIS_", "VIS-", "MCH-", "MCH_")

_GENITAL_MESH_KEYS = ("penis", "genital", "cock", "dick", "phallus", "penetrator")
_CLOTHING_MESH_KEYS = (
    "cloth", "outfit", "dress", "shirt", "skirt", "pant", "trouser", "jean",
    "sock", "shoe", "boot", "jacket", "coat", "cloak", "cape", "hat", "hood",
    "bikini", "swim", "bra", "under", "top", "bottom", "armor", "vest",
)
_BODY_MESH_KEYS = (
    "body", "hair", "eye", "ear", "lash", "brow", "teeth", "tongue", "head",
    "face", "skin", "nipple", "breast",
)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (name or "").strip().lower())
    return re.sub(r"_+", "_", s).strip("_")[:64] or "creature"


def is_wgt_name(name: str) -> bool:
    if not name:
        return False
    n = name.strip()
    if n.startswith("WGT.") or n.startswith("WGT-") or n.startswith("WGT_"):
        return True
    low = n.lower()
    return low.startswith("wgt.") or low.startswith("wgt-") or low.startswith("wgt_")


def is_control_shape_name(name: str) -> bool:
    """cs_ / *_cs — custom bone shapes (стрелки и кружки контроллеров рига)."""
    if not name:
        return False
    low = name.strip().lower()
    if low.startswith("cs_") or low.startswith("cs."):
        return True
    if low.endswith("_cs") or low.endswith(".cs"):
        return True
    return False


def is_rig_helper_mesh_name(name: str) -> bool:
    if is_wgt_name(name) or is_control_shape_name(name):
        return True
    low = (name or "").lower()
    return any(k in low for k in _RIG_HIDE + ("collision", "weapon", "sword", "shadow", "lod3", "lod4"))


def skip_mesh(name: str) -> bool:
    return is_rig_helper_mesh_name(name)


def link_objects_to_collection(objects, coll):
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


def ensure_collection(name: str):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _safe_object_name(obj) -> Optional[str]:
    if obj is None:
        return None
    try:
        return obj.name
    except ReferenceError:
        return None


def _safe_collection_name(coll) -> Optional[str]:
    if coll is None:
        return None
    try:
        return coll.name
    except ReferenceError:
        return None


def _remove_object_subtree(root) -> None:
    root_name = _safe_object_name(root)
    if not root_name or root_name not in bpy.data.objects:
        return
    stack = [bpy.data.objects[root_name]]
    ordered: List[str] = []
    while stack:
        obj = stack.pop()
        name = _safe_object_name(obj)
        if not name:
            continue
        ordered.append(name)
        try:
            stack.extend(list(obj.children))
        except ReferenceError:
            pass
    for name in reversed(ordered):
        if name not in bpy.data.objects:
            continue
        try:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        except (ReferenceError, RuntimeError):
            pass


_VIU_MANAGED_COLLECTIONS = frozenset({
    "VIU_PrepSlot",
    "VIU_CreatureSlot",
    "VIU_WardrobeSlot",
    "VIU_ShanyaRef",
})


def _purge_orphan_import_collections(import_collections: Optional[Sequence] = None) -> None:
    scene_coll = bpy.context.scene.collection
    candidates = list(import_collections or [])
    for child in list(scene_coll.children):
        if child.name in _VIU_MANAGED_COLLECTIONS or child.name.startswith("VIU_"):
            continue
        if child not in candidates:
            candidates.append(child)
    for coll in candidates:
        coll_name = _safe_collection_name(coll)
        if not coll_name or coll_name not in bpy.data.collections:
            continue
        if coll_name in _VIU_MANAGED_COLLECTIONS:
            continue
        coll = bpy.data.collections[coll_name]
        if len(coll.all_objects) > 0:
            continue
        try:
            if coll_name in scene_coll.children:
                scene_coll.children.unlink(coll)
        except RuntimeError:
            pass
        if coll_name in bpy.data.collections:
            try:
                bpy.data.collections.remove(coll)
            except ReferenceError:
                pass


def clear_collection_slot(
    slot_name: str,
    root_prefix: str = "VIU_CREATURE_ROOT",
    *,
    tracked_objects: Optional[Sequence] = None,
    root=None,
    import_collections: Optional[Sequence] = None,
):
    if root is not None:
        _remove_object_subtree(root)
    if tracked_objects:
        seen: set = set()
        for obj in tracked_objects:
            name = _safe_object_name(obj)
            if not name or name in seen or name not in bpy.data.objects:
                continue
            seen.add(name)
            _remove_object_subtree(bpy.data.objects[name])

    coll = bpy.data.collections.get(slot_name)
    if coll:
        for obj in list(coll.all_objects):
            name = _safe_object_name(obj)
            if not name or name not in bpy.data.objects:
                continue
            try:
                bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
            except (ReferenceError, RuntimeError):
                pass
        try:
            bpy.data.collections.remove(coll)
        except ReferenceError:
            pass

    for obj in list(bpy.data.objects):
        if obj.name.startswith(root_prefix):
            _remove_object_subtree(obj)

    _purge_orphan_import_collections(import_collections)

    for block in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images):
        for b in list(block):
            if b.users == 0:
                try:
                    block.remove(b)
                except (AttributeError, ReferenceError):
                    pass


def post_import_visibility(objects):
    body = []
    for obj in objects:
        if is_wgt_name(obj.name) or is_control_shape_name(obj.name):
            obj.hide_set(True)
            try:
                obj.hide_viewport = True
            except AttributeError:
                pass
            obj.hide_render = True
            continue
        if obj.type == "MESH" and skip_mesh(obj.name):
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


def hide_helpers(objects):
    for obj in objects:
        if is_wgt_name(obj.name) or is_control_shape_name(obj.name):
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


def hide_rig_viewport(objects) -> None:
    """IK/WGT/cs_ + armature целиком — для wardrobe / работы с одеждой."""
    hide_helpers(objects)
    for obj in objects:
        try:
            if obj.type == "ARMATURE":
                obj.hide_set(True)
                obj.hide_render = True
                obj.show_in_front = False
        except (AttributeError, ReferenceError):
            pass


def import_asset(path: Path, *, for_shanya: bool = False, target_coll=None):
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
    new_colls = [c for c in bpy.data.collections if c not in before_colls]
    if for_shanya:
        wgt = [o for o in imported if is_wgt_name(o.name) or is_control_shape_name(o.name)]
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
        post_import_visibility(imported)
    if target_coll is not None:
        link_objects_to_collection(imported, target_coll)
    return imported, new_colls


def wrap_root(imported, root_name="VIU_CREATURE_ROOT", target_coll=None):
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


def mesh_points(obj, depsgraph):
    if obj.type != "MESH" or skip_mesh(obj.name):
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


def aabb_pts(pts):
    if not pts:
        return Vector((0, 0, 0)), Vector((0, 0, 1))
    mins = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    maxs = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mins, maxs


def height_of_objects(objects, body_mesh: str = ""):
    deps = bpy.context.evaluated_depsgraph_get()
    if body_mesh:
        obj = bpy.data.objects.get(body_mesh)
        if obj:
            pts = mesh_points(obj, deps)
            if pts:
                _, maxs = aabb_pts(pts)
                mins, _ = aabb_pts(pts)
                return float(maxs.z - mins.z)
    meshes = [o for o in objects if o.type == "MESH" and not skip_mesh(o.name)]
    if not meshes:
        return 0.0
    best = max(meshes, key=lambda o: len(o.data.vertices) if o.data else 0)
    pts = mesh_points(best, deps)
    if not pts:
        return 0.0
    mins, maxs = aabb_pts(pts)
    return float(maxs.z - mins.z)


def gather_under_root(root) -> List:
    if root is None:
        return []
    out = []

    def walk(o):
        out.append(o)
        for ch in o.children:
            walk(ch)

    walk(root)
    return out


def save_objects_blend(filepath: Path, objects: Sequence) -> bool:
    if not objects:
        return False
    filepath.parent.mkdir(parents=True, exist_ok=True)
    if filepath.is_file():
        filepath.unlink()
    bpy.data.libraries.write(str(filepath), set(objects), path_remap="RELATIVE", fake_user=True)
    return filepath.is_file()


def _is_face_bone(name: str) -> bool:
    low = (name or "").lower()
    return any(k in low for k in _FACE_BONE_KEYS)


def _scale_near_zero(scale) -> bool:
    return any(abs(float(s)) < 1e-4 for s in scale)


def _remove_pose_scale_drivers(arm_obj, bone_name: str) -> int:
    ad = arm_obj.animation_data
    if not ad:
        return 0
    removed = 0
    prefix = f'pose.bones["{bone_name}"].scale'
    for drv in list(getattr(ad, "drivers", []) or []):
        if drv.data_path.startswith(prefix):
            ad.drivers.remove(drv)
            removed += 1
    return removed


def repair_bursting_head(objects: Sequence) -> Tuple[int, int, str]:
    """Diffeomorphic / Blender 4+: facial bone scale=0 + drivers."""
    arms = [o for o in objects if o.type == "ARMATURE"]
    if not arms:
        return 0, 0, "Нет armature в сцене"
    fixed_bones = 0
    removed_drivers = 0
    for arm_obj in arms:
        view_layer = bpy.context.view_layer
        view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        try:
            bpy.ops.object.mode_set(mode="POSE")
        except RuntimeError:
            continue
        for pb in arm_obj.pose.bones:
            name = pb.name
            if _is_face_bone(name) or _scale_near_zero(pb.scale):
                removed_drivers += _remove_pose_scale_drivers(arm_obj, name)
                pb.scale = (1.0, 1.0, 1.0)
                fixed_bones += 1
        for pb in arm_obj.pose.bones:
            for c in pb.constraints:
                if c.type != "COPY_SCALE":
                    continue
                tgt = c.target
                sub = getattr(c, "subtarget", "") or ""
                if tgt and tgt.type == "ARMATURE" and sub in tgt.pose.bones:
                    tpb = tgt.pose.bones[sub]
                    if _scale_near_zero(tpb.scale):
                        removed_drivers += _remove_pose_scale_drivers(tgt, sub)
                        tpb.scale = (1.0, 1.0, 1.0)
                        fixed_bones += 1
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
        arm_obj.select_set(False)
    msg = f"костей: {fixed_bones}, драйверов scale: {removed_drivers}"
    return fixed_bones, removed_drivers, msg


def check_textures(objects: Sequence) -> Tuple[int, int, List[str]]:
    """Вернуть (ok, missing, lines) — краткий отчёт."""
    rows = audit_textures(objects)
    ok = sum(1 for r in rows if r.get("ok"))
    missing = sum(1 for r in rows if not r.get("ok"))
    lines = [
        f"{r.get('mesh')}: {r.get('image')} → {r.get('resolved')}"
        for r in rows[:12]
    ]
    return ok, missing, lines


def audit_textures(objects: Sequence) -> List[dict]:
    """Полный аудит TEX_IMAGE: source, resolved, ok."""
    rows: List[dict] = []
    seen = set()
    for obj in objects:
        if obj.type != "MESH" or not obj.data:
            continue
        for slot in getattr(obj.data, "materials", []) or []:
            if slot is None or not slot.node_tree:
                continue
            for node in slot.node_tree.nodes:
                if node.type != "TEX_IMAGE":
                    continue
                img = node.image
                if img is None:
                    rows.append({
                        "mesh": obj.name,
                        "material": slot.name,
                        "image": "",
                        "source": "",
                        "resolved": "missing",
                        "ok": False,
                    })
                    continue
                key = (img.name, obj.name)
                if key in seen:
                    continue
                seen.add(key)
                packed = bool(getattr(img, "packed_file", None))
                raw_fp = (img.filepath or "").strip()
                abs_fp = bpy.path.abspath(raw_fp) if raw_fp else ""
                if packed:
                    resolved = "packed"
                    ok = True
                    source = f"packed:{img.name}"
                elif abs_fp and Path(abs_fp).is_file():
                    resolved = "local"
                    ok = True
                    source = abs_fp
                elif raw_fp:
                    resolved = "external"
                    ok = False
                    source = abs_fp or raw_fp
                else:
                    resolved = "missing"
                    ok = False
                    source = ""
                rows.append({
                    "mesh": obj.name,
                    "material": slot.name,
                    "image": img.name,
                    "source": source,
                    "resolved": resolved,
                    "ok": ok,
                })
    return rows


def pack_all_textures() -> int:
    """Упаковать внешние изображения в .blend."""
    before = sum(1 for img in bpy.data.images if getattr(img, "packed_file", None))
    try:
        bpy.ops.file.pack_all()
    except RuntimeError:
        pass
    after = sum(1 for img in bpy.data.images if getattr(img, "packed_file", None))
    return max(0, after - before)


def relocate_external_textures(dest_textures_dir: Path, prepared_root: Path) -> int:
    """Скопировать внешние текстуры в Prepared/<slug>/textures/ и перепривязать."""
    dest_textures_dir = Path(dest_textures_dir)
    dest_textures_dir.mkdir(parents=True, exist_ok=True)
    prepared_root = Path(prepared_root).resolve()
    moved = 0
    for img in bpy.data.images:
        if getattr(img, "packed_file", None):
            continue
        raw = (img.filepath or "").strip()
        if not raw:
            continue
        src = Path(bpy.path.abspath(raw))
        if not src.is_file():
            continue
        try:
            src.resolve().relative_to(prepared_root)
            continue
        except ValueError:
            pass
        dest = dest_textures_dir / src.name
        if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dest)
        img.filepath = str(dest)
        moved += 1
    return moved


def write_texture_manifest(
    out_dir: Path,
    *,
    stage: str,
    images: Sequence[dict],
    packed_in_blend: bool,
    source_inbox: str = "",
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = list(images)
    summary = {
        "ok": sum(1 for r in rows if r.get("ok")),
        "missing": sum(1 for r in rows if not r.get("ok")),
        "external": sum(1 for r in rows if r.get("resolved") == "external"),
        "packed": sum(1 for r in rows if r.get("resolved") == "packed"),
        "local": sum(1 for r in rows if r.get("resolved") == "local"),
    }
    payload = {
        "stage": stage,
        "packed_in_blend": packed_in_blend,
        "source_inbox": source_inbox,
        "summary": summary,
        "images": rows,
    }
    path = out_dir / "texture_manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def prepare_textures_for_prepared(
    objects: Sequence,
    prepared_dir: Path,
    *,
    source_inbox: str = "",
) -> Tuple[Path, str]:
    """Pack + relocate + texture_manifest.json в Prepared/<slug>/."""
    prepared_dir = Path(prepared_dir)
    packed_n = pack_all_textures()
    relocated = relocate_external_textures(prepared_dir / "textures", prepared_dir)
    rows = audit_textures(objects)
    packed_in_blend = all(
        r.get("resolved") in ("packed", "local") for r in rows
    ) if rows else True
    manifest = write_texture_manifest(
        prepared_dir,
        stage="prepared",
        images=rows,
        packed_in_blend=packed_in_blend,
        source_inbox=source_inbox,
    )
    s = manifest.read_text(encoding="utf-8")
    data = json.loads(s).get("summary") or {}
    msg = (
        f"manifest: {manifest.name}; packed+={packed_n}; relocated={relocated}; "
        f"ok={data.get('ok', 0)} missing={data.get('missing', 0)}"
    )
    return manifest, msg


def is_genital_mesh(name: str) -> bool:
    low = (name or "").lower()
    return any(k in low for k in _GENITAL_MESH_KEYS)


def is_clothing_mesh(name: str) -> bool:
    if is_wgt_name(name) or is_genital_mesh(name):
        return False
    low = (name or "").lower()
    return any(k in low for k in _CLOTHING_MESH_KEYS)


def is_body_mesh_name(name: str) -> bool:
    if is_wgt_name(name) or is_genital_mesh(name):
        return False
    low = (name or "").lower()
    if is_clothing_mesh(name):
        return False
    return any(k in low for k in _BODY_MESH_KEYS)


def mesh_visibility_snapshot(objects: Sequence) -> dict:
    """Снимок видимости мешей для outfit set."""
    show: List[str] = []
    hide: List[str] = []
    for obj in objects:
        if obj.type != "MESH" or is_wgt_name(obj.name):
            continue
        if obj.hide_get():
            hide.append(obj.name)
        else:
            show.append(obj.name)
    genital_visible = any(
        is_genital_mesh(o.name) and not o.hide_get()
        for o in objects
        if o.type == "MESH"
    )
    clothing_visible = any(
        is_clothing_mesh(o.name) and not o.hide_get()
        for o in objects
        if o.type == "MESH"
    )
    return {
        "show_meshes": sorted(show),
        "hide_meshes": sorted(hide),
        "genital_mesh_visible": genital_visible,
        "clothing_visible": clothing_visible,
    }


def set_genital_meshes_visible(objects: Sequence, visible: bool) -> int:
    n = 0
    for obj in objects:
        if obj.type != "MESH" or not is_genital_mesh(obj.name):
            continue
        obj.hide_set(not visible)
        obj.hide_render = not visible
        n += 1
    return n


def apply_mesh_visibility(objects: Sequence, show_names: Sequence[str], hide_names: Sequence[str]) -> None:
    show = set(show_names or [])
    hide = set(hide_names or [])
    for obj in objects:
        if obj.type != "MESH":
            continue
        if obj.name in hide:
            obj.hide_set(True)
            obj.hide_render = True
        elif obj.name in show:
            obj.hide_set(False)
            obj.hide_render = False


def clothing_genital_clipping_warning(objects: Sequence) -> str:
    genital_on = any(
        is_genital_mesh(o.name) and not o.hide_get()
        for o in objects
        if o.type == "MESH"
    )
    pants_on = any(
        is_clothing_mesh(o.name) and not o.hide_get() and "pant" in o.name.lower()
        for o in objects
        if o.type == "MESH"
    )
    if genital_on and pants_on:
        return "⚠ genital mesh + штаны — будет clipping"
    return ""


def clear_pose_transforms(objects: Sequence) -> int:
    """Сброс позы на rest (ручная A-pose — правь после)."""
    n = 0
    for arm_obj in [o for o in objects if o.type == "ARMATURE"]:
        view_layer = bpy.context.view_layer
        view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        try:
            bpy.ops.object.mode_set(mode="POSE")
            for pb in arm_obj.pose.bones:
                pb.location = (0.0, 0.0, 0.0)
                pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
                pb.rotation_euler = (0.0, 0.0, 0.0)
                pb.scale = (1.0, 1.0, 1.0)
                n += 1
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
        arm_obj.select_set(False)
    return n


def _is_widget_mesh(obj, arm_obj) -> bool:
    if obj.type != "MESH":
        return False
    name = obj.name
    if name in {"Circle", "Sphere", "Cube", "Plane"}:
        return True
    for pref in _WIDGET_PREFIXES:
        if name.startswith(pref):
            return True
    low = name.lower()
    if "widget" in low or low.endswith("_rig") or "_ctrl" in low:
        return True
    if is_wgt_name(name):
        return True
    if is_control_shape_name(name):
        return True
    return False


def _mesh_for_character(obj, arm_obj) -> bool:
    if obj.type != "MESH" or _is_widget_mesh(obj, arm_obj):
        return False
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object == arm_obj:
            return True
    if obj.vertex_groups:
        bones = {b.name for b in arm_obj.data.bones}
        for vg in obj.vertex_groups:
            if vg.name in bones:
                return True
    par = obj.parent
    while par is not None:
        if par == arm_obj:
            return True
        par = par.parent
    return False


def _pick_armature(objects: Sequence):
    arms = [o for o in objects if o.type == "ARMATURE"]
    if not arms:
        arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not arms:
        return None
    if len(arms) == 1:
        return arms[0]

    def score(arm_obj):
        deform = sum(1 for b in arm_obj.data.bones if b.use_deform)
        meshes = sum(1 for o in bpy.data.objects if _mesh_for_character(o, arm_obj))
        return deform * 10 + meshes

    return max(arms, key=score)


def export_creature_fbx(filepath: Path, objects: Sequence) -> Tuple[bool, str]:
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    arm = _pick_armature(objects)
    if arm is None:
        return False, "Нет armature"
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    for obj in bpy.data.objects:
        try:
            obj.select_set(False)
        except RuntimeError:
            pass
    selected = []
    try:
        if arm.hide_get():
            arm.hide_set(False)
        arm.select_set(True)
        selected.append(arm.name)
    except RuntimeError as exc:
        return False, f"armature: {exc}"
    for obj in list(bpy.data.objects):
        if obj.type != "MESH" or not _mesh_for_character(obj, arm):
            continue
        try:
            if obj.hide_get():
                obj.hide_set(False)
            obj.select_set(True)
            selected.append(obj.name)
        except RuntimeError:
            pass
    if len(selected) < 2:
        return False, "Нет skinned mesh для FBX"
    view_layer.objects.active = arm
    try:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    except RuntimeError:
        pass
    with bpy.context.temp_override(scene=scene, view_layer=view_layer, active_object=arm):
        bpy.ops.export_scene.fbx(
            filepath=str(filepath),
            use_selection=True,
            object_types={"ARMATURE", "MESH"},
            use_mesh_modifiers=True,
            use_armature_deform_only=True,
            bake_anim=False,
            add_leaf_bones=False,
            mesh_smooth_type="FACE",
            apply_scale_options="FBX_SCALE_ALL",
        )
    if not filepath.is_file():
        return False, "FBX не записан"
    return True, f"FBX: {filepath.name} ({len(selected)} obj)"


def legs_hint(locomotion: str) -> str:
    m = {
        "biped": "2 ноги",
        "quadruped": "4 ноги",
        "flyer": "2+крылья",
        "tentacle": "щупальца",
        "amorph": "без ног",
        "mimic": "мимик",
    }
    return m.get(locomotion or "", "?")


def write_feedback_file(path: Path, entry: dict, **extra) -> None:
    import json

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
