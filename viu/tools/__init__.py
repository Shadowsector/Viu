"""Система инструментов Вью."""

from .affordance_tool import AffordanceMatchTool, AffordanceShowTool
from .ask_tool import AskUserTool
from .base import AgentContext, Tool, ToolRegistry, ToolResult
from .blender_tool import (
    BlenderCommandTool,
    BlenderExportShanyaTool,
    BlenderInfoTool,
    BlenderScanTool,
    BlenderScreenshotTool,
)
from .filesystem import ListDirTool, ReadFileTool, WriteFileTool
from .loader import load_custom_tools
from .memory_tool import MemorySearchTool, MemoryWriteTool
from .planning_tool import PlanCreateTool, PlanShowTool, PlanUpdateTool
from .director_tool import RunNextStepTool
from .prepare_asset_tool import PrepareUnityAssetTool
from .prop_catalog_tool import PropCatalogListTool, PropCatalogScanTool, PropOrganizeDownloadsTool
from .roadmap_tool import (
    NextStepTool,
    ProjectStatusTool,
    RoadmapShowTool,
    RoadmapUpdateTool,
)
from .rig_tool import RigApplyAutoTool, RigApplyTool, RigCheckTool, RigMapTool, RigStandardTool
from .self_improve import AddToolTool, ImprovePromptTool, SelfInspectTool
from .shell import ShellTool
from .unity_project_tool import (
    UnityCloseTool,
    UnityDeploySetupTool,
    UnityFixManifestTool,
    UnityInitProjectTool,
    UnityImportStagingTool,
    UnityListTool,
    UnityOpenTool,
    UnityOverlayTool,
    UnityOverlayTuneTool,
    UnityPrepareSceneTool,
    UnityReadTool,
    UnityRunSetupTool,
    UnityScanAnimationsTool,
    UnitySyncAnimationsTool,
    UnityVerifyTool,
    UnityWriteTool,
)
from .unity_tool import UnityLogTool, UnityReportTool, UnityScanTool, UnityWorkflowTool
from .cursor_handoff_tool import (
    CursorHandoffBundleTool,
    CursorHandoffTool,
    CursorPushTool,
    GithubDiagnoseTool,
)
from .building_cascadeur_tool import BuildingWorkflowTool, CascadeurStatusTool
from .export_asset_tool import ExportUnityAssetTool
from .animation_catalog_tool import (
    AnimationCatalogMatchTool,
    AnimationCatalogShowTool,
    RouteInboxTool,
)
from .vision_tool import VisionAppendTool, VisionReadTool
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
        PropCatalogScanTool(),
        PropCatalogListTool(),
        PropOrganizeDownloadsTool(),
        PrepareUnityAssetTool(),
        RunNextStepTool(),
        VisionReadTool(),
        VisionAppendTool(),
        CursorHandoffTool(),
        CursorPushTool(),
        CursorHandoffBundleTool(),
        GithubDiagnoseTool(),
        BuildingWorkflowTool(),
        CascadeurStatusTool(),
        ExportUnityAssetTool(),
        AnimationCatalogShowTool(),
        AnimationCatalogMatchTool(),
        RouteInboxTool(),
        RoadmapShowTool(),
        RoadmapUpdateTool(),
        ProjectStatusTool(),
        NextStepTool(),
        SelfInspectTool(),
        AddToolTool(),
        ImprovePromptTool(),
        BlenderInfoTool(),
        BlenderCommandTool(),
        BlenderScanTool(),
        BlenderExportShanyaTool(),
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
        UnityScanAnimationsTool(),
        UnitySyncAnimationsTool(),
        UnityImportStagingTool(),
        UnityCloseTool(),
        UnityOpenTool(),
        UnityOverlayTool(),
        UnityOverlayTuneTool(),
        UnityPrepareSceneTool(),
        UnityVerifyTool(),
        UnityInitProjectTool(),
    ):
        registry.register(tool)
    load_custom_tools(registry)
    return registry
