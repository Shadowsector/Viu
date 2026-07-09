"""Тесты подготовки asset для Unity."""

import json

from viu.integrations.blender.prepare_asset import (
    _MARK_BEGIN,
    _MARK_END,
    find_blend_for_prepare,
    find_inbox_blend,
    format_prepare_report,
    parse_prepare_output,
    prepared_output_path,
)
from viu.config import Config
from viu.prop_catalog.pack_layout import repair_split_pack


def test_find_inbox_blend_single_file(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    blend = inbox / "hut.blend"
    blend.write_bytes(b"x")
    assert find_inbox_blend(inbox) == blend


def test_find_inbox_blend_pack_folder(tmp_path):
    inbox = tmp_path / "Inbox"
    pack = inbox / "hut_pack"
    pack.mkdir(parents=True)
    blend = pack / "hut.blend"
    blend.write_bytes(b"x")
    assert find_inbox_blend(inbox) == blend


def test_prepared_output_path(tmp_path):
    lib = tmp_path / "Library"
    blend = tmp_path / "Inbox" / "hut_pack" / "hut.blend"
    out = prepared_output_path(blend, lib)
    assert out == lib / "Processed" / "hut_pack" / "hut_prepared.blend"


def test_parse_prepare_output():
    payload = {"source": "/a.blend", "output": "/b.blend", "packed_count": 3}
    stdout = f"noise\n{_MARK_BEGIN}{json.dumps(payload)}{_MARK_END}\n"
    assert parse_prepare_output(stdout)["packed_count"] == 3


def test_find_blend_from_library_when_inbox_empty(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    lib = tmp_path / "Library" / "Blender"
    lib.mkdir(parents=True)
    blend = lib / "Old Stables.blend"
    blend.write_bytes(b"x")
    cfg = Config(root=tmp_path / "Viu", data_dir=tmp_path / "Viu" / ".viu")
    import os

    os.environ["VIU_INBOX_DIR"] = str(inbox)
    os.environ["VIU_LIBRARY_ROOT"] = str(tmp_path / "Library")
    try:
        found, label = find_blend_for_prepare(cfg)
        assert found == blend.resolve()
        assert "Library" in label
    finally:
        os.environ.pop("VIU_INBOX_DIR", None)
        os.environ.pop("VIU_LIBRARY_ROOT", None)


def test_repair_split_textures(tmp_path):
    lib = tmp_path / "Library"
    blend = lib / "Blender" / "Old Stables.blend"
    blend.parent.mkdir(parents=True)
    blend.write_bytes(b"b")
    tex = lib / "References" / "images" / "textures"
    tex.mkdir(parents=True)
    (tex / "a.png").write_bytes(b"t")
    lines = repair_split_pack(blend, lib)
    assert lines
    assert (blend.parent / "textures").is_dir()
    assert not tex.exists()


def test_format_prepare_report():
    text = format_prepare_report(
        {
            "source": "/in/hut.blend",
            "output": "/out/hut_prepared.blend",
            "relinked_images": [{"name": "wood", "path": "/t/wood.png"}],
            "packed_count": 1,
            "hidden_objects": ["Ground"],
            "meshes": [{"name": "Shell_Wall", "suggest_role": "shell"}],
            "blender_opened": True,
        }
    )
    assert "hut_prepared.blend" in text
    assert "Ground" in text
    assert "Shell_Wall" in text
