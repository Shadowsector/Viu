"""Сборка и запуск десктоп-оверлея Шани (Windows)."""

from __future__ import annotations

from pathlib import Path

OVERLAY_SCENE_REL = "Assets/Scenes/OverlayDesktop.unity"
OVERLAY_BUILD_DIR = "Builds/AnabarraOverlay"
OVERLAY_EXE = "AnabarraOverlay.exe"


def overlay_exe_path(project_root: Path) -> Path:
    return (project_root / OVERLAY_BUILD_DIR / OVERLAY_EXE).resolve()


def _batch_command(project_root: Path, unity_exe: Path, method: str, log_name: str) -> str:
    proj = str(project_root.resolve())
    exe = str(unity_exe.resolve())
    # Без -nographics: иначе FBX animation takes часто пустые (defaultClipAnimations=0).
    return (
        f'"{exe}" -batchmode -quit '
        f'-projectPath "{proj}" '
        f'-executeMethod Viu.Editor.ShanyaOverlaySetup.{method} '
        f'-logFile "{proj}/{log_name}"'
    )


def batch_overlay_scene_command(project_root: Path, unity_exe: Path) -> str:
    return _batch_command(project_root, unity_exe, "RunBatch", "viu_overlay_scene.log")


def batch_overlay_validate_command(project_root: Path, unity_exe: Path) -> str:
    return _batch_command(
        project_root, unity_exe, "ValidateOverlaySceneBatch", "viu_overlay_validate.log"
    )


def batch_overlay_rebind_command(project_root: Path, unity_exe: Path) -> str:
    return _batch_command(
        project_root, unity_exe, "RebindMaterialsBatch", "viu_overlay_rebind.log"
    )


def batch_overlay_build_command(project_root: Path, unity_exe: Path) -> str:
    return _batch_command(
        project_root, unity_exe, "BuildWindowsBatch", "viu_overlay_build.log"
    )
