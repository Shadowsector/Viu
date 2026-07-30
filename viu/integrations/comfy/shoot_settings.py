"""Единые настройки съёмки: режим (t2v/i2v/t2i/i2i), длина, чекпоинт.

Хранятся в session.meta lab-топика comfy — панель «Съёмка» и generate читают отсюда.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from ...config import Config
from .paths import resolve_comfy_root
from .show_profile import SHOW_FPS, SHOW_LENGTH

# Режимы генерации (как выбор LoRA — явно в панели).
MODE_T2V = "t2v"
MODE_I2V = "i2v"
MODE_T2I = "t2i"
MODE_I2I = "i2i"
SHOOT_MODES = (MODE_T2V, MODE_I2V, MODE_T2I, MODE_I2I)

_MODE_ALIASES = {
    "text2video": MODE_T2V,
    "txt2vid": MODE_T2V,
    "img2video": MODE_I2V,
    "image2video": MODE_I2V,
    "text2image": MODE_T2I,
    "txt2img": MODE_T2I,
    "img2img": MODE_I2I,
    "image2image": MODE_I2I,
}

META_MODE = "shoot_mode"
META_LENGTH = "video_length_frames"
META_UNET = "shoot_unet"
META_PROFILE = "render_profile"
META_STYLE = "show_style"

# Разумные пределы кадров Wan (~24 fps).
MIN_FRAMES = 17
MAX_FRAMES = 121
DEFAULT_MOCAP_FRAMES = 81


def normalize_shoot_mode(raw: str) -> str:
    key = (raw or "").strip().lower().replace("-", "").replace("_", "")
    if key in SHOOT_MODES:
        return key
    return _MODE_ALIASES.get((raw or "").strip().lower(), MODE_T2V)


def mode_needs_seed(mode: str) -> bool:
    return normalize_shoot_mode(mode) in (MODE_I2V, MODE_I2I)


def mode_is_image(mode: str) -> bool:
    return normalize_shoot_mode(mode) in (MODE_T2I, MODE_I2I)


def mode_is_video(mode: str) -> bool:
    return not mode_is_image(mode)


def clamp_frames(n: int) -> int:
    try:
        v = int(n)
    except (TypeError, ValueError):
        v = SHOW_LENGTH
    # Wan любит нечётную длину (start + motion).
    if v % 2 == 0:
        v += 1
    return max(MIN_FRAMES, min(MAX_FRAMES, v))


def frames_from_seconds(seconds: float, *, fps: float = SHOW_FPS) -> int:
    try:
        sec = float(seconds)
    except (TypeError, ValueError):
        sec = SHOW_LENGTH / fps
    return clamp_frames(int(round(sec * float(fps))))


def seconds_from_frames(frames: int, *, fps: float = SHOW_FPS) -> float:
    return round(clamp_frames(frames) / float(fps), 2)


def list_diffusion_checkpoints(config: Config) -> List[str]:
    """Файлы в models/diffusion_models (UNET / Wan / SmoothMix)."""
    root = resolve_comfy_root(config)
    if root is None:
        return []
    folder = root / "models" / "diffusion_models"
    if not folder.is_dir():
        return []
    out: List[str] = []
    try:
        for p in folder.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".safetensors", ".gguf", ".pt", ".ckpt"):
                continue
            out.append(p.name)
    except OSError:
        return []
    out.sort(key=lambda n: n.lower())
    return out


def shoot_mode_from_meta(meta: dict | None) -> str:
    if not isinstance(meta, dict):
        return MODE_T2V
    return normalize_shoot_mode(str(meta.get(META_MODE) or MODE_T2V))


def length_from_meta(meta: dict | None, *, default: int = SHOW_LENGTH) -> int:
    if not isinstance(meta, dict):
        return clamp_frames(default)
    raw = meta.get(META_LENGTH)
    if raw is None or str(raw).strip() == "":
        return clamp_frames(default)
    try:
        return clamp_frames(int(raw))
    except (TypeError, ValueError):
        return clamp_frames(default)


def unet_from_meta(meta: dict | None) -> str:
    if not isinstance(meta, dict):
        return ""
    return str(meta.get(META_UNET) or "").strip()


def apply_shoot_settings(
    meta: dict,
    *,
    mode: str = "",
    length_frames: int | None = None,
    unet: str = "",
    clear_unet: bool = False,
) -> dict:
    if mode:
        meta[META_MODE] = normalize_shoot_mode(mode)
    if length_frames is not None:
        meta[META_LENGTH] = clamp_frames(length_frames)
    if clear_unet:
        meta.pop(META_UNET, None)
    elif unet.strip():
        meta[META_UNET] = unet.strip()
    return meta


def describe_mode(mode: str) -> str:
    m = normalize_shoot_mode(mode)
    return {
        MODE_T2V: "T2V — текст → видео (без эталона)",
        MODE_I2V: "I2V — эталон → видео",
        MODE_T2I: "T2I — текст → картинка (граф позже; пока черновик)",
        MODE_I2I: "I2I — эталон → картинка (граф позже; пока черновик)",
    }.get(m, m)


def resolve_workflow_for_shoot(
    config: Config,
    meta: dict | None,
    *,
    has_seed: bool,
    is_show: bool,
) -> Tuple[str, str]:
    """Вернуть (workflow_name, note). Картиночные режимы пока падают на video-граф."""
    from .model_pref import choose_workflow_name

    mode = shoot_mode_from_meta(meta)
    if mode_is_image(mode):
        # Пока нет отдельных t2i/i2i графов — честно говорим и снимаем video.
        note = f"{describe_mode(mode)} → временно как video"
        if mode == MODE_I2I and has_seed:
            return choose_workflow_name(config, has_seed_image=True), note
        return "t2v", note

    if mode == MODE_T2V:
        return "t2v", describe_mode(mode)
    if mode == MODE_I2V:
        if not has_seed:
            return "t2v", "I2V выбран, но эталона нет → T2V"
        wf = choose_workflow_name(config, has_seed_image=True)
        if wf != "i2v":
            return "t2v", "I2V модели нет → T2V (comfy_install i2v=1)"
        return "i2v", describe_mode(mode)

    # Авто: шоу по умолчанию T2V; mocap — seed если есть.
    if is_show:
        return "t2v", "шоу: T2V"
    return choose_workflow_name(config, has_seed_image=has_seed), "авто"


def seed_list_labels(config: Config, entries: list) -> List[str]:
    """Подписи эталонов: ★ у активного."""
    from .seed_pose import resolve_active_seed

    active_path, _name, enabled = resolve_active_seed(config)
    active_name = active_path.name if enabled and active_path is not None else ""
    out: List[str] = []
    for e in entries:
        label = e.label() if hasattr(e, "label") else str(e)
        path = ""
        if hasattr(e, "resolve_path"):
            p = e.resolve_path()
            path = Path(p).name if p else ""
        elif hasattr(e, "path"):
            path = Path(str(e.path)).name
        mark = "★ " if (active_name and path == active_name) else "  "
        if active_name and path == active_name:
            out.append(f"{mark}{label}  ← ВЫБРАН")
        else:
            out.append(f"{mark}{label}")
    return out
