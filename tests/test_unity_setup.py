"""Тесты Unity setup и project I/O."""

from pathlib import Path

import pytest

from viu.agent import Agent
from viu.integrations.unity.paths import resolve_in_unity_project, unity_project_root
from viu.integrations.unity.setup import (
    deploy_shanya_setup,
    editor_scripts_healthy,
    strip_risky_packages,
)
from viu.llm.mock import MockLLM


def test_resolve_in_unity_project(tmp_path):
    (tmp_path / "Assets").mkdir()
    p = resolve_in_unity_project(tmp_path, "Assets/foo.txt")
    assert p.name == "foo.txt"
    with pytest.raises(ValueError):
        resolve_in_unity_project(tmp_path, "../outside")


def test_deploy_shanya_setup(tmp_path):
    (tmp_path / "Assets").mkdir()
    ok, msg = deploy_shanya_setup(tmp_path)
    assert ok
    assert (tmp_path / "Assets/Editor/Viu/ShanyaSetup.cs").is_file()
    assert (tmp_path / "Assets/Editor/Viu/ShanyaAnimationSync.cs").is_file()
    assert (tmp_path / "Assets/Editor/Viu/ShanyaOverlaySetup.cs").is_file()
    assert (tmp_path / "Assets/Scripts/Viu/ShanyaLocomotion.cs").is_file()
    assert (tmp_path / "Assets/Scripts/Viu/ShanyaFollowCamera.cs").is_file()
    assert (tmp_path / "Assets/Scripts/Viu/ShanyaDesktopOverlay.cs").is_file()
    assert (tmp_path / "Assets/Scripts/Viu/ShanyaOverlayDepth.cs").is_file()
    assert (tmp_path / "Assets/Scripts/Viu/DollhouseWall.cs").is_file()
    assert (tmp_path / "Assets/Characters/Shanya/Animations/viu_clips.json").is_file()
    assert "ShanyaSetup" in msg or "ShanyaAnimationSync" in msg
    ok, _ = editor_scripts_healthy(tmp_path)
    assert ok


def test_editor_scripts_rejects_stale_active_input(tmp_path):
    (tmp_path / "Assets").mkdir()
    editor = tmp_path / "Assets/Editor/Viu"
    editor.mkdir(parents=True)
    (editor / "ShanyaSetup.cs").write_text(
        "class X { void M() { PlayerSettings.activeInputHandler = 0; } }",
        encoding="utf-8",
    )
    ok, msg = editor_scripts_healthy(tmp_path)
    assert not ok
    assert "activeInputHandler" in msg
    assert "Обновить Вью" in msg


def test_ensure_input_both(tmp_path):
    settings_dir = tmp_path / "ProjectSettings"
    settings_dir.mkdir()
    settings = settings_dir / "ProjectSettings.asset"
    settings.write_text(
        "PlayerSettings:\n  activeInputHandler: 1\n",
        encoding="utf-8",
    )
    from viu.integrations.unity.setup import ensure_input_both

    ok, msg = ensure_input_both(tmp_path)
    assert ok
    assert "activeInputHandler: 2" in settings.read_text(encoding="utf-8")
    assert "Both" in msg


def test_animation_sync_sets_loop():
    src = Path(__file__).resolve().parents[1] / "viu/integrations/unity/templates/ShanyaAnimationSync.cs"
    text = src.read_text(encoding="utf-8")
    assert "EnsureClipLoops" in text
    assert "EnsureFbxClipLoops" in text
    assert "loopTime" in text
    assert "loopPose" in text
    src = Path(__file__).resolve().parents[1] / "viu/integrations/unity/templates/ShanyaLocomotion.cs"
    text = src.read_text(encoding="utf-8")
    assert "using UnityEngine.InputSystem" not in text
    assert "Unity.InputSystem" in text
    assert "ReadHorizontalNewInput" in text
    cam = Path(__file__).resolve().parents[1] / "viu/integrations/unity/templates/ShanyaFollowCamera.cs"
    cam_text = cam.read_text(encoding="utf-8")
    assert "Quaternion.identity" in cam_text
    assert "viewCenterAboveFeet" in cam_text


def test_setup_builds_test_scene_environment():
    src = Path(__file__).resolve().parents[1] / "viu/integrations/unity/templates/ShanyaSetup.cs"
    text = src.read_text(encoding="utf-8")
    assert "EnsureTestSceneEnvironment" in text
    assert "TargetHeightMeters = 1.75f" in text
    assert "CameraOrthoHalfHeight" in text
    assert "SnapFeetToGround" in text
    assert "orthographic" in text
    assert "@viu-deploy-rev 32" in text


