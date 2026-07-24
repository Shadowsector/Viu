"""Тесты структуры папок Анабарры."""

from pathlib import Path

from viu.anabarra_layout import (
    anabarra_root,
    inbox_dir,
    library_root,
    migrate_inbox_to_anabarra,
    project_data_dir,
)
from viu.config import Config


def test_anabarra_root_from_unity_path(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_DATA_DIR", raising=False)
    monkeypatch.delenv("VIU_INBOX_DIR", raising=False)
    root = tmp_path / "Anabarra"
    viu = tmp_path / "Viu"
    viu.mkdir()
    unity = root / "Unity" / "Anabarra"
    unity.mkdir(parents=True)
    cfg = Config(root=viu, data_dir=viu / ".viu", unity_project=str(unity))
    assert anabarra_root(cfg) == root.resolve()
    assert library_root(cfg) == (root / "Library").resolve()
    assert project_data_dir(cfg) == (viu / ".viu").resolve()
    assert inbox_dir(cfg) == (root / "Inbox").resolve()


def test_inbox_defaults_to_anabarra_not_viu(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_INBOX_DIR", raising=False)
    monkeypatch.delenv("VIU_DOWNLOADS_DIR", raising=False)
    viu = tmp_path / "Viu"
    ana = tmp_path / "Anabarra"
    viu.mkdir()
    ana.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(ana))
    cfg = Config(root=viu, data_dir=viu / ".viu")
    assert inbox_dir(cfg) == (ana / "Inbox").resolve()
    assert inbox_dir(cfg) != (viu / "Inbox").resolve()
    assert inbox_dir(cfg) != Path.home() / "Downloads"


def test_migrate_inbox_from_viu_to_anabarra(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_INBOX_DIR", raising=False)
    viu = tmp_path / "Viu"
    ana = tmp_path / "Anabarra"
    viu.mkdir()
    ana.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(ana))
    old = viu / "Inbox" / "references"
    old.mkdir(parents=True)
    (old / "pose.png").write_bytes(b"pic")
    cfg = Config(root=viu, data_dir=viu / ".viu")
    ok, msg = migrate_inbox_to_anabarra(cfg)
    assert ok
    assert "перенесён" in msg
    assert (ana / "Inbox" / "references" / "pose.png").read_bytes() == b"pic"
    assert "Anabarra" in (viu / "Inbox" / "README.txt").read_text(encoding="utf-8")
