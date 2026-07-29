"""comfy_diag: факты про живой Comfy vs пустой OK."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from viu.config import Config
from viu.integrations.comfy import comfy_diag as diag
from viu.integrations.comfy.comfy_diag import (
    ProcessSnap,
    TimedHttp,
    _verdict,
    format_comfy_diag,
    run_comfy_diag,
)
from viu.tools import build_default_registry


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    data = tmp_path / ".viu"
    data.mkdir(parents=True)
    (tmp_path / "Viu").mkdir(parents=True, exist_ok=True)
    return Config(root=tmp_path / "Viu", data_dir=data, comfy_url="http://127.0.0.1:8188")


def test_registry_has_comfy_diag():
    assert build_default_registry().get("comfy_diag") is not None


def test_verdict_waiting_panel():
    v, actions = _verdict(["waiting_panel", "executor_alive", "comfy_idle_cpu"], ok_ping=True)
    assert "ЖДЁТ" in v or "Снять" in v
    assert any("Снять" in a for a in actions)


def test_verdict_dead():
    v, actions = _verdict(["api_dead", "no_listener"], ok_ping=False)
    assert "МЁРТВ" in v
    assert any("restart" in a for a in actions)


def test_verdict_idle_healthy():
    v, _ = _verdict(["executor_alive", "comfy_idle_cpu"], ok_ping=True)
    assert "ПРОСТАИВАЕТ" in v or "ЖИВ" in v


def test_run_diag_dead_api(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)

    class FakeClient:
        def __init__(self, *a, **k):
            self.timeout = 12.0

        def ping(self):
            return False, "ComfyUI недоступен"

    monkeypatch.setattr(diag, "ComfyClient", FakeClient)
    monkeypatch.setattr(diag, "sample_listeners", lambda port, sample_sec=1.2: [])
    monkeypatch.setattr(
        diag,
        "_timed_get",
        lambda base, path, timeout=8.0: TimedHttp(path=path, ok=False, ms=10, detail="refused"),
    )
    monkeypatch.setattr(diag, "_log_tail_analysis", lambda cfg, max_lines=40: ("(нет лога)", []))
    monkeypatch.setattr(diag, "_lab_line", lambda cfg: "Lab: нет")

    rep = run_comfy_diag(cfg, sample_sec=0, probe_prompt=False)
    assert "МЁРТВ" in rep.verdict
    text = format_comfy_diag(cfg, sample_sec=0, probe_prompt=False)
    assert "comfy_diag" in text
    assert "ВЕРДИКТ" in text


def test_run_diag_idle_comfy(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)

    class FakeClient:
        def __init__(self, *a, **k):
            self.timeout = 12.0
            self.base_url = "http://127.0.0.1:8188"

        def ping(self):
            return True, "ComfyUI OK (running=0, pending=0)"

        def _get(self, path):
            if path == "/object_info":
                return {"KSampler": {}, "CLIPTextEncode": {}}
            if path == "/system_stats":
                return {"devices": [{"name": "cuda:0", "vram_total": 12}], "system": {}}
            return {}

    monkeypatch.setattr(diag, "ComfyClient", FakeClient)
    monkeypatch.setattr(
        diag,
        "sample_listeners",
        lambda port, sample_sec=1.2: [
            ProcessSnap(
                pid=24252,
                name="python.exe",
                exe=r"U:\Viu\ComfyUI\venv\Scripts\python.exe",
                cmdline=r"python.exe -u main.py --port 8188",
                is_comfy=True,
                cpu_delta=0.01,
                ram_mb=1800.0,
                responding=True,
            )
        ],
    )
    monkeypatch.setattr(
        diag,
        "_timed_get",
        lambda base, path, timeout=8.0: TimedHttp(
            path=path, ok=True, ms=40, bytes_n=5000, detail="HTTP 200"
        ),
    )
    monkeypatch.setattr(
        diag,
        "probe_prompt_executor",
        lambda client, timeout=8.0: (True, "executor ответил 50ms", 50.0),
    )
    monkeypatch.setattr(
        diag,
        "_log_tail_analysis",
        lambda cfg, max_lines=40: ("Starting server\nTo see the GUI", ["log_started"]),
    )
    monkeypatch.setattr(diag, "_lab_line", lambda cfg: "Lab awaiting_prompt")

    # waiting_panel via load_session
    sess = MagicMock()
    sess.status = "awaiting_prompt"
    sess.step = 4
    sess.meta = {"action": "wave", "approved": False}
    monkeypatch.setattr(
        "viu.lab.session.load_session",
        lambda config, topic: sess,
    )

    rep = run_comfy_diag(cfg, sample_sec=0.0, probe_prompt=True)
    assert "Снять" in rep.verdict or "ЖДЁТ" in rep.verdict or "ПРОСТАИВАЕТ" in rep.verdict
    assert any(a for a in rep.actions)


def test_probe_prompt_alive_on_http_error():
    from viu.integrations.comfy.client import ComfyError
    from viu.integrations.comfy.comfy_diag import probe_prompt_executor

    client = MagicMock()
    client.timeout = 8.0

    def boom(wf):
        raise ComfyError("ComfyUI HTTP 400 /prompt: node '1' class_type missing")

    client.queue_prompt.side_effect = boom
    ok, msg, ms = probe_prompt_executor(client, timeout=2.0)
    assert ok
    assert "executor" in msg.lower() or "400" in msg
