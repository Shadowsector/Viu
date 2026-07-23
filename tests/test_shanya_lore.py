"""Канон Шаньки: lore, CHARACTERS_VISION seed, MoCap prompt."""

from __future__ import annotations

from pathlib import Path

from viu.characters_vision import ensure_characters_vision, read_characters_vision
from viu.config import Config
from viu.integrations.comfy.prompts import mocap_prompt
from viu.lore.shanya import (
    SHANYA_REFLECT_COMPACT,
    replace_shanya_section,
    shanya_section_needs_seed,
)
from viu.situational_context import build_reflect_notes


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(root=tmp_path / "Viu", data_dir=data)


def test_shanya_seed_fills_empty_template(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    path = ensure_characters_vision(cfg)
    text = path.read_text(encoding="utf-8")
    assert "табакси" in text.lower() or "балбеск" in text.lower()
    assert not shanya_section_needs_seed(text)


def test_shanya_seed_does_not_overwrite_user_edit(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    path = ensure_characters_vision(cfg)
    custom = replace_shanya_section(
        path.read_text(encoding="utf-8"),
        "### Шанька\n**Типаж:** моя версия\n**Характер:** уникальный\n",
    )
    path.write_text(custom, encoding="utf-8")
    ensure_characters_vision(cfg)
    assert "моя версия" in path.read_text(encoding="utf-8")


def test_mocap_prompt_tabaxi(monkeypatch):
    monkeypatch.setenv("VIU_COMFY_FACE_SWAP", "0")
    p = mocap_prompt("idle stand", None)
    assert "tabaxi" in p.lower()
    assert "white" in p.lower()
    assert "static" in p.lower()
    assert len(p) < 240


def test_mocap_prompt_human_with_face_swap(monkeypatch):
    monkeypatch.setenv("VIU_COMFY_FACE_SWAP", "1")
    p = mocap_prompt("lie down on back", None)
    assert "young woman" in p.lower()
    assert "tabaxi" not in p.lower()


def test_reflect_notes_include_shanya_canon(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    chat = build_reflect_notes(cfg, user_text="привет, как дела?")
    work = build_reflect_notes(cfg, user_text="чем занимаешься сейчас")
    for ctx in (chat, work):
        assert "Шанька" in ctx or "табакси" in ctx.lower()
        assert SHANYA_REFLECT_COMPACT[:40] in ctx
