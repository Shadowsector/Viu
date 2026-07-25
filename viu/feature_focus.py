"""Что сейчас важно, а что на паузе.

Для Дена: код не выкидываем — кнопки просто скрыты.
Показать всё снова: VIU_SHOW_PAUSED_UI=1
"""

from __future__ import annotations

import os
from typing import FrozenSet

# Группы боковой панели, которые сейчас не нужны (видео→анимации).
PAUSED_GUI_GROUPS: FrozenSet[str] = frozenset(
    {
        "Cascadeur — анимации",
        "ComfyUI — видео",
    }
)

# Отдельные кнопки вне этих групп (тоже на паузе).
PAUSED_ACTION_IDS: FrozenSet[str] = frozenset(
    {
        "interaction_blocking",  # расстановка под Comfy-сцены
        "lab_interaction",
        "unity_apply",  # загрузка клипов после Cascadeur — позже, для Idle
        "creature_lineup",  # массовая линейка зверей — не пилот Erisa
    }
)


def show_paused_ui() -> bool:
    return os.environ.get("VIU_SHOW_PAUSED_UI", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def is_action_paused(action_id: str, group: str, *, paused_flag: bool = False) -> bool:
    if show_paused_ui():
        return False
    if paused_flag:
        return True
    if group in PAUSED_GUI_GROUPS:
        return True
    return action_id in PAUSED_ACTION_IDS
