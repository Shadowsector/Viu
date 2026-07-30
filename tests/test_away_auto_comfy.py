"""Away AFK: Comfy auto-start off by default."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.runtime_settings import get_away_auto_comfy, set_away_auto_comfy


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(root=tmp_path / "Viu", data_dir=data).ensure_dirs()


def test_away_auto_comfy_default_off(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_AWAY_AUTO_COMFY", raising=False)
    cfg = _cfg(tmp_path, monkeypatch)
    assert get_away_auto_comfy(cfg) is False


def test_away_auto_comfy_env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_AWAY_AUTO_COMFY", "1")
    cfg = _cfg(tmp_path, monkeypatch)
    assert get_away_auto_comfy(cfg) is True


def test_away_auto_comfy_runtime_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_AWAY_AUTO_COMFY", "1")
    cfg = _cfg(tmp_path, monkeypatch)
    set_away_auto_comfy(cfg, False)
    assert get_away_auto_comfy(cfg) is False
    set_away_auto_comfy(cfg, True)
    assert get_away_auto_comfy(cfg) is True


def test_reflect_voice_splits_viu_and_shanya():
    from viu.prompts.reflect_mode import REFLECT_BODY_BOUNDARY, REFLECT_VOICE
    from viu.situational_context import _REFLECT_CHAT_BRIEF

    voice = REFLECT_VOICE.lower()
    assert "не шаня" in voice or "сама ты не шаня" in voice
    assert "без кошачьих ушей" in voice
    assert "шаня" in voice
    # Не путать: «твой … уши и хвост» больше не про Вью.
    assert "твой смелый голос" not in voice
    assert "твой смелый голос" not in _REFLECT_CHAT_BRIEF.lower()
    boundary = REFLECT_BODY_BOUNDARY.lower()
    assert "без хвоста" in boundary
    assert "мужск" in boundary
    assert "шанька" in boundary or "шаня" in boundary


def test_reflect_life_block_body_before_shanya(tmp_path, monkeypatch):
    from viu.config import Config
    from viu.situational_context import format_reflect_life_block

    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config(root=tmp_path / "Viu", data_dir=tmp_path / ".viu").ensure_dirs()
    text = format_reflect_life_block(cfg)
    assert "обычная человеческая девушка" in text.lower() or "без хвоста" in text.lower()
    assert "не тело вью" in text.lower() or "отдельный персонаж" in text.lower()
    # Тело Вью раньше канона Шани.
    i_body = text.lower().find("тело вью")
    i_shanya = text.lower().find("шанька")
    assert i_body >= 0 and i_shanya > i_body
