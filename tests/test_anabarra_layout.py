"""Тесты структуры папок Анабарры."""

from pathlib import Path

from viu.anabarra_layout import anabarra_root, library_root, project_data_dir
from viu.config import Config


def test_anabarra_root_from_unity_path(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_DATA_DIR", raising=False)
    root = tmp_path / "Anabarra"
    unity = root / "Unity" / "Anabarra"
    unity.mkdir(parents=True)
    cfg = Config(root=tmp_path, data_dir=root / ".viu", unity_project=str(unity))
    assert anabarra_root(cfg) == root.resolve()
    assert library_root(cfg) == (root / "Library").resolve()
    assert project_data_dir(cfg) == (root / ".viu").resolve()
