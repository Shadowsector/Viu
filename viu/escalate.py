"""Эскалация сбоев: поиск в сети + отчёт Cursor (не крутить ту же команду)."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from .tools.base import AgentContext


def build_search_query(tool_name: str, error_text: str) -> str:
    err = " ".join((error_text or "").split())[:220]
    return f"Unity 6 {tool_name} {err}".strip()


def escalate_failure(
    ctx: AgentContext,
    *,
    tool_name: str,
    error_text: str,
    task_id: str = "",
    search: bool = True,
) -> Tuple[bool, str]:
    """
    1) web_search по ошибке (если сеть разрешена и это не ложный OK)
    2) cursor_handoff + push — чтобы Cursor увидел лог
    Не зовёт Дена кнопками. Возвращает (ok_handoff, отчёт).
    """
    content = (error_text or "").strip()
    looks_ok = content.startswith("[OK]") or content.lower().startswith("ok:")
    if looks_ok:
        lines: list[str] = [
            f"ПОВТОР: инструмент `{tool_name}` отвечал OK, но вызывался снова.",
            "Это не падение tool — застряла в цикле work-режима.",
        ]
    else:
        lines = [
            f"ЭСКАЛАЦИЯ: инструмент `{tool_name}` не справился.",
        ]
    if task_id:
        lines.append(f"Inbox task: `{task_id}`")
    lines.append("")
    lines.append("Ошибка / лог:" if not looks_ok else "Последний ответ:")
    lines.append(content[:3500] or "(пусто)")

    search_notes = ""
    do_search = search and not looks_ok and getattr(ctx.config, "allow_network", True)
    if do_search:
        try:
            from .tools.web import WebSearchTool

            q = build_search_query(tool_name, error_text)
            sr = WebSearchTool().run({"query": q}, ctx)
            search_notes = sr.content[:2000]
            lines.append("")
            lines.append(f"web_search (`{q}`):")
            lines.append(search_notes if sr.ok else f"(поиск не вышел: {sr.content})")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"\nweb_search исключение: {exc}")

    body = "\n".join(lines)
    handoff_ok = False
    handoff_msg = ""
    try:
        from .integrations.github.handoff import append_handoff, push_handoff

        title = (
            f"REPEAT-OK `{tool_name}`"
            if looks_ok
            else f"ESCALATE `{tool_name}`"
        ) + (f" / {task_id}" if task_id else "")
        append_handoff(title, body[:8000], author="Viu")
        handoff_ok, handoff_msg = push_handoff(message=f"Viu escalate: {tool_name}")
    except Exception as exc:  # noqa: BLE001
        handoff_msg = str(exc)

    lines.append("")
    lines.append(
        "Handoff Cursor: " + ("OK — " + handoff_msg if handoff_ok else "FAIL — " + handoff_msg)
    )
    lines.append(
        "Дальше не крути тот же инструмент. Жди ответ Cursor в VIU_INBOX "
        "или почини по web_search, если фикс ясен."
    )
    return handoff_ok, "\n".join(lines)


def is_soft_failure(tool_name: str, content: str) -> bool:
    """WARN/частичный успех, который нельзя считать done."""
    low = (content or "").lower()
    if tool_name == "overlay_playtest":
        if "--- вердикт ---" in low and (
            "warn:" in low or "fail:" in low or "unknown:" in low or "partial:" in low
        ):
            return True
        if "shanya=false" in low or "сборка fail" in low:
            return True
    return False


def classify_direct_status(tool_name: str, ok: bool, content: str) -> str:
    if not ok or is_soft_failure(tool_name, content):
        return "blocked"
    return "done"
