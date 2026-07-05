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
        lines = [f"- {r.text}" + (f" [{', '.join(r.tags)}]" if r.tags else "") for r in records]
        return ToolResult(True, "\n".join(lines))
