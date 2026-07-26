"""Tests for GUI window geometry persistence."""

import re

from viu.config import Config
from viu.runtime_settings import (
    get_window_geometry,
    sanitize_window_geometry,
    set_window_geometry,
)


def test_window_geometry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path))
    cfg = Config()
    assert get_window_geometry(cfg) == ""
    set_window_geometry(cfg, "1180x800+40+200")
    assert get_window_geometry(cfg) == "1180x800+40+200"


def test_sanitize_keeps_left_monitor_when_present(monkeypatch):
    monkeypatch.setattr(
        "viu.integrations.screen.monitor.list_monitor_rects",
        lambda: [(-1920, 0, 0, 1080), (0, 0, 1920, 1080)],
    )
    raw = "920x1053+-1029+667"
    assert sanitize_window_geometry(raw) == raw


def test_sanitize_resets_when_left_monitor_gone(monkeypatch):
    monkeypatch.setattr(
        "viu.integrations.screen.monitor.list_monitor_rects",
        lambda: [(0, 0, 1920, 1080)],
    )
    out = sanitize_window_geometry("920x1053+-1029+667")
    m = re.match(r"^(\d+)x(\d+)\+(\d+)\+(\d+)$", out)
    assert m, out
    assert int(m.group(3)) >= 0
    assert int(m.group(4)) >= 0


def test_sanitize_keeps_normal(monkeypatch):
    monkeypatch.setattr(
        "viu.integrations.screen.monitor.list_monitor_rects",
        lambda: [(0, 0, 1920, 1080)],
    )
    assert sanitize_window_geometry("1200x840+100+80") == "1200x840+100+80"
    assert sanitize_window_geometry("") == "1200x840"
    assert sanitize_window_geometry("1100x700") == "1100x700"
