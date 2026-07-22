"""LoRA: триггеры из (), sidecar txt, привязка по папке slug."""

from pathlib import Path

import pytest

from viu.config import Config
from viu.integrations.comfy.lora import (
    _read_sidecar_description,
    _triggers_from_filename,
    find_loras_for_slug,
    format_lora_pick_message,
    scan_loras,
    suggest_loras_for_slug,
)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    c = Config()
    c.data_dir = tmp_path / ".viu"
    c.data_dir.mkdir(parents=True)
    loras = tmp_path / "loras"
    loras.mkdir()
    monkeypatch.setattr(
        "viu.integrations.comfy.lora.comfy_loras_dir",
        lambda _c: loras,
    )
    monkeypatch.setattr(
        "viu.integrations.comfy.lora.resolve_comfy_root",
        lambda _c: None,
    )
    return c


def test_triggers_from_filename_parens():
    assert _triggers_from_filename("wan_motion_(touching herself).safetensors") == "touching herself"
    assert _triggers_from_filename("plain.safetensors") == ""


def test_sidecar_any_txt_in_folder(tmp_path):
    lora = tmp_path / "touch_self" / "motion_(touch).safetensors"
    lora.parent.mkdir(parents=True)
    lora.write_bytes(b"x")
    (lora.parent / "notes.txt").write_text("Any txt works", encoding="utf-8")
    assert "Any txt" in _read_sidecar_description(lora)


def test_scan_picks_trigger_and_description(cfg, tmp_path, monkeypatch):
    loras = tmp_path / "loras"
    sub = loras / "touch_self"
    sub.mkdir(parents=True)
    (sub / "motion_(touching herself).safetensors").write_bytes(b"x" * 100)
    (sub / "description.txt").write_text("Touches herself slowly", encoding="utf-8")
    entries = scan_loras(cfg)
    assert len(entries) == 1
    e = entries[0]
    assert e.trigger == "touching herself"
    assert "Touches" in e.description
    assert e.folder_slug == "touch_self"


def test_find_loras_for_slug_by_folder(cfg, tmp_path, monkeypatch):
    loras = tmp_path / "loras"
    sub = loras / "walk_cycle"
    sub.mkdir(parents=True)
    (sub / "stride_(walk).safetensors").write_bytes(b"x")
    scan_loras(cfg)
    found = find_loras_for_slug(cfg, "walk_cycle")
    assert len(found) == 1
    assert found[0].file.endswith(".safetensors")


def test_suggest_loras_merges_folder_bind(cfg, tmp_path, monkeypatch):
    loras = tmp_path / "loras"
    sub = loras / "idle_stand"
    sub.mkdir(parents=True)
    (sub / "pose_(idle).safetensors").write_bytes(b"x")
    scan_loras(cfg)
    specs = suggest_loras_for_slug(cfg, "idle_stand")
    assert len(specs) == 1
    assert specs[0].trigger == "idle"


def test_format_pick_shows_description(cfg, tmp_path, monkeypatch):
    loras = tmp_path / "loras"
    (loras / "a_(tag).safetensors").write_bytes(b"z" * 100)
    (loras / "a_(tag).txt").write_text("Test desc", encoding="utf-8")
    entries = scan_loras(cfg)
    msg = format_lora_pick_message(entries)
    assert "Test desc" in msg
    assert 'trigger="tag"' in msg
