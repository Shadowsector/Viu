"""Invent промпта + подбор LoRA для фото/желания из чата."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.integrations.comfy.character_refs import assign_character_ref
from viu.integrations.comfy.chat_flow import try_handle_comfy_chat
from viu.integrations.comfy.lora import LoraIndexEntry, recommend_loras
from viu.integrations.comfy.prompt_invent import (
    EDIT_ANIME,
    EDIT_OUTFIT,
    EDIT_POSE,
    EDIT_REALISM,
    classify_edit_kind,
    invent_prompt_package,
)
from viu.integrations.comfy.prompts import SUBJECT_PREFIX


def _cfg(tmp_path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def _png(path: Path) -> Path:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return path


def _mock_look(monkeypatch):
    def fake_look(config, path, *, as_self=False, hint="", character_title=""):
        del config, path, hint, character_title
        return True, ("Это я. " if as_self else "") + "Светлые волосы, мягкий свет."

    monkeypatch.setattr(
        "viu.integrations.comfy.reference_vision.look_at_photo",
        fake_look,
    )


def test_classify_edit_kinds():
    assert classify_edit_kind("эту девушку сидящей в кресле") == EDIT_POSE
    assert classify_edit_kind("сделай её из анимешной — реалистичной") == EDIT_REALISM
    assert classify_edit_kind("сделай аниме стиль") == EDIT_ANIME
    assert classify_edit_kind("надень на неё платье") == EDIT_OUTFIT
    # Голое «из аниме» в разговоре ≠ режим realism.
    from viu.integrations.comfy.prompt_invent import EDIT_GENERIC

    kind = classify_edit_kind("поваспоминай тварей из аниме и фильмов")
    assert kind in (EDIT_GENERIC, EDIT_POSE)
    assert kind != EDIT_REALISM


def test_invent_package_armchair_and_outfit(tmp_path):
    cfg = _cfg(tmp_path)
    pose = invent_prompt_package(cfg, "нарисуй эту девушку сидящей в кресле")
    assert pose.edit_kind == EDIT_POSE
    assert pose.positive.startswith(SUBJECT_PREFIX)
    assert "armchair" in pose.process.lower() or "chair" in pose.process.lower()
    assert "Tongue out" in pose.negative

    outfit = invent_prompt_package(cfg, "надень на неё платье")
    assert outfit.edit_kind == EDIT_OUTFIT
    assert "dress" in outfit.process.lower()

    real = invent_prompt_package(cfg, "из анимешной сделай реалистичной")
    assert real.edit_kind == EDIT_REALISM
    assert "photoreal" in real.process.lower() or "realistic" in real.process.lower()


def test_recommend_loras_scores_tags(tmp_path):
    cfg = _cfg(tmp_path)
    entries = [
        LoraIndexEntry(index=1, file="beauty_cinema.safetensors", tags=["beauty", "cinematic"]),
        LoraIndexEntry(index=2, file="wan_anime_style.safetensors", tags=["anime", "wan", "style"]),
        LoraIndexEntry(index=3, file="outfit_fashion.safetensors", tags=["outfit", "clothing", "dress"]),
    ]
    with patch("viu.integrations.comfy.lora.load_index", return_value=entries):
        anime = recommend_loras(cfg, ["anime", "wan", "style"], limit=2)
        assert anime and anime[0].file.startswith("wan_anime")
        outfit = recommend_loras(cfg, ["outfit", "dress", "clothing"], limit=1)
        assert outfit and "outfit" in outfit[0].file


def test_chat_photo_girl_armchair_auto_fire(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "girl.png")
    out = try_handle_comfy_chat(
        cfg, f"[tg_photo:{img}]\nнарисуй эту девушку сидящей в кресле"
    )
    assert out.handled
    assert out.start_shoot
    assert out.auto_fire
    assert out.wan_positive.startswith(SUBJECT_PREFIX)
    assert "armchair" in out.shoot_action.lower() or "chair" in out.shoot_action.lower()
    assert "пришлю" in out.message.lower()
    assert "панель" not in out.message.lower() or "без панели" in out.message.lower()


def test_chat_anime_to_real_auto_invent(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "a.png")
    assign_character_ref(cfg, "viu", img)
    out = try_handle_comfy_chat(
        cfg, f"[tg_photo:{img}]\nсделай её из анимешной — реалистичной"
    )
    assert out.handled
    assert out.auto_fire
    assert out.start_shoot
    assert "photoreal" in out.wan_positive.lower() or "realistic" in out.wan_positive.lower()
    low = out.message.lower()
    assert "realism" in low or "png" in low or "делаю" in low


def test_chat_outfit_invent(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "o.png")
    out = try_handle_comfy_chat(cfg, f"[tg_photo:{img}]\nнадень на неё платье")
    assert out.handled
    assert out.auto_fire
    assert "dress" in out.shoot_action.lower()
    assert out.wan_negative
