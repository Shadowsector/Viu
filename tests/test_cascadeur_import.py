"""Тесты импорта FBX в Cascadeur."""

import json
import os
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
    commands = tmp_path / "Cascadeur" / "resources" / "scripts" / "python" / "commands"
    commands.mkdir(parents=True)
    os.environ["VIU_CASCADEUR_SCRIPTS"] = str(commands)
    ok, msg, script = deploy_import_command(cfg)
    assert ok
    assert script.is_file()
    assert script.name == COMMAND_FILENAME
    text = script.read_text(encoding="utf-8")
    assert "Viu.LabImport" in text
    assert "import_scene" in text
    assert "create_application_scene" in text or "New scene" in text


def test_discover_commands_dir(tmp_path):
    cfg = _cfg(tmp_path)
    commands = tmp_path / "resources" / "scripts" / "python" / "commands"
    commands.mkdir(parents=True)
    (commands / "sample.py").write_text("# x", encoding="utf-8")
    os.environ["VIU_CASCADEUR_SCRIPTS"] = str(commands)
    from viu.integrations.cascadeur.import_fbx import discover_commands_dirs

    dirs = discover_commands_dirs(cfg)
    assert any("commands" in d.as_posix() for d in dirs)


def test_write_console_import_script(tmp_path):
    cfg = _cfg(tmp_path)
    fbx = tmp_path / "model.fbx"
    fbx.write_text("x", encoding="utf-8")
    from viu.integrations.cascadeur.import_fbx import write_console_import_script

    ok, msg, art = write_console_import_script(cfg, fbx)
    assert ok
    assert art.is_file()
    text = art.read_text(encoding="utf-8")
    assert "import_scene" in text
    assert "model.fbx" in text.replace("\\", "/")


def test_write_pending_import(tmp_path):
    cfg = _cfg(tmp_path)
    fbx = tmp_path / "model.fbx"
    fbx.write_text("fake", encoding="utf-8")
    ok, msg = write_pending_import(cfg, fbx)
    assert ok
    lab_pending = cfg.data_dir / "lab" / "cascadeur" / "pending_import.json"
    assert lab_pending.is_file()
    text = lab_pending.read_text(encoding="utf-8")
    assert "model.fbx" in text
    assert '"mode": "scene"' in text


def test_write_pending_import_animation_mode(tmp_path):
    cfg = _cfg(tmp_path)
    fbx = tmp_path / "clip.fbx"
    fbx.write_text("fake", encoding="utf-8")
    ok, msg = write_pending_import(cfg, fbx, mode="animation")
    assert ok
    lab_pending = cfg.data_dir / "lab" / "cascadeur" / "pending_import.json"
    data = json.loads(lab_pending.read_text(encoding="utf-8"))
    assert data["mode"] == "animation"


def test_deploy_command_supports_animation_mode(tmp_path):
    cfg = _cfg(tmp_path)
    commands = tmp_path / "Cascadeur" / "resources" / "scripts" / "python" / "commands"
    commands.mkdir(parents=True)
    os.environ["VIU_CASCADEUR_SCRIPTS"] = str(commands)
    ok, msg, script = deploy_import_command(cfg)
    assert ok
    text = script.read_text(encoding="utf-8")
    assert "import_animation" in text
    assert 'mode in ("animation"' in text or "animation" in text


def test_trigger_fbx_import_no_fbx(tmp_path):
    cfg = _cfg(tmp_path)
    ok, msg, opened = trigger_fbx_import(cfg)
    assert not ok
    assert not opened
    assert "Inbox" in msg
