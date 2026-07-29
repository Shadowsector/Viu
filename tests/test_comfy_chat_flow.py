"""Чат-оркестратор Comfy: рефы / NL без имён тулов."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.character_refs import (
    assign_character_ref,
    load_character_refs,
    resolve_character_id,
)
from viu.integrations.comfy.chat_flow import (
    get_pending_ref,
    parse_tg_photo_payload,
    set_pending_ref,
    try_handle_comfy_chat,
)


def _cfg(tmp_path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def _png(path: Path) -> Path:
    # минимальный валидный PNG 1x1
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return path


def test_resolve_character_aliases():
    assert resolve_character_id("это Шаня") == "shanya"
    assert resolve_character_id("минотавр") == "minotaur"
    assert resolve_character_id("ты") == "viu"


def test_assign_character_ref(tmp_path):
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "face.png")
    ok, msg = assign_character_ref(cfg, "viu", img)
    assert ok
    assert "Вью" in msg
    store = load_character_refs(cfg)
    assert Path(store["viu"].path).is_file()


def test_parse_tg_photo_payload():
    p, cap = parse_tg_photo_payload("[tg_photo:/tmp/a.jpg]\nэто ты")
    assert str(p) == "/tmp/a.jpg"
    assert cap == "это ты"


def test_chat_assign_from_photo_caption(tmp_path):
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "ref.png")
    text = f"[tg_photo:{img}]\nэто ты"
    out = try_handle_comfy_chat(cfg, text)
    assert out.handled
    assert "Вью" in out.message
    store = load_character_refs(cfg)
    assert Path(store["viu"].path).is_file()


def test_chat_assign_shanya_and_minotaur(tmp_path):
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "s.png")
    out = try_handle_comfy_chat(cfg, f"[tg_photo:{img}]\nвот референс, так выглядит Шаня")
    assert out.handled
    assert load_character_refs(cfg)["shanya"].path
    img2 = _png(tmp_path / "m.png")
    out2 = try_handle_comfy_chat(cfg, f"[tg_photo:{img2}]\nэто минотавр")
    assert out2.handled
    assert load_character_refs(cfg)["minotaur"].path


def test_chat_pending_then_assign(tmp_path):
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "p.png")
    out = try_handle_comfy_chat(cfg, f"[tg_photo:{img}]")
    assert out.handled
    assert get_pending_ref(cfg) is not None
    out2 = try_handle_comfy_chat(cfg, "это Шаня")
    assert out2.handled
    assert "Шаня" in out2.message


def test_chat_video_with_comfy_starts_shoot(tmp_path):
    cfg = _cfg(tmp_path)
    out = try_handle_comfy_chat(cfg, "сделай видео в Комфи")
    assert out.handled
    assert out.start_shoot


def test_chat_does_not_steal_lab_ok(tmp_path):
    cfg = _cfg(tmp_path)
    assert not try_handle_comfy_chat(cfg, "ок").handled
    assert not try_handle_comfy_chat(cfg, "lora: 1").handled


def test_chat_comfy_hint_without_job(tmp_path):
    cfg = _cfg(tmp_path)
    out = try_handle_comfy_chat(cfg, "Комфи как тебе?")
    assert out.handled
    assert "реф" in out.message.lower() or "LoRA" in out.message or "видео" in out.message.lower()


def test_set_pending_ref(tmp_path):
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "x.png")
    set_pending_ref(cfg, img, caption="hi")
    assert get_pending_ref(cfg) == img.resolve()
