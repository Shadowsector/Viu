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
        "Показать план разработки",
        "Игра",
        tool="roadmap_show",
        hint="Только просмотр: этапы Анабарры и что сейчас в фокусе. "
        "Менять план — через «Что делаем дальше?» или в чате.",
    ),
    # --- Unity: по шагам, человеческим языком ---
    GuiAction(
        "add_animation",
        "Импорт FBX анимации…",
        "Unity",
        tool="__add_animation__",
        hint="Новый FBX лежит на диске (Mixamo и т.п.) — Вью скопирует в проект и "
        "сразу пересоберёт Animator. Если FBX уже в папке Animations/ — "
        "кнопка «Обновить аниматор».",
    ),
    GuiAction(
        "unity_apply",
        "Обновить аниматор",
        "Unity",
        tool_chain=(
            ("unity_deploy_setup", {}),
            ("unity_sync_animations", {}),
        ),
        hint="Перечитать FBX, которые уже лежат в Assets/Characters/Shanya/Animations/, "
        "и обновить Animator Controller. С диска ничего не копирует.",
    ),
    GuiAction(
        "unity_prepare",
        "Тест: Шаня стоит и ходит",
        "Unity",
        tool="unity_prepare_scene",
        hint="Вид сбоку (Terraria), полный кадр мира на экран, рост ~1.75 м, A/D. "
        "Обнови Viu перед запуском — скрипты Setup и Camera должны совпадать.",
    ),
    GuiAction(
        "unity_overlay",
        "Оверлей: у панели задач",
        "Unity",
        tool="unity_overlay",
        hint="Собрать Windows-оверлей (Unity закрыт, 5–15 мин). Esc — закрыть. "
        "Сначала «Обновить аниматор».",
    ),
    GuiAction(
        "overlay_depth_far",
        "Оверлей: в глубину",
        "Unity",
        tool="unity_overlay_tune",
        tool_args={"lane": "taskbar"},
        hint="Без пересборки: Шаня дальше, мелко. W/S в оверлее точнее. Перезапусти exe.",
    ),
    GuiAction(
        "overlay_depth_close",
        "Оверлей: на экран",
        "Unity",
        tool="unity_overlay_tune",
        tool_args={"lane": "attention"},
        hint="Без пересборки: Шаня ближе, крупнее (~пол-экрана). W/S + F5 сохранить.",
    ),
    GuiAction(
        "unity_open",
        "Открыть Unity",
        "Unity",
        tool="unity_open",
        hint="Просто запустить редактор. Ничего не собирает и не импортирует.",
    ),
    GuiAction(
        "unity_diagnose",
        "Диагностика проекта",
        "Unity",
        tool="unity_report",
        hint="Посмотреть состояние: логи, FBX, Humanoid, ошибки компиляции. "
        "Проект не меняет — только отчёт, можно скопировать и прислать мне.",
    ),
    GuiAction(
        "unity_play",
        "После ▶ Play: всё ок?",
        "Unity",
        tool="unity_verify",
        hint="Ты уже нажал Play в Unity? Проверю логи: вошла ли игра в Play Mode, "
        "нет ли ошибок анимации и компиляции.",
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
