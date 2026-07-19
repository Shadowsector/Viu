"""Дедуп заметок в каталоге."""

from __future__ import annotations


def append_pipeline_note(existing: str, tag: str, text: str) -> str:
    """Добавить [tag] заметку без точного дубликата строки."""
    line = f"[{tag}] {(text or '').strip()}"
    if not line.strip() or line in (existing or ""):
        return (existing or "").strip()
    base = (existing or "").strip()
    return f"{base}\n{line}".strip() if base else line
