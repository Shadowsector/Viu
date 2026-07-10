"""Канал Вью → Cursor через docs/CURSOR_HANDOFF.md на GitHub."""

from __future__ import annotations

from typing import Any, Dict

from ..integrations.github.handoff import append_handoff, handoff_path, push_handoff
from ..integrations.github.api import diagnose_github
from ..env_file import github_token
from .base import AgentContext, Tool, ToolResult


class CursorHandoffTool(Tool):
    name = "cursor_handoff"
    description = (
        "Записать мысли/задачи для облачного Cursor в docs/CURSOR_HANDOFF.md "
        "(репозиторий Viu). Используй, когда Ден просит выложить размышления на GitHub."
    )
    parameters = {
        "title": "короткий заголовок блока",
        "body": "текст: идеи, задачи, контекст для Cursor",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        title = str(args.get("title", "Handoff")).strip()
        body = str(args.get("body", "")).strip()
        if not body:
            return ToolResult(False, "Нужен body — что записать для Cursor.")
        path = append_handoff(title, body, author="Viu")
        return ToolResult(
            True,
            f"Записала: {path}\nДальше вызови cursor_push (или cursor_handoff_with_logs с push).",
        )


class CursorPushTool(Tool):
    name = "cursor_push"
    description = (
        "Закоммитить и push docs/CURSOR_HANDOFF.md на GitHub через API "
        "(VIU_GITHUB_TOKEN; локальный git не нужен)."
    )
    parameters = {
        "message": "сообщение коммита (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        msg = str(args.get("message", "Viu: handoff для Cursor")).strip()
        ok, text = push_handoff(message=msg)
        return ToolResult(ok, text)


class CursorHandoffBundleTool(Tool):
    """Записать handoff + собрать последние логи чата в тот же блок."""

    name = "cursor_handoff_with_logs"
    description = (
        "Handoff для Cursor + последние строки chat-лога из .viu/logs. "
        "Когда Ден просит выложить размышления и логи."
    )
    parameters = {
        "title": "заголовок",
        "body": "основной текст",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        title = str(args.get("title", "Handoff + logs")).strip()
        body = str(args.get("body", "")).strip()
        if not body:
            return ToolResult(False, "Нужен body.")
        logs_dir = ctx.config.data_dir / "logs"
        tail = ""
        if logs_dir.is_dir():
            chats = sorted(
                logs_dir.glob("chat_*.txt"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if chats:
                try:
                    text = chats[0].read_text(encoding="utf-8", errors="replace")
                    tail = text[-4000:]
                except OSError:
                    pass
        full = body
        if tail:
            full += "\n\n### Последний chat-лог\n```\n" + tail + "\n```"
        path = append_handoff(title, full, author="Viu")
        ok, push_msg = push_handoff(message=f"Viu: {title[:60]}")
        if ok:
            return ToolResult(True, f"Handoff + push OK.\n{push_msg}\nЛокально: {path}")
        return ToolResult(
            False,
            f"Ден, handoff записала локально: {path}\n"
            f"На GitHub не ушло: {push_msg}\n\n"
            "Public repo — это нормально, дело не в private/public.\n"
            "Classic PAT: scopes **repo** (запись) + **gist** (запасной канал).\n"
            "Проверь U:\\Viu\\.env — VIU_GITHUB_TOKEN=ghp_... без кавычек, "
            "VIU_GITHUB_REPO=Shadowsector/Viu. Перезапусти Viu или вызови github_diagnose.",
        )


class GithubDiagnoseTool(Tool):
    name = "github_diagnose"
    description = (
        "Проверить VIU_GITHUB_TOKEN: авторизация, scopes, доступ к репо, gist. "
        "Без записи на GitHub. Используй, если cursor_push вернул 404."
    )
    parameters: dict = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        token = github_token()
        report = diagnose_github(token)
        return ToolResult(bool(token), report)
