"""Запрет git через run_shell — только cursor_push и zip-обновление."""

from __future__ import annotations

import re

_GIT_SHELL_RE = re.compile(
    r"(^|[;&|]\s*)git\s+(init|add|commit|push|pull|fetch|remote|clone|checkout|merge|rebase)\b",
    re.IGNORECASE,
)


def shell_git_blocked(command: str) -> str | None:
    if _GIT_SHELL_RE.search(command or ""):
        return (
            "Git через run_shell запрещён (ломает zip-установку). "
            "Handoff → cursor_push / cursor_handoff_with_logs. "
            "Обновление Viu → кнопка «Обновить Вью»."
        )
    if re.search(r"\bgit\s+init\b", command or "", re.I):
        return "git init запрещён — не создавай .git в U:\\Viu."
    return None
