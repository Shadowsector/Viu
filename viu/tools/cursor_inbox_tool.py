"""Инструменты: очередь Cursor → Viu."""

from __future__ import annotations

from typing import Any, Dict

from ..integrations.github.inbox import (
    fetch_inbox,
    format_task_prompt,
    mark_task,
    pending_tasks,
    push_inbox,
    save_inbox_local,
)
from .base import AgentContext, Tool, ToolResult


class CursorInboxPullTool(Tool):
    name = "cursor_inbox_pull"
    description = (
        "Забрать docs/VIU_INBOX.json с GitHub: список pending-задач от Cursor. "
        "Вызывай при старте work / автопилоте / когда Ден сказал «работай с Cursor»."
    )
    parameters: dict = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        ok, data = fetch_inbox()
        if not ok:
            return ToolResult(False, str(data))
        assert isinstance(data, dict)
        save_inbox_local(data)
        pending = pending_tasks(data)
        if not pending:
            return ToolResult(True, "Inbox пуст — pending-задач от Cursor нет.")
        lines = [f"Pending задач: {len(pending)}"]
        for t in pending:
            lines.append(
                f"- `{t.get('id')}` prio={t.get('priority', '?')}: {t.get('title')}"
            )
            lines.append("  → выполни по instructions, потом cursor_inbox_complete")
        lines.append("")
        lines.append("Первая задача (промпт):")
        lines.append(format_task_prompt(pending[0]))
        return ToolResult(True, "\n".join(lines))


class CursorInboxCompleteTool(Tool):
    name = "cursor_inbox_complete"
    description = (
        "Пометить задачу в VIU_INBOX как done/blocked/needs_decision и запушить на GitHub."
    )
    parameters = {
        "id": "id задачи",
        "status": "done | blocked | needs_decision",
        "result": "краткий отчёт для Cursor",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        tid = str(args.get("id") or "").strip()
        status = str(args.get("status") or "done").strip().lower()
        result = str(args.get("result") or "").strip()
        if not tid:
            return ToolResult(False, "Нужен id задачи.")
        if status not in ("done", "blocked", "needs_decision"):
            return ToolResult(False, "status: done | blocked | needs_decision")

        ok, data = fetch_inbox()
        if not ok:
            return ToolResult(False, str(data))
        assert isinstance(data, dict)
        if not mark_task(data, tid, status=status, result=result):
            return ToolResult(False, f"Задача `{tid}` не найдена в inbox.")
        push_ok, push_msg = push_inbox(
            data,
            message=f"Viu: task {tid} → {status}",
        )
        local = save_inbox_local(data)
        if push_ok:
            return ToolResult(True, f"Задача `{tid}` → {status}.\n{push_msg}\nЛокально: {local}")
        return ToolResult(
            False,
            f"Статус записала локально ({local}), на GitHub не ушло:\n{push_msg}",
        )
