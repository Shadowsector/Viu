"""ReActor diagnostics."""

from unittest.mock import patch

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.reactor_diag import (
    probe_reactor_deps,
    reactor_errors_in_launch_log,
)


def test_reactor_errors_in_launch_log(tmp_path):
    cfg = Config(root=tmp_path / "Viu", data_dir=tmp_path / ".viu")
    cfg.data_dir.mkdir(parents=True)
    log = cfg.data_dir / "logs" / "comfy_launch.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        "Starting\n"
        "Traceback importing ComfyUI-ReActor\n"
        "ModuleNotFoundError: No module named 'insightface'\n",
        encoding="utf-8",
    )
    root = tmp_path / "ComfyUI"
    root.mkdir()
    (root / "main.py").write_text("#\n", encoding="utf-8")
    (root / "folder_paths.py").write_text("", encoding="utf-8")
    cfg.comfy_root = str(root)
    text = reactor_errors_in_launch_log(cfg)
    assert "insightface" in text.lower()


def test_probe_reactor_deps_missing(monkeypatch, tmp_path):
    cfg = Config(root=tmp_path / "Viu", data_dir=tmp_path / ".viu")
    root = tmp_path / "ComfyUI"
    root.mkdir()
    (root / "main.py").write_text("#\n", encoding="utf-8")
    (root / "venv" / "Scripts").mkdir(parents=True)
    fake_py = root / "venv" / "Scripts" / "python.exe"
    fake_py.write_text("", encoding="utf-8")
    cfg.comfy_root = str(root)

    from viu.integrations.comfy import reactor_diag as rd

    def fake_run(*a, **k):
        class R:
            returncode = 1
            stdout = "MISSING\ninsightface: No module"
            stderr = ""

        return R()

    monkeypatch.setattr(rd.subprocess, "run", fake_run)
    ok, msg, missing = probe_reactor_deps(cfg)
    assert not ok
    assert "insightface" in msg.lower() or missing
