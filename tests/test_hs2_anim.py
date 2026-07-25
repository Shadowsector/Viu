"""Тесты HS2 → анимации (без игры и Blender)."""

from pathlib import Path

import pytest

from viu.integrations.hs2.bone_map import hs2_bone_to_mixamo
from viu.integrations.hs2.catalog_hints import suggest_catalog_slug
from viu.integrations.hs2.fbx_import import import_fbx_dump
from viu.integrations.hs2.paths import hs2_fbx_dump_dir, resolve_hs2_root
from viu.integrations.hs2.scan import ClipIndexEntry, ScanResult, re_safe_name


def test_hs2_bone_map():
    assert hs2_bone_to_mixamo("cf_J_Hips") == "Hips"
    assert hs2_bone_to_mixamo("cf_J_L_Hand") == "LeftHand"


def test_catalog_slug_hints():
    assert suggest_catalog_slug("loop_IDLE_stand") == "idle"
    assert suggest_catalog_slug("anim_climb_wall") == "climb_up"
    assert suggest_catalog_slug("walk_backwards") == "walk_back"


def test_import_fbx_dump_to_inbox(tmp_path, monkeypatch):
    from viu.config import Config

    cfg = Config(data_dir=tmp_path / ".viu", root=tmp_path)
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(tmp_path / "Anabarra"))
    monkeypatch.setenv("VIU_HS2_FBX_DUMP", str(tmp_path / "dump"))
    dump = tmp_path / "dump"
    dump.mkdir()
    fbx = dump / "loop_sit_idle.fbx"
    fbx.write_bytes(b"FBX")

    report = import_fbx_dump(cfg, limit=5)
    assert report.ok
    assert report.copied
    dest = Path(report.copied[0][1])
    assert dest.is_file()
    assert "Sit" in dest.name or "sit" in dest.name.lower()


def test_resolve_hs2_root_env(tmp_path, monkeypatch):
    from viu.config import Config

    root = tmp_path / "HS2"
    (root / "abdata").mkdir(parents=True)
    monkeypatch.setenv("VIU_HS2_ROOT", str(root))
    cfg = Config()
    assert resolve_hs2_root(cfg) == root.resolve()


def test_scan_result_format():
    r = ScanResult(
        ok=True,
        clips=[
            ClipIndexEntry(name="idle", bundle="/x/y.unity3d", suggested_slug="idle"),
        ],
    )
    text = r.format_brief()
    assert "idle" in text


def test_re_safe_name():
    assert re_safe_name("a/b c") == "a_b_c"
