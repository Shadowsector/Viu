"""Инструмент уточнения у пользователя — останавливает цикл агента."""

from __future__ import annotations

from typing import Any, Dict

from .base import AgentContext, Tool, ToolResult


class AskUserTool(Tool):
    name = "ask_user"
    description = (
        "Задать Дену осмысленный вопрос (выбор направления, пайплайн, вкус). "
        "Если Ден «дома» — остановиться и ждать. Если «меня нет» — вопрос уйдёт "
        "в очередь решений, а ты продолжишь без него, когда можно. "
        "Не используй для «нажми кнопку / пришли лог»."
    )
    parameters = {
        "question": "вопрос",
        "kind": "pipeline | vision | design | scope | story | decision",
        "context": "зачем спрашиваешь (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        q = str(args.get("question", "")).strip()
        if not q:
            return ToolResult(False, "Не указан question")
        kind = str(args.get("kind") or "decision").strip()
        context = str(args.get("context") or "").strip()

        from ..presence import is_away
        from ..decision_queue import enqueue, is_meaningful

        if is_away(ctx.config):
            if not is_meaningful(q, kind=kind):
                return ToolResult(
                    True,
                    "Ден не у ПК; вопрос операционный — не коплю. "
                    "Реши сама или пропусти. " + q,
                )
            ok, msg = enqueue(ctx.config, q, kind=kind, context=context)
            # Специальный префикс — agent не ставит waiting_for_user.
            return ToolResult(
                True,
                "QUEUED_FOR_DEN: " + (msg if ok else msg),
            )

        return ToolResult(True, q)
