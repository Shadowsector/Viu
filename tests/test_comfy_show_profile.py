"""Профиль шоу-дубль: промпт, unet, workflow inject, chat/gui aliases."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.chat_flow import try_handle_comfy_chat
from viu.integrations.comfy.show_profile import (
    PROFILE_SHOW,
    SHOW_HEIGHT,
    SHOW_STEPS,
    SHOW_WIDTH,
    arm_show_profile,
    draft_show_bundle,
    find_show_unet,
    is_show_profile,
    normalize_profile,
    show_negative,
    show_positive,
)
from viu.integrations.comfy.workflows import inject_sampler_settings, prepare_show_workflow
from viu.gui_direct import parse_direct_tool_command
from viu.tools import build_default_registry


def _cfg(tmp_path: Path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_normalize_show_aliases():
    assert normalize_profile("шоу") == PROFILE_SHOW
    assert normalize_profile("smoothmix") == PROFILE_SHOW
    assert normalize_profile("mocap") == "mocap"
    assert normalize_profile("") == "mocap"


def test_show_positive_cinematic_no_white_bg():
    pos = show_positive("standing by a window", style="realism", has_smoothmix=True)
    assert "smoothmixrealism" in pos
    assert "cinematic" in pos.lower()
    assert "white background" not in pos.lower()
    assert "standing by a window" in pos


def test_show_positive_anime_trigger():
    pos = show_positive("walking", style="anime", has_smoothmix=True)
    assert "smoothmixanime" in pos
    assert "anime" in pos.lower()
    neg = show_negative(style="anime")
    assert "photorealistic" in neg


def test_draft_bundle_mentions_one_take():
    draft = draft_show_bundle("pose", style="realism", unet_note="test.safetensors")
    assert "ШОУ" in draft or "шоу" in draft.lower()
    assert "Дублей: 1" in draft
    assert "pose" in draft


def test_find_show_unet_discovers_smoothmix(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    root = tmp_path / "ComfyUI"
    models = root / "models" / "diffusion_models"
    models.mkdir(parents=True)
    (root / "main.py").write_text("# comfy\n", encoding="utf-8")
    (root / "comfy").mkdir()
    (models / "SmoothMix_Wan22_realism.safetensors").write_bytes(b"x")
    monkeypatch.setenv("VIU_COMFY_ROOT", str(root))
    monkeypatch.delenv("VIU_COMFY_SHOW_UNET", raising=False)
    cfg.comfy_root = str(root)
    name, note = find_show_unet(cfg)
    assert name == "SmoothMix_Wan22_realism.safetensors"
    assert "найдено" in note.lower() or "SmoothMix" in note


def test_arm_show_profile_meta():
    meta: dict = {}
    arm_show_profile(meta, style="anime", action="wave hello")
    assert is_show_profile(meta)
    assert meta["show_style"] == "anime"
    assert meta["action"] == "wave hello"
    assert meta.get("shoot_intent") is True


def test_prepare_show_workflow_frame_and_steps():
    wf = {
        "1": {
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {"width": 480, "height": 832, "length": 33},
        },
        "2": {
            "class_type": "KSampler",
            "inputs": {
                "steps": 20,
                "cfg": 6.0,
                "sampler_name": "uni_pc",
                "scheduler": "normal",
            },
        },
        "3": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": "wan2.1_t2v_1.3B_fp16.safetensors"},
        },
    }
    out = prepare_show_workflow(
        wf, filename_prefix="viu_show_test", unet_name="SmoothMix.safetensors"
    )
    latent = out["1"]["inputs"]
    assert latent["width"] == SHOW_WIDTH
    assert latent["height"] == SHOW_HEIGHT
    samp = out["2"]["inputs"]
    assert samp["steps"] == SHOW_STEPS
    assert samp["sampler_name"] == "euler"
    assert out["3"]["inputs"]["unet_name"] == "SmoothMix.safetensors"


def test_chat_wants_show_double(tmp_path):
    cfg = _cfg(tmp_path)
    out = try_handle_comfy_chat(cfg, "Хочу шоу-дубль")
    assert out.handled
    assert out.start_shoot
    assert out.render_profile == "show"
    assert out.show_style == "realism"
    assert "шоу" in out.message.lower()


def test_chat_show_anime_with_pose(tmp_path):
    cfg = _cfg(tmp_path)
    out = try_handle_comfy_chat(cfg, "шоу дубль аниме: standing near cherry blossom")
    assert out.handled
    assert out.render_profile == "show"
    assert out.show_style == "anime"
    assert "cherry" in out.shoot_action.lower() or "blossom" in out.shoot_action.lower()


def test_gui_alias_show_double():
    reg = build_default_registry()
    parsed = parse_direct_tool_command("хочу шоу-дубль", reg)
    assert parsed is not None
    assert parsed[0] == "comfy_show"
    parsed2 = parse_direct_tool_command("шоу аниме", reg)
    assert parsed2 == ("comfy_show", {"style": "anime"})
    assert "comfy_show" in reg.names()


def test_inject_sampler_only_first_ksampler():
    wf = {
        "a": {"class_type": "KSampler", "inputs": {"steps": 30}},
        "b": {"class_type": "KSampler", "inputs": {"steps": 30}},
    }
    out = inject_sampler_settings(wf, steps=8, sampler_name="euler")
    assert out["a"]["inputs"]["steps"] == 8
    assert out["b"]["inputs"]["steps"] == 30  # first only
