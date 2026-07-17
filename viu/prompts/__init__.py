"""Сборка системного промпта Вью."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..memory import MemoryStore
from ..planning import Planner
from ..tools import ToolRegistry

_BASE = (Path(__file__).parent / "system.md").read_text(encoding="utf-8")


def build_system_prompt(
    config: Config,
    registry: ToolRegistry,
    memory: MemoryStore,
    planner: Planner,
) -> str:
    """Собирает полный системный промпт: база + инструменты + память + план + уроки."""
    parts = [_BASE.strip(), "\n## Доступные инструменты\n" + registry.spec()]

    recent = memory.recent(limit=5)
    if recent:
        mem_lines = "\n".join(f"- {r.text}" for r in recent)
        parts.append("\n## Недавняя память\n" + mem_lines)

    if planner.plan.steps:
        parts.append("\n## Текущий план\n" + planner.plan.render())

    learnings = config.data_dir / "learnings.md"
    if learnings.exists():
        text = learnings.read_text(encoding="utf-8").strip()
        if text:
            parts.append("\n## Усвоенные уроки\n" + text)

    return "\n".join(parts)
