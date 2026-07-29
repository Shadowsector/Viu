"""Промпты Wan/Comfy: фиксированное начало + процесс/антураж, короткий negative.

Канон Дена:
  positive = "a fit girl with a big fake breast and perfect body is …"
           + описание процесса и антуража (подставляет Вью)
  negative = "Tongue out, wet hair"
Отдельного блока «Действие» / Action в промпте нет.
"""

from __future__ import annotations

import re

from .angles import CameraAngle, mocap_take_count
from .framing import frame_spec_for_action

# Стандартное начало — не менять без Дена.
SUBJECT_PREFIX = "a fit girl with a big fake breast and perfect body is"

_NEGATIVE = "Tongue out, wet hair"

_PREFIX_RE = re.compile(
    r"(?is)^\s*a\s+fit\s+girl\s+with\s+a\s+big\s+fake\s+breast\s+and\s+perfect\s+body\s+is\s*"
)
_LEADING_IS_RE = re.compile(r"(?i)^\s*is\s+")
_CYR_TOKEN_RE = re.compile(r"[А-Яа-яЁё]+")
_MULTI_COMMA_RE = re.compile(r",\s*,+")


def mocap_subject_line() -> str:
    """Совместимость: канон — SUBJECT_PREFIX без хвостового is-хвоста."""
    return SUBJECT_PREFIX.rsplit(" is", 1)[0]


def clean_process_for_wan(process: str) -> str:
    """Описание процесса/антуража после «… body is» — без RU и без второго «is»."""
    a = (process or "").strip()
    if not a:
        return "posing in soft light"
    if _PREFIX_RE.match(a):
        a = _PREFIX_RE.sub("", a).strip()
    a = _LEADING_IS_RE.sub("", a).strip()
    a = _CYR_TOKEN_RE.sub("", a)
    a = _MULTI_COMMA_RE.sub(", ", a)
    a = re.sub(r"\s{2,}", " ", a).strip(" ,.;")
    return a or "posing in soft light"


# Старое имя — вызовы в chat_flow / gui.
def clean_action_for_wan(action: str) -> str:
    return clean_process_for_wan(action)


def process_from_positive(positive: str) -> str:
    """Вытащить хвост после канон-начала (для session.meta без UI «Действие»)."""
    raw = (positive or "").strip()
    if not raw:
        return ""
    m = _PREFIX_RE.match(raw)
    if m:
        return raw[m.end() :].strip(" ,.;")
    return raw


def build_wan_positive(
    process: str,
    angle: CameraAngle | None = None,
    *,
    positive_override: str = "",
) -> str:
    """Собрать positive: PREFIX + процесс/антураж (+ угол как антураж камеры)."""
    if (positive_override or "").strip():
        base = positive_override.strip()
        # Если правка без канон-начала — дописать.
        if not _PREFIX_RE.match(base) and not base.lower().startswith(
            "a fit girl with a big fake breast"
        ):
            base = f"{SUBJECT_PREFIX} {clean_process_for_wan(base)}"
        return base
    body = clean_process_for_wan(process)
    base = f"{SUBJECT_PREFIX} {body}"
    if angle is not None and (angle.prompt_en or "").strip():
        # Камера — часть антуража, не отдельное «Action».
        cam = angle.prompt_en.strip()
        if cam.lower() not in base.lower():
            base = f"{base}, {cam}"
    return base


def mocap_prompt(
    action: str,
    angle: CameraAngle | None = None,
    *,
    positive_override: str = "",
) -> str:
    """Positive для Wan (имя mocap_prompt — историческое)."""
    return build_wan_positive(
        action, angle, positive_override=positive_override
    )


def mocap_negative(*, negative_override: str = "") -> str:
    if (negative_override or "").strip():
        return negative_override.strip()
    return _NEGATIVE


def diversify_action(action: str, take_index: int) -> str:
    """Дубли — разный seed; процесс не раздуваем."""
    del take_index
    return clean_process_for_wan(action)


def draft_bundle(action: str) -> str:
    """Текст для Telegram/GUI: только Positive + Negative, без «Действие»."""
    process = clean_process_for_wan(action)
    base = mocap_prompt(process, None)
    spec = frame_spec_for_action(process)
    n = mocap_take_count()
    return (
        f"Промпт (Wan, {n} дублей ¾, разный seed):\n{base}\n\n"
        f"Кадр: {spec.summary_ru()}.\n"
        f"Формула: «{SUBJECT_PREFIX} …» + процесс и антураж. "
        f"Отдельного Action в промпте нет.\n"
        f"Negative:\n{mocap_negative()}"
    )