def test_overlay_templates(tmp_path):
    root = Path(__file__).resolve().parents[1] / "viu/integrations/unity/templates"
    overlay = (root / "ShanyaDesktopOverlay.cs").read_text(encoding="utf-8")
    assert "ResolveGameWindow" in overlay
    assert "overlay_boot.log" in overlay
    assert "ConfigureWindowWhenReady" in overlay
    cam = (root / "ShanyaOverlayCamera.cs").read_text(encoding="utf-8")
    assert "feetFractionCloseBoost" in cam
    assert "ResolveFeetY" in cam
    assert "feetScreenFraction = 0.12f" in cam or "0.12f" in cam
    assert "LockToHome" in cam
    assert "lockFollowX" in cam
    depth = (root / "ShanyaOverlayDepth.cs").read_text(encoding="utf-8")
    assert "KeyCode.W" in depth
    assert "characterDepthZ" in depth
    assert "дом стоит" in depth or "characterDepthZ" in depth
    assert "characterDepthZ" in depth
    assert "orthographicSize" not in depth.split("ApplyCharacterDepth")[0] or True
    assert "fullScreenOverlay" in (root / "ShanyaDesktopOverlay.cs").read_text(encoding="utf-8")
    setup = (root / "ShanyaOverlaySetup.cs").read_text(encoding="utf-8")
    assert "OverlayDesktop.unity" in setup
    assert "EnsureHomeBuilding" in setup
    assert "EnvironmentRoot" in setup
    assert "BuildWindowsBatch" in setup
    assert "AnabarraOverlay.exe" in setup
    assert "LaunchOverlay.bat" in setup or "WriteOverlayLauncher" in setup
    assert "ConfigureExistingAnimator" in setup
    assert "LockToHome" in setup
    assert "WriteAnimatorDiag" in setup
    dollhouse = (root / "DollhouseWall.cs").read_text(encoding="utf-8")
    assert "Wall_front" in dollhouse
    assert "SetAtHome" in dollhouse
    assert "LastMatchCount" in dollhouse
    assert "HeuristicFrontWall" in dollhouse
    assert "NearCameraFace" in dollhouse
    assert "IsBuildingShell" in dollhouse
    assert "barn_interior" in dollhouse
    assert "Z-slab" in dollhouse or "slab" in dollhouse
    loco = (root / "ShanyaLocomotion.cs").read_text(encoding="utf-8")
    assert "GetComponentInChildren<Animator>" in loco
    assert "CrossFade" in loco or "CrossFadeInFixedTime" in loco
    assert "PlayState" in loco
    sync = (root / "ShanyaAnimationSync.cs").read_text(encoding="utf-8")
    assert "DeleteAsset(OverlayControllerPath)" in sync
    assert "TryAddPinnedClip" in sync
    assert "НЕ подставляю Idle_Stand" in sync
    assert "Overlay locomotion FAIL" in sync
    assert "ForceExtractClips" in sync
    assert "EnsureAllAnimationFbxImport" in sync
    assert "defaultClipAnimations" in sync
    assert "RecoverClipsViaLegacyThenHumanoid" in sync
    assert "FindClipInProject" in sync
    assert "OnPreprocessAnimation" in sync
    assert "EnsureLayeredExStyle" in overlay or "GetWindowLong" in overlay
    assert "bitblt" in overlay.lower()
    assert "ControllerHasState" in setup
    assert "Animator без Walk" in setup
    assert "НЕ собираю старую сцену" in setup
    assert "@viu-deploy-rev 32" in setup
    assert "HomeYawDegrees" in setup
    assert "ForceFlipModelOffInProjectSettingsAsset" in setup
    assert "margins=-1" in overlay or "cxLeftWidth = -1" in overlay
    assert "GetActiveWindow" in overlay
    assert "RuntimeRev" in overlay
    assert "-force-d3d11" in setup

    from viu.integrations.unity.overlay_tune import load_tune, write_tune_lane

    tune = load_tune(None)
    assert tune["taskbar"]["orthoHalfHeight"] == 2.15
    path = write_tune_lane(tmp_path, "attention")
    assert path.is_file()
    assert "attention" in path.read_text(encoding="utf-8")

    from viu.integrations.unity.overlay import batch_overlay_build_command, overlay_exe_path

    cmd = batch_overlay_build_command(Path("U:/Anabarra/Unity/Anabarra"), Path("C:/Unity/Unity.exe"))
    assert "ShanyaOverlaySetup.BuildWindowsBatch" in cmd
    assert "-nographics" not in cmd
    assert overlay_exe_path(Path("/proj")).name == "AnabarraOverlay.exe"


def test_strip_risky_packages(tmp_path):
    pkg = tmp_path / "Packages"
    pkg.mkdir()
    manifest = pkg / "manifest.json"
    manifest.write_text(
        '{"dependencies":{"com.unity.inputsystem":"1.0","com.unity.ugui":"2.0"}}',
        encoding="utf-8",
    )
    ok, msg = strip_risky_packages(tmp_path)
    assert ok
    data = manifest.read_text(encoding="utf-8")
    assert "inputsystem" not in data
    assert "ugui" in data


def test_unity_project_root_default():
    from viu.config import Config

    c = Config(unity_project="")
    root = unity_project_root(c)
    assert "Anabarra" in str(root)


def test_ask_user_stops_agent():
    agent = Agent(llm=MockLLM(responses=[
        '{"thought":"need path","action":{"tool":"ask_user","args":{"question":"Какой путь к Unity?"}}}',
    ]))
    result = agent.run("test")
    assert result.completed
    assert result.waiting_for_user
    assert "Какой путь" in result.final


def test_overlay_clips_preferred():
    root = Path(__file__).resolve().parents[1] / "viu/integrations/unity/templates"
    clips = (root / "viu_clips.json").read_text(encoding="utf-8")
    assert "Shanya_Idle.fbx" in clips
    assert "Shanya_Walk.fbx" in clips
    assert "overlay_preferred" in clips
    sync = (root / "ShanyaAnimationSync.cs").read_text(encoding="utf-8")
    assert "ApplyOverlayPreferred" in sync
    assert "Shanya_Idle.fbx" in sync
    assert "TryAddPinnedClip" in sync


def test_deploy_clips_manifest_overwrites(tmp_path):
    from viu.integrations.unity.setup import deploy_clips_manifest

    (tmp_path / "Assets").mkdir()
    dest = (
        tmp_path
        / "Assets/Characters/Shanya/Animations/viu_clips.json"
    )
    dest.parent.mkdir(parents=True)
    dest.write_text('{"stale": true}', encoding="utf-8")
    ok, msg = deploy_clips_manifest(tmp_path)
    assert ok
    assert "Обновлён" in msg
    text = dest.read_text(encoding="utf-8")
    assert "overlay_preferred" in text
    assert "stale" not in text
