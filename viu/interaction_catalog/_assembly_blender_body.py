"""Assembly-сцена в Blender: клипы актёров + timeline markers + active socket.

Не dual-mocap и не IK: импорт отдельных FBX, общая timeline, Empty сокета
на target (из SOCKET_SPECS если mocap без empties). Constraints source→socket — позже.
"""
import json
import sys
import traceback
from pathlib import Path

import bpy


def _argv_job():
    argv = sys.argv
    if "--" in argv:
        return Path(argv[argv.index("--") + 1])
    return Path(__file__).resolve().parent / "assembly_job.json"


def _load_nsfw():
    here = Path(__file__).resolve().parent
    path = here / "viu_nsfw_attach.py"
    if not path.is_file():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("viu_nsfw_attach", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.actions):
        for b in list(block):
            if b.users == 0:
                block.remove(b)


def import_fbx(path: Path):
    path = Path(path)
    before = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)
    bpy.ops.import_scene.fbx(filepath=str(path), global_scale=1.0, automatic_bone_orientation=True)
    bpy.context.view_layer.update()
    objs = [o for o in bpy.data.objects if o not in before]
    new_actions = [a for a in bpy.data.actions if a not in before_actions]
    return objs, new_actions


def _collection_for_role(role: str):
    name = f"ACTOR_{role}"[:60]
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _move_to_collection(objs, coll):
    for obj in objs:
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        coll.objects.link(obj)


def _find_armature(objs):
    arms = [o for o in objs if o.type == "ARMATURE"]
    if not arms:
        return None
    # Prefer largest bone count
    arms.sort(key=lambda o: len(o.data.bones), reverse=True)
    return arms[0]


def _role_offset(role: str, index: int):
    presets = {
        "target": (0.0, 0.0),
        "initiator": (1.2, 0.6),
        "bystander": (-1.6, -0.4),
        "mount": (0.0, 0.0),
        "rider": (0.0, 0.0),
    }
    if role in presets:
        return presets[role]
    return (float(index) * 1.3, 0.0)


def _offset_objects(objs, dx, dy):
    tops = [o for o in objs if o.parent is None]
    for o in tops:
        o.location.x += dx
        o.location.y += dy
    bpy.context.view_layer.update()


def ensure_active_socket(arm_obj, socket_id: str, nsfw):
    """Найти или создать один Empty aim-сокет на арматуре."""
    if arm_obj is None or arm_obj.type != "ARMATURE" or not socket_id:
        return None, "no_armature_or_socket"
    # Уже есть Empty с именем сокета среди детей / сцены
    for obj in bpy.data.objects:
        if obj.type == "EMPTY" and obj.name == socket_id:
            if obj.parent is None:
                obj.parent = arm_obj
            return obj, "existing"

    if nsfw is None:
        return None, "no_nsfw_module"

    spec = None
    for s in nsfw.SOCKET_SPECS:
        if str(s.get("id")) == socket_id:
            spec = s
            break
    if spec is None:
        return None, "unknown_socket"

    bone_names = [b.name for b in arm_obj.data.bones]
    aliases = tuple(spec.get("aliases") or ())
    prefer = tuple(spec.get("prefer") or ())
    bone = nsfw.match_bone_name(bone_names, aliases, prefer=prefer)
    if not bone:
        return None, "no_parent_bone"

    empty = bpy.data.objects.new(socket_id, None)
    for c in list(arm_obj.users_collection) or [bpy.context.collection]:
        try:
            c.objects.link(empty)
        except RuntimeError:
            pass
    empty.empty_display_type = "SPHERE"
    empty.empty_display_size = float(spec.get("size") or 0.025)
    empty.parent = arm_obj
    empty.parent_type = "BONE"
    empty.parent_bone = bone
    off = spec.get("offset") or (0.0, 0.0, 0.0)
    empty.location = (float(off[0]), float(off[1]), float(off[2]))
    empty.show_in_front = True
    empty["viu_aim_socket"] = socket_id
    bpy.context.view_layer.update()
    return empty, "created"


