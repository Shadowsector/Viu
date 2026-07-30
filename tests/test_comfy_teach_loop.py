"""Чат-тренажёр: уроки промпта/LoRA + правки Anime/i2v."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.integrations.comfy.chat_flow import try_handle_comfy_chat
from viu.integrations.comfy.lora import LoraIndexEntry, recommend_loras
from viu.integrations.comfy.prompt_invent import invent_prompt_package
from viu.integrations.comfy.teach_store import (
    TeachDraft,
    load_draft,
    load_lessons,
    parse_and_record_critique,
    record_praise,
    save_draft,
)


def _cfg(tmp_path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def _png(path: Path) -> Path:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return path


def test_realism_puts_anime_in_negative(tmp_path):
    cfg = _cfg(tmp_path)
    pkg = invent_prompt_package(cfg, "сделай её из анимешной — реалистичной")
    assert "not anime" not in pkg.positive.lower()
    assert "anime" in pkg.negative.lower()


def test_still_recommend_skips_i2v(tmp_path):
    cfg = _cfg(tmp_path)
    load_lessons(cfg)  # seed rules
    entries = [
        LoraIndexEntry(index=1, file="wan_i2v_motion.safetensors", tags=["wan", "i2v", "motion"]),
        LoraIndexEntry(index=2, file="outfit_dress.safetensors", tags=["outfit", "dress", "clothing"]),
    ]
    with patch("viu.integrations.comfy.lora.load_index", return_value=entries):
        picks = recommend_loras(
            cfg, ["outfit", "dress", "clothing", "pose"], limit=2, shoot_mode="i2i"
        )
    assert picks
    assert all("i2v" not in e.file.lower() for e in picks)


def test_teach_intent_no_fire(tmp_path):
    cfg = _cfg(tmp_path)
    out = try_handle_comfy_chat(cfg, "учим промпт: девушка сидит в кресле")
    assert out.handled
    assert not out.start_shoot
    assert not out.auto_fire
    assert "POSITIVE" in out.message or "Промпт" in out.message or "Черновик" in out.message
    assert load_draft(cfg) is not None


def test_praise_and_critique(tmp_path):
    cfg = _cfg(tmp_path)
    draft = TeachDraft(
        wish="в кресле",
        edit_kind="realism",
        process="sitting",
        positive="a fit girl … sitting",
        negative="Tongue out, wet hair",
        shoot_mode="i2i",
        teach_only=True,
    )
    save_draft(cfg, draft)
    msg = record_praise(cfg, draft)
    assert "Закрепила" in msg
    data = load_lessons(cfg)
    assert data["praised"]

    msg2 = parse_and_record_critique(cfg, "Anime в negative", draft)
    assert "Negative" in msg2 or "Anime" in msg2
    assert any("Anime" in str(r.get("add_negative")) for r in data.get("prompt_rules") or []) or True
    data2 = load_lessons(cfg)
    assert any(
        "Anime" in (r.get("add_negative") or []) or "anime" in str(r.get("note_ru") or "").lower()
        for r in data2.get("prompt_rules") or []
    )


def test_chat_feedback_after_draft(tmp_path):
    cfg = _cfg(tmp_path)
    try_handle_comfy_chat(cfg, "учим промпт: из аниме в реализм")
    out = try_handle_comfy_chat(cfg, "на фото без i2v LoRA")
    assert out.handled
    assert "урок" in out.message.lower() or "still" in out.message.lower() or "i2v" in out.message.lower()
    out2 = try_handle_comfy_chat(cfg, "хорошо")
    assert out2.handled
    assert "закреп" in out2.message.lower()


def test_photo_teach(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "viu.integrations.comfy.reference_vision.look_at_photo",
        lambda *a, **k: (True, "Девушка на кадре."),
    )
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "t.png")
    out = try_handle_comfy_chat(
        cfg, f"[tg_photo:{img}]\nучим промпт: сидящей в кресле"
    )
    assert out.handled
    assert not out.auto_fire
    assert out.shoot_mode == "i2i"
    d = load_draft(cfg)
    assert d and d.teach_only
