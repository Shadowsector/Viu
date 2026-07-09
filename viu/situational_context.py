"""Снимок «что вокруг» — для размышления, не для слепого автопилота."""

from __future__ import annotations

from .config import Config


def build_situational_context(config: Config, *, recent_chat: str = "") -> str:
    parts: list[str] = []

    try:
        from .integrations.unity.process import unity_process_running

        if unity_process_running():
            parts.append(
                "Unity Editor **открыт** на машине. Ден может быть не у ПК — "
                "не проси нажать Play; при необходимости закрой unity_close."
            )
        else:
            parts.append("Unity Editor закрыт.")
    except OSError:
        pass

    try:
        from .director import format_banner, plan_next_step

        plan = plan_next_step(config)
        parts.append(
            "Подсказка режиссёра (не выполнять автоматически):\n"
            + format_banner(plan)
        )
    except OSError:
        pass

    try:
        from .vision import read_vision

        parts.append("--- vision.md ---\n" + read_vision(config, max_chars=2500))
    except OSError:
        pass

    if recent_chat.strip():
        parts.append("--- Недавний чат ---\n" + recent_chat.strip()[-2000:])

    return "\n\n".join(parts)


def build_reflect_notes(config: Config) -> str:
    """Фон для reflect — без director-баннера (он делает речь роботом)."""
    parts: list[str] = []

    try:
        from .integrations.unity.process import unity_process_running

        parts.append(
            "Unity открыт — Ден может быть не у ПК."
            if unity_process_running()
            else "Unity закрыт."
        )
    except OSError:
        pass

    try:
        from .vision import read_vision

        parts.append(read_vision(config, max_chars=1800))
    except OSError:
        pass

    try:
        from .memory import MemoryStore

        recent = MemoryStore(config.data_dir / "memory.json").recent(limit=3)
        if recent:
            parts.append(
                "Память:\n" + "\n".join(f"- {r.text}" for r in recent)
            )
    except OSError:
        pass

    return "\n\n".join(parts) if parts else "(заметок пока мало)"
