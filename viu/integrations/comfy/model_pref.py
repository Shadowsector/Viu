"""Предпочтительная видеомодель: Wan 2.1 (T2V 1.3B + I2V при seed)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from ...config import Config
from .paths import resolve_comfy_root

# Выбор Вью: Wan 2.1 — лучший open T2V/I2V для явного full-body motion под Cascadeur MoCap.
# На ~6–8 GB VRAM: T2V 1.3B; I2V 480p 14B — только если влезет (fp8/gguf).
PREFERRED_FAMILY = "Wan 2.1"
PREFERRED_T2V = "wan2.1_t2v_1.3B_fp16.safetensors"
PREFERRED_I2V = "wan2.1_i2v_480p_14B_fp16.safetensors"
PREFERRED_VAE = "wan_2.1_vae.safetensors"
PREFERRED_TEXT_ENCODER = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
PREFERRED_CLIP_VISION = "clip_vision_h.safetensors"

T2V_WORKFLOW = "t2v"
I2V_WORKFLOW = "i2v"


@dataclass
class ModelProbe:
    root: Path | None
    family: str
    t2v_ok: bool
    i2v_ok: bool
    vae_ok: bool
    text_ok: bool
    clip_vision_ok: bool
    notes: List[str]

    @property
    def ready_t2v(self) -> bool:
        return bool(self.root) and self.t2v_ok and self.vae_ok and self.text_ok

    @property
    def ready_i2v(self) -> bool:
        return self.ready_t2v and self.i2v_ok and self.clip_vision_ok


def _exists_under(models: Path, *parts: str, names: Tuple[str, ...]) -> bool:
    folder = models.joinpath(*parts)
    if not folder.is_dir():
        return False
    lower = {p.name.lower() for p in folder.iterdir() if p.is_file()}
    for name in names:
        if name.lower() in lower:
            return True
        # partial match (fp8 / gguf variants)
        stem = name.lower().split("_fp")[0].split(".gguf")[0]
        if any(stem in n for n in lower):
            return True
    return False


def probe_models(config: Config) -> ModelProbe:
    root = resolve_comfy_root(config)
    notes: List[str] = []
    if root is None:
        return ModelProbe(
            None,
            PREFERRED_FAMILY,
            False,
            False,
            False,
            False,
            False,
            ["ComfyUI не найден — жду U:\\Viu\\ComfyUI"],
        )
    models = root / "models"
    t2v = _exists_under(
        models,
        "diffusion_models",
        names=(PREFERRED_T2V, "wan2.1_t2v_1.3B", "wan2.1-t2v-1.3b"),
    )
    i2v = _exists_under(
        models,
        "diffusion_models",
        names=(PREFERRED_I2V, "wan2.1_i2v_480p", "wan2.1-i2v"),
    )
    vae = _exists_under(models, "vae", names=(PREFERRED_VAE, "wan_2.1_vae"))
    text = _exists_under(
        models,
        "text_encoders",
        names=(PREFERRED_TEXT_ENCODER, "umt5_xxl"),
    ) or _exists_under(models, "clip", names=(PREFERRED_TEXT_ENCODER, "umt5_xxl"))
    clip_v = _exists_under(
        models,
        "clip_vision",
        names=(PREFERRED_CLIP_VISION, "clip_vision_h"),
    )
    if not t2v:
        notes.append(f"Нет T2V: models/diffusion_models/{PREFERRED_T2V}")
    if not i2v:
        notes.append(f"I2V опционально: {PREFERRED_I2V} (для last-frame → next)")
    if not vae:
        notes.append(f"Нет VAE: models/vae/{PREFERRED_VAE}")
    if not text:
        notes.append(f"Нет text encoder: models/text_encoders/{PREFERRED_TEXT_ENCODER}")
    if t2v and vae and text:
        notes.append(f"{PREFERRED_FAMILY} T2V готов к генерации.")
    return ModelProbe(root, PREFERRED_FAMILY, t2v, i2v, vae, text, clip_v, notes)


def choose_workflow_name(config: Config, *, has_seed_image: bool) -> str:
    probe = probe_models(config)
    if has_seed_image and probe.ready_i2v:
        return I2V_WORKFLOW
    return T2V_WORKFLOW
