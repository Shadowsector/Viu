"""Тесты глаз: PNG encoder + registry."""

from pathlib import Path

from viu.integrations.screen.capture import _write_png
from viu.tools import build_default_registry
from viu.tools.eyes_tool import _looks_bad


def test_write_png(tmp_path):
    path = tmp_path / "t.png"
    # 2x2 red
    rgb = bytes([255, 0, 0] * 4)
    _write_png(path, 2, 2, rgb)
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert path.stat().st_size > 30


def test_registry_has_eyes():
    reg = build_default_registry()
    assert reg.get("screen_capture") is not None
    assert reg.get("vision_observe") is not None


def test_looks_bad():
    assert _looks_bad("Вердикт: BROKEN_IDLE тело искажено")
    assert _looks_bad("нет дома на фоне")
    assert not _looks_bad("Вердикт: OK всё видно")
