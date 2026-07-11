"""Кнопки боковой панели — по задачам, не по названию софта."""

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
    "Ещё — модели",
    "Ещё — анимации",
    "Ещё — Cascadeur",
    "Ещё — игра",
    "Ещё — Вью",
    "Ещё — план",
]

GUI_ACTIONS: List[GuiAction] = [
    GuiAction(
        "next_step",
        "▶ Следующий шаг",
        "Главное",
        tool="__next_step__",
        hint="Вью сама решает: Inbox, разметка, экспорт…",
    ),
    GuiAction(
        "presence_toggle",
        "Режим: я дома / меня нет",
        "Главное",
        tool="__presence_toggle__",
        hint="Дома — спрашивает. Нет дома — работает сама, копит осмысленные вопросы.",
    ),
    GuiAction(
        "decision_queue",
        "Очередь вопросов",
        "Главное",
        tool="__decision_queue__",
        hint="Накопленные вопросы про пайплайн и направление.",
    ),
    GuiAction(
        "send_logs",
        "Что сломалось? → разработчику",
        "Главное",
        tool="__collect_logs__",
    ),
    GuiAction(
        "telegram_test",
        "Telegram: тест связи",
        "Главное",
        tool="__telegram_test__",
    ),
    # --- Модели (Blender → Unity props) ---
    GuiAction(
        "route_inbox",
        "Разобрать Inbox (модели)",
        "Ещё — модели",
        tool="route_inbox",
        hint="Blend, prop FBX, картинки. Анимации — отдельная кнопка.",
    ),
    GuiAction(
        "prepare_unity_asset",
        "Prepare .blend (Inbox)",
        "Ещё — модели",
        tool="prepare_unity_asset",
        tool_args={"open_blender": "1"},
    ),
    GuiAction(
        "prop_catalog",
        "Разметить предметы",
        "Ещё — модели",
        tool="__prop_catalog__",
    ),
    GuiAction(
        "export_unity_asset",
        "Экспорт домика → Unity",
        "Ещё — модели",
        tool="export_unity_asset",
    ),
    GuiAction(
        "blender_info",
        "Что в Blender?",
        "Ещё — модели",
        tool="blender_info",
    ),
    GuiAction(
        "rig_check",
        "Скелет персонажа",
        "Ещё — модели",
        tool="rig_check",
    ),
    # --- Анимации ---
    GuiAction(
        "accept_animation",
        "Принять анимацию (Inbox)",
        "Ещё — анимации",
        tool="__accept_animation__",
        hint="Один Mixamo FBX → описание + scope → Unity Animations/",
    ),
    GuiAction(
        "animation_catalog",
        "Очередь анимаций",
        "Ещё — анимации",
        tool="__animation_review__",
        hint="Описать pending или править каталог.",
    ),
    GuiAction(
        "unity_apply",
        "Обновить аниматор",
        "Ещё — анимации",
        tool_chain=(
            ("unity_deploy_setup", {}),
            ("unity_sync_animations", {}),
        ),
        hint="После review — пересобрать Shanya_Idle_Stand.controller",
    ),
    # --- Cascadeur ---
    GuiAction(
        "cascadeur_status",
        "Cascadeur: статус",
        "Ещё — Cascadeur",
        tool="cascadeur_status",
        hint="Inbox Cascadeur, пути, что дальше.",
    ),
    # --- Игра (Unity playtest) ---
    GuiAction(
        "unity_overlay",
        "Оверлей: у панели задач",
        "Ещё — игра",
        tool="unity_overlay",
    ),
    GuiAction(
        "overlay_depth_far",
        "Оверлей: в глубину",
        "Ещё — игра",
        tool="unity_overlay_tune",
        tool_args={"lane": "taskbar"},
    ),
    GuiAction(
        "overlay_depth_close",
        "Оверлей: на экран",
        "Ещё — игра",
        tool="unity_overlay_tune",
        tool_args={"lane": "attention"},
    ),
    GuiAction(
        "unity_open",
        "Открыть Unity",
        "Ещё — игра",
        tool="unity_open",
    ),
    GuiAction(
        "unity_prepare",
        "Тест: Шаня стоит и ходит",
        "Ещё — игра",
        tool="unity_prepare_scene",
    ),
    GuiAction(
        "unity_diagnose",
        "Диагностика Unity",
        "Ещё — игра",
        tool="unity_report",
    ),
    GuiAction(
        "apps_status",
        "Окна: статус",
        "Ещё — игра",
        tool="apps_status",
        hint="Unity / Blender / Cascadeur — запущены ли.",
    ),
    GuiAction(
        "apps_close_unity",
        "Закрыть Unity",
        "Ещё — игра",
        tool="apps_close",
        tool_args={"app": "unity"},
    ),
    GuiAction(
        "apps_close_blender",
        "Закрыть Blender",
        "Ещё — игра",
        tool="apps_close",
        tool_args={"app": "blender"},
    ),
    GuiAction(
        "apps_close_cascadeur",
        "Закрыть Cascadeur",
        "Ещё — игра",
        tool="apps_close",
        tool_args={"app": "cascadeur"},
    ),
    GuiAction(
        "apps_close_all",
        "Закрыть все (Unity+Blender+Cascadeur)",
        "Ещё — игра",
        tool="apps_close",
        tool_args={"app": "all"},
    ),
    GuiAction(
        "apps_restart_unity",
        "Перезапустить Unity",
        "Ещё — игра",
        tool="apps_restart",
        tool_args={"app": "unity"},
    ),
    GuiAction(
        "apps_restart_blender",
        "Перезапустить Blender",
        "Ещё — игра",
        tool="apps_restart",
        tool_args={"app": "blender"},
    ),
    GuiAction(
        "apps_restart_cascadeur",
        "Перезапустить Cascadeur",
        "Ещё — игра",
        tool="apps_restart",
        tool_args={"app": "cascadeur"},
    ),
    # --- Вью ---
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
    # --- План ---
    GuiAction(
        "autopilot",
        "Автопилот (чат, долго)",
        "Ещё — план",
        prompt=(
            "Двигай Анабарру без кнопок Дена. Сначала cursor_inbox_pull — "
            "если есть pending от Cursor, выполни и cursor_inbox_complete. "
            "Иначе project_status → следующий безопасный шаг. "
            "Оверлей: один `overlay_playtest` → вердикт → handoff; при ошибке "
            "web_search + cursor_handoff, не крути по кругу. "
            "ask_user только на decision. Unity мёртв → unity_open."
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
