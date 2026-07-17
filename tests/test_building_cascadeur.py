"""Тесты building_workflow и Cascadeur."""

from pathlib import Path

from viu.building_workflow import parse_building_notes, read_sidecar_for_blend
from viu.integrations.cascadeur.status import cascadeur_status


def test_parse_open_wall():
    notes = parse_building_notes("building_type=barn\nopen_wall=front\n")
    assert notes.building_type == "barn"
    assert notes.open_wall == "front"
    assert notes.wants_open_wall


def test_parse_open_wall_ru():
    notes = parse_building_notes("open_wall=перед")
    assert notes.open_wall == "front"


def test_read_sidecar(tmp_path):
    blend = tmp_path / "hut.blend"
    blend.write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("open_wall=left", encoding="utf-8")
    assert "open_wall" in read_sidecar_for_blend(blend)


def test_cascadeur_status_no_exe(tmp_path, monkeypatch):
    from viu.config import Config

    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu", library_root=str(tmp_path / "lib"))
    cfg.ensure_dirs()
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "lib"))
    monkeypatch.delenv("VIU_CASCADEUR_EXE", raising=False)
    monkeypatch.setattr(
        "viu.integrations.cascadeur.exe.discover_cascadeur_exe",
        lambda: None,
    )
    ok, text = cascadeur_status(cfg)
    assert not ok
    assert "Cascadeur" in text
    assert (tmp_path / "lib" / "Cascadeur" / "Inbox").is_dir()


def test_discover_cascadeur_exe_u_drive(tmp_path, monkeypatch):
    from viu.integrations.cascadeur.exe import discover_cascadeur_exe, resolve_cascadeur_exe

    fake = tmp_path / "Cascadeur" / "App" / "Cascadeur" / "cascadeur.exe"
    fake.parent.mkdir(parents=True)
    fake.write_bytes(b"MZ")

    def fake_candidates():
        yield fake

    monkeypatch.setattr(
        "viu.integrations.cascadeur.exe._candidate_paths",
        fake_candidates,
    )
    assert discover_cascadeur_exe() == fake.resolve()

    from viu.config import Config

    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu")
    monkeypatch.delenv("VIU_CASCADEUR_EXE", raising=False)
    assert resolve_cascadeur_exe(cfg) == fake.resolve()
