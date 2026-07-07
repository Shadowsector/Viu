"""Сборка и запуск десктоп-оверлея Шани (Windows)."""

from __future__ import annotations

from pathlib import Path

OVERLAY_SCENE_REL = "Assets/Scenes/OverlayDesktop.unity"
OVERLAY_BUILD_DIR = "Builds/AnabarraOverlay"
OVERLAY_EXE = "AnabarraOverlay.exe"


def overlay_exe_path(project_root: Path) -> Path:
    return (project_root / OVERLAY_BUILD_DIR / OVERLAY_EXE).resolve()


def batch_overlay_scene_command(project_root: Path, unity_exe: Path) -> str:
    proj = str(project_root.resolve())
    exe = str(unity_exe.resolve())
    return (
        f'"{exe}" -batchmode -quit -nographics '
        f'-projectPath "{proj}" '
        f'-executeMethod Viu.Editor.ShanyaOverlaySetup.RunBatch '
        f'-logFile "{proj}/viu_overlay_scene.log"'
    )


def batch_overlay_build_command(project_root: Path, unity_exe: Path) -> str:
    proj = str(project_root.resolve())
    exe = str(unity_exe.resolve())
    return (
        f'"{exe}" -batchmode -quit -nographics '
        f'-projectPath "{proj}" '
        f'-executeMethod Viu.Editor.ShanyaOverlaySetup.BuildWindowsBatch '
        f'-logFile "{proj}/viu_overlay_build.log"'
    )
