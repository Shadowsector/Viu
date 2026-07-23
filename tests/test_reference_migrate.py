"""Тесты миграции референсов из Library/References."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.reference_catalog.migrate import migrate_legacy_references
from viu.reference_catalog.scanner import scan_references_inbox


def test_migrate_legacy_references(tmp_path: Path, monkeypatch) -> None:
    viu = tmp_path / "Viu"
    anabarra = tmp_path / "Anabarra"
    lib = anabarra / "Library" / "References" / "images"
    lib.mkdir(parents=True)
    (lib / "old_ref.png").write_bytes(b"png")

    inbox = viu / "Inbox"
    refs = inbox / "references"
    refs.mkdir(parents=True)

    monkeypatch.setenv("VIU_ROOT", str(viu))
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(anabarra))
    cfg = Config(root=viu, data_dir=viu / ".viu")

    moved, notes = migrate_legacy_references(cfg, copy=True)
    assert moved == 1
    assert (refs / "old_ref.png").is_file()
    assert (lib / "old_ref.png").is_file()  # copy, not move

    added, total = scan_references_inbox(cfg)
    assert added >= 1
    assert total >= 1
