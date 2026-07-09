"""Кнопки боковой панели GUI — прямой вызов инструментов без LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ToolStep = Tuple[str, Dict[str, Any]]


@dataclass(frozen=True)
class GuiAction:
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


# «Главное» — одна кнопка. Остальное — «Ещё», не обязательно.
ACTION_GROUPS: List[str] = ["Главное", "Ещё — Unity", "Ещё — Blender", "Ещё — Вью", "Ещё — план"]

GUI_ACTIONS: List[GuiAction] = [
    GuiAction(
        "next_step",
        "▶ Следующий шаг",
        "Главное",
        tool="__next_step__",
        hint="Вью сама решает: Inbox, разметка, оверлей… Тебе — одно действие или просто прочитать подсказку.",
    ),
    GuiAction(
        "send_logs",
        "Что сломалось? → разработчику",
        "Главное",
        tool="__collect_logs__",
        hint="Если ошибка — жми сюда. Лог улетит на GitHub (если есть токен) или откроется файл.",
    ),
    # --- Ещё Unity ---
    GuiAction(
        "unity_apply",
        "Обновить аниматор",
        "Ещё — Unity",
        tool_chain=(
            ("unity_deploy_setup", {}),
            ("unity_sync_animations", {}),
        ),
        hint="FBX уже в проекте — пересобрать Animator.",
    ),
    GuiAction(
        "unity_overlay",
        "Оверлей: у панели задач",
        "Ещё — Unity",
        tool="unity_overlay",
        hint="Unity закрыт. Сборка оверлея 5–15 мин.",
    ),
    GuiAction(
        "overlay_depth_far",
        "Оверлей: в глубину",
        "Ещё — Unity",
        tool="unity_overlay_tune",
        tool_args={"lane": "taskbar"},
    ),
    GuiAction(
        "overlay_depth_close",
        "Оверлей: на экран",
        "Ещё — Unity",
        tool="unity_overlay_tune",
        tool_args={"lane": "attention"},
    ),
    GuiAction(
        "unity_open",
        "Открыть Unity",
        "Ещё — Unity",
        tool="unity_open",
    ),
    GuiAction(
        "add_animation",
        "Импорт FBX анимации…",
        "Ещё — Unity",
        tool="__add_animation__",
    ),
    GuiAction(
        "unity_prepare",
        "Тест: Шаня стоит и ходит",
        "Ещё — Unity",
        tool="unity_prepare_scene",
    ),
    GuiAction(
        "unity_diagnose",
        "Диагностика Unity",
        "Ещё — Unity",
        tool="unity_report",
    ),
    # --- Ещё Blender ---
    GuiAction(
        "prepare_unity_asset",
        "Принять asset (Inbox)",
        "Ещё — Blender",
        tool="prepare_unity_asset",
        tool_args={"open_blender": "1"},
    ),
    GuiAction(
        "prop_catalog",
        "Разметить предметы",
        "Ещё — Blender",
        tool="__prop_catalog__",
    ),
    GuiAction(
        "blender_info",
        "Что в Blender?",
        "Ещё — Blender",
        tool="blender_info",
    ),
    GuiAction(
        "rig_check",
        "Скелет в порядке?",
        "Ещё — Blender",
        tool="rig_check",
    ),
    # --- Ещё Вью ---
    GuiAction(
        "update_viu",
        "Обновить Вью",
        "Ещё — Вью",
        tool="__update_viu__",
    ),
    GuiAction(
        "open_logs",
        "Открыть логи",
        "Ещё — Вью",
        tool="__open_logs__",
    ),
    GuiAction(
        "clear_chat",
        "Очистить чат",
        "Ещё — Вью",
        tool="__clear__",
    ),
    # --- Ещё план ---
    GuiAction(
        "autopilot",
        "Автопилот (чат, долго)",
        "Ещё — план",
        prompt=(
            "Двигай проект Анабарра. Начни с project_status, определи следующий шаг "
            "к текущей цели и действуй. На развилке — ask_user."
        ),
    ),
    GuiAction(
        "roadmap",
        "Показать план разработки",
        "Ещё — план",
        tool="roadmap_show",
    ),
]


def actions_by_group() -> Dict[str, List[GuiAction]]:
    out: Dict[str, List[GuiAction]] = {g: [] for g in ACTION_GROUPS}
    for action in GUI_ACTIONS:
        out.setdefault(action.group, []).append(action)
    return out
