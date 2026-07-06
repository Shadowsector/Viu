"""Кнопки боковой панели GUI — прямой вызов инструментов без LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class GuiAction:
    """Одна кнопка в боковой панели."""

    action_id: str
    label: str
    group: str
    tool: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    prompt: Optional[str] = None
    hint: str = ""

    @property
    def uses_agent(self) -> bool:
        return bool(self.prompt) and not self.tool


# Порядок групп на панели.
ACTION_GROUPS: List[str] = ["Unity", "Blender", "Сервис"]

GUI_ACTIONS: List[GuiAction] = [
    GuiAction(
        "unity_report",
        "Отчёт Unity",
        "Unity",
        tool="unity_report",
        hint="Editor.log + скан FBX (как check_unity)",
    ),
    GuiAction(
        "unity_deploy",
        "Deploy скрипты",
        "Unity",
        tool="unity_deploy_setup",
        hint="ShanyaSetup, AnimationSync, Locomotion",
    ),
    GuiAction(
        "unity_scan_anim",
        "Скан Animations",
        "Unity",
        tool="unity_scan_animations",
        hint="Папка Assets/Characters/Shanya/Animations",
    ),
    GuiAction(
        "unity_sync_anim",
        "Sync Animations",
        "Unity",
        tool="unity_sync_animations",
        hint="Batchmode — Unity должен быть закрыт",
    ),
    GuiAction(
        "unity_verify",
        "Проверить setup",
        "Unity",
        tool="unity_verify",
        hint="После Play или unity_run_setup",
    ),
    GuiAction(
        "unity_init",
        "Init проект",
        "Unity",
        tool="unity_init_project",
        hint="manifest + deploy + память",
    ),
    GuiAction(
        "unity_import_staging",
        "Импорт FBX → Unity",
        "Unity",
        tool="unity_import_staging",
        hint="Копирует *.fbx из U:\\Anabarra\\Animations в проект",
    ),
    GuiAction(
        "blender_info",
        "Blender: сцена",
        "Blender",
        tool="blender_info",
        hint="Что Viu видит в .blend",
    ),
    GuiAction(
        "rig_check",
        "Blender: rig",
        "Blender",
        tool="rig_check",
        hint="Сверка скелета со стандартом",
    ),
    GuiAction(
        "blender_export",
        "Экспорт Шани",
        "Blender",
        prompt="Экспортируй Shanya_Erisa.fbx через blender_export_shanya",
        hint="Нужен путь к .blend в памяти или уточни",
    ),
    GuiAction(
        "check_update",
        "Проверить обновления",
        "Сервис",
        tool="__update_check__",
        hint="Git или подсказка про zip",
    ),
    GuiAction(
        "apply_update",
        "Обновить Viu",
        "Сервис",
        tool="__update_apply__",
        hint="Git pull или zip с GitHub + pip",
    ),
    GuiAction(
        "install_deps",
        "Установить Viu (pip)",
        "Сервис",
        tool="__install_deps__",
        hint="pip install -e . — после zip или первой установки",
    ),
    GuiAction(
        "open_logs",
        "Папка логов",
        "Сервис",
        tool="__open_logs__",
    ),
    GuiAction(
        "clear_chat",
        "Очистить чат",
        "Сервис",
        tool="__clear__",
    ),
]


def actions_by_group() -> Dict[str, List[GuiAction]]:
    out: Dict[str, List[GuiAction]] = {g: [] for g in ACTION_GROUPS}
    for action in GUI_ACTIONS:
        out.setdefault(action.group, []).append(action)
    return out
