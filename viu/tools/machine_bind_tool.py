"""Инструмент привязки личной установки к машине."""

from __future__ import annotations

from typing import Any, Dict

from ..machine_bind import ensure_bind, rebind, require_personal_machine, status_text, verify_bind
from .base import AgentContext, Tool, ToolResult


class MachineBindTool(Tool):
    name = "machine_bind"
    description = (
        "Личная привязка Вью к компу Дена (user+host+пути U:, не материнка/GPU). "
        "action=status|ensure|rebind|check. После апгрейда железа — rebind."
    )
    parameters = {
        "action": "status | ensure | rebind | check",
        "reason": "для rebind — зачем (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        action = str(args.get("action") or "status").strip().lower()
        if action in ("status", "show"):
            return ToolResult(ok=True, content=status_text(ctx.config))
        if action == "ensure":
            bind, created = ensure_bind(ctx.config)
            verb = "создана" if created else "уже есть"
            return ToolResult(
                ok=True,
                content=f"привязка {verb}: install_id={bind.install_id}\n{status_text(ctx.config)}",
            )
        if action == "rebind":
            reason = str(args.get("reason") or "hardware_or_paths_changed").strip()
            bind, msg = rebind(ctx.config, reason=reason)
            return ToolResult(
                ok=True,
                content=f"{msg}\ninstall_id={bind.install_id}\n{status_text(ctx.config)}",
            )
        if action == "check":
            ok, msg = require_personal_machine(ctx.config, auto_ensure=True)
            return ToolResult(ok=ok, content=msg if ok else f"блок: {msg}")
        return ToolResult(ok=False, content="action: status|ensure|rebind|check")
