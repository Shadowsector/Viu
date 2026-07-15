"""Тесты каталога существ."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.creature_catalog.lineup import build_lineup_job
from viu.creature_catalog.models import (
    GIRL_SOCKETS,
    CreatureEntry,
    suggest_locomotion_from_name,
    suggest_size_from_name,
)
from viu.creature_catalog.paths import creature_catalog_path, creatures_inbox_dir
from viu.creature_catalog.scanner import scan_creatures_inbox
from viu.creature_catalog.sockets import ensure_girl_sockets_doc, list_girl_socket_ids
from viu.creature_catalog.store import CreatureCatalogStore
from viu.tools import build_default_registry


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    lib = tmp_path / "Library"
    lib.mkdir()
    return Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        library_root=str(lib),
    ).ensure_dirs()


def test_girl_sockets_include_hands_and_cleavage():
    ids = list_girl_socket_ids()
    assert "socket_oral" in ids
    assert "socket_hand_l" in ids
    assert "socket_hand_r" in ids
    assert "socket_cleavage" in ids
    assert len(GIRL_SOCKETS) == 6


def test_suggest_size_goblin():
    assert "small" in suggest_size_from_name("Goblin_warrior")
    assert suggest_locomotion_from_name("green_slime") == "amorph"
    assert suggest_locomotion_from_name("mimic_chest") == "mimic"


def test_scan_and_set_size(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    inbox = creatures_inbox_dir(cfg)
    fbx = inbox / "Goblin_A.fbx"
    fbx.write_bytes(b"fbx")
    (inbox / "textures").mkdir()
    (inbox / "textures" / "a.png").write_bytes(b"x")

    added, total, msg = scan_creatures_inbox(cfg)
    assert added == 1
    assert total == 1
    assert "Goblin" in msg

    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    e = store.all()[0]
    assert e.textures_external
    assert e.status == "new"
    assert "small" in e.tags or "small" in e.notes

    updated = store.set_size(
        e.id, "small", size_alt=["humanoid"], locomotion="biped"
    )
    assert updated is not None
    assert updated.anim_bucket() == "small__biped"
    assert updated.size_alt == ["humanoid"]
    store.save()

    sock = ensure_girl_sockets_doc(cfg)
    assert sock.is_file()


def test_lineup_job(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    inbox = creatures_inbox_dir(cfg)
    fbx = inbox / "Wolf.fbx"
    fbx.write_bytes(b"fbx")
    scan_creatures_inbox(cfg)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    e = store.all()[0]
    store.set_size(e.id, "quad_med", locomotion="quadruped")
    store.save()

    ok, msg, job = build_lineup_job(cfg, size_filter=["quad_med"])
    assert ok, msg
    assert job.is_file()
    script = job.parent / "viu_creature_lineup.py"
    assert script.is_file()
    assert "import_scene.fbx" in script.read_text(encoding="utf-8")


def test_tools_registered():
    names = build_default_registry().names()
    assert "creature_catalog_scan" in names
    assert "creature_catalog_set_size" in names
    assert "creature_lineup" in names
