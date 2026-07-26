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

# Токены (целиком между разделителями), не сырой substring:
# иначе «Spike»/«Like»/«retarget» ловились по «ik»/«target».
_RIG_HIDE_TOKENS = (
    "ik", "pole", "ctrl", "control", "target", "widget", "wgt", "handle",
    "gizmo", "helper", "empties", "guide", "wire",
    "collision", "weapon", "sword", "shadow", "lod3", "lod4",
)

_FACE_BONE_KEYS = (
    "face", "jaw", "lip", "brow", "cheek", "nose", "eye", "lid", "ear",
    "tongue", "teeth", "head", "mouth", "chin", "forehead", "temple",
)

_WIDGET_PREFIXES = ("WGT", "WGT-", "VIS_", "VIS-", "MCH-", "MCH_")

_GENITAL_MESH_KEYS = (
    "penis", "genital", "cock", "dick", "phallus", "penetrator", "peen",
    "scrotum", "testicle", "balls", "groin", "member", "intimat",
)
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


def is_gzm_name(name: str) -> bool:
    """GZM_ — gizmo/helper части (часто у сложных CC/DAZ моделей)."""
    if not name:
        return False
    low = name.strip().lower()
    return low.startswith("gzm_") or low.startswith("gzm.")


def _name_tokens(name: str) -> List[str]:
    return [p for p in re.split(r"[^a-z0-9]+", (name or "").lower()) if p]


def is_rig_helper_mesh_name(name: str) -> bool:
    if is_wgt_name(name) or is_control_shape_name(name) or is_gzm_name(name):
        return True
    tokens = set(_name_tokens(name))
    return any(tok in tokens for tok in _RIG_HIDE_TOKENS)


def mesh_vertex_count(obj) -> int:
    try:
        if obj is None or getattr(obj, "type", "") != "MESH" or not obj.data:
            return 0
        return int(len(obj.data.vertices))
    except (ReferenceError, AttributeError, TypeError):
        return 0


def skip_mesh(name: str, obj=None) -> bool:
    """True for real rig helpers. Large body meshes keep showing even if named Shadow/etc."""
    if is_wgt_name(name) or is_control_shape_name(name) or is_gzm_name(name):
        return True
    vc = mesh_vertex_count(obj) if obj is not None else 0
    # Ahmed/Blue Devil: body often named *Shadow* / *Control* but is real geo.
    if vc >= 400:
        return False
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


def _collection_in_scene_tree(root_coll, target) -> bool:
    if root_coll is None or target is None:
        return False
    if root_coll == target:
        return True
    for child in getattr(root_coll, "children", []) or []:
        if _collection_in_scene_tree(child, target):
            return True
    return False


def ensure_collection(name: str):
    """Get-or-create collection and keep it linked into the active scene tree."""
    scene_coll = bpy.context.scene.collection
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        scene_coll.children.link(coll)
    elif not _collection_in_scene_tree(scene_coll, coll):
        try:
            scene_coll.children.link(coll)
        except RuntimeError:
            pass
    try:
        reveal_collection(name)
    except Exception:
        pass
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
        if is_wgt_name(obj.name) or is_control_shape_name(obj.name) or is_gzm_name(obj.name):
            safe_hide_object_for_render(obj)
            continue
        if obj.type == "MESH" and skip_mesh(obj.name, obj):
            safe_hide_object_for_render(obj)
            continue
        if obj.type == "MESH":
            safe_unhide_object(obj)
            vc = mesh_vertex_count(obj)
            if vc > 32:
                body.append(obj)
        elif obj.type == "ARMATURE":
            safe_unhide_object(obj)
            try:
                obj.data.display_type = "STICK"
            except (AttributeError, ReferenceError):
                pass
        elif obj.type == "EMPTY":
            safe_hide_object_for_render(obj)
    return body


