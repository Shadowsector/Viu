"""Тесты экспорта prepared → FBX."""

from pathlib import Path

from viu.config import Config
from viu.director import plan_next_step
from viu.integrations.blender.export_building import (
    export_building_fbx,
    pack_name_from_prepared,
    slugify_pack_name,
)
from viu.integrations.blender.export_pipeline import (
    needs_export,
    run_export_pipeline,
)


def test_slugify():
    assert slugify_pack_name("Old Stables") == "Old_Stables"


def test_pack_name_from_prepared():
    p = Path("U:/Lib/Processed/Old Stables/Old Stables_prepared.blend")
    assert pack_name_from_prepared(p) == "Old Stables"


def test_export_building_mock(tmp_path):
    blend = tmp_path / "barn_prepared.blend"
    blend.write_bytes(b"x")
    out = tmp_path / "barn.fbx"

    def fake_runner(cmd, capture_output=True, text=True, timeout=300.0):
        out.write_text("fake fbx", encoding="utf-8")
        from viu.integrations.blender.export_building import _MARK_BEGIN, _MARK_END
        import json

        payload = json.dumps({"meshes": ["Barn", "Wall_front"], "skipped": []})
        return type(
            "P",
            (),
            {"returncode": 0, "stdout": _MARK_BEGIN + payload + _MARK_END, "stderr": ""},
        )()

    report = export_building_fbx(str(blend), str(out), blender_exe="blender", runner=fake_runner)
    assert report["meshes"] == ["Barn", "Wall_front"]
    assert out.is_file()


def test_export_pipeline_mock(tmp_path, monkeypatch):
    lib = tmp_path / "Library"
    prepared = lib / "Processed" / "Old Stables" / "Old Stables_prepared.blend"
    prepared.parent.mkdir(parents=True)
    prepared.write_bytes(b"blend")
    unity = tmp_path / "Unity" / "Anabarra" / "Assets"
    unity.mkdir(parents=True)

    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        library_root=str(lib),
        unity_project=str(unity.parent),
    ).ensure_dirs()

    monkeypatch.setattr(
        "viu.integrations.blender.export_pipeline.resolve_blender_exe",
        lambda config: Path("blender"),
    )
    def fake_export(blend, out, blender_exe="blender"):
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fbx", encoding="utf-8")
        return {"meshes": ["Barn", "Wall_front"], "output": str(p)}

    monkeypatch.setattr(
        "viu.integrations.blender.export_pipeline.export_building_fbx",
        fake_export,
    )

    result = run_export_pipeline(cfg, blend_file=prepared)
    assert result.ok
    assert result.dollhouse_wall == "Wall_front"
    assert Path(result.unity_fbx).is_file()
    assert Path(result.metadata).is_file()


def test_director_suggests_export_before_overlay(tmp_path):
    import os

    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    lib = tmp_path / "Library"
    prepared = lib / "Processed" / "Old Stables" / "Old Stables_prepared.blend"
    prepared.parent.mkdir(parents=True)
    prepared.write_bytes(b"prepared")
    os.environ["VIU_INBOX_DIR"] = str(inbox)
    os.environ["VIU_LIBRARY_ROOT"] = str(lib)
    try:
        config = Config(
            root=tmp_path,
            data_dir=tmp_path / ".viu",
            inbox_dir=str(inbox),
            library_root=str(lib),
        ).ensure_dirs()
        plan = plan_next_step(config)
        assert plan.tool == "export_unity_asset"
        assert "Old Stables" in plan.message or "экспорт" in plan.message.lower()
    finally:
        os.environ.pop("VIU_INBOX_DIR", None)
        os.environ.pop("VIU_LIBRARY_ROOT", None)


def test_needs_export_when_no_fbx(tmp_path):
    lib = tmp_path / "Library"
    prepared = lib / "Processed" / "X" / "X_prepared.blend"
    prepared.parent.mkdir(parents=True)
    prepared.write_bytes(b"x")
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu", library_root=str(lib)).ensure_dirs()
    assert needs_export(cfg, prepared)
