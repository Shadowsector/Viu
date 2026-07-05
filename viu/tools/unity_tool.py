"""Инструменты Вью для Unity-проекта Анабарра."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ..integrations.unity import (
    default_editor_log,
    extract_compiler_errors,
    parse_editor_log,
    scan_unity_project,
    workflow_status_text,
)
from .base import AgentContext, Tool, ToolResult


def _unity_project(ctx: AgentContext) -> Path:
    raw = ctx.config.unity_project or ""
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / "Anabarra" / "Unity"  # типичный путь пользователя


class UnityLogTool(Tool):
    name = "unity_log"
    description = (
        "Прочитать хвост Unity Editor.log — ошибки Rig, компиляции, WGT-предупреждения"
    )
    parameters = {
        "log_path": "путь к Editor.log (опционально)",
        "lines": "сколько последних строк анализировать (по умолчанию 400)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        log_path = args.get("log_path")
        path = Path(log_path).expanduser() if log_path else default_editor_log()
        lines = int(args.get("lines") or 400)
        summary = parse_editor_log(path, tail_lines=lines)
        ok = not (summary.playmode_blockers or summary.compiler_errors or summary.rig_errors)
        return ToolResult(ok, summary.render())


class UnityScanTool(Tool):
    name = "unity_scan"
    description = (
        "Сканировать Unity-проект: FBX, Humanoid/.meta, проблемы Copy Avatar"
    )
    parameters = {"project_path": "путь к корню Unity-проекта (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        proj = args.get("project_path")
        root = Path(proj).expanduser() if proj else _unity_project(ctx)
        scan = scan_unity_project(root)
        ok = not any(f.copy_avatar for f in scan.fbx_files) and bool(scan.fbx_files)
        if not root.is_dir():
            return ToolResult(False, scan.render())
        return ToolResult(ok, scan.render())


class UnityWorkflowTool(Tool):
    name = "unity_workflow"
    description = "Показать чеклист пайплайна Шани: Blender → FBX → Unity → Mixamo"
    parameters = {"step": "номер текущего шага 1–6 (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        step = args.get("step")
        current = int(step) if step is not None else None
        return ToolResult(True, workflow_status_text(current_step=current))


class UnityReportTool(Tool):
    name = "unity_report"
    description = (
        "Полный отчёт для отладки: Editor.log + скан FBX (как check_unity.bat)"
    )
    parameters = {
        "project_path": "путь к Unity-проекту (опционально)",
        "log_path": "путь к Editor.log (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        log_path = args.get("log_path")
        path = Path(log_path).expanduser() if log_path else default_editor_log()
        log_sum = parse_editor_log(path)
        all_cs = extract_compiler_errors(path)
        parts = [log_sum.render()]
        if all_cs:
            parts.extend(["", f"=== Все CS-ошибки в логе ({len(all_cs)} уникальных) ==="])
            parts.extend(all_cs[:80])
            if len(all_cs) > 80:
                parts.append(f"... и ещё {len(all_cs) - 80}")
        parts.append("")
        parts.append(workflow_status_text(current_step=5))
        if scan:
            parts.extend(["", scan.render()])
        elif root:
            parts.append(f"\nUnity-проект не найден: {root}\nЗадай VIU_UNITY_PROJECT=путь")
        ok = not (log_sum.rig_errors or log_sum.compiler_errors or log_sum.playmode_blockers)
        proj_note = ""
        if proj and ("..." in str(proj) or not root.is_dir()):
            proj_note = (
                f"\n⚠ Путь Unity-проекта неверный: {root}\n"
                "  Задай реальный путь, например:\n"
                "  set VIU_UNITY_PROJECT=C:\\Users\\Den\\My project\n"
            )
        return ToolResult(ok, "\n".join(parts) + proj_note)
