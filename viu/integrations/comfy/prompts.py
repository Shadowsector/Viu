"""Промпты под Cascadeur MoCap: коротко, статичная камера, nude ref, белый фон."""

from __future__ import annotations

from .angles import CameraAngle, mocap_take_count
from .face_refs import face_swap_enabled
from .framing import frame_spec_for_action
from ...lore.shanya import SHANYA_MOCAP_VISUAL

# Короткий negative — Wan и так не любит длинные списки.
_NEGATIVE = (
    "multiple people, text, watermark, blur, camera motion, zoom, "
    "cropped limbs, busy background, clothed, tiny figure, "
    "moaning, sweat, jiggle, facial expression, emotional face, "
    "pleasure, erotic acting, cinematic drama"
)

# База MoCap: не лицо/эмоции, а поза и силуэт для трекинга.
_BASE = (
    "full body head to toe, nude, white background, static locked camera, "
    "even lighting, clear limbs, mocap reference"
)


def mocap_subject_line() -> str:
    """С ReActor — человеческий силуэт (лицо из FaceRefs); иначе табакси из лора."""
    if face_swap_enabled():
        return "nude young woman"
    return SHANYA_MOCAP_VISUAL


def mocap_prompt(
    action: str,
    angle: CameraAngle | None = None,
    *,
    positive_override: str = "",
) -> str:
    if (positive_override or "").strip():
        base = positive_override.strip()
    else:
        action = (action or "").strip() or "idle stand"
        parts = [mocap_subject_line(), _BASE, action]
        spec = frame_spec_for_action(action)
        if spec.orientation == "horizontal":
            parts.append("horizontal framing, lying full body")
        else:
            parts.append("vertical framing, standing or seated full body")
        base = ", ".join(parts)
    if angle is not None:
        return f"{base}, {angle.prompt_en}"
    return base


def mocap_negative(*, negative_override: str = "") -> str:
    if (negative_override or "").strip():
        return negative_override.strip()
    return _NEGATIVE


def diversify_action(action: str, take_index: int) -> str:
    """Три дубля — разный seed; промпт не раздуваем."""
    del take_index
    return (action or "").strip() or "idle stand"


def draft_bundle(action: str) -> str:
    """Текст для Telegram: короткий промпт + кадр."""
    action_e = (action or "").strip() or "idle stand"
    base = mocap_prompt(action_e, None)
    spec = frame_spec_for_action(action_e)
    n = mocap_take_count()
    return (
        f"Действие: {action_e}\n\n"
        f"Промпт (MoCap ref, {n} дублей ¾, разный seed):\n{base}\n\n"
        f"Кадр: {spec.summary_ru()}. Камера статична — **только поза и переход**, без лица/эмоций/звука.\n"
        f"Не добавляй: moaning, sweat, jiggle, pleasure — это не MoCap.\n"
        f"Negative:\n{mocap_negative()}"
    )
