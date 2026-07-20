"""LoRA registry + workflow injection."""

import json
from pathlib import Path

import pytest

from viu.config import Config
from viu.integrations.comfy.lora import (
    LoraSpec,
    append_trigger_words,
    bind_slug,
    ensure_lora_files,
    ensure_registry,
    load_registry,
    resolve_loras_for_slug,
)
from viu.integrations.comfy.workflows import inject_loras


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.data_dir = tmp_path / ".viu"
    c.data_dir.mkdir(parents=True)
    return c


def test_ensure_registry_creates_template(cfg):
    path = ensure_registry(cfg)
    assert path.is_file()
    data = load_registry(cfg)
    assert "touch_self" in (data.get("by_slug") or {})


def test_bind_slug_appends(cfg):
    bind_slug(cfg, catalog_slug="wave", lora_file="wave_v1.safetensors", strength=0.7)
    specs = resolve_loras_for_slug(cfg, "wave")
    assert len(specs) == 1
    assert specs[0].file == "wave_v1.safetensors"
    assert specs[0].strength == 0.7


def test_resolve_only_for_matching_slug(cfg):
    bind_slug(cfg, catalog_slug="touch_self", lora_file="a.safetensors")
    assert resolve_loras_for_slug(cfg, "touch_self")
    assert resolve_loras_for_slug(cfg, "idle_stand") == []


def test_append_trigger_words_no_dup():
    loras = [LoraSpec(file="x.safetensors", trigger="touching herself")]
    out = append_trigger_words("girl idle, touching herself", loras)
    assert out.count("touching herself") == 1
    out2 = append_trigger_words("girl idle", loras)
    assert "touching herself" in out2


def test_inject_loras_chains_after_unet(cfg):
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
    assert lora_node["inputs"]["lora_name"] == "test_lora.safetensors"
    assert lora_node["inputs"]["strength_model"] == 0.9
    assert lora_node["inputs"]["model"] == ["37", 0]
    assert out["48"]["inputs"]["model"] == [lora_id, 0]


def test_inject_loras_empty_unchanged(cfg):
    t2v = Path(__file__).resolve().parents[1] / "viu/integrations/comfy/templates/t2v.json"
    wf = json.loads(t2v.read_text(encoding="utf-8"))
    out = inject_loras(wf, [])
    assert out == wf


def test_ensure_lora_files_missing(cfg, tmp_path, monkeypatch):
    bind_slug(cfg, catalog_slug="x", lora_file="missing.safetensors")
    specs = resolve_loras_for_slug(cfg, "x")
    monkeypatch.setattr(
        "viu.integrations.comfy.lora.comfy_loras_dir",
        lambda _c: tmp_path / "loras",
    )
    ok, notes = ensure_lora_files(cfg, specs, auto_fetch=False)
    assert not ok
    assert any("НЕТ" in n for n in notes)


def test_registry_comfy_lora_tools():
    from viu.tools import build_default_registry

    reg = build_default_registry()
    for name in ("comfy_lora_list", "comfy_lora_bind", "comfy_lora_fetch"):
        assert reg.get(name) is not None
