"""Comfy Studio: LoRA preset без awaiting_lora_pick."""

from __future__ import annotations

from viu.integrations.comfy.lora import LoraIndexEntry, save_index
from viu.integrations.comfy.studio_gui import apply_lora_from_indices
from viu.lab.comfy_pipeline import COMFY_TOPIC
from viu.lab.session import load_session, new_session, save_session


def test_apply_lora_preset_while_idle(tmp_path, monkeypatch):
    from viu.config import Config

    cfg = Config(data_dir=tmp_path / ".viu")
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        LoraIndexEntry(index=1, file="a.safetensors", size_mb=1.0),
        LoraIndexEntry(index=2, file="b.safetensors", size_mb=2.0),
    ]
    save_index(cfg, entries)
    monkeypatch.setattr(
        "viu.integrations.comfy.studio_gui.scan_loras",
        lambda _c: entries,
    )
    sess = new_session(COMFY_TOPIC)
    sess.status = "running"
    save_session(cfg, sess)

    msg = apply_lora_from_indices(cfg, [2])
    assert "Пресет" in msg or "b.safetensors" in msg
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.meta.get("lora_last_pick") == [2]
    assert loaded.meta["selected_loras"][0]["file"] == "b.safetensors"
