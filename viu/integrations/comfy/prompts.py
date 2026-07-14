"""Промпты под Cascadeur MoCap (белый фон, фигура на весь вертикальный кадр, mp4)."""

from __future__ import annotations

from .angles import CameraAngle

_NEGATIVE = (
    "crowd, multiple people, text, watermark, logo, blur, motion blur, "
    "heavy pan, zoom, dutch angle, close-up face only, cropped limbs, "
    "busy background, colored background, scenery, room interior, "
    "UI, subtitles, low contrast, horizontal framing, wide shot empty space, "
    "tiny figure, character too small in frame"
)

_BASE = (
    "simple tanned young woman, sun-kissed skin, athletic, "
    "full body head to toe filling the vertical frame, feet visible, "
    "pure white studio background, seamless white backdrop, "
    "locked static camera, no text, no blur, clear limbs and joints, "
    "high contrast silhouette against white, loopable short motion, "
    "flat even studio lighting"
)


def mocap_prompt(action: str, angle: CameraAngle | None = None) -> str:
    action = (action or "").strip() or "idle standing, subtle breathing"
    parts = [_BASE, action]
    if angle is not None:
        parts.append(angle.prompt_en)
    return ", ".join(parts)


def mocap_negative() -> str:
    return _NEGATIVE


def draft_bundle(action: str) -> str:
    """Текст для Telegram: базовый промпт без ракурсов (ракурсы добавит Вью)."""
    base = mocap_prompt(action, None)
    return (
        f"Действие: {action.strip()}\n\n"
        f"Базовый промпт (к нему Вью добавит 3 ракурса: сбоку / ¾ / анфас):\n"
        f"{base}\n\n"
        f"Кадр: вертикальный 480×832, фигура на весь кадр, белый фон → MP4.\n\n"
        f"Negative:\n{mocap_negative()}"
    )
