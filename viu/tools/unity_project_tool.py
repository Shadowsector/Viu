"""Инструменты записи в Unity-проект и автонастройки Шани."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict

from ..integrations.unity.animation_scan import ANIMATIONS_REL
from ..integrations.unity.paths import resolve_in_unity_project, unity_project_root
from ..integrations.unity.setup import (
    batch_setup_command,
    batch_sync_animations_command,
    deploy_animation_pipeline,
    deploy_shanya_setup,
    find_unity_exe,
    strip_risky_packages,
)
from ..integrations.unity.verify import verify_unity_project
from .base import AgentContext, Tool, ToolResult


def _root(ctx: AgentContext, args: Dict[str, Any]) -> Path:
    override = args.get("project_path")
    return unity_project_root(ctx.config, override)


class UnityReadTool(Tool):
    name = "unity_read"
    description = (
        "Прочитать файл в Unity-проекте (VIU_UNITY_PROJECT). "
        "Путь относительно корня проекта, напр. Packages/manifest.json"
    )
    parameters = {
        "path": "относительный путь в Unity-проекте",
        "project_path": "корень проекта (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        rel = args.get("path", "")
        if not rel:
            return ToolResult(False, "Не указан path")
        root = _root(ctx, args)
        try:
            target = resolve_in_unity_project(root, rel)
            if not target.is_file():
                return ToolResult(False, f"Файл не найден: {target}")
            return ToolResult(True, target.read_text(encoding="utf-8", errors="replace"))
        except (ValueError, OSError) as exc:
            return ToolResult(False, str(exc))


class UnityWriteTool(Tool):
    name = "unity_write"
    description = (
        "Записать файл в Unity-проект (VIU_UNITY_PROJECT). "
        "Для Editor-скриптов, manifest.json и т.п."
    )
    parameters = {
        "path": "относительный путь",
        "content": "содержимое",
        "project_path": "корень проекта (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        rel = args.get("path", "")
        content = args.get("content", "")
        if not rel:
            return ToolResult(False, "Не указан path")
        root = _root(ctx, args)
        try:
            target = resolve_in_unity_project(root, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolResult(True, f"Записано {len(content)} символов → {target}")
        except (ValueError, OSError) as exc:
            return ToolResult(False, str(exc))


class UnityListTool(Tool):
    name = "unity_list"
    description = "Список файлов в каталоге Unity-проекта"
    parameters = {
        "path": "относительный путь (по умолчанию Assets)",
        "project_path": "корень проекта (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        rel = args.get("path") or "Assets"
        root = _root(ctx, args)
        try:
            target = resolve_in_unity_project(root, rel)
            if not target.is_dir():
                return ToolResult(False, f"Каталог не найден: {target}")
            lines = []
            for p in sorted(target.iterdir()):
                lines.append(p.name + ("/" if p.is_dir() else ""))
            return ToolResult(True, "\n".join(lines) if lines else "(пусто)")
        except (ValueError, OSError) as exc:
            return ToolResult(False, str(exc))


class UnityDeploySetupTool(Tool):
    name = "unity_deploy_setup"
    description=(
        "Скопировать скрипты Viu в Unity: ShanyaSetup, ShanyaAnimationSync, "
        "ShanyaLocomotion, viu_clips.json. Меню: Viu → Setup Shanya / Sync Animations"
    )
    parameters = {"project_path": "корень проекта (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект (нет Assets): {root}")
        ok, msg = deploy_shanya_setup(root)
        hint = (
            "\nДальше: открой Unity → дождись компиляции →\n"
            "  **Viu → Sync Animations** (скан Animations/) или **Setup Shanya (Idle)**\n"
            "Положи FBX в Assets/Characters/Shanya/Animations/ — при открытом Unity импорт подхватится сам.\n"
            "Или: unity_sync_animations / unity_run_setup (batchmode, Unity закрыт)."
        )
        return ToolResult(ok, msg + hint)


class UnityFixManifestTool(Tool):
    name = "unity_fix_manifest"
    description=(
        "Убрать из Packages/manifest.json пакеты, часто ломающие Play "
        "(Input System, AI Navigation). Unity должен быть закрыт."
    )
    parameters = {
        "project_path": "корень проекта (опционально)",
        "packages": "список через запятую (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        pkgs_raw = args.get("packages")
        pkgs = [p.strip() for p in pkgs_raw.split(",") if p.strip()] if pkgs_raw else None
        ok, msg = strip_risky_packages(root, pkgs)
        return ToolResult(ok, msg)


class UnityRunSetupTool(Tool):
    name = "unity_run_setup"
    description=(
        "Запустить Unity в batchmode: deploy ShanyaSetup + Setup Shanya (Idle). "
        "Unity Editor должен быть **закрыт**. Нужен VIU_UNITY_EXE или Hub 6000.3.x."
    )
    parameters = {
        "project_path": "корень проекта (опционально)",
        "timeout": "таймаут секунд (по умолчанию 600)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")
        ok, msg = deploy_shanya_setup(root)
        if not ok:
            return ToolResult(False, msg)
        exe = find_unity_exe(ctx.config.unity_exe)
        if exe is None:
            return ToolResult(
                False,
                "Unity.exe не найден. Задай VIU_UNITY_EXE=путь\\к\\Unity.exe "
                "или установи 6.3 LTS через Hub.",
            )
        cmd = batch_setup_command(root, exe)
        timeout = float(args.get("timeout") or 600)
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(root),
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"Таймаут {timeout}s. Смотри {root / 'viu_setup.log'}")
        log_path = root / "viu_setup.log"
        tail = ""
        if log_path.is_file():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-30:])
        ok_run = proc.returncode == 0
        body = f"exit={proc.returncode}\n{tail or proc.stderr or proc.stdout or '(нет вывода)'}"
        return ToolResult(ok_run, body)


class UnityVerifyTool(Tool):
    name = "unity_verify"
    description=(
        "Проверить результат setup: viu_setup.log, Controller, Editor.log, Play. "
        "После unity_run_setup или Play в Unity."
    )
    parameters = {
        "project_path": "корень проекта (опционально)",
        "log_path": "Editor.log (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from pathlib import Path

        from ..integrations.unity import default_editor_log

        root = _root(ctx, args)
        log_raw = args.get("log_path")
        log_path = Path(log_raw).expanduser() if log_raw else default_editor_log()
        result = verify_unity_project(root, log_path)
        ok = (
            result.setup_log_ok
            and result.controller_found
            and not result.cs_errors
            and not (result.editor_log and (result.editor_log.safe_mode or result.editor_log.playmode_blockers))
        )
        return ToolResult(ok, result.render())


class UnityInitProjectTool(Tool):
    name = "unity_init_project"
    description=(
        "Подготовить чистый Unity-проект для Шани: fix manifest + deploy Editor-скрипты + "
        "записать факты в память. Unity закрыт."
    )
    parameters = {"project_path": "корень проекта (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")
        parts = []
        ok1, msg1 = strip_risky_packages(root)
        parts.append(f"manifest: {msg1}")
        ok2, msg2 = deploy_animation_pipeline(root)
        parts.append(f"pipeline: {msg2}")
        ctx.memory.add(
            f"Unity Шани: проект={root}, LTS 6.3, Humanoid Create From This Model, "
            "Avatar Shanya_ErisaAvatar, без Input System в manifest."
        )
        parts.append("Память: факты проекта записаны.")
        parts.append(
            "\nДальше:\n"
            "1. Открой Unity, импортируй FBX в Assets/Characters/Shanya/\n"
            "2. Анимации (Idle, Walk…) — в Assets/Characters/Shanya/Animations/\n"
            "3. Модель → Rig → Humanoid → Configure → Apply\n"
            "4. Viu → Sync Animations или unity_sync_animations\n"
            "5. Viu → Setup Shanya (Idle) или unity_run_setup\n"
            "6. unity_verify"
        )
        return ToolResult(ok1 and ok2, "\n".join(parts))


class UnityScanAnimationsTool(Tool):
    name = "unity_scan_animations"
    description = (
        "Скан папки Assets/Characters/Shanya/Animations/: классификация FBX "
        "(Idle/Walk/Run…), Humanoid, непонятные имена → ask_user / viu_clips.json"
    )
    parameters = {"project_path": "корень проекта (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.unity.animation_scan import scan_animations_folder

        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")
        scan = scan_animations_folder(root)
        ok = bool(scan.clips) and not scan.questions
        return ToolResult(ok, scan.render())


class UnitySyncAnimationsTool(Tool):
    name = "unity_sync_animations"
    description = (
        "Deploy скриптов + Unity batchmode: ShanyaAnimationSync — Humanoid, "
        "Animator Controller из Animations/*.fbx. Unity Editor должен быть **закрыт**."
    )
    parameters = {
        "project_path": "корень проекта (опционально)",
        "timeout": "таймаут секунд (по умолчанию 600)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")
        ok, msg = deploy_animation_pipeline(root)
        if not ok:
            return ToolResult(False, msg)
        exe = find_unity_exe(ctx.config.unity_exe)
        if exe is None:
            return ToolResult(
                False,
                "Unity.exe не найден. Задай VIU_UNITY_EXE или открой Unity → "
                "меню Viu → Sync Animations (scan folder).",
            )
        cmd = batch_sync_animations_command(root, exe)
        timeout = float(args.get("timeout") or 600)
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(root),
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"Таймаут {timeout}s. Смотри {root / 'viu_anim_sync.log'}")
        log_path = root / "viu_anim_sync.log"
        tail = ""
        if log_path.is_file():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-30:])
        ok_run = proc.returncode == 0
        body = f"{msg}\n\nexit={proc.returncode}\n{tail or proc.stderr or proc.stdout or '(нет вывода)'}"
        return ToolResult(ok_run, body)


class UnityImportStagingTool(Tool):
    name = "unity_import_staging"
    description = (
        "Скопировать *.fbx из папки-входа (VIU_ANIM_STAGING, по умолчанию "
        "U:\\Anabarra\\Animations) в Assets/Characters/Shanya/Animations/"
    )
    parameters = {
        "staging_path": "папка с FBX (опционально)",
        "project_path": "корень Unity-проекта (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        raw = args.get("staging_path") or ctx.config.unity_anim_staging
        staging = Path(raw).expanduser().resolve()
        if not staging.is_dir():
            return ToolResult(
                False,
                f"Папка не найдена: {staging}\n"
                "Положи FBX туда или задай VIU_ANIM_STAGING.",
            )
        dest = resolve_in_unity_project(root, ANIMATIONS_REL)
        dest.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for fbx in sorted(staging.glob("*.fbx")):
            target = dest / fbx.name
            shutil.copy2(fbx, target)
            copied.append(fbx.name)
        if not copied:
            return ToolResult(False, f"В {staging} нет *.fbx")
        lines = [f"Скопировано в {dest}:"]
        lines.extend(f"  + {name}" for name in copied)
        lines.append("\nДальше: Sync Animations (Unity открыт → само, иначе кнопка).")
        return ToolResult(True, "\n".join(lines))