def hide_helpers(objects):
    for obj in objects:
        try:
            if is_wgt_name(obj.name) or is_control_shape_name(obj.name) or is_gzm_name(obj.name):
                safe_hide_object_for_render(obj)
                continue
            if obj.type == "EMPTY":
                safe_hide_object_for_render(obj)
            elif obj.type == "ARMATURE":
                obj.data.display_type = "STICK"
            elif obj.type == "MESH" and is_rig_helper_mesh_name(obj.name):
                safe_hide_object_for_render(obj)
            elif obj.type == "CURVE":
                safe_hide_object_for_render(obj)
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
    # Сначала в целевую коллекцию (View Layer), потом visibility — иначе hide_set падает.
    if target_coll is not None:
        link_objects_to_collection(imported, target_coll)
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
                safe_unhide_object(obj)
            elif obj.type == "ARMATURE":
                safe_unhide_object(obj)
                try:
                    obj.data.display_type = "STICK"
                except (AttributeError, ReferenceError):
                    pass
    else:
        post_import_visibility(imported)
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
    if obj.type != "MESH" or skip_mesh(obj.name, obj):
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
                mins, maxs = aabb_pts(pts)
                return float(maxs.z - mins.z)
    meshes = [o for o in objects if o.type == "MESH" and not skip_mesh(o.name, o)]
    if not meshes:
        # Last resort: any mesh with geometry (studio visibility for odd names).
        meshes = [o for o in objects if o.type == "MESH" and mesh_vertex_count(o) > 32]
    if not meshes:
        return 0.0
    best = max(meshes, key=mesh_vertex_count)
    pts = mesh_points(best, deps)
    if not pts:
        return 0.0
    mins, maxs = aabb_pts(pts)
    return float(maxs.z - mins.z)


def set_render_engine(scene) -> str:
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = eng
            return eng
        except TypeError:
            continue
    return str(scene.render.engine)


def setup_shot_world(
    scene,
    *,
    strength: float = 1.0,
    color: Tuple[float, float, float, float] = (0.55, 0.55, 0.58, 1.0),
) -> None:
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("VIU_ShotWorld")
        scene.world = world
    try:
        world.use_nodes = True
        nt = world.node_tree
        nodes = nt.nodes
        links = nt.links
        nodes.clear()
        out = nodes.new("ShaderNodeOutputWorld")
        bg = nodes.new("ShaderNodeBackground")
        bg.inputs["Color"].default_value = color
        bg.inputs["Strength"].default_value = strength
        links.new(bg.outputs["Background"], out.inputs["Surface"])
    except (AttributeError, TypeError, RuntimeError):
        pass


def setup_shot_render(scene, *, res: int = 1536) -> str:
    engine = set_render_engine(scene)
    scene.render.resolution_x = int(res)
    scene.render.resolution_y = int(res)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    setup_shot_world(scene)
    return engine


