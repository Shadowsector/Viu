"""Тесты строки активности GUI."""

from __future__ import annotations

import json
from pathlib import Path

from viu.config import Config
from viu.gui_activity import activity_view
from viu.lab.comfy_pipeline import COMFY_TOPIC
from viu.lab.session import LabSession, save_session


def test_activity_idle():
    cfg = Config()
    view = activity_view(cfg)
    assert view.mode == "idle"
    assert "Готова" in view.line
    assert view.blink is False


def test_activity_llm_busy():
    cfg = Config()
    view = activity_view(cfg, llm_busy=True, hint="про сцену в сарае")
    assert view.mode == "llm"
    assert "Думаю" in view.line
    assert "сарае" in view.line
    assert view.blink is True


def test_activity_comfy_generating(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config().ensure_dirs()
    session = LabSession(
        id="t1",
        topic=COMFY_TOPIC,
        status="running",
        step=4,
        steps_total=8,
        meta={"catalog_slug": "lie_down"},
    )
    save_session(cfg, session)
    view = activity_view(cfg, tool_busy=True)
    assert view.mode == "comfy"
    assert "генерация" in view.line.lower()
    assert "lie_down" in view.line


def test_activity_awaiting_lora(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config().ensure_dirs()
    session = LabSession(
        id="t2",
        topic=COMFY_TOPIC,
        status="awaiting_lora_pick",
        step=3,
        steps_total=8,
    )
    save_session(cfg, session)
    view = activity_view(cfg)
    assert view.mode == "wait"
    assert "LoRA" in view.line
