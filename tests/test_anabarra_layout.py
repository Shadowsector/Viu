"""Тесты структуры папок Анабарры."""

from pathlib import Path

from viu.anabarra_layout import anabarra_root, inbox_dir, library_root, project_data_dir, viu_install_root
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
    assert inbox_dir(cfg) == (viu / "Inbox").resolve()


def test_inbox_not_home_downloads(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_INBOX_DIR", raising=False)
    monkeypatch.delenv("VIU_DOWNLOADS_DIR", raising=False)
    viu = tmp_path / "Viu"
    viu.mkdir()
    cfg = Config(root=viu, data_dir=viu / ".viu")
    assert inbox_dir(cfg) == (viu / "Inbox").resolve()
    assert inbox_dir(cfg) != Path.home() / "Downloads"
