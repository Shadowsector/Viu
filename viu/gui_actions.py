"""Кнопки боковой панели — секции по программам, подписи для человека без жаргона."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .feature_focus import is_action_paused

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
    # True = на паузе (кнопка скрыта). Код инструмента остаётся.
    paused: bool = False
    pause_reason: str = ""

    @property
    def uses_agent(self) -> bool:
        return bool(self.prompt) and not self.tool and not self.tool_chain

    @property
    def is_chain(self) -> bool:
        return len(self.tool_chain) > 0

    @property
    def is_paused(self) -> bool:
        return is_action_paused(self.action_id, self.group, paused_flag=self.paused)


# Порядок секций: сверху — каждый день и тело, ниже — по программам.
ACTION_GROUPS: List[str] = [
    "Каждый день",
    "Тело Шани",
    "Девушки — риг и шоу",
    "Unity — тест на столе",
    "Blender — существа",
    "Blender — сцены и домик",
    "Cascadeur — анимации",
    "Unity — анимации",
    "ComfyUI — видео",
    "Сервис",
]

_PAUSE_COMFY = "Пауза: съёмка анимаций из видео сейчас не нужна."
_PAUSE_CASCADEUR = "Пауза: Cascadeur/lab вернём, когда займёмся Idle."
_PAUSE_INTERACT = "Пауза: совместные видео-сцены не в фокусе."


GUI_ACTIONS: List[GuiAction] = [
    # --- Каждый день ---
    GuiAction(
        "next_step",
        "▶ Что делать дальше",
        "Каждый день",
        tool="__next_step__",
        hint="Вью сама выберет шаг: Inbox, разметка, экспорт…",
    ),
    GuiAction(
        "update_viu",
        "Обновить Вью",
        "Каждый день",
        tool="__update_viu__",
        hint="Скачает новую версию с GitHub и перезапустит окно.",
    ),
    GuiAction(
        "decision_queue",
        "Очередь вопросов",
        "Каждый день",
        tool="__decision_queue__",
        hint="На что Вью ждёт твоего ответа.",
    ),
    # --- Тело Шани (фокус сейчас) ---
    GuiAction(
        "body_pipeline",
        "Тело Шани — что делать",
        "Тело Шани",
        tool="body_pipeline",
        tool_args={"action": "status"},
        hint="Простой чеклист: Inbox → Blender → Rigify → Unity. Без Comfy.",
    ),
    GuiAction(
        "body_pipeline_done",
        "Шаг тела — готово",
        "Тело Шани",
        tool="body_pipeline",
        tool_args={"action": "done"},
        hint="Отметить текущий шаг чеклиста и показать следующий.",
    ),
    GuiAction(
        "machine_bind_status",
        "Привязка к моему компу",
        "Тело Шани",
        tool="machine_bind",
        tool_args={"action": "status"},
        hint="Личная установка. После смены материнки: viu machine rebind.",
    ),
    # --- Девушки: канон-риг, NSFW, шоу SmoothMix ---
    GuiAction(
        "biped_hub",
        "❓ Как переригать / органы / шоу",
        "Девушки — риг и шоу",
        tool="__biped_canon_hub__",
        hint=(
            "Откроет окошко с простыми шагами для ламера.\n"
            "Там же все кнопки: список девок → органы → папка AccuRIG → "
            "забрать канон → шоу SmoothMix.\n"
            "Наведи на любую кнопку ниже — подсказка длинная."
        ),
    ),
    GuiAction(
        "biped_list_girls",
        "1. Список девок (biped)",
        "Девушки — риг и шоу",
        tool="creature_biped_canon",
        tool_args={"action": "list", "girls": "1"},
        hint=(
            "Покажет, кого Вью считает «девками» на двух ногах "
            "(vagina/futa или имя girl/woman/…).\n"
            "FBX✓ = можно сразу в AccuRIG.\n"
            "BLEND→FBX = сначала студия «эталон FBX», потом снова очередь.\n"
            "Все biped без фильтра девок: в чате «бипеды канон»."
        ),
    ),
    GuiAction(
        "biped_mark_genital",
        "2. Органы NSFW в каталог",
        "Девушки — риг и шоу",
        tool="creature_biped_canon",
        tool_args={"action": "mark_genital", "girls": "1"},
        hint=(
            "Только запись в каталоге (ещё не 3D):\n"
            "• девки → futa (вагина + penis)\n"
            "• genital_rig=pending — «надо прикрутить»\n"
            "• прячем scale кости ≈ 0, показ — scale вверх\n"
            "Прикрутка НЕ руками: Студия существ → панель Viu →\n"
            "«Всё NSFW сразу» (мишени + penis + вагина).\n"
            "Потом подвинь Empty/кости глазами и сохрани FBX.\n"
            "Все biped: в чате «органы biped»."
        ),
    ),
    GuiAction(
        "biped_queue_girls",
        "3. Собрать папку для AccuRIG",
        "Девушки — риг и шоу",
        tool="creature_biped_canon",
        tool_args={"action": "queue", "girls": "1"},
        hint=(
            "Скопирует модели девок в:\n"
            "Lab\\Creatures\\BipedCanonQueue\\\n"
            "Там README. Дальше — кнопка «Открыть папку AccuRIG».\n"
            "AccuRIG — отдельная бесплатная программа (Reallusion), "
            "Вью её сама не запускает.\n"
            "Экспорт из AccuRIG сохраняй как имя_canon.fbx в ту же папку."
        ),
    ),
    GuiAction(
        "biped_open_queue",
        "4. Открыть папку AccuRIG",
        "Девушки — риг и шоу",
        tool="__open_biped_queue__",
        hint=(
            "Откроет проводник на BipedCanonQueue.\n"
            "1) Поставь AccuRIG 2\n"
            "2) Открой каждый .fbx → Rig → Export Unity\n"
            "3) Сохрани рядом как slug_canon.fbx\n"
            "4) Жми «Забрать канон из AccuRIG»"
        ),
    ),
    GuiAction(
        "biped_ingest",
        "5. Забрать канон из AccuRIG",
        "Девушки — риг и шоу",
        tool="creature_biped_canon",
        tool_args={"action": "ingest"},
        hint=(
            "Ищет *_canon.fbx в папке очереди и кладёт в\n"
            "Processed\\<slug>\\<slug>_ready.fbx + пометка в каталоге.\n"
            "Потом в Unity: Rig = Humanoid → Apply.\n"
            "Хвост/jiggle — отдельные кости после тела, не Humanoid."
        ),
    ),
    GuiAction(
        "biped_sockets",
        "6. Шесть мишеней NSFW",
        "Девушки — риг и шоу",
        tool="creature_catalog_show",
        tool_args={"mode": "sockets"},
        hint=(
            "Покажет 6 точек прицеливания (не «вагинальные кости»):\n"
            "рот · вагина · анус · левая ладонь · правая · меж грудей.\n"
            "Ставятся в Blender Studio кнопкой «Поставить 6 мишеней» "
            "(или «Всё NSFW сразу»).\n"
            "Unity penetrator целится в активный Empty.\n"
            "Большой penis: пресеты S/M/L + кламп. Bulge живота — morph 0…1."
        ),
    ),
    GuiAction(
        "biped_guide",
        "Памятка текстом",
        "Девушки — риг и шоу",
        tool="creature_biped_canon",
        tool_args={"action": "guide"},
        hint="Печатает docs/BIPED_RERIG_SIMPLE.md в чат — читай по шагам.",
    ),
    GuiAction(
        "show_double",
        "Шоу-дубль SmoothMix",
        "Девушки — риг и шоу",
        tool="comfy_show",
        tool_args={"style": "realism"},
        hint=(
            "Один красивый клип (не MoCap×5 для Cascadeur).\n"
            "Если SmoothMix лежит в ComfyUI\\models\\diffusion_models\\ — "
            "подхватит; иначе cinematic на Wan.\n"
            "Дальше панель Telegram: Промпт / LoRA → «Снять».\n"
            "Поза по умолчанию — standing relaxed; другую скажи в чате "
            "«шоу дубль: …»."
        ),
    ),
    GuiAction(
        "show_double_anime",
        "Шоу-дубль аниме",
        "Девушки — риг и шоу",
        tool="comfy_show",
        tool_args={"style": "anime"},
        hint="То же шоу, стиль anime / SmoothMix anime, если модель есть.",
    ),
    # --- Unity: тестовая сцена (оверлей) ---
    GuiAction(
        "unity_overlay",
        "▶ Запустить тестовую сцену",
        "Unity — тест на столе",
        tool="unity_overlay",
        hint="Шаня на рабочем столе. Unity закроется на время сборки.",
    ),
    GuiAction(
        "unity_overlay_rebind",
        "Починить текстуры сцены",
        "Unity — тест на столе",
        tool="unity_overlay_rebind",
        hint="Если после переэкспорта домика картинки «поплыли».",
    ),
    # --- Blender: существа ---
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
        hint="Blender Wardrobe: Casual/…, кожа, волосы.",
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
        hint="После Ctrl+S в Blender — подтянуть правки во Вью.",
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
        hint="Массово для всех существ. Сейчас не нужно — только Шаня.",
        paused=True,
        pause_reason="Пилот — одно тело Шани, не линейка всех.",
    ),
    # --- Blender: сцены и домик ---
    GuiAction(
        "interaction_blocking",
        "1. Расставить героев в сцене",
        "Blender — сцены и домик",
        tool="interaction_blocking",
        hint="Под совместные видео-сцены.",
        paused=True,
        pause_reason=_PAUSE_INTERACT,
    ),
    GuiAction(
        "export_unity_asset",
        "2. Переэкспорт домика в Unity",
        "Blender — сцены и домик",
        tool="export_unity_asset",
        tool_args={"force": "1"},
        hint="После правок сарая в Blender (Ctrl+S) → FBX в Unity.",
    ),
    GuiAction(
        "prop_catalog",
        "3. Разметить предметы — окно",
        "Blender — сцены и домик",
        tool="__prop_catalog__",
        hint="Мебель домика: вес, можно ли взять, куда ставить.",
    ),
    # --- Cascadeur (пауза всей группы) ---
    GuiAction(
        "cascadeur_batch_export",
        "1. Выгрузить FBX пачкой",
        "Cascadeur — анимации",
        tool="blender_export_cascadeur_batch",
        tool_args={"force": "1"},
        hint=_PAUSE_CASCADEUR,
        paused=True,
        pause_reason=_PAUSE_CASCADEUR,
    ),
    GuiAction(
        "blender_anim_to_cascadeur",
        "1b. Клип Blender → Cascadeur",
        "Cascadeur — анимации",
        tool="blender_anim_to_cascadeur",
        hint=(
            "Простой клип в Blender (idle/wave/…) → FBX с анимацией → Inbox Cascadeur. "
            "В чате укажи blend_file и preset. Полировка — в Cascadeur."
        ),
    ),
    GuiAction(
        "lab_cascadeur",
        "2. Lab: один тестовый шаг",
        "Cascadeur — анимации",
        tool="__lab_start__",
        hint=_PAUSE_CASCADEUR,
        paused=True,
        pause_reason=_PAUSE_CASCADEUR,
    ),
    GuiAction(
        "lab_cascadeur_all",
        "3. Lab: все 9 шагов",
        "Cascadeur — анимации",
        tool="__lab_run_all__",
        hint=_PAUSE_CASCADEUR,
        paused=True,
        pause_reason=_PAUSE_CASCADEUR,
    ),
    GuiAction(
        "lab_rate",
        "4. Оценить результат lab",
        "Cascadeur — анимации",
        tool="__lab_rate__",
        hint=_PAUSE_CASCADEUR,
        paused=True,
        pause_reason=_PAUSE_CASCADEUR,
    ),
    # --- Unity: анимации ---
    GuiAction(
        "animation_catalog",
        "1. Описать новые FBX — окно",
        "Unity — анимации",
        tool="__animation_review__",
        hint="Список анимаций из Inbox (когда появятся готовые FBX).",
    ),
    GuiAction(
        "unity_apply",
        "2. Загрузить в Animator Unity",
        "Unity — анимации",
        tool_chain=(
            ("unity_deploy_setup", {}),
            ("unity_sync_animations", {}),
        ),
        hint="После Cascadeur — сейчас на паузе. Вернём для Idle.",
        paused=True,
        pause_reason=_PAUSE_CASCADEUR,
    ),
    # --- ComfyUI (пауза всей группы) ---
    GuiAction(
        "comfy_studio",
        "Студия Comfy — статус и управление",
        "ComfyUI — видео",
        tool="__comfy_studio__",
        hint=_PAUSE_COMFY,
        paused=True,
        pause_reason=_PAUSE_COMFY,
    ),
    GuiAction(
        "comfy_shot_queue",
        "0. План MoCap — очередь, промпт Wan, LoRA",
        "ComfyUI — видео",
        tool="__comfy_shot_queue__",
        hint=_PAUSE_COMFY,
        paused=True,
        pause_reason=_PAUSE_COMFY,
    ),
    GuiAction(
        "comfy_seed_library",
        "0s. Эталоны I2V (HS2 → натуральное)",
        "ComfyUI — видео",
        tool="__comfy_seed_library__",
        hint=_PAUSE_COMFY,
        paused=True,
        pause_reason=_PAUSE_COMFY,
    ),
    GuiAction(
        "reference_catalog",
        "0. Референсы — окно",
        "ComfyUI — видео",
        tool="__reference_catalog__",
        hint=_PAUSE_COMFY,
        paused=True,
        pause_reason=_PAUSE_COMFY,
    ),
    GuiAction(
        "comfy_prompt",
        "0b. Промпт Wan → Comfy",
        "ComfyUI — видео",
        tool="__comfy_prompt__",
        hint=_PAUSE_COMFY,
        paused=True,
        pause_reason=_PAUSE_COMFY,
    ),
    GuiAction(
        "lab_comfy",
        "1. MoCap: снять клип",
        "ComfyUI — видео",
        tool="__lab_comfy__",
        hint=_PAUSE_COMFY,
        paused=True,
        pause_reason=_PAUSE_COMFY,
    ),
    GuiAction(
        "interaction_master",
        "2. Черновик видео сцены",
        "ComfyUI — видео",
        tool_chain=(
            ("comfy_ensure", {}),
            ("interaction_master_draft", {}),
        ),
        hint=_PAUSE_INTERACT,
        paused=True,
        pause_reason=_PAUSE_INTERACT,
    ),
    GuiAction(
        "comfy_clips",
        "3. Выбрать лучший клип — окно",
        "ComfyUI — видео",
        tool="__comfy_clips__",
        hint=_PAUSE_COMFY,
        paused=True,
        pause_reason=_PAUSE_COMFY,
    ),
    GuiAction(
        "comfy_open",
        "4. Открыть Comfy в браузере",
        "ComfyUI — видео",
        tool="__comfy_open__",
        hint=_PAUSE_COMFY,
        paused=True,
        pause_reason=_PAUSE_COMFY,
    ),
    GuiAction(
        "lab_interaction",
        "5. Lab: вся сцена (пилот)",
        "ComfyUI — видео",
        tool="__interaction_lab__",
        hint=_PAUSE_INTERACT,
        paused=True,
        pause_reason=_PAUSE_INTERACT,
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
        hint="Перед сборкой тестовой сцены.",
    ),
    GuiAction(
        "characters_vision",
        "Файл персонажей",
        "Сервис",
        tool="__characters_vision__",
        hint="Характеры — локальный файл.",
    ),
    GuiAction(
        "send_logs",
        "Собрать логи",
        "Сервис",
        tool="__collect_logs__",
        hint="Упаковать логи для отладки.",
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
        hint="Дорожная карта в окне инструментов.",
    ),
]


def actions_by_group(*, include_paused: bool = False) -> Dict[str, List[GuiAction]]:
    out: Dict[str, List[GuiAction]] = {g: [] for g in ACTION_GROUPS}
    for action in GUI_ACTIONS:
        if not include_paused and action.is_paused:
            continue
        out.setdefault(action.group, []).append(action)
    return out
