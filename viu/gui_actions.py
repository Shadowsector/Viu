"""Кнопки боковой панели GUI — прямой вызов инструментов без LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# (имя инструмента, аргументы)
ToolStep = Tuple[str, Dict[str, Any]]


@dataclass(frozen=True)
class GuiAction:
    """Одна кнопка в боковой панели."""

    action_id: str
    label: str
    group: str
    tool: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    tool_chain: Tuple[ToolStep, ...] = ()
    prompt: Optional[str] = None
    hint: str = ""

    @property
    def uses_agent(self) -> bool:
        return bool(self.prompt) and not self.tool and not self.tool_chain

    @property
    def is_chain(self) -> bool:
        return len(self.tool_chain) > 0


# Порядок групп на панели.
ACTION_GROUPS: List[str] = ["Unity", "Blender", "Вью"]

GUI_ACTIONS: List[GuiAction] = [
    # --- Unity: четыре шага человеческим языком ---
    GuiAction(
        "unity_grab",
        "Забрать с диска U",
        "Unity",
        tool_chain=(
            ("unity_import_staging", {}),
            ("unity_scan_animations", {}),
        ),
        hint="FBX из U:\\Anabarra\\Animations → в Unity. Покажу, Idle/Walk или «Ден, что это?»",
    ),
    GuiAction(
        "unity_apply",
        "Записать в Unity",
        "Unity",
        tool_chain=(
            ("unity_deploy_setup", {}),
            ("unity_sync_animations", {}),
        ),
        hint="Скрипты Вью + Animator. Перед нажатием закрой Unity.",
    ),
    GuiAction(
        "unity_diagnose",
        "Что не так с Unity?",
        "Unity",
        tool="unity_report",
        hint="Логи, FBX, Humanoid, Safe Mode — всё в чат, можно скопировать в Cursor.",
    ),
    GuiAction(
        "unity_play",
        "Play нормально?",
        "Unity",
        tool="unity_verify",
        hint="После Play или настройки — ок ли анимация и нет ли ошибок.",
    ),
    # --- Blender ---
    GuiAction(
        "blender_info",
        "Что в Blender?",
        "Blender",
        tool="blender_info",
        hint="Что Вью видит в открытой сцене.",
    ),
    GuiAction(
        "rig_check",
        "Скелет в порядке?",
        "Blender",
        tool="rig_check",
        hint="Сверка костей со стандартом для Unity.",
    ),
    GuiAction(
        "blender_export",
        "Выгрузить Шаню",
        "Blender",
        prompt="Экспортируй Shanya_Erisa.fbx через blender_export_shanya",
        hint="Через чат — нужен путь к .blend.",
    ),
    # --- Вью ---
    GuiAction(
        "update_viu",
        "Обновить Вью",
        "Вью",
        tool="__update_viu__",
        hint="Проверить → скачать, если можно → pip install. Один раз нажал и забыл.",
    ),
    GuiAction(
        "open_logs",
        "Открыть логи",
        "Вью",
        tool="__open_logs__",
    ),
    GuiAction(
        "clear_chat",
        "Очистить чат",
        "Вью",
        tool="__clear__",
    ),
]


def actions_by_group() -> Dict[str, List[GuiAction]]:
    out: Dict[str, List[GuiAction]] = {g: [] for g in ACTION_GROUPS}
    for action in GUI_ACTIONS:
        out.setdefault(action.group, []).append(action)
    return out
