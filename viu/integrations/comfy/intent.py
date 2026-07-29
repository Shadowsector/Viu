"""Триггер Comfy/Комфи в чате — отличать пайплайн от фантазии «снять»."""

from __future__ import annotations

import re
from typing import Optional

from ...config import Config

# Явный маркер пайплайна. Без него «снять» / «сними» = сцена/фантазия.
_COMFY_TRIGGER_RE = re.compile(
    r"(?i)(?:"
    r"comfy\s*ui|comfyui|\bcomfy\b|"
    r"комфи\s*юай|комфьюай|\bкомфи\b"
    r")"
)

_COMFY_JOB_RE = re.compile(
    r"(?i)(?:"
    r"сгенер|генерир|сделай\s+видео|сделай\s+фото|сними|снять|запусти|очеред|"
    r"нарисуй|рисунок|сфотка|сфотографир|"
    r"lab\b|wan\b|mocap|видео|video|клип|shoot|render|"
    r"референс|реф\b|лор[ауы]?|lora|обработай"
    r")"
)


def mentions_comfy(text: str) -> bool:
    """В тексте есть Comfy / Комфи — свойство «про пайплайн», не про камеру в фантазии."""
    return bool(_COMFY_TRIGGER_RE.search(text or ""))


def looks_like_comfy_job_request(text: str) -> bool:
    """Снять/сгенерировать/запустить именно в Comfy (нужен триггер)."""
    if not mentions_comfy(text):
        return False
    return bool(_COMFY_JOB_RE.search(text or ""))


def comfy_ui_paused() -> bool:
    """Кнопки Comfy скрыты (focus), пока не VIU_SHOW_PAUSED_UI=1."""
    try:
        from ...feature_focus import PAUSED_GUI_GROUPS, show_paused_ui

        if show_paused_ui():
            return False
        return "ComfyUI — видео" in PAUSED_GUI_GROUPS
    except Exception:  # noqa: BLE001
        return True


def format_reflect_comfy_block(config: Optional[Config] = None) -> str:
    """Блок в reflect: Комфи ≠ фантазия «снять»; не врать про «нет доступа»."""
    del config  # запас под статус :8188 позже
    lines = [
        "--- ComfyUI (триггер: Комфи / Comfy) ---",
        "Ден назвал Comfy/Комфи — это пайплайн видео/MoCap во Вью.",
        "Без слова Comfy/Комфи «снять» может быть просто сцена/фантазия — не путай.",
        "Запрещено: «нет доступа к камерам / к ComfyUI» — ты Вью на компе Дена.",
        "Reflect-чат сам jobs в очередь не ставит — оркестратор чата (рефы/LoRA/видео) уже умеет.",
        "В чате: посмотреть реф, «это ты», сделать кадр как скажешь (нарисуй / сделай фото / сними), LoRA.",
        "AFK-автосъёмка выкл — только когда Ден просит в чате.",
    ]
    if comfy_ui_paused():
        lines.append(
            "Кнопки Студии могут быть спрятаны — это не отказ. "
            "Если Ден просит в чате — не отговаривай «на паузе» как «не умею»."
        )
    else:
        lines.append("Студия Comfy / Lab тоже доступны; не обещай, что уже сняла, пока не запущено.")
    return "\n".join(lines)
