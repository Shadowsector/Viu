"""Кнопки боковой панели — минимум, по задачам Дена."""

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


ACTION_GROUPS: List[str] = [
    "Главное",
    "Редко",
]

GUI_ACTIONS: List[GuiAction] = [
    # --- То, чем пользуешься каждый день ---
    GuiAction(
        "next_step",
        "▶ Следующий шаг",
        "Главное",
        tool="__next_step__",
        hint="Inbox → разметка → экспорт. Вью сама выбирает, что делать.",
    ),
    GuiAction(
        "unity_overlay",
        "▶ Запустить оверлей",
        "Главное",
        tool="unity_overlay",
        hint="Собрать и запустить Шаню на рабочем столе. Unity закроется на время сборки.",
    ),
    GuiAction(
        "presence_toggle",
        "Я дома / меня нет",
        "Главное",
        tool="__presence_toggle__",
        hint="Дома — Вью спрашивает. Нет дома — работает сама.",
    ),
    GuiAction(
        "update_viu",
        "Обновить Вью",
        "Главное",
        tool="__update_viu__",
        hint="Скачать новую версию с GitHub.",
    ),
    GuiAction(
        "send_logs",
        "Что сломалось?",
        "Главное",
        tool="__collect_logs__",
        hint="Собрать логи и отправить разработчику.",
    ),
    # --- Редко (ручные обходы, если «Следующий шаг» не хватает) ---
    GuiAction(
        "prop_catalog",
        "Разметить предметы",
        "Редко",
        tool="__prop_catalog__",
        hint="Вес и галочки для мебели из домика.",
    ),
    GuiAction(
        "animation_catalog",
        "Очередь анимаций",
        "Редко",
        tool="__animation_review__",
        hint="Описать новые FBX-анимации.",
    ),
    GuiAction(
        "unity_apply",
        "Обновить аниматор",
        "Редко",
        tool_chain=(
            ("unity_deploy_setup", {}),
            ("unity_sync_animations", {}),
        ),
        hint="После новых Idle/Walk — пересобрать контроллер.",
    ),
    GuiAction(
        "cascadeur_batch_export",
        "Cascadeur: batch FBX",
        "Редко",
        tool="blender_export_cascadeur_batch",
        tool_args={"force": "1"},
        hint="Все .blend из Inbox → CascadeurReady (без WGT, deform bones). Blender headless.",
    ),
    GuiAction(
        "lab_cascadeur",
        "Лаборатория: Cascadeur",
        "Редко",
        tool="__lab_start__",
        hint="Один шаг lab. Прерывается кнопками экспорт/оверлей.",
    ),
    GuiAction(
        "lab_comfy",
        "Лаборатория: Comfy MoCap",
        "Редко",
        tool="__lab_comfy__",
        hint="Wan 2.1 → Telegram → 3 ракурса → выбор лучшего → kept/ + seed.",
    ),
    GuiAction(
        "comfy_clips",
        "Оценить клипы Comfy",
        "Редко",
        tool="__comfy_clips__",
        hint="Выбрать лучший из 3 ракурсов, сохранить last-frame для следующей анимации.",
    ),
    GuiAction(
        "lab_cascadeur_all",
        "Lab: весь цикл",
        "Редко",
        tool="__lab_run_all__",
        hint="Все 9 шагов до отчёта или затыка. В away — автономно по таймеру.",
    ),
    GuiAction(
        "lab_rate",
        "Оценить лабораторию",
        "Редко",
        tool="__lab_rate__",
        hint="После отчёта lab — оценки 1–5 по пяти критериям.",
    ),
    GuiAction(
        "export_unity_asset",
        "Переэкспорт сарая в Unity",
        "Редко",
        tool="export_unity_asset",
        tool_args={"force": "1"},
        hint="После Ctrl+S в Blender: FBX + Textures/ + .viu.json → Assets/Environment/.",
    ),
    GuiAction(
        "unity_overlay_rebind",
        "Починить текстуры оверлея",
        "Редко",
        tool="unity_overlay_rebind",
        hint="После переэкспорта — bake материалов. Потом «▶ Запустить оверлей».",
    ),
    GuiAction(
        "unity_open",
        "Открыть Unity",
        "Редко",
        tool="unity_open",
    ),
    GuiAction(
        "apps_close_unity",
        "Закрыть Unity",
        "Редко",
        tool="apps_close",
        tool_args={"app": "unity"},
        hint="Нужно перед сборкой оверлея, если редактор открыт.",
    ),
    GuiAction(
        "clear_chat",
        "Очистить чат",
        "Редко",
        tool="__clear__",
    ),
    GuiAction(
        "roadmap",
        "План разработки",
        "Редко",
        tool="roadmap_show",
    ),
    # --- Оставлены для тестов / чата, но в «Редко» не дублируем всё ---
    # accept_animation, prepare, export — через «Следующий шаг»
]


def actions_by_group() -> Dict[str, List[GuiAction]]:
    out: Dict[str, List[GuiAction]] = {g: [] for g in ACTION_GROUPS}
    for action in GUI_ACTIONS:
        out.setdefault(action.group, []).append(action)
    return out
