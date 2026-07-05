"""Тесты verify и blender export."""

import subprocess
from pathlib import Path

import pytest

from viu.integrations.blender.export_shanya import EXPORT_SCRIPT, build_export_command, export_shanya_fbx
from viu.integrations.unity.setup import deploy_editor_scripts
from viu.integrations.unity.verify import verify_unity_project


def test_deploy_both_editor_scripts(tmp_path):
    (tmp_path / "Assets").mkdir()
    ok, msg = deploy_editor_scripts(tmp_path)
    assert ok
    assert (tmp_path / "Assets/Editor/Viu/ShanyaSetup.cs").is_file()
    assert (tmp_path / "Assets/Editor/Viu/ShanyaOutfit.cs").is_file()
    assert "ShanyaOutfit" in msg


def test_verify_no_setup_log(tmp_path):
    (tmp_path / "Assets").mkdir()
    r = verify_unity_project(tmp_path)
    assert "viu_setup.log" in r.render()
    assert not r.setup_log_ok


def test_verify_setup_success(tmp_path):
    (tmp_path / "Assets/Characters/Shanya").mkdir(parents=True)
    (tmp_path / "Assets/Characters/Shanya/Shanya_Idle_Stand.controller").write_text("x")
    (tmp_path / "Assets/Editor/Viu").mkdir(parents=True)
    (tmp_path / "Assets/Editor/Viu/ShanyaSetup.cs").write_text("//")
    (tmp_path / "viu_setup.log").write_text("[Viu] Setup готов: Shanya\n")
    r = verify_unity_project(tmp_path)
    assert r.setup_log_ok
    assert r.controller_found
    assert "✓" in r.render()


def test_export_command_includes_blend():
    cmd = build_export_command("blender", "a.blend", "script.py", "out.fbx")
    assert "a.blend" in cmd
    assert "out.fbx" in cmd
    assert "--" in cmd


def test_export_script_has_wgt_hide():
    assert "WGT" in EXPORT_SCRIPT
    assert "export_scene.fbx" in EXPORT_SCRIPT


def test_export_shanya_mock_runner(tmp_path):
    blend = tmp_path / "Shanya.blend"
    blend.write_bytes(b"fake")
    out = tmp_path / "Shanya.fbx"

    def fake_runner(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd, returncode=0,
            stdout=f"<<<VIU_EXPORT_OK>>>{out}<<<VIU_EXPORT_END>>>",
            stderr="",
        )

    path = export_shanya_fbx(str(blend), str(out), blender_exe="blender", runner=fake_runner)
    assert path == out.resolve()
