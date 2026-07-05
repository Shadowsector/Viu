"""Система инструментов Вью."""

from .base import AgentContext, Tool, ToolRegistry, ToolResult
from .blender_tool import BlenderCommandTool, BlenderInfoTool, BlenderScreenshotTool
from .filesystem import ListDirTool, ReadFileTool, WriteFileTool
from .loader import load_custom_tools
from .memory_tool import MemorySearchTool, MemoryWriteTool
from .planning_tool import PlanCreateTool, PlanShowTool, PlanUpdateTool
from .rig_tool import RigApplyTool, RigCheckTool, RigStandardTool
from .self_improve import AddToolTool, ImprovePromptTool, SelfInspectTool
from .shell import ShellTool
from .web import WebFetchTool, WebSearchTool

__all__ = [
    "AgentContext",
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "build_default_registry",
    "load_custom_tools",
]


def build_default_registry() -> ToolRegistry:
    """Создаёт реестр со всеми встроенными инструментами + пользовательскими."""
    registry = ToolRegistry()
    for tool in (
        ReadFileTool(),
        WriteFileTool(),
        ListDirTool(),
        ShellTool(),
        WebSearchTool(),
        WebFetchTool(),
        MemoryWriteTool(),
        MemorySearchTool(),
        PlanCreateTool(),
        PlanUpdateTool(),
        PlanShowTool(),
        SelfInspectTool(),
        AddToolTool(),
        ImprovePromptTool(),
        BlenderInfoTool(),
        BlenderCommandTool(),
        BlenderScreenshotTool(),
        RigStandardTool(),
        RigCheckTool(),
        RigApplyTool(),
    ):
        registry.register(tool)
    load_custom_tools(registry)
    return registry
