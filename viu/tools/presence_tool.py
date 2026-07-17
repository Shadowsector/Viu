"""Режим присутствия, очередь решений, закрытие приложений."""

from __future__ import annotations

from typing import Any, Dict, List

from ..decision_queue import answer, dismiss, enqueue, render_open
from ..integrations.apps.process import kill_app, kill_apps, restart_app, status_apps
from ..presence import (
    MODE_AWAY,
    MODE_HOME,
    get_presence,
    is_away,
    presence_label,
    set_presence,
)
from .base import AgentContext, Tool, ToolResult


class PresenceSetTool(Tool):
    name = "presence_set"
    description = (
        "Режим Дена: home = я за компом, можно спрашивать; "
        "away = меня нет, работай автономно и копи осмысленные вопросы."
    )
    parameters = {"mode": "home | away"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        mode = str(args.get("mode") or "").strip().lower()
        if mode not in (MODE_HOME, MODE_AWAY):
            return ToolResult(False, "mode: home | away")
        set_presence(ctx.config, mode)
        extra = ""
        if mode == MODE_HOME:
            from ..decision_queue import flush_prompt_for_home

            flush = flush_prompt_for_home(ctx.config)
            if flush:
                extra = "\n\n" + flush
        return ToolResult(True, presence_label(ctx.config) + extra)


class PresenceStatusTool(Tool):
    name = "presence_status"
    description = "Текущий режим: дома / нет дома + сколько вопросов в очереди."
    parameters: dict = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..decision_queue import count_open

        n = count_open(ctx.config)
        return ToolResult(
            True,
            f"{presence_label(ctx.config)}\n"
            f"mode={get_presence(ctx.config)}\n"
            f"Очередь вопросов: {n}",
        )


class DecisionQueueShowTool(Tool):
    name = "decision_queue_show"
    description = "Показать накопленные осмысленные вопросы к Дену."
    parameters: dict = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        return ToolResult(True, render_open(ctx.config))


class DecisionQueueAddTool(Tool):
    name = "decision_queue_add"
    description = (
        "Положить осмысленный вопрос в очередь (вектор пайплайна, выбор направления). "
        "Мелочь и «нажми кнопку» — не клади."
    )
    parameters = {
        "question": "вопрос",
        "kind": "pipeline | vision | design | scope | story | decision",
        "context": "краткий контекст (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        ok, msg = enqueue(
            ctx.config,
            str(args.get("question") or ""),
            kind=str(args.get("kind") or "decision"),
            context=str(args.get("context") or ""),
        )
        return ToolResult(ok, msg)


class DecisionQueueAnswerTool(Tool):
    name = "decision_queue_answer"
    description = "Записать ответ Дена на вопрос из очереди (по id)."
    parameters = {"id": "id вопроса", "answer": "ответ Дена"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        ok, msg = answer(
            ctx.config,
            str(args.get("id") or "").strip(),
            str(args.get("answer") or ""),
        )
        return ToolResult(ok, msg)


class DecisionQueueDismissTool(Tool):
    name = "decision_queue_dismiss"
    description = "Снять вопрос с очереди без ответа."
    parameters = {"id": "id вопроса"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        ok, msg = dismiss(ctx.config, str(args.get("id") or "").strip())
        return ToolResult(ok, msg)


class AppsStatusTool(Tool):
    name = "apps_status"
    description = "Статус окон Unity / Blender / Cascadeur (запущены ли)."
    parameters: dict = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        return ToolResult(True, status_apps(ctx.config))


class AppsCloseTool(Tool):
    name = "apps_close"
    description = (
        "Закрыть окна приложений. app=unity|blender|cascadeur|all. "
        "Нужно перед batch Unity / когда зависли."
    )
    parameters = {"app": "unity | blender | cascadeur | all"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        raw = str(args.get("app") or "unity").strip().lower()
        if raw == "all":
            ok, msg = kill_apps(["unity", "blender", "cascadeur"])
        else:
            ok, msg = kill_app(raw)
        return ToolResult(ok, msg)


class AppsRestartTool(Tool):
    name = "apps_restart"
    description = "Закрыть и снова открыть Unity / Blender / Cascadeur."
    parameters = {"app": "unity | blender | cascadeur"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        app = str(args.get("app") or "").strip().lower()
        if app not in ("unity", "blender", "cascadeur"):
            return ToolResult(False, "app: unity | blender | cascadeur")
        ok, msg = restart_app(app, ctx.config)
        return ToolResult(ok, msg)
