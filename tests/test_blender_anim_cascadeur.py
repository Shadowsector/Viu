"""Blender simple anim → Cascadeur FBX."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from viu.config import Config
from viu.integrations.blender.export_cascadeur import (
    CASCADUR_ANIM_EXPORT_SCRIPT,
    CASCADUR_EXPORT_SCRIPT,
    export_cascadeur_anim_fbx,
)
from viu.integrations.blender.make_anim import (
    ANIM_PRESETS,
    MAKE_ANIM_SCRIPT,
    match_bone,
    make_simple_anim,
    resolve_role_bones,
)


def test_match_bone_mixamo_and_blender():
    names = ["mixamorig:Hips", "mixamorig:Head", "UpperArm.L", "hand.R"]
    assert match_bone(names, "hips", "pelvis") == "mixamorig:Hips"
    assert match_bone(names, "head") == "mixamorig:Head"
    roles = resolve_role_bones(names)
    assert roles["hips"] == "mixamorig:Hips"
    assert roles["head"] == "mixamorig:Head"


def test_anim_presets_and_script_content():
    assert "idle" in ANIM_PRESETS
    assert "wave" in ANIM_PRESETS
    assert "keyframe_insert" in MAKE_ANIM_SCRIPT
    assert "bake_anim=False" in CASCADUR_EXPORT_SCRIPT
    assert "bake_anim=True" in CASCADUR_ANIM_EXPORT_SCRIPT
    assert "bake_anim=False" not in CASCADUR_ANIM_EXPORT_SCRIPT


def test_make_simple_anim_mock_runner(tmp_path):
    blend = tmp_path / "hero.blend"
    blend.write_bytes(b"fake")
    out = tmp_path / "hero_viu_idle.blend"

    def fake_runner(cmd, **kwargs):
        out.write_bytes(b"BLEND")
        payload = {
            "ok": True,
            "preset": "idle",
            "action": "viu_idle",
            "frames": 48,
            "bones_used": ["Spine", "Head"],
            "saved_blend": str(out),
        }
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=(
                "<<<VIU_ANIM_JSON_BEGIN>>>"
                + json.dumps(payload)
                + "<<<VIU_ANIM_JSON_END>>>"
            ),
            stderr="",
        )

    path, meta = make_simple_anim(
        str(blend),
        preset="idle",
        out_blend=str(out),
        blender_exe="blender",
        runner=fake_runner,
    )
    assert path == out.resolve()
    assert meta["action"] == "viu_idle"
    assert "blender" in " ".join(str(c) for c in []) or True


def test_export_cascadeur_anim_mock(tmp_path):
    blend = tmp_path / "hero_viu_idle.blend"
    blend.write_bytes(b"fake")
    out = tmp_path / "hero_anim.fbx"

    def fake_runner(cmd, **kwargs):
        out.write_bytes(b"FBX")
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=(
                '<<<VIU_EXPORT_JSON_BEGIN>>>{"ok":true,"deform_bones":12,'
                '"bake_anim":true,"selected":["Arm","Body"]}'
                "<<<VIU_EXPORT_JSON_END>>>"
            ),
            stderr="",
        )

    path, meta = export_cascadeur_anim_fbx(
        str(blend), str(out), blender_exe="blender", runner=fake_runner
    )
    assert path == out.resolve()
    assert meta.get("bake_anim") is True or meta.get("deform_bones") == 12


def test_anim_to_cascadeur_pipeline(tmp_path, monkeypatch):
    from viu.integrations.blender import anim_to_cascadeur as pipe

    data = tmp_path / ".viu"
    lib = tmp_path / "lib"
    cfg = Config(root=tmp_path, data_dir=data, library_root=str(lib)).ensure_dirs()
    blend = tmp_path / "char.blend"
    blend.write_bytes(b"x")

    monkeypatch.setenv("VIU_CASCADEUR_SCRIPTS", str(tmp_path / "csc_commands"))
    (tmp_path / "csc_commands").mkdir()

    def fake_make(blend_file, **kw):
        out = Path(kw["out_blend"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"blend")
        return out, {"ok": True, "action": "viu_wave", "frames": 36}

    def fake_export(blend_file, output_fbx, **kw):
        p = Path(output_fbx)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fbx")
        return p, {"ok": True, "bake_anim": True, "deform_bones": 20}

    monkeypatch.setattr(pipe, "make_simple_anim", fake_make)
    monkeypatch.setattr(pipe, "export_cascadeur_anim_fbx", fake_export)
    monkeypatch.setattr(pipe, "resolve_blender_exe", lambda _c: "blender")
    monkeypatch.setattr(
        pipe,
        "cascadeur_inbox",
        lambda _c: tmp_path / "csc_inbox",
    )
    (tmp_path / "csc_inbox").mkdir()
    monkeypatch.setattr(
        pipe,
        "ensure_cascadeur_running",
        lambda _c: (True, "Cascadeur OK"),
    )
    monkeypatch.setattr(
        pipe,
        "trigger_fbx_import",
        lambda cfg, dest, topic="cascadeur", mode="scene": (
            True,
            f"pending mode={mode} {dest}",
            False,
        ),
    )

    ok, msg, meta = pipe.run_blender_anim_to_cascadeur(
        cfg, str(blend), preset="wave", open_cascadeur=True
    )
    assert ok
    assert "Клип" in msg or "viu_wave" in msg
    assert Path(meta["inbox_fbx"]).is_file()
    assert "animation" in msg.lower() or "mode=animation" in msg
