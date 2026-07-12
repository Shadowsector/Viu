"""Tests for GUI window geometry persistence."""

from viu.config import Config
from viu.runtime_settings import get_window_geometry, set_window_geometry


def test_window_geometry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path))
    cfg = Config()
    assert get_window_geometry(cfg) == ""
    set_window_geometry(cfg, "1180+40+200")
    assert get_window_geometry(cfg) == "1180+40+200"
