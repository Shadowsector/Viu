"""Тесты Cascadeur export из Blender."""

import subprocess
from pathlib import Path

import pytest

from viu.config import Config
from viu.integrations.blender.export_cascadeur import (
    CASCADUR_EXPORT_SCRIPT,
    batch_export_cascadeur_models,
    export_cascadeur_fbx,
)
from viu.lab.paths import cascadeur_ready_dir


def test_cascadeur_export_script_deform_only():
    assert "use_armature_deform_only=True" in CASCADUR_EXPORT_SCRIPT
    assert "WGT" in CASCADUR_EXPORT_SCRIPT
    assert "_is_widget_mesh" in CASCADUR_EXPORT_SCRIPT
    assert "_deselect_all" in CASCADUR_EXPORT_SCRIPT
    assert "_mesh_has_armature_weights" in CASCADUR_EXPORT_SCRIPT
    assert "temp_override" in CASCADUR_EXPORT_SCRIPT


def test_export_cascadeur_mock_runner(tmp_path):
    blend = tmp_path / "hero.blend"
    blend.write_bytes(b"fake")
    out = tmp_path / "hero_cascadeur.fbx"

    def fake_runner(cmd, **kwargs):
        out.write_bytes(b"FBX")
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=(
                '<<<VIU_EXPORT_JSON_BEGIN>>>{"ok":true,"deform_bones":42,'
                '"hidden_widgets":3,"selected":["Arm","Body"]}'
                '<<<VIU_EXPORT_JSON_END>>>'
            ),
            stderr="",
        )

    path, meta = export_cascadeur_fbx(
        str(blend), str(out), blender_exe="blender", runner=fake_runner,
    )
    assert path == out.resolve()
    assert meta["deform_bones"] == 42


def _cfg(tmp_path: Path) -> Config:
    import os

    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    os.environ["VIU_LAB_MODELS_INBOX"] = str(tmp_path / "models_inbox")
    os.environ["VIU_LIBRARY_ROOT"] = str(tmp_path / "lib")
    return Config(root=tmp_path, data_dir=tmp_path / ".viu", library_root=str(tmp_path / "lib")).ensure_dirs()


def test_batch_export_cascadeur(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    inbox = tmp_path / "models_inbox"
    inbox.mkdir(parents=True)
    (inbox / "a.blend").write_bytes(b"blend")
    ready = cascadeur_ready_dir(cfg)
    assert ready.is_dir()

    def fake_export(blend_file, output_fbx, **kw):
        Path(output_fbx).write_bytes(b"fbx")
        return Path(output_fbx), {"deform_bones": 10, "hidden_widgets": 2, "selected": ["Arm", "M"]}

    monkeypatch.setattr(
        "viu.integrations.blender.export_cascadeur.export_cascadeur_fbx",
        fake_export,
    )
    monkeypatch.setattr(
        "viu.integrations.blender.exe.resolve_blender_exe",
        lambda _c: r"C:\Blender\blender.exe",
    )

    ok, msg, manifest = batch_export_cascadeur_models(cfg)
    assert ok
    assert manifest.is_file()
    assert (ready / "a_cascadeur.fbx").is_file()
    assert "OK:" in msg
