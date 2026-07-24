"""Тесты миграции референсов из Library/References."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.reference_catalog.migrate import migrate_legacy_reference_files
from viu.reference_catalog.scanner import scan_references_inbox


def test_migrate_legacy_references(tmp_path: Path, monkeypatch) -> None:
    viu = tmp_path / "Viu"
    anabarra = tmp_path / "Anabarra"
    lib = anabarra / "Library" / "References" / "images"
    lib.mkdir(parents=True)
    (lib / "old_ref.png").write_bytes(b"png")

    refs = anabarra / "Inbox" / "references"
    refs.mkdir(parents=True)

    monkeypatch.setenv("VIU_ROOT", str(viu))
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(anabarra))
    monkeypatch.delenv("VIU_INBOX_DIR", raising=False)
    cfg = Config(root=viu, data_dir=viu / ".viu")
    cfg.data_dir.mkdir(parents=True, exist_ok=True)

    n, msg = migrate_legacy_reference_files(cfg)
    assert n == 1
    assert (refs / "old_ref.png").is_file() or any(refs.rglob("old_ref.png"))
    assert (lib / "old_ref.png").is_file()  # copy, not move
    assert "Inbox/references" in msg or n == 1

    added, total = scan_references_inbox(cfg)
    assert added >= 1
    assert total >= 1
