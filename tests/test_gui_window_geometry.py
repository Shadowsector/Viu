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


def test_sanitize_offscreen_left_monitor():
    # Реальный runtime Дена: окно на -1029 (левый монитор выключен).
    out = sanitize_window_geometry("920x1053+-1029+667")
    m = re.match(r"^(\d+)x(\d+)\+(\d+)\+(\d+)$", out)
    assert m, out
    assert int(m.group(3)) >= 0
    assert int(m.group(4)) >= 0


def test_sanitize_keeps_normal():
    assert sanitize_window_geometry("1200x840+100+80") == "1200x840+100+80"
    assert sanitize_window_geometry("") == "1200x840"
    assert sanitize_window_geometry("1100x700") == "1100x700"
