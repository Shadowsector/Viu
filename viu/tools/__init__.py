"""Система инструментов Вью."""

from .affordance_tool import AffordanceMatchTool, AffordanceShowTool
from .ask_tool import AskUserTool
from .base import AgentContext, Tool, ToolRegistry, ToolResult
from .blender_tool import (
    BlenderCommandTool,
    BlenderInfoTool,
    BlenderScanTool,
    BlenderScreenshotTool,
)
from .filesystem import ListDirTool, ReadFileTool, WriteFileTool
from .loader import load_custom_tools
from .memory_tool import MemorySearchTool, MemoryWriteTool
from .planning_tool import PlanCreateTool, PlanShowTool, PlanUpdateTool
from .rig_tool import RigApplyAutoTool, RigApplyTool, RigCheckTool, RigMapTool, RigStandardTool
from .self_improve import AddToolTool, ImprovePromptTool, SelfInspectTool
from .shell import ShellTool
from .unity_project_tool import (
    UnityDeploySetupTool,
    UnityFixManifestTool,
    UnityListTool,
    UnityReadTool,
    UnityRunSetupTool,
    UnityWriteTool,
)
from .unity_tool import UnityLogTool, UnityReportTool, UnityScanTool, UnityWorkflowTool
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
        AskUserTool(),
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
        BlenderScanTool(),
        BlenderScreenshotTool(),
        RigStandardTool(),
        RigCheckTool(),
        RigMapTool(),
        RigApplyTool(),
        RigApplyAutoTool(),
        AffordanceShowTool(),
        AffordanceMatchTool(),
        UnityLogTool(),
        UnityScanTool(),
        UnityWorkflowTool(),
        UnityReportTool(),
        UnityReadTool(),
        UnityWriteTool(),
        UnityListTool(),
        UnityDeploySetupTool(),
        UnityFixManifestTool(),
        UnityRunSetupTool(),
    ):
        registry.register(tool)
    load_custom_tools(registry)
    return registry
