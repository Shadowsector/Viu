"""Промпты под Cascadeur MoCap: коротко, статичная камера, nude ref, белый фон."""

from __future__ import annotations

import re

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

_CYR_PAREN_RE = re.compile(r"\([^)]*[А-Яа-яЁё][^)]*\)")
_MATCH_LOOK_RE = re.compile(
    r",?\s*matching the reference look\s*\([^)]*\)", re.IGNORECASE
)
_MATCH_FACE_RE = re.compile(
    r",?\s*matching the reference (?:look|face)(?:, body and style)?",
    re.IGNORECASE,
)
_MEDIUM_SHOT_RE = re.compile(r",?\s*medium shot\b", re.IGNORECASE)
_UPPER_BODY_RE = re.compile(r",?\s*upper body\b", re.IGNORECASE)
_CYR_TOKEN_RE = re.compile(r"[А-Яа-яЁё]+")
_MULTI_COMMA_RE = re.compile(r",\s*,+")
_DESCRIBED_POSE_RE = re.compile(
    r"(?i)\byoung woman in the described (?:pose|scene)\b,?\s*"
)


def mocap_subject_line() -> str:
    """С ReActor — человеческий силуэт (лицо из FaceRefs); иначе табакси из лора."""
    if face_swap_enabled():
        # nude один раз — в _BASE
        return "young woman"
    return SHANYA_MOCAP_VISUAL


def clean_action_for_wan(action: str) -> str:
    """Убрать RU/look-хвосты и конфликты кадра из action перед сборкой positive."""
    a = (action or "").strip()
    if not a:
        return "idle stand"
    a = _CYR_PAREN_RE.sub("", a)
    a = _MATCH_LOOK_RE.sub("", a)
    a = _MATCH_FACE_RE.sub("", a)
    a = _DESCRIBED_POSE_RE.sub("", a)
    if _CYR_TOKEN_RE.search(a):
        a = _CYR_TOKEN_RE.sub("", a)
    # full body vs medium/upper — оставляем full body (MoCap)
    if re.search(r"(?i)\bfull body\b", a) or True:
        # MoCap всегда full body — medium/upper только мешают
        a = _MEDIUM_SHOT_RE.sub("", a)
        if not re.search(r"(?i)\bselfie\b", a):
            a = _UPPER_BODY_RE.sub("", a)
    a = _MULTI_COMMA_RE.sub(", ", a)
    a = re.sub(r"\s{2,}", " ", a).strip(" ,.;")
    return a or "idle stand"


def _framing_tail(action: str) -> str:
    """Один хвост кадра — без «standing or seated», если поза уже в action."""
    spec = frame_spec_for_action(action)
    low = (action or "").lower()
    if spec.orientation == "horizontal":
        return "horizontal framing"
    # vertical
    if any(
        k in low
        for k in (
            "sit",
            "seat",
            "armchair",
            "sofa",
            "couch",
            "loung",
            "kneel",
            "squat",
        )
    ):
        return "vertical framing"
    if any(k in low for k in ("stand", "standing", "walk", "pose")):
        return "vertical framing"
    return "vertical framing"


def mocap_prompt(
    action: str,
    angle: CameraAngle | None = None,
    *,
    positive_override: str = "",
) -> str:
    if (positive_override or "").strip():
        base = positive_override.strip()
    else:
        action = clean_action_for_wan(action)
        parts = [mocap_subject_line(), _BASE, action, _framing_tail(action)]
        # уникальные куски, порядок сохранить
        seen: set[str] = set()
        uniq: list[str] = []
        for p in parts:
            key = p.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            uniq.append(p.strip())
        base = ", ".join(uniq)
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
    return clean_action_for_wan(action)


def draft_bundle(action: str) -> str:
    """Текст для Telegram: короткий промпт + кадр."""
    action_e = clean_action_for_wan(action)
    base = mocap_prompt(action_e, None)
    spec = frame_spec_for_action(action_e)
    n = mocap_take_count()
    return (
        f"Действие: {action_e}\n\n"
        f"Промпт (MoCap ref, {n} дублей ¾, разный seed):\n{base}\n\n"
        f"Кадр: {spec.summary_ru()}. Камера статична — **только поза и переход**, без лица/эмоций.\n"
        f"Внешность — FaceRefs/ReActor, не текст look в Wan.\n"
        f"Не добавляй: moaning, sweat, jiggle, pleasure — это не MoCap.\n"
        f"Negative:\n{mocap_negative()}"
    )
