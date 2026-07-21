"""Кнопки боковой панели — по задачам, без стены из 16 пунктов в одной группе."""

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


# Порядок групп сверху вниз. «Каждый день» — не больше 4–5 кнопок.
ACTION_GROUPS: List[str] = [
    "Каждый день",
    "Существа",
    "Анимации",
    "Сцены",
    "Редко",
]

GUI_ACTIONS: List[GuiAction] = [
    # --- Каждый день ---
    GuiAction(
        "next_step",
        "▶ Следующий шаг",
        "Каждый день",
        tool="__next_step__",
        hint="Inbox → разметка → экспорт. Вью сама выбирает, что делать.",
    ),
    GuiAction(
        "unity_overlay",
        "▶ Запустить оверлей",
        "Каждый день",
        tool="unity_overlay",
        hint="Собрать и запустить Шаню на рабочем столе. Unity закроется на время сборки.",
    ),
    GuiAction(
        "update_viu",
        "Обновить Вью",
        "Каждый день",
        tool="__update_viu__",
        hint="Скачать новую версию с GitHub.",
    ),
    GuiAction(
        "decision_queue",
        "Очередь вопросов",
        "Каждый день",
        tool="__decision_queue__",
        hint="Что Вью отложила, пока тебя не было.",
    ),
    # --- Существа: Prep → Wardrobe → Студия (синхр. одной кнопкой) ---
    GuiAction(
        "creature_prep",
        "1. Подготовить",
        "Существа",
        tool="creature_prep_open",
        hint="Blender: очистка, текстуры → prepared.blend.",
    ),
    GuiAction(
        "creature_wardrobe",
        "2. Одежда",
        "Существа",
        tool="creature_wardrobe_open",
        hint="Blender Wardrobe: наборы Casual/…, кожа/волосы, genital.",
    ),
    GuiAction(
        "creature_studio",
        "3. Студия",
        "Существа",
        tool="creature_studio_open",
        tool_args={"all": "0"},
        hint="Blender: рост vs Шаня, скрины, эталон FBX.",
    ),
    GuiAction(
        "creature_blender_sync",
        "↻ Синхр. Blender",
        "Существа",
        tool_chain=(
            ("creature_prep_sync", {}),
            ("creature_wardrobe_sync", {}),
            ("creature_studio_sync", {}),
        ),
        hint="Забрать prep / wardrobe / studio feedback в каталог (все три, что есть).",
    ),
    GuiAction(
        "creature_catalog",
        "Разметка (окно)",
        "Существа",
        tool="__creature_catalog__",
        hint="Класс роста и анатомия без Blender — опционально.",
    ),
    GuiAction(
        "creature_lineup",
        "Линейка (массово)",
        "Редко",
        tool="creature_lineup",
        tool_args={"need_photos": "1", "open": "0"},
        hint="Headless-линейка. Обычно лучше «3. Студия» по одному.",
    ),
    # --- Анимации ---
    GuiAction(
        "animation_catalog",
        "Очередь анимаций",
        "Анимации",
        tool="__animation_review__",
        hint="Описать новые FBX после Inbox.",
    ),
    GuiAction(
        "unity_apply",
        "Обновить аниматор",
        "Анимации",
        tool_chain=(
            ("unity_deploy_setup", {}),
            ("unity_sync_animations", {}),
        ),
        hint="После новых Idle/Walk — пересобрать контроллер Unity.",
    ),
    # --- Совместные сцены ---
    GuiAction(
        "interaction_blocking",
        "Blocking",
        "Сцены",
        tool="interaction_blocking",
        hint="Blender: Шаня + зверь, маркеры контакта.",
    ),
    GuiAction(
        "interaction_master",
        "Master ref (Comfy)",
        "Сцены",
        tool_chain=(
            ("comfy_ensure", {}),
            ("interaction_master_draft", {}),
        ),
        hint="Comfy: черновик видео сцены. Сначала Blocking.",
    ),
    GuiAction(
        "lab_interaction",
        "Lab: вся сцена",
        "Редко",
        tool="__interaction_lab__",
        hint="Пилот shanya_wolf_approach — полный lab interaction.",
    ),
    # --- Редко ---
    GuiAction(
        "prop_catalog",
        "Разметить предметы",
        "Редко",
        tool="__prop_catalog__",
        hint="Вес и галочки для мебели из домика.",
    ),
    GuiAction(
        "characters_vision",
        "Персонажи",
        "Редко",
        tool="__characters_vision__",
        hint="Характеры и отношения — локальный файл.",
    ),
    GuiAction(
        "send_logs",
        "Что сломалось?",
        "Редко",
        tool="__collect_logs__",
        hint="Собрать логи и отправить разработчику.",
    ),
    GuiAction(
        "cascadeur_batch_export",
        "Cascadeur: batch FBX",
        "Редко",
        tool="blender_export_cascadeur_batch",
        tool_args={"force": "1"},
        hint="Все .blend из Inbox → CascadeurReady.",
    ),
    GuiAction(
        "lab_cascadeur",
        "Лаборатория: Cascadeur",
        "Редко",
        tool="__lab_start__",
        hint="Один шаг lab Cascadeur.",
    ),
    GuiAction(
        "lab_comfy",
        "Лаборатория: Comfy MoCap",
        "Редко",
        tool="__lab_comfy__",
        hint="Кадр из каталога → 3 ракурса → выбор клипа.",
    ),
    GuiAction(
        "comfy_clips",
        "Оценить клипы Comfy",
        "Редко",
        tool="__comfy_clips__",
        hint="Окно оценки после съёмки или вручную.",
    ),
    GuiAction(
        "comfy_open",
        "Открыть ComfyUI",
        "Редко",
        tool="__comfy_open__",
        hint="Браузер :8188 — отладка вручную.",
    ),
    GuiAction(
        "lab_cascadeur_all",
        "Lab: весь цикл",
        "Редко",
        tool="__lab_run_all__",
        hint="Все 9 шагов lab до отчёта.",
    ),
    GuiAction(
        "lab_rate",
        "Оценить лабораторию",
        "Редко",
        tool="__lab_rate__",
        hint="Оценки 1–5 после отчёта lab.",
    ),
    GuiAction(
        "export_unity_asset",
        "Переэкспорт сарая",
        "Редко",
        tool="export_unity_asset",
        tool_args={"force": "1"},
        hint="Blender Ctrl+S → FBX в Unity Assets.",
    ),
    GuiAction(
        "unity_overlay_rebind",
        "Починить текстуры оверлея",
        "Редко",
        tool="unity_overlay_rebind",
        hint="После переэкспорта сарая.",
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
        hint="Перед сборкой оверлея.",
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
    # Места — меню «Места» сверху (дубль убран из сайдбара).
    # accept_animation, prepare, export — через «Следующий шаг».
]


def actions_by_group() -> Dict[str, List[GuiAction]]:
    out: Dict[str, List[GuiAction]] = {g: [] for g in ACTION_GROUPS}
    for action in GUI_ACTIONS:
        out.setdefault(action.group, []).append(action)
    return out
