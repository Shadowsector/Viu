"""LoRA scan, pick, workflow injection."""

import json
from pathlib import Path

import pytest

from viu.config import Config
from viu.integrations.comfy.lora import (
    LoraSpec,
    append_trigger_words,
    format_lora_pick_message,
    parse_lora_pick_reply,
    scan_loras,
    specs_from_indices,
    update_library_entry,
)
from viu.integrations.comfy.workflows import inject_loras


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    c = Config()
    c.data_dir = tmp_path / ".viu"
    c.data_dir.mkdir(parents=True)
    loras = tmp_path / "loras"
    loras.mkdir()
    monkeypatch.setattr(
        "viu.integrations.comfy.lora.comfy_loras_dir",
        lambda _c: loras,
    )
    monkeypatch.setattr(
        "viu.integrations.comfy.lora.resolve_comfy_root",
        lambda _c: None,
    )
    return c


def test_scan_loras_numbers_files(cfg, tmp_path, monkeypatch):
    loras = tmp_path / "loras"
    (loras / "wan_touch.safetensors").write_bytes(b"x" * 1000)
    (loras / "sub" / "walk_v2.safetensors").parent.mkdir(parents=True, exist_ok=True)
    (loras / "sub" / "walk_v2.safetensors").write_bytes(b"y" * 2000)
    entries = scan_loras(cfg)
    assert len(entries) == 2
    by_file = {e.file: e for e in entries}
    assert set(e.index for e in entries) == {1, 2}
    assert by_file["walk_v2.safetensors"].subfolder == "sub"


def test_parse_lora_pick_reply():
    assert parse_lora_pick_reply("lora: none") == []
    assert parse_lora_pick_reply("lora: 1,3", max_index=5) == [1, 3]
    assert parse_lora_pick_reply("lora: all", max_index=3) == [1, 2, 3]
    assert parse_lora_pick_reply("что-то") is None


def test_specs_from_indices(cfg, tmp_path, monkeypatch):
    loras = tmp_path / "loras"
    (loras / "a.safetensors").write_bytes(b"a")
    (loras / "b.safetensors").write_bytes(b"b")
    scan_loras(cfg)
    update_library_entry(cfg, "a.safetensors", trigger="touch motion", strength=0.7)
    specs = specs_from_indices(cfg, [1])
    assert len(specs) == 1
    assert specs[0].file == "a.safetensors"
    assert specs[0].trigger == "touch motion"
    assert specs[0].strength == 0.7


def test_format_pick_message_lists_numbers(cfg, tmp_path, monkeypatch):
    loras = tmp_path / "loras"
    (loras / "test.safetensors").write_bytes(b"z" * 500)
    entries = scan_loras(cfg)
    msg = format_lora_pick_message(entries)
    assert "1." in msg
    assert "lora: none" in msg


def test_append_trigger_words_no_dup():
    loras = [LoraSpec(file="x.safetensors", trigger="touching herself")]
    out = append_trigger_words("girl idle, touching herself", loras)
    assert out.count("touching herself") == 1


def test_inject_loras_chains_after_unet():
    t2v = Path(__file__).resolve().parents[1] / "viu/integrations/comfy/templates/t2v.json"
    wf = json.loads(t2v.read_text(encoding="utf-8"))
    specs = [LoraSpec(file="test_lora.safetensors", strength=0.9)]
    out = inject_loras(wf, specs)
    lora_nodes = [
        (nid, n)
        for nid, n in out.items()
        if isinstance(n, dict) and n.get("class_type") == "LoraLoaderModelOnly"
    ]
    assert len(lora_nodes) == 1
    lora_id, lora_node = lora_nodes[0]
    assert lora_node["inputs"]["model"] == ["37", 0]
    assert out["48"]["inputs"]["model"] == [lora_id, 0]


def test_registry_comfy_lora_tools():
    from viu.tools import build_default_registry

    reg = build_default_registry()
    for name in (
        "comfy_lora_list",
        "comfy_lora_scan",
        "comfy_lora_pick",
        "comfy_lora_note",
    ):
        assert reg.get(name) is not None
