"""Система инструментов Вью."""

from .affordance_tool import AffordanceMatchTool, AffordanceShowTool
from .ask_tool import AskUserTool
from .base import AgentContext, Tool, ToolRegistry, ToolResult
from .blender_tool import (
    BlenderAnimToCascadeurTool,
    BlenderCommandTool,
    BlenderExportCascadeurAnimTool,
    BlenderExportCascadeurBatchTool,
    BlenderExportCascadeurTool,
    BlenderExportShanyaTool,
    BlenderInfoTool,
    BlenderMakeAnimTool,
    BlenderScanTool,
    BlenderScreenshotTool,
)
from .filesystem import ListDirTool, ReadFileTool, WriteFileTool
from .loader import load_custom_tools
from .memory_tool import (
    ChatLogsClearTool,
    EventMemoryShowTool,
    MemorySearchTool,
    MemoryWriteTool,
)
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
    UnityOverlayBuildTool,
    UnityOverlayRebindTool,
    UnityOverlayTool,
    UnityOverlayTuneTool,
    UnityOverlayValidateTool,
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
from .cursor_inbox_tool import CursorInboxCompleteTool, CursorInboxPullTool
from .overlay_playtest_tool import OverlayPlaytestTool
from .creature_catalog_tool import (
    CreatureCatalogAutoSizeTool,
    CreatureCatalogScanTool,
    CreatureCatalogSetSizeTool,
    CreatureCatalogShowTool,
    CreatureBipedCanonTool,
    CreatureDescribeTool,
    CreatureLineupTool,
    CreaturePrepOpenTool,
    CreaturePrepSyncTool,
    CreaturePipelineNotesTool,
    CreatureCatalogMergeTool,
    CreatureWardrobeOpenTool,
    CreatureWardrobeSyncTool,
    CreatureStudioOpenTool,
    CreatureStudioSyncTool,
)
from .building_cascadeur_tool import BuildingWorkflowTool, CascadeurStatusTool
from .export_asset_tool import ExportUnityAssetTool
from .lab_tool import LabRateTool, LabRunAllTool, LabStartTool, LabStatusTool, LabStepTool
from .comfy_tool import (
    ComfyClipPickTool,
    ComfyVisionReviewTool,
    ComfyDiagTool,
    ComfyEnsureTool,
    ComfyReactorFixTool,
    ComfyFocusTool,
    ComfyQueueClearTool,
    ComfyInstallTool,
    ComfyLoraBindTool,
    ComfyLoraFetchTool,
    ComfyLoraListTool,
    ComfyLoraNoteTool,
    ComfyLoraPickTool,
    ComfyLoraScanTool,
    ComfyMocapTool,
    ComfyPromptTool,
    ComfyRunTool,
    ComfyShowTool,
    ComfyStatusTool,
    ComfyTripleTool,
    ComfyVisionReviewTool,
)
from .animation_catalog_tool import (
    AcceptAnimationInboxTool,
    AnimationCatalogMatchTool,
    AnimationCatalogShowTool,
    RouteInboxTool,
)
from .interaction_catalog_tool import (
    InteractionBlockingTool,
    InteractionCatalogShowTool,
    InteractionMasterDraftTool,
)
from .presence_tool import (
    AppsCloseTool,
    AppsRestartTool,
    AppsStatusTool,
    DecisionQueueAddTool,
    DecisionQueueAnswerTool,
    DecisionQueueDismissTool,
    DecisionQueueShowTool,
    PresenceSetTool,
    PresenceStatusTool,
)
from .eyes_tool import ScreenCaptureTool, VisionObserveTool, VisionReferenceTool
from .vision_tool import VisionAppendTool, VisionReadTool
from .web import WebFetchTool, WebSearchTool
from .asset_archive_tool import (
    AssetArchiveInventoryTool,
    AssetArchiveStageTool,
    AssetProvenanceTool,
)
from .machine_bind_tool import MachineBindTool
from .body_pipeline_tool import BodyPipelineTool
from .character_card_tool import (
    CharacterCardDeserializeTool,
    CharacterCardMatchTool,
    CharacterCardProbeTool,
    CharacterCardSetupTool,
)

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
        PresenceSetTool(),
        PresenceStatusTool(),
        DecisionQueueShowTool(),
        DecisionQueueAddTool(),
        DecisionQueueAnswerTool(),
        DecisionQueueDismissTool(),
        AppsStatusTool(),
        AppsCloseTool(),
        AppsRestartTool(),
        ReadFileTool(),
        WriteFileTool(),
        ListDirTool(),
        ShellTool(),
        WebSearchTool(),
        WebFetchTool(),
        ScreenCaptureTool(),
        VisionObserveTool(),
        VisionReferenceTool(),
        MemoryWriteTool(),
        MemorySearchTool(),
        ChatLogsClearTool(),
        EventMemoryShowTool(),
        PlanCreateTool(),
        PlanUpdateTool(),
        PlanShowTool(),
        PropCatalogScanTool(),
        PropCatalogListTool(),
        PropOrganizeDownloadsTool(),
        AssetArchiveInventoryTool(),
        AssetArchiveStageTool(),
        AssetProvenanceTool(),
        MachineBindTool(),
        BodyPipelineTool(),
        CharacterCardProbeTool(),
        CharacterCardDeserializeTool(),
        CharacterCardMatchTool(),
        CharacterCardSetupTool(),
        PrepareUnityAssetTool(),
        RunNextStepTool(),
        VisionReadTool(),
        VisionAppendTool(),
        CursorHandoffTool(),
        CursorPushTool(),
        CursorHandoffBundleTool(),
        CursorInboxPullTool(),
        CursorInboxCompleteTool(),
        GithubDiagnoseTool(),
        OverlayPlaytestTool(),
        BuildingWorkflowTool(),
        CascadeurStatusTool(),
        CreatureCatalogScanTool(),
        CreatureCatalogShowTool(),
        CreatureBipedCanonTool(),
        CreatureCatalogSetSizeTool(),
        CreatureCatalogAutoSizeTool(),
        CreatureDescribeTool(),
        CreatureLineupTool(),
        CreaturePrepOpenTool(),
        CreaturePrepSyncTool(),
        CreaturePipelineNotesTool(),
        CreatureCatalogMergeTool(),
        CreatureWardrobeOpenTool(),
        CreatureWardrobeSyncTool(),
        CreatureStudioOpenTool(),
        CreatureStudioSyncTool(),
        LabStartTool(),
        LabStepTool(),
        LabRunAllTool(),
        LabStatusTool(),
        LabRateTool(),
        ComfyStatusTool(),
        ComfyInstallTool(),
        ComfyEnsureTool(),
        ComfyDiagTool(),
        ComfyReactorFixTool(),
        ComfyFocusTool(),
        ComfyQueueClearTool(),
        ComfyRunTool(),
        ComfyMocapTool(),
        ComfyShowTool(),
        ComfyPromptTool(),
        ComfyTripleTool(),
        ComfyVisionReviewTool(),
        ComfyClipPickTool(),
        ComfyLoraListTool(),
        ComfyLoraScanTool(),
        ComfyLoraPickTool(),
        ComfyLoraNoteTool(),
        ComfyLoraBindTool(),
        ComfyLoraFetchTool(),
        ExportUnityAssetTool(),
        AcceptAnimationInboxTool(),
        AnimationCatalogShowTool(),
        AnimationCatalogMatchTool(),
        InteractionCatalogShowTool(),
        InteractionBlockingTool(),
        InteractionMasterDraftTool(),
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
        BlenderExportCascadeurTool(),
        BlenderExportCascadeurBatchTool(),
        BlenderExportCascadeurAnimTool(),
        BlenderMakeAnimTool(),
        BlenderAnimToCascadeurTool(),
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
        UnityOverlayValidateTool(),
        UnityOverlayRebindTool(),
        UnityOverlayBuildTool(),
        UnityOverlayTool(),
        UnityOverlayTuneTool(),
        UnityPrepareSceneTool(),
        UnityVerifyTool(),
        UnityInitProjectTool(),
    ):
        registry.register(tool)
    load_custom_tools(registry)
    return registry
