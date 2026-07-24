"""Тесты единого Inbox и каталога референсов."""

from __future__ import annotations

from viu.config import Config
from viu.inbox_layout import inbox_references_dir
from viu.reference_catalog.scanner import scan_references_inbox


def test_inbox_references_subdir(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_INBOX_DIR", str(tmp_path / "Inbox"))
    cfg = Config(root=tmp_path).ensure_dirs()
    refs = inbox_references_dir(cfg)
    assert refs.name == "references"
    assert refs.parent.name == "Inbox"


def test_scan_references_inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_INBOX_DIR", str(tmp_path / "Inbox"))
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config(root=tmp_path).ensure_dirs()
    refs = inbox_references_dir(cfg)
    (refs / "pose_ref.png").write_bytes(b"png")
    added, total = scan_references_inbox(cfg)
    assert added == 1
    assert total == 1
