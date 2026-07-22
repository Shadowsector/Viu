"""Тесты локального CHARACTERS_VISION.md."""

from __future__ import annotations

from pathlib import Path

from viu.characters_vision import (
    ensure_characters_vision,
    open_characters_vision,
    read_characters_vision,
)
from viu.config import Config


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(root=tmp_path / "Viu", data_dir=data)


def test_ensure_creates_once(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    p1 = ensure_characters_vision(cfg)
    assert p1.is_file()
    assert "Шанька" in p1.read_text(encoding="utf-8") or "Шаня" in p1.read_text(encoding="utf-8")
    p1.write_text("# mine\n**Типаж:** lithe\n", encoding="utf-8")
    p2 = ensure_characters_vision(cfg)
    assert p2.read_text(encoding="utf-8").startswith("# mine")


def test_read_and_gui_action(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    text = read_characters_vision(cfg)
    assert "CHARACTERS_VISION" in text
    from viu.gui_actions import GUI_ACTIONS

    assert any(a.tool == "__characters_vision__" for a in GUI_ACTIONS)


def test_open_returns_path(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)

    def fake_startfile(_path: str) -> None:
        return None

    monkeypatch.setattr("viu.characters_vision.os.startfile", fake_startfile, raising=False)
    monkeypatch.setattr("viu.characters_vision.sys.platform", "win32")
    ok, msg = open_characters_vision(cfg)
    assert ok
    assert "CHARACTERS_VISION.md" in msg
