"""Comfy launch: лог не обрывать, ранняя смерть ловится."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from viu.config import Config
from viu.integrations.comfy import process as proc_mod


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(root=tmp_path, data_dir=data).ensure_dirs()


def test_launch_keeps_log_handle_open(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    root = tmp_path / "ComfyUI"
    root.mkdir()
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    py = tmp_path / "python.exe"
    py.write_text("x", encoding="utf-8")

    monkeypatch.setattr(proc_mod, "_console_python", lambda p: p)
    monkeypatch.setattr(proc_mod, "_python_for_comfy", lambda _r: py)
    monkeypatch.setattr(
        proc_mod,
        "_run_py",
        lambda *_a, **_k: (True, "viu-comfy-ok"),
    )
    monkeypatch.setattr(proc_mod, "comfy_show_console", lambda: False)

    fake = MagicMock()
    fake.pid = 4242
    fake.poll.return_value = None  # still running

    opened = {}

    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        f = real_open(self, *args, **kwargs)
        if self.name.endswith("comfy_launch.log") or "comfy_launch" in str(self):
            opened["f"] = f
        return f

    with patch.object(Path, "open", tracking_open), patch(
        "viu.integrations.comfy.process.subprocess.Popen", return_value=fake
    ) as popen, patch("viu.integrations.comfy.process.time.sleep"):
        ok, msg, p = proc_mod.launch_comfy_process(cfg, root, py=py)

    assert ok, msg
    assert p is fake
    assert "log=" in msg
    # handle must stay open (in _OPEN_LAUNCH_LOGS)
    assert opened["f"] in proc_mod._OPEN_LAUNCH_LOGS
    assert not opened["f"].closed
    # stdout redirected to the same file object
    call_kwargs = popen.call_args.kwargs
    assert call_kwargs.get("stdout") is opened["f"]


def test_launch_detects_immediate_exit(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    root = tmp_path / "ComfyUI"
    root.mkdir()
    (root / "main.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
    py = tmp_path / "python"
    py.write_text("x", encoding="utf-8")

    monkeypatch.setattr(proc_mod, "_console_python", lambda p: p)
    monkeypatch.setattr(proc_mod, "_python_for_comfy", lambda _r: py)
    monkeypatch.setattr(proc_mod, "_run_py", lambda *_a, **_k: (True, "viu-comfy-ok"))
    monkeypatch.setattr(proc_mod, "comfy_show_console", lambda: False)

    fake = MagicMock()
    fake.pid = 7
    fake.poll.return_value = 1
    fake.returncode = 1

    with patch(
        "viu.integrations.comfy.process.subprocess.Popen", return_value=fake
    ), patch("viu.integrations.comfy.process.time.sleep"):
        ok, msg, _p = proc_mod.launch_comfy_process(cfg, root, py=py)

    assert not ok
    assert "сразу вышел" in msg.lower() or "код 1" in msg


def test_launch_rejects_dead_python(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    root = tmp_path / "ComfyUI"
    root.mkdir()
    (root / "main.py").write_text("x", encoding="utf-8")
    py = tmp_path / "python"
    py.write_text("x", encoding="utf-8")

    monkeypatch.setattr(proc_mod, "_console_python", lambda p: p)
    monkeypatch.setattr(
        proc_mod, "_run_py", lambda *_a, **_k: (False, "DLL load failed")
    )

    ok, msg, p = proc_mod.launch_comfy_process(cfg, root, py=py)
    assert not ok
    assert p is None
    assert "venv python" in msg.lower() or "DLL" in msg
