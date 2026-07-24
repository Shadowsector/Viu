"""Comfy yield GPU for reflect + lab interval."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from viu.config import Config
from viu.integrations.comfy.client import ComfyClient
from viu.integrations.comfy.gpu_yield import (
    comfy_yield_interrupt_running,
    comfy_yield_on_chat_enabled,
    yield_comfy_for_llm,
)
from viu.integrations.comfy.process import comfy_open_browser_on_launch, comfy_show_console
from viu.lab.paths import lab_interval_min


def test_comfy_yield_on_by_default(monkeypatch):
    monkeypatch.delenv("VIU_COMFY_YIELD_ON_CHAT", raising=False)
    assert comfy_yield_on_chat_enabled() is True
    monkeypatch.setenv("VIU_COMFY_YIELD_ON_CHAT", "0")
    assert comfy_yield_on_chat_enabled() is False


def test_comfy_yield_interrupt_off_by_default(monkeypatch):
    monkeypatch.delenv("VIU_COMFY_YIELD_INTERRUPT", raising=False)
    assert comfy_yield_interrupt_running() is False
    monkeypatch.setenv("VIU_COMFY_YIELD_INTERRUPT", "1")
    assert comfy_yield_interrupt_running() is True


def test_comfy_show_console_off_by_default(monkeypatch):
    monkeypatch.delenv("VIU_COMFY_SHOW_CONSOLE", raising=False)
    assert comfy_show_console() is False
    monkeypatch.setenv("VIU_COMFY_SHOW_CONSOLE", "1")
    assert comfy_show_console() is True
    monkeypatch.delenv("VIU_COMFY_OPEN_BROWSER", raising=False)
    assert comfy_open_browser_on_launch() is True


def test_yield_soft_skip_when_running(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.delenv("VIU_COMFY_YIELD_INTERRUPT", raising=False)
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    calls: list[str] = []

    def fake_post(self, path, payload):
        calls.append(path)
        return {}

    with (
        patch.object(ComfyClient, "ping", return_value=(True, "ok")),
        patch.object(ComfyClient, "queue_summary", return_value="running=1 pending=0"),
        patch.object(
            ComfyClient,
            "get_queue",
            return_value={"queue_running": [1], "queue_pending": []},
        ),
        patch.object(ComfyClient, "_post", fake_post),
    ):
        note = yield_comfy_for_llm(cfg)
    assert "soft skip" in note
    assert "/interrupt" not in calls


def test_yield_noop_when_queue_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_COMFY_YIELD_INTERRUPT", "1")
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    calls: list[str] = []

    def fake_post(self, path, payload):
        calls.append(path)
        return {}

    with (
        patch.object(ComfyClient, "ping", return_value=(True, "ok")),
        patch.object(ComfyClient, "queue_summary", return_value="running=0 pending=0"),
        patch.object(
            ComfyClient,
            "get_queue",
            return_value={"queue_running": [], "queue_pending": []},
        ),
        patch.object(ComfyClient, "_post", fake_post),
    ):
        note = yield_comfy_for_llm(cfg)
    assert note == ""
    assert calls == []


def test_yield_comfy_interrupt_and_free(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_COMFY_YIELD_INTERRUPT", "1")
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    calls: list[tuple[str, dict]] = []

    def fake_post(self, path, payload):
        calls.append((path, payload))
        return {}

    with (
        patch.object(ComfyClient, "ping", return_value=(True, "ok")),
        patch.object(
            ComfyClient,
            "queue_summary",
            side_effect=["running=1 pending=0", "running=0 pending=0"],
        ),
        patch.object(
            ComfyClient,
            "get_queue",
            return_value={"queue_running": [MagicMock()], "queue_pending": []},
        ),
        patch.object(ComfyClient, "_post", fake_post),
    ):
        note = yield_comfy_for_llm(cfg)
    assert "interrupt" in note
    assert any(p == "/interrupt" for p, _ in calls)
    assert any(p == "/free" for p, _ in calls)
    free_payload = next(pl for p, pl in calls if p == "/free")
    assert free_payload.get("unload_models") is True


def test_lab_interval_min_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LAB_INTERVAL_MIN", "0")
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    assert lab_interval_min(cfg) == 0


def test_lab_interval_min_default_positive(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_LAB_INTERVAL_MIN", raising=False)
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    assert lab_interval_min(cfg) >= 1
