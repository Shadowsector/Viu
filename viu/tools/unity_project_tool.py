"""Инструменты записи в Unity-проект и автонастройки Шани."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

from ..integrations.unity.paths import resolve_in_unity_project, unity_project_root
from ..integrations.unity.setup import (
    batch_setup_command,
    deploy_shanya_setup,
    find_unity_exe,
    strip_risky_packages,
)
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
        "Скопировать Editor-скрипт Viu (ShanyaSetup.cs) в Unity-проект. "
        "После этого в Unity: меню Viu → Setup Shanya (Idle)"
    )
    parameters = {"project_path": "корень проекта (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект (нет Assets): {root}")
        ok, msg = deploy_shanya_setup(root)
        hint = (
            "\nДальше: открой Unity → дождись компиляции → "
            "меню **Viu → Setup Shanya (Idle)**\n"
            "Или: unity_run_setup (batchmode, Unity закрыт)."
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
