"""Запись Editor-скриптов и правки manifest.json Unity-проекта."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from .paths import resolve_in_unity_project, unity_project_root

_TEMPLATE_SETUP = Path(__file__).parent / "templates" / "ShanyaSetup.cs"
_TEMPLATE_OUTFIT = Path(__file__).parent / "templates" / "ShanyaOutfit.cs"
_EDITOR_DIR = "Assets/Editor/Viu"
_SETUP_REL = f"{_EDITOR_DIR}/ShanyaSetup.cs"
_OUTFIT_REL = f"{_EDITOR_DIR}/ShanyaOutfit.cs"

# Пакеты, которые часто ломают новый URP-проект (Safe Mode) — опционально убрать.
_RISKY_PACKAGES = (
    "com.unity.inputsystem",
    "com.unity.ai.navigation",
)


def deploy_editor_scripts(project_root: Path) -> Tuple[bool, str]:
    """Копирует ShanyaSetup.cs и ShanyaOutfit.cs в Assets/Editor/Viu/."""
    if not _TEMPLATE_SETUP.is_file():
        return False, f"Шаблон не найден: {_TEMPLATE_SETUP}"
    dest_dir = resolve_in_unity_project(project_root, _EDITOR_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for src, rel in ((_TEMPLATE_SETUP, _SETUP_REL), (_TEMPLATE_OUTFIT, _OUTFIT_REL)):
        if not src.is_file():
            continue
        dest = resolve_in_unity_project(project_root, rel)
        shutil.copy2(src, dest)
        copied.append(rel)
    if not copied:
        return False, "Нет шаблонов для копирования"
    return True, "Установлено: " + ", ".join(copied)


def deploy_shanya_setup(project_root: Path) -> Tuple[bool, str]:
    """Обратная совместимость — deploy обоих Editor-скриптов."""
    return deploy_editor_scripts(project_root)


def strip_risky_packages(project_root: Path, packages: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Удаляет проблемные пакеты из Packages/manifest.json."""
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
    """VIU_UNITY_EXE или типичный путь Hub на Windows."""
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return p.resolve()
    # Hub: последний 6000.3.x LTS
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