def ensure_shot_lights() -> List:
    """Ключ + заполняющий + контровой — для EEVEE/Cycles скринов студии."""
    if bpy.data.objects.get("VIU_ShotSun"):
        return []
    coll = bpy.context.scene.collection
    created = []

    sun_data = bpy.data.lights.new("VIU_ShotSun", type="SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("VIU_ShotSun", sun_data)
    coll.objects.link(sun)
    sun.location = (2.0, -3.0, 5.0)
    sun.rotation_euler = (math.radians(55), 0, math.radians(25))
    created.append(sun)

    fill_data = bpy.data.lights.new("VIU_ShotFill", type="AREA")
    fill_data.energy = 250.0
    fill_data.size = 5.0
    fill = bpy.data.objects.new("VIU_ShotFill", fill_data)
    coll.objects.link(fill)
    fill.location = (-2.5, 2.0, 3.0)
    fill.rotation_euler = (math.radians(70), 0, math.radians(-35))
    created.append(fill)

    rim_data = bpy.data.lights.new("VIU_ShotRim", type="AREA")
    rim_data.energy = 140.0
    rim_data.size = 3.5
    rim = bpy.data.objects.new("VIU_ShotRim", rim_data)
    coll.objects.link(rim)
    rim.location = (0.0, 3.5, 4.0)
    rim.rotation_euler = (math.radians(115), 0, math.radians(180))
    created.append(rim)

    return created


_RENDER_KEEP_TYPES = frozenset({"CAMERA", "LIGHT"})


def _find_layer_collection(layer_coll, name: str):
    if layer_coll is None:
        return None
    try:
        if layer_coll.collection.name == name:
            return layer_coll
    except (AttributeError, ReferenceError):
        return None
    for child in getattr(layer_coll, "children", []) or []:
        found = _find_layer_collection(child, name)
        if found is not None:
            return found
    return None


def _object_in_view_layer(obj, view_layer=None) -> bool:
    """hide_set() only works for objects present in the active View Layer."""
    if obj is None:
        return False
    vl = view_layer or getattr(bpy.context, "view_layer", None)
    if vl is None:
        return False
    try:
        return obj.name in vl.objects
    except (ReferenceError, AttributeError, RuntimeError):
        return False


def reveal_collection(name: str) -> bool:
    """Un-exclude / unhide a scene collection in the active View Layer."""
    if not name:
        return False
    coll = bpy.data.collections.get(name)
    if coll is None:
        return False
    try:
        coll.hide_render = False
        try:
            coll.hide_viewport = False
        except (AttributeError, TypeError):
            pass
    except (ReferenceError, AttributeError):
        pass
    view_layer = getattr(bpy.context, "view_layer", None)
    layer_root = getattr(view_layer, "layer_collection", None) if view_layer else None
    lc = _find_layer_collection(layer_root, name)
    if lc is not None:
        try:
            lc.exclude = False
            lc.hide_viewport = False
        except (ReferenceError, AttributeError, RuntimeError):
            pass
    return True


def safe_unhide_object(obj) -> None:
    """Show object without crashing when it is outside the View Layer."""
    if obj is None:
        return
    try:
        obj.hide_render = False
        try:
            obj.hide_viewport = False
        except (AttributeError, TypeError):
            pass
        if _object_in_view_layer(obj):
            try:
                obj.hide_set(False)
            except RuntimeError:
                pass
    except (ReferenceError, AttributeError, RuntimeError):
        pass


def safe_hide_object_for_render(obj) -> Optional[Tuple]:
    """Hide for PNG render via hide_render/hide_viewport only (never hide_set).

    hide_set() raises RuntimeError when the object is not in the View Layer
    (e.g. after collection exclude) and used to abort screenshots mid-restore.
    """
    if obj is None:
        return None
    try:
        hvp = bool(getattr(obj, "hide_viewport", False))
        row = ("obj", obj, bool(obj.hide_render), hvp)
        obj.hide_render = True
        try:
            obj.hide_viewport = True
        except (AttributeError, TypeError):
            pass
        return row
    except (ReferenceError, AttributeError, RuntimeError):
        return None


def isolate_creature_for_render(
    creature_root,
    *,
    extra_hide_roots: Optional[Sequence] = None,
    extra_hide_collections: Optional[Sequence[str]] = None,
) -> List[Tuple]:
    """Спрятать всё кроме существа, камер и ламп. Возвращает список для restore.

    Не вызывает hide_set и не делает layer_collection.exclude — оба ломают
    объекты вне View Layer и оставляют Шаню «навсегда» скрытой при ошибке.
    """
    keep = set()

    def walk(obj):
        keep.add(obj)
        for ch in obj.children:
            walk(ch)

    if creature_root is not None:
        walk(creature_root)

    forced_hide = set()
    for root in extra_hide_roots or []:
        if root is None:
            continue
        for o in gather_under_root(root):
            forced_hide.add(o)
            keep.discard(o)

    restore: List[Tuple] = []

    for name in extra_hide_collections or []:
        if not name:
            continue
        coll = bpy.data.collections.get(name)
        if coll is None:
            continue
        try:
            restore.append(
                ("coll", coll, bool(coll.hide_render), bool(getattr(coll, "hide_viewport", False)))
            )
            coll.hide_render = True
            try:
                coll.hide_viewport = True
            except (AttributeError, TypeError):
                pass
        except (ReferenceError, AttributeError, RuntimeError):
            pass
        # Objects in the ref collection (одежда вне root hierarchy тоже).
        try:
            objs = list(getattr(coll, "all_objects", None) or coll.objects)
        except (ReferenceError, AttributeError):
            objs = []
        for obj in objs:
            forced_hide.add(obj)
            keep.discard(obj)

    for obj in list(bpy.data.objects):
        try:
            if obj.type in _RENDER_KEEP_TYPES:
                continue
            if obj in keep and obj not in forced_hide:
                continue
        except (ReferenceError, AttributeError):
            continue
        row = safe_hide_object_for_render(obj)
        if row is not None:
            restore.append(row)
    return restore


def restore_render_visibility(restore: Sequence[Tuple]) -> None:
    # Collections first so objects are back in the View Layer before any legacy hide_set.
    rows = list(restore or [])
    coll_rows = [r for r in rows if r and r[0] in ("coll", "layer_coll")]
    obj_rows = [r for r in rows if r and r[0] not in ("coll", "layer_coll")]
    for row in coll_rows + obj_rows:
        if not row:
            continue
        try:
            tag = row[0]
        except (IndexError, TypeError):
            continue
        try:
            if tag == "obj":
                # New: ("obj", obj, hide_render, hide_viewport)
                # Old: ("obj", obj, hide_get, hide_render, hide_viewport)
                if len(row) == 4:
                    _, obj, hr, hvp = row
                    obj.hide_render = hr
                    try:
                        obj.hide_viewport = hvp
                    except (AttributeError, TypeError):
                        pass
                else:
                    _, obj, hv, hr, hvp = row
                    obj.hide_render = hr
                    try:
                        obj.hide_viewport = hvp
                    except (AttributeError, TypeError):
                        pass
                    if _object_in_view_layer(obj):
                        try:
                            obj.hide_set(hv)
                        except RuntimeError:
                            pass
            elif tag == "coll":
                _, coll, hr, hvp = row
                coll.hide_render = hr
                try:
                    coll.hide_viewport = hvp
                except (AttributeError, TypeError):
                    pass
            elif tag == "layer_coll":
                _, lc, excl, hvp = row
                lc.exclude = excl
                lc.hide_viewport = hvp
            else:
                # legacy: (obj, hide_get, hide_render)
                obj, hv, hr = row  # type: ignore[misc]
                obj.hide_render = hr
                if _object_in_view_layer(obj):
                    try:
                        obj.hide_set(hv)
                    except RuntimeError:
                        pass
        except (ReferenceError, AttributeError, ValueError, TypeError, RuntimeError):
            pass


def reveal_objects(objects: Sequence) -> int:
    n = 0
    for obj in objects or []:
        try:
            safe_unhide_object(obj)
            n += 1
        except (ReferenceError, AttributeError):
            pass
    return n


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


def uniform_scale_value(obj, *, tol: float = 1e-3) -> Optional[float]:
    """Return uniform XYZ scale, or None if missing / non-uniform / near-zero."""
    if obj is None:
        return None
    try:
        sx, sy, sz = float(obj.scale[0]), float(obj.scale[1]), float(obj.scale[2])
    except (AttributeError, TypeError, IndexError):
        return None
    if min(abs(sx), abs(sy), abs(sz)) < 1e-8:
        return None
    if max(abs(sx - sy), abs(sy - sz), abs(sx - sz)) > tol:
        return None
    return (abs(sx) + abs(sy) + abs(sz)) / 3.0


def _object_depth(obj) -> int:
    d = 0
    cur = obj
    seen = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        d += 1
        cur = cur.parent
    return d


def normalize_uniform_scales_under_root(root) -> float:
    """Fold uniform local scales under root into ancestors (usually the wrap empty).

    FBX/Mixamo packs often leave scale=10 on the armature. Height fit only scaled
    VIU_CREATURE_ROOT, so Outliner still showed 10 and «Применить рост» looked broken.
    Returns the product of absorbed scale factors (1.0 if nothing changed).
    """
    if root is None:
        return 1.0
    nodes = [o for o in gather_under_root(root) if o != root]
    if not nodes:
        return 1.0

    by_parent: Dict[object, List] = {}
    for o in nodes:
        parent = o.parent
        if parent is None:
            continue
        by_parent.setdefault(parent, []).append(o)

    absorbed = 1.0
    parents = sorted(by_parent.keys(), key=_object_depth, reverse=True)
    for parent in parents:
        children = list(by_parent.get(parent) or [])
        if not children:
            continue
        scales = []
        for ch in children:
            u = uniform_scale_value(ch)
            if u is not None and abs(u - 1.0) > 1e-4:
                scales.append(u)
        if not scales:
            continue
        # Absorb one shared factor when siblings match (typical FBX root scale).
        s0 = scales[0]
        if any(abs(u - s0) > 1e-2 for u in scales):
            # Different sibling scales: fold each child individually via matrix restore.
            for ch in children:
                u = uniform_scale_value(ch)
                if u is None or abs(u - 1.0) <= 1e-4:
                    continue
                mw = ch.matrix_world.copy()
                parent.scale = (
                    float(parent.scale[0]) * u,
                    float(parent.scale[1]) * u,
                    float(parent.scale[2]) * u,
                )
                ch.scale = (1.0, 1.0, 1.0)
                bpy.context.view_layer.update()
                ch.matrix_world = mw
                absorbed *= u
            bpy.context.view_layer.update()
            continue

        mws = [ch.matrix_world.copy() for ch in children]
        parent.scale = (
            float(parent.scale[0]) * s0,
            float(parent.scale[1]) * s0,
            float(parent.scale[2]) * s0,
        )
        for ch in children:
            u = uniform_scale_value(ch)
            if u is not None and abs(u - s0) <= 1e-2:
                ch.scale = (1.0, 1.0, 1.0)
        bpy.context.view_layer.update()
        for ch, mw in zip(children, mws):
            ch.matrix_world = mw
        absorbed *= s0
        bpy.context.view_layer.update()
    return absorbed


def height_fit_multiplier(measured_m: float, target_m: float) -> float:
    """Pure helper: root scale multiplier to go from measured height to target metres."""
    if measured_m <= 1e-6 or target_m <= 0:
        return 1.0
    h = float(measured_m)
    pre = 1.0
    if h > 20.0 and target_m < 10.0:
        # Likely centimetres exported as metres.
        pre = 0.01
        h *= pre
    return pre * (float(target_m) / h)


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
    if is_wgt_name(name) or is_genital_mesh(name) or is_gzm_name(name):
        return False
    low = (name or "").lower()
    return any(k in low for k in _CLOTHING_MESH_KEYS)


def is_body_mesh_name(name: str) -> bool:
    if is_wgt_name(name) or is_genital_mesh(name) or is_gzm_name(name):
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


def set_mesh_viewport_visible(obj, visible: bool) -> None:
    """Viewport + render flags (в т.ч. «Disable in Renders» у импорта)."""
    if obj is None or obj.type != "MESH":
        return
    hidden = not visible
    try:
        obj.hide_set(hidden)
        obj.hide_render = hidden
        try:
            obj.hide_viewport = hidden
        except AttributeError:
            pass
        for attr in (
            "visible_camera",
            "visible_diffuse",
            "visible_glossy",
            "visible_transmission",
            "visible_volume_scatter",
            "visible_shadow",
        ):
            if hasattr(obj, attr):
                setattr(obj, attr, visible)
    except (AttributeError, ReferenceError):
        pass


def set_genital_meshes_visible(objects: Sequence, visible: bool) -> int:
    n = 0
    for obj in objects:
        if obj.type != "MESH" or not is_genital_mesh(obj.name):
            continue
        set_mesh_viewport_visible(obj, visible)
        n += 1
    return n


def apply_mesh_visibility(objects: Sequence, show_names: Sequence[str], hide_names: Sequence[str]) -> None:
    show = set(show_names or [])
    hide = set(hide_names or [])
    for obj in objects:
        if obj.type != "MESH":
            continue
        if obj.name in hide:
            set_mesh_viewport_visible(obj, False)
        elif obj.name in show:
            set_mesh_viewport_visible(obj, True)


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


def _mesh_for_character(obj, arm_obj, *, allowed: Optional[set] = None) -> bool:
    if obj is None or arm_obj is None:
        return False
    if allowed is not None and obj not in allowed:
        return False
    if obj.type != "MESH" or _is_widget_mesh(obj, arm_obj):
        return False
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object == arm_obj:
            return True
    par = obj.parent
    while par is not None:
        if par == arm_obj:
            return True
        par = par.parent
    # Не матчим только по именам vertex groups — у Шани/существа общие кости Humanoid.
    return False


def _pick_armature(objects: Sequence):
    """Armature только из переданного набора (без fallback на всю сцену / Шаню)."""
    arms = [o for o in objects if o is not None and getattr(o, "type", "") == "ARMATURE"]
    if not arms:
        return None
    if len(arms) == 1:
        return arms[0]

    allowed = {o for o in objects if o is not None}

    def score(arm_obj):
        deform = sum(1 for b in arm_obj.data.bones if b.use_deform)
        meshes = sum(1 for o in allowed if _mesh_for_character(o, arm_obj, allowed=allowed))
        return deform * 10 + meshes

    return max(arms, key=score)


def images_from_objects(objects: Sequence) -> List:
    """Image datablocks used by MESH materials under the given objects only."""
    out: List = []
    seen = set()
    for obj in objects or []:
        if getattr(obj, "type", "") != "MESH":
            continue
        for slot in getattr(obj, "material_slots", []) or []:
            mat = getattr(slot, "material", None)
            if mat is None:
                continue
            try:
                if mat.use_nodes and mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if getattr(node, "type", "") != "TEX_IMAGE":
                            continue
                        img = getattr(node, "image", None)
                        if img is None or id(img) in seen:
                            continue
                        if getattr(img, "type", "") in ("RENDER_RESULT", "COMPOSITING"):
                            continue
                        seen.add(id(img))
                        out.append(img)
            except (ReferenceError, AttributeError):
                continue
    return out


def materialize_textures_beside_fbx(out_dir: Path, objects: Sequence = ()) -> Tuple[int, int]:
    """Unpack/copy only creature textures into Processed/<slug>/textures/.

    Returns (files_written, images_on_creature). Does NOT touch Shanya images.
    """
    out_dir = Path(out_dir)
    tex_dir = out_dir / "textures"
    tex_dir.mkdir(parents=True, exist_ok=True)
    imgs = images_from_objects(objects)
    # Чистый каталог — иначе остаются чужие файлы Шани от прошлых экспортов.
    keep_names = set()
    n = 0
    for img in imgs:
        try:
            raw_name = Path((img.name or "tex").replace("\\", "/")).name
            if not re.search(r"\.(png|jpe?g|tga|tif{1,2}|exr|bmp|webp)$", raw_name, re.I):
                raw_name = f"{raw_name}.png"
            dest = tex_dir / raw_name
            keep_names.add(dest.name.lower())
            packed = getattr(img, "packed_file", None)
            if packed is not None:
                img.filepath_raw = str(dest)
                try:
                    img.save()
                    n += 1
                except RuntimeError:
                    try:
                        img.unpack(method="WRITE_LOCAL")
                        n += 1
                    except RuntimeError:
                        pass
            else:
                raw = (img.filepath or "").strip()
                src = Path(bpy.path.abspath(raw)) if raw else None
                if src is not None and src.is_file():
                    if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
                        shutil.copy2(src, dest)
                    n += 1
            if dest.is_file():
                try:
                    img.filepath = f"//textures/{dest.name}"
                    img.reload()
                except (RuntimeError, AttributeError):
                    pass
        except (ReferenceError, AttributeError, OSError):
            continue
    # Удалить чужие текстуры (Шаня и т.п.) из папки существа.
    try:
        for p in tex_dir.iterdir():
            if p.is_file() and p.name.lower() not in keep_names:
                try:
                    p.unlink()
                except OSError:
                    pass
    except OSError:
        pass
    return n, len(imgs)


def _bake_export_world_transforms(export_objs: Sequence) -> List[Tuple]:
    """Unparent keep-transform + apply scale so FBX without wrap-empty keeps mesh≈rig size.

    Studio scales VIU_CREATURE_ROOT; FBX exports only ARMATURE/MESH, so without this
    the armature often stays at local scale while the mesh keeps world size.
    """
    restore: List[Tuple] = []
    objs = [o for o in export_objs if o is not None]
    if not objs:
        return restore
    for obj in sorted(objs, key=_object_depth, reverse=True):
        try:
            restore.append(
                (
                    obj,
                    obj.parent,
                    obj.matrix_parent_inverse.copy(),
                    obj.matrix_local.copy(),
                )
            )
            mw = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = mw
        except (ReferenceError, AttributeError, RuntimeError):
            continue
    bpy.context.view_layer.update()
    view_layer = bpy.context.view_layer
    for obj in bpy.data.objects:
        try:
            if _object_in_view_layer(obj, view_layer):
                obj.select_set(False)
        except RuntimeError:
            pass
    active = None
    for obj in objs:
        try:
            safe_unhide_object(obj)
            if _object_in_view_layer(obj, view_layer):
                obj.select_set(True)
                if active is None or obj.type == "ARMATURE":
                    active = obj
        except RuntimeError:
            pass
    if active is not None:
        view_layer.objects.active = active
        try:
            if bpy.context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
        try:
            with bpy.context.temp_override(
                scene=bpy.context.scene,
                view_layer=view_layer,
                active_object=active,
                selected_objects=[o for o in objs if _object_in_view_layer(o, view_layer)],
            ):
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        except RuntimeError:
            pass
    bpy.context.view_layer.update()
    return restore


def _restore_export_transforms(restore: Sequence[Tuple]) -> None:
    for row in reversed(list(restore or [])):
        try:
            obj, parent, mpi, ml = row
            obj.parent = parent
            obj.matrix_parent_inverse = mpi
            obj.matrix_local = ml
        except (ReferenceError, AttributeError, RuntimeError, ValueError):
            continue
    try:
        bpy.context.view_layer.update()
    except (ReferenceError, AttributeError):
        pass


def export_creature_fbx(filepath: Path, objects: Sequence) -> Tuple[bool, str]:
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    allowed = {o for o in objects if o is not None}
    # Пустышка-root и всё под ним — без объектов Шани из сцены.
    arm = _pick_armature(list(allowed))
    if arm is None:
        return False, "Нет armature у существа (не у Шани)"
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    export_list = [arm]
    for obj in list(allowed):
        if obj.type == "MESH" and _mesh_for_character(obj, arm, allowed=allowed):
            export_list.append(obj)
    if len(export_list) < 2:
        return False, "Нет skinned mesh у существа для FBX"

    tex_n, tex_imgs = 0, 0
    try:
        tex_n, tex_imgs = materialize_textures_beside_fbx(filepath.parent, export_list)
    except Exception:
        pass

    bake_restore: List[Tuple] = []
    try:
        bake_restore = _bake_export_world_transforms(export_list)
        for obj in bpy.data.objects:
            try:
                if _object_in_view_layer(obj, view_layer):
                    obj.select_set(False)
            except RuntimeError:
                pass
        selected = []
        for obj in export_list:
            try:
                safe_unhide_object(obj)
                if not _object_in_view_layer(obj, view_layer):
                    continue
                obj.select_set(True)
                selected.append(obj.name)
            except RuntimeError:
                pass
        if arm.name not in selected or len(selected) < 2:
            return False, "Не удалось выделить armature+mesh для FBX"
        view_layer.objects.active = arm
        try:
            if bpy.context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
        with bpy.context.temp_override(scene=scene, view_layer=view_layer, active_object=arm):
            kwargs = dict(
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
            # COPY + embed: текстуры внутри FBX (и копия в textures/ только существа).
            exported = False
            for extra in (
                {"path_mode": "COPY", "embed_textures": True},
                {"path_mode": "COPY"},
                {},
            ):
                try:
                    bpy.ops.export_scene.fbx(**kwargs, **extra)
                    exported = True
                    break
                except TypeError:
                    continue
            if not exported:
                return False, "export_scene.fbx не принял аргументы"
    finally:
        _restore_export_transforms(bake_restore)

    if not filepath.is_file():
        return False, "FBX не записан"
    if tex_imgs == 0:
        tex_note = "⚠ в материалах 0 текстур"
    else:
        tex_note = f"текстур {tex_imgs} (файлов {tex_n}, embed)"
    return True, f"FBX: {filepath.name} ({len(selected)} obj, scale baked, {tex_note})"


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
