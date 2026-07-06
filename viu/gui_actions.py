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
ACTION_GROUPS: List[str] = ["Игра", "Unity", "Blender", "Вью"]

GUI_ACTIONS: List[GuiAction] = [
    # --- Игра: автопилот ---
    GuiAction(
        "autopilot",
        "Что делаем дальше?",
        "Игра",
        prompt=(
            "Двигай проект Анабарра. Начни с project_status, определи следующий шаг "
            "к текущей цели и действуй: безопасные шаги выполняй сам (импорт, скан, "
            "deploy, sync, отчёт), а на развилке или где нужны мои руки в Unity — "
            "спроси через ask_user. Продвинул веху — обнови roadmap_update. "
            "В конце дай короткий итог по-человечески."
        ),
        hint="Вью сама смотрит состояние игры и делает следующий шаг. Спросит, если нужно решение.",
    ),
    GuiAction(
        "roadmap",
        "План игры",
        "Игра",
        tool="roadmap_show",
        hint="Дорожная карта Анабарры и что сейчас в фокусе.",
    ),
    # --- Unity: по шагам, человеческим языком ---
    GuiAction(
        "add_animation",
        "Добавить анимацию…",
        "Unity",
        tool="__add_animation__",
        hint="Выбери FBX с анимацией (например, скачанный с Mixamo) — Вью положит его "
        "в проект и соберёт Animator.",
    ),
    GuiAction(
        "unity_apply",
        "Собрать анимации в Unity",
        "Unity",
        tool_chain=(
            ("unity_deploy_setup", {}),
            ("unity_sync_animations", {}),
        ),
        hint="Обновить скрипты Вью и пересобрать Animator из всех клипов. Unity лучше закрыть.",
    ),
    GuiAction(
        "unity_open",
        "Открыть Unity",
        "Unity",
        tool="unity_open",
        hint="Запустить редактор Unity с проектом Анабарра — чтобы настроить сцену и нажать Play.",
    ),
    GuiAction(
        "unity_diagnose",
        "Проверить Unity",
        "Unity",
        tool="unity_report",
        hint="Собрать отчёт: логи, FBX, Humanoid, ошибки. Можно скопировать и прислать мне.",
    ),
    GuiAction(
        "unity_play",
        "Проверить после Play",
        "Unity",
        tool="unity_verify",
        hint="Нажал Play в Unity? Эта кнопка скажет, всё ли в порядке с анимацией.",
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
        "send_logs",
        "Отправить логи разработчику",
        "Вью",
        tool="__collect_logs__",
        hint="Соберу логи в один файл. С токеном — сама залью на GitHub, иначе покажу файл.",
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
