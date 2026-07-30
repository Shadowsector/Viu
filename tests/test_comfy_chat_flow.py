"""Чат-оркестратор Comfy: рефы / взгляд / NL без имён тулов."""

from __future__ import annotations

import re
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
    assert "целиком" in msg.lower() or "Вью" in msg
    store = load_character_refs(cfg)
    assert Path(store["viu"].path).is_file()
    assert Path(store["viu"].body_path).is_file()


def test_chat_assign_text_before_photo(tmp_path, monkeypatch):
    from viu.integrations.comfy.chat_flow import get_pending_character

    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    out1 = try_handle_comfy_chat(cfg, "это ты.\nПосмотри, какая ты красивая!")
    assert out1.handled
    assert "кидай фото" in out1.message.lower()
    assert get_pending_character(cfg) == "viu"
    img = _png(tmp_path / "later.png")
    out2 = try_handle_comfy_chat(cfg, f"[tg_photo:{img}]")
    assert out2.handled
    assert load_character_refs(cfg)["viu"].path
    assert "если это я" not in out2.message.lower()


def test_chat_draw_in_comfy_armchair(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "me.png")
    assign_character_ref(cfg, "viu", img)
    out = try_handle_comfy_chat(cfg, "Ок, нарисуй себя в Комфи, как ты сидишь в кресле")
    assert out.handled
    assert out.start_shoot
    assert out.auto_fire
    assert out.wan_positive.startswith("a fit girl")
    assert "armchair" in out.shoot_action.lower() or "chair" in out.shoot_action.lower()
    assert not re.search(r"[А-Яа-яЁё]", out.shoot_action.split("matching")[0])
    assert "пришлю" in out.message.lower()


def test_chat_sprawled_in_armchair_en(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "me.png")
    assign_character_ref(cfg, "viu", img)
    out = try_handle_comfy_chat(cfg, "нарисуй себя, развалившуюся в кресле")
    assert out.handled
    assert out.start_shoot
    low = out.shoot_action.lower()
    assert "armchair" in low or "lounge" in low or "sprawl" in low
    assert "развал" not in low
    from viu.integrations.comfy.reference_vision import extract_scene_wish

    assert "кресл" in extract_scene_wish("нарисуй себя, развалившуюся в кресле")


def test_chat_make_photo_sexy_pose(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "p.png")
    out = try_handle_comfy_chat(
        cfg, f"[tg_photo:{img}]\nЭто ты.\nСделай фото, как ты стоишь в секси позе"
    )
    assert out.handled
    assert out.start_shoot
    low = out.shoot_action.lower()
    assert "pose" in low or "confident" in low or "hip" in low
    assert load_character_refs(cfg)["viu"].path


def test_look_quality_rejects_garble():
    from viu.integrations.comfy.reference_vision import (
        _look_quality_ok,
        format_look_from_fields,
        sanitize_vision_hint,
    )

    bad = "Она стоит на баскete в зале. If stands on basket toлько значит modelю."
    assert not _look_quality_ok(bad)
    good = "Стоя на площадке в зале, я в лёгком платье, мягкий свет падает на лицо."
    assert _look_quality_ok(good)
    llava_meta = (
        "Я вижу девушку в позе, но не могу показать ее первый лиц. "
        "Однако будут минуты от прироdesnogo света, я могу обservarь и упоминать такие elementy:\n"
        "1. Я observuju deвушку в поze\n"
        "2. Я могу показать предметы"
    )
    assert not _look_quality_ok(llava_meta)
    formatted = format_look_from_fields(
        {
            "КТО": "девушка-суккуб с рогами",
            "ОДЕЖДА": "тёмное бельё",
            "ПОЗА": "лежит в кресле",
            "ДЕЙСТВИЕ": "смотрит в камеру",
            "ВОЛОСЫ_ЛИЦО": "тёмные волосы, томный взгляд",
            "ФОН": "тусклая комната",
        }
    )
    assert "суккуб" in formatted.lower()
    assert "бельё" in formatted.lower()
    assert _look_quality_ok(formatted)
    assert "перепиш" not in sanitize_vision_hint(
        "Суккуб - это обычно девушка. Перепиши сцену и расскажи впечатления."
    ).lower() or "впечатлен" not in sanitize_vision_hint(
        "Суккуб - это обычно девушка. Перепиши сцену и расскажи впечатления от суккуба."
    ).lower()


def test_succubus_caption_does_not_assign_viu(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    _mock_look(monkeypatch, "На кадре девушка в тёмном белье, лежит расслабленно.")
    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        library_root=str(tmp_path / "Library"),
    ).ensure_dirs()
    from viu.integrations.comfy.chat_flow import set_pending_character

    set_pending_character(cfg, "viu", note="это ты")
    img = _png(tmp_path / "succ.png")
    out = try_handle_comfy_chat(
        cfg,
        f"[tg_photo:{img}]\nСуккуб - это обычно девушка.\n"
        "Перепиши сцену и расскажи впечатления от суккуба-девушки.",
    )
    assert out.handled
    low = out.message.lower()
    assert "запомнила тебя" not in low
    assert "ок — запомнила" not in low
    store = load_character_refs(cfg)
    assert not store["viu"].path
    assert "девушк" in low or "кадр" in low
    # Можно предложить «это ты», но не привязывать автоматом.
    assert "суккуб" not in low or "девушк" in low


