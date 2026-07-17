"""Базовые примитивы системы инструментов.

`Tool` — единица действия агента. `ToolRegistry` хранит доступные
инструменты и умеет формировать их описание для промпта. `AgentContext`
передаётся каждому инструменту и даёт доступ к конфигу, памяти и плану.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:  # избегаем циклических импортов во время выполнения
    from ..config import Config
    from ..memory import MemoryStore
    from ..planning import Planner


@dataclass
class ToolResult:
    ok: bool
    content: str

    @property
    def message(self) -> str:
        """Alias для совместимости (GUI, старый код)."""
        return self.content

    @message.setter
    def message(self, value: str) -> None:
        self.content = value

    def render(self) -> str:
        prefix = "OK" if self.ok else "ERROR"
        return f"[{prefix}] {self.content}"


@dataclass
class AgentContext:
    """Общий контекст, доступный инструментам во время выполнения."""

    config: "Config"
    memory: "MemoryStore"
    planner: "Planner"
    registry: "ToolRegistry"


class Tool(ABC):
    name: str = "tool"
    description: str = ""
    # Описание параметров в свободной форме {имя: пояснение}.
    parameters: Dict[str, str] = {}

    @abstractmethod
    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        raise NotImplementedError

    def spec(self) -> str:
        params = ", ".join(f"{k} ({v})" for k, v in self.parameters.items()) or "нет"
        return f"- {self.name}: {self.description} | параметры: {params}"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> List[Tool]:
        return list(self._tools.values())

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def spec(self) -> str:
        return "\n".join(t.spec() for t in self._tools.values())