def add_timeline_markers(markers):
    scene = bpy.context.scene
    # Clear previous VIU markers
    for m in list(scene.timeline_markers):
        if m.name.startswith("viu_") or m.name.startswith("sync_"):
            scene.timeline_markers.remove(m)
    for m in markers or []:
        frame = int(m.get("frame") or 0)
        event = str(m.get("event") or "mark").strip() or "mark"
        name = f"sync_{event}"[:60]
        tm = scene.timeline_markers.new(name, frame=frame)
        note = str(m.get("note") or "")
        if note:
            tm["viu_note"] = note


def pick_socket_owner(actors_job, imported_by_role):
    """Target / shanya — владелец active_socket."""
    for a in actors_job:
        role = str(a.get("role") or "")
        slug = str(a.get("creature_slug") or "").lower()
        if role == "target" or slug in ("shanya", "шаня"):
            if role in imported_by_role:
                return role
    for role in imported_by_role:
        return role
    return ""


def main():
    job_path = _argv_job()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    clear_scene()
    nsfw = _load_nsfw()

    scene = bpy.context.scene
    fps = int(job.get("fps") or 24)
    duration = max(int(job.get("duration_frames") or 72), 1)
    frame_start = int(job.get("frame_start") or 0)
    scene.render.fps = fps
    scene.frame_start = frame_start
    scene.frame_end = frame_start + duration - 1
    scene.frame_current = frame_start

    actors_job = list(job.get("actors") or [])
    imported_by_role = {}
    report_actors = []

    for i, actor in enumerate(actors_job):
        role = str(actor.get("role") or f"actor{i}")
        clip = Path(actor.get("clip_fbx") or actor.get("expected_mocap") or "")
        if not clip.is_file():
            print(
                "VIU_ASSEMBLY_WARN",
                json.dumps({"role": role, "error": "missing_clip", "path": str(clip)}),
            )
            continue
        try:
            objs, actions = import_fbx(clip)
            coll = _collection_for_role(role)
            _move_to_collection(objs, coll)
            dx, dy = _role_offset(role, i)
            _offset_objects(objs, dx, dy)
            arm = _find_armature(objs)
            imported_by_role[role] = {"objs": objs, "arm": arm, "actions": [a.name for a in actions]}
            row = {
                "role": role,
                "creature_slug": actor.get("creature_slug"),
                "objects": len(objs),
                "armature": arm.name if arm else "",
                "actions": [a.name for a in actions],
                "offset": [dx, dy],
            }
            report_actors.append(row)
            print("VIU_ASSEMBLY_ACTOR", json.dumps(row, ensure_ascii=False))
        except Exception as exc:
            print("VIU_ASSEMBLY_WARN", role, exc)
            traceback.print_exc()

    add_timeline_markers(job.get("sync_markers") or [])

    socket_id = str(job.get("active_socket") or "")
    owner_role = str(job.get("socket_owner_role") or "") or pick_socket_owner(
        actors_job, imported_by_role
    )
    socket_info = {"socket": socket_id, "owner_role": owner_role, "status": "skipped"}
    if socket_id and owner_role and owner_role in imported_by_role:
        arm = imported_by_role[owner_role].get("arm")
        empty, status = ensure_active_socket(arm, socket_id, nsfw)
        socket_info["status"] = status
        socket_info["empty"] = empty.name if empty else ""
        socket_info["armature"] = arm.name if arm else ""
    print("VIU_ASSEMBLY_SOCKET", json.dumps(socket_info, ensure_ascii=False))

    out = Path(job.get("assembly_blend") or (job_path.parent / "assembly.blend"))
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print(
        "VIU_ASSEMBLY_OK",
        json.dumps(
            {
                "blend": str(out),
                "actors": len(report_actors),
                "socket": socket_info,
            },
            ensure_ascii=False,
        ),
    )


if __name__ == "__main__":
    main()
