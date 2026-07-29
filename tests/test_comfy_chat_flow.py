"""Чат-оркестратор Comfy: рефы / взгляд / NL без имён тулов."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.character_refs import (
    assign_character_ref,
    load_character_refs,
    resolve_character_id,
)
from viu.integrations.comfy.chat_flow import (
    get_pending_look,
    get_pending_ref,
    parse_tg_photo_payload,
    set_pending_ref,
    try_handle_comfy_chat,
)
from viu.integrations.comfy.reference_vision import build_scene_action_en


def _cfg(tmp_path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def _png(path: Path) -> Path:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return path


def _mock_look(monkeypatch, text: str = "Смотрю: светлые волосы, мягкий свет, смотрю в кадр."):
    def fake_look(config, path, *, as_self=False, hint="", character_title=""):
        del config, path, hint, character_title
        prefix = "Это я. " if as_self else ""
        return True, prefix + text

    monkeypatch.setattr(
        "viu.integrations.comfy.reference_vision.look_at_photo",
        fake_look,
    )


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


def test_chat_looks_at_photo_when_its_you(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "ref.png")
    text = f"[tg_photo:{img}]\nвот, это ты. Посмотри, какая ты красивая."
    out = try_handle_comfy_chat(cfg, text)
    assert out.handled
    assert "Смотрю" in out.message or "волосы" in out.message
    assert "Вью" in out.message or "запомнила" in out.message.lower()
    assert get_pending_look(cfg)
    store = load_character_refs(cfg)
    assert Path(store["viu"].path).is_file()


def test_chat_always_looks_on_new_photo(tmp_path, monkeypatch):
    _mock_look(monkeypatch, "На фото девушка у окна.")
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "x.png")
    out = try_handle_comfy_chat(cfg, f"[tg_photo:{img}]")
    assert out.handled
    assert "девушк" in out.message.lower() or "окн" in out.message.lower()
    assert get_pending_ref(cfg) is not None


def test_chat_directed_scene_from_ref(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "s.png")
    out = try_handle_comfy_chat(
        cfg,
        f"[tg_photo:{img}]\nсними себя в фентезийном пейзаже на закате",
    )
    assert out.handled
    assert out.start_shoot
    assert "фентез" in out.shoot_action.lower() or "закат" in out.shoot_action.lower()
    assert "снимаю" in out.message.lower()


def test_chat_scene_description_after_pending(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "f.png")
    set_pending_ref(cfg, img, caption="", look_text="светлые волосы")
    out = try_handle_comfy_chat(
        cfg, "сцена: стоишь у окна и поправляешь волосы, мягкий свет"
    )
    assert out.handled
    assert out.start_shoot
    assert "окн" in out.shoot_action.lower() or "волос" in out.shoot_action.lower()


def test_chat_fantasy_landscape(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "f.png")
    set_pending_ref(cfg, img, caption="", look_text="светлые волосы")
    out = try_handle_comfy_chat(cfg, "сними себя в фентезийном пейзаже")
    assert out.handled
    assert out.start_shoot
    assert "фентез" in out.shoot_action.lower() or "fantasy" in out.shoot_action.lower()


def test_build_scene_action_en():
    from viu.integrations.comfy.reference_vision import extract_scene_wish

    a = build_scene_action_en(
        kind="scene",
        user_text="сними себя в лесу на закате",
        look_ru="рыжие волосы",
    )
    assert "лес" in a.lower() or "закат" in a.lower()
    assert "рыжие" in a.lower()
    assert extract_scene_wish("сними себя в лесу") == "в лесу"
    b = build_scene_action_en(kind="selfie", user_text="селфи", look_ru="я")
    assert "selfie" in b.lower()


def test_chat_assign_shanya_and_minotaur(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "s.png")
    out = try_handle_comfy_chat(cfg, f"[tg_photo:{img}]\nвот референс, так выглядит Шаня")
    assert out.handled
    assert load_character_refs(cfg)["shanya"].path
    img2 = _png(tmp_path / "m.png")
    out2 = try_handle_comfy_chat(cfg, f"[tg_photo:{img2}]\nэто минотавр")
    assert out2.handled
    assert load_character_refs(cfg)["minotaur"].path


def test_chat_pending_then_assign(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
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
    assert (
        "фото" in out.message.lower()
        or "сцен" in out.message.lower()
        or "реф" in out.message.lower()
    )


def test_set_pending_ref(tmp_path):
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "x.png")
    set_pending_ref(cfg, img, caption="hi", look_text="вижу свет")
    assert get_pending_ref(cfg) == img.resolve()
    assert get_pending_look(cfg) == "вижу свет"
