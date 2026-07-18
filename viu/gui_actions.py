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
        "update_viu",
        "Обновить Вью",
        "Главное",
        tool="__update_viu__",
        hint="Скачать новую версию с GitHub.",
    ),
    GuiAction(
        "decision_queue",
        "Очередь вопросов",
        "Главное",
        tool="__decision_queue__",
        hint="Что Вью отложила, пока тебя не было.",
    ),
    GuiAction(
        "creature_catalog",
        "Разметить существ",
        "Главное",
        tool="__creature_catalog__",
        hint="Скан Inbox → авто по именам → кнопки размеров (гоблин/волк/…).",
    ),
    GuiAction(
        "creature_lineup",
        "Линейка существ",
        "Главное",
        tool="creature_lineup",
        tool_args={"need_photos": "1", "open": "1"},
        hint="Только без одобренных скринов. Смотри в «Разметить существ» → переснять одного.",
    ),
    GuiAction(
        "interaction_blocking",
        "Сцена: blocking",
        "Главное",
        tool="interaction_blocking",
        hint="Blender: Шаня + зверь, маркеры контакта, studio-камера. Нужны FBX в Inbox/CascadeurReady.",
    ),
    GuiAction(
        "interaction_master",
        "Сцена: master ref",
        "Главное",
        tool_chain=(
            ("comfy_ensure", {}),
            ("interaction_master_draft", {}),
        ),
        hint="Comfy: черновик видео всей сцены (2 актёра). Сначала «Сцена: blocking».",
    ),
    GuiAction(
        "characters_vision",
        "Персонажи",
        "Главное",
        tool="__characters_vision__",
        hint="Характеры и отношения — локальный файл, не на GitHub. Правишь сам.",
    ),
    GuiAction(
        "places",
        "Места (папки)",
        "Главное",
        tool="__places__",
        hint="Inbox, клипы Comfy, Animations, Vision, модели — все входы/выходы.",
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
        hint="Вью сама выбирает кадр из каталога → Telegram/авто → 3 ракурса → выбор.",
    ),
    GuiAction(
        "lab_interaction",
        "Лаборатория: совместные",
        "Редко",
        tool="__interaction_lab__",
        hint="Пилот shanya_wolf_approach: blocking → Comfy master → … (весь lab interaction).",
    ),
    GuiAction(
        "comfy_clips",
        "Оценить клипы Comfy",
        "Редко",
        tool="__comfy_clips__",
        hint="Дома окно открывается само после съёмки. Здесь — вручную / подтянуть из ComfyUI/output.",
    ),
    GuiAction(
        "comfy_open",
        "Открыть ComfyUI",
        "Редко",
        tool="__comfy_open__",
        hint="Браузер → :8188. LoRA/v2v/отладка вручную; обычный MoCap — через Вью.",
    ),
    GuiAction(
        "lab_cascadeur_all",
        "Lab: весь цикл",
        "Редко",
        tool="__lab_run_all__",
        hint="Все 9 шагов до отчёта. Нет дома — автономно по таймеру.",
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
