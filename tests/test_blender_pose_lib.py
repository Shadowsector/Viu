"""Библиотека поз Blender + blend_to (без запуска Blender)."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.integrations.blender.make_anim import (
    ANIM_PRESETS,
    POSE_HOLD_PRESETS,
    match_bone,
    resolve_role_bones,
)
from viu.integrations.blender.pose_ops import (
    blend_to,
    list_poses,
    normalize_character,
    pose_character,
    resolve_character_blend,
)


def test_presets_include_holds():
    for p in ("stand", "sit", "kneel", "all_fours", "lie"):
        assert p in ANIM_PRESETS
        assert p in POSE_HOLD_PRESETS
    assert "idle" in ANIM_PRESETS
    poses = list_poses()
    assert "all_fours" in poses["holds"]


def test_match_unity_and_mixamo_legs():
    names = [
        "Hips",
        "Spine",
        "Chest",
        "Neck",
        "Head",
        "LeftUpperLeg",
        "LeftLowerLeg",
        "LeftFoot",
        "RightUpperLeg",
        "RightLowerLeg",
        "RightFoot",
        "LeftUpperArm",
        "RightUpperArm",
    ]
    roles = resolve_role_bones(names)
    assert roles["hips"] == "Hips"
    assert roles["thigh_l"] == "LeftUpperLeg"
    assert roles["shin_r"] == "RightLowerLeg"
    assert roles["foot_l"] == "LeftFoot"
    assert match_bone(["mixamorig:LeftUpLeg"], "LeftUpperLeg", "leftupleg", "mixamorig:LeftUpLeg")


def test_normalize_character():
    assert normalize_character("Шаня") == "shanya"
    assert normalize_character("viu") == "viu"


def test_resolve_character_blend(tmp_path: Path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu", library_root=tmp_path / "Lib")
    cfg.ensure_dirs()
    root = Path(cfg.library_root) / "Lab" / "Models" / "CascadeurReady"
    root.mkdir(parents=True, exist_ok=True)
    blend = root / "Shanya_rig.blend"
    blend.write_text("x", encoding="utf-8")
    found = resolve_character_blend(cfg, "shanya")
    assert found == blend.resolve()


def test_pose_character_validates_without_blender(tmp_path: Path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    try:
        pose_character(cfg, "shanya", "sit")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass
    try:
        pose_character(cfg, "shanya", "nope")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_blend_to_validates(tmp_path: Path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    blend = tmp_path / "x.blend"
    blend.write_bytes(b"not-real")
    try:
        # file exists but blender will fail — we only check ValueError path
        blend_to(cfg, "shanya", "nope", blend_file=str(blend))
        assert False
    except ValueError:
        pass


def test_catalog_has_kneel_all_fours():
    from viu.animation_catalog.models import DEFAULT_WISHES

    slugs = {w.slug for w in DEFAULT_WISHES}
    assert "kneel" in slugs
    assert "all_fours" in slugs
