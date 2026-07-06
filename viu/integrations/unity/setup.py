"""Запись Editor-скриптов и правки manifest.json Unity-проекта."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from .animation_scan import ANIMATIONS_REL, MANIFEST_NAME
from .paths import resolve_in_unity_project, unity_project_root

_TEMPLATE_SETUP = Path(__file__).parent / "templates" / "ShanyaSetup.cs"
_TEMPLATE_OUTFIT = Path(__file__).parent / "templates" / "ShanyaOutfit.cs"
_TEMPLATE_SYNC = Path(__file__).parent / "templates" / "ShanyaAnimationSync.cs"
_TEMPLATE_LOCOMOTION = Path(__file__).parent / "templates" / "ShanyaLocomotion.cs"
_TEMPLATE_MANIFEST = Path(__file__).parent / "templates" / "viu_clips.json"
_EDITOR_DIR = "Assets/Editor/Viu"
_RUNTIME_DIR = "Assets/Scripts/Viu"
_SETUP_REL = f"{_EDITOR_DIR}/ShanyaSetup.cs"
_OUTFIT_REL = f"{_EDITOR_DIR}/ShanyaOutfit.cs"
_SYNC_REL = f"{_EDITOR_DIR}/ShanyaAnimationSync.cs"
_LOCOMOTION_REL = f"{_RUNTIME_DIR}/ShanyaLocomotion.cs"
_MANIFEST_REL = f"{ANIMATIONS_REL}/{MANIFEST_NAME}"

_RISKY_PACKAGES = (
    "com.unity.inputsystem",
    "com.unity.ai.navigation",
)


def deploy_editor_scripts(project_root: Path) -> Tuple[bool, str]:
    """Копирует Editor-скрипты Viu в Assets/Editor/Viu/."""
    dest_dir = resolve_in_unity_project(project_root, _EDITOR_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    for src, rel in (
        (_TEMPLATE_SETUP, _SETUP_REL),
        (_TEMPLATE_OUTFIT, _OUTFIT_REL),
        (_TEMPLATE_SYNC, _SYNC_REL),
    ):
        if not src.is_file():
            continue
        shutil.copy2(src, resolve_in_unity_project(project_root, rel))
        copied.append(rel)
    if not copied:
        return False, "Нет шаблонов Editor-скриптов"
    return True, "Editor: " + ", ".join(Path(p).name for p in copied)


def deploy_runtime_scripts(project_root: Path) -> Tuple[bool, str]:
    """Копирует runtime-скрипты (ShanyaLocomotion) в Assets/Scripts/Viu/."""
    if not _TEMPLATE_LOCOMOTION.is_file():
        return False, "Шаблон locomotion не найден"
    dest = resolve_in_unity_project(project_root, _LOCOMOTION_REL)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_TEMPLATE_LOCOMOTION, dest)
    return True, str(dest)


def deploy_clips_manifest(project_root: Path, overwrite: bool = False) -> Tuple[bool, str]:
    """Кладёт viu_clips.json в Animations/, если файла ещё нет."""
    if not _TEMPLATE_MANIFEST.is_file():
        return False, "Шаблон viu_clips.json не найден"
    dest = resolve_in_unity_project(project_root, _MANIFEST_REL)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not overwrite:
        return True, f"Уже есть: {dest}"
    shutil.copy2(_TEMPLATE_MANIFEST, dest)
    return True, f"Создан: {dest}"


def deploy_animation_pipeline(project_root: Path) -> Tuple[bool, str]:
    """Editor + runtime + viu_clips.json."""
    parts: List[str] = []
    ok = True
    for fn in (deploy_editor_scripts, deploy_runtime_scripts, deploy_clips_manifest):
        part_ok, msg = fn(project_root)
        parts.append(msg)
        ok = ok and part_ok
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
