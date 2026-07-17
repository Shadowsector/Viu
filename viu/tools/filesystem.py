"""Файловые инструменты (в песочнице рабочего каталога)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .base import AgentContext, Tool, ToolResult


def _resolve_in_root(root: Path, rel: str) -> Path:
    """Разрешает путь и запрещает выход за пределы песочницы."""
    candidate = (root / rel).resolve()
    root = root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Путь вне песочницы: {rel}")
    return candidate


class ReadFileTool(Tool):
    name = "read_file"
    description = "Прочитать содержимое текстового файла"
    parameters = {"path": "относительный путь к файлу"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        path = args.get("path", "")
        if not path:
            return ToolResult(False, "Не указан path")
        try:
            target = _resolve_in_root(ctx.config.root, path)
            if not target.exists():
                return ToolResult(False, f"Файл не найден: {path}")
            text = target.read_text(encoding="utf-8")
            return ToolResult(True, text)
        except (ValueError, OSError, UnicodeDecodeError) as exc:
            return ToolResult(False, str(exc))


class WriteFileTool(Tool):
    name = "write_file"
    description = "Создать или перезаписать текстовый файл"
    parameters = {"path": "относительный путь", "content": "содержимое файла"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        path = args.get("path", "")
        content = args.get("content", "")
        if not path:
            return ToolResult(False, "Не указан path")
        try:
            target = _resolve_in_root(ctx.config.root, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolResult(True, f"Записано {len(content)} символов в {path}")
        except (ValueError, OSError) as exc:
            return ToolResult(False, str(exc))


class ListDirTool(Tool):
    name = "list_dir"
    description = "Показать содержимое каталога"
    parameters = {"path": "относительный путь (по умолчанию корень)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        path = args.get("path", ".")
        try:
            target = _resolve_in_root(ctx.config.root, path)
            if not target.exists():
                return ToolResult(False, f"Каталог не найден: {path}")
            if not target.is_dir():
                return ToolResult(False, f"Это не каталог: {path}")
            entries = []
            for p in sorted(target.iterdir()):
                mark = "/" if p.is_dir() else ""
                entries.append(p.name + mark)
            return ToolResult(True, "\n".join(entries) if entries else "(пусто)")
        except (ValueError, OSError) as exc:
            return ToolResult(False, str(exc))