def test_explicit_eto_ty_still_assigns(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "me.png")
    out = try_handle_comfy_chat(cfg, f"[tg_photo:{img}]\nэто ты")
    assert out.handled
    assert load_character_refs(cfg)["viu"].path
    assert "запомнила" in out.message.lower() or "Вью" in out.message


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
    low = out.shoot_action.lower()
    assert "fantasy" in low or "sunset" in low
    assert "делаю из рефа" in out.message.lower() or "пришлю" in out.message.lower()


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
    low = out.shoot_action.lower()
    assert "window" in low or "hair" in low


def test_lore_read_does_not_auto_shoot(tmp_path, monkeypatch):
    """«Почитай документы про Шаню» → reflect, не invent+PNG."""
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "body.png")
    assign_character_ref(cfg, "viu", img)
    for text in (
        "У тебя есть документы про Шаню, этот мир и её подруг, почитай",
        "У тебя есть документы про Шаню, этот мир и её подруг, так что можешь ознакомиться",
        "ознакомься с каноном Шаньки и подруг",
    ):
        out = try_handle_comfy_chat(cfg, text)
        assert not out.handled, text
        assert not out.auto_fire, text
        assert not out.start_shoot, text

    # Явная съёмка всё ещё работает.
    out_ok = try_handle_comfy_chat(cfg, "нарисуй эту девушку у окна")
    assert out_ok.handled and out_ok.auto_fire


def test_creative_fantasy_creatures_not_auto_png(tmp_path, monkeypatch):
    """«Придумай тварей из фентези/аниме» → reflect, не PNG+NSFW LoRA."""
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "body.png")
    assign_character_ref(cfg, "viu", img)
    text = (
        "Нет, солнце моё, придумывай новое. Мы же с тобой умные. "
        "Повспоминай интересных тварей из фентези книг, из аниме, из фильмов."
    )
    out = try_handle_comfy_chat(cfg, text)
    assert not out.handled
    assert not out.start_shoot
    assert not out.auto_fire

    # Без рефа — тоже.
    cfg2 = _cfg(tmp_path / "noref")
    out2 = try_handle_comfy_chat(cfg2, text)
    assert not out2.handled

    # Явная съёмка с фентези — всё ещё Comfy.
    out_ok = try_handle_comfy_chat(cfg, "сними себя в фентезийном пейзаже")
    assert out_ok.handled and out_ok.start_shoot

    out_draw = try_handle_comfy_chat(cfg, "нарисуй интересных тварей из фентези")
    assert out_draw.handled and out_draw.start_shoot


def test_scene_at_window_still_shoots(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "w.png")
    set_pending_ref(cfg, img, caption="", look_text="светлые волосы")
    out = try_handle_comfy_chat(cfg, "у окна в мягком свете, поправляешь волосы")
    assert out.handled
    assert out.start_shoot


def test_chat_fantasy_landscape(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "f.png")
    set_pending_ref(cfg, img, caption="", look_text="светлые волосы")
    out = try_handle_comfy_chat(cfg, "сними себя в фентезийном пейзаже")
    assert out.handled
    assert out.start_shoot
    assert "fantasy" in out.shoot_action.lower()


def test_build_scene_action_en():
    from viu.integrations.comfy.reference_vision import extract_scene_wish
    from viu.integrations.comfy.scene_en import has_cyrillic

    a = build_scene_action_en(
        kind="scene",
        user_text="сними себя в лесу на закате",
        look_ru="рыжие волосы, Вижу кадр — запомнила референс.",
    )
    assert "sunset" in a.lower() or "forest" in a.lower()
    assert not has_cyrillic(a)
    assert "matching the reference" not in a.lower()
    assert "рыжие" not in a.lower()
    assert extract_scene_wish("сними себя в лесу") == "в лесу"
    assert "armchair" in extract_scene_wish(
        "нарисуй себя, развалившуюся в кресле"
    ) or "кресл" in extract_scene_wish("нарисуй себя, развалившуюся в кресле")
    b = build_scene_action_en(kind="selfie", user_text="селфи", look_ru="я")
    assert "selfie" in b.lower()
    assert not has_cyrillic(b)
    sprawl = build_scene_action_en(
        kind="scene",
        user_text="нарисуй себя, развалившуюся в кресле",
        look_ru="Вижу кадр — запомнила референс.",
    )
    assert "armchair" in sprawl.lower()
    assert not has_cyrillic(sprawl)
    assert "matching" not in sprawl.lower()


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
    assert out.auto_fire
    assert out.wan_positive


def test_chat_does_not_steal_lab_ok(tmp_path):
    cfg = _cfg(tmp_path)
    assert not try_handle_comfy_chat(cfg, "ок").handled
    assert not try_handle_comfy_chat(cfg, "lora: 1").handled


def test_chat_comfy_hint_without_job(tmp_path):
    cfg = _cfg(tmp_path)
    out = try_handle_comfy_chat(cfg, "Комфи как тебе?")
    assert out.handled
    low = out.message.lower()
    assert "фото" in low or "промпт" in low or "lora" in low


def test_set_pending_ref(tmp_path):
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "x.png")
    set_pending_ref(cfg, img, caption="hi", look_text="вижу свет")
    assert get_pending_ref(cfg) == img.resolve()
    assert get_pending_look(cfg) == "вижу свет"
