# Blender background: retarget HS2 armature animation onto Mixamo rig.
import bpy
import json
import os
import traceback

BEGIN = os.environ.get("VIU_HS2_MARK_BEGIN", "<<<VIU_HS2_RETARGET_BEGIN>>>")
END = os.environ.get("VIU_HS2_MARK_END", "<<<VIU_HS2_RETARGET_END>>>")


def emit(payload):
    print(BEGIN + json.dumps(payload, ensure_ascii=False) + END)


def main():
    src = os.environ.get("VIU_HS2_SOURCE", "")
    rig = os.environ.get("VIU_HS2_TARGET_RIG", "")
    out = os.environ.get("VIU_HS2_OUT", "")
    map_path = os.environ.get("VIU_HS2_BONE_MAP", "")
    if not src or not rig or not out:
        emit({"ok": False, "error": "missing env VIU_HS2_SOURCE/TARGET/OUT"})
        raise SystemExit(2)

    with open(map_path, encoding="utf-8") as f:
        bone_map = json.load(f)

    bpy.ops.wm.read_factory_settings(use_empty=True)

    bpy.ops.import_scene.fbx(filepath=rig)
    target_arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    if target_arm is None:
        emit({"ok": False, "error": "no target armature in rig FBX"})
        raise SystemExit(2)

    bpy.ops.import_scene.fbx(filepath=src)
    source_arm = None
    for o in bpy.data.objects:
        if o.type == "ARMATURE" and o != target_arm:
            source_arm = o
            break
    if source_arm is None:
        emit({"ok": False, "error": "no source armature in HS2 FBX"})
        raise SystemExit(2)

    # Bake mapped bones: sample source pose per frame, copy rotation to target.
    if not source_arm.animation_data or not source_arm.animation_data.action:
        emit({"ok": False, "error": "HS2 FBX без action/анимации"})
        raise SystemExit(2)

    action = source_arm.animation_data.action
    frame_start = int(action.frame_range[0])
    frame_end = int(action.frame_range[1])
    if frame_end <= frame_start:
        frame_end = frame_start + 1

    bpy.context.view_layer.objects.active = target_arm
    bpy.ops.object.mode_set(mode="POSE")
    target_action = bpy.data.actions.new(name=source_arm.animation_data.action.name + "_humanoid")
    target_arm.animation_data_create()
    target_arm.animation_data.action = target_action

    mapped = 0
    for pb_src in source_arm.pose.bones:
        tgt_name = bone_map.get(pb_src.name)
        if not tgt_name:
            continue
        if tgt_name not in target_arm.pose.bones:
            continue
        mapped += 1
        pb_tgt = target_arm.pose.bones[tgt_name]
        for frame in range(frame_start, frame_end + 1):
            bpy.context.scene.frame_set(frame)
            pb_tgt.rotation_mode = "QUATERNION"
            pb_tgt.rotation_quaternion = pb_src.rotation_quaternion.copy()
            pb_tgt.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    bpy.ops.object.mode_set(mode="OBJECT")

    # Export target armature only
    for o in bpy.data.objects:
        o.select_set(o == target_arm)
    bpy.context.view_layer.objects.active = target_arm
    bpy.ops.export_scene.fbx(
        filepath=out,
        use_selection=True,
        bake_anim=True,
        add_leaf_bones=False,
        object_types={"ARMATURE"},
    )

    emit(
        {
            "ok": True,
            "message": f"retargeted {mapped} bones, frames {frame_start}-{frame_end} → {out}",
            "mapped_bones": mapped,
        }
    )


try:
    main()
except Exception as exc:
    emit({"ok": False, "error": str(exc), "traceback": traceback.format_exc()[-1200:]})
    raise SystemExit(2)
