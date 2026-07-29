"""Профиль «шоу-дубль»: красивый клип (SmoothMix / cinematic), не MoCap-ref.

MoCap остаётся дефолтом (белый фон, ¾, Cascadeur).
Шоу — отдельный render_profile=show: другой кадр, steps/sampler, промпт со стилем.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from ...config import Config
from .angles import CameraAngle
from .paths import resolve_comfy_root

PROFILE_MOCAP = "mocap"
PROFILE_SHOW = "show"

# ~900×600 из шоукейса SmoothMix, кратно 16 для Wan.
SHOW_WIDTH = 896
SHOW_HEIGHT = 576
SHOW_LENGTH = 49  # ~2 с @ 24fps
SHOW_FPS = 24.0
SHOW_STEPS = 8
SHOW_CFG = 4.0
SHOW_SAMPLER = "euler"
SHOW_SCHEDULER = "simple"

SHOW_TAKE = CameraAngle(
    "show_a",
    "шоу A",
    "cinematic three-quarter view, full body in frame",
)

_SHOW_UNET_ENV = "VIU_COMFY_SHOW_UNET"
_SMOOTH_NAME_RE = re.compile(r"smoothmix|smooth.?mix|wan.?2\.?2.?smooth", re.I)


def normalize_profile(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key in (
        "show",
        "шоу",
        "smooth",
        "smoothmix",
        "beauty",
        "pretty",
        "cinema",
        "кино",
    ):
        return PROFILE_SHOW
    return PROFILE_MOCAP


def is_show_profile(meta: dict | None) -> bool:
    if not isinstance(meta, dict):
        return False
    return normalize_profile(str(meta.get("render_profile") or "")) == PROFILE_SHOW


def show_style_from_meta(meta: dict | None) -> str:
    raw = ""
    if isinstance(meta, dict):
        raw = str(meta.get("show_style") or "").strip().lower()
    if raw in ("anime", "аниме"):
        return "anime"
    return "realism"


def find_show_unet(config: Config) -> Tuple[Optional[str], str]:
    """Имя файла в models/diffusion_models для шоу (SmoothMix и т.п.)."""
    forced = (os.environ.get(_SHOW_UNET_ENV) or "").strip()
    if forced:
        return forced, f"из {_SHOW_UNET_ENV}"
    root = resolve_comfy_root(config)
    if root is None:
        return None, "ComfyUI root не найден"
    folder = root / "models" / "diffusion_models"
    if not folder.is_dir():
        return None, f"нет папки {folder}"
    hits: List[Path] = []
    try:
        for p in folder.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".safetensors", ".gguf", ".pt"):
                continue
            if _SMOOTH_NAME_RE.search(p.name):
                hits.append(p)
    except OSError as exc:
        return None, str(exc)
    if not hits:
        return None, (
            "SmoothMix не найден в models/diffusion_models/. "
            f"Положи .safetensors/.gguf туда или задай {_SHOW_UNET_ENV}=имя_файла. "
            "Пока шоу идёт на обычном Wan 2.1 с cinematic-промптом."
        )
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0].name, f"найдено: {hits[0].name}"


def show_angles() -> List[CameraAngle]:
    return [SHOW_TAKE]


def show_take_count() -> int:
    return 1


def show_positive(
    action: str,
    *,
    style: str = "realism",
    has_smoothmix: bool = False,
) -> str:
    """Красивый positive — не white-bg MoCap."""
    pose = (action or "").strip() or "young woman standing relaxed, full body"
    # не тащить mocap-boilerplate если action уже из chat
    pose = re.sub(
        r"(?i),?\s*matching the reference look\s*\([^)]*\)",
        "",
        pose,
    )
    pose = re.sub(r"[А-Яа-яЁё]+", "", pose)
    pose = re.sub(r",\s*,+", ", ", pose).strip(" ,")
    if style == "anime":
        style_bits = "anime style, stylized, vibrant colors"
        if has_smoothmix:
            style_bits = f"smoothmixanime, {style_bits}"
    else:
        style_bits = "realistic style, detailed skin, soft cinematic lighting"
        if has_smoothmix:
            # v3: smoothmixrealism сильный — дополняем Realistic Style
            style_bits = f"smoothmixrealism, {style_bits}"
    parts = [
        "young woman",
        pose,
        style_bits,
        "cinematic composition, shallow depth of field, high detail",
        "three-quarter view, full body in frame",
    ]
    # unique preserve order
    seen: set[str] = set()
    out: List[str] = []
    for p in parts:
        k = p.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(p.strip())
    return ", ".join(out)


def show_negative(*, style: str = "realism") -> str:
    base = (
        "low quality, blurry, watermark, text, logo, "
        "extra limbs, deformed hands, cropped head, "
        "static frame, slideshow, worst quality"
    )
    if style == "anime":
        return base + ", photorealistic, uncanny"
    return base + ", flat anime cel shading, plastic doll"


def draft_show_bundle(
    action: str,
    *,
    style: str = "realism",
    unet_note: str = "",
    has_smoothmix: bool = False,
) -> str:
    pos = show_positive(action, style=style, has_smoothmix=has_smoothmix)
    neg = show_negative(style=style)
    model_line = unet_note or "Wan 2.1 (SmoothMix не найден — cinematic fallback)"
    return (
        f"Профиль: ШОУ-ДУБЛЬ ({style})\n"
        f"Модель: {model_line}\n"
        f"Кадр: {SHOW_WIDTH}×{SHOW_HEIGHT}, {SHOW_LENGTH} кадров, "
        f"steps={SHOW_STEPS} {SHOW_SAMPLER}/{SHOW_SCHEDULER} cfg={SHOW_CFG}\n"
        f"Дублей: {show_take_count()} (не MoCap×5)\n\n"
        f"Действие: {action}\n\n"
        f"Промпт (шоу):\n{pos}\n\n"
        f"Negative:\n{neg}\n\n"
        "Это не ref для Cascadeur — красивый клип. "
        "MoCap снова: «mocap» / без слова шоу."
    )


def arm_show_profile(
    session_meta: dict,
    *,
    style: str = "realism",
    action: str = "",
) -> dict:
    """Пометить session.meta под шоу-съёмку."""
    session_meta["render_profile"] = PROFILE_SHOW
    session_meta["show_style"] = "anime" if style == "anime" else "realism"
    session_meta["shoot_intent"] = True
    session_meta["catalog_slug"] = session_meta.get("catalog_slug") or "chat_scene"
    session_meta["shot_reason"] = session_meta.get("shot_reason") or "chat: show double"
    if action.strip():
        session_meta["action"] = action.strip()
        session_meta["approved_action"] = action.strip()
    # не тащить stale mocap wan_positive
    session_meta.pop("wan_positive", None)
    session_meta.pop("wan_negative", None)
    return session_meta


def clear_show_profile(session_meta: dict) -> dict:
    session_meta["render_profile"] = PROFILE_MOCAP
    session_meta.pop("show_style", None)
    return session_meta


def status_line(config: Config, meta: dict | None = None) -> str:
    unet, note = find_show_unet(config)
    if is_show_profile(meta):
        style = show_style_from_meta(meta)
        return f"профиль: ШОУ ({style}) · {note}"
    if unet:
        return f"шоу готово (модель {unet}); включи: «шоу дубль» / comfy_show"
    return f"шоу: модель не стоит — {note}"
