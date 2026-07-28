"""Инструменты доступа к долгосрочной памяти."""

from __future__ import annotations

from typing import Any, Dict

from .base import AgentContext, Tool, ToolResult


class MemoryWriteTool(Tool):
    name = "memory_write"
    description = "Сохранить важный факт/вывод в долгосрочную память"
    parameters = {"text": "что запомнить", "tags": "список тегов (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        text = args.get("text", "")
        if not text:
            return ToolResult(False, "Не указан text")
        tags = args.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        ctx.memory.add(text, tags)
        return ToolResult(True, f"Запомнено (теги: {tags or 'нет'})")


class MemorySearchTool(Tool):
    name = "memory_search"
    description = "Найти релевантные записи в долгосрочной памяти"
    parameters = {"query": "поисковый запрос", "limit": "сколько записей (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        query = args.get("query", "")
        try:
            limit = int(args.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        records = ctx.memory.search(query, limit=limit)
        if not records:
            return ToolResult(True, "Память пуста или ничего не найдено.")
        lines = [
            f"- {r.text}" + (f" [{', '.join(r.tags)}]" if r.tags else "")
            for r in records
        ]
        return ToolResult(True, "\n".join(lines))


class ChatLogsClearTool(Tool):
    name = "chat_logs_clear"
    description = (
        "Удалить сырые логи чатов и story_memory. "
        "События (event_memory), vision и канву не трогает."
    )
    parameters: Dict[str, str] = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        del args
        from ..event_memory import clear_chat_transcripts

        info = clear_chat_transcripts(ctx.config)
        removed = info.get("removed") or []
        if not removed:
            return ToolResult(True, "Нечего чистить — логов чата уже нет.")
        return ToolResult(
            True,
            "Удалила сырые логи:\n- "
            + "\n- ".join(removed)
            + "\n\nСобытия и канон на месте.",
        )


class EventMemoryShowTool(Tool):
    name = "event_memory_show"
    description = "Показать последние события приключений (не логи чата)"
    parameters = {"limit": "сколько событий (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..event_memory import get_event_memory

        try:
            limit = int(args.get("limit", 12))
        except (TypeError, ValueError):
            limit = 12
        digest = get_event_memory(ctx.config).format_digest(limit=limit)
        if not digest:
            return ToolResult(True, "Событий пока нет — сыграйте сцену в чате.")
        return ToolResult(True, digest)
