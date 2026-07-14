"""Промпты под Cascadeur MoCap (чистый силуэт, одна камера, short clip)."""

from __future__ import annotations

from .angles import CameraAngle

_NEGATIVE = (
    "crowd, multiple people, text, watermark, logo, blur, motion blur, "
    "heavy pan, zoom, dutch angle, close-up face only, cropped limbs, "
    "busy background, UI, subtitles, low contrast"
)

_BASE = (
    "full body, single female character, plain solid background, "
    "stable locked camera, no text, no blur, clear limbs and joints, "
    "high contrast silhouette, loopable short motion, "
    "cinematic but simple lighting"
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
        f"Negative:\n{mocap_negative()}"
    )
