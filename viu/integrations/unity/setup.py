"""Запись Editor-скриптов и правки manifest.json Unity-проекта."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from .animation_scan import ANIMATIONS_REL, MANIFEST_NAME
from .paths import resolve_in_unity_project, unity_project_root

_TEMPLATE_SETUP = Path(__file__).parent / "templates" / "ShanyaSetup.cs"
_TEMPLATE_OUTFIT = Path(__file__).parent / "templates" / "ShanyaOutfit.cs"
_TEMPLATE_SYNC = Path(__file__).parent / "templates" / "ShanyaAnimationSync.cs"
_TEMPLATE_LOCOMOTION = Path(__file__).parent / "templates" / "ShanyaLocomotion.cs"
_TEMPLATE_CAMERA = Path(__file__).parent / "templates" / "ShanyaFollowCamera.cs"
_TEMPLATE_OVERLAY = Path(__file__).parent / "templates" / "ShanyaDesktopOverlay.cs"
_TEMPLATE_OVERLAY_CAM = Path(__file__).parent / "templates" / "ShanyaOverlayCamera.cs"
_TEMPLATE_OVERLAY_DEPTH = Path(__file__).parent / "templates" / "ShanyaOverlayDepth.cs"
_TEMPLATE_DOLLHOUSE = Path(__file__).parent / "templates" / "DollhouseWall.cs"
_TEMPLATE_OVERLAY_SETUP = Path(__file__).parent / "templates" / "ShanyaOverlaySetup.cs"
_TEMPLATE_MANIFEST = Path(__file__).parent / "templates" / "viu_clips.json"
_EDITOR_DIR = "Assets/Editor/Viu"
_RUNTIME_DIR = "Assets/Scripts/Viu"
_SETUP_REL = f"{_EDITOR_DIR}/ShanyaSetup.cs"
_OUTFIT_REL = f"{_EDITOR_DIR}/ShanyaOutfit.cs"
_SYNC_REL = f"{_EDITOR_DIR}/ShanyaAnimationSync.cs"
_OVERLAY_SETUP_REL = f"{_EDITOR_DIR}/ShanyaOverlaySetup.cs"
_LOCOMOTION_REL = f"{_RUNTIME_DIR}/ShanyaLocomotion.cs"
_CAMERA_REL = f"{_RUNTIME_DIR}/ShanyaFollowCamera.cs"
_OVERLAY_REL = f"{_RUNTIME_DIR}/ShanyaDesktopOverlay.cs"
_OVERLAY_CAM_REL = f"{_RUNTIME_DIR}/ShanyaOverlayCamera.cs"
_OVERLAY_DEPTH_REL = f"{_RUNTIME_DIR}/ShanyaOverlayDepth.cs"
_DOLLHOUSE_REL = f"{_RUNTIME_DIR}/DollhouseWall.cs"
_MANIFEST_REL = f"{ANIMATIONS_REL}/{MANIFEST_NAME}"

VIU_DEPLOY_REV = "29"
VIU_DEPLOY_MARKER = f"@viu-deploy-rev {VIU_DEPLOY_REV}"
_BROKEN_EDITOR_MARKERS = (
    "activeInputHandler",
    "EnsureInputCompatible",
    "follow.height",
    "lookAtHeight",
    "follow.cameraY",
)

_RISKY_PACKAGES = (
    "com.unity.inputsystem",
    "com.unity.ai.navigation",
)


def editor_scripts_healthy(project_root: Path) -> Tuple[bool, str]:
    """Проверить, что в Unity лежат актуальные Editor-скрипты Viu (не старый кэш)."""
    setup = resolve_in_unity_project(project_root, _SETUP_REL)
    if not setup.is_file():
        return False, "В проекте нет Assets/Editor/Viu/ShanyaSetup.cs — нужен deploy скриптов."
    text = setup.read_text(encoding="utf-8", errors="replace")
    for bad in _BROKEN_EDITOR_MARKERS:
        if bad in text:
            return False, (
                f"В Unity лежит **старый** ShanyaSetup.cs (внутри «{bad}»). "
                "Сначала нажми **«Обновить Вью»**, потом снова «Импорт FBX» или «Обновить аниматор»."
            )
    if VIU_DEPLOY_MARKER not in text:
        return False, (
            "Скрипты Viu в проекте устарели (нет метки версии deploy). "
            "Нажми **«Обновить Вью»** и повтори операцию."
        )
    return True, ""


def ensure_flip_model_off(project_root: Path) -> Tuple[bool, str]:
    """Прозрачный оверлей ломается с DXGI flip model — нужен BitBlt."""
    settings = project_root / "ProjectSettings" / "ProjectSettings.asset"
    if not settings.is_file():
        return True, ""
    text = settings.read_text(encoding="utf-8", errors="replace")
    new_text, n = re.subn(
        r"(?m)^(\s*)useFlipModelSwapchain:\s*1\s*$",
        r"\1useFlipModelSwapchain: 0",
        text,
    )
    if n:
        settings.write_text(new_text, encoding="utf-8")
        return True, "Player Settings: flip model swapchain OFF (нужно для прозрачного оверлея)."
    return True, ""


def ensure_input_both(project_root: Path) -> Tuple[bool, str]:
    """Input System only без пакета ломает A/D — ставим Both в ProjectSettings.asset."""
    settings = project_root / "ProjectSettings" / "ProjectSettings.asset"
    if not settings.is_file():
        return True, ""
    text = settings.read_text(encoding="utf-8", errors="replace")
    new_text, n = re.subn(
        r"(?m)^(\s*)activeInputHandler:\s*1\s*$",
        r"\1activeInputHandler: 2",
        text,
    )
    if n:
        settings.write_text(new_text, encoding="utf-8")
        return True, "Player Settings: Input → Both (A/D через старый Input Manager)."
    return True, ""


def deploy_editor_scripts(project_root: Path) -> Tuple[bool, str]:
    """Копирует Editor-скрипты Viu в Assets/Editor/Viu/."""
    dest_dir = resolve_in_unity_project(project_root, _EDITOR_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    for src, rel in (
        (_TEMPLATE_SETUP, _SETUP_REL),
        (_TEMPLATE_OUTFIT, _OUTFIT_REL),
        (_TEMPLATE_SYNC, _SYNC_REL),
        (_TEMPLATE_OVERLAY_SETUP, _OVERLAY_SETUP_REL),
    ):
        if not src.is_file():
            continue
        shutil.copy2(src, resolve_in_unity_project(project_root, rel))
        copied.append(rel)
    if not copied:
        return False, "Нет шаблонов Editor-скриптов"
    ok, hint = editor_scripts_healthy(project_root)
    if not ok:
        return False, f"Скопировал файлы, но проверка не прошла: {hint}"
    return True, "Editor: " + ", ".join(Path(p).name for p in copied)


def deploy_runtime_scripts(project_root: Path) -> Tuple[bool, str]:
    """Копирует runtime-скрипты в Assets/Scripts/Viu/."""
    dest_dir = resolve_in_unity_project(project_root, _RUNTIME_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    for src, rel in (
        (_TEMPLATE_LOCOMOTION, _LOCOMOTION_REL),
        (_TEMPLATE_CAMERA, _CAMERA_REL),
        (_TEMPLATE_OVERLAY, _OVERLAY_REL),
        (_TEMPLATE_OVERLAY_CAM, _OVERLAY_CAM_REL),
        (_TEMPLATE_OVERLAY_DEPTH, _OVERLAY_DEPTH_REL),
        (_TEMPLATE_DOLLHOUSE, _DOLLHOUSE_REL),
    ):
        if not src.is_file():
            continue
        shutil.copy2(src, resolve_in_unity_project(project_root, rel))
        copied.append(Path(rel).name)
    if not copied:
        return False, "Нет runtime-шаблонов"
    return True, ", ".join(copied)


def deploy_clips_manifest(project_root: Path, overwrite: bool = True) -> Tuple[bool, str]:
    """Кладёт viu_clips.json (overlay_preferred Idle/Walk). По умолчанию перезаписывает —
    иначе на машине Дена навсегда залипает старый манифест без Walk-пинов."""
    if not _TEMPLATE_MANIFEST.is_file():
        return False, "Шаблон viu_clips.json не найден"
    dest = resolve_in_unity_project(project_root, _MANIFEST_REL)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not overwrite:
        return True, f"Уже есть: {dest}"
    existed = dest.exists()
    shutil.copy2(_TEMPLATE_MANIFEST, dest)
    return True, f"{'Обновлён' if existed else 'Создан'}: {dest}"


def deploy_animation_pipeline(project_root: Path) -> Tuple[bool, str]:
    """Editor + runtime + viu_clips.json."""
    parts: List[str] = []
    ok = True
    for fn in (deploy_editor_scripts, deploy_runtime_scripts, deploy_clips_manifest):
        part_ok, msg = fn(project_root)
        parts.append(msg)
        ok = ok and part_ok
    in_ok, in_msg = ensure_input_both(project_root)
    if in_msg:
        parts.append(in_msg)
    ok = ok and in_ok
    flip_ok, flip_msg = ensure_flip_model_off(project_root)
    if flip_msg:
        parts.append(flip_msg)
    ok = ok and flip_ok
    return ok, "\n".join(parts)


def deploy_shanya_setup(project_root: Path) -> Tuple[bool, str]:
    return deploy_animation_pipeline(project_root)


def strip_risky_packages(project_root: Path, packages: Optional[List[str]] = None) -> Tuple[bool, str]:
    manifest = resolve_in_unity_project(project_root, "Packages/manifest.json")
    if not manifest.is_file():
        return False, f"manifest.json не найден: {manifest}"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    deps = data.get("dependencies", {})
    remove = packages or list(_RISKY_PACKAGES)
    removed = [p for p in remove if p in deps]
    if not removed:
        return True, "Нечего удалять — пакеты уже отсутствуют в manifest.json"
    for p in removed:
        del deps[p]
    manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True, f"Удалено из manifest.json: {', '.join(removed)}. Перезапусти Unity."


def find_unity_exe(configured: str) -> Optional[Path]:
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return p.resolve()
    hub = Path("C:/Program Files/Unity/Hub/Editor")
    if hub.is_dir():
        candidates = sorted(hub.glob("6000.3.*/Editor/Unity.exe"), reverse=True)
        if candidates:
            return candidates[0].resolve()
        any_unity = sorted(hub.glob("*/Editor/Unity.exe"), reverse=True)
        if any_unity:
            return any_unity[0].resolve()
    return None


def batch_setup_command(project_root: Path, unity_exe: Path) -> str:
    proj = str(project_root.resolve())
    exe = str(unity_exe.resolve())
    return (
        f'"{exe}" -batchmode -quit -nographics '
        f'-projectPath "{proj}" '
        f'-executeMethod Viu.Editor.ShanyaSetup.RunBatch '
        f'-logFile "{proj}/viu_setup.log"'
    )


def batch_sync_animations_command(project_root: Path, unity_exe: Path) -> str:
    proj = str(project_root.resolve())
    exe = str(unity_exe.resolve())
    return (
        f'"{exe}" -batchmode -quit -nographics '
        f'-projectPath "{proj}" '
        f'-executeMethod Viu.Editor.ShanyaAnimationSync.RunBatch '
        f'-logFile "{proj}/viu_anim_sync.log"'
    )


def open_editor_command(project_root: Path, unity_exe: Path) -> list[str]:
    """Аргументы для запуска обычного (GUI) редактора Unity с проектом."""
    return [str(unity_exe.resolve()), "-projectPath", str(project_root.resolve())]


def batch_overlay_build_command(project_root: Path, unity_exe: Path) -> str:
    from .overlay import batch_overlay_build_command as _cmd

    return _cmd(project_root, unity_exe)
