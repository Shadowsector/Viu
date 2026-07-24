"""Тесты MoCap sanitize и LoRA pick format."""

from viu.integrations.comfy.mocap_sanitize import (
    extract_slug_token,
    has_mocap_fluff,
    sanitize_mocap_action,
)


def test_extract_slug_from_fluffy_edit():
    assert extract_slug_token("sit_down to pleasure herself") == "sit_down"


def test_has_mocap_fluff():
    assert has_mocap_fluff("moaning and sweat")
    assert not has_mocap_fluff("sit down from stand onto bed")


def test_sanitize_uses_canonical():
    action, note = sanitize_mocap_action(
        "sit_down to pleasure herself with jiggle physics",
        canonical="sit down from stand onto bed",
    )
    assert action == "sit down from stand onto bed"
    assert "MoCap" in note


def test_format_lora_short_names(tmp_path, monkeypatch):
    from viu.config import Config
    from viu.integrations.comfy.lora import format_lora_pick_message, scan_loras

    c = Config()
    c.data_dir = tmp_path / ".viu"
    c.data_dir.mkdir(parents=True)
    loras = tmp_path / "loras"
    loras.mkdir()
    long = "Anal-Side View Doggy_2V_T2V.safetensors"
    (loras / long).write_bytes(b"x" * 100)
    monkeypatch.setattr(
        "viu.integrations.comfy.lora.comfy_loras_dir",
        lambda _c: loras,
    )
    monkeypatch.setattr(
        "viu.integrations.comfy.lora.resolve_comfy_root",
        lambda _c: None,
    )
    entries = scan_loras(c)
    msg = format_lora_pick_message(entries)
    assert "Anal-Side View Doggy_2V_T2V" in msg
    assert ".safetensors" not in msg.split("1.")[1].split("\n")[0]
