"""Инструмент выполнения shell-команд (управление локальным ПО).

Команды выполняются в корне песочницы с таймаутом. Выполнение можно
полностью отключить через VIU_ALLOW_SHELL=0.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any, Dict

from ..shell_guard import shell_git_blocked
from .base import AgentContext, Tool, ToolResult


class ShellTool(Tool):
    name = "run_shell"
    description = "Выполнить shell-команду в корне рабочего каталога"
    parameters = {"command": "команда для оболочки", "timeout": "таймаут в секундах (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        if not ctx.config.allow_shell:
            return ToolResult(False, "Выполнение shell отключено (VIU_ALLOW_SHELL=0)")
        command = args.get("command", "")
        if not command:
            return ToolResult(False, "Не указана command")
        blocked = shell_git_blocked(str(command))
        if blocked:
            return ToolResult(False, blocked)
        try:
            timeout = float(args.get("timeout", 60))
        except (TypeError, ValueError):
            timeout = 60.0
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(ctx.config.root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"Команда превысила таймаут {timeout}s")
        except OSError as exc:
            return ToolResult(False, str(exc))

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        parts = [f"exit_code={proc.returncode}"]
        if out:
            parts.append(f"stdout:\n{out}")
        if err:
            parts.append(f"stderr:\n{err}")
        return ToolResult(proc.returncode == 0, "\n".join(parts))
