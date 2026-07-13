"""Тесты импорта FBX в Cascadeur."""

from pathlib import Path

from viu.config import Config
from viu.integrations.cascadeur.import_fbx import (
    COMMAND_FILENAME,
    deploy_import_command,
    trigger_fbx_import,
    write_pending_import,
)


def _cfg(tmp_path: Path) -> Config:
    import os

    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    os.environ["VIU_CASCADEUR_SCRIPTS"] = str(tmp_path / "csc_scripts")
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_deploy_import_command(tmp_path):
    cfg = _cfg(tmp_path)
    ok, msg, script = deploy_import_command(cfg)
    assert ok
    assert script.is_file()
    assert script.name == COMMAND_FILENAME
    text = script.read_text(encoding="utf-8")
    assert "Viu.Lab Import" in text
    assert "import_fbx_scene" in text


def test_write_pending_import(tmp_path):
    cfg = _cfg(tmp_path)
    fbx = tmp_path / "model.fbx"
    fbx.write_text("fake", encoding="utf-8")
    ok, msg = write_pending_import(cfg, fbx)
    assert ok
    lab_pending = cfg.data_dir / "lab" / "cascadeur" / "pending_import.json"
    assert lab_pending.is_file()
    assert "model.fbx" in lab_pending.read_text(encoding="utf-8")


def test_trigger_fbx_import_no_fbx(tmp_path):
    cfg = _cfg(tmp_path)
    ok, msg, opened = trigger_fbx_import(cfg)
    assert not ok
    assert not opened
    assert "Inbox" in msg
