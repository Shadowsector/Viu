"""Кнопки боковой панели — секции по программам, подписи для человека без жаргона."""

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


# Порядок секций: сверху — каждый день, ниже — по программам (Blender, ComfyUI, Unity…).
ACTION_GROUPS: List[str] = [
    "Каждый день",
    "Unity — тест на столе",
    "Blender — существа",
    "Blender — сцены и домик",
    "Cascadeur — анимации",
    "Unity — анимации",
    "ComfyUI — видео",
    "Сервис",
]

GUI_ACTIONS: List[GuiAction] = [
    # --- Каждый день ---
    GuiAction(
        "next_step",
        "▶ Что делать дальше",
        "Каждый день",
        tool="__next_step__",
        hint="Вью сама выберет шаг: Inbox, разметка, экспорт, анимации…",
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
        hint="На что Вью ждёт твоего ответа.",
    ),
    # --- Unity: тестовая сцена (оверлей) ---
    GuiAction(
        "unity_overlay",
        "▶ Запустить тестовую сцену",
        "Unity — тест на столе",
        tool="unity_overlay",
        hint="Шаня на рабочем столе поверх игр. Unity закроется на время сборки.",
    ),
    GuiAction(
        "unity_overlay_rebind",
        "Починить текстуры сцены",
        "Unity — тест на столе",
        tool="unity_overlay_rebind",
        hint="Если после переэкспорта домика картинки на Шане «поплыли».",
    ),
    # --- Blender: существа (нумерованный конвейер) ---
    GuiAction(
        "creature_prep",
        "1. Очистить модель",
        "Blender — существа",
        tool="creature_prep_open",
        hint="Blender: убрать мусор, навести текстуры → prepared.blend.",
    ),
    GuiAction(
        "creature_wardrobe",
        "2. Собрать комплекты одежды",
        "Blender — существа",
        tool="creature_wardrobe_open",
        hint="Blender Wardrobe: Casual/…, кожа, волосы, гениталии.",
    ),
    GuiAction(
        "creature_studio",
        "3. Фото роста и эталон",
        "Blender — существа",
        tool="creature_studio_open",
        tool_args={"all": "0"},
        hint="Blender Studio: сравнить рост со Шаней, скрины, FBX-эталон.",
    ),
    GuiAction(
        "creature_blender_sync",
        "4. Забрать правки в каталог",
        "Blender — существа",
        tool_chain=(
            ("creature_prep_sync", {}),
            ("creature_wardrobe_sync", {}),
            ("creature_studio_sync", {}),
        ),
        hint="После Ctrl+S в Blender — подтянуть prep/одежду/студию во Вью.",
    ),
    GuiAction(
        "creature_catalog",
        "5. Размер и анатомия — окно",
        "Blender — существа",
        tool="__creature_catalog__",
        hint="Без Blender: класс роста, пол, анатомия по фото.",
    ),
    GuiAction(
        "creature_lineup",
        "6. Линейка всех сразу",
        "Blender — существа",
        tool="creature_lineup",
        tool_args={"need_photos": "1", "open": "0"},
        hint="Массово: фронт/профиль для всех. Обычно хватает шага 3 по одному.",
    ),
    # --- Blender: сцены и домик ---
    GuiAction(
        "interaction_blocking",
        "1. Расставить героев в сцене",
        "Blender — сцены и домик",
        tool="interaction_blocking",
        hint="Blender: Шаня + зверь, маркеры касания, камера студии.",
    ),
    GuiAction(
        "export_unity_asset",
        "2. Переэкспорт домика в Unity",
        "Blender — сцены и домик",
        tool="export_unity_asset",
        tool_args={"force": "1"},
        hint="После правок сарая в Blender (Ctrl+S) → FBX в Unity Assets.",
    ),
    GuiAction(
        "prop_catalog",
        "3. Разметить предметы — окно",
        "Blender — сцены и домик",
        tool="__prop_catalog__",
        hint="Мебель домика: вес, можно ли взять, куда ставить.",
    ),
    # --- Cascadeur ---
    GuiAction(
        "cascadeur_batch_export",
        "1. Выгрузить FBX пачкой",
        "Cascadeur — анимации",
        tool="blender_export_cascadeur_batch",
        tool_args={"force": "1"},
        hint="Все .blend из Inbox → папка CascadeurReady для Cascadeur.",
    ),
    GuiAction(
        "lab_cascadeur",
        "2. Lab: один тестовый шаг",
        "Cascadeur — анимации",
        tool="__lab_start__",
        hint="Автотест одного шага пайплайна Cascadeur.",
    ),
    GuiAction(
        "lab_cascadeur_all",
        "3. Lab: все 9 шагов",
        "Cascadeur — анимации",
        tool="__lab_run_all__",
        hint="Прогнать весь тестовый цикл до отчёта.",
    ),
    GuiAction(
        "lab_rate",
        "4. Оценить результат lab",
        "Cascadeur — анимации",
        tool="__lab_rate__",
        hint="Оценки 1–5 после отчёта lab.",
    ),
    # --- Unity: анимации ---
    GuiAction(
        "animation_catalog",
        "1. Описать новые FBX — окно",
        "Unity — анимации",
        tool="__animation_review__",
        hint="Список анимаций из Inbox: что это за движение, куда в каталоге.",
    ),
    GuiAction(
        "unity_apply",
        "2. Загрузить в Animator Unity",
        "Unity — анимации",
        tool_chain=(
            ("unity_deploy_setup", {}),
            ("unity_sync_animations", {}),
        ),
        hint="После Cascadeur: скопировать FBX в проект и пересобрать контроллер.",
    ),
    # --- ComfyUI ---
    GuiAction(
        "reference_catalog",
        "0. Референсы — окно",
        "ComfyUI — видео",
        tool="__reference_catalog__",
        hint="Inbox/references/ — картинки и видео; LLaVA-описание для MoCap.",
    ),
    GuiAction(
        "lab_comfy",
        "1. MoCap: снять клип",
        "ComfyUI — видео",
        tool="__lab_comfy__",
        hint="Следующий кадр из каталога → 3 ракурса → выбор лучшего mp4.",
    ),
    GuiAction(
        "interaction_master",
        "2. Черновик видео сцены",
        "ComfyUI — видео",
        tool_chain=(
            ("comfy_ensure", {}),
            ("interaction_master_draft", {}),
        ),
        hint="Comfy: master_draft.mp4. Сначала «Расставить героев в сцене».",
    ),
    GuiAction(
        "comfy_clips",
        "3. Выбрать лучший клип — окно",
        "ComfyUI — видео",
        tool="__comfy_clips__",
        hint="Сравнить и отметить удачные mp4 после съёмки.",
    ),
    GuiAction(
        "comfy_open",
        "4. Открыть Comfy в браузере",
        "ComfyUI — видео",
        tool="__comfy_open__",
        hint="Ручная отладка на http://127.0.0.1:8188.",
    ),
    GuiAction(
        "lab_interaction",
        "5. Lab: вся сцена (пилот)",
        "ComfyUI — видео",
        tool="__interaction_lab__",
        hint="Полный автотест совместной сцены shanya_wolf_approach.",
    ),
    # --- Сервис ---
    GuiAction(
        "unity_open",
        "Открыть Unity Editor",
        "Сервис",
        tool="unity_open",
        hint="Проект Anabarra в редакторе Unity.",
    ),
    GuiAction(
        "apps_close_unity",
        "Закрыть Unity",
        "Сервис",
        tool="apps_close",
        tool_args={"app": "unity"},
        hint="Перед сборкой тестовой сцены или batch-импортом.",
    ),
    GuiAction(
        "characters_vision",
        "Файл персонажей",
        "Сервис",
        tool="__characters_vision__",
        hint="Характеры, отношения — локальный markdown.",
    ),
    GuiAction(
        "send_logs",
        "Собрать логи",
        "Сервис",
        tool="__collect_logs__",
        hint="Упаковать логи для отладки / отправки разработчику.",
    ),
    GuiAction(
        "clear_chat",
        "Очистить чат",
        "Сервис",
        tool="__clear__",
    ),
    GuiAction(
        "roadmap",
        "План разработки",
        "Сервис",
        tool="roadmap_show",
        hint="Текущий фокус и дорожная карта в окне инструментов.",
    ),
    # Места — меню «Места» сверху.
    # accept_animation, prepare, export — через «Что делать дальше».
]


def actions_by_group() -> Dict[str, List[GuiAction]]:
    out: Dict[str, List[GuiAction]] = {g: [] for g in ACTION_GROUPS}
    for action in GUI_ACTIONS:
        out.setdefault(action.group, []).append(action)
    return out
