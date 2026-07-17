"""Флаги занятости GUI: tool (Comfy/lab) vs LLM (думает).

Comfy крутит GPU — LLM свободна. Блокировать чат/Telegram из‑за lab нельзя.
"""

from __future__ import annotations


def can_accept_chat(*, llm_busy: bool) -> bool:
    """Чат и Telegram-болтовня: только пока модель не думает."""
    return not llm_busy


def can_accept_scripts(*, tool_busy: bool, llm_busy: bool) -> bool:
    """Сайдбар кликабелен во время Comfy/lab; блокируем только пока LLM думает.

    Повторный tool при tool_busy отклонит ``_run_tool`` сообщением — чат свободен.
    """
    del tool_busy  # намеренно: долгий Comfy не серит кнопки
    return not llm_busy


def can_start_tool(*, tool_busy: bool) -> bool:
    """Второй параллельный tool (ещё один lab) — нет."""
    return not tool_busy


def can_run_background_tick(*, tool_busy: bool, llm_busy: bool) -> bool:
    """Heartbeat / lab tick / inbox — не мешать активной работе."""
    return not tool_busy and not llm_busy


def busy_status_ru(*, tool_busy: bool, llm_busy: bool) -> str:
    if llm_busy and tool_busy:
        return "думает + lab/Comfy"
    if llm_busy:
        return "думает"
    if tool_busy:
        return "lab/Comfy (чат и кнопки свободны)"
    return "нет"
