"""Тесты подготовки asset для Unity."""

import json

from viu.integrations.blender.prepare_asset import (
    _MARK_BEGIN,
    _MARK_END,
    find_inbox_blend,
    format_prepare_report,
    parse_prepare_output,
    prepared_output_path,
)


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
