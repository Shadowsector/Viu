"""Тесты OSS-библиотеки анимаций (Mesh2Motion)."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.animation_catalog.paths import oss_animations_dir
from viu.animation_catalog.oss_library import (
    ensure_registry,
    fetch_to_inbox,
    prepare_exports,
    status_text,
)
from viu.anabarra_layout import inbox_dir
from viu.tools import build_default_registry


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(tmp_path / "Anabarra"))
    lib = tmp_path / "Library"
    lib.mkdir()
    (tmp_path / "Anabarra").mkdir()
    (tmp_path / "Viu").mkdir()
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    return Config(
        root=tmp_path / "Viu",
        data_dir=tmp_path / ".viu",
        library_root=str(lib),
    ).ensure_dirs()


def test_ensure_registry_wave1_slugs(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    reg = ensure_registry(cfg)
    by_slug = reg.get("by_slug") or {}
    assert "walk" in by_slug
    assert "sit_idle" in by_slug
    assert by_slug["walk"]["inbox_name"] == "Walking.fbx"
    assert (cfg.data_dir / "oss_animations.json").is_file()


def test_fetch_to_inbox_copies_with_mixamo_name(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ensure_registry(cfg)
    oss_dir = oss_animations_dir(cfg)
    (oss_dir / "walk.fbx").write_bytes(b"fbx")

    ok, msg = fetch_to_inbox(cfg, "walk", accept=False)
    assert ok, msg
    inbox_files = list(inbox_dir(cfg).glob("*.fbx"))
    assert len(inbox_files) == 1
    assert inbox_files[0].name == "Walking.fbx"


def test_prepare_exports(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ensure_registry(cfg)
    oss_dir = oss_animations_dir(cfg)
    (oss_dir / "idle.fbx").write_bytes(b"fbx")
    n, lines = prepare_exports(cfg, wave=1)
    assert n >= 1
    assert any("idle" in line for line in lines)
    export = oss_dir / "_export" / "Idle.fbx"
    assert export.is_file()


def test_status_text_mentions_mesh2motion(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ensure_registry(cfg)
    text = status_text(cfg)
    assert "mesh2motion" in text.lower()
    assert "OSS" in text


def test_oss_tools_registered():
    names = build_default_registry().names()
    assert "animation_oss_bootstrap" in names
    assert "animation_oss_fetch" in names
    assert "animation_oss_status" in names
    assert "animation_oss_prepare" in names
