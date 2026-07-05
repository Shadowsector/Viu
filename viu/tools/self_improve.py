"""Инструменты самоулучшения Вью.

Позволяют агенту:
* читать собственный исходный код (self_inspect);
* добавлять себе новые инструменты на лету (add_tool);
* дополнять свой системный промпт усвоенными уроками (improve_prompt).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .base import AgentContext, Tool, ToolResult

PKG_ROOT = Path(__file__).resolve().parent.parent  # каталог пакета viu/
CUSTOM_DIR = Path(__file__).resolve().parent / "custom"
LEARNINGS_FILE = "learnings.md"  # относительно data_dir


class SelfInspectTool(Tool):
    name = "self_inspect"
    description = "Прочитать собственный исходный код Вью (список файлов или конкретный файл)"
    parameters = {"path": "путь относительно пакета viu/ (пусто = список всех .py)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        rel = args.get("path", "")
        if not rel:
            files = sorted(p.relative_to(PKG_ROOT).as_posix() for p in PKG_ROOT.rglob("*.py"))
            return ToolResult(True, "\n".join(files))
        target = (PKG_ROOT / rel).resolve()
        if PKG_ROOT not in target.parents and target != PKG_ROOT:
            return ToolResult(False, "Путь вне пакета viu/")
        if not target.exists():
            return ToolResult(False, f"Файл не найден: {rel}")
        try:
            return ToolResult(True, target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            return ToolResult(False, str(exc))


class AddToolTool(Tool):
    name = "add_tool"
    description = (
        "Создать себе новый инструмент: записать Python-модуль с подклассом Tool "
        "в каталог custom/ и сразу зарегистрировать его"
    )
    parameters = {
        "filename": "имя файла, напр. my_tool.py",
        "code": "исходный код модуля с подклассом Tool",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        filename = args.get("filename", "")
        code = args.get("code", "")
        if not filename or not code:
            return ToolResult(False, "Нужны filename и code")
        if not filename.endswith(".py") or "/" in filename or filename.startswith("_"):
            return ToolResult(False, "filename должен быть простым именем *.py без '/'")

        CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
        target = CUSTOM_DIR / filename
        target.write_text(code, encoding="utf-8")

        # Горячая регистрация нового инструмента.
        try:
            from .loader import load_one

            names = load_one(ctx.registry, target)
        except Exception as exc:  # noqa: BLE001 — сообщаем об ошибке, но файл уже сохранён
            return ToolResult(
                False, f"Файл сохранён, но загрузка не удалась: {exc}"
            )
        if not names:
            return ToolResult(False, "В модуле не найдено подклассов Tool")
        return ToolResult(True, f"Добавлены и зарегистрированы инструменты: {', '.join(names)}")


class ImprovePromptTool(Tool):
    name = "improve_prompt"
    description = "Записать усвоенный урок/правило, которое будет добавляться в системный промпт"
    parameters = {"lesson": "формулировка правила или урока"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        lesson = args.get("lesson", "").strip()
        if not lesson:
            return ToolResult(False, "Не указан lesson")
        path = ctx.config.data_dir / LEARNINGS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- {lesson}\n")
        return ToolResult(True, f"Урок сохранён в {path.name}. Он будет учитываться в след. запусках.")
