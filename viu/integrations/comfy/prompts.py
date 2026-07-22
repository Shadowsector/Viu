"""Промпты под Cascadeur MoCap (фронтальный свет, белый фон, фигура на весь кадр)."""

from __future__ import annotations

from .angles import CameraAngle
from .framing import enrich_idle_action, frame_spec_for_action
from ...lore.shanya import SHANYA_MOCAP_VISUAL

_NEGATIVE = (
    "crowd, multiple people, text, watermark, logo, blur, motion blur, "
    "heavy pan, zoom, dutch angle, close-up face only, cropped limbs, "
    "busy background, colored background, scenery, room interior, "
    "UI, subtitles, low contrast, tiny figure, character too small in frame, "
    "backlit silhouette, rim light only, dark face, underexposed subject, "
    "harsh backlight, pure black silhouette"
)

_BASE = (
    f"{SHANYA_MOCAP_VISUAL}, "
    "pure white studio background, seamless white backdrop, no scenery, "
    "soft frontal key light, fill light from front, even face lighting, "
    "subject clearly lit from camera side, no backlight silhouette, "
    "locked static tripod camera, no text, no blur, clear limbs and joints, "
    "high contrast against white, motion capture reference video, "
    "all body joints readable for mocap software, no motion blur"
)

# Вариации дублей — чтобы A/B/C не были копиями
_TAKE_FLAVOR = (
    "calm natural pacing, soft micro-movements",
    "slightly snappier timing, clearer weight shifts, more decisive limb arcs",
    "slower softer motion, gentler breath, smaller gestures, relaxed energy",
)


def take_flavor(take_index: int) -> str:
    return _TAKE_FLAVOR[take_index % len(_TAKE_FLAVOR)]


def diversify_action(action: str, take_index: int) -> str:
    """Базовое действие + вкус дубля (не копипаста трёх одинаковых клипов)."""
    base = enrich_idle_action((action or "").strip())
    flavor = take_flavor(take_index)
    # не дублировать, если уже есть
    if flavor.split(",")[0] in base:
        return base
    return f"{base}, {flavor}"


def mocap_prompt(action: str, angle: CameraAngle | None = None) -> str:
    action = enrich_idle_action(action)
    parts = [_BASE, action]
    spec = frame_spec_for_action(action)
    if spec.orientation == "vertical":
        parts.append("vertical portrait framing, figure fills the tall frame")
    else:
        parts.append("horizontal landscape framing, figure lying fills the wide frame")
    if angle is not None:
        parts.append(angle.prompt_en)
    return ", ".join(parts)


def mocap_negative() -> str:
    return _NEGATIVE


def draft_bundle(action: str) -> str:
    """Текст для Telegram: базовый промпт + объяснение длины/кадра."""
    action_e = enrich_idle_action(action)
    base = mocap_prompt(action_e, None)
    spec = frame_spec_for_action(action_e)
    return (
        f"Действие: {action_e}\n\n"
        f"Базовый промпт (Вью снимет 3 дубля в ракурсе ¾ с разным timing/seed):\n"
        f"{base}\n\n"
        f"Кадр: {spec.summary_ru()}. Ракурс: только три четверти.\n"
        f"Длина: Wan = кадры 4n+1, FPS={spec.fps:.0f}; "
        f"idle длиннее (~3.4 с), жест ~2 с; переход ~2.7 с. Выход — MP4 h264.\n\n"
        f"Negative:\n{mocap_negative()}"
    )
